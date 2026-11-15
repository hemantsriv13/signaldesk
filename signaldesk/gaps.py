"""Recurring requirements and gaps across analysed roles, and which of your facts to lead with.

Rules only; nothing here calls the model. Everything is grouped from saved job-fit analyses, so it is
only as good as those analyses. Suggestions reuse your profile facts word for word: they reorder,
never rewrite or add.
"""
from __future__ import annotations

import json
import re

from .db import DB, now_iso

STOP = {"and", "the", "for", "with", "experience", "strong", "ability", "skills", "skill", "knowledge", "years", "year", "plus", "good",
        "excellent", "proven", "track", "record", "working", "work", "using", "role", "team", "teams", "understanding", "familiarity",
        "including", "related", "relevant", "least", "minimum", "preferred", "required", "must", "have", "has", "will", "able", "you",
        # how gaps are worded: "X not shown", "no X stated", "lacks X"
        "not", "shown", "stated", "mentioned", "lack", "lacks", "missing", "evidence", "unclear", "unknown", "demonstrated", "listed",
        "provided", "profile", "direct", "specific", "explicit", "explicitly"}
WORD = re.compile(r"[a-z][a-z0-9+#]{2,}")


def _key(text: str) -> frozenset:
    words = {w.rstrip("s") if len(w) > 4 else w for w in WORD.findall((text or "").lower())}
    return frozenset(w for w in words if w not in STOP)


def _similar(a: frozenset, b: frozenset) -> bool:
    return bool(a and b) and len(a & b) / len(a | b) >= 0.5


def _group(items: list[tuple[str, int, dict]]) -> list[dict]:
    """items: (text, job_id, extra). Greedy grouping by word overlap; label = most common wording."""
    groups: list[dict] = []
    for text, job_id, extra in items:
        k = _key(text)
        if not k:
            continue
        g = next((g for g in groups if _similar(g["key"], k)), None)
        if not g:
            g = {"key": k, "texts": {}, "jobs": set(), "evidenced_jobs": set()}
            groups.append(g)
        g["key"] = g["key"] | k if len(g["key"]) < 8 else g["key"]
        g["texts"][text] = g["texts"].get(text, 0) + 1
        g["jobs"].add(job_id)
        if extra.get("evidenced"):
            g["evidenced_jobs"].add(job_id)
    return groups


def _latest_fits(db: DB, families: list[str]) -> list[dict]:
    rows = db.all("SELECT j.id, j.title, j.employer, j.role_families, a.output_json FROM jobs j JOIN analyses a ON a.target_id = j.id "
                  "AND a.kind = 'job_fit' AND a.id = (SELECT MAX(b.id) FROM analyses b WHERE b.kind = 'job_fit' AND b.target_id = j.id) "
                  "WHERE j.listing_state = 'open' AND j.duplicate_of IS NULL")
    out = []
    for r in rows:
        fams = set(json.loads(r["role_families"] or "[]"))
        if families and not fams & set(families):
            continue
        out.append({**r, "fit": json.loads(r["output_json"])})
    return out


def recurring(db: DB, profile: dict, families: list[str], limit: int = 15) -> dict:
    """Top recurring essential requirements and gaps, each with how many roles ask for it, whether
    an analysis tied it to one of your facts, which of your facts share its words, and related reading."""
    fits = _latest_fits(db, families)
    facts = profile.get("facts", [])
    reqs, gaps = [], []
    for f in fits:
        cited_reqs = {_key(e.get("req", "")) for e in f["fit"].get("evidence", []) if e.get("facts")}
        for r in f["fit"].get("essential", []):
            k = _key(r.get("req", ""))
            reqs.append((r.get("req", ""), f["id"], {"evidenced": any(_similar(k, c) for c in cited_reqs)}))
        for g in f["fit"].get("gaps", []):
            gaps.append((g, f["id"], {}))
    cards = db.all("SELECT a.id, a.title, n.output_json FROM articles a JOIN analyses n ON n.target_id = a.id AND n.kind = 'reading_card' "
                   "WHERE a.duplicate_of IS NULL GROUP BY a.id")

    def finish(groups, kind):
        out = []
        for g in sorted(groups, key=lambda g: -len(g["jobs"]))[:limit]:
            label = max(g["texts"], key=g["texts"].get)
            fact_hits = [x["id"] for x in facts if len(g["key"] & _key(x["text"])) >= 2 or (len(g["key"]) <= 2 and g["key"] <= _key(x["text"]))]
            reading = []
            for c in cards:
                card = json.loads(c["output_json"])
                text = f"{c['title']} {card.get('main_argument', '')} {(card.get('concept') or {}).get('term', '')}"
                if len(g["key"] & _key(text)) >= min(2, len(g["key"])):
                    reading.append({"id": c["id"], "title": c["title"]})
            item = {"label": label, "roles": len(g["jobs"]), "job_ids": sorted(g["jobs"]), "facts_mentioning": fact_hits, "reading": reading[:3]}
            if kind == "requirement":
                item["roles_with_cited_evidence"] = len(g["evidenced_jobs"])
                item["evidence"] = ("cited in an analysis" if g["evidenced_jobs"] else
                                    "your facts mention it, no analysis cited them" if fact_hits else "no evidence in your profile")
            out.append(item)
        return out

    return {"roles_analysed": len(fits), "families": families, "requirements": finish(_group(reqs), "requirement"),
            "gaps": finish(_group(gaps), "gap")}


# ---------------------------------------------------------------- what to lead with, per job
def lead_with(db: DB, profile: dict, job_id: int) -> dict:
    """Your existing facts in a suggested order for this job: the ones its analysis cited first (in the
    order cited), then by how many words they share with its essential requirements. Unchanged text."""
    job = db.one("SELECT id, title, description_text FROM jobs WHERE id = ?", (job_id,))
    if not job:
        raise ValueError("Job not found")
    a = db.one("SELECT output_json FROM analyses WHERE kind = 'job_fit' AND target_id = ? ORDER BY id DESC LIMIT 1", (job_id,))
    fit = json.loads(a["output_json"]) if a else {}
    facts = {f["id"]: f for f in profile.get("facts", [])}
    cited, why = [], {}
    for e in fit.get("evidence", []):
        for fid in e.get("facts", []):
            if fid in facts and fid not in cited:
                cited.append(fid)
                why[fid] = f"The fit analysis tied it to: {e.get('req')}"
    req_key = frozenset().union(*[_key(r.get("req", "") + " " + r.get("quote", "")) for r in fit.get("essential", [])]) if fit.get("essential") \
        else _key(f"{job['title']} {job['description_text'] or ''}")
    rest = sorted((fid for fid in facts if fid not in cited), key=lambda fid: -len(req_key & _key(facts[fid]["text"])))
    for fid in rest:
        shared = sorted(req_key & _key(facts[fid]["text"]))
        why[fid] = f"Shares with the requirements: {', '.join(shared[:5])}" if shared else "Little overlap with this job's requirements"
    order = cited + rest
    saved = db.get_setting(f"lead_with:{job_id}")
    return {"job_id": job_id, "suggested": [{"id": fid, "text": facts[fid]["text"], "why": why[fid]} for fid in order],
            "current_profile_order": list(facts), "decision": saved, "analysed": bool(a)}


def decide(db: DB, profile: dict, job_id: int, accept: bool) -> dict:
    """Accept saves the suggested order for this job only (drafts for it then lead with those facts);
    your profile is not changed. Reject records that you declined."""
    s = lead_with(db, profile, job_id)
    value = {"decision": "accepted" if accept else "rejected", "order": [x["id"] for x in s["suggested"]] if accept else [],
             "facts": {x["id"]: x["text"] for x in s["suggested"]} if accept else {}, "at": now_iso()}
    db.set_setting(f"lead_with:{job_id}", value)
    return value


def accepted_order(db: DB, profile: dict, job_id: int) -> list[dict]:
    """The facts you accepted for this job, only where their text is still in your profile unchanged."""
    v = db.get_setting(f"lead_with:{job_id}") or {}
    if v.get("decision") != "accepted":
        return []
    current = {f["id"]: f for f in profile.get("facts", [])}
    return [current[i] for i in v.get("order", []) if i in current and current[i]["text"] == v["facts"].get(i)]
