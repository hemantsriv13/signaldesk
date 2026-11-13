"""Hiring companies: employers with eligible open roles, built from the same job records as Jobs.

An opening counts when it is an open, non-duplicate listing located in Bengaluru or explicitly open
to remote work from India. Openings are grouped by employer (the tracked company when there is one,
otherwise the employer name on the listing). Funding, investors, pay and a model assessment are all
optional context: none of them decides whether a company is listed. Nothing here writes to jobs.
"""
from __future__ import annotations

import json

from . import jobrules, registry
from .db import DB
from .text import norm

ELIGIBLE = ("bengaluru", "remote_india")
UNCLASSIFIED = ("other", "ambiguous")
SHORTLIST = ("Interested", "Investigate", "Applied")
PREVIEW = 3


def _families(row: dict) -> list[str]:
    try:
        fams = json.loads(row.get("role_families") or "[]")
    except (TypeError, ValueError):
        fams = []
    return [f for f in fams if f] or [row.get("role_family") or "other"]


def _wanted(fams: list[str], selected: set[str]) -> bool:
    """No selection means every family, unclassified included. 'other' selects unclassified roles."""
    if not selected:
        return True
    return any(f in selected or (f in UNCLASSIFIED and "other" in selected) for f in fams)


def _key(row: dict) -> str:
    return f"c{row['company_id']}" if row.get("company_id") else f"e:{norm(row['employer'])}"


def _fits(db: DB, ids: list[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for r in db.all(f"SELECT target_id, output_json FROM analyses WHERE kind = 'job_fit' AND target_id IN ({','.join('?' * len(part))}) "
                        "ORDER BY id", part):
            try:
                out[r["target_id"]] = json.loads(r["output_json"]).get("match")
            except (TypeError, ValueError):
                pass
    return out


def _relevance(job: dict, match: str | None) -> int:
    """Profile order: the model's fit first, then your role and location preferences, then your own shortlist."""
    return ({"potential match": 4, "weak match": 1}.get(match or "", 0) + {"candidate": 3, "review": 1}.get(job["bucket"], 0)
            + (2 if job["status"] in SHORTLIST else 0) - (3 if match == "not a match" else 0))


def _investor_names(db: DB, home) -> dict[str, str]:
    try:
        return {s["key"]: s.get("investor") or s["name"] for s in registry.load(db, home) if s.get("group") == "funding"}
    except Exception:  # a malformed sources file must not hide hiring data
        return {}


def _backing(db: DB, home) -> tuple[dict[int, dict], dict[str, dict]]:
    """Evidence of backing per startup, indexed by tracked company and by normalised name."""
    names = _investor_names(db, home)
    events: dict[int, list[dict]] = {}
    for e in db.all("SELECT startup_id, investor, round, announced_on FROM funding_events ORDER BY announced_on DESC"):
        events.setdefault(e["startup_id"], []).append(e)
    by_company, by_name = {}, {}
    for s in db.all("SELECT * FROM startups WHERE is_demo = 0"):
        evs = events.get(s["id"], [])
        investors = sorted({e["investor"] for e in evs if e["investor"]} | ({names.get(s["watch_source"], s["watch_source"])} if s["watch_source"] else set()))
        info = {"startup_id": s["id"], "investors": investors, "latest_round": evs[0] if evs else None, "rounds": len(evs),
                "portfolio": names.get(s["watch_source"], s["watch_source"]) if s["watch_source"] else None,
                "careers_status": s["careers_status"], "careers_note": s["careers_note"], "careers_url": s["careers_url"],
                "careers_checked_at": s["careers_checked_at"], "domain": s["domain"], "name": s["name"], "company_id": s["company_id"]}
        if s["company_id"]:
            by_company[s["company_id"]] = info
        by_name[s["name_key"]] = info
    return by_company, by_name


def _board(c: dict | None, b: dict | None) -> dict:
    """Whether the company's openings could be read, and when they were last confirmed."""
    if c:
        failed = bool(c["last_error_at"] and (not c["last_success_at"] or c["last_error_at"] >= c["last_success_at"]))
        return {"state": "failed" if failed else "ok" if c["last_success_at"] else "unchecked", "careers_url": c["careers_url"],
                "last_success_at": c["last_success_at"], "last_attempt_at": c["last_attempt_at"],
                "error": c["last_error"] if failed else None, "warning": c["last_warning"]}
    if b:
        state = {"board_found": "ok", "failed": "failed", "page_only": "unreadable", "no_domain": "no_website", "unchecked": "unchecked",
                 "not_found": "no_careers_page"}.get(b["careers_status"], "unchecked")
        return {"state": state, "careers_url": b["careers_url"], "last_success_at": None, "last_attempt_at": b["careers_checked_at"],
                "error": b["careers_note"] if state != "ok" else None, "warning": None}
    return {"state": "listing_only", "careers_url": None, "last_success_at": None, "last_attempt_at": None, "error": None, "warning": None}


def companies(db: DB, home, *, families: list[str] | None = None, backing: str = "all", q: str = "", view: str = "hiring") -> dict:
    selected = {f for f in (families or []) if f}
    jobs = db.all("SELECT id, company_id, employer, title, location_raw, location_class, role_family, role_families, bucket, status, "
                  "verification_state, last_verified_at, first_seen_at, listing_state FROM jobs WHERE duplicate_of IS NULL")
    fits = _fits(db, [j["id"] for j in jobs if j["listing_state"] == "open" and j["location_class"] in ELIGIBLE])
    tracked = {c["id"]: c for c in db.all("SELECT * FROM companies")}
    by_company, by_name = _backing(db, home)

    groups: dict[str, dict] = {}

    def group(key: str, name: str, company_id: int | None) -> dict:
        if key not in groups:
            b = by_company.get(company_id) if company_id else None
            b = b or by_name.get(norm(name))
            groups[key] = {"key": key, "name": name, "company_id": company_id, "backing": b, "eligible": [], "eligible_all": 0,
                           "other_open": 0, "closed": 0}
        return groups[key]

    for c in tracked.values():                       # every tracked employer appears under All companies
        group(f"c{c['id']}", c["name"], c["id"])
    for j in jobs:
        g = group(_key(j), tracked[j["company_id"]]["name"] if j["company_id"] in tracked else j["employer"], j["company_id"])
        if j["listing_state"] != "open":
            g["closed"] += 1
        elif j["location_class"] not in ELIGIBLE:
            g["other_open"] += 1
        else:
            g["eligible_all"] += 1
            if _wanted(_families(j), selected):
                g["eligible"].append(j)
    for s in by_name.values():                       # discovered startups not yet tied to a tracked employer
        if not s["company_id"] and not any(g["backing"] is s for g in groups.values()):
            groups[f"s{s['startup_id']}"] = {"key": f"s{s['startup_id']}", "name": s["name"], "company_id": None, "backing": s,
                                             "eligible": [], "eligible_all": 0, "other_open": 0, "closed": 0}

    investors = sorted({i for g in groups.values() if g["backing"] for i in g["backing"]["investors"]})
    ql = q.strip().lower()
    out = []
    for g in groups.values():
        b = g["backing"]
        if backing == "backed" and not (b and b["investors"]):
            continue
        if backing == "unknown" and b and b["investors"]:
            continue
        if backing.startswith("investor:") and not (b and backing[9:] in b["investors"]):
            continue
        if ql and ql not in g["name"].lower() and not any(ql in j["title"].lower() for j in g["eligible"]):
            continue
        g["eligible"].sort(key=lambda j: (-_relevance(j, fits.get(j["id"])), j["title"]))
        board = _board(tracked.get(g["company_id"]), b)
        n = len(g["eligible"])
        state = ("hiring" if n else "filtered" if g["eligible_all"] else "unchecked" if board["state"] not in ("ok", "listing_only")
                 else "no_eligible")
        out.append({
            "key": g["key"], "name": g["name"], "company_id": g["company_id"], "openings": n, "openings_all_families": g["eligible_all"],
            "other_open": g["other_open"], "closed": g["closed"], "state": state,
            "preview": [j["title"] for j in g["eligible"][:PREVIEW]],
            "families": sorted({f for j in g["eligible"] for f in _families(j)}),
            "matches": sum(fits.get(j["id"]) == "potential match" or j["bucket"] == "candidate" for j in g["eligible"]),
            "shortlisted": sum(j["status"] in SHORTLIST for j in g["eligible"]),
            "relevance": sum(_relevance(j, fits.get(j["id"])) for j in g["eligible"]),
            "investors": b["investors"] if b else [], "latest_round": b["latest_round"] if b else None,
            "board": board, "last_verified_at": max((j["last_verified_at"] or "" for j in g["eligible"]), default="") or board["last_success_at"],
        })
    hiring = [c for c in out if c["openings"]]
    rows = hiring if view == "hiring" else out
    # Profile order: openings in your target roles first, then the model's fit and your shortlist, then size.
    rows.sort(key=lambda c: (-c["matches"], -c["relevance"], -c["openings"], c["name"].lower()))
    unfiltered = [g for g in groups.values() if g["eligible_all"]]
    return {
        "companies": rows,
        "counts": {"hiring": len(hiring), "openings": sum(c["openings"] for c in hiring), "all": len(out),
                   "hiring_unfiltered": len(unfiltered), "openings_unfiltered": sum(g["eligible_all"] for g in unfiltered)},
        "investors": investors,
        "families": {k: v for k, v in jobrules.FAMILY_LABEL.items() if k not in UNCLASSIFIED} | {"other": "Other and unclassified roles"},
    }


def company(db: DB, home, key: str) -> dict | None:
    """One company: its eligible openings (every family), what else it has open, its board and its backing."""
    tracked = None
    if key.startswith("s") and key[1:].isdigit():   # a startup tied to a tracked employer opens as that employer
        tied = db.scalar("SELECT company_id FROM startups WHERE id = ?", (int(key[1:]),))
        if tied:
            key = f"c{tied}"
    if key.startswith("c") and key[1:].isdigit():
        tracked = db.one("SELECT * FROM companies WHERE id = ?", (int(key[1:]),))
        if not tracked:
            return None
        rows = db.all("SELECT * FROM jobs WHERE company_id = ? AND duplicate_of IS NULL", (tracked["id"],))
        name = tracked["name"]
    elif key.startswith("e:"):
        rows = [r for r in db.all("SELECT * FROM jobs WHERE company_id IS NULL AND duplicate_of IS NULL") if norm(r["employer"]) == key[2:]]
        if not rows:
            return None
        name = rows[0]["employer"]
    elif key.startswith("s") and key[1:].isdigit():
        s = db.one("SELECT * FROM startups WHERE id = ?", (int(key[1:]),))
        if not s:
            return None
        rows, name = [], s["name"]
    else:
        return None
    by_company, by_name = _backing(db, home)
    b = (by_company.get(tracked["id"]) if tracked else None) or by_name.get(norm(name))
    if key.startswith("s"):
        b = next((x for x in by_name.values() if x["startup_id"] == int(key[1:])), b)
    eligible = [r for r in rows if r["listing_state"] == "open" and r["location_class"] in ELIGIBLE]
    fits = _fits(db, [r["id"] for r in eligible])
    eligible.sort(key=lambda j: (-_relevance(j, fits.get(j["id"])), j["title"]))
    labels = jobrules.FAMILY_LABEL
    return {
        "key": key, "name": name, "company_id": tracked["id"] if tracked else None, "board": _board(tracked, b),
        "openings": [{"id": r["id"], "title": r["title"], "location_raw": r["location_raw"], "location_class": r["location_class"],
                      "location_label": jobrules.LOCATION_LABEL.get(r["location_class"], r["location_class"]),
                      "families": [labels.get(f, f) for f in _families(r)], "status": r["status"], "bucket": r["bucket"],
                      "match": fits.get(r["id"]), "verification_state": r["verification_state"], "last_verified_at": r["last_verified_at"],
                      "first_seen_at": r["first_seen_at"], "apply_url": r["apply_url"] or r["official_url"], "official_url": r["official_url"]}
                     for r in eligible],
        "other_open": sum(r["listing_state"] == "open" and r["location_class"] not in ELIGIBLE for r in rows),
        "closed": sum(r["listing_state"] != "open" for r in rows),
        "startup_id": b["startup_id"] if b else None, "investors": b["investors"] if b else [], "portfolio": b["portfolio"] if b else None,
    }
