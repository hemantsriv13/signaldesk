"""HTTP API and the built web app. Bound to 127.0.0.1 by default.

Requests must name this machine in the Host header, and changes must come from this app's own
pages, so another website open in the browser cannot drive the API.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import collect, jobrules
from .cv import MAX_BYTES, preview_cv
from starlette.concurrency import run_in_threadpool
from .analysis import LABELS
from .discovery import discover
from .delivery import Delivery
from .db import now_iso
from .engine import AGENTS, Engine
from .netsafe import FetchError
from .scheduler import Scheduler

WEB = Path(__file__).resolve().parent.parent / "web" / "dist"
JOB_STATUSES = ["New", "Interested", "Investigate", "Applied", "Not relevant", "Archived"]
VERDICTS = ["useful", "not_relevant", "known", "too_technical"]
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}


class JobPatch(BaseModel):
    status: str

class JobImport(BaseModel):
    url: str
    text: str = ""
    employer: str = ""
    title: str = ""
    location: str = ""
    apply_url: str = ""

class UrlBody(BaseModel):
    url: str

class Feedback(BaseModel):
    item_type: str
    item_id: int
    verdict: str
    on: bool = True

class DigestPatch(BaseModel):
    status: str

class Generate(BaseModel):
    regenerate: bool = False
    confirm: bool = False

class RunBody(BaseModel):
    agent: str

class Company(BaseModel):
    name: str
    careers_url: str
    ats: str
    ats_id: str = ""
    enabled: bool = True
    verification: str = ""

class Feed(BaseModel):
    name: str
    feed_url: str
    site_url: str = ""
    kind: str = "blog"
    enabled: bool = True

class ScheduleBody(BaseModel):
    enabled: bool
    time: str


class _Redact(logging.Filter):
    EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
    PHONE = re.compile(r"(?<!\d)(\+?\d[\d -]{8,}\d)(?!\d)")

    def filter(self, record):
        msg = record.getMessage()
        record.msg, record.args = self.PHONE.sub("[phone]", self.EMAIL.sub("[email]", msg)), ()
        return True


def setup_logging(logs_dir: Path) -> None:
    h = logging.FileHandler(logs_dir / "signaldesk.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    h.addFilter(_Redact())
    lg = logging.getLogger("signaldesk")
    lg.setLevel(logging.INFO)
    lg.addHandler(h)


def _hours(iso):
    if not iso:
        return None
    dt = datetime.fromisoformat(iso)
    return round((datetime.now(timezone.utc) - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))).total_seconds() / 3600, 1)


def create_app(engine: Engine, scheduler: Scheduler | None = None) -> FastAPI:
    app = FastAPI(title="SignalDesk", docs_url=None, redoc_url=None, openapi_url=None)
    db = engine.db
    scheduler = scheduler or Scheduler(engine)
    delivery = Delivery(engine)
    app.state.delivery = delivery

    @app.middleware("http")
    async def guard(request: Request, call_next):
        raw = request.headers.get("host") or ""
        host = raw[: raw.find("]") + 1] if raw.startswith("[") else raw.rsplit(":", 1)[0]
        if host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "SignalDesk only answers requests addressed to this computer."}, 403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and re.sub(r"^https?://", "", origin).rsplit(":", 1)[0] not in LOCAL_HOSTS:
                return JSONResponse({"detail": "Changes are only accepted from SignalDesk's own pages."}, 403)
        return await call_next(request)

    def job_or_404(job_id: int) -> dict:
        j = db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if not j:
            raise HTTPException(404, "Job not found")
        return j

    def article_or_404(aid: int) -> dict:
        a = db.one("SELECT * FROM articles WHERE id = ?", (aid,))
        if not a:
            raise HTTPException(404, "Article not found")
        return a

    def pending(kind: str, target_id: int) -> dict | None:
        return db.one("SELECT id, status, attempts, error, note FROM tasks WHERE kind = ? AND target_id = ? AND status IN ('queued', 'running', 'failed') "
                      "ORDER BY id DESC LIMIT 1", (kind, target_id))

    # ------------------------------------------------------------ status
    @app.get("/api/status")
    def status():
        model = engine.check_model()
        runs = []
        for r in engine.active_runs():
            counts = {x["status"]: x["n"] for x in db.all("SELECT status, COUNT(*) n FROM tasks WHERE run_id = ? GROUP BY status", (r["id"],))}
            runs.append({"id": r["id"], "agent": r["agent"], "agentName": AGENTS[r["agent"]], "status": r["status"], "started_at": r["started_at"],
                         "tasks": counts, "stats": json.loads(r["stats_json"]), "current": engine.current_task})
        latest = db.one("SELECT id, created_at, content_json FROM digests WHERE status = 'saved' ORDER BY id DESC LIMIT 1")
        failures = db.all("SELECT 'company' AS type, id, name, COALESCE(last_error, last_warning) AS error, COALESCE(last_error_at, last_attempt_at) AS at "
                          "FROM companies WHERE enabled = 1 AND (last_error IS NOT NULL OR last_warning IS NOT NULL) UNION ALL "
                          "SELECT 'feed', id, name, last_error, last_error_at FROM reading_sources WHERE enabled = 1 AND last_error IS NOT NULL")
        return {
            "model": model,
            "runs": runs,
            "queue": {"queued": db.scalar("SELECT COUNT(*) FROM tasks WHERE status = 'queued'"),
                      "running": db.scalar("SELECT COUNT(*) FROM tasks WHERE status = 'running'"),
                      "failed": db.scalar("SELECT COUNT(*) FROM tasks WHERE status = 'failed'")},
            "counts": {
                "newMatches": db.scalar("SELECT COUNT(*) FROM jobs WHERE bucket = 'candidate' AND listing_state = 'open' AND status = 'New' AND change_state IN ('new', 'changed') AND duplicate_of IS NULL"),
                "matches": db.scalar("SELECT COUNT(*) FROM jobs WHERE bucket = 'candidate' AND listing_state = 'open' AND duplicate_of IS NULL AND status NOT IN ('Not relevant', 'Archived')"),
                "review": db.scalar("SELECT COUNT(*) FROM jobs WHERE bucket = 'review' AND listing_state = 'open' AND duplicate_of IS NULL AND status NOT IN ('Not relevant', 'Archived')"),
                "articles": db.scalar("SELECT COUNT(*) FROM articles WHERE duplicate_of IS NULL"),
                "cards": db.scalar("SELECT COUNT(DISTINCT target_id) FROM analyses WHERE kind = 'reading_card'"),
                "cases": db.scalar("SELECT COUNT(DISTINCT target_id) FROM analyses WHERE kind = 'case_study'"),
                "everCollected": db.scalar("SELECT COUNT(*) FROM runs WHERE agent IN ('job_scout', 'reading_scout') AND status NOT IN ('failed')"),
            },
            "failures": failures,
            "latestDigest": {"id": latest["id"], "created_at": latest["created_at"], **json.loads(latest["content_json"])} if latest else None,
            "schedule": scheduler.describe(),
        }

    # ------------------------------------------------------------ jobs
    @app.get("/api/jobs")
    def jobs(view: str = "matches", status: str = "", q: str = "", sort: str = "first_seen", location: str = ""):
        where, args = ["duplicate_of IS NULL"], []
        if view == "matches":
            where.append("bucket = 'candidate' AND listing_state = 'open'")
        elif view == "review":
            where.append("bucket = 'review' AND listing_state = 'open'")
        elif view == "outside":
            where.append("bucket = 'outside' AND listing_state = 'open'")
        elif view == "closed":
            where.append("listing_state = 'no_longer_listed'")
        elif view == "saved":
            where.append("status IN ('Interested', 'Investigate', 'Applied')")
        if status:
            where.append("status = ?")
            args.append(status)
        elif view in ("matches", "review"):
            where.append("status NOT IN ('Not relevant', 'Archived')")
        if location:
            where.append("location_class = ?")
            args.append(location)
        if q:
            where.append("(title LIKE ? OR employer LIKE ? OR description_text LIKE ?)")
            args += [f"%{q}%"] * 3
        order = {"first_seen": "first_seen_at DESC, id DESC", "published": "COALESCE(published_at, '') DESC", "employer": "employer, title", "title": "title"}.get(sort, "first_seen_at DESC")
        rows = db.all(f"SELECT id, employer, title, location_raw, location_class, salary_text, bucket, bucket_reason, role_family, status, change_state, "
                      f"listing_state, published_at, first_seen_at, last_verified_at, source, injection_flag FROM jobs WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 500", args)
        if rows:
            ids = [r["id"] for r in rows]
            fits = {r["target_id"]: json.loads(r["output_json"])["match"] for r in db.all(
                f"SELECT target_id, output_json FROM analyses WHERE kind = 'job_fit' AND target_id IN ({','.join('?' * len(ids))}) ORDER BY id", ids)}
            waiting = {r["target_id"] for r in db.all(f"SELECT target_id FROM tasks WHERE kind = 'job_fit' AND status IN ('queued', 'running') AND target_id IN ({','.join('?' * len(ids))})", ids)}
            for r in rows:
                r["match"] = fits.get(r["id"])
                r["analysis_pending"] = r["id"] in waiting
                r["verified_hours_ago"] = _hours(r["last_verified_at"])
        counts = {v: db.scalar(f"SELECT COUNT(*) FROM jobs WHERE duplicate_of IS NULL AND {c}") for v, c in {
            "matches": "bucket = 'candidate' AND listing_state = 'open' AND status NOT IN ('Not relevant', 'Archived')",
            "review": "bucket = 'review' AND listing_state = 'open' AND status NOT IN ('Not relevant', 'Archived')",
            "outside": "bucket = 'outside' AND listing_state = 'open'", "closed": "listing_state = 'no_longer_listed'",
            "saved": "status IN ('Interested', 'Investigate', 'Applied')"}.items()}
        return {"jobs": rows, "counts": counts, "statuses": JOB_STATUSES, "locationLabels": jobrules.LOCATION_LABEL}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: int):
        j = job_or_404(job_id)
        prefs = engine.profiles.prefs()
        company = db.one("SELECT id, name, careers_url, verification, last_success_at, last_error FROM companies WHERE id = ?", (j["company_id"],)) if j["company_id"] else None
        versions = db.all("SELECT id, title, location_raw, salary_text, seen_at FROM job_versions WHERE job_id = ? ORDER BY id DESC", (job_id,))
        dups = db.all("SELECT id, title, official_url FROM jobs WHERE duplicate_of = ?", (job_id,))
        return {**j, "company": company, "versions": versions, "duplicates": dups,
                "fit": engine.latest("job_fit", "job", job_id), "task": pending("job_fit", job_id),
                "compensation_note": jobrules.compensation_note(j["salary_text"], j["salary_kind"], prefs["ctc_threshold_lakh"]),
                "location_label": jobrules.LOCATION_LABEL.get(j["location_class"] or "unknown"), "family_label": jobrules.FAMILY_LABEL.get(j["role_family"] or "other"),
                "verified_hours_ago": _hours(j["last_verified_at"]), "feedback": [r["verdict"] for r in db.all("SELECT verdict FROM feedback WHERE item_type = 'job' AND item_id = ?", (job_id,))],
                "profile_facts": engine.profiles.profile()["facts"]}


    @app.patch("/api/jobs/{job_id}")
    def patch_job(job_id: int, body: JobPatch):
        job_or_404(job_id)
        if body.status not in JOB_STATUSES:
            raise HTTPException(400, "Unknown status")
        db.update("jobs", job_id, {"status": body.status})
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/analyse")
    def analyse_job(job_id: int):
        job_or_404(job_id)
        return {"result": engine.analyse("job_fit", job_id)}

    @app.post("/api/jobs/{job_id}/recheck")
    def recheck_job(job_id: int):
        j = job_or_404(job_id)
        if not j["company_id"]:
            try:
                r = engine.fetcher.get(j["official_url"], check_robots=True)
            except FetchError as e:
                return {"result": f"Could not check: {e}"}
            if r.status in (404, 410):
                db.update("jobs", job_id, {"listing_state": "no_longer_listed", "closed_at": now_iso()})
                return {"result": f"The page returned HTTP {r.status}; marked as no longer listed."}
            db.update("jobs", job_id, {"last_verified_at": now_iso()})
            return {"result": f"The page answered (HTTP {r.status}). Check it still shows the job."}
        company = db.one("SELECT * FROM companies WHERE id = ?", (j["company_id"],))
        res = collect.collect_company(db, engine.fetcher, company, engine.profiles.prefs())
        if res.get("error"):
            return {"result": f"Could not reach the board: {res['error']}. Nothing was changed."}
        state = db.scalar("SELECT listing_state FROM jobs WHERE id = ?", (job_id,))
        return {"result": "Still listed on the employer's board." if state == "open" else "No longer listed on the employer's board."}


    @app.post("/api/jobs/import")
    def import_job(body: JobImport):
        try:
            return collect.import_job(db, engine.fetcher, engine.profiles.prefs(), **body.model_dump())
        except (ValueError, FetchError) as e:
            raise HTTPException(400, str(e)) from None

    # ------------------------------------------------------------ reading and cases
    def article_rows(where: str, args: list, q: str) -> list[dict]:
        if q:
            where += " AND (a.title LIKE ? OR a.source_name LIKE ? OR a.content_text LIKE ?)"
            args = [*args, *[f"%{q}%"] * 3]
        rows = db.all(f"SELECT a.id, a.title, a.source_name, a.source_kind, a.author, a.published_at, a.retrieved_at, a.content_basis, a.url, a.origin, "
                      f"a.case_candidate, a.injection_flag, (SELECT COUNT(*) FROM articles d WHERE d.duplicate_of = a.id) AS repeats "
                      f"FROM articles a WHERE a.duplicate_of IS NULL AND {where} ORDER BY COALESCE(a.published_at, a.retrieved_at) DESC LIMIT 300", args)
        if rows:
            ids = [r["id"] for r in rows]
            marks = ",".join("?" * len(ids))
            done = {(r["kind"], r["target_id"]): r["output_json"] for r in db.all(f"SELECT kind, target_id, output_json FROM analyses WHERE target_id IN ({marks}) AND kind IN ('reading_card', 'case_study') ORDER BY id", ids)}
            waiting = {(r["kind"], r["target_id"]) for r in db.all(f"SELECT kind, target_id FROM tasks WHERE status IN ('queued', 'running') AND target_id IN ({marks})", ids)}
            fb = {}
            for r in db.all(f"SELECT item_id, verdict FROM feedback WHERE item_type = 'article' AND item_id IN ({marks})", ids):
                fb.setdefault(r["item_id"], []).append(r["verdict"])
            for r in rows:
                r["has_card"] = ("reading_card", r["id"]) in done
                case = done.get(("case_study", r["id"]))
                r["case_suitability"] = json.loads(case)["suitability"] if case else None
                r["card_pending"] = ("reading_card", r["id"]) in waiting
                r["case_pending"] = ("case_study", r["id"]) in waiting
                r["feedback"] = fb.get(r["id"], [])
        return rows

    @app.get("/api/articles")
    def articles(q: str = "", source: int | None = None, basis: str = "", analysed: str = ""):
        where, args = "1=1", []
        if source:
            where += " AND a.source_id = ?"
            args.append(source)
        if basis:
            where += " AND a.content_basis = ?"
            args.append(basis)
        if analysed == "yes":
            where += " AND EXISTS (SELECT 1 FROM analyses n WHERE n.kind = 'reading_card' AND n.target_id = a.id)"
        rows = article_rows(where, args, q)
        sources = db.all("SELECT id, name FROM reading_sources ORDER BY name")
        return {"articles": rows, "sources": sources}

    @app.get("/api/articles/{aid}")
    def article(aid: int):
        a = article_or_404(aid)
        dups = db.all("SELECT id, title, url, source_name FROM articles WHERE duplicate_of = ?", (aid,))
        return {**a, "duplicates": dups, "card": engine.latest("reading_card", "article", aid), "case": engine.latest("case_study", "article", aid),
                "card_task": pending("reading_card", aid), "case_task": pending("case_study", aid),
                "feedback": [r["verdict"] for r in db.all("SELECT verdict FROM feedback WHERE item_type = 'article' AND item_id = ?", (aid,))]}

    @app.post("/api/articles/{aid}/analyse")
    def analyse_article(aid: int, kind: str = "reading_card"):
        a = article_or_404(aid)
        if kind not in ("reading_card", "case_study"):
            raise HTTPException(400, "Unknown analysis")
        if a["content_basis"] == "metadata":
            raise HTTPException(400, "Only the title and link were retrieved; there is no text to analyse.")
        return {"result": engine.analyse(kind, aid)}

    @app.get("/api/cases")
    def cases(q: str = ""):
        rows = article_rows("(a.case_candidate = 1 OR EXISTS (SELECT 1 FROM analyses n WHERE n.kind = 'case_study' AND n.target_id = a.id))", [], q)
        return {"articles": rows, "labels": LABELS}


    @app.post("/api/cases/import")
    def import_case(body: UrlBody):
        try:
            res = collect.import_article(db, engine.fetcher, body.url.strip())
        except FetchError as e:
            raise HTTPException(400, str(e)) from None
        a = db.one("SELECT content_basis FROM articles WHERE id = ?", (res["id"],))
        if a["content_basis"] == "metadata":
            return {**res, "analysis": "No readable text on the page; nothing to analyse."}
        return {**res, "analysis": engine.analyse("case_study", res["id"])}

    # ------------------------------------------------------------ feedback

    @app.post("/api/feedback")
    def feedback(body: Feedback):
        if body.verdict not in VERDICTS or body.item_type not in ("job", "article", "case"):
            raise HTTPException(400, "Unknown feedback")
        if body.on:
            db.run("INSERT OR IGNORE INTO feedback (item_type, item_id, verdict, created_at) VALUES (?, ?, ?, ?)", (body.item_type, body.item_id, body.verdict, now_iso()))
        else:
            db.run("DELETE FROM feedback WHERE item_type = ? AND item_id = ? AND verdict = ?", (body.item_type, body.item_id, body.verdict))
        return {"ok": True, "suggestions": suggestions()}

    @app.get("/api/feedback/suggestions")
    def suggestions():
        prefs = engine.profiles.prefs()
        out = []
        tech = db.scalar("SELECT COUNT(*) FROM feedback WHERE verdict = 'too_technical'")
        if tech >= 2 and prefs["reading_level"] != "prefer_less_technical":
            out.append({"id": "less_technical", "text": f"You marked {tech} items too technical. Rank sources you marked that way lower in briefings?",
                        "change": {"reading_level": "prefer_less_technical"}})
        for r in db.all("SELECT a.source_id, a.source_name, COUNT(*) n FROM feedback f JOIN articles a ON a.id = f.item_id "
                        "WHERE f.item_type = 'article' AND f.verdict = 'not_relevant' AND a.source_id IS NOT NULL GROUP BY a.source_id HAVING n >= 2"):
            if r["source_id"] not in prefs["muted_sources"]:
                out.append({"id": f"mute_{r['source_id']}", "text": f"{r['n']} items from {r['source_name']} were not relevant. Leave this source out of briefings?",
                            "change": {"muted_sources": [*prefs["muted_sources"], r["source_id"]]}})
        for r in db.all("SELECT j.role_family, COUNT(*) n FROM jobs j LEFT JOIN feedback f ON f.item_type = 'job' AND f.item_id = j.id "
                        "WHERE (j.status = 'Not relevant' OR f.verdict = 'not_relevant') GROUP BY j.role_family HAVING n >= 3"):
            if r["role_family"] in prefs["role_families"]:
                fams = [f for f in prefs["role_families"] if f != r["role_family"]]
                out.append({"id": f"family_{r['role_family']}", "text": f"{r['n']} {jobrules.FAMILY_LABEL[r['role_family']].lower()} jobs were not relevant. Stop treating this role family as a match?",
                            "change": {"role_families": fams}})
        return out

    @app.post("/api/feedback/suggestions/{sid}")
    def apply_suggestion(sid: str):
        s = next((x for x in suggestions() if x["id"] == sid), None)
        if not s:
            raise HTTPException(404, "That suggestion no longer applies")
        return {"preferences": engine.profiles.save_prefs(s["change"])}

    # ------------------------------------------------------------ digests
    @app.get("/api/digests")
    def digests(status: str = "saved"):
        rows = db.all("SELECT id, created_at, status, content_json FROM digests WHERE status = ? ORDER BY id DESC LIMIT 100", (status,))
        out = []
        for r in rows:
            c = json.loads(r["content_json"])
            out.append({"id": r["id"], "created_at": r["created_at"], "status": r["status"], "jobs": len(c["jobs"]), "articles": len(c["articles"]),
                        "case": bool(c.get("case")), "quiet": c.get("quiet")})
        return {"digests": out}

    @app.get("/api/digests/{did}")
    def digest(did: int):
        r = db.one("SELECT * FROM digests WHERE id = ?", (did,))
        if not r:
            raise HTTPException(404, "Briefing not found")
        return {"id": r["id"], "created_at": r["created_at"], "status": r["status"], **json.loads(r["content_json"])}


    @app.patch("/api/digests/{did}")
    def patch_digest(did: int, body: DigestPatch):
        if body.status not in ("saved", "archived"):
            raise HTTPException(400, "Unknown status")
        db.update("digests", did, {"status": body.status})
        return {"ok": True}


    @app.post("/api/digests/generate")
    def generate(body: Generate):
        if body.regenerate:
            if not body.confirm:
                raise HTTPException(400, "Regenerating collects again and runs analysis for new or changed items. Confirm to continue.")
            return engine.start_all(trigger="regenerate")
        return {"started": [engine.start_run("digest_editor")["id"]]}

    # ------------------------------------------------------------ runs and usage
    @app.get("/api/runs")
    def runs(agent: str = ""):
        rows = db.all("SELECT * FROM runs WHERE (? = '' OR agent = ?) ORDER BY id DESC LIMIT 100", (agent, agent))
        for r in rows:
            r["stats"] = json.loads(r.pop("stats_json"))
            r.pop("log_json")
            r["agentName"] = AGENTS[r["agent"]]
            r["tasks"] = {x["status"]: x["n"] for x in db.all("SELECT status, COUNT(*) n FROM tasks WHERE run_id = ? GROUP BY status", (r["id"],))}
        return {"runs": rows, "agents": AGENTS}

    @app.get("/api/runs/{rid}")
    def run(rid: int):
        r = db.one("SELECT * FROM runs WHERE id = ?", (rid,))
        if not r:
            raise HTTPException(404, "Run not found")
        tasks = db.all("SELECT t.*, COALESCE(j.title, a.title) AS target_title FROM tasks t LEFT JOIN jobs j ON t.target_type = 'job' AND j.id = t.target_id "
                       "LEFT JOIN articles a ON t.target_type = 'article' AND a.id = t.target_id WHERE t.run_id = ? ORDER BY t.priority, t.id", (rid,))
        calls = db.all("SELECT purpose, model_served, duration_ms, tokens_in, tokens_out, finish_reason, ok, error, started_at FROM model_calls WHERE run_id = ? ORDER BY id", (rid,))
        return {**r, "stats": json.loads(r["stats_json"]), "log": json.loads(r["log_json"]), "agentName": AGENTS[r["agent"]], "tasks": tasks, "calls": calls}


    @app.post("/api/runs")
    def start(body: RunBody):
        if body.agent == "all":
            return engine.start_all()
        if body.agent not in AGENTS:
            raise HTTPException(400, "Unknown agent")
        return engine.start_run(body.agent)

    @app.post("/api/runs/{rid}/cancel")
    def cancel(rid: int):
        return engine.cancel_run(rid)

    @app.post("/api/runs/{rid}/retry")
    def retry(rid: int):
        return {"requeued": engine.retry_failed(rid)}

    @app.get("/api/usage")
    def usage():
        def block(since: str | None):
            cond, args = ("WHERE started_at >= ?", [since]) if since else ("", [])
            c = db.one(f"SELECT COUNT(*) requests, SUM(ok) ok, SUM(1 - ok) failed, SUM(duration_ms) ms, SUM(tokens_in) tin, SUM(tokens_out) tout, "
                       f"SUM(CASE WHEN ok = 1 AND tokens_in IS NULL THEN 1 ELSE 0 END) no_tokens FROM model_calls {cond}", args)
            rcond = "WHERE started_at >= ?" if since else ""
            stats = [json.loads(r["stats_json"]) for r in db.all(f"SELECT stats_json FROM runs {rcond}", args)]
            agg = lambda k: sum(s.get(k, 0) for s in stats)  # noqa: E731
            return {"modelRequests": c["requests"] or 0, "failedRequests": c["failed"] or 0, "modelSeconds": round((c["ms"] or 0) / 1000, 1),
                    "tokensIn": c["tin"], "tokensOut": c["tout"], "requestsWithoutTokenCounts": c["no_tokens"] or 0,
                    "fetched": agg("fetched"), "analysed": agg("analysed"), "cacheHits": agg("cache_hits"), "retries": agg("retries"), "errors": agg("errors"),
                    "runs": len(stats)}
        week = (datetime.now(timezone.utc) - timedelta(days=7)).replace(microsecond=0).isoformat()
        models = db.all("SELECT model_served, COUNT(*) n FROM model_calls WHERE ok = 1 GROUP BY model_served")
        return {"week": block(week), "all": block(None), "modelsServed": models, "paidApis": "disabled",
                "note": "Local inference has no per-token bill, but it uses this laptop's electricity and time; SignalDesk does not estimate those."}

    # ------------------------------------------------------------ sources

    def check_company(body: Company):
        if body.ats not in ("greenhouse", "lever", "ashby", "manual"):
            raise HTTPException(400, "Board type must be greenhouse, lever, ashby or manual")
        if body.ats != "manual" and not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", body.ats_id or ""):
            raise HTTPException(400, "Enter the board id from the job board address, e.g. 'stripe' in boards.greenhouse.io/stripe")
        if not re.match(r"https?://", body.careers_url):
            raise HTTPException(400, "The careers URL must start with https://")

    @app.post("/api/sources/discover")
    def discover_source(body: UrlBody):
        try:
            return discover(engine.fetcher, body.url)
        except (FetchError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/delivery")
    def delivery_status():
        return delivery.describe()

    @app.post("/api/delivery/sync")
    def sync_now():
        delivery.tick()
        return delivery.describe()

    @app.get("/api/sources")
    def sources():
        comps = db.all("SELECT c.*, (SELECT COUNT(*) FROM jobs j WHERE j.company_id = c.id AND j.listing_state = 'open') AS open_jobs, "
                       "(SELECT COUNT(*) FROM jobs j WHERE j.company_id = c.id AND j.listing_state = 'open' AND j.bucket = 'candidate') AS matches FROM companies c ORDER BY c.enabled DESC, c.name")
        feeds = db.all("SELECT s.*, (SELECT COUNT(*) FROM articles a WHERE a.source_id = s.id) AS items FROM reading_sources s ORDER BY s.enabled DESC, s.name")
        return {"companies": comps, "feeds": feeds}

    @app.post("/api/sources/companies")
    def add_company(body: Company):
        check_company(body)
        cid = db.insert("companies", {"name": body.name.strip(), "careers_url": body.careers_url.strip(), "ats": body.ats, "ats_id": body.ats_id.strip() or None,
                                      "enabled": int(body.enabled), "verification": body.verification.strip() or "Added by you", "created_at": now_iso()})
        return {"id": cid}

    @app.put("/api/sources/companies/{cid}")
    def edit_company(cid: int, body: Company):
        check_company(body)
        db.update("companies", cid, {"name": body.name.strip(), "careers_url": body.careers_url.strip(), "ats": body.ats, "ats_id": body.ats_id.strip() or None,
                                     "enabled": int(body.enabled), "verification": body.verification.strip()})
        return {"ok": True}

    @app.post("/api/sources/companies/{cid}/test")
    def test_company(cid: int):
        c = db.one("SELECT * FROM companies WHERE id = ?", (cid,))
        if not c:
            raise HTTPException(404, "Not found")
        if c["ats"] == "manual":
            return {"result": "This employer is checked by hand: open its careers page."}
        res = collect.collect_company(db, engine.fetcher, c, engine.profiles.prefs())
        if res.get("error"):
            return {"result": f"Failed: {res['error']}"}
        return {"result": res.get("warning") or f"{res['fetched']} listings: {res['new']} new, {res['changed']} changed, {res['closed']} no longer listed."}


    @app.post("/api/sources/feeds")
    def add_feed(body: Feed):
        if body.kind not in ("substack", "blog", "engineering", "vendor") or not re.match(r"https?://", body.feed_url):
            raise HTTPException(400, "Check the feed address and type")
        fid = db.insert("reading_sources", {"name": body.name.strip(), "feed_url": body.feed_url.strip(), "site_url": body.site_url.strip(),
                                            "kind": body.kind, "enabled": int(body.enabled), "verification": "Added by you", "created_at": now_iso()})
        return {"id": fid}

    @app.put("/api/sources/feeds/{fid}")
    def edit_feed(fid: int, body: Feed):
        db.update("reading_sources", fid, {"name": body.name.strip(), "feed_url": body.feed_url.strip(), "site_url": body.site_url.strip(),
                                           "kind": body.kind, "enabled": int(body.enabled)})
        return {"ok": True}

    @app.post("/api/sources/feeds/{fid}/test")
    def test_feed(fid: int):
        s = db.one("SELECT * FROM reading_sources WHERE id = ?", (fid,))
        if not s:
            raise HTTPException(404, "Not found")
        res = collect.collect_source(db, engine.fetcher, s, engine.cfg.limits.items_per_feed)
        return {"result": f"Failed: {res['error']}" if res.get("error") else f"{res['fetched']} items: {res['new']} new, {res['duplicate']} repeats."}

    # ------------------------------------------------------------ profile and settings
    @app.get("/api/profile")
    def get_profile():
        return {"profile": engine.profiles.profile(), "version": engine.profiles.profile_version(), "preferences": engine.profiles.prefs(),
                "families": {k: v for k, v in jobrules.FAMILY_LABEL.items() if k not in ("ambiguous", "other")},
                "locations": jobrules.LOCATION_LABEL}

    @app.post("/api/profile/cv-preview")
    async def cv_preview(request: Request, filename: str):
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, "Choose a CV smaller than 5 MB.")
            payload.extend(chunk)
        try:
            return await run_in_threadpool(preview_cv, filename, bytes(payload))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.put("/api/profile")
    def put_profile(body: dict):
        return {"profile": engine.profiles.save_profile(body), "version": engine.profiles.profile_version()}

    @app.put("/api/preferences")
    def put_prefs(body: dict):
        return {"preferences": engine.profiles.save_prefs(body)}

    @app.get("/api/settings")
    def settings():
        m = engine.cfg.model
        return {"model": {"base_url": m.base_url, "model_id": m.model_id, "context_tokens": m.context_tokens, "max_output_tokens": m.max_output_tokens,
                          "prompt_char_budget": m.prompt_char_budget, "timeout": m.request_timeout_seconds, "max_attempts": m.max_attempts},
                "limits": vars(engine.cfg.limits), "fetch": {k: v for k, v in vars(engine.cfg.fetch).items()},
                "dataDir": str(engine.cfg.home), "configFile": str(engine.cfg.home / "config.toml"), "schedule": scheduler.describe(),
                "server": vars(engine.cfg.server)}


    @app.put("/api/schedule")
    def put_schedule(body: ScheduleBody):
        try:
            return scheduler.update(body.enabled, body.time)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    # ------------------------------------------------------------ the web app
    if WEB.exists():
        app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = WEB / path
            if path and f.is_file() and WEB in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(WEB / "index.html")

    return app
