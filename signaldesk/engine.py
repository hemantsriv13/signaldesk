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

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from . import analysis, collect, contacts, funding, registry, sweep
from .config import Config
from .db import DB, now_iso
from .llm import LocalModel, ModelError, ModelUnavailable
from .netsafe import FetchError, Fetcher
from .profile import ProfileStore
from .sources import web

log = logging.getLogger("signaldesk")

AGENTS = {
    "funding_scout": "Funding Scout",
    "job_scout": "Job Scout",
    "reading_scout": "Reading Scout",
    "case_analyst": "Case Study Analyst",
    "contact_scout": "Contact Scout",
    "digest_editor": "Digest Editor",
    "source_refresh": "Source refresh",
}
MODEL_KINDS = ("job_fit", "reading_card", "case_study", "role_classify", "funding_extract", "outreach_draft")
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
        self.escalation = None
        if cfg.model.escalation_model_id:
            esc = replace(cfg.model, model_id=cfg.model.escalation_model_id, base_url=cfg.model.escalation_base_url or cfg.model.base_url)
            self.escalation = LocalModel(esc)
        self.messaging = contacts.NoMessaging()     # no authorised messaging integration exists for this project
        self._start_lock = threading.Lock()
        self._claim_lock = threading.Lock()
        self._resume()
        self.worker = None
        self.workers: list[threading.Thread] = []
        if start_worker:
            for i in range(max(1, cfg.model.concurrency)):
                t = threading.Thread(target=self._loop, name=f"signaldesk-queue-{i}", daemon=True)
                t.start()
                self.workers.append(t)
            self.worker = self.workers[0]

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

    def start_run(self, agent: str, trigger: str = "manual", group_id: str | None = None, options: dict | None = None) -> dict:
        if agent not in AGENTS:
            raise ValueError("Unknown agent")
        with self.db.write_lock:
            busy = self.db.one(f"SELECT id FROM runs WHERE agent = ? AND status IN {ACTIVE}", (agent,))
            if busy:
                return {"id": busy["id"], "already_running": True}
            run_id = self.db.insert("runs", {"agent": agent, "trigger": trigger, "group_id": group_id, "status": "collecting",
                                             "started_at": now_iso(), "stats_json": "{}", "log_json": "[]",
                                             "options_json": json.dumps(options or {})})
        threading.Thread(target=self._run_body, args=(run_id, agent), name=f"run-{run_id}", daemon=True).start()
        return {"id": run_id, "already_running": False}

    def start_all(self, trigger: str = "manual", scope: str = "full") -> dict:
        """The single entry point for manual and scheduled sweeps. One sweep at a time, across this
        app and any scheduled-task process: a second trigger returns the active sweep instead.

        Full sweep order: Funding Scout finds funded startups and their boards; Job Scout then collects
        every board and listing source; analyses queue; Contact Scout and the Digest Editor wait
        behind the analyses they depend on."""
        agents = sweep.agents_for(scope)
        with self._start_lock:
            active = self.active_runs()
            if active:
                return {"started": [], "skipped": "A sweep is already in progress.", "active": [r["id"] for r in active]}
            group = uuid.uuid4().hex[:8]
            owner = f"{os.getpid()}:{group}"
            held = sweep.acquire(self.db, owner, scope=scope, trigger=trigger, minutes=self.cfg.limits.sweep_lock_minutes)
            if held:
                return {"started": [], "skipped": f"Another SignalDesk process is sweeping (since {held['at']}, {held.get('trigger')}).", "lock": held}
            options = {"scope": scope, "lease": owner}
            if scope.startswith("source:"):
                options["source"] = scope.split(":", 1)[1]
            started = [self.start_run(a, trigger, group, options)["id"] for a in agents]
        return {"started": started, "group": group, "scope": scope}

    def _options(self, run_id: int) -> dict:
        return json.loads(self.db.scalar("SELECT options_json FROM runs WHERE id = ?", (run_id,)) or "{}")

    def _wait_for(self, run_id: int, agent: str, minutes: int = 60) -> None:
        """Let a later agent start after an earlier one in the same sweep has finished collecting."""
        group = self.db.scalar("SELECT group_id FROM runs WHERE id = ?", (run_id,))
        deadline = time.monotonic() + minutes * 60
        while group and time.monotonic() < deadline and not self._cancelled(run_id):
            if not self.db.scalar("SELECT 1 FROM runs WHERE group_id = ? AND agent = ? AND status = 'collecting'", (group, agent)):
                return
            time.sleep(1)

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
            self._settle_runs()

    def _settle_runs(self) -> None:
        """Close analysing runs whose tasks have all finished, and release the sweep lock once no run
        of that sweep is active."""
        for r in self.db.all("SELECT id, cancel_requested FROM runs WHERE status = 'analysing'"):
            counts = {row["status"]: row["n"] for row in self.db.all("SELECT status, COUNT(*) n FROM tasks WHERE run_id = ? GROUP BY status", (r["id"],))}
            if counts.get("queued") or counts.get("running"):
                continue
            status = "cancelled" if r["cancel_requested"] else ("done_with_errors" if counts.get("failed") else "done")
            self.db.update("runs", r["id"], {"status": status, "finished_at": now_iso()})
        lease = sweep.holder(self.db)
        if lease:
            group = lease["owner"].split(":", 1)[1]
            mine = lease["owner"].startswith(f"{os.getpid()}:")
            # Another process's lease is released here only when it has stopped beating (it crashed or
            # the app restarted) and its sweep has nothing left to do.
            if (mine or sweep.stale(lease)) and not self.db.scalar(f"SELECT 1 FROM runs WHERE group_id = ? AND status IN {ACTIVE}", (group,)):
                sweep.release(self.db, lease["owner"])
                self.db.set_setting("last_sweep", {"group": group, "finished_at": now_iso(), "scope": lease.get("scope"),
                                                   "trigger": lease.get("trigger"), "summary": self.sweep_summary(group)})

    def sweep_summary(self, group: str) -> dict:
        totals = {"new": 0, "updated": 0, "duplicates": 0, "failed_sources": 0, "funding_new": 0, "contacts": 0, "drafts": 0}
        for r in self.db.all("SELECT agent, stats_json, status FROM runs WHERE group_id = ?", (group,)):
            s = json.loads(r["stats_json"])
            totals["new"] += s.get("new", 0)
            totals["updated"] += s.get("changed", 0)
            totals["duplicates"] += s.get("duplicate", 0) + s.get("merged", 0)
            totals["failed_sources"] += s.get("sources_failed", 0)
            totals["funding_new"] += s.get("funding_new", 0)
            totals["contacts"] += s.get("contacts", 0)
            totals["drafts"] += s.get("drafts", 0)
        return totals

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
        if kind == "role_classify":
            job = self.db.one("SELECT content_hash FROM jobs WHERE id = ?", (target_id,))
            return job and analysis.cache_key(kind, model_id=m, content=job["content_hash"], extra={"budget": self.cfg.model.prompt_char_budget})
        if kind == "funding_extract":
            a = self.db.one("SELECT url, text FROM announcements WHERE id = ?", (target_id,))
            return a and analysis.cache_key(kind, model_id=m, content=analysis.sha(a["url"], a["text"] or ""))
        if kind == "outreach_draft":
            c = self.db.one("SELECT c.name, c.title, c.evidence_text, c.recipient_key, j.content_hash FROM contacts c JOIN jobs j ON j.id = c.job_id "
                            "WHERE c.id = ?", (target_id,))
            # A changed recipient, contact evidence, posting or profile makes the draft stale.
            return c and analysis.cache_key(kind, model_id=m, content=analysis.sha(dict(c)), extra={"profile": self.profiles.profile_version()})
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

    TARGET = {"job_fit": "job", "role_classify": "job", "funding_extract": "announcement", "outreach_draft": "contact"}

    def analyse(self, kind: str, target_id: int, run_id: int | None = None, priority: int = 20) -> str:
        key = self.key_for(kind, target_id)
        if not key:
            raise ValueError("Item not found")
        return self.enqueue(run_id, kind, self.TARGET.get(kind, "article"), target_id, key, priority)

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
    def sources(self) -> list[dict]:
        return registry.load(self.db, self.cfg.home)

    def _collect_funding_scout(self, run_id: int) -> None:
        only = self._options(run_id).get("source")
        srcs = [s for s in self.sources() if s["group"] == "funding" and s["mode"] in ("automatic", "unavailable") and (not only or s["key"] == only)]
        enqueue = lambda ann_id: self.analyse("funding_extract", ann_id, run_id, 25)  # noqa: E731
        with ThreadPoolExecutor(max(1, min(len(srcs), self.fetcher.cfg.concurrency))) as ex:
            results = list(ex.map(lambda s: (s, funding.collect_source(self.db, self.fetcher, s, enqueue)), srcs))
        ok = failed = funded = 0
        for s, r in results:
            if r.get("error"):
                failed += 1
                self._log(run_id, f"{s['name']}: {r['error']}. Saved records were kept; unprocessed items stay pending for the next sweep.")
            else:
                ok += 1
                funded += r.get("funding", 0)
                self._log(run_id, f"{s['name']}: {json.dumps({k: v for k, v in r.items() if v})}")
        for s in self.sources():
            if s["group"] == "funding" and s["mode"] == "needs_setup":
                self._log(run_id, f"{s['name']}: needs setup (no page address yet); skipped.")
        if self._cancelled(run_id):
            return
        careers = funding.resolve_careers(self.db, self.fetcher)
        self._stat(run_id, sources_ok=ok, sources_failed=failed, funding_new=funded, boards_found=careers["boards"])
        self._log(run_id, f"Careers pages: {careers['checked']} checked, {careers['boards']} job boards added, "
                          f"{careers['page_only']} need a manual check, {careers['failed']} could not be reached.")

    def _collect_listing_sources(self, run_id: int, prefs: dict, only: str | None = None) -> dict:
        """Job listing pages (YC, investor job boards). Boards they link become employers; other
        listings are kept as unverified until the employer's own board confirms them."""
        totals = {"listing_sources_ok": 0, "listing_sources_failed": 0, "merged": 0, "unverified": 0, "boards_added": 0}
        now = now_iso()
        for s in self.sources():
            if s["kind"] != "job_listings" or s["mode"] not in ("automatic", "unavailable") or (only and s["key"] != only):
                continue
            try:
                res = web.job_listings(self.fetcher, s["url"])
            except FetchError as e:
                registry.record(self.db, s["key"], ok=False, error=str(e))
                totals["listing_sources_failed"] += 1
                self._log(run_id, f"{s['name']}: {e}. Nothing was changed.")
                continue
            counts: dict[str, int] = {"listings": len(res["postings"]), "boards": len(res["boards"])}
            for b in res["boards"]:
                before = self.db.scalar("SELECT 1 FROM companies WHERE ats = ? AND lower(ats_id) = lower(?)", (b["ats"], b["ats_id"]))
                collect.add_board(self.db, name=b["name"], ats=b["ats"], ats_id=b["ats_id"], careers_url=b["url"], origin=s["key"], tie="source_link",
                                  verification=f"Linked from {s['name']} ({b['found_on']}); not yet confirmed on the employer's own site")
                totals["boards_added"] += not before
            with self.db.batch():
                for p in res["postings"]:
                    if not p.get("employer") and p.get("employer_slug"):
                        p["employer"] = p["employer_slug"].replace("-", " ").title()
                    r = collect.attach_listing(self.db, p, source=s["key"], prefs=prefs, now=now)
                    counts[r] = counts.get(r, 0) + 1
            totals["merged"] += counts.get("merged", 0)
            totals["unverified"] += counts.get("unverified", 0) + counts.get("ambiguous", 0)
            totals["listing_sources_ok"] += 1
            registry.record(self.db, s["key"], ok=True, counts=counts)
            self._log(run_id, f"{s['name']}: {json.dumps(counts)}")
        return totals

    def _collect_source_refresh(self, run_id: int) -> None:
        key = self._options(run_id).get("source")
        src = next((s for s in self.sources() if s["key"] == key), None)
        if not src:
            raise ValueError(f"Unknown source '{key}'")
        if src["group"] == "funding":
            return self._collect_funding_scout(run_id)
        if src["kind"] == "ats":
            return self._collect_job_scout(run_id)
        totals = self._collect_listing_sources(run_id, self.profiles.prefs(), only=key)
        merged = collect.verify_unverified(self.db)
        self._stat(run_id, **totals, merged_later=merged)

    def _collect_contact_scout(self, run_id: int) -> None:
        # Waits in the queue behind fit analyses, so it can use them to choose the shortlist.
        self.db.insert("tasks", {"run_id": run_id, "kind": "contact_select", "target_type": "run", "target_id": run_id, "status": "queued",
                                 "created_at": now_iso(), "priority": 80, "max_attempts": 1})
        self._log(run_id, "Waiting for fit analyses, then finding contacts for shortlisted roles.")

    def _collect_job_scout(self, run_id: int) -> None:
        self._wait_for(run_id, "funding_scout")
        prefs = self.profiles.prefs()
        results = collect.collect_jobs(self.db, self.fetcher, prefs, cancelled=lambda: self._cancelled(run_id))
        failed_boards = sum(bool(r.get("error") or r.get("warning")) for r in results)
        registry.record(self.db, "ats_boards", ok=failed_boards < len(results) or not results,
                        counts={"boards": len(results), "failed": failed_boards}, error=None if failed_boards < len(results) else "Every board failed")
        listing = self._collect_listing_sources(run_id, prefs)
        merged = collect.verify_unverified(self.db)
        funding.update_hiring_links(self.db)
        self._stat(run_id, **listing, merged_later=merged)
        if listing["listing_sources_ok"] or listing["listing_sources_failed"]:
            self._log(run_id, f"Listing sources: {listing['merged']} matched to employer boards, {listing['unverified']} kept as unverified, "
                              f"{listing['boards_added']} new boards; {merged} earlier listings now confirmed on the employer's board.")
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
        # Only titles the rules could not place, and only where the location already qualifies:
        # a clear location mismatch never costs a model call.
        amb = self.db.all("SELECT id FROM jobs WHERE role_source = 'rules_uncertain' AND listing_state = 'open' AND duplicate_of IS NULL "
                          "AND location_class IN ('bengaluru', 'remote_india') ORDER BY first_seen_at DESC LIMIT ?",
                          (self.cfg.limits.max_role_checks_per_run,))
        roles_queued = sum(self.analyse("role_classify", r["id"], run_id, 28) == "queued" for r in amb)
        if amb:
            self._log(run_id, f"{len(amb)} jobs with unclear role titles considered for a role check; {roles_queued} need the model.")
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

    GATED = ("case_select", "contact_select", "digest_compose")

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
        last_beat = 0.0
        while not self.stop_flag.is_set():
            try:
                worked = self.step()
                if time.monotonic() - last_beat > 60:
                    last_beat = time.monotonic()
                    lease = sweep.holder(self.db)
                    if lease and lease["owner"].startswith(f"{os.getpid()}:"):
                        sweep.beat(self.db, lease["owner"])
            except Exception:  # noqa: BLE001
                log.error("queue loop error: %s", traceback.format_exc())
                worked = False
            if not worked:
                self.wake.wait(5)
                self.wake.clear()

    def _claim(self, task: dict) -> bool:
        """Atomic across threads and processes: only one worker moves a queued task to running."""
        with self.db.write_lock:
            cur = self.db.conn.execute("UPDATE tasks SET status = 'running', started_at = ?, attempts = ? WHERE id = ? AND status = 'queued'",
                                       (now_iso(), task["attempts"] + 1, task["id"]))
            self.db.conn.commit()
            return cur.rowcount == 1

    def step(self) -> bool:
        """Process at most one task. Returns True when a task was handled."""
        with self._claim_lock:
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
            if not self._claim(task):
                return True
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

    def _call(self, task: dict, purpose: str, prompt: str, max_tokens: int | None = None, escalate: bool = False):
        model = self.escalation if escalate else self.model
        wanted = model.cfg.model_id
        rec = {"task_id": task["id"], "run_id": task["run_id"], "purpose": purpose + (" (larger model)" if escalate else ""),
               "model_requested": wanted, "started_at": now_iso()}
        try:
            reply = model.chat(analysis.SYSTEM, prompt, max_tokens=max_tokens)
        except Exception as e:
            self.db.insert("model_calls", {**rec, "ok": 0, "error": str(e)[:300]})
            raise
        if escalate:
            self.db.insert("model_calls", {**rec, "model_served": reply.model_served, "duration_ms": reply.duration_ms, "tokens_in": reply.tokens_in,
                                           "tokens_out": reply.tokens_out, "finish_reason": reply.finish_reason, "ok": 1})
            if task["run_id"]:
                self._stat(task["run_id"], model_requests=1, model_ms=reply.duration_ms, escalations=1)
            if reply.model_served != wanted or reply.finish_reason == "length":
                raise ModelError(f"The larger model's reply was unusable ({reply.model_served}, {reply.finish_reason}).")
            return reply
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
        sent_profile = {**profile, "facts": [f for f in profile["facts"] if f["id"] in cov["profile_fact_ids"]]}
        (out, val), served, escalated = self._try_both(task, "job_fit", prompt, lambda d: analysis.validate_job(d, job, sent_profile),
                                                       self.cfg.model.max_output_tokens, unsure=lambda r: r[0]["match"] == "unknown")
        if escalated:
            val["notes"].append("Written by the larger local model after the default model's answer failed checks or stayed unknown.")
        if len(sent_profile['facts']) < len(profile['facts']):
            val['notes'].append(f"Used {len(sent_profile['facts'])} of {len(profile['facts'])} profile facts, selected by keyword overlap. Other experience may have been missed; this is a partial assessment.")
        # Fact ids are renumbered when the profile changes, so keep the exact text
        # each cited id had when this assessment was made.
        inputs = {"coverage": cov, "profile_version": profile_version, "facts_sent": sent_profile["facts"], "escalated": escalated}
        self._save(task, "job_fit", "job", out, val, inputs, served)
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

    # ------------------------------------------------------------ the larger model, only when needed
    def escalation_ready(self) -> bool:
        return bool(self.escalation) and bool(self.escalation.status().get("ready"))

    def _try_both(self, task: dict, purpose: str, prompt: str, validate, max_tokens: int, unsure=lambda out: False):
        """Default model first. The larger model is asked only when the first answer fails validation
        or is unsure, and its answer is used only if it passes the same checks."""
        first_error, out, served = None, None, None
        try:
            reply = self._call(task, purpose, prompt, max_tokens=max_tokens)
            out, served = validate(analysis.parse_json(reply.text)), reply.model_served
        except (ValueError, ModelError) as e:
            first_error = e
        if (out is None or unsure(out)) and self.escalation_ready():
            try:
                reply = self._call(task, purpose, prompt, max_tokens=max_tokens, escalate=True)
                better = validate(analysis.parse_json(reply.text))
                if out is None or not unsure(better):
                    return better, reply.model_served, True
            except (ValueError, ModelError) as e:
                if out is None:
                    raise ModelError(f"Both models failed: {first_error}; larger model: {e}") from None
        if out is None:
            raise first_error
        return out, served, False

    # ------------------------------------------------------------ roles, funding, outreach
    def _do_role_classify(self, task: dict) -> str:
        job = self.db.one("SELECT * FROM jobs WHERE id = ?", (task["target_id"],))
        prompt, cov = analysis.role_prompt(job, self._budget(task))
        (out, val), served, escalated = self._try_both(task, "role_classify", prompt, lambda d: analysis.validate_roles(d, job), 200,
                                                       unsure=lambda r: r[0]["confidence"] != "clear")
        if escalated:
            val["notes"].append("Decided by the larger local model after the default model was unsure.")
        self._save(task, "role_classify", "job", out, val, {"coverage": cov}, served)
        if out["confidence"] != "clear":
            self.db.update("jobs", job["id"], {"role_source": "model_uncertain"})
            return "Still unclear; kept in To review"
        p = {"title": job["title"], "location": job["location_raw"], "workplace": job["workplace_raw"], "description_text": job["description_text"],
             "salary_extra": None}
        got = collect.classify(p, self.profiles.prefs(), out["families"])
        evidence = [out["quote"]] if out["quote"] else []
        self.db.update("jobs", job["id"], {"role_family": got["role_family"], "role_families": got["role_families"], "role_evidence": json.dumps(evidence),
                                           "role_source": "model", "bucket": got["bucket"], "bucket_reason": got["bucket_reason"]})
        return f"Role families: {', '.join(out['families'])}"

    def _do_funding_extract(self, task: dict) -> str:
        ann = self.db.one("SELECT * FROM announcements WHERE id = ?", (task["target_id"],))
        prompt = analysis.funding_prompt(ann, self._budget(task))

        def check(d):
            text = f"{ann['title']}\n{ann['text'] or ''}"
            if d.get("is_funding_round") and (str(d.get("company") or "").lower() not in text.lower() or not analysis.find_quote(str(d.get("quote") or ""), text)):
                raise ValueError("The company or quote is not in the announcement.")
            return d
        data, served, _esc = self._try_both(task, "funding_extract", prompt, check, 200)
        status, notes = funding.model_reading(self.db, ann["id"], data)
        self._save(task, "funding_extract", "announcement", {"company": data.get("company"), "round": data.get("round"), "status": status},
                   {"notes": notes}, {}, served)
        return f"Announcement read: {status}"

    def _do_outreach_draft(self, task: dict) -> str:
        c = self.db.one("SELECT * FROM contacts WHERE id = ?", (task["target_id"],))
        job = self.db.one("SELECT * FROM jobs WHERE id = ?", (c["job_id"],))
        profile = self.profiles.profile()
        fit = self.latest("job_fit", "job", job["id"])
        fact = contacts.pick_fact(profile, job, fit)
        prompt = contacts.draft_prompt(c, job, fact, profile)
        (note, msg), served, _esc = self._try_both(task, "outreach_draft", prompt, lambda d: contacts.validate_draft(d, c, job, fact), 400)
        o = self.db.one("SELECT * FROM outreach WHERE contact_id = ?", (c["id"],))
        if o and o["state"] == "drafted":
            self.db.update("outreach", o["id"], {"note_text": note, "message_text": msg, "drafted_by": "model", "updated_at": now_iso(),
                                                 "inputs_json": json.dumps({"fact": fact, "detail": contacts.detail_for(c, job), "model": served})})
        self._save(task, "outreach_draft", "contact", {"note": note, "message": msg}, {"notes": []}, {"fact": fact["id"] if fact else None}, served)
        return "Draft written" if o and o["state"] == "drafted" else "Draft written; the message was already sent or marked contacted, so it was not replaced"

    def _do_contact_select(self, task: dict) -> str:
        run_id = task["run_id"]
        week_ago = _iso_in(-7 * 86400)
        rows = self.db.all(
            "SELECT j.* FROM jobs j WHERE j.listing_state = 'open' AND j.duplicate_of IS NULL AND (j.status IN ('Interested', 'Investigate') "
            "OR (j.bucket = 'candidate' AND j.status = 'New' AND EXISTS (SELECT 1 FROM analyses a WHERE a.kind = 'job_fit' AND a.target_id = j.id "
            "AND json_extract(a.output_json, '$.match') = 'potential match'))) "
            "AND NOT EXISTS (SELECT 1 FROM contacts c WHERE c.job_id = j.id AND c.verified_at >= ?) "
            "ORDER BY (j.status IN ('Interested', 'Investigate')) DESC, j.first_seen_at DESC LIMIT ?", (week_ago[:10], self.cfg.limits.max_contact_jobs_per_run))
        found = 0
        for j in rows:
            try:
                found += contacts.discover_for_job(self.db, self.fetcher, j["id"])["found"]
            except (FetchError, ValueError) as e:
                self._log(run_id, f"Contacts for {j['title']} at {j['employer']}: {e}")
        # High-priority companies without a matching opening: founders and team, no draft (there is no role yet).
        for s in self.db.all("SELECT s.* FROM startups s WHERE s.domain IS NOT NULL AND s.is_demo = 0 AND s.india_link != 'unknown' "
                             "AND EXISTS (SELECT 1 FROM funding_events e WHERE e.startup_id = s.id AND e.announced_on >= ?) "
                             "AND NOT EXISTS (SELECT 1 FROM contacts c WHERE c.startup_id = s.id) LIMIT 3", (_iso_in(-90 * 86400)[:10],)):
            people = contacts.from_team_page(self.fetcher, s["domain"], s["name"])
            for ann in self.db.all("SELECT a.url, a.text FROM funding_events e JOIN announcements a ON a.url = e.announcement_url WHERE e.startup_id = ?", (s["id"],)):
                people += contacts.from_announcement(ann["text"] or "", ann["url"], s["name"])
            found += len(contacts.save_contacts(self.db, contacts.rank_for_job(people, {"role_families": "[\"founders_office\"]"}, True),
                                                job_id=None, startup_id=s["id"], company=s["name"]))
        profile = self.profiles.profile()
        drafts = 0
        for c in self.db.all("SELECT c.id, c.job_id FROM contacts c LEFT JOIN outreach o ON o.contact_id = c.id "
                             "WHERE c.job_id IS NOT NULL AND o.id IS NULL AND c.status != 'unresolved'"):
            contacts.ensure_draft(self.db, c["id"], profile, self.latest("job_fit", "job", c["job_id"]))
            drafts += 1
            self.analyse("outreach_draft", c["id"], run_id, 85)
        sent = contacts.send_due(self.db, self.messaging)
        self._stat(run_id, contacts=found, drafts=drafts, sent=sent.get("sent", 0))
        msg = (f"{len(rows)} shortlisted role(s) checked: {found} contact(s) found, {drafts} new draft(s). "
               f"Sending: {sent.get('reason') or str(sent['sent']) + ' sent'}.")
        self._log(run_id, msg)
        return msg
