"""Job board adapters for documented public APIs: Greenhouse, Lever and Ashby.

Each returns a list of postings in one shape. A failure raises FetchError; callers must not treat a
failed fetch as "no jobs".
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..netsafe import FetchError, Fetcher
from ..text import html_to_text

SUPPORTED = ("greenhouse", "lever", "ashby")


def board_url(ats: str, ats_id: str) -> str:
    return {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{ats_id}/jobs?content=true",
        "lever": f"https://api.lever.co/v0/postings/{ats_id}?mode=json",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{ats_id}?includeCompensation=true",
    }[ats]


def fetch_board(fetcher: Fetcher, ats: str, ats_id: str) -> list[dict]:
    if ats not in SUPPORTED:
        raise FetchError(f"{ats} boards are not supported; check this employer by hand.")
    r = fetcher.get(board_url(ats, ats_id), accept="application/json")
    if r.status == 404:
        raise FetchError(f"The {ats} board '{ats_id}' was not found (HTTP 404).")
    if r.status != 200:
        raise FetchError(f"HTTP {r.status} from the {ats} board.")
    try:
        data = r.json()
    except ValueError:
        raise FetchError("The board did not return JSON.") from None
    return {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}[ats](data)


def _greenhouse(data) -> list[dict]:
    if not isinstance(data, dict) or "jobs" not in data:
        raise FetchError("Unexpected Greenhouse response.")
    out = []
    for j in data["jobs"]:
        offices = ", ".join(o.get("name", "") for o in j.get("offices") or [] if o.get("name"))
        out.append({
            "ext_id": f"gh:{j['id']}",
            "title": j.get("title", "").strip(),
            "location": (j.get("location") or {}).get("name") or offices,
            "workplace": None,
            "description_text": html_to_text(j.get("content")),
            "official_url": j.get("absolute_url"),
            "apply_url": j.get("absolute_url"),
            "published_at": j.get("first_published") or None,
            "salary_extra": None,
        })
    return out


def _lever(data) -> list[dict]:
    if not isinstance(data, list):
        raise FetchError("Unexpected Lever response.")
    out = []
    for j in data:
        cats = j.get("categories") or {}
        parts = [j.get("descriptionPlain") or html_to_text(j.get("description"))]
        for lst in j.get("lists") or []:
            parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}")
        parts.append(j.get("additionalPlain") or html_to_text(j.get("additional")))
        sal = j.get("salaryRange") or {}
        salary = None
        if sal.get("min") or sal.get("max"):
            salary = f"{sal.get('currency', '')} {sal.get('min', '?')}–{sal.get('max', '?')} per {sal.get('interval', 'period')}".strip()
        locs = cats.get("allLocations") or [cats.get("location")]
        created = j.get("createdAt")
        out.append({
            "ext_id": f"lever:{j['id']}",
            "title": (j.get("text") or "").strip(),
            "location": ", ".join(x for x in locs if x),
            "workplace": j.get("workplaceType"),
            "description_text": "\n\n".join(p for p in parts if p).strip(),
            "official_url": j.get("hostedUrl"),
            "apply_url": j.get("applyUrl") or j.get("hostedUrl"),
            "published_at": datetime.fromtimestamp(created / 1000, timezone.utc).isoformat() if isinstance(created, (int, float)) else None,
            "salary_extra": salary or j.get("salaryDescriptionPlain"),
        })
    return out


def _ashby(data) -> list[dict]:
    if not isinstance(data, dict) or "jobs" not in data:
        raise FetchError("Unexpected Ashby response.")
    out = []
    for j in data["jobs"]:
        if j.get("isListed") is False:
            continue
        locs = [j.get("location")] + [s.get("location") for s in j.get("secondaryLocations") or []]
        comp = j.get("compensation") or {}
        out.append({
            "ext_id": f"ashby:{j['id']}",
            "title": (j.get("title") or "").strip(),
            "location": ", ".join(x for x in locs if x),
            "workplace": j.get("workplaceType") or ("Remote" if j.get("isRemote") else None),
            "description_text": j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            "official_url": j.get("jobUrl"),
            "apply_url": j.get("applyUrl") or j.get("jobUrl"),
            "published_at": j.get("publishedAt"),
            "salary_extra": comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary"),
        })
    return out
