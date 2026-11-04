"""Runs, the persistent model queue and the four agents.

The queue lives in SQLite. One worker thread takes one task at a time, so only one model request
is ever in flight. Tasks survive restarts: anything left "running" is put back in the queue.
Before a task is queued its cache key is computed from the source content, prompt version, model
identity and (where relevant) profile and preference versions; an existing result with that key
is reused and counted as a cache hit. A task that fails is retried a bounded number of times with
backoff, then marked failed; it never blocks the tasks behind it. When the model server is down or
serving another model, tasks wait without spending attempts.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

from . import analysis, collect
from .config import Config
from .db import DB, now_iso
from .llm import LocalModel, ModelError, ModelUnavailable
from .netsafe import Fetcher
from .profile import ProfileStore

log = logging.getLogger("signaldesk")

AGENTS = {
    "job_scout": "Job Scout",
    "reading_scout": "Reading Scout",
    "case_analyst": "Case Study Analyst",
    "digest_editor": "Digest Editor",
}
ACTIVE = ("collecting", "analysing")
STALE_JOB_HOURS = 48


class Cancelled(Exception):
    pass


def _iso_in(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


class Engine:
    def __init__(self, cfg: Config, db: DB, model: LocalModel, fetcher: Fetcher, *, start_worker: bool = True):
        self.cfg, self.db, self.model, self.fetcher = cfg, db, model, fetcher
        self.profiles = ProfileStore(cfg.profile_path, db)
        self.wake = threading.Event()
        self.stop_flag = threading.Event()
        self.model_state = {"ready": False, "message": "Not checked yet", "checked_at": None}
        self.current_task: int | None = None
        self._resume()
        self.worker = None
        if start_worker:
            self.worker = threading.Thread(target=self._loop, name="signaldesk-queue", daemon=True)
            self.worker.start()

    # ------------------------------------------------------------ runs
    def _resume(self) -> None:
        """After a restart: put interrupted tasks back in the queue; close runs that cannot continue."""
        n = self.db.run("UPDATE tasks SET status = 'queued', note = 'Resumed after restart' WHERE status = 'running'")
        for r in self.db.all("SELECT id FROM runs WHERE status = 'collecting'"):
            self._log(r["id"], "The app stopped during collection. Saved results were kept; start a new run to collect again.")
            self.db.update("runs", r["id"], {"status": "failed", "finished_at": now_iso()})
        self._settle_runs()

    def active_runs(self) -> list[dict]:
        return self.db.all(f"SELECT * FROM runs WHERE status IN {ACTIVE} ORDER BY id")

    def _log(self, run_id: int, msg: str) -> None:
        row = self.db.one("SELECT log_json FROM runs WHERE id = ?", (run_id,))
        entries = json.loads(row["log_json"]) if row else []
        entries.append({"at": now_iso(), "msg": msg})
        self.db.update("runs", run_id, {"log_json": json.dumps(entries[-200:])})

    def _stat(self, run_id: int, **inc) -> None:
        with self.db.write_lock:
            row = self.db.one("SELECT stats_json FROM runs WHERE id = ?", (run_id,))
            stats = json.loads(row["stats_json"])
            for k, v in inc.items():
                stats[k] = stats.get(k, 0) + v if isinstance(v, (int, float)) else v
            self.db.update("runs", run_id, {"stats_json": json.dumps(stats)})

    def start_run(self, agent: str, trigger: str = "manual", group_id: str | None = None) -> dict:
        if agent not in AGENTS:
            raise ValueError("Unknown agent")
        with self.db.write_lock:
            busy = self.db.one(f"SELECT id FROM runs WHERE agent = ? AND status IN {ACTIVE}", (agent,))
            if busy:
                return {"id": busy["id"], "already_running": True}
            run_id = self.db.insert("runs", {"agent": agent, "trigger": trigger, "group_id": group_id, "status": "collecting",
                                             "started_at": now_iso(), "stats_json": "{}", "log_json": "[]"})
        threading.Thread(target=self._run_body, args=(run_id, agent), name=f"run-{run_id}", daemon=True).start()
        return {"id": run_id, "already_running": False}

    def start_all(self, trigger: str = "manual") -> dict:
        """Job Scout and Reading Scout collect now; the Case Study Analyst and Digest Editor are queued
        behind their analyses, so they see this run's results."""
        if self.active_runs():
            return {"started": [], "skipped": "A run is already in progress."}
        group = uuid.uuid4().hex[:8]
        started = [self.start_run(a, trigger, group)["id"] for a in ("job_scout", "reading_scout")]
        started.append(self.start_run("case_analyst", trigger, group)["id"])
        started.append(self.start_run("digest_editor", trigger, group)["id"])
        return {"started": started, "group": group}

    def cancel_run(self, run_id: int) -> dict:
        self.db.run("UPDATE runs SET cancel_requested = 1 WHERE id = ?", (run_id,))
        n = self.db.conn.execute("SELECT COUNT(*) FROM tasks WHERE run_id = ? AND status = 'queued'", (run_id,)).fetchone()[0]
        self.db.run("UPDATE tasks SET status = 'cancelled', finished_at = ?, note = 'Cancelled before it started' WHERE run_id = ? AND status = 'queued'",
                    (now_iso(), run_id))
        self._log(run_id, f"Cancel requested: {n} queued task(s) cancelled. A model request already in progress finishes and its result is kept.")
        self._settle_runs()
        return {"cancelled_tasks": n}

    def retry_failed(self, run_id: int) -> int:
        n = self.db.scalar("SELECT COUNT(*) FROM tasks WHERE run_id = ? AND status = 'failed'", (run_id,))
        self.db.run("UPDATE tasks SET status = 'queued', attempts = 0, error = NULL, note = 'Retried by you', next_attempt_at = NULL "
                    "WHERE run_id = ? AND status = 'failed'", (run_id,))
        if n:
            self.db.update("runs", run_id, {"status": "analysing", "finished_at": None, "cancel_requested": 0})
            self.wake.set()
        return n

    def _cancelled(self, run_id: int) -> bool:
        return bool(self.db.scalar("SELECT cancel_requested FROM runs WHERE id = ?", (run_id,)))

    def _run_body(self, run_id: int, agent: str) -> None:
        try:
            getattr(self, f"_collect_{agent}")(run_id)
            if self._cancelled(run_id):
                self.db.update("runs", run_id, {"status": "cancelled", "finished_at": now_iso()})
                return
            self.db.update("runs", run_id, {"status": "analysing"})
            self._settle_runs()
            self.wake.set()
        except Exception as e:  # noqa: BLE001 - a run must always end in a visible state
            log.error("run %s failed: %s", run_id, traceback.format_exc())
            self._log(run_id, f"Run failed: {type(e).__name__}: {e}")
            self.db.update("runs", run_id, {"status": "failed", "finished_at": now_iso()})

    def _settle_runs(self) -> None:
        """Close analysing runs whose tasks have all finished."""
        for r in self.db.all("SELECT id, cancel_requested FROM runs WHERE status = 'analysing'"):
            counts = {row["status"]: row["n"] for row in self.db.all("SELECT status, COUNT(*) n FROM tasks WHERE run_id = ? GROUP BY status", (r["id"],))}
            if counts.get("queued") or counts.get("running"):
                continue
            status = "cancelled" if r["cancel_requested"] else ("done_with_errors" if counts.get("failed") else "done")
            self.db.update("runs", r["id"], {"status": status, "finished_at": now_iso()})

    # ------------------------------------------------------------ enqueue with cache
    def enqueue(self, run_id: int | None, kind: str, target_type: str, target_id: int, key: str, priority: int = 50) -> str:
        if self.db.scalar("SELECT 1 FROM analyses WHERE cache_key = ?", (key,)):
            if run_id:
                self._stat(run_id, cache_hits=1)
                self.db.insert("tasks", {"run_id": run_id, "kind": kind, "target_type": target_type, "target_id": target_id, "cache_key": key,
                                         "status": "cached", "created_at": now_iso(), "finished_at": now_iso(), "note": "Saved result reused",
                                         "priority": priority, "max_attempts": self.cfg.model.max_attempts})
            return "cached"
        if self.db.scalar("SELECT 1 FROM tasks WHERE cache_key = ? AND status IN ('queued', 'running')", (key,)):
            return "already queued"
        self.db.insert("tasks", {"run_id": run_id, "kind": kind, "target_type": target_type, "target_id": target_id, "cache_key": key,
                                 "status": "queued", "created_at": now_iso(), "priority": priority, "max_attempts": self.cfg.model.max_attempts})
        self.wake.set()
        return "queued"

    def key_for(self, kind: str, target_id: int) -> str | None:
        m = self.cfg.model.model_id
        if kind == "job_fit":
            job = self.db.one("SELECT content_hash FROM jobs WHERE id = ?", (target_id,))
            return job and analysis.cache_key(kind, model_id=m, content=job["content_hash"], extra={
                "profile": self.profiles.profile_version(), "budget": self.cfg.model.prompt_char_budget})
        if kind in ("reading_card", "case_study"):
            a = self.db.one("SELECT content_hash FROM articles WHERE id = ?", (target_id,))
            extra = {"budget": self.cfg.model.prompt_char_budget}
            if kind == "reading_card":
                extra["prefs"] = self.profiles.prefs_version(("reading_interests",))
            return a and analysis.cache_key(kind, model_id=m, content=a["content_hash"], extra=extra)
        return None

    def analyse(self, kind: str, target_id: int, run_id: int | None = None, priority: int = 20) -> str:
        key = self.key_for(kind, target_id)
        if not key:
            raise ValueError("Item not found")
        return self.enqueue(run_id, kind, "job" if kind == "job_fit" else "article", target_id, key, priority)

    def latest(self, kind: str, target_type: str, target_id: int) -> dict | None:
        row = self.db.one("SELECT * FROM analyses WHERE kind = ? AND target_type = ? AND target_id = ? ORDER BY id DESC LIMIT 1",
                          (kind, target_type, target_id))
        if not row:
            return None
        current = self.key_for(kind, target_id) if kind != "digest_action" else row["cache_key"]
        return {"id": row["id"], "output": json.loads(row["output_json"]), "validation": json.loads(row["validation_json"]),
                "inputs": json.loads(row["inputs_json"]), "model_id": row["model_id"], "prompt_version": row["prompt_version"],
                "created_at": row["created_at"], "outdated": current != row["cache_key"]}

    # ------------------------------------------------------------ collection phases
    def _collect_job_scout(self, run_id: int) -> None:
        prefs = self.profiles.prefs()
        results = collect.collect_jobs(self.db, self.fetcher, prefs, cancelled=lambda: self._cancelled(run_id))
        totals = {"sources_ok": 0, "sources_failed": 0, "fetched": 0, "new": 0, "changed": 0, "closed": 0}
        for r in results:
            if r.get("error"):
                totals["sources_failed"] += 1
                self._log(run_id, f"{r['company']}: fetch failed ({r['error']}). Its jobs were left as they were.")
            elif r.get("warning"):
                totals["sources_failed"] += 1
                self._log(run_id, f"{r['company']}: {r['warning']}")
            elif not r.get("skipped"):
                totals["sources_ok"] += 1
                for k in ("fetched", "new", "changed", "closed"):
                    totals[k] += r.get(k, 0)
        self._stat(run_id, **totals)
        self._log(run_id, f"Checked {totals['sources_ok']} employer boards ({totals['sources_failed']} with problems): "
                          f"{totals['fetched']} listings, {totals['new']} new, {totals['changed']} changed, {totals['closed']} no longer listed.")
        if self._cancelled(run_id):
            return
        limit = self.cfg.limits.max_job_analyses_per_run
        rows = self.db.all(
            "SELECT id FROM jobs WHERE bucket = 'candidate' AND listing_state = 'open' AND duplicate_of IS NULL "
            "AND status NOT IN ('Not relevant', 'Archived') ORDER BY (change_state != 'unchanged') DESC, first_seen_at DESC LIMIT ?", (limit,))
        queued = sum(self.analyse("job_fit", r["id"], run_id, 30) == "queued" for r in rows)
        self._stat(run_id, queued_for_analysis=queued)
        self._log(run_id, f"{len(rows)} matching jobs considered for fit analysis (limit {limit}); {queued} need the model.")

    def _collect_reading_scout(self, run_id: int) -> None:
        results = collect.collect_reading(self.db, self.fetcher, self.cfg.limits.items_per_feed, cancelled=lambda: self._cancelled(run_id))
        totals = {"sources_ok": 0, "sources_failed": 0, "fetched": 0, "new": 0, "duplicate": 0}
        for r in results:
            if r.get("error"):
                totals["sources_failed"] += 1
                self._log(run_id, f"{r['source']}: fetch failed ({r['error']}).")
            elif not r.get("skipped"):
                totals["sources_ok"] += 1
                for k in ("fetched", "new", "duplicate"):
                    totals[k] += r.get(k, 0)
        self._stat(run_id, **totals)
        self._log(run_id, f"Read {totals['sources_ok']} feeds ({totals['sources_failed']} failed): {totals['fetched']} items, "
                          f"{totals['new']} new, {totals['duplicate']} repeats of items already saved.")
        if self._cancelled(run_id):
            return
        prefs = self.profiles.prefs()
        muted = tuple(prefs.get("muted_sources") or [-1])
        limit = self.cfg.limits.max_article_cards_per_run
        rows = self.db.all(
            f"SELECT a.id FROM articles a LEFT JOIN feedback f ON f.item_type = 'article' AND f.item_id = a.id "
            f"WHERE a.duplicate_of IS NULL AND a.content_basis != 'metadata' AND f.id IS NULL "
            f"AND COALESCE(a.source_id, -2) NOT IN ({','.join('?' * len(muted))}) "
            f"ORDER BY COALESCE(a.published_at, a.retrieved_at) DESC LIMIT ?", (*muted, limit))
        queued = sum(self.analyse("reading_card", r["id"], run_id, 40) == "queued" for r in rows)
        self._stat(run_id, queued_for_analysis=queued)
        self._log(run_id, f"{len(rows)} recent articles considered for reading cards (limit {limit}); {queued} need the model.")

    def _collect_case_analyst(self, run_id: int) -> None:
        # Selection waits in the queue behind reading cards, so it can use their "case study" labels.
        self.db.insert("tasks", {"run_id": run_id, "kind": "case_select", "target_type": "run", "target_id": run_id, "status": "queued",
                                 "created_at": now_iso(), "priority": 60, "max_attempts": 1})
        self._log(run_id, "Waiting for reading cards, then choosing case-study candidates.")

    def _collect_digest_editor(self, run_id: int) -> None:
        self.db.insert("tasks", {"run_id": run_id, "kind": "digest_compose", "target_type": "run", "target_id": run_id, "status": "queued",
                                 "created_at": now_iso(), "priority": 90, "max_attempts": 2})
        self._log(run_id, "The briefing is composed after queued analyses finish.")

    # ------------------------------------------------------------ the worker
    def check_model(self) -> dict:
        st = self.model.status()
        self.model_state = {**st, "checked_at": now_iso()}
        return self.model_state

    GATED = ("case_select", "digest_compose")

    def _next_task(self) -> dict | None:
        """Highest-priority ready task. Case selection and briefing composition wait while any run is
        still collecting or any earlier-stage analysis is queued, unless the model is unavailable, in
        which case they go ahead and mark what is still pending."""
        rows = self.db.all("SELECT * FROM tasks WHERE status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
                           "ORDER BY priority, id LIMIT 20", (now_iso(),))
        for t in rows:
            if t["kind"] not in self.GATED:
                return t
            if self.db.scalar("SELECT 1 FROM runs WHERE status = 'collecting'"):
                continue
            earlier = self.db.scalar("SELECT COUNT(*) FROM tasks WHERE status IN ('queued', 'running') AND priority < ? AND id != ?",
                                     (t["priority"], t["id"]))
            if earlier and self.model_state.get("ready", False):
                continue
            return t
        return None

    def _loop(self) -> None:
        while not self.stop_flag.is_set():
            try:
                worked = self.step()
            except Exception:  # noqa: BLE001
                log.error("queue loop error: %s", traceback.format_exc())
                worked = False
            if not worked:
                self.wake.wait(5)
                self.wake.clear()

    def step(self) -> bool:
        """Process at most one task. Returns True when a task was handled."""
        task = self._next_task()
        if not task:
            self._settle_runs()
            return False
        if task["kind"] not in self.GATED and not self.check_model()["ready"]:
            # Model tasks wait without spending attempts; rule-based steps can still go ahead.
            task = None
            if not self.db.scalar("SELECT 1 FROM runs WHERE status = 'collecting'"):
                task = self.db.one(f"SELECT * FROM tasks WHERE status = 'queued' AND kind IN {self.GATED} ORDER BY priority, id LIMIT 1")
            if not task:
                return False
        self.db.update("tasks", task["id"], {"status": "running", "started_at": now_iso(), "attempts": task["attempts"] + 1})
        self.current_task = task["id"]
        try:
            note = getattr(self, f"_do_{task['kind']}")(task)
            if task["error"]:  # keep why the earlier attempt failed
                note = f"{note}. Succeeded on attempt {task['attempts'] + 1}; earlier attempt: {task['error']}"
            self.db.update("tasks", task["id"], {"status": "done", "finished_at": now_iso(), "error": None, "note": note})
            if task["run_id"]:
                self._stat(task["run_id"], analysed=1 if task["kind"] in ("job_fit", "reading_card", "case_study") else 0)
        except ModelUnavailable as e:
            self.db.update("tasks", task["id"], {"status": "queued", "attempts": task["attempts"], "note": f"Waiting for the model: {e}"})
            self.model_state = {**self.model_state, "ready": False, "message": str(e)}
        except Exception as e:  # noqa: BLE001 - one failing task must not stop the queue
            attempts = task["attempts"] + 1
            msg = f"{type(e).__name__}: {e}"[:500]
            if attempts < task["max_attempts"]:
                self.db.update("tasks", task["id"], {"status": "queued", "error": msg, "next_attempt_at": _iso_in(10 * 2 ** attempts)})
                if task["run_id"]:
                    self._stat(task["run_id"], retries=1)
            else:
                self.db.update("tasks", task["id"], {"status": "failed", "error": msg, "finished_at": now_iso()})
                if task["run_id"]:
                    self._stat(task["run_id"], errors=1)
                    self._log(task["run_id"], f"Task {task['id']} ({task['kind']} for {task['target_type']} {task['target_id']}) failed after {attempts} attempt(s): {msg}")
        finally:
            self.current_task = None
        self._settle_runs()
        return True

    def _call(self, task: dict, purpose: str, prompt: str, max_tokens: int | None = None):
        rec = {"task_id": task["id"], "run_id": task["run_id"], "purpose": purpose, "model_requested": self.cfg.model.model_id, "started_at": now_iso()}
        try:
            reply = self.model.chat(analysis.SYSTEM, prompt, max_tokens=max_tokens)
        except Exception as e:
            self.db.insert("model_calls", {**rec, "ok": 0, "error": str(e)[:300]})
            raise
        self.db.insert("model_calls", {**rec, "model_served": reply.model_served, "duration_ms": reply.duration_ms, "tokens_in": reply.tokens_in,
                                       "tokens_out": reply.tokens_out, "finish_reason": reply.finish_reason, "ok": 1})
        if task["run_id"]:
            self._stat(task["run_id"], model_requests=1, model_ms=reply.duration_ms, tokens_in=reply.tokens_in or 0, tokens_out=reply.tokens_out or 0)
        if reply.model_served != self.cfg.model.model_id:
            raise ModelUnavailable(f"The reply came from {reply.model_served}, not the configured {self.cfg.model.model_id}; it was discarded.")
        if reply.finish_reason == "length":
            raise ModelError("The reply was cut off at the output limit.")
        return reply

    def _budget(self, task: dict) -> int:
        # Each retry sends less text, in case the request was too long for the context window.
        return int(self.cfg.model.prompt_char_budget * (0.75 ** max(0, task["attempts"])))

    def _save(self, task: dict, kind: str, target_type: str, output: dict, validation: dict, inputs: dict, model_id: str) -> None:
        self.db.run("INSERT OR REPLACE INTO analyses (kind, target_type, target_id, cache_key, prompt_version, model_id, inputs_json, output_json, validation_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (kind, target_type, task["target_id"], task["cache_key"], analysis.PROMPT_VERSIONS[kind], model_id,
                     json.dumps(inputs), json.dumps(output), json.dumps(validation), now_iso()))

    def _do_job_fit(self, task: dict) -> str:
        job = self.db.one("SELECT * FROM jobs WHERE id = ?", (task["target_id"],))
        profile = self.profiles.profile()
        # Bind both the cache and provenance to the exact CV snapshot read here,
        # even if the user edits the profile while a queued/requested job runs.
        profile_version = analysis.sha(profile['facts'], profile.get('not_claimed', []))[:12]
        task['cache_key'] = analysis.cache_key('job_fit', model_id=self.cfg.model.model_id,
            content=job['content_hash'], extra={'profile': profile_version, 'budget': self.cfg.model.prompt_char_budget})
        self.db.update('tasks', task['id'], {'cache_key': task['cache_key']})
        prompt, cov = analysis.job_prompt(job, profile, self._budget(task))
        reply = self._call(task, "job_fit", prompt)
        sent_profile = {**profile, "facts": [f for f in profile["facts"] if f["id"] in cov["profile_fact_ids"]]}
        out, val = analysis.validate_job(analysis.parse_json(reply.text), job, sent_profile)
        if len(sent_profile['facts']) < len(profile['facts']):
            val['notes'].append(f"Used {len(sent_profile['facts'])} of {len(profile['facts'])} profile facts, selected by keyword overlap. Other experience may have been missed; this is a partial assessment.")
        # Fact ids are renumbered when the profile changes, so keep the exact text
        # each cited id had when this assessment was made.
        inputs = {"coverage": cov, "profile_version": profile_version, "facts_sent": sent_profile["facts"],
                  "tokens_in": reply.tokens_in, "tokens_out": reply.tokens_out}
        self._save(task, "job_fit", "job", out, val, inputs, reply.model_served)
        return f"Analysed {cov['chars_sent']:,} of {cov['chars_total']:,} characters"

    def _do_reading_card(self, task: dict) -> str:
        art = self.db.one("SELECT * FROM articles WHERE id = ?", (task["target_id"],))
        prompt, cov = analysis.card_prompt(art, self.profiles.prefs()["reading_interests"], self._budget(task))
        reply = self._call(task, "reading_card", prompt)
        out, val = analysis.validate_card(analysis.parse_json(reply.text), art)
        if out["kind"] == "case_study" and art["content_basis"] == "full":
            self.db.run("UPDATE articles SET case_candidate = 1 WHERE id = ?", (art["id"],))
        self._save(task, "reading_card", "article", out, val, {"coverage": cov, "basis": art["content_basis"]}, reply.model_served)
        return f"Card from {cov['chars_sent']:,} of {cov['chars_total']:,} characters ({art['content_basis']})"

    def _do_case_study(self, task: dict) -> str:
        art = self.db.one("SELECT * FROM articles WHERE id = ?", (task["target_id"],))
        budget = self._budget(task)
        pa, cov = analysis.case_prompt(art, "a", budget)
        a = analysis.parse_json(self._call(task, "case_study_a", pa).text)
        pb, _ = analysis.case_prompt(art, "b", budget)
        rb = self._call(task, "case_study_b", pb)
        out, val = analysis.validate_case(a, analysis.parse_json(rb.text), art)
        self._save(task, "case_study", "article", out, val, {"coverage": cov, "basis": art["content_basis"]}, rb.model_served)
        return f"Case study from {cov['chars_sent']:,} of {cov['chars_total']:,} characters; suitability {out['suitability']}"

    def _do_case_select(self, task: dict) -> str:
        run_id = task["run_id"]
        limit = self.cfg.limits.max_case_studies_per_run
        rows = self.db.all(
            "SELECT a.id FROM articles a WHERE a.case_candidate = 1 AND a.duplicate_of IS NULL AND a.content_basis = 'full' "
            "AND NOT EXISTS (SELECT 1 FROM feedback f WHERE f.item_type = 'article' AND f.item_id = a.id AND f.verdict = 'not_relevant') "
            "ORDER BY (a.origin = 'manual') DESC, COALESCE(a.published_at, a.retrieved_at) DESC LIMIT ?", (limit,))
        queued = sum(self.analyse("case_study", r["id"], run_id, 70) == "queued" for r in rows)
        self._stat(run_id, candidates=len(rows), queued_for_analysis=queued)
        msg = (f"{len(rows)} case-study candidate(s) with full text; {queued} need the model." if rows else
               "No article with full text looked like a case study. None was analysed.")
        self._log(run_id, msg)
        return msg

    def _do_digest_compose(self, task: dict) -> str:
        from .digest import compose
        digest = compose(self, task)
        self._log(task["run_id"], f"Briefing {digest['id']} saved.")
        return f"Briefing {digest['id']} saved"
