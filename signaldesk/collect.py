"""Collection without the model: job boards, feeds and manually supplied items.

Rules that keep the record honest:
* A failed fetch changes nothing about that employer's jobs; it is recorded as a source error.
* A board that suddenly returns no jobs while we hold several open ones is treated as suspect:
  nothing is closed and a warning is shown.
* Jobs missing from a successful fetch are marked "no longer listed", never deleted.
* Edits are detected by content hash; the previous version is kept.
"""
from __future__ import annotations

import csv
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor

from . import jobrules
from .db import DB, now_iso
from .netsafe import FetchError, Fetcher
from .sources import ats, feeds
from .text import canonical_url, has_injection, norm, sha, title_key

SUSPECT_EMPTY_MIN = 3

CASE_HINTS = re.compile(
    r"case study|how we (built|use|used|scaled|moved|migrated|reduced)|in production|we (built|deployed|launched|rolled out)|"
    r"lessons (learned|from)|post-?mortem|our customers? (use|used)|\b\d+(\.\d+)?% (faster|fewer|less|more|reduction|increase|improvement)", re.I)


def classify(p: dict, prefs: dict, families: list[str] | None = None) -> dict:
    """Rules only. `families` overrides the rule-based families (a validated model reading)."""
    loc = jobrules.classify_location(p.get("location"), p.get("workplace"), p.get("description_text"))
    salary, kind = jobrules.extract_salary(p.get("description_text"), p.get("salary_extra"))
    fams, evidence, ambiguous = jobrules.classify_roles(p["title"], p.get("description_text"))
    if families:
        fams, ambiguous = families, False
    wanted_locs = prefs.get("locations", [])
    b, reason = jobrules.bucket(p["title"], fams, loc.cls, prefs.get("role_families", []))
    if b == "candidate" and loc.cls not in wanted_locs:
        b, reason = "review", f"Check: {jobrules.LOCATION_LABEL[loc.cls]} is not in your location preferences"
    return {"location_class": loc.cls, "location_evidence": loc.evidence[:400], "salary_text": salary, "salary_kind": kind,
            "role_family": fams[0], "role_families": json.dumps(fams), "role_evidence": json.dumps(evidence),
            "role_source": "model" if families else ("rules_uncertain" if ambiguous else "rules"),
            "bucket": b, "bucket_reason": reason,
            "injection_flag": int(has_injection(p.get("description_text")) or has_injection(p["title"]))}


def note_source(db: DB, job_id: int, source: str, url: str | None, now: str) -> None:
    """Remember every place an opening was found. One row per (source, listing URL)."""
    if not url:
        return
    key = canonical_url(url)
    row = db.one("SELECT id, job_id FROM job_sources WHERE source = ? AND url = ?", (source, key))
    if row:
        db.run("UPDATE job_sources SET last_seen_at = ?, job_id = ? WHERE id = ?", (now, job_id, row["id"]))
    else:
        db.insert("job_sources", {"job_id": job_id, "source": source, "url": key, "first_seen_at": now, "last_seen_at": now})


def job_hash(p: dict) -> str:
    return sha(p["title"], p.get("location") or "", p.get("workplace") or "", p.get("description_text") or "", p.get("salary_extra") or "")


def upsert_job(db: DB, p: dict, *, company_id: int | None, employer: str, source: str, prefs: dict, now: str) -> str:
    h = job_hash(p)
    row = db.one("SELECT * FROM jobs WHERE source = ? AND ext_id = ?", (source, p["ext_id"]))
    fields = {
        "title": p["title"], "location_raw": p.get("location"), "workplace_raw": p.get("workplace"),
        "description_text": p.get("description_text"), "content_hash": h, "official_url": p.get("official_url"),
        "apply_url": p.get("apply_url"), "published_at": p.get("published_at"), **classify(p, prefs),
    }
    if row is None:
        job_id = db.insert("jobs", {**fields, "company_id": company_id, "employer": employer, "source": source, "ext_id": p["ext_id"],
                                    "first_seen_at": now, "last_seen_at": now, "last_verified_at": now, "change_state": "new",
                                    "listing_state": "open"})
        note_source(db, job_id, source, p.get("official_url"), now)
        return "new"
    note_source(db, row["id"], source, p.get("official_url"), now)
    if row.get("role_source") == "model" and row["content_hash"] == h:
        # A validated model reading of this exact text stays until the text changes.
        for k in ("role_family", "role_families", "role_evidence", "role_source"):
            fields.pop(k, None)
        fams = json.loads(row["role_families"] or "[]")
        if fams:
            fields.update({k: v for k, v in classify(p, prefs, fams).items() if k in ("bucket", "bucket_reason")})
    reopened = row["listing_state"] != "open"
    if row["content_hash"] != h or reopened:
        if row["content_hash"] != h:
            db.insert("job_versions", {"job_id": row["id"], "content_hash": row["content_hash"], "title": row["title"],
                                       "location_raw": row["location_raw"], "salary_text": row["salary_text"],
                                       "description_text": row["description_text"], "seen_at": row["last_seen_at"]})
        db.update("jobs", row["id"], {**fields, "last_seen_at": now, "last_verified_at": now, "change_state": "changed",
                                      "changed_at": now, "listing_state": "open", "closed_at": None})
        return "changed"
    db.update("jobs", row["id"], {"last_seen_at": now, "last_verified_at": now, "change_state": "unchanged",
                                  # Preferences and rules may have changed since; the rules are cheap to re-run.
                                  **{k: v for k, v in fields.items() if k in ("bucket", "bucket_reason", "location_class", "location_evidence",
                                                                              "role_family", "role_families", "role_evidence", "role_source")}})
    return "unchanged"


def mark_duplicates(db: DB, company_id: int) -> int:
    """Hide word-for-word reposts only. Two requisitions with the same title and location but any
    difference in their text are kept as separate openings."""
    rows = db.all("SELECT id, title, location_raw, content_hash FROM jobs WHERE company_id = ? AND listing_state = 'open' "
                  "AND verification_state = 'board' ORDER BY id", (company_id,))
    seen: dict[tuple, int] = {}
    marked = 0
    for r in rows:
        key = (title_key(r["title"]), title_key(r["location_raw"] or ""), r["content_hash"])
        first = seen.setdefault(key, r["id"])
        dup = first if first != r["id"] else None
        db.run("UPDATE jobs SET duplicate_of = ? WHERE id = ?", (dup, r["id"]))
        marked += dup is not None
    return marked


def collect_company(db: DB, fetcher: Fetcher, company: dict, prefs: dict) -> dict:
    now = now_iso()
    db.update("companies", company["id"], {"last_attempt_at": now})
    stats = {"company": company["name"], "fetched": 0, "new": 0, "changed": 0, "unchanged": 0, "closed": 0}
    try:
        postings = ats.fetch_board(fetcher, company["ats"], company["ats_id"])
    except FetchError as e:
        db.update("companies", company["id"], {"last_error": str(e), "last_error_at": now})
        return {**stats, "error": str(e)}
    stats["fetched"] = len(postings)
    # Only this board's own records can be closed by it; listings found elsewhere are never closed here.
    open_ids = {r["ext_id"]: r["id"] for r in db.all(
        "SELECT id, ext_id FROM jobs WHERE company_id = ? AND source = ? AND listing_state = 'open' AND verification_state = 'board'",
        (company["id"], company["ats"]))}
    if not postings and len(open_ids) >= SUSPECT_EMPTY_MIN:
        msg = f"The board returned no jobs while {len(open_ids)} were open last time. Nothing was closed; check the careers page."
        db.update("companies", company["id"], {"last_warning": msg, "last_error": None})
        return {**stats, "warning": msg}
    with db.batch():
        for p in postings:
            stats[upsert_job(db, p, company_id=company["id"], employer=company["name"], source=company["ats"], prefs=prefs, now=now)] += 1
        seen = {p["ext_id"] for p in postings}
        for ext_id, job_id in open_ids.items():
            if ext_id not in seen:
                db.update("jobs", job_id, {"listing_state": "no_longer_listed", "closed_at": now})
                stats["closed"] += 1
        stats["duplicates"] = mark_duplicates(db, company["id"])
    db.update("companies", company["id"], {"last_success_at": now, "last_error": None, "last_warning": None})
    return stats


def collect_jobs(db: DB, fetcher: Fetcher, prefs: dict, company_ids: list[int] | None = None, cancelled=lambda: False) -> list[dict]:
    rows = db.all("SELECT * FROM companies WHERE enabled = 1 AND ats != 'manual' ORDER BY name")
    if company_ids is not None:
        rows = [r for r in rows if r["id"] in company_ids]
    with ThreadPoolExecutor(max(1, fetcher.cfg.concurrency)) as ex:
        return list(ex.map(lambda c: {"company": c["name"], "skipped": "cancelled"} if cancelled() else collect_company(db, fetcher, c, prefs), rows))


# ---------------------------------------------------------------- reading
def upsert_article(db: DB, item: dict, *, source: dict | None, now: str, origin: str = "feed") -> str:
    url = canonical_url(item["url"])
    text = item.get("content_text") or ""
    h = sha(item["title"], text)
    row = db.one("SELECT * FROM articles WHERE url = ?", (url,))
    case = int(item.get("content_basis") != "metadata" and bool(CASE_HINTS.search(f"{item['title']}\n{text}")))
    if row:
        rank = {"metadata": 0, "excerpt": 1, "full": 2}
        if row["content_hash"] != h and rank[item["content_basis"]] >= rank[row["content_basis"]]:
            db.update("articles", row["id"], {"content_text": text, "content_hash": h, "content_basis": item["content_basis"],
                                              "retrieved_at": now, "title": item["title"], "case_candidate": max(case, row["case_candidate"]),
                                              "injection_flag": int(has_injection(text))})
            return "changed"
        return "unchanged"
    key = title_key(item["title"])
    dup = db.scalar("SELECT id FROM articles WHERE dedupe_key = ? AND duplicate_of IS NULL ORDER BY id LIMIT 1", (key,))
    db.insert("articles", {
        "source_id": source["id"] if source else None, "source_name": source["name"] if source else item.get("source_name"),
        "source_kind": source["kind"] if source else item.get("source_kind", "manual"), "guid": item.get("guid"), "url": url,
        "title": item["title"][:500], "author": item.get("author"), "published_at": item.get("published_at"), "retrieved_at": now,
        "content_text": text, "content_basis": item["content_basis"], "content_hash": h, "dedupe_key": key, "duplicate_of": dup,
        "injection_flag": int(has_injection(text)), "case_candidate": case, "origin": origin,
    })
    return "duplicate" if dup else "new"


def collect_source(db: DB, fetcher: Fetcher, source: dict, limit: int) -> dict:
    now = now_iso()
    db.update("reading_sources", source["id"], {"last_attempt_at": now})
    stats = {"source": source["name"], "fetched": 0, "new": 0, "changed": 0, "unchanged": 0, "duplicate": 0}
    try:
        items = feeds.fetch_feed(fetcher, source["feed_url"], limit)
    except FetchError as e:
        db.update("reading_sources", source["id"], {"last_error": str(e), "last_error_at": now})
        return {**stats, "error": str(e)}
    stats["fetched"] = len(items)
    with db.batch():
        for it in items:
            stats[upsert_article(db, it, source=source, now=now)] += 1
    db.update("reading_sources", source["id"], {"last_success_at": now, "last_error": None})
    return stats


def collect_reading(db: DB, fetcher: Fetcher, limit: int, cancelled=lambda: False) -> list[dict]:
    rows = db.all("SELECT * FROM reading_sources WHERE enabled = 1 ORDER BY name")
    with ThreadPoolExecutor(max(1, fetcher.cfg.concurrency)) as ex:
        return list(ex.map(lambda s: {"source": s["name"], "skipped": "cancelled"} if cancelled() else collect_source(db, fetcher, s, limit), rows))


# ---------------------------------------------------------------- what an imported URL may cause us to fetch
# Opening a link in your browser and asking SignalDesk to fetch it are separate. A pasted URL is
# untrusted: SignalDesk fetches it only when it is an employer ATS job page or a careers site you
# already track. Aggregators and LinkedIn are never fetched; their links are kept as the source.
ATS_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com")
NEVER_FETCH = re.compile(r"(^|\.)(linkedin\.com|lnkd\.in|wellfound\.com|angel\.co|naukri\.com|indeed\.[a-z.]+|glassdoor\.[a-z.]+|instahyre\.com|"
                         r"iimjobs\.com|foundit\.in|monster\.[a-z.]+|google\.[a-z.]+)$", re.I)
MANUAL_SOURCES = ("manual", "manual_import", "wellfound")   # pasted by you; kept local unless you enable sync


def fetch_refusal(db: DB, url: str) -> str | None:
    """None when SignalDesk may fetch this imported URL, else the reason it will not."""
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not host:
        return "That is not a web address."
    if NEVER_FETCH.search(host):
        return "SignalDesk does not fetch pages from this site. Paste the job description; the link is kept as the source."
    if host in ATS_HOSTS:
        return None
    known = {(urlparse(r["careers_url"] or "").hostname or "").lower().removeprefix("www.") for r in db.all("SELECT careers_url FROM companies")}
    known |= {(r["domain"] or "").lower().removeprefix("www.") for r in db.all("SELECT domain FROM startups WHERE domain IS NOT NULL")}
    known.discard("")
    if any(host == d or host.endswith("." + d) for d in known):
        return None
    return ("SignalDesk only fetches employer job boards and careers sites you already track. Paste the description; "
            "the link is kept as the source. To track this employer, add it under Sources.")


# ---------------------------------------------------------------- manual imports
def import_job(db: DB, fetcher: Fetcher | None, prefs: dict, *, url: str, text: str = "", employer: str = "", title: str = "",
               location: str = "", apply_url: str = "") -> dict:
    """Add a job from a URL plus pasted text. The URL is the original listing; if no text is given the
    page is fetched (robots.txt respected) and schema.org JobPosting data is used when present."""
    url = url.strip()
    if not url:
        raise ValueError("The original job URL is required.")
    existing = db.one("SELECT id FROM jobs WHERE official_url = ? OR apply_url = ?", (url, url))
    if existing:
        return {"id": existing["id"], "result": "already saved"}
    published = None
    if not text.strip():
        if fetcher is None:
            raise ValueError("Paste the job description: fetching is unavailable.")
        refusal = fetch_refusal(db, url)
        if refusal:
            raise ValueError(refusal)
        page = feeds.fetch_page(fetcher, url)
        jp = page.get("job_posting") or {}
        text = feeds.html_to_text(jp.get("description")) if jp.get("description") else page["text"]
        title = title or jp.get("title") or page["title"]
        org = jp.get("hiringOrganization") or {}
        employer = employer or (org.get("name") if isinstance(org, dict) else "") or ""
        loc = jp.get("jobLocation")
        if not location and loc:
            locs = loc if isinstance(loc, list) else [loc]
            location = ", ".join(filter(None, ((l.get("address") or {}).get("addressLocality") for l in locs if isinstance(l, dict))))
        if jp.get("jobLocationType") == "TELECOMMUTE":
            location = f"{location} (Remote)".strip()
        published = jp.get("datePosted")
    if not title.strip():
        raise ValueError("Add the job title.")
    p = {"ext_id": "manual:" + sha(url)[:16], "title": title.strip(), "location": location.strip() or None, "workplace": None,
         "description_text": text.strip(), "official_url": url, "apply_url": apply_url.strip() or url, "published_at": published,
         "salary_extra": None}
    upsert_job(db, p, company_id=None, employer=employer.strip() or "Unknown employer", source="manual", prefs=prefs, now=now_iso())
    return {"id": db.scalar("SELECT id FROM jobs WHERE source = 'manual' AND ext_id = ?", (p["ext_id"],)), "result": "added"}


# ---------------------------------------------------------------- discovery listings (Wellfound, YC, investor boards)
def _listing_from_dict(d: dict) -> dict:
    def g(*keys):
        for k in keys:
            for kk in (k, k.title(), k.upper()):
                if d.get(kk):
                    return str(d[kk]).strip()
        return ""
    return {"url": g("url", "link", "listing_url", "job_url"), "title": g("title", "role", "job_title", "position"),
            "employer": g("company", "employer", "company_name", "startup"), "location": g("location", "locations"),
            "apply_url": g("apply_url", "application_url", "employer_url", "external_url"),
            "company_url": g("company_url", "website", "company_website", "domain"),
            "description": g("description", "details", "summary"), "salary": g("salary", "compensation", "pay")}


def parse_listing_import(text: str) -> list[dict]:
    """Saved listing URLs (one per line), a CSV export with a header row, or a JSON list of objects."""
    text = (text or "").strip()
    if not text:
        return []
    if text[0] in "[{":
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("jobs") or data.get("results") or data.get("listings") or [data]
        items = [_listing_from_dict(d) for d in data if isinstance(d, dict)]
    elif re.search(r"(^|,)\s*\"?(url|link|listing_url|job_url)\"?\s*(,|$)", text.splitlines()[0], re.I):
        items = [_listing_from_dict(r) for r in csv.DictReader(io.StringIO(text))]
    else:
        items = [{"url": u.rstrip(").,;'\"")} for u in re.findall(r"https?://[^\s<>\"]+", text)]
    return [i for i in items if i.get("url", "").startswith(("http://", "https://"))]


def _open_board_jobs(db: DB) -> list[dict]:
    return db.all("SELECT id, employer, title, location_raw, location_class, official_url, apply_url, status FROM jobs "
                  "WHERE listing_state = 'open' AND duplicate_of IS NULL AND verification_state = 'board'")


def _match_board_job(db: DB, item: dict) -> tuple[int | None, int]:
    """Find the employer/ATS record for a discovered listing. Returns (job id, candidates seen).
    An application URL decides it; otherwise employer + exact title, narrowed by location.
    Several same-title requisitions with nothing to tell them apart are never merged."""
    jobs = _open_board_jobs(db)
    for u in (item.get("apply_url"), item.get("url")):
        if u:
            key = canonical_url(u)
            hit = [j for j in jobs if key in (canonical_url(j["official_url"] or ""), canonical_url(j["apply_url"] or ""))]
            if len(hit) == 1:
                return hit[0]["id"], 1
    if not (item.get("title") and item.get("employer")):
        return None, 0
    cands = [j for j in jobs if norm(j["employer"]) == norm(item["employer"]) and title_key(j["title"]) == title_key(item["title"])]
    if len(cands) > 1 and item.get("location"):
        cls = jobrules.classify_location(item["location"]).cls
        cands = [j for j in cands if j["location_class"] == cls] or cands
    return (cands[0]["id"], 1) if len(cands) == 1 else (None, len(cands))


def attach_listing(db: DB, item: dict, *, source: str, prefs: dict, now: str) -> str:
    """Record one discovered listing. Returns already | merged | ambiguous | unverified | needs_details."""
    url = canonical_url(item["url"])
    known = db.one("SELECT job_id FROM job_sources WHERE source = ? AND url = ?", (source, url))
    if known:
        db.run("UPDATE job_sources SET last_seen_at = ? WHERE source = ? AND url = ?", (now, source, url))
        return "already"
    target, seen = _match_board_job(db, item)
    if target:
        note_source(db, target, source, url, now)
        return "merged"
    if not (item.get("title") and item.get("employer")):
        return "needs_details"
    p = {"ext_id": f"{source}:{sha(url)[:16]}", "title": item["title"][:300], "location": item.get("location") or None, "workplace": None,
         "description_text": item.get("description") or "", "official_url": url, "apply_url": item.get("apply_url") or url,
         "published_at": None, "salary_extra": item.get("salary") or None}
    company = db.one("SELECT id FROM companies WHERE lower(name) = lower(?)", (item["employer"],))
    upsert_job(db, p, company_id=None, employer=item["employer"][:200], source=source, prefs=prefs, now=now)
    job = db.one("SELECT id, bucket FROM jobs WHERE source = ? AND ext_id = ?", (source, p["ext_id"]))
    reason = (f"Found on {source}; {seen} employer listings share this title, so it was not merged. Check which one it is."
              if seen > 1 else f"Found on {source}; not yet confirmed on the employer's own job board")
    db.update("jobs", job["id"], {"verification_state": "unverified", "company_id": company["id"] if company else None, "last_verified_at": None,
                                  **({"bucket": "review", "bucket_reason": reason} if job["bucket"] == "candidate" else {})})
    return "ambiguous" if seen > 1 else "unverified"


def verify_unverified(db: DB) -> int:
    """After boards are collected, fold discovered listings into the employer's record when they
    match it unambiguously. Your status on either record is kept."""
    merged = 0
    for u in db.all("SELECT * FROM jobs WHERE verification_state = 'unverified' AND duplicate_of IS NULL"):
        target, _seen = _match_board_job(db, {"apply_url": u["apply_url"], "url": None, "title": u["title"],
                                              "employer": u["employer"], "location": u["location_raw"]})
        if not target:
            continue
        with db.batch():
            db.run("UPDATE job_sources SET job_id = ? WHERE job_id = ?", (target, u["id"]))
            tgt = db.one("SELECT status FROM jobs WHERE id = ?", (target,))
            if tgt["status"] == "New" and u["status"] != "New":
                db.update("jobs", target, {"status": u["status"]})
            db.update("jobs", u["id"], {"duplicate_of": target})
        merged += 1
    return merged


def import_listings(db: DB, prefs: dict, *, source: str, text: str) -> dict:
    now = now_iso()
    counts: dict[str, int] = {}
    items = parse_listing_import(text)
    with db.batch():
        for it in items:
            r = attach_listing(db, it, source=source, prefs=prefs, now=now)
            counts[r] = counts.get(r, 0) + 1
    return {"read": len(items), **counts}


def add_board(db: DB, *, name: str, ats: str, ats_id: str, careers_url: str, origin: str, tie: str, verification: str) -> int:
    """Add (or find) an employer board found by a discovery source. Boards found on the employer's
    own careers page are tied to it; boards linked from an investor or YC page say so."""
    row = db.one("SELECT id FROM companies WHERE ats = ? AND lower(ats_id) = lower(?)", (ats, ats_id))
    if row:
        return row["id"]
    return db.insert("companies", {"name": name[:200], "careers_url": careers_url, "ats": ats, "ats_id": ats_id, "enabled": 1,
                                   "verification": verification[:400], "origin": origin, "tie": tie, "created_at": now_iso()})


def import_article(db: DB, fetcher: Fetcher, url: str) -> dict:
    page = feeds.fetch_page(fetcher, url)
    text = page["text"]
    basis = "excerpt" if page["paywall_hint"] else feeds.content_basis(text)
    from urllib.parse import urlparse
    item = {"url": page["final_url"], "title": page["title"], "author": page["author"], "published_at": page["published_at"],
            "content_text": text, "content_basis": basis, "source_name": urlparse(page["final_url"]).hostname, "source_kind": "manual"}
    result = upsert_article(db, item, source=None, now=now_iso(), origin="manual")
    row = db.one("SELECT id FROM articles WHERE url = ?", (canonical_url(page["final_url"]),))
    db.run("UPDATE articles SET case_candidate = 1 WHERE id = ?", (row["id"],))
    return {"id": row["id"], "result": result}
