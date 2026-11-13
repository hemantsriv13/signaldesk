"""Discovery sources and their honest status.

Built-in entries live here. `<data dir>/sources.toml` can add sources or change any field, and the
app's Sources page stores small overrides (on/off, page address) in the database. A source with
the same format as an existing one needs only configuration, for example another investor's
announcements page or another portfolio job board:

    [[source]]
    key = "my_investor"
    name = "My Investor"
    kind = "announcements"        # announcements | portfolio | job_listings | import
    group = "funding"             # funding | jobs
    investor = "My Investor"
    url = "https://example.com/news"

Modes shown in the app:
  automatic          collected on every sweep
  import_assisted    the site does not allow automated collection; you import saved listings
  needs_setup        the page address has not been confirmed yet
  unavailable        the last attempt failed or found nothing recognisable (temporary)
  off                turned off
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from .db import DB, now_iso

KINDS = ("ats", "announcements", "portfolio", "job_listings", "import")

# Page addresses are left empty where they have not been confirmed against the live site.
# Empty means "needs setup": nothing is fetched until you add the address in Sources.
BUILTIN: list[dict] = [
    {"key": "ats_boards", "name": "Employer job boards (Greenhouse, Lever, Ashby)", "kind": "ats", "group": "jobs",
     "note": "Public posting APIs of the employers listed in Sources. Final records and Apply links come from here."},
    {"key": "wellfound", "name": "Wellfound", "kind": "import", "group": "jobs",
     "note": "Wellfound does not allow automated collection. Import saved listing URLs or an export; each listing is then "
             "matched to the employer's own job board."},
    {"key": "yc_jobs", "name": "Y Combinator startup jobs", "kind": "job_listings", "group": "jobs",
     "url": "https://www.ycombinator.com/jobs",
     "note": "Public YC jobs page. Links to employer boards are added as employers; other listings are imported as unverified."},
    {"key": "yc_companies_india", "name": "Y Combinator companies in India", "kind": "portfolio", "group": "funding",
     "investor": "Y Combinator", "url": "https://www.ycombinator.com/companies/location/india",
     "note": "Portfolio membership only. YC batch dates are never used as funding dates. Uses YC's India location page: "
             "its robots.txt disallows the filtered directory (/companies?...) and its API."},
    {"key": "westbridge_portfolio", "name": "WestBridge Capital portfolio", "kind": "portfolio", "group": "funding",
     "investor": "WestBridge Capital", "url": "https://westbridgecap.com/portfolio",
     "note": "Portfolio membership only, regardless of when WestBridge invested. Each company's page links its website."},
    {"key": "westbridge", "name": "WestBridge Capital announcements", "kind": "announcements", "group": "funding",
     "investor": "WestBridge Capital", "url": "", "site": "https://www.westbridgecap.com",
     "note": "Add the address of WestBridge's news or portfolio announcements page after checking it in your browser."},
    {"key": "accel", "name": "Accel announcements", "kind": "announcements", "group": "funding", "investor": "Accel", "url": "",
     "enabled": False, "note": "Optional. Add a public Accel news or portfolio page address to use it."},
    {"key": "peak_xv", "name": "Peak XV and Surge announcements", "kind": "announcements", "group": "funding", "investor": "Peak XV",
     "url": "", "enabled": False, "note": "Optional. Add a public Peak XV or Surge news page address to use it."},
    {"key": "lightspeed", "name": "Lightspeed announcements", "kind": "announcements", "group": "funding", "investor": "Lightspeed",
     "url": "", "enabled": False, "note": "Optional. Add a public Lightspeed India news page address to use it."},
]

MODE_LABEL = {"automatic": "Automatic", "import_assisted": "Import-assisted", "needs_setup": "Needs setup",
              "unavailable": "Temporarily unavailable", "off": "Off"}


def _file_sources(home: Path) -> list[dict]:
    path = home / "sources.toml"
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [s for s in data.get("source", []) if isinstance(s, dict) and s.get("key")]


def load(db: DB, home: Path) -> list[dict]:
    merged: dict[str, dict] = {s["key"]: {"enabled": True, "url": "", **s} for s in BUILTIN}
    for s in _file_sources(home):
        merged[s["key"]] = {**merged.get(s["key"], {"enabled": True, "url": "", "group": "jobs"}), **s}
    for key, ov in (db.get_setting("source_overrides") or {}).items():
        if key in merged:
            merged[key].update({k: v for k, v in ov.items() if k in ("enabled", "url")})
    out = []
    for s in merged.values():
        if s.get("kind") not in KINDS:
            continue
        st = db.one("SELECT * FROM source_status WHERE key = ?", (s["key"],)) or {}
        s = {**s, "status": {k: st.get(k) for k in ("last_attempt_at", "last_success_at", "last_error", "last_error_at")},
             "counts": json.loads(st.get("last_counts_json") or "{}")}
        s["mode"] = mode(s)
        s["modeLabel"] = MODE_LABEL[s["mode"]]
        out.append(s)
    return out


def mode(s: dict) -> str:
    if not s.get("enabled", True):
        return "off"
    if s["kind"] == "import":
        return "import_assisted"
    if s["kind"] != "ats" and not s.get("url"):
        return "needs_setup"
    st = s.get("status") or {}
    if st.get("last_error_at") and (not st.get("last_success_at") or st["last_error_at"] >= st["last_success_at"]):
        return "unavailable"
    return "automatic"


def get(db: DB, home: Path, key: str) -> dict | None:
    return next((s for s in load(db, home) if s["key"] == key), None)


def set_override(db: DB, key: str, *, enabled: bool | None = None, url: str | None = None) -> None:
    ov = db.get_setting("source_overrides") or {}
    cur = ov.get(key, {})
    if enabled is not None:
        cur["enabled"] = bool(enabled)
    if url is not None:
        url = url.strip()
        if url and not url.startswith("https://"):
            raise ValueError("Use the page's https:// address.")
        cur["url"] = url
    ov[key] = cur
    db.set_setting("source_overrides", ov)


# ---------------------------------------------------------------- status and checkpoints
def record(db: DB, key: str, *, ok: bool, counts: dict | None = None, error: str | None = None) -> None:
    """An empty but successful check and a failed check are stored differently, so the app can
    tell "nothing new" from "the collector stopped working"."""
    now = now_iso()
    db.run("INSERT OR IGNORE INTO source_status (key) VALUES (?)", (key,))
    if ok:
        db.run("UPDATE source_status SET last_attempt_at = ?, last_success_at = ?, last_error = NULL, last_counts_json = ? WHERE key = ?",
               (now, now, json.dumps(counts or {}), key))
    else:
        db.run("UPDATE source_status SET last_attempt_at = ?, last_error = ?, last_error_at = ?, last_counts_json = ? WHERE key = ?",
               (now, (error or "failed")[:400], now, json.dumps(counts or {}), key))


def checkpoint(db: DB, key: str) -> dict:
    v = db.scalar("SELECT checkpoint_json FROM source_status WHERE key = ?", (key,))
    return json.loads(v) if v else {}


def save_checkpoint(db: DB, key: str, cp: dict) -> None:
    db.run("INSERT OR IGNORE INTO source_status (key) VALUES (?)", (key,))
    db.run("UPDATE source_status SET checkpoint_json = ? WHERE key = ?", (json.dumps(cp), key))
