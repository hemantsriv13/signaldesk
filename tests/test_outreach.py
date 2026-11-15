"""Drafts, follow-ups and manual contacts (signaldesk/contacts.py). Invented companies, people and
profile facts only (tests/fixtures/profile_synthetic.json)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from signaldesk import contacts, pipeline
from signaldesk.server import create_app

from conftest import TEST_PROFILE, add_company, greenhouse

CO = "Quillfeather Labs (fixture)"
POSTING = ("<p>About the role</p><p>You will own quarterly business reviews and build the operating cadence with the founders.</p>"
           "<p>Requirements:</p><ul><li>Experience presenting analysis to business stakeholders and leadership.</li>"
           "<li>Strong SQL and Python for ad-hoc analysis.</li></ul><p>Apply at https://quillfeather.example/apply</p>"
           "<p>You will report directly to Tamsin Orlowe, Head of Strategy.</p>")
FACTS = TEST_PROFILE["facts"]


@pytest.fixture
def role(engine, boards):
    engine.cfg.experimental.contacts = True
    add_company(engine.db, CO, "quill")
    boards.routes["https://boards-api.greenhouse.io/v1/boards/quill/"] = (200, greenhouse([{"id": 801, "title": "Strategy Manager", "content": POSTING}]))
    from signaldesk import collect
    collect.collect_jobs(engine.db, engine.fetcher, engine.profiles.prefs())
    jid = engine.db.scalar("SELECT id FROM jobs WHERE ext_id = 'gh:801'")
    (cid,) = contacts.discover_for_job(engine.db, engine.fetcher, jid)["contact_ids"]
    return engine.db.one("SELECT * FROM jobs WHERE id = ?", (jid,)), engine.db.one("SELECT * FROM contacts WHERE id = ?", (cid,))


# ---------------------------------------------------------------- the quoted detail and your facts
def test_detail_is_a_sentence_copied_from_the_posting_about_the_work(role):
    job, _ = role
    facts = contacts.pick_facts(TEST_PROFILE, job, None)
    d = contacts.pick_detail(job, facts)
    assert d and d in job["description_text"] and "http" not in d and "Tamsin" not in d or d == "You will report directly to Tamsin Orlowe, Head of Strategy."
    assert "stakeholders" in d.lower() or "sql" in d.lower()          # the duty that overlaps the facts (P4, P5)


def test_fit_analysis_facts_come_first(role):
    job, _ = role
    fit = {"output": {"evidence": [{"facts": ["P2"]}]}}
    assert [f["id"] for f in contacts.pick_facts(TEST_PROFILE, job, fit)][0] == "P2"
    assert len(contacts.pick_facts(TEST_PROFILE, job, fit)) == 2


def test_template_drafts_quote_the_posting_use_only_facts_and_pass_every_check(role):
    job, c = role
    facts = contacts.pick_facts(TEST_PROFILE, job, None)
    detail = contacts.pick_detail(job, facts)
    note, msg = contacts.template_draft(c, job, facts, detail)
    assert len(note) <= 300 and f'"{detail}"' in msg and job["employer"] in msg
    for f in facts:
        assert f["text"].rstrip(".") in msg
    claims = [{"text": f["text"], "fact": f["id"]} for f in facts]
    assert contacts.validate_draft({"note": note, "message": msg, "claims": claims, "quote": detail}, c, job, facts, detail) == (note, msg)


# ---------------------------------------------------------------- every claim about you maps to a fact
@pytest.mark.parametrize("claim", [
    "I led a team of 12 analysts at a bank.",                       # not in any fact
    "I built data products used by 40 teams.",                     # a fact, plus an invented number
    "Over my career I managed supply-chain budgets for a decade.",  # stretches a fact into something else
])
def test_unbacked_claims_are_caught(claim):
    assert contacts.unbacked_claims(claim, [FACTS[1], FACTS[2]])


@pytest.mark.parametrize("claim", [
    "I built data products.",
    "I worked on finance and supply-chain analytics.",
    "I'd value a short chat about the role.",                      # not a claim about experience
])
def test_claims_that_restate_a_fact_pass(claim):
    assert contacts.unbacked_claims(claim, [FACTS[1], FACTS[2]]) == []


def test_model_draft_is_rejected_for_an_unbacked_claim_a_foreign_fact_id_or_a_missing_quote(role):
    job, c = role
    facts = contacts.pick_facts(TEST_PROFILE, job, None)
    detail = contacts.pick_detail(job, facts)
    good = {"note": f'Hi Tamsin, the {job["title"]} role at {CO} says "{detail}" Open to a short chat?',
            "message": f"Hi Tamsin, I'm applying for the {job['title']} role at {CO}. I presented to business stakeholders.",
            "claims": [{"text": "I presented to business stakeholders.", "fact": "P4"}], "quote": detail}
    contacts.validate_draft(good, c, job, facts, detail)
    for bad, why in [({**good, "message": good["message"] + " I led a team of 12 analysts."}, "not backed"),
                     ({**good, "claims": [{"text": "x", "fact": "P9"}]}, "fact id that was not given"),
                     ({**good, "quote": "Something the posting never says at all"}, "word for word"),
                     ({**good, "note": "Hi Tamsin, huge fan of your work at " + CO}, "generic praise"),
                     ({**good, "message": good["message"] + " I am a former chief of staff."}, "title or experience")]:
        with pytest.raises(ValueError, match=why):
            contacts.validate_draft(bad, c, job, facts, detail)


# ---------------------------------------------------------------- mark sent and follow-ups
def test_mark_sent_records_the_date_moves_the_role_and_schedules_follow_ups(engine, role):
    job, c = role
    oid = contacts.ensure_draft(engine.db, c["id"], TEST_PROFILE, None)
    pipeline.record(engine.db, job["id"], "Applied")
    sent = (date.today() - timedelta(days=6)).isoformat()
    r = contacts.mark_sent(engine.db, oid, sent)
    assert r["state"] == "contacted" and r["sent_at"].startswith(sent)
    assert engine.db.scalar("SELECT status FROM jobs WHERE id = ?", (job["id"],)) == "Contact made"
    fu = engine.db.all("SELECT n, due_on, text FROM outreach_followups WHERE outreach_id = ? ORDER BY n", (oid,))
    assert [(f["n"], f["due_on"]) for f in fu] == [(1, (date.today() - timedelta(days=1)).isoformat()), (2, (date.today() + timedelta(days=6)).isoformat())]
    assert all(len(f["text"]) <= 300 and CO in f["text"] for f in fu)
    due = contacts.followups_due(engine.db, date.today().isoformat())
    assert [d["n"] for d in due] == [1]
    assert [a["kind"] for a in pipeline.todays_actions(engine.db, [])][:1] == ["followup_due"]
    assert contacts.mark_sent(engine.db, oid)["sent_at"].startswith(sent)        # marking twice changes nothing


def test_follow_ups_stop_once_they_reply_or_the_role_ends(engine, role):
    job, c = role
    oid = contacts.ensure_draft(engine.db, c["id"], TEST_PROFILE, None)
    contacts.mark_sent(engine.db, oid, (date.today() - timedelta(days=20)).isoformat())
    late = (date.today() + timedelta(days=1)).isoformat()
    assert [d["n"] for d in contacts.followups_due(engine.db, late)] == [1]          # day 12 waits for day 5
    contacts.mark_followup_sent(engine.db, contacts.followups_due(engine.db, late)[0]["id"])
    assert [d["n"] for d in contacts.followups_due(engine.db, late)] == [2]
    pipeline.record(engine.db, job["id"], "Reply")
    assert contacts.followups_due(engine.db, late) == []


def test_mark_sent_api_takes_a_date_and_lists_follow_ups(engine, role):
    job, c = role
    oid = contacts.ensure_draft(engine.db, c["id"], TEST_PROFILE, None)
    api = TestClient(create_app(engine))
    assert api.post(f"/api/outreach/{oid}/contacted", json={"at": "2099-01-01"}).status_code == 400
    assert api.post(f"/api/outreach/{oid}/contacted", json={"at": date.today().isoformat()}).json()["state"] == "contacted"
    item = next(i for i in api.get("/api/outreach").json()["items"] if i["id"] == oid)
    assert [f["n"] for f in item["followups"]] == [1, 2] and item["detail"]
    fid = item["followups"][0]["id"]
    assert api.post(f"/api/outreach/followups/{fid}/sent", json={}).json()["state"] == "sent"


# ---------------------------------------------------------------- manual entry with a LinkedIn address
def test_pasted_linkedin_address_is_stored_in_one_form_and_gets_a_draft(engine, role):
    job, _ = role
    api = TestClient(create_app(engine))
    r = api.post("/api/contacts", json={"job_id": job["id"], "company": CO, "name": "Odile Ferncastle",
                                         "profile_url": "https://in.linkedin.com/in/odile-ferncastle-fixture/?utm_source=share"})
    cid = r.json()["id"]
    c = engine.db.one("SELECT * FROM contacts WHERE id = ?", (cid,))
    assert c["profile_url"] == "https://www.linkedin.com/in/odile-ferncastle-fixture" and c["status"] == "added_by_you"
    assert engine.db.scalar("SELECT COUNT(*) FROM outreach WHERE contact_id = ?", (cid,)) == 1
    again = api.post("/api/contacts", json={"job_id": job["id"], "company": CO, "name": "Odile Ferncastle",
                                             "profile_url": "https://www.linkedin.com/in/odile-ferncastle-fixture"}).json()["id"]
    assert again == cid                                                       # the same person pasted twice
    for bad in ("https://www.linkedin.com/company/quillfeather", "https://www.linkedin.com/search/results/people/?keywords=odile",
                "http://www.linkedin.com/in/odile"):
        assert api.post("/api/contacts", json={"job_id": job["id"], "company": CO, "name": "Odile Ferncastle", "profile_url": bad}).status_code == 400
