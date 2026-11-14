"""Demo mode:  python -m signaldesk --demo

Runs the app against a synthetic database in a new temporary folder, for screenshots and for trying
SignalDesk without your setup. Everything comes from the test fixtures: invented employers, postings,
articles and model outputs (eval/cases.json, eval/run_eval.py, tests/fixtures). Nothing is fetched and
no model is called: the fetcher and the model below refuse every request, and the API refuses runs.
Your data folder, config and cloud settings are never read.
"""
from __future__ import annotations

import json
import string
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import analysis, collect
from .config import Config, load_config
from .db import DB, now_iso
from .llm import ModelUnavailable
from .netsafe import FetchError

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "eval" / "cases.json"
V3 = ROOT / "tests" / "fixtures" / "v3_synthetic.json"
PROFILE = ROOT / "tests" / "fixtures" / "profile_synthetic.json"
MODEL_ID = "demo: no model was run"
MESSAGE = "Demo data: invented employers, jobs and articles. Collection and model calls are off."


class DemoFetcher:
    """Stands in for netsafe.Fetcher. Every request is refused before any connection is made."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.requests: list[str] = []

    def get(self, url: str, **_kw):
        self.requests.append(url)
        raise FetchError("Demo mode: SignalDesk does not fetch anything.")


class DemoModel:
    """Stands in for llm.LocalModel. Always unavailable, so analysis tasks wait and nothing is sent."""

    def __init__(self, cfg):
        self.cfg = cfg

    def status(self) -> dict:
        return {"reachable": False, "served": [], "configured": self.cfg.model_id, "ready": False, "message": "Demo mode: model calls are off."}

    def chat(self, *_a, **_kw):
        raise ModelUnavailable("Demo mode: model calls are off.")


def _ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()


def _employer(i: int) -> str:
    return "Fixture Co" if i == 0 else f"Synthetic Startup {string.ascii_uppercase[(i - 1) % 26]} (fixture)"


def _req_lines(text: str) -> list[str]:
    """Bullet lines under the posting's requirement and preference headings, as written."""
    out, section = {"essential": [], "preferred": []}, None
    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if low.endswith(":"):
            section = "preferred" if any(w in low for w in ("prefer", "nice", "bonus", "plus")) else \
                "essential" if any(w in low for w in ("require", "qualif", "must", "you have", "need")) else None
            continue
        if section and line.startswith(("-", "*", "•")):
            out[section].append(line.lstrip("-*• ").strip())
    return out["essential"][:4] + ["|"] + out["preferred"][:2]


def _fit_output(job: dict, profile: dict) -> dict:
    """A demo answer in the model's own schema, built from the posting's lines and passed through the
    app's validator like any model reply. It is labelled as demo data; no model wrote it."""
    lines = _req_lines(job["description_text"] or "")
    cut = lines.index("|")
    essential, preferred = lines[:cut], lines[cut + 1:]
    text = (job["description_text"] or "").lower()
    cited = [f["id"] for f in profile["facts"] if any(w in text for w in ("sql", "analytics", "stakeholder") if w in f["text"].lower())][:2]
    match = "potential match" if cited and essential else "weak match" if essential else "unknown"
    return {"essential": [{"req": e, "quote": e} for e in essential], "preferred": [{"req": p, "quote": p} for p in preferred],
            "evidence": [{"req": essential[0], "facts": cited, "note": "Demo: matched on shared words"}] if cited and essential else [],
            "gaps": ["Demo data: no real assessment"], "unknowns": ["Team size"], "match": match,
            "summary": "Demo data. A real analysis comes from your local model.", "injection_seen": False}


def build(home: Path) -> Config:
    """Create the synthetic data folder. Returns its configuration with demo mode on."""
    cfg = load_config(home)
    cfg.demo = True
    cfg.model.model_id = MODEL_ID
    profile = {k: v for k, v in json.loads(PROFILE.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    profile["name"], profile["summary"] = "Demo profile", "Invented facts for demo mode."
    cfg.profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    db = DB(cfg.db_path)

    # Avoid a circular import: Engine needs this module's classes only at run time.
    from .engine import Engine
    engine = Engine(cfg, db, DemoModel(cfg.model), DemoFetcher(cfg.fetch), start_worker=False)
    prefs = engine.profiles.prefs()
    cases, v3 = json.loads(CASES.read_text(encoding="utf-8")), json.loads(V3.read_text(encoding="utf-8"))

    postings = [(c["id"], c["title"], c["location"], c["description"]) for c in cases["jobs"]]
    postings += [(f"v3-{r['id']}", r["title"], "Bengaluru, Karnataka, India", r["description"]) for r in v3["roles"]]
    companies: dict[str, int] = {}
    for i, (pid, title, location, description) in enumerate(postings):
        employer = _employer(i % 9)
        if employer not in companies:
            slug = employer.lower().replace(" ", "-").replace("(", "").replace(")", "")
            companies[employer] = db.insert("companies", {"name": employer, "careers_url": f"https://{slug}.example/careers", "ats": "manual",
                                                          "enabled": 1, "verification": "Demo data (invented)", "created_at": _ago(30)})
        url = f"https://{employer.split(' (')[0].lower().replace(' ', '-')}.example/jobs/{pid}"
        collect.upsert_job(db, {"ext_id": f"demo:{pid}", "title": title, "location": location, "workplace": None, "description_text": description,
                                "official_url": url, "apply_url": url, "published_at": _ago(i % 6), "salary_extra": None},
                           company_id=companies[employer], employer=employer, source="manual", prefs=prefs, now=_ago(i % 5))
    db.run("UPDATE jobs SET last_verified_at = ?", (now_iso(),))

    # Job-fit analyses for the matching jobs, saved exactly as the app saves real ones.
    for j in db.all("SELECT * FROM jobs WHERE bucket = 'candidate' ORDER BY id LIMIT 6"):
        out, val = analysis.validate_job(_fit_output(j, profile), j, profile)
        val["notes"].append("Demo data: written from the posting's own lines, not by a model.")
        engine._save({"target_id": j["id"], "cache_key": engine.key_for("job_fit", j["id"])}, "job_fit", "job", out, val,
                     {"coverage": {"chars_sent": len(j["description_text"] or ""), "chars_total": len(j["description_text"] or ""), "complete": True},
                      "facts_sent": profile["facts"]}, MODEL_ID)

    # Articles: the evaluation's invented articles, with reading cards and a case study.
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from eval.run_eval import ARTICLES
    src = {"id": db.insert("reading_sources", {"name": "Fixture feed (demo)", "feed_url": "https://feed.fixture.example/rss", "site_url": "https://feed.fixture.example",
                                               "kind": "blog", "enabled": 1, "verification": "Demo data (invented)", "created_at": _ago(30)}),
           "name": "Fixture feed (demo)", "kind": "blog"}
    for k, a in enumerate(ARTICLES):
        collect.upsert_article(db, {"url": f"https://feed.fixture.example/{a['id']}", "title": a["title"], "content_text": a["content_text"],
                                    "content_basis": a["content_basis"], "author": a["author"], "published_at": _ago(k + 1)},
                               source={**src, "name": a["source_name"], "kind": a["source_kind"]}, now=_ago(k + 1))
    for art in db.all("SELECT * FROM articles"):
        first = (art["content_text"] or "").split(". ")[0].strip()
        card, val = analysis.validate_card({"main_argument": first, "evidence": [{"point": "The article states this", "quote": first[:80]}],
                                            "why_it_matters": "Demo data: shows how a reading card looks.", "limitations": "Demo data, not an analysis.",
                                            "concept": {"term": "Evaluation set", "explanation": "Examples with known answers used to check a system."},
                                            "kind": "case_study" if art["source_kind"] == "vendor" else "opinion"}, art)
        engine._save({"target_id": art["id"], "cache_key": engine.key_for("reading_card", art["id"])}, "reading_card", "article", card, val, {}, MODEL_ID)
    vendor = db.one("SELECT * FROM articles WHERE source_kind = 'vendor'")
    if vendor:
        c = next(x for x in cases["case_outputs"] if x["id"] == "vendor-claim")
        out, val = analysis.validate_case({**c["model_output_a"], "suitability": "strong"}, c["model_output_b"], vendor)
        engine._save({"target_id": vendor["id"], "cache_key": engine.key_for("case_study", vendor["id"])}, "case_study", "article", out, val, {}, MODEL_ID)
        db.run("UPDATE articles SET case_candidate = 1 WHERE id = ?", (vendor["id"],))

    # One briefing, composed by the Digest Editor's own rules (the model is off, so the rule writes the action).
    from .digest import compose
    run = db.insert("runs", {"agent": "digest_editor", "trigger": "manual", "status": "done", "started_at": now_iso(), "finished_at": now_iso(),
                             "stats_json": "{}", "log_json": json.dumps([{"at": now_iso(), "msg": "Demo briefing built from fixtures."}]), "options_json": "{}"})
    compose(engine, {"id": 0, "run_id": run, "attempts": 0, "error": None})
    engine.stop_flag.set()
    return cfg


def start_home() -> Path:
    """A new, empty temporary folder for one demo session."""
    return Path(tempfile.mkdtemp(prefix="signaldesk-demo-"))
