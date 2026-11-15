"""The application pipeline (signaldesk/pipeline.py): migration, stage moves, the funnel and the
action lists. Invented jobs and people only; dates are fixed so the arithmetic is checkable."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from signaldesk import pipeline
from signaldesk.db import DB
from signaldesk.server import create_app

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)          # a Friday


def iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def job(db, title="Strategy Associate", employer="Quillfeather Labs (fixture)", status="New", bucket="candidate"):
    n = db.scalar("SELECT COUNT(*) FROM jobs") + 1
    return db.insert("jobs", {"source": "manual", "ext_id": f"p{n}", "employer": employer, "title": title, "status": status, "bucket": bucket,
                              "listing_state": "open", "content_hash": f"h{n}", "first_seen_at": iso(30), "last_seen_at": iso(1)})


def event(db, job_id, stage, days_ago, dated=1):
    db.insert("job_events", {"job_id": job_id, "stage": stage, "at": iso(days_ago), "note": None, "origin": "you", "dated": dated,
                             "created_at": iso(days_ago)})


def outreach(db, job_id, state="drafted", days_ago=0, name="Tamsin Orlowe"):
    cid = db.insert("contacts", {"job_id": job_id, "company": "Quillfeather Labs (fixture)", "name": name, "origin": "manual",
                                 "recipient_key": f"k{job_id}{name}", "status": "added_by_you", "created_at": iso(days_ago)})
    return db.insert("outreach", {"contact_id": cid, "job_id": job_id, "recipient_key": f"k{job_id}{name}", "note_text": "n", "message_text": "m",
                                  "drafted_by": "template", "state": state, "created_at": iso(days_ago), "updated_at": iso(days_ago)})


# ---------------------------------------------------------------- migration
def test_migration_keeps_statuses_and_marks_old_dates_unknown(tmp_path):
    path = tmp_path / "old.db"
    db = DB(path)
    a, b, c = job(db, status="Interested"), job(db, status="Applied"), job(db, status="Not relevant")
    o = outreach(db, b, state="contacted", days_ago=2)
    db.update("outreach", o, {"sent_at": iso(2)})
    db.conn.execute("DROP TABLE job_events")                    # back to the database before the pipeline
    db.conn.execute("PRAGMA user_version = 2")
    db.conn.commit()
    db = DB(path)
    assert [db.scalar("SELECT status FROM jobs WHERE id = ?", (j,)) for j in (a, b, c)] == ["Interested", "Applied", "Not relevant"]
    evs = {(r["job_id"], r["stage"], r["dated"]) for r in db.all("SELECT job_id, stage, dated FROM job_events")}
    assert evs == {(a, "Shortlisted", 0), (b, "Applied", 0), (b, "Contact made", 1)}
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == 3


# ---------------------------------------------------------------- stage moves
def test_record_sets_status_logs_date_and_note(engine):
    db = engine.db
    j = job(db)
    res = pipeline.record(db, j, "Shortlisted", note="Founder-facing role")
    assert res["status"] == "Interested" and db.scalar("SELECT status FROM jobs WHERE id = ?", (j,)) == "Interested"
    pipeline.record(db, j, "Applied", at="2026-11-10")
    evs = pipeline.events(db, j)
    assert [e["stage"] for e in evs] == ["Applied", "Shortlisted"]          # in date order: Applied was given an earlier date
    applied = next(e for e in evs if e["stage"] == "Applied")
    assert applied["at"].startswith("2026-11-10") and next(e for e in evs if e["stage"] == "Shortlisted")["note"] == "Founder-facing role"
    with pytest.raises(ValueError, match="future"):
        pipeline.record(db, j, "Interview", at="2099-01-01")
    with pytest.raises(ValueError, match="Unknown stage"):
        pipeline.record(db, j, "Ghosted")


def test_a_sent_draft_never_moves_a_job_backwards_or_reopens_it(engine):
    db = engine.db
    j, k = job(db, status="Interview"), job(db, status="Rejected")
    assert pipeline.record(db, j, "Contact made", origin="outreach", advance_only=True)["status"] == "Interview"
    assert pipeline.record(db, k, "Contact made", origin="outreach", advance_only=True)["status"] == "Rejected"
    s = job(db, status="Interested")
    assert pipeline.record(db, s, "Contact made", origin="outreach", advance_only=True)["status"] == "Contact made"
    assert db.scalar("SELECT COUNT(*) FROM job_events WHERE stage = 'Contact made'") == 3      # logged every time


# ---------------------------------------------------------------- the funnel
def test_counts_conversion_medians_and_weeks(engine):
    db = engine.db
    a, b, c = job(db, status="Interview"), job(db, status="Applied"), job(db, status="Interested")
    for jid, path in ((a, [("Shortlisted", 20), ("Applied", 16), ("Contact made", 10), ("Reply", 8), ("Interview", 2)]),
                      (b, [("Shortlisted", 12), ("Applied", 9)]),
                      (c, [("Shortlisted", 1)])):
        for stage, d in path:
            event(db, jid, stage, d)
    s = pipeline.summary(db, NOW)
    assert s["counts"]["Interview"] == 1 and s["counts"]["Applied"] == 1 and s["counts"]["Shortlisted"] == 1
    conv = {(x["from"], x["to"]): (x["reached"], x["moved"], x["rate"]) for x in s["conversion"]}
    assert conv[("Shortlisted", "Applied")] == (3, 2, 0.67) and conv[("Applied", "Contact made")] == (2, 1, 0.5)
    assert conv[("Interview", "Offer")] == (1, 0, 0.0)
    # Shortlisted: 4 days (a), 3 days (b), 1 day so far (c, still there) -> median 3
    assert s["median_days"]["Shortlisted"] == 3.0
    assert s["median_days"]["Applied"] == 7.5                     # a: 6 days; b: 9 days so far
    weeks = {w["week_of"]: w["applications"] for w in s["weeks"]}
    assert weeks["2026-11-09"] == 1 and weeks["2026-11-02"] == 1 and len(s["weeks"]) == 8


def test_undated_events_count_as_reached_but_not_in_timings(engine):
    db = engine.db
    j = job(db, status="Applied")
    event(db, j, "Applied", 40, dated=0)
    s = pipeline.summary(db, NOW)
    assert s["reached"]["Applied"] == 1 and s["median_days"]["Applied"] is None
    assert sum(w["applications"] for w in s["weeks"]) == 0


# ---------------------------------------------------------------- what needs you
def test_needs_action_rules(engine):
    db = engine.db
    late, recent, contacted, replied = (job(db, status="Applied", title=t) for t in ("Late", "Recent", "Contacted", "Replied"))
    db.update("jobs", replied, {"status": "Reply"})
    event(db, late, "Applied", 8)
    event(db, recent, "Applied", 3)
    event(db, contacted, "Applied", 10)
    outreach(db, contacted, state="contacted", days_ago=5)
    event(db, replied, "Reply", 1)
    old_draft_job, new_draft_job, dropped = job(db, status="Interested", title="Draft old"), job(db, status="Interested", title="Draft new"), job(db, status="Dropped", title="Dropped")
    outreach(db, old_draft_job, days_ago=4, name="Odile Ferncastle")
    outreach(db, new_draft_job, days_ago=1, name="Corwin Ashdale")
    outreach(db, dropped, days_ago=9, name="Petra Lindqvane")
    got = [(n["kind"], n["title"]) for n in pipeline.needs_action(db, NOW)]
    assert got == [("reply_waiting", "Replied"), ("applied_no_contact", "Late"), ("draft_unsent", "Draft old")]


def test_todays_actions_are_at_most_five_in_priority_order(engine):
    db = engine.db
    r = job(db, status="Reply", title="Replied role")
    event(db, r, "Reply", 1)
    job(db, status="Interview", title="Interview role")
    a = job(db, status="Applied", title="Applied role")
    event(db, a, "Applied", 9)
    s = job(db, status="Interested", title="Shortlisted role")
    event(db, s, "Shortlisted", 5)
    fresh = job(db, status="Interested", title="Just shortlisted")
    event(db, fresh, "Shortlisted", 1)
    matches = [{"id": 900 + i, "title": f"New match {i}", "employer": "Brambleway Systems (fixture)", "status": "New", "match": "potential match"}
               for i in range(4)] + [{"id": 999, "title": "Weak", "employer": "x", "status": "New", "match": "weak match"}]
    acts = pipeline.todays_actions(db, matches, NOW)
    assert [a["kind"] for a in acts] == ["reply_waiting", "interview", "applied_no_contact", "apply", "review_match"]
    assert acts[3]["title"] == "Shortlisted role" and all(a["text"] and a["why"] for a in acts)
    assert pipeline.todays_actions(db, [], NOW, limit=2)[1]["kind"] == "interview"


# ---------------------------------------------------------------- the API
def test_api_moves_logs_and_reports(engine):
    db = engine.db
    c = TestClient(create_app(engine))
    j = job(db)
    assert c.patch(f"/api/jobs/{j}", json={"status": "Interested"}).status_code == 200
    r = c.post(f"/api/jobs/{j}/stage", json={"stage": "Applied", "note": "Applied on the careers site", "at": "2026-11-12"}).json()
    assert r["status"] == "Applied" and [e["stage"] for e in r["events"]] == ["Applied", "Shortlisted"]   # by date: Applied was backdated
    assert c.post(f"/api/jobs/{j}/stage", json={"stage": "Nope"}).status_code == 400
    detail = c.get(f"/api/jobs/{j}").json()
    assert detail["stage"] == "Applied" and detail["stages"] == pipeline.STAGES and len(detail["events"]) == 2
    p = c.get("/api/pipeline").json()
    assert p["counts"]["Applied"] == 1 and p["items"][0]["id"] == j and p["items"][0]["last_event"]["note"] == "Applied on the careers site"
    assert "actions" in c.get("/api/actions").json()
    o = outreach(db, j)
    assert c.post(f"/api/outreach/{o}/contacted").json()["state"] == "contacted"
    assert db.scalar("SELECT status FROM jobs WHERE id = ?", (j,)) == "Contact made"


def test_rejected_and_dropped_leave_matches_but_stay_in_saved(engine):
    db = engine.db
    c = TestClient(create_app(engine))
    keep, gone = job(db, title="Keep"), job(db, title="Gone")
    c.post(f"/api/jobs/{gone}/stage", json={"stage": "Rejected"})
    titles = lambda view: {x["title"] for x in c.get(f"/api/jobs?view={view}").json()["jobs"]}  # noqa: E731
    assert titles("matches") == {"Keep"} and titles("saved") == {"Gone"}
