"""Digest Editor: picks a few items by rule, explains why each is there, and asks the model for one
suggested action. A quiet day gives a short briefing; nothing is padded."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import analysis, collect, jobrules
from .db import now_iso
from .llm import ModelError, ModelUnavailable

RECENT_DIGESTS = 3
RECHECK_HOURS = 12


def _age_hours(iso: str | None) -> float:
    if not iso:
        return 1e9
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def recent_refs(db) -> set[str]:
    refs = set()
    for d in db.all("SELECT content_json FROM digests ORDER BY id DESC LIMIT ?", (RECENT_DIGESTS,)):
        c = json.loads(d["content_json"])
        for sec in ("jobs", "articles"):
            refs |= {f"{i['type']}:{i['id']}:{i.get('version', '')}" for i in c.get(sec, [])}
        if c.get("case") and c["case"].get("id"):
            refs.add(f"case:{c['case']['id']}:")
    return refs


def _feedback(db, item_type: str) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for r in db.all("SELECT item_id, verdict FROM feedback WHERE item_type = ?", (item_type,)):
        out.setdefault(r["item_id"], set()).add(r["verdict"])
    return out


def pick_jobs(engine, limit: int, seen: set[str]) -> list[dict]:
    db, prefs = engine.db, engine.profiles.prefs()
    fb = _feedback(db, "job")
    rows = db.all("SELECT * FROM jobs WHERE bucket = 'candidate' AND listing_state = 'open' AND duplicate_of IS NULL "
                  "AND status IN ('New', 'Interested', 'Investigate') ORDER BY first_seen_at DESC LIMIT 200")
    scored = []
    for j in rows:
        if fb.get(j["id"], set()) & {"not_relevant", "known"}:
            continue
        if f"job:{j['id']}:{j['content_hash'][:8]}" in seen:
            continue
        fit = engine.latest("job_fit", "job", j["id"])
        match = fit["output"]["match"] if fit and not fit["outdated"] else None
        if match == "not a match":
            continue
        score = {"potential match": 3, "weak match": 1, "unknown": 0, None: 0}[match]
        score += 1 if j["change_state"] in ("new", "changed") else 0
        note = jobrules.compensation_note(j["salary_text"], j["salary_kind"], prefs["ctc_threshold_lakh"])
        score += 1 if "meets" in note else 0
        score -= 2 * sum(t.lower() in j["title"].lower() for t in prefs.get("muted_terms", []))
        scored.append((score, j["first_seen_at"], j, fit, note))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [{"job": j, "fit": fit, "comp": note} for _s, _t, j, fit, note in scored[:limit]]


def recheck(engine, picked: list[dict], notes: list[str]) -> None:
    """Re-fetch the boards of chosen jobs that were not verified recently, so 'open' is current."""
    prefs = engine.profiles.prefs()
    done = set()
    for p in picked:
        j = p["job"]
        if j["company_id"] and j["company_id"] not in done and _age_hours(j["last_verified_at"]) > RECHECK_HOURS:
            done.add(j["company_id"])
            company = engine.db.one("SELECT * FROM companies WHERE id = ?", (j["company_id"],))
            res = collect.collect_company(engine.db, engine.fetcher, company, prefs)
            if res.get("error"):
                notes.append(f"Could not recheck {company['name']} ({res['error']}); its jobs are shown as last verified.")
    for p in picked:
        p["job"] = engine.db.one("SELECT * FROM jobs WHERE id = ?", (p["job"]["id"],))
        p["fit"] = engine.latest("job_fit", "job", p["job"]["id"])
        p["comp"] = jobrules.compensation_note(
            p["job"]["salary_text"], p["job"]["salary_kind"], prefs["ctc_threshold_lakh"])


def job_item(engine, p: dict) -> dict:
    j, fit = p["job"], p["fit"]
    badges = []
    if j["listing_state"] != "open":
        badges.append({"tone": "danger", "text": "No longer listed"})
    if _age_hours(j["last_verified_at"]) > 48:
        badges.append({"tone": "warning", "text": "Not verified in 2 days"})
    if j["location_class"] != "bengaluru":
        badges.append({"tone": "warning", "text": jobrules.LOCATION_LABEL[j["location_class"]]})
    if not fit:
        badges.append({"tone": "neutral", "text": "Fit analysis pending"})
    elif fit["outdated"]:
        badges.append({"tone": "warning", "text": "Analysis outdated"})
    if fit and fit["outdated"]:
        fit = None  # Historical wording stays on the detail page, not the new digest.
    why = [j["bucket_reason"]]
    if fit and fit["output"]["evidence"]:
        why.append(f"Your background touches: {fit['output']['evidence'][0]['req']}")
    why.append(f"Pay: {p['comp']}")
    return {"type": "job", "id": j["id"], "version": j["content_hash"][:8], "origin": "manual" if j["source"] in collect.MANUAL_SOURCES else "board",
            "title": j["title"], "subtitle": f"{j['employer']} · {j['location_raw'] or 'location not stated'}",
            "summary": fit["output"]["summary"] if fit else None, "match": fit["output"]["match"] if fit else None,
            "why": why, "badges": badges, "detail": f"#/jobs/{j['id']}", "original_url": j["official_url"]}


def pick_articles(engine, limit: int, seen: set[str]) -> list[dict]:
    db, prefs = engine.db, engine.profiles.prefs()
    fb = _feedback(db, "article")
    too_technical_sources = {r["source_id"] for r in db.all(
        "SELECT a.source_id FROM feedback f JOIN articles a ON a.id = f.item_id WHERE f.item_type = 'article' AND f.verdict = 'too_technical'")}
    rows = db.all("SELECT a.* FROM articles a JOIN analyses n ON n.kind = 'reading_card' AND n.target_id = a.id "
                  "WHERE a.duplicate_of IS NULL GROUP BY a.id ORDER BY COALESCE(a.published_at, a.retrieved_at) DESC LIMIT 100")
    out = []
    for a in rows:
        if fb.get(a["id"]) or f"article:{a['id']}:" in seen or a["source_id"] in prefs.get("muted_sources", []):
            continue
        card = engine.latest("reading_card", "article", a["id"])
        score = -_age_hours(a["published_at"] or a["retrieved_at"]) / 24
        score += 1 if a["content_basis"] == "full" else 0
        if prefs.get("reading_level") == "prefer_less_technical" and a["source_id"] in too_technical_sources:
            score -= 3
        score -= 2 * sum(t.lower() in a["title"].lower() for t in prefs.get("muted_terms", []))
        out.append((score, a, card))
    out.sort(key=lambda x: x[0], reverse=True)
    return [{"article": a, "card": c} for _s, a, c in out[:limit]]


def article_item(p: dict) -> dict:
    a, card = p["article"], p["card"]
    badges = []
    if a["content_basis"] != "full":
        badges.append({"tone": "warning", "text": "Excerpt only" if a["content_basis"] == "excerpt" else "Title only"})
    if card and card["outdated"]:
        badges.append({"tone": "warning", "text": "Analysis outdated"})
    why = [f"From {a['source_name']}, a source you follow"]
    if card and card["output"]["why_it_matters"] != "unknown":
        why.append(card["output"]["why_it_matters"])
    return {"type": "article", "id": a["id"], "title": a["title"], "subtitle": f"{a['source_name']} · {(a['published_at'] or '')[:10]}",
            "summary": card["output"]["main_argument"] if card else None, "why": why, "badges": badges,
            "detail": f"#/reading/{a['id']}", "original_url": a["url"]}


def pick_case(engine, seen: set[str]) -> tuple[dict | None, int]:
    rows = engine.db.all("SELECT target_id FROM analyses WHERE kind = 'case_study' GROUP BY target_id ORDER BY MAX(id) DESC LIMIT 30")
    weak = 0
    for r in rows:
        res = engine.latest("case_study", "article", r["target_id"])
        if f"case:{r['target_id']}:" in seen:
            continue
        if res["output"]["suitability"] == "strong":
            a = engine.db.one("SELECT * FROM articles WHERE id = ?", (r["target_id"],))
            o = res["output"]
            return {"type": "case", "id": a["id"], "title": a["title"], "subtitle": a["source_name"],
                    "summary": o["ai_contribution"]["text"], "why": [f"Problem: {o['bottleneck']['text']}", f"Lesson: {o['lesson']['text']}"],
                    "badges": ([{"tone": "warning", "text": "Vendor-published"}] if a["source_kind"] == "vendor" else []),
                    "detail": f"#/cases/{a['id']}", "original_url": a["url"]}, weak
        weak += 1
    return None, weak


def compose(engine, task: dict) -> dict:
    db, prefs = engine.db, engine.profiles.prefs()
    limits = prefs.get("digest", {})
    seen = recent_refs(db)
    notes: list[str] = []
    jobs = pick_jobs(engine, int(limits.get("jobs", 3)), seen)
    recheck(engine, jobs, notes)
    jobs = [p for p in jobs if p["job"]["listing_state"] == "open" and p["job"]["bucket"] == "candidate"]
    job_items = [job_item(engine, p) for p in jobs]
    arts = pick_articles(engine, int(limits.get("articles", 2)), seen)
    art_items = [article_item(p) for p in arts]
    case, weak = pick_case(engine, seen) if int(limits.get("case_studies", 1)) else (None, 0)
    term = None
    used_terms = {(json.loads(d["content_json"]).get("term") or {}).get("term", "").lower()
                  for d in db.all("SELECT content_json FROM digests ORDER BY id DESC LIMIT 10")} - {""}
    for p in arts + [{"card": engine.latest("reading_card", "article", r["target_id"]), "article": db.one("SELECT * FROM articles WHERE id = ?", (r["target_id"],))}
                     for r in db.all("SELECT target_id FROM analyses WHERE kind = 'reading_card' ORDER BY id DESC LIMIT 20")]:
        c = p["card"] and p["card"]["output"]["concept"]
        if c and c["term"] != "unknown" and c["explanation"] != "unknown" and c["term"].lower() not in used_terms:
            term = {**c, "from_title": p["article"]["title"], "detail": f"#/reading/{p['article']['id']}", "original_url": p["article"]["url"]}
            break
    pending = db.scalar("SELECT COUNT(*) FROM tasks WHERE status = 'queued'") or 0
    if pending:
        notes.append(f"{pending} analysis task(s) are still waiting; some items may be partly analysed.")
    if case is None:
        notes.append("No strong case study among analysed articles" + (f" ({weak} weaker candidate(s) not shown)." if weak else "."))

    entries = [{"ref": f"J{i + 1}", "line": f"Job: {it['title']} ({it['subtitle']}). {it['summary'] or ''}"} for i, it in enumerate(job_items)]
    entries += [{"ref": f"A{i + 1}", "line": f"Article: {it['title']}. {it['summary'] or ''}"} for i, it in enumerate(art_items)]
    if case:
        entries.append({"ref": "C1", "line": f"Case study: {case['title']}. {case['summary']}"})
    action = None
    if entries:
        try:
            if not engine.check_model()["ready"]:
                raise ModelUnavailable(engine.model_state["message"])
            reply = engine._call(task, "digest_action", analysis.action_prompt(entries), max_tokens=160)
            out, _ = analysis.validate_action(analysis.parse_json(reply.text), {e["ref"] for e in entries})
            action = {**out, "by": "model", "model_id": reply.model_served}
        except (ModelUnavailable, ModelError, ValueError) as e:
            first = entries[0]
            action = {"action": f"Open {first['line'].split('.')[0]} and decide whether it deserves your time this week.",
                      "ref": first["ref"], "by": "rule", "reason": f"The model did not provide one ({str(e)[:120]})."}
    content = {
        "generated_at": now_iso(), "jobs": job_items, "articles": art_items, "case": case, "term": term, "action": action,
        "refs": {e["ref"]: e["line"] for e in entries}, "notes": notes, "quiet": not (job_items or art_items or case),
        "model_id": engine.cfg.model.model_id,
    }
    digest_id = db.insert("digests", {"created_at": content["generated_at"], "status": "saved", "run_id": task["run_id"], "content_json": json.dumps(content)})
    try:
        (engine.cfg.digests_dir / f"briefing-{digest_id}.md").write_text(to_markdown(digest_id, content), encoding="utf-8")
    except OSError:
        pass
    return {"id": digest_id, **content}


def to_markdown(digest_id: int, c: dict) -> str:
    lines = [f"# SignalDesk briefing {digest_id}", f"Generated {c['generated_at']}", ""]
    for title, items in (("Jobs", c["jobs"]), ("Reading", c["articles"])):
        if items:
            lines.append(f"## {title}")
            for it in items:
                lines += [f"- **{it['title']}** ({it['subtitle']}) {it['original_url']}", *(f"  - {w}" for w in it["why"])]
            lines.append("")
    if c.get("case"):
        lines += ["## Case study", f"- **{c['case']['title']}** {c['case']['original_url']}", ""]
    if c.get("term"):
        lines += ["## Term", f"**{c['term']['term']}**: {c['term']['explanation']}", ""]
    if c.get("action"):
        lines += ["## Suggested action", c["action"]["action"], ""]
    if c.get("notes"):
        lines += ["## Notes", *(f"- {n}" for n in c["notes"])]
    return "\n".join(lines)
