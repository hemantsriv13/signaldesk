"""Recurring requirements, gaps and lead-with suggestions (signaldesk/gaps.py). Invented jobs and the
synthetic profile only."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from signaldesk import contacts, gaps
from signaldesk.server import create_app

from conftest import TEST_PROFILE

FAMS = ["strategy_ops"]


def job_with_fit(db, title, fit, families=("strategy_ops",)):
    n = db.scalar("SELECT COUNT(*) FROM jobs") + 1
    jid = db.insert("jobs", {"source": "manual", "ext_id": f"g{n}", "employer": f"Fixture Co {n}", "title": title, "status": "New", "bucket": "candidate",
                             "listing_state": "open", "content_hash": f"h{n}", "first_seen_at": "2026-11-01", "last_seen_at": "2026-11-01",
                             "role_families": json.dumps(list(families)), "description_text": "Requirements: SQL. Stakeholder management."})
    db.insert("analyses", {"kind": "job_fit", "target_type": "job", "target_id": jid, "cache_key": f"k{n}", "prompt_version": "v", "model_id": "m",
                           "inputs_json": "{}", "output_json": json.dumps(fit), "validation_json": "{}", "created_at": "2026-11-01"})
    db.insert("articles", {"url": f"https://x.example/{n}", "title": "Why financial modelling matters for strategy teams", "retrieved_at": "2026-11-01",
                           "content_basis": "full", "content_hash": f"a{n}", "dedupe_key": f"d{n}", "source_name": "Fixture blog"}) if n == 1 else None
    return jid


def fit(essential, gaps_, evidence=()):
    return {"essential": [{"req": r, "quote": r} for r in essential], "preferred": [], "gaps": list(gaps_), "unknowns": [], "match": "weak match",
            "evidence": [{"req": r, "facts": f, "note": ""} for r, f in evidence], "summary": ""}


def test_recurring_requirements_count_roles_and_say_whether_you_have_evidence(engine):
    db = engine.db
    job_with_fit(db, "Strategy Associate", fit(["SQL for analysis", "Financial modelling"], ["No financial modelling experience stated"],
                                                [("SQL for analysis", ["P5"])]))
    job_with_fit(db, "Strategy Manager", fit(["Advanced financial modelling", "Stakeholder management"], ["Financial modelling not shown"]))
    job_with_fit(db, "Sales Lead", fit(["Financial modelling"], []), families=("solutions",))       # outside the target family
    aid = db.scalar("SELECT id FROM articles")
    db.insert("analyses", {"kind": "reading_card", "target_type": "article", "target_id": aid, "cache_key": "rc", "prompt_version": "v", "model_id": "m",
                           "inputs_json": "{}", "output_json": json.dumps({"main_argument": "Financial modelling helps strategy teams decide.",
                                                                           "concept": {"term": "Financial modelling"}}),
                           "validation_json": "{}", "created_at": "2026-11-01"})
    r = gaps.recurring(db, TEST_PROFILE, FAMS)
    assert r["roles_analysed"] == 2
    top = r["requirements"][0]
    assert "financial modelling" in top["label"].lower() and top["roles"] == 2 and top["evidence"] == "no evidence in your profile"
    assert [x["title"] for x in top["reading"]] == ["Why financial modelling matters for strategy teams"]
    sql = next(x for x in r["requirements"] if "sql" in x["label"].lower())
    assert sql["evidence"] == "cited in an analysis" and sql["roles_with_cited_evidence"] == 1
    assert r["gaps"][0]["roles"] == 2 and "financial modelling" in r["gaps"][0]["label"].lower()


def test_lead_with_reuses_your_facts_unchanged_and_accepting_changes_only_this_job(engine):
    db = engine.db
    jid = job_with_fit(db, "Strategy Associate", fit(["Present to business stakeholders", "SQL and Python"], [], [("SQL and Python", ["P5"])]))
    s = gaps.lead_with(db, TEST_PROFILE, jid)
    texts = {f["id"]: f["text"] for f in TEST_PROFILE["facts"]}
    assert [x["id"] for x in s["suggested"]][:2] == ["P5", "P4"]
    assert all(x["text"] == texts[x["id"]] for x in s["suggested"]) and len(s["suggested"]) == len(texts)
    before = json.dumps(engine.profiles.profile())
    api = TestClient(create_app(engine))
    assert api.post(f"/api/jobs/{jid}/lead-with", json={"accept": True}).json()["decision"] == "accepted"
    assert json.dumps(engine.profiles.profile()) == before                         # your profile is not rewritten
    assert [f["id"] for f in gaps.accepted_order(db, TEST_PROFILE, jid)][:2] == ["P5", "P4"]
    edited = {**TEST_PROFILE, "facts": [{**f, "text": f["text"] + " (edited)"} if f["id"] == "P5" else f for f in TEST_PROFILE["facts"]]}
    assert "P5" not in [f["id"] for f in gaps.accepted_order(db, edited, jid)]      # a changed fact is not reused silently
    assert api.post(f"/api/jobs/{jid}/lead-with", json={"accept": False}).json()["decision"] == "rejected"
    assert gaps.accepted_order(db, TEST_PROFILE, jid) == []
    assert api.get("/api/gaps").status_code == 200


def test_drafts_lead_with_the_accepted_facts(engine):
    db = engine.db
    engine.cfg.experimental.contacts = True
    jid = job_with_fit(db, "Strategy Associate", fit(["Present to business stakeholders"], [], [("Present to business stakeholders", ["P4"])]))
    gaps.decide(db, TEST_PROFILE, jid, True)
    cid = contacts.add_manual(db, job_id=jid, startup_id=None, company="Fixture Co 1", name="Tamsin Orlowe")
    oid = contacts.ensure_draft(db, cid, TEST_PROFILE, None)
    facts = json.loads(db.scalar("SELECT inputs_json FROM outreach WHERE id = ?", (oid,)))["facts"]
    assert facts[0]["id"] == "P4"
