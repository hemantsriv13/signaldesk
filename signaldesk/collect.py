"""Collection without the model: job boards, feeds and manually supplied items.

Rules that keep the record honest:
* A failed fetch changes nothing about that employer's jobs; it is recorded as a source error.
* A board that suddenly returns no jobs while we hold several open ones is treated as suspect:
  nothing is closed and a warning is shown.
* Jobs missing from a successful fetch are marked "no longer listed", never deleted.
* Edits are detected by content hash; the previous version is kept.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from . import jobrules
from .db import DB, now_iso
from .netsafe import FetchError, Fetcher
from .sources import ats, feeds
from .text import canonical_url, has_injection, sha, title_key

SUSPECT_EMPTY_MIN = 3

CASE_HINTS = re.compile(
    r"case study|how we (built|use|used|scaled|moved|migrated|reduced)|in production|we (built|deployed|launched|rolled out)|"
    r"lessons (learned|from)|post-?mortem|our customers? (use|used)|\b\d+(\.\d+)?% (faster|fewer|less|more|reduction|increase|improvement)", re.I)


def classify(p: dict, prefs: dict) -> dict:
    loc = jobrules.classify_location(p.get("location"), p.get("workplace"), p.get("description_text"))
    salary, kind = jobrules.extract_salary(p.get("description_text"), p.get("salary_extra"))
    family = jobrules.role_family(p["title"])
    wanted_locs = prefs.get("locations", [])
    b, reason = jobrules.bucket(p["title"], family, loc.cls, prefs.get("role_families", []))
    if b == "candidate" and loc.cls not in wanted_locs:
        b, reason = "review", f"Check: {jobrules.LOCATION_LABEL[loc.cls]} is not in your location preferences"
    return {"location_class": loc.cls, "location_evidence": loc.evidence[:400], "salary_text": salary, "salary_kind": kind,
            "role_family": family, "bucket": b, "bucket_reason": reason,
            "injection_flag": int(has_injection(p.get("description_text")) or has_injection(p["title"]))}


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
        db.insert("jobs", {**fields, "company_id": company_id, "employer": employer, "source": source, "ext_id": p["ext_id"],
                           "first_seen_at": now, "last_seen_at": now, "last_verified_at": now, "change_state": "new",
                           "listing_state": "open"})
        return "new"
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
                                  # Preferences may have changed since; the rules are cheap to re-run.
                                  **{k: v for k, v in fields.items() if k in ("bucket", "bucket_reason", "location_class", "location_evidence")}})
    return "unchanged"


def mark_duplicates(db: DB, company_id: int) -> int:
    rows = db.all("SELECT id, title, location_raw FROM jobs WHERE company_id = ? AND listing_state = 'open' ORDER BY id", (company_id,))
    seen: dict[tuple, int] = {}
    marked = 0
    for r in rows:
        key = (title_key(r["title"]), title_key(r["location_raw"] or ""))
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
    open_ids = {r["ext_id"]: r["id"] for r in db.all(
        "SELECT id, ext_id FROM jobs WHERE company_id = ? AND listing_state = 'open'", (company["id"],))}
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
