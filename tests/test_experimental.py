"""Experimental features are off by default and cannot run until [experimental] in config.toml turns
them on. Each test uses the default configuration and invented fixtures only; see docs/STATUS.md."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from signaldesk import collect, registry
from signaldesk.__main__ import main as signaldesk_main
from signaldesk.config import load_config
from signaldesk.lan import check as lan_check
from signaldesk.scheduler import Scheduler
from signaldesk.server import create_app

from conftest import add_company, drain

FOUNDER_DUTIES = ("About the role\nYou will report directly to the founder.\n"
                  "You will lead cross-functional strategic initiatives across the company.\n")


# One founder duty under an unclear title: with duties on, this is exactly the case sent for a model check.
ONE_DUTY = "About the role\nYou will report directly to the founder.\n"


def run_row(engine, agent):
    return engine.db.insert("runs", {"agent": agent, "trigger": "manual", "status": "collecting", "started_at": "2026-11-01T00:00:00+00:00",
                                     "stats_json": "{}", "log_json": "[]", "options_json": "{}"})


def test_every_switch_is_off_in_the_default_config(tmp_path):
    cfg = load_config(tmp_path)
    assert not any(vars(cfg.experimental).values()), vars(cfg.experimental)
    assert cfg.model.escalation_model_id == ""
    assert cfg.lan.enabled is False


def test_listing_sources_are_off_and_never_fetched(engine, boards):
    db = engine.db
    db.set_setting("source_overrides", {"yc_jobs": {"url": "https://jobs.fixture.example/"}})
    modes = {s["key"]: s["mode"] for s in engine.sources()}
    assert modes["wellfound"] == modes["yc_jobs"] == "experimental_off"
    totals = engine._collect_listing_sources(run_row(engine, "job_scout"), engine.profiles.prefs())
    assert totals["listing_sources_ok"] == totals["listing_sources_failed"] == 0
    assert not [u for u in boards.hits if "fixture.example" in u]


def test_listing_import_api_is_refused(engine):
    c = TestClient(create_app(engine))
    r = c.post("/api/imports/listings", json={"source": "wellfound", "text": json.dumps([{"title": "Strategy Associate", "company": "Synthetic Co"}])})
    assert r.status_code == 403 and "experimental" in r.json()["detail"]
    assert not engine.db.scalar("SELECT COUNT(*) FROM jobs")


def test_funding_announcements_are_off_but_portfolios_are_unchanged(engine, boards):
    engine.db.set_setting("source_overrides", {"accel": {"enabled": True, "url": "https://news.fixture.example/"},
                                               "westbridge": {"url": "https://news2.fixture.example/"}})
    modes = {s["key"]: s["mode"] for s in engine.sources()}
    assert {modes[k] for k in ("westbridge", "accel", "peak_xv", "lightspeed")} == {"experimental_off"}
    assert modes["yc_companies_india"] != "experimental_off" and modes["westbridge_portfolio"] != "experimental_off"
    engine._collect_funding_scout(run_row(engine, "funding_scout"))
    assert not [u for u in boards.hits if "news" in u and "fixture.example" in u]


def test_role_families_from_duties_are_off_by_default(engine):
    p = {"title": "Special Projects Lead", "location": "Bengaluru", "workplace": None, "description_text": FOUNDER_DUTIES, "salary_extra": None}
    off = collect.classify(p, engine.profiles.prefs())
    assert "founders_office" not in json.loads(off["role_families"]) and off["role_source"] == "rules"
    engine.cfg.experimental.duty_role_families = True
    on = collect.classify(p, engine.profiles.prefs())
    assert "founders_office" in json.loads(on["role_families"])


def test_no_model_role_checks_when_duties_are_off(engine, boards, fake_model):
    add_company(engine.db, "Synthetic Startup R (fixture)", "synthr")
    boards.routes["https://boards-api.greenhouse.io/v1/boards/synthr/"] = (200, {"jobs": [{
        "id": 1, "title": "Program Manager", "location": {"name": "Bengaluru"}, "content": ONE_DUTY,
        "absolute_url": "https://example.com/jobs/1", "first_published": "2026-10-30T10:00:00Z"}]})
    engine._collect_job_scout(run_row(engine, "job_scout"))
    assert not engine.db.scalar("SELECT COUNT(*) FROM tasks WHERE kind = 'role_classify'")
    assert not engine.db.scalar("SELECT COUNT(*) FROM jobs WHERE role_source = 'rules_uncertain'")


def test_contacts_never_run_by_default(engine, boards):
    rid = run_row(engine, "contact_scout")
    engine._collect_contact_scout(rid)
    assert not engine.db.scalar("SELECT COUNT(*) FROM tasks WHERE kind = 'contact_select'")
    c = TestClient(create_app(engine))
    jid = engine.db.insert("jobs", {"source": "manual", "ext_id": "x1", "employer": "Synthetic Co", "title": "Analyst", "status": "New",
                                    "first_seen_at": "2026-11-01T00:00:00+00:00", "last_seen_at": "2026-11-01T00:00:00+00:00", "content_hash": "h"})
    assert c.post(f"/api/jobs/{jid}/contacts/discover").status_code == 403
    assert c.post("/api/contacts", json={"job_id": jid, "company": "Synthetic Co", "name": "Invented Person"}).status_code == 403
    assert not engine.db.scalar("SELECT COUNT(*) FROM contacts") and not engine.db.scalar("SELECT COUNT(*) FROM outreach")
    assert boards.hits == []


def test_schedule_never_runs_by_default(engine, tmp_path):
    sch = Scheduler(engine)
    engine.db.set_setting("schedule", {"enabled": True, "times": ["08:00", "20:00"], "last_slot": None})   # even if stored as on
    assert sch.tick() == "wait" and not engine.db.scalar("SELECT COUNT(*) FROM runs")
    c = TestClient(create_app(engine, sch))
    assert c.put("/api/schedule", json={"enabled": True, "time": "08:00, 20:00"}).status_code == 403
    assert c.post("/api/sweep", json={"scope": "full", "trigger": "schedule"}).status_code == 403
    assert not engine.db.scalar("SELECT COUNT(*) FROM runs")
    # The Windows task's command is refused before it touches anything.
    assert signaldesk_main(["sweep", "--home", str(tmp_path / "cli"), "--trigger", "schedule"]) == 2


def test_larger_model_is_never_asked_by_default(engine, fake_model):
    assert engine.escalation is None and not engine.escalation_ready()
    jid = engine.db.insert("jobs", {"source": "manual", "ext_id": "x2", "employer": "Synthetic Co", "title": "Product Analyst", "status": "New",
                                    "first_seen_at": "2026-11-01T00:00:00+00:00", "last_seen_at": "2026-11-01T00:00:00+00:00", "content_hash": "h2", "description_text": "Requirements: SQL"})
    engine.analyse("job_fit", jid)
    drain(engine)
    served = {r["model_requested"] for r in engine.db.all("SELECT model_requested FROM model_calls")}
    assert served == {engine.cfg.model.model_id}


def test_lan_mode_cannot_start_from_the_default_config(tmp_path):
    cfg = load_config(tmp_path)
    errors, _ = lan_check(cfg)
    assert errors


def test_side_panel_api_is_refused_by_default(engine):
    c = TestClient(create_app(engine))
    assert c.get("/api/panel/ping").status_code == 403
    assert c.post("/api/panel/tokens", json={"label": "x"}).status_code == 403
    assert not engine.db.scalar("SELECT COUNT(*) FROM panel_tokens")
