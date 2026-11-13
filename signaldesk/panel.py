"""Edge side panel backend: manual review of jobs you paste from LinkedIn (or anywhere).

Nothing here fetches a pasted URL. Pasted text is parsed by rules, saved as a "manual import",
matched to an employer/ATS record when the employer and title match one unambiguously, ranked
with the same rules and local-model fit analysis as the rest of SignalDesk, and counted once per
search label however often it is pasted.

Routes (reachable with a side-panel token, a signed-in session, or from this PC):
  GET  /api/panel/ping, /api/panel/labels, /api/panel/metrics, /api/panel/results?ids=
  POST /api/panel/parse, /api/panel/import, /api/panel/jobs/{id}/decision, /api/panel/jobs/{id}/description
"""
from __future__ import annotations

import json
import re

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import collect, jobrules
from .db import now_iso
from .text import canonical_url, norm, sha, title_key

SOURCE = "manual_import"          # shown as "Manual import"; never fetched, never synced unless you enable it
THIN_CHARS = 600                  # less description than this is not enough to assess fit
ELIGIBLE = ("bengaluru", "remote_india")
NOISE = re.compile(r"^(promoted|easy apply|viewed|saved|applied|actively (reviewing|recruiting)( applicants)?|be an early applicant|"
                   r"with verification|show more|show less|save|apply|\d+ (applicants?|clicked apply)|over \d+ applicants|"
                   r"(reposted )?\d+ (second|minute|hour|day|week|month)s? ago|your profile matches.*|\d+ connections? work here.*|"
                   r"see how you compare.*|alumni work here.*|response insights.*|.*school alumni.*)$", re.I)
LOCATION_LINE = re.compile(r"\b(bengaluru|bangalore|india|remote|hybrid|on-site|onsite|mumbai|delhi|gurugram|gurgaon|hyderabad|pune|chennai|"
                           r"noida|united states|london|singapore)\b", re.I)
LI_ID = re.compile(r"linkedin\.com/(?:jobs/view/(?:[^/?#]*-)?(\d{6,})|.*[?&]currentJobId=(\d{6,}))", re.I)
URL = re.compile(r"https?://[^\s<>\"]+")


class ParseBody(BaseModel):
    text: str


class Listing(BaseModel):
    title: str
    company: str
    location: str = ""
    url: str = ""
    description: str = ""


class ImportBody(BaseModel):
    label: str
    listings: list[Listing]


class DecisionBody(BaseModel):
    decision: str                 # shortlist | dismiss | clear


class DescriptionBody(BaseModel):
    description: str


# ---------------------------------------------------------------- parsing pasted text (rules only)
def _clean_lines(block: str) -> list[str]:
    out = []
    for raw in block.splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" ·•\t")
        if not line or NOISE.match(line) or URL.fullmatch(line):
            continue
        if out and line.lower().startswith(out[-1].lower()) and len(line) - len(out[-1]) <= 20:
            continue                                   # LinkedIn repeats a title for screen readers
        out.append(line)
    return out


def _full_description(block: str) -> dict | None:
    """A whole job page: title, then 'Company · Location · posted · applicants', then 'About the job'."""
    m = re.search(r"\babout the job\b", block, re.I)
    if not m:
        return None
    head = _clean_lines(block[: m.start()])
    desc = block[m.end():].strip()
    title = head[0] if head else ""
    company, location = "", ""
    for line in head[1:4]:
        parts = [p.strip() for p in re.split(r"\s+·\s+|\s+\|\s+", line) if p.strip()]
        if len(parts) >= 2:
            company, location = parts[0], parts[1]
            break
        if not company:
            company = line
        elif not location and LOCATION_LINE.search(line):
            location = line
    return {"title": title, "company": company, "location": location, "description": desc}


def parse(text: str) -> dict:
    """Split pasted text into listings. Separate listings with a line of three dashes (---) to set
    the boundaries yourself; otherwise cards are found from their title / company / location lines."""
    text = (text or "").replace("\r\n", "\n")
    urls = URL.findall(text)
    blocks = [b for b in re.split(r"\n\s*-{3,}\s*\n", text) if b.strip()] if re.search(r"\n\s*-{3,}\s*\n", text) else [text]
    out, notes = [], []
    for block in blocks:
        full = _full_description(block)
        if full:
            out.append(full)
            continue
        lines = _clean_lines(block)
        found = False
        i = 2
        while i < len(lines):
            if LOCATION_LINE.search(lines[i]) and not LOCATION_LINE.search(lines[i - 2]) and len(lines[i - 2]) <= 120:
                out.append({"title": lines[i - 2], "company": lines[i - 1], "location": lines[i], "description": ""})
                found = True
                i += 3
            else:
                i += 1
        if not found and lines:
            out.append({"title": lines[0], "company": lines[1] if len(lines) > 1 else "", "location": next((l for l in lines[2:] if LOCATION_LINE.search(l)), ""),
                        "description": "\n".join(lines[2:])})
            notes.append("One listing was guessed from loose text. Check its title, company and location.")
    block_urls = [u for u in urls if "linkedin.com" in u or len(urls) == len(out)]
    for item, u in zip(out, block_urls if len(block_urls) == len(out) else []):
        item["url"] = u.rstrip(").,;")
    if urls and len(block_urls) != len(out):
        notes.append("Links could not be matched to listings one-to-one; add each listing's link yourself.")
    for item in out:
        item.setdefault("url", "")
        item["thin"] = len(item["description"]) < THIN_CHARS
    return {"listings": out, "notes": notes}


# ---------------------------------------------------------------- saving
def ext_id_for(item: dict) -> str:
    """Stable identity so pasting the same job again updates one record (and keeps your decision)."""
    m = LI_ID.search(item.get("url") or "")
    if m:
        return "li:" + (m.group(1) or m.group(2))
    # The location's class, not its wording, so "Bengaluru" and "Bengaluru, Karnataka (Hybrid)" stay one job.
    where = jobrules.classify_location(item.get("location") or "").cls
    return "mi:" + sha(norm(item["company"]), title_key(item["title"]), where)[:16]


def save(engine, item: dict, label: str, batch_id: int) -> int:
    """Save or refresh one pasted listing; return the job record it belongs to."""
    db, prefs, now = engine.db, engine.profiles.prefs(), now_iso()
    ext = ext_id_for(item)
    source_url = canonical_url(item["url"]) if item.get("url", "").startswith(("http://", "https://")) else f"manual-import:{ext}"
    known = db.one("SELECT job_id FROM job_sources WHERE source = ? AND url = ?", (SOURCE, source_url))
    existing = db.one("SELECT id, duplicate_of, description_text FROM jobs WHERE source = ? AND ext_id = ?", (SOURCE, ext))
    target = None
    if known:
        target = known["job_id"]
    else:
        board, _seen = collect._match_board_job(db, {"title": item["title"], "employer": item["company"], "location": item.get("location"), "url": None})
        target = board
    if target and not existing:
        collect.note_source(db, target, SOURCE, source_url, now)       # where you found it is kept
    else:
        desc = item.get("description") or (existing["description_text"] if existing else "") or ""
        p = {"ext_id": ext, "title": item["title"].strip()[:300], "location": (item.get("location") or "").strip() or None, "workplace": None,
             "description_text": desc.strip(), "official_url": item["url"] if item.get("url", "").startswith("http") else None,
             "apply_url": item["url"] if item.get("url", "").startswith("http") else None, "published_at": None, "salary_extra": None}
        collect.upsert_job(db, p, company_id=None, employer=item["company"].strip()[:200] or "Unknown employer", source=SOURCE, prefs=prefs, now=now)
        row = db.one("SELECT id, bucket FROM jobs WHERE source = ? AND ext_id = ?", (SOURCE, ext))
        collect.note_source(db, row["id"], SOURCE, source_url, now)
        upd = {"verification_state": "unverified", "last_verified_at": None}
        if row["bucket"] == "candidate":
            upd.update(bucket="review", bucket_reason="Manual import; not yet confirmed on the employer's own job board")
        db.update("jobs", row["id"], upd)
        target = row["id"]
        board, _seen = collect._match_board_job(db, {"title": item["title"], "employer": item["company"], "location": item.get("location"), "url": None})
        if board and board != target:
            db.update("jobs", target, {"duplicate_of": board})
            collect.note_source(db, board, SOURCE, source_url, now)
    canonical = db.scalar("SELECT COALESCE(duplicate_of, id) FROM jobs WHERE id = ?", (target,))
    db.run("INSERT INTO panel_items (label, job_id, first_batch_id, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?) "
           "ON CONFLICT(label, job_id) DO UPDATE SET last_seen_at = excluded.last_seen_at, times_pasted = times_pasted + 1",
           (label, canonical, batch_id, now, now))
    return canonical


def enough_evidence(job: dict) -> bool:
    return job["source"] != SOURCE or len(job.get("description_text") or "") >= THIN_CHARS


def assess(engine, job_id: int) -> None:
    """Rules first; the local model only for eligible listings with enough text. Cached by content."""
    job = engine.db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if job["location_class"] in ELIGIBLE and enough_evidence(job) and job["bucket"] != "outside":
        engine.analyse("job_fit", job_id, None, 15)


# ---------------------------------------------------------------- results
def result(engine, job_id: int) -> dict:
    db = engine.db
    j = db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    fams = json.loads(j.get("role_families") or "[]") or [j.get("role_family") or "other"]
    fit = engine.latest("job_fit", "job", job_id)
    o = fit["output"] if fit and not fit["outdated"] else None
    waiting = db.scalar("SELECT status FROM tasks WHERE kind = 'job_fit' AND target_id = ? AND status IN ('queued', 'running') LIMIT 1", (job_id,))
    eligible = j["location_class"] in ELIGIBLE
    if not eligible:
        state = "location_not_eligible"
    elif not enough_evidence(j):
        state = "need_full_description"
    elif o:
        state = "assessed"
    elif waiting:
        state = "queued" if engine.model_state.get("ready", True) else "queued_model_offline"
    else:
        state = "not_assessed"
    facts = {f["id"]: f["text"] for f in (fit["inputs"].get("facts_sent") or [])} if fit else {}
    evidence_list = json.loads(j.get("role_evidence") or "[]")
    phrase = next((q["quote"] for q in (o["essential"] if o else []) if q.get("quote_found")), None) or (evidence_list[0] if evidence_list else None)
    background = next((facts.get(fid) for e in (o["evidence"] if o else []) for fid in e["facts"] if facts.get(fid)), None)
    gap = (o["gaps"][0] if o and o["gaps"] else (o["unknowns"][0] if o and o["unknowns"] else None))
    if state == "need_full_description":
        gap = "Need full description: the card alone is not enough to judge fit."
    elif state == "location_not_eligible":
        gap = f"Location: {jobrules.LOCATION_LABEL.get(j['location_class'] or 'unknown')}."
    found_on = [r["source"] for r in db.all("SELECT DISTINCT source FROM job_sources WHERE job_id = ?", (job_id,))]
    order = {"potential match": 0, "weak match": 1, "unknown": 2}
    rank = (0 if eligible else 9) + (order.get(o["match"], 3) if o else 3) + (2 if state == "need_full_description" else 0)
    decision = {"Interested": "shortlisted", "Investigate": "shortlisted", "Applied": "applied", "Not relevant": "dismissed", "Archived": "dismissed"}.get(j["status"])
    return {"id": j["id"], "title": j["title"], "company": j["employer"], "location": j["location_raw"],
            "location_label": jobrules.LOCATION_LABEL.get(j["location_class"] or "unknown"), "eligible": eligible,
            "families": [jobrules.FAMILY_LABEL.get(f, f) for f in fams], "state": state, "match": o["match"] if o else None,
            "phrase": phrase, "background": background, "gap": gap, "decision": decision, "status": j["status"], "rank": rank,
            "original_url": j["apply_url"] or j["official_url"], "found_on": found_on,
            "on_employer_board": j["verification_state"] == "board", "manual_import": j["source"] == SOURCE}


# ---------------------------------------------------------------- metrics
def metrics(engine) -> dict:
    """Per search label, each job counted once (and once overall), using the job it resolves to."""
    db = engine.db
    rows = db.all("SELECT p.label, COALESCE(j.duplicate_of, j.id) AS jid FROM panel_items p JOIN jobs j ON j.id = p.job_id")
    by_label: dict[str, set[int]] = {}
    for r in rows:
        by_label.setdefault(r["label"], set()).add(r["jid"])
    every = set().union(*by_label.values()) if by_label else set()
    jobs = {j["id"]: j for j in db.all(f"SELECT * FROM jobs WHERE id IN ({','.join('?' * len(every)) or 'NULL'})", list(every))}
    predicted = {}
    for jid in every:
        fit = engine.latest("job_fit", "job", jid)
        predicted[jid] = fit["output"]["match"] if fit and not fit["outdated"] else None

    def block(ids: set[int]) -> dict:
        js = [jobs[i] for i in ids if i in jobs]
        eligible = [j for j in js if j["location_class"] in ELIGIBLE]
        assessable = [j for j in eligible if enough_evidence(j)]
        shortlisted = [j for j in js if j["status"] in ("Interested", "Investigate", "Applied")]
        applied = [j for j in js if j["status"] == "Applied"]
        model_yes = [j for j in assessable if predicted.get(j["id"]) == "potential match"]
        return {"reviewed": len(js), "eligible": len(eligible), "assessable": len(assessable), "shortlisted": len(shortlisted),
                "applied": len(applied), "model_potential": len(model_yes), "small_sample": len(js) < 10}
    labels = [{"label": k, **block(v)} for k, v in sorted(by_label.items(), key=lambda kv: -len(kv[1]))]
    return {"labels": labels, "overall": block(every),
            "note": "These describe only the jobs you pasted, not the search itself. Under 10 reviewed jobs is too few to compare searches."}


# ---------------------------------------------------------------- routes
def register(app: FastAPI, engine) -> None:
    db = engine.db

    def job_or_404(jid: int) -> dict:
        j = db.one("SELECT * FROM jobs WHERE id = ?", (jid,))
        if not j:
            raise HTTPException(404, "Job not found")
        return j

    @app.get("/api/panel/ping")
    def ping():
        return {"ok": True, "model": engine.model_state.get("ready", False)}

    @app.post("/api/panel/parse")
    def panel_parse(body: ParseBody):
        if len(body.text) > 200_000:
            raise HTTPException(413, "That paste is too long. Paste fewer listings at a time.")
        return parse(body.text)

    @app.post("/api/panel/import")
    def panel_import(body: ImportBody):
        label = re.sub(r"\s+", " ", body.label).strip()[:80]
        if not label:
            raise HTTPException(400, "Name the search you used, e.g. Founder's Office Bengaluru.")
        if not body.listings or len(body.listings) > 50:
            raise HTTPException(400, "Import between 1 and 50 listings at a time.")
        bid = db.insert("panel_batches", {"label": label, "created_at": now_iso(), "pasted": len(body.listings)})
        ids = []
        for it in body.listings:
            d = it.model_dump()
            if not d["title"].strip() or not d["company"].strip():
                raise HTTPException(400, "Every listing needs a title and a company.")
            if d["url"] and not d["url"].startswith(("https://", "http://")):
                d["url"] = ""
            jid = save(engine, d, label, bid)
            assess(engine, jid)
            ids.append(jid)
        engine.check_model()
        res = sorted((result(engine, i) for i in dict.fromkeys(ids)), key=lambda r: r["rank"])
        return {"batch": bid, "results": res}

    @app.get("/api/panel/results")
    def panel_results(ids: str = ""):
        wanted = [int(x) for x in ids.split(",") if x.strip().isdigit()][:100]
        return {"results": sorted((result(engine, i) for i in wanted if db.scalar("SELECT 1 FROM jobs WHERE id = ?", (i,))), key=lambda r: r["rank"])}

    @app.post("/api/panel/jobs/{jid}/decision")
    def panel_decision(jid: int, body: DecisionBody):
        job_or_404(jid)
        status = {"shortlist": "Interested", "dismiss": "Not relevant", "clear": "New", "applied": "Applied"}.get(body.decision)
        if not status:
            raise HTTPException(400, "Unknown decision")
        db.update("jobs", jid, {"status": status})
        return result(engine, jid)

    @app.post("/api/panel/jobs/{jid}/description")
    def panel_description(jid: int, body: DescriptionBody):
        j = job_or_404(jid)
        if j["source"] != SOURCE:
            raise HTTPException(400, "This job comes from the employer's own board; its description there is kept.")
        text = body.description.strip()
        if len(text) < 50 or len(text) > 100_000:
            raise HTTPException(400, "Paste the full job description.")
        p = {"ext_id": j["ext_id"], "title": j["title"], "location": j["location_raw"], "workplace": None, "description_text": text,
             "official_url": j["official_url"], "apply_url": j["apply_url"], "published_at": None, "salary_extra": None}
        collect.upsert_job(db, p, company_id=j["company_id"], employer=j["employer"], source=SOURCE, prefs=engine.profiles.prefs(), now=now_iso())
        row = db.one("SELECT bucket FROM jobs WHERE id = ?", (jid,))
        upd = {"verification_state": "unverified", "last_verified_at": None}
        if row["bucket"] == "candidate":
            upd.update(bucket="review", bucket_reason="Manual import; not yet confirmed on the employer's own job board")
        db.update("jobs", jid, upd)
        assess(engine, jid)
        return result(engine, jid)

    @app.get("/api/panel/labels")
    def panel_labels():
        return {"labels": [r["label"] for r in db.all("SELECT label, MAX(id) m FROM panel_batches GROUP BY label ORDER BY m DESC LIMIT 12")]}

    @app.get("/api/panel/metrics")
    def panel_metrics():
        return metrics(engine)
