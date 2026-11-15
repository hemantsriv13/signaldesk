"""The application pipeline, built on the job's existing status.

A job's `status` stays the one record of where it stands. The stages are status values: existing
ones keep their meaning ("Interested" and "Investigate" are Shortlisted, "Applied" is Applied) and
the later stages are new values. Every move to a stage is also written to `job_events` with a date
and your note, which is what the funnel, the timings and the action lists are computed from.

Rules decide everything here. Nothing calls the model.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone

from .db import DB, now_iso

STAGES = ["Shortlisted", "Applied", "Contact made", "Reply", "Interview", "Offer", "Rejected", "Dropped"]
MAIN = STAGES[:6]                       # the funnel, in order; Rejected and Dropped end it
CLOSED = ("Rejected", "Dropped")
# Stored status for each stage. Shortlisted keeps the existing "Interested" value.
STAGE_STATUS = {"Shortlisted": "Interested", **{s: s for s in STAGES[1:]}}
STATUS_STAGE = {"Interested": "Shortlisted", "Investigate": "Shortlisted", **{s: s for s in STAGES[1:]}}
# Statuses a job can have outside the pipeline: not triaged yet, or set aside before shortlisting.
OUTSIDE = ("New", "Not relevant", "Archived")
STATUSES = ["New", "Interested", "Investigate", *STAGES[1:], "Not relevant", "Archived"]
ACTIVE_STATUSES = tuple(s for s, st in STATUS_STAGE.items() if st not in CLOSED)
# Not shown among matches and To review any more: dismissed, or the application has ended.
HIDDEN_STATUSES = ("Not relevant", "Archived", *CLOSED)

APPLIED_NO_CONTACT_DAYS = 7
DRAFT_UNSENT_DAYS = 3
SHORTLIST_NOT_APPLIED_DAYS = 3
MAX_ACTIONS = 5


def stage_of(status: str | None) -> str | None:
    return STATUS_STAGE.get(status or "")


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _parse(at: str) -> datetime:
    dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _when(at: str | None) -> str:
    """A date you typed (YYYY-MM-DD) or now. Dates in the future are refused."""
    if not at:
        return now_iso()
    try:
        d = date.fromisoformat(at[:10])
    except ValueError:
        raise ValueError("Give the date as YYYY-MM-DD.") from None
    if d > datetime.now(timezone.utc).date() + timedelta(days=1):
        raise ValueError("That date is in the future.")
    return datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).isoformat()


def record(db: DB, job_id: int, stage: str, *, note: str = "", at: str | None = None, origin: str = "you", advance_only: bool = False) -> dict:
    """Move a job to a stage and log it. `advance_only` (used when a draft is marked sent) never moves
    a job backwards along the funnel or out of Rejected/Dropped; the event is logged either way."""
    if stage not in STAGES:
        raise ValueError(f"Unknown stage. Use one of: {', '.join(STAGES)}.")
    job = db.one("SELECT id, status FROM jobs WHERE id = ?", (job_id,))
    if not job:
        raise ValueError("Job not found")
    when = _when(at)
    db.insert("job_events", {"job_id": job_id, "stage": stage, "at": when, "note": (note or "").strip()[:2000] or None,
                             "origin": origin, "created_at": now_iso()})
    current = stage_of(job["status"])
    move = True
    if advance_only and current:
        if current in CLOSED:
            move = False                       # an ended application stays ended
        elif stage in MAIN and current in MAIN:
            move = MAIN.index(stage) > MAIN.index(current)
    if move:
        db.update("jobs", job_id, {"status": STAGE_STATUS[stage]})
    return {"status": STAGE_STATUS[stage] if move else job["status"], "stage": stage if move else current, "logged": stage, "at": when}


def on_status_change(db: DB, job_id: int, old: str | None, new: str) -> None:
    """A status set from the Jobs page or the side panel is a stage move too; log it."""
    stage = stage_of(new)
    if stage and stage != stage_of(old):
        db.insert("job_events", {"job_id": job_id, "stage": stage, "at": now_iso(), "note": None, "origin": "status",
                                 "created_at": now_iso()})


def events(db: DB, job_id: int) -> list[dict]:
    return db.all("SELECT id, stage, at, note, origin, dated FROM job_events WHERE job_id = ? ORDER BY at, id", (job_id,))


# ---------------------------------------------------------------- the funnel
def _job_events(db: DB) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for e in db.all("SELECT job_id, stage, at, dated FROM job_events ORDER BY at, id"):
        out.setdefault(e["job_id"], []).append(e)
    return out


def summary(db: DB, now: datetime | None = None) -> dict:
    """Counts per stage, conversion between funnel stages, median days in each stage, applications
    per week and the items that need action. Event dates you did not give (older statuses found
    when the pipeline was added) count for stages but not for timings."""
    now = _now(now)
    per_job = _job_events(db)
    current = {r["id"]: r for r in db.all(f"SELECT id, status FROM jobs WHERE status IN ({','.join('?' * len(STATUS_STAGE))})", tuple(STATUS_STAGE))}
    counts = {s: 0 for s in STAGES}
    for r in current.values():
        counts[stage_of(r["status"])] += 1
    reached = {s: {j for j, evs in per_job.items() if any(e["stage"] == s for e in evs)} for s in STAGES}
    for j, r in current.items():               # a status set before events existed still counts as reached
        reached[stage_of(r["status"])].add(j)
    conversion = []
    for a, b in zip(MAIN, MAIN[1:]):
        base = len(reached[a])
        moved = len(reached[a] & reached[b])
        conversion.append({"from": a, "to": b, "reached": base, "moved": moved, "rate": round(moved / base, 2) if base else None})
    durations: dict[str, list[float]] = {s: [] for s in MAIN}
    for j, evs in per_job.items():
        dated = [e for e in evs if e["dated"]]
        for i, e in enumerate(dated):
            if e["stage"] not in durations:
                continue
            end = _parse(dated[i + 1]["at"]) if i + 1 < len(dated) else (now if stage_of(current.get(j, {}).get("status")) == e["stage"] else None)
            if end:
                durations[e["stage"]].append(max(0.0, (end - _parse(e["at"])).total_seconds() / 86400))
    median_days = {s: (round(statistics.median(v), 1) if v else None) for s, v in durations.items()}
    weeks = []
    monday = (now - timedelta(days=now.weekday())).date()
    applied = [_parse(e["at"]).date() for evs in per_job.values() for e in evs if e["stage"] == "Applied" and e["dated"]]
    for k in range(7, -1, -1):
        start = monday - timedelta(weeks=k)
        weeks.append({"week_of": start.isoformat(), "applications": sum(start <= d < start + timedelta(days=7) for d in applied)})
    return {"stages": STAGES, "counts": counts, "reached": {s: len(v) for s, v in reached.items()}, "conversion": conversion,
            "median_days": median_days, "weeks": weeks, "needs_action": needs_action(db, now)}


# ---------------------------------------------------------------- what needs you
def _last_event(db: DB, job_id: int, stage: str) -> dict | None:
    return db.one("SELECT at, dated FROM job_events WHERE job_id = ? AND stage = ? ORDER BY at DESC, id DESC LIMIT 1", (job_id, stage))


def _days(now: datetime, at: str) -> float:
    return (now - _parse(at)).total_seconds() / 86400


def needs_action(db: DB, now: datetime | None = None) -> list[dict]:
    """Applied 7+ days ago with no contact; a draft not sent for 3+ days; a reply waiting on you."""
    now = _now(now)
    out = []
    for j in db.all("SELECT id, title, employer FROM jobs WHERE status = 'Reply'"):
        e = _last_event(db, j["id"], "Reply")
        out.append({"kind": "reply_waiting", "job_id": j["id"], "title": j["title"], "employer": j["employer"],
                    "since": e["at"] if e else None, "days": round(_days(now, e["at"])) if e and e["dated"] else None,
                    "why": "They replied; the next move is yours"})
    for j in db.all("SELECT id, title, employer FROM jobs WHERE status = 'Applied'"):
        e = _last_event(db, j["id"], "Applied")
        if not e or not e["dated"] or _days(now, e["at"]) < APPLIED_NO_CONTACT_DAYS:
            continue
        contacted = db.scalar("SELECT 1 FROM outreach WHERE job_id = ? AND state IN ('contacted', 'sent')", (j["id"],)) or \
            db.scalar("SELECT 1 FROM job_events WHERE job_id = ? AND stage = 'Contact made'", (j["id"],))
        if not contacted:
            out.append({"kind": "applied_no_contact", "job_id": j["id"], "title": j["title"], "employer": j["employer"], "since": e["at"],
                        "days": round(_days(now, e["at"])), "why": f"Applied {round(_days(now, e['at']))} days ago and no one contacted yet"})
    hidden = ",".join("?" * len(HIDDEN_STATUSES))
    for o in db.all(f"SELECT o.id, o.job_id, o.created_at, c.name, c.company, j.title FROM outreach o JOIN contacts c ON c.id = o.contact_id "
                    f"JOIN jobs j ON j.id = o.job_id WHERE o.state = 'drafted' AND j.status NOT IN ({hidden}) ORDER BY o.created_at", HIDDEN_STATUSES):
        days = _days(now, o["created_at"])
        if days >= DRAFT_UNSENT_DAYS:
            out.append({"kind": "draft_unsent", "job_id": o["job_id"], "outreach_id": o["id"], "title": o["title"], "employer": o["company"],
                        "contact": o["name"], "since": o["created_at"], "days": round(days),
                        "why": f"Draft to {o['name']} written {round(days)} days ago and not sent"})
    from .contacts import followups_due
    for f in followups_due(db, now.date().isoformat()):
        out.append({"kind": "followup_due", "job_id": f["job_id"], "outreach_id": f["outreach_id"], "followup_id": f["id"], "title": f["title"],
                    "employer": f["company"], "contact": f["name"], "since": f["due_on"], "days": None,
                    "why": f"Day-{5 if f['n'] == 1 else 12} follow-up to {f['name']} is due"})
    order = {"reply_waiting": 0, "followup_due": 1, "applied_no_contact": 2, "draft_unsent": 3}
    return sorted(out, key=lambda x: (order[x["kind"]], -(x["days"] or 0)))


def todays_actions(db: DB, new_matches: list[dict], now: datetime | None = None, limit: int = MAX_ACTIONS) -> list[dict]:
    """At most five concrete actions, by rule, in this order: replies waiting on you, interviews,
    applications to follow up, drafts to send, shortlisted roles not applied to yet, then new
    potential matches to look at. `new_matches` comes from the Today page's own ranking."""
    now = _now(now)
    acts: list[dict] = []
    for n in needs_action(db, now):
        if n["kind"] == "reply_waiting":
            acts.append({**n, "text": f"Reply about {n['title']} at {n['employer']}"})
    for j in db.all("SELECT id, title, employer FROM jobs WHERE status = 'Interview'"):
        acts.append({"kind": "interview", "job_id": j["id"], "title": j["title"], "employer": j["employer"],
                     "text": f"Prepare for the {j['employer']} interview ({j['title']})", "why": "Interview stage"})
    for n in needs_action(db, now):
        if n["kind"] == "applied_no_contact":
            acts.append({**n, "text": f"Find someone at {n['employer']} to follow up on {n['title']}"})
        elif n["kind"] == "draft_unsent":
            acts.append({**n, "text": f"Send or drop the note to {n['contact']} at {n['employer']}"})
        elif n["kind"] == "followup_due":
            acts.append({**n, "text": f"Send the follow-up to {n['contact']} at {n['employer']}"})
    for j in db.all("SELECT id, title, employer FROM jobs WHERE status IN ('Interested', 'Investigate')"):
        e = _last_event(db, j["id"], "Shortlisted")
        if e and e["dated"] and _days(now, e["at"]) >= SHORTLIST_NOT_APPLIED_DAYS:
            d = round(_days(now, e["at"]))
            acts.append({"kind": "apply", "job_id": j["id"], "title": j["title"], "employer": j["employer"], "days": d,
                         "text": f"Apply to {j['title']} at {j['employer']}", "why": f"Shortlisted {d} days ago"})
    for m in new_matches:
        if m.get("status", "New") == "New" and m.get("match") == "potential match":
            acts.append({"kind": "review_match", "job_id": m["id"], "title": m["title"], "employer": m["employer"],
                         "text": f"Decide on {m['title']} at {m['employer']}", "why": "New potential match: shortlist it or set it aside"})
    seen, out = set(), []
    for a in acts:
        key = (a["kind"], a["job_id"], a.get("outreach_id"), a.get("followup_id"))
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out[:limit]
