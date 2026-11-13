"""Funding-to-careers agent: recently funded India-linked startups and their openings.

Pipeline, all deterministic except one optional model step:
  1. Read configured announcement pages/feeds and portfolio pages (registry.py).
  2. Keep each announcement once; parse company, round, amount and date from its own text.
     Announcements whose company cannot be read by rule go to the local model (validated).
  3. Resolve the company's official domain only from a link the announcement or portfolio
     page gives; never from a guess.
  4. Find the careers page / ATS board on that domain and add it to the jobs pipeline.

Dates: only the announcement's publication date is a funding date. A YC batch, a page's
"updated" date or the day SignalDesk found a company never is. Undated companies go to the
watchlist, separate from funded companies.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from urllib.parse import urlsplit

from . import collect, registry
from .db import DB, now_iso
from .discovery import discover
from .netsafe import FetchError, Fetcher
from .sources import web
from .text import find_quote, norm

WINDOWS = (30, 90, 180)
DEFAULT_WINDOW = 180
SAME_ROUND_DAYS = 45
MAX_ARTICLES_PER_SOURCE = 12
MAX_CAREERS_CHECKS = 8
RECHECK_DAYS = 7

FUNDING_HINT = re.compile(r"\b(raises?|raised|funding|series [a-h]\b|pre-?seed|seed round|seed funding|investment in|invests? in|"
                          r"leads? .{0,40}round|secures?|bags?|backs?|backed|led by|round)\b", re.I)
ROUND = re.compile(r"\b(pre-?seed|seed|angel|pre-series [a-h]|series [a-h]\d?|bridge|growth|venture debt|debt)\b", re.I)
AMOUNT = re.compile(r"((?:US\$|\$|₹|Rs\.?\s?|INR\s?|USD\s?)\s?\d[\d,.]*\s?(?:million|mn|m|billion|bn|crores?|cr|lakhs?|k)?\b"
                    r"|\b\d[\d,.]*\s?(?:million|crores?|billion)\s?(?:dollars|rupees|usd|inr)?)", re.I)
NAME = r"([A-Z][\w.&'’-]*(?:\s+(?:[A-Z][\w.&'’-]*|AI|ai|Labs|Health|Tech|Pay|Bank)){0,3})"
TITLE_PATTERNS = [
    re.compile(rf"^{NAME}\s+(?:has\s+)?(?:raises?|raised|secures?|secured|bags?|closes?|closed|lands?|gets?|nets?|announces?)\b"),
    re.compile(rf"\b(?:investment|invests?|investing|leads?|led|backs?|backing|participates?)\b[^.]{{0,60}}?\bin\s+{NAME}"),
    re.compile(rf"\b(?:welcom(?:e|es|ing)|partnering with|backing|announcing)\s+{NAME}"),
]
PREFIX = re.compile(r"^(?:(?:[\w-]+-based|Indian|Startup|Fintech|Edtech|Healthtech|SaaS|D2C|B2B|Deeptech|Agritech|Logistics|AI|Exclusive:?)\s+)+")
CITIES = r"bengaluru|bangalore|mumbai|delhi|new delhi|gurugram|gurgaon|noida|hyderabad|pune|chennai|kolkata|ahmedabad|jaipur|kochi"
INDIA_BASED = re.compile(rf"\b((?:{CITIES})-based|based (?:in|out of) (?:{CITIES}|india)|headquartered in (?:{CITIES}|india)|"
                         rf"indian (?:startup|company|firm)|india-based|india-headquartered)\b", re.I)


# ---------------------------------------------------------------- extraction
def normalise_round(text: str | None) -> str:
    if not text:
        return "unknown"
    t = text.lower().replace("-", " ")
    m = re.search(r"pre series ([a-h])", t) or re.search(r"series ([a-h])", t)
    if m:
        return ("pre_series_" if t.startswith("pre") else "series_") + m.group(1)
    for k in ("pre seed", "seed", "angel", "bridge", "growth", "venture debt", "debt"):
        if k in t:
            return k.replace(" ", "_")
    return "unknown"


def company_from_title(title: str) -> str | None:
    for pat in TITLE_PATTERNS:
        m = pat.search(title or "")
        if m:
            name = PREFIX.sub("", m.group(1)).strip(" ,.:'’")
            if 2 <= len(name) <= 60 and not re.fullmatch(r"(?i)the|our|a|an|we|it|this", name):
                return name
    return None


def extract_round(title: str, text: str = "") -> dict:
    """Rule-based reading of one announcement. `company` is None when the rules cannot tell."""
    blob = f"{title}\n{text}"
    is_funding = bool(FUNDING_HINT.search(blob)) and bool(ROUND.search(blob) or AMOUNT.search(blob) or re.search(r"\b(raises?|raised|funding)\b", blob, re.I))
    company = company_from_title(title) if is_funding else None
    r = ROUND.search(blob)
    a = AMOUNT.search(title) or AMOUNT.search(text)
    india = None
    for sent in re.split(r"(?<=[.!?])\s+|\n+", blob):
        if INDIA_BASED.search(sent):
            india = sent.strip()[:300]
            break
    return {"is_funding": is_funding, "company": company, "round": normalise_round(r.group(0) if r else None),
            "amount": a.group(0).strip() if a else None, "india_evidence": india}


def domain_for(company: str, links: list[dict]) -> str | None:
    """The company's site, only when the page links to it: link text names the company, or the host
    is the company name. Never inferred from the name alone."""
    key = norm(company).replace(" ", "")
    first = norm(company).split(" ")[0] if company else ""
    for l in links:
        host = l["host"]
        label = host.split(".")[0]
        if norm(l.get("text") or "") == norm(company) or label == key or (len(first) >= 4 and label == first):
            return host
    return None


# ---------------------------------------------------------------- storage
def upsert_startup(db: DB, name: str, *, domain: str | None = None, domain_evidence: str | None = None, india: str | None = None,
                   india_url: str | None = None, watch_source: str | None = None, watch_url: str | None = None, is_demo: int = 0) -> int:
    key = norm(name)
    row = db.one("SELECT * FROM startups WHERE name_key = ?", (key,))
    if domain and not row:
        row = db.one("SELECT * FROM startups WHERE domain = ?", (domain,))
    if row is None:
        return db.insert("startups", {"name": name.strip()[:120], "name_key": key, "domain": domain, "domain_evidence": domain_evidence,
                                      "india_link": "india_based" if india else "unknown", "india_evidence": india, "india_evidence_url": india_url,
                                      "careers_status": "unchecked" if domain else "no_domain", "watch_source": watch_source,
                                      "watch_url": watch_url, "is_demo": is_demo, "created_at": now_iso()})
    upd = {}
    if domain and not row["domain"]:
        upd.update(domain=domain, domain_evidence=domain_evidence, careers_status="unchecked")
    if india and row["india_link"] != "india_based":
        upd.update(india_link="india_based", india_evidence=india, india_evidence_url=india_url)
    if watch_source and not row["watch_source"]:
        upd.update(watch_source=watch_source, watch_url=watch_url)
    db.update("startups", row["id"], upd)
    return row["id"]


def _amount_key(a: str | None) -> str:
    return re.sub(r"[^0-9a-z.]", "", (a or "").lower())


def save_event(db: DB, startup_id: int, *, investor: str | None, round_: str, amount: str | None, announced_on: str, url: str,
               title: str, source: str) -> str:
    """new | duplicate | already. Syndicated reports of one round collapse into the first record;
    a different round, or the same round label far apart in time, stays separate."""
    if db.scalar("SELECT 1 FROM funding_events WHERE announcement_url = ?", (url,)):
        return "already"
    d = date.fromisoformat(announced_on)
    for e in db.all("SELECT * FROM funding_events WHERE startup_id = ?", (startup_id,)):
        near = abs((date.fromisoformat(e["announced_on"]) - d).days) <= SAME_ROUND_DAYS
        same = (round_ != "unknown" and e["round"] == round_) or (amount and _amount_key(e["amount_text"]) == _amount_key(amount))
        if near and same:
            others = json.loads(e["other_reports_json"])
            if url not in others:
                others.append(url)
            db.update("funding_events", e["id"], {"other_reports_json": json.dumps(others),
                                                  "investor": e["investor"] or investor, "amount_text": e["amount_text"] or amount})
            return "duplicate"
    db.insert("funding_events", {"startup_id": startup_id, "investor": investor, "round": round_, "amount_text": amount,
                                 "announced_on": announced_on, "announcement_url": url, "title": (title or "")[:300], "source": source,
                                 "first_seen_at": now_iso()})
    return "new"


def apply_reading(db: DB, ann: dict, reading: dict, *, investor: str | None, links: list[dict] | None = None) -> str:
    """Store one announcement's reading. Returns the announcement's new status."""
    if not reading.get("is_funding"):
        return "not_funding"
    if not reading.get("company"):
        return "needs_model"
    dom = domain_for(reading["company"], links or [])
    sid = upsert_startup(db, reading["company"], domain=dom, domain_evidence=f"Linked from {ann['url']}" if dom else None,
                         india=reading.get("india_evidence"), india_url=ann["url"] if reading.get("india_evidence") else None)
    when = ann.get("published_on") or ann.get("listed_date")
    if not when:
        db.update("startups", sid, {"watch_source": ann["source"], "watch_url": ann["url"]})
        return "undated"
    save_event(db, sid, investor=investor, round_=reading.get("round") or "unknown", amount=reading.get("amount"), announced_on=when,
               url=ann["url"], title=ann.get("title") or "", source=ann["source"])
    return "parsed"


# ---------------------------------------------------------------- collection
def collect_announcements(db: DB, fetcher: Fetcher, src: dict, enqueue=None) -> dict:
    """List new announcements, then process pending ones. A failure part-way keeps everything
    processed so far and leaves the rest pending for the next sweep: nothing is skipped."""
    counts = {"listed": 0, "new": 0, "processed": 0, "funding": 0, "duplicates": 0, "to_model": 0, "failed": 0}
    items = web.announcements(fetcher, src["url"])           # FetchError propagates: nothing changes
    counts["listed"] = len(items)
    now = now_iso()
    for it in items:
        if not db.scalar("SELECT 1 FROM announcements WHERE url = ?", (it["url"],)):
            db.insert("announcements", {"source": src["key"], "url": it["url"], "title": it["title"], "listed_date": it.get("date"),
                                        "text": it.get("text") or None, "first_seen_at": now})
            counts["new"] += 1
    pending = db.all("SELECT * FROM announcements WHERE source = ? AND status = 'pending' ORDER BY id LIMIT ?", (src["key"], MAX_ARTICLES_PER_SOURCE))
    error = None
    for ann in pending:
        if not FUNDING_HINT.search(ann["title"] or ""):
            db.update("announcements", ann["id"], {"status": "not_funding", "processed_at": now_iso()})
            counts["processed"] += 1
            continue
        try:
            page = web.article(fetcher, ann["url"]) if not ann["text"] else {"text": ann["text"], "date": None, "links": []}
        except FetchError as e:
            counts["failed"] += 1
            error = f"{ann['url']}: {e}"
            break                                           # stop here; later items stay pending for the next sweep
        ann = {**ann, "text": page["text"][:20000], "published_on": page.get("date") or ann["published_on"]}
        db.update("announcements", ann["id"], {"text": ann["text"], "published_on": ann["published_on"]})
        reading = extract_round(ann["title"], ann["text"])
        status = apply_reading(db, ann, reading, investor=src.get("investor"), links=page.get("links"))
        if status == "needs_model" and enqueue:
            enqueue(ann["id"])
            counts["to_model"] += 1
        counts["funding"] += status == "parsed"
        db.update("announcements", ann["id"], {"status": status, "processed_at": now_iso()})
        counts["processed"] += 1
    counts["pending"] = db.scalar("SELECT COUNT(*) FROM announcements WHERE source = ? AND status = 'pending'", (src["key"],))
    if error:
        counts["error"] = error
    return counts


def collect_portfolio(db: DB, fetcher: Fetcher, src: dict, limit_details: int = 15) -> dict:
    """Portfolio membership feeds the watchlist only: no funding event is created from it."""
    companies = web.portfolio(fetcher, src["url"])
    counts = {"listed": len(companies), "new": 0, "websites_found": 0, "failed": 0}
    for c in companies:
        before = db.scalar("SELECT 1 FROM startups WHERE name_key = ?", (norm(c["name"]),))
        dom = urlsplit(c["website"]).hostname if c["website"] else None
        upsert_startup(db, c["name"], domain=dom, domain_evidence=f"Linked from {src['url']}" if dom else None,
                       watch_source=src["key"], watch_url=c["detail_url"] or src["url"])
        counts["new"] += not before
    # Detail pages give the website for portfolios that link inside the site (YC). Bounded per sweep.
    for s in db.all("SELECT id, watch_url FROM startups WHERE watch_source = ? AND domain IS NULL AND watch_url LIKE 'http%' "
                    "AND (last_checked_at IS NULL OR last_checked_at < ?) ORDER BY id LIMIT ?",
                    (src["key"], (date.today() - timedelta(days=RECHECK_DAYS)).isoformat(), limit_details)):
        try:
            site = web.company_website(fetcher, s["watch_url"])
        except FetchError:
            counts["failed"] += 1
            continue
        upd = {"last_checked_at": now_iso()}
        if site:
            upd.update(domain=urlsplit(site).hostname, domain_evidence=f"Website link on {s['watch_url']}", careers_status="unchecked")
            counts["websites_found"] += 1
        db.update("startups", s["id"], upd)
    return counts


def resolve_careers(db: DB, fetcher: Fetcher, limit: int = MAX_CAREERS_CHECKS) -> dict:
    """Find each startup's careers page or ATS board on its own domain, and add the board to the
    jobs pipeline. A board found on the company's own page is tied to it."""
    counts = {"checked": 0, "boards": 0, "page_only": 0, "failed": 0}
    stale = (date.today() - timedelta(days=RECHECK_DAYS)).isoformat()
    rows = db.all("SELECT * FROM startups WHERE domain IS NOT NULL AND company_id IS NULL AND is_demo = 0 "
                  "AND (careers_checked_at IS NULL OR careers_checked_at < ?) ORDER BY id DESC LIMIT ?", (stale, limit))
    for s in rows:
        counts["checked"] += 1
        found, page_seen, errors = None, None, []
        for path in ("/careers", "/jobs", "/"):
            url = f"https://{s['domain']}{path}"
            try:
                res = discover(fetcher, url)
            except (FetchError, ValueError) as e:
                errors.append(str(e))
                continue
            page_seen = page_seen or res.get("checked_url")
            if res["boards"]:
                found = (res["boards"][0], res["checked_url"])
                break
        upd = {"careers_checked_at": now_iso(), "last_checked_at": now_iso()}
        if found:
            board, page = found
            cid = collect.add_board(db, name=s["name"], ats=board["ats"], ats_id=board["ats_id"], careers_url=page, origin="funding",
                                    tie="employer_page", verification=f"{page} on the company's own domain links this board (found {date.today()})")
            upd.update(company_id=cid, careers_url=page, careers_status="board_found", careers_note=None)
            counts["boards"] += 1
        elif page_seen:
            upd.update(careers_url=page_seen, careers_status="page_only",
                       careers_note="Careers page found, but it uses a system SignalDesk cannot read. Check it by hand or import listings.")
            counts["page_only"] += 1
        else:
            upd.update(careers_status="failed", careers_note=("; ".join(errors))[:300] or "No careers page could be reached.")
            counts["failed"] += 1
        db.update("startups", s["id"], upd)
    return counts


def update_hiring_links(db: DB) -> None:
    """A company not shown to be India-based, with open roles located in India, is "hiring in India"."""
    for s in db.all("SELECT id, company_id FROM startups WHERE india_link = 'unknown' AND company_id IS NOT NULL"):
        j = db.one("SELECT title, location_raw FROM jobs WHERE company_id = ? AND listing_state = 'open' "
                   "AND location_class IN ('bengaluru', 'remote_india', 'india_other', 'india_unspecified') LIMIT 1", (s["company_id"],))
        if j:
            db.update("startups", s["id"], {"india_link": "hiring_in_india",
                                            "india_evidence": f"Open role in India: {j['title']} ({j['location_raw']})"})


def model_reading(db: DB, ann_id: int, data: dict) -> tuple[str, list[str]]:
    """Validate the local model's reading of an announcement, then store it. The company name and
    the supporting quote must both appear in the announcement text."""
    ann = db.one("SELECT * FROM announcements WHERE id = ?", (ann_id,))
    text = f"{ann['title']}\n{ann['text'] or ''}"
    notes = []
    company = str(data.get("company") or "").strip()
    quote = str(data.get("quote") or "").strip()
    is_funding = bool(data.get("is_funding_round"))
    if is_funding and (not company or company.lower() not in text.lower()):
        notes.append("The company name the model gave is not in the announcement; nothing was stored.")
        is_funding = False
    if is_funding and not find_quote(quote, text):
        notes.append("The supporting quote was not found in the announcement; nothing was stored.")
        is_funding = False
    rule = extract_round(ann["title"], ann["text"] or "")
    reading = {"is_funding": is_funding, "company": company or None, "round": normalise_round(str(data.get("round") or "")) if is_funding else "unknown",
               "amount": rule["amount"], "india_evidence": rule["india_evidence"]}
    src = db.get_setting("source_investors") or {}
    status = apply_reading(db, ann, reading, investor=src.get(ann["source"])) if is_funding else "not_funding"
    db.update("announcements", ann_id, {"status": status, "processed_at": now_iso(), "note": "; ".join(notes) or "Read by the local model"})
    return status, notes


# ---------------------------------------------------------------- views
def openings(db: DB, company_id: int | None) -> dict:
    if not company_id:
        return {"open": 0, "matching": 0, "review": 0, "jobs": []}
    rows = db.all("SELECT id, title, location_raw, bucket, location_class FROM jobs WHERE company_id = ? AND listing_state = 'open' "
                  "AND duplicate_of IS NULL ORDER BY (bucket = 'candidate') DESC, first_seen_at DESC", (company_id,))
    return {"open": len(rows), "matching": sum(r["bucket"] == "candidate" for r in rows), "review": sum(r["bucket"] == "review" for r in rows),
            "jobs": [r for r in rows if r["bucket"] in ("candidate", "review")][:10]}


CAREERS_LABEL = {
    "board_found": "Job board found on the company's site", "page_only": "Careers page can't be read automatically",
    "failed": "Careers page could not be checked", "no_domain": "Company website not known yet", "unchecked": "Not checked yet",
    "not_found": "No careers page found",
}


def opening_state(s: dict, o: dict) -> str:
    """Tell 'no matching opening' apart from 'could not check'."""
    if s["careers_status"] != "board_found":
        return CAREERS_LABEL.get(s["careers_status"], s["careers_status"])
    if o["matching"]:
        return f"{o['matching']} matching opening(s)"
    if o["open"]:
        return f"{o['open']} open role(s), none matching yet"
    return "Board checked: no open roles"


def startups(db: DB, *, window: str = str(DEFAULT_WINDOW), india: str = "all", include_demo: bool = False) -> list[dict]:
    demo = "" if include_demo else "AND s.is_demo = 0"
    india_sql = {"based": "AND s.india_link = 'india_based'", "hiring": "AND s.india_link = 'hiring_in_india'",
                 "linked": "AND s.india_link != 'unknown'"}.get(india, "")
    if window == "watch":
        rows = db.all(f"SELECT s.* FROM startups s WHERE NOT EXISTS (SELECT 1 FROM funding_events e WHERE e.startup_id = s.id) {demo} {india_sql} "
                      "ORDER BY s.created_at DESC LIMIT 300")
        events = {}
    else:
        days = int(window) if window.isdigit() else DEFAULT_WINDOW
        since = (date.today() - timedelta(days=days)).isoformat()
        rows = db.all(f"SELECT s.*, MAX(e.announced_on) AS latest FROM startups s JOIN funding_events e ON e.startup_id = s.id "
                      f"WHERE e.announced_on >= ? {demo} {india_sql} GROUP BY s.id ORDER BY latest DESC LIMIT 300", (since,))
        events = {}
        for e in db.all(f"SELECT * FROM funding_events WHERE announced_on >= ? ORDER BY announced_on DESC", (since,)):
            events.setdefault(e["startup_id"], []).append(e)
    out = []
    for s in rows:
        o = openings(db, s["company_id"])
        evs = events.get(s["id"], [])
        out.append({**{k: s[k] for k in ("id", "name", "domain", "india_link", "india_evidence", "careers_status", "careers_url", "watch_source", "is_demo")},
                    "latest": evs[0] if evs else None, "rounds": len(evs), "openings": {k: o[k] for k in ("open", "matching", "review")},
                    "opening_state": opening_state(s, o)})
    return out


def startup_detail(db: DB, sid: int) -> dict | None:
    s = db.one("SELECT * FROM startups WHERE id = ?", (sid,))
    if not s:
        return None
    o = openings(db, s["company_id"])
    events = db.all("SELECT * FROM funding_events WHERE startup_id = ? ORDER BY announced_on DESC", (sid,))
    for e in events:
        e["other_reports"] = json.loads(e.pop("other_reports_json"))
    return {**s, "events": events, "openings": o, "opening_state": opening_state(s, o),
            "careers_label": CAREERS_LABEL.get(s["careers_status"], s["careers_status"])}


def for_job(db: DB, job: dict) -> dict | None:
    """The funding context of a job's employer, if SignalDesk knows one."""
    s = db.one("SELECT * FROM startups WHERE company_id = ?", (job["company_id"],)) if job.get("company_id") else None
    s = s or db.one("SELECT * FROM startups WHERE name_key = ?", (norm(job["employer"]),))
    if not s:
        return None
    e = db.one("SELECT * FROM funding_events WHERE startup_id = ? ORDER BY announced_on DESC LIMIT 1", (s["id"],))
    return {"startup_id": s["id"], "name": s["name"], "india_link": s["india_link"], "india_evidence": s["india_evidence"],
            "latest": e, "days_since": (date.today() - date.fromisoformat(e["announced_on"])).days if e else None}


def add_manual(db: DB, *, name: str, domain: str = "", investor: str = "", round_: str = "", amount: str = "", announced_on: str = "",
               announcement_url: str = "") -> int:
    """Add a startup by hand. A dated round needs the announcement link that states it."""
    if not name.strip():
        raise ValueError("Add the company name.")
    dom = urlsplit(domain if "://" in domain else f"https://{domain}").hostname if domain.strip() else None
    sid = upsert_startup(db, name, domain=dom, domain_evidence="Added by you" if dom else None)
    if announced_on or announcement_url:
        if not (announced_on and announcement_url.startswith("https://")):
            raise ValueError("A funding round needs both the announcement date and the https:// link that states it.")
        date.fromisoformat(announced_on)
        save_event(db, sid, investor=investor or None, round_=normalise_round(round_), amount=amount or None, announced_on=announced_on,
                   url=announcement_url, title=f"Added by you: {name}", source="manual")
    else:
        db.update("startups", sid, {"watch_source": "manual"})
    return sid


def collect_source(db: DB, fetcher: Fetcher, src: dict, enqueue=None) -> dict:
    """Run one funding source and record its status. Each source fails on its own."""
    try:
        if src["kind"] == "announcements":
            db.set_setting("source_investors", {**(db.get_setting("source_investors") or {}), src["key"]: src.get("investor")})
            counts = collect_announcements(db, fetcher, src, enqueue)
        elif src["kind"] == "portfolio":
            counts = collect_portfolio(db, fetcher, src)
        else:
            return {"skipped": src["kind"]}
    except FetchError as e:
        registry.record(db, src["key"], ok=False, error=str(e))
        return {"error": str(e)}
    if counts.get("error"):
        registry.record(db, src["key"], ok=False, counts=counts, error=counts["error"])
    else:
        registry.record(db, src["key"], ok=True, counts=counts)
    return counts
