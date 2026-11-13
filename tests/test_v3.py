"""Offline checks for the V3 features. Everything is mocked: no network, no model server.
All companies, people, postings and announcements are SYNTHETIC (tests/fixtures/v3_synthetic.json)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from signaldesk import collect, contacts, funding, jobrules, registry, sweep
from signaldesk.profile import DEFAULT_PREFS

from conftest import add_company, drain, greenhouse

FX = json.loads((Path(__file__).resolve().parent / "fixtures" / "v3_synthetic.json").read_text(encoding="utf-8"))
RECENT = (date.today() - timedelta(days=10)).isoformat()


def html(body: str) -> str:
    return f"<html><head><title>Synthetic page</title></head><body>{body}</body></html>"


# ---------------------------------------------------------------- 1. one opening on two sites; a second requisition stays separate
def test_wellfound_listing_merges_with_ats_and_second_requisition_stays_distinct(engine, boards):
    db = engine.db
    add_company(db, "Synthetic Startup A (fixture)", "syntha")
    boards.routes["https://boards-api.greenhouse.io/v1/boards/syntha/"] = (200, greenhouse([
        {"id": 101, "title": "Strategy Associate", "content": "<p>Requisition 101. Business planning and quarterly reviews.</p>"},
        {"id": 102, "title": "Strategy Associate", "content": "<p>Requisition 102. Market research and pricing strategy.</p>"}]))
    prefs = engine.profiles.prefs()
    collect.collect_jobs(db, engine.fetcher, prefs)
    listing = [{"url": "https://wellfound.com/jobs/1-strategy-associate", "title": "Strategy Associate",
                "company": "Synthetic Startup A (fixture)", "apply_url": "https://example.com/jobs/101"}]
    res = collect.import_listings(db, prefs, source="wellfound", text=json.dumps(listing))
    assert res["merged"] == 1
    first = db.scalar("SELECT id FROM jobs WHERE ext_id = 'gh:101'")
    assert {r["source"] for r in db.all("SELECT source FROM job_sources WHERE job_id = ?", (first,))} == {"greenhouse", "wellfound"}
    assert db.scalar("SELECT duplicate_of FROM jobs WHERE ext_id = 'gh:102'") is None
    assert db.scalar("SELECT COUNT(*) FROM jobs WHERE listing_state = 'open' AND duplicate_of IS NULL") == 2
    # The same listing imported again is recognised, not added twice.
    assert collect.import_listings(db, prefs, source="wellfound", text=json.dumps(listing))["already"] == 1
    # Without an application link, a title shared by two requisitions is never merged into either.
    res = collect.import_listings(db, prefs, source="wellfound", text=json.dumps([{**listing[0], "url": "https://wellfound.com/jobs/2", "apply_url": ""}]))
    assert res["ambiguous"] == 1
    assert db.scalar("SELECT COUNT(*) FROM job_sources WHERE job_id = ?", (first,)) == 2


# ---------------------------------------------------------------- 2. YC membership is not funding
def test_yc_batch_company_without_dated_announcement_goes_to_watchlist(engine, boards):
    db = engine.db
    boards.routes["https://www.ycombinator.com/companies/synthetic-b"] = (200, html('<a href="https://synthb.example">Website</a>'))
    boards.routes["https://www.ycombinator.com/companies?regions=India"] = (200, html('<a href="/companies/synthetic-b">Synthetic Startup B (fixture)</a>'))
    src = {"key": "yc_companies_india", "kind": "portfolio", "investor": "Y Combinator", "url": "https://www.ycombinator.com/companies?regions=India"}
    res = funding.collect_source(db, engine.fetcher, src)
    assert res["listed"] == 1 and res["websites_found"] == 1
    s = db.one("SELECT * FROM startups WHERE name = 'Synthetic Startup B (fixture)'")
    assert s["domain"] == "synthb.example"
    assert not db.scalar("SELECT COUNT(*) FROM funding_events")
    assert not funding.startups(db, window="180")
    assert [x["name"] for x in funding.startups(db, window="watch")] == ["Synthetic Startup B (fixture)"]


# ---------------------------------------------------------------- 3. announcement -> company site -> Bengaluru strategy opening
def test_recent_investor_announcement_leads_to_verified_bengaluru_strategy_opening(engine, boards):
    db = engine.db
    a = FX["announcements"][0]
    boards.routes["https://fixture-capital.example/news/synthfin"] = (200, (
        f'<html><head><title>{a["title"]}</title><script type="application/ld+json">{{"@type": "NewsArticle", "datePublished": "{RECENT}"}}</script></head>'
        f'<body><p>{a["text"]}</p><a href="https://synthfin.example">Synthfin Labs</a></body></html>'))
    boards.routes["https://fixture-capital.example/news"] = (200, html(
        f'<ul><li><a href="https://fixture-capital.example/news/synthfin">{a["title"]}</a> <time datetime="{RECENT}">recent</time></li></ul>'))
    boards.routes["https://synthfin.example/careers"] = (200, html('<a href="https://boards.greenhouse.io/synthfin">Open roles</a>'))
    boards.routes["https://boards-api.greenhouse.io/v1/boards/synthfin/"] = (200, greenhouse([
        {"id": 201, "title": "Strategy Manager", "location": "Bengaluru", "content": "<p>Own business planning and market research.</p>"}]))
    src = {"key": "westbridge", "kind": "announcements", "investor": "Fixture Capital (synthetic)", "url": "https://fixture-capital.example/news"}
    res = funding.collect_source(db, engine.fetcher, src)
    assert res["funding"] == 1, res
    s = db.one("SELECT * FROM startups WHERE name = 'Synthfin Labs'")
    assert s["india_link"] == "india_based" and s["domain"] == "synthfin.example"
    e = db.one("SELECT * FROM funding_events WHERE startup_id = ?", (s["id"],))
    assert e["announced_on"] == RECENT and e["round"] == "series_a" and e["investor"] == "Fixture Capital (synthetic)"
    assert funding.resolve_careers(db, engine.fetcher)["boards"] == 1
    collect.collect_jobs(db, engine.fetcher, engine.profiles.prefs())
    row = funding.startups(db, window="30")[0]
    assert row["name"] == "Synthfin Labs" and row["openings"]["matching"] == 1
    assert row["opening_state"] == "1 matching opening(s)"
    job = db.one("SELECT * FROM jobs WHERE ext_id = 'gh:201'")
    assert job["bucket"] == "candidate" and "strategy_ops" in json.loads(job["role_families"])
    # A syndicated report of the same round does not create a second round.
    assert funding.save_event(db, s["id"], investor=None, round_="series_a", amount="$12 million", announced_on=RECENT,
                              url="https://news.example/synthfin-copy", title="copy", source="news") == "duplicate"


# ---------------------------------------------------------------- 4. roles judged by duties
@pytest.mark.parametrize("case", FX["roles"], ids=lambda c: c["id"])
def test_role_families_from_duties(case):
    fams, _evidence, _amb = jobrules.classify_roles(case["title"], case["description"])
    for f in case["expected"]:
        assert f in fams, (case["id"], fams)
    for f in case["not_expected"]:
        assert f not in fams, (case["id"], fams)


# ---------------------------------------------------------------- 5. location groups
@pytest.mark.parametrize("case", FX["locations"], ids=lambda c: c["id"])
def test_location_groups(case):
    cls = jobrules.classify_location(case["location"], case["workplace"], case["description"]).cls
    assert cls == case["expected_class"]
    assert jobrules.LOCATION_GROUP[cls] == case["expected_group"]


def test_uncertain_location_never_a_top_match():
    p = {"title": "Strategy Manager", "location": "Remote", "workplace": None, "description_text": "", "salary_extra": None}
    assert collect.classify(p, DEFAULT_PREFS)["bucket"] == "review"


@pytest.mark.parametrize("case", FX["pay"], ids=lambda c: c["id"])
def test_pay_bands(case):
    assert jobrules.comp_band(case["text"], case["kind"], 22)[0] == case["expected"]


# ---------------------------------------------------------------- 6. failures keep records and progress
def test_source_failing_midway_keeps_processed_items_and_skips_nothing(engine, boards):
    db = engine.db
    names = {1: "Synthco Alpha", 2: "Synthco Beta", 3: "Synthco Gamma"}
    items = "".join(f'<li><a href="https://fixture-news.example/a{i}">{names[i]} raises seed funding from Fixture Fund</a>'
                    f'<time datetime="{RECENT}">x</time></li>' for i in (1, 2, 3))
    boards.routes["https://fixture-news.example/a1"] = (200, html(f"<p>{names[1]} raises seed funding from Fixture Fund.</p>"))
    boards.routes["https://fixture-news.example/a2"] = (500, "down")
    boards.routes["https://fixture-news.example/news"] = (200, html(f"<ul>{items}</ul>"))
    src = {"key": "fixture_news", "kind": "announcements", "investor": "Fixture Fund", "url": "https://fixture-news.example/news"}
    res = funding.collect_source(db, engine.fetcher, src)
    assert "error" in res
    status = {r["url"][-2:]: r["status"] for r in db.all("SELECT url, status FROM announcements")}
    assert status["a1"] in ("parsed", "undated") and status["a2"] == "pending" and status["a3"] == "pending"
    assert db.one("SELECT last_error FROM source_status WHERE key = 'fixture_news'")["last_error"]
    boards.routes["https://fixture-news.example/a2"] = (200, html(f"<p>{names[2]} raises seed funding from Fixture Fund.</p>"))
    boards.routes["https://fixture-news.example/a3"] = (200, html(f"<p>{names[3]} raises seed funding from Fixture Fund.</p>"))
    funding.collect_source(db, engine.fetcher, src)
    assert not db.scalar("SELECT COUNT(*) FROM announcements WHERE status = 'pending'")


def test_listing_page_with_nothing_recognisable_is_unavailable_not_zero(engine, boards):
    db = engine.db
    cid = add_company(db, "Synthetic Startup C (fixture)", "synthc")
    boards.routes["https://boards-api.greenhouse.io/v1/boards/synthc/"] = (200, greenhouse([{"id": 301, "title": "Chief of Staff"}]))
    collect.collect_jobs(db, engine.fetcher, engine.profiles.prefs())
    boards.routes["https://jobs.fixture.example/"] = (200, html("<p>Please enable JavaScript.</p>"))
    db.set_setting("source_overrides", {"yc_jobs": {"url": "https://jobs.fixture.example/"}})
    totals = engine._collect_listing_sources(engine.db.insert("runs", {"agent": "job_scout", "trigger": "manual", "status": "collecting",
                                                                       "started_at": RECENT}), engine.profiles.prefs())
    assert totals["listing_sources_failed"] == 1
    assert registry.get(db, engine.cfg.home, "yc_jobs")["mode"] == "unavailable"
    # A board that suddenly fails changes nothing about its jobs.
    boards.routes["https://boards-api.greenhouse.io/v1/boards/synthc/"] = (500, "down")
    collect.collect_jobs(db, engine.fetcher, engine.profiles.prefs())
    assert db.scalar("SELECT listing_state FROM jobs WHERE company_id = ?", (cid,)) == "open"


# ---------------------------------------------------------------- 7. one active sweep
def test_two_overlapping_triggers_produce_one_active_sweep(engine):
    first = engine.start_all(trigger="manual", scope="funding")
    second = engine.start_all(trigger="schedule", scope="funding")
    assert first["started"] and not second["started"]
    assert engine.db.scalar("SELECT COUNT(DISTINCT group_id) FROM runs") == 1


def test_lock_held_by_another_process_blocks_a_sweep(engine):
    assert sweep.acquire(engine.db, "99999:other", scope="full", trigger="schedule", minutes=180) is None
    res = engine.start_all(scope="full")
    assert not res["started"] and "Another SignalDesk process" in res["skipped"]
    sweep.release(engine.db, "99999:other")
    assert sweep.holder(engine.db) is None


# ---------------------------------------------------------------- 8. an unchanged second sweep
def test_unchanged_second_sweep_adds_no_records_and_no_model_calls(engine, boards, fake_model):
    db = engine.db
    add_company(db, "Synthetic Startup D (fixture)", "synthd")
    boards.routes["https://boards-api.greenhouse.io/v1/boards/synthd/"] = (200, greenhouse([{"id": 401, "title": "Chief of Staff"}]))
    prefs = engine.profiles.prefs()
    collect.collect_jobs(db, engine.fetcher, prefs)
    job_id = db.scalar("SELECT id FROM jobs WHERE ext_id = 'gh:401'")
    assert engine.analyse("job_fit", job_id) == "queued"
    drain(engine)
    calls = len(fake_model.calls)
    before = (db.scalar("SELECT COUNT(*) FROM jobs"), db.scalar("SELECT COUNT(*) FROM job_sources"))
    stats = collect.collect_jobs(db, engine.fetcher, prefs)[0]
    assert stats["new"] == 0 and stats["changed"] == 0 and stats["unchanged"] == 1
    assert (db.scalar("SELECT COUNT(*) FROM jobs"), db.scalar("SELECT COUNT(*) FROM job_sources")) == before
    assert engine.analyse("job_fit", job_id) == "cached"
    drain(engine)
    assert len(fake_model.calls) == calls


# ---------------------------------------------------------------- 9. contacts and drafts without messaging access
class FakeSender:
    name, available, reason = "fake", True, ""

    def __init__(self):
        self.sent = []

    def send(self, contact, text):
        self.sent.append(contact["recipient_key"])
        return "sent"


def _job_with_named_manager(engine, boards, company="Synthetic Startup E (fixture)", board="synthe", ext=501):
    add_company(engine.db, company, board)
    boards.routes[f"https://boards-api.greenhouse.io/v1/boards/{board}/"] = (200, greenhouse([{
        "id": ext, "title": "Strategy Manager",
        "content": "<p>You will report directly to Meera Iyer, Head of Strategy. Own quarterly planning and business reviews.</p>"}]))
    collect.collect_jobs(engine.db, engine.fetcher, engine.profiles.prefs())
    return engine.db.scalar("SELECT id FROM jobs WHERE ext_id = ?", (f"gh:{ext}",))


def test_no_messaging_access_still_gives_verified_contact_and_draft(engine, boards):
    db = engine.db
    job_id = _job_with_named_manager(engine, boards)
    res = contacts.discover_for_job(db, engine.fetcher, job_id)
    c = db.one("SELECT * FROM contacts WHERE id = ?", (res["contact_ids"][0],))
    assert c["name"] == "Meera Iyer" and c["title"] == "Head of Strategy" and c["status"] == "verified"
    assert c["profile_url"] is None                     # never guessed
    oid = contacts.ensure_draft(db, c["id"], engine.profiles.profile(), None)
    o = db.one("SELECT * FROM outreach WHERE id = ?", (oid,))
    assert o["state"] == "drafted" and "Strategy Manager" in o["note_text"] and len(o["note_text"]) <= 300
    assert contacts.send_due(db, engine.messaging)["sent"] == 0
    assert db.scalar("SELECT state FROM outreach WHERE id = ?", (oid,)) == "drafted"


def test_repeated_runs_never_send_twice(engine, boards):
    db = engine.db
    job_a = _job_with_named_manager(engine, boards)
    job_b = _job_with_named_manager(engine, boards, "Synthetic Startup E (fixture)", "synthe2", 502)
    profile = engine.profiles.profile()
    for j in (job_a, job_b):
        for cid in contacts.discover_for_job(db, engine.fetcher, j)["contact_ids"]:
            contacts.ensure_draft(db, cid, profile, None)
    contacts.save_settings(db, {"autosend": True, "daily_cap": 5, "job_ids": [job_a, job_b]})
    sender = FakeSender()
    contacts.send_due(db, sender)
    contacts.send_due(db, sender)
    assert len(sender.sent) == 1                       # same person on two roles: contacted once
    contacts.save_settings(db, {"stopped": True})
    assert contacts.send_due(db, sender)["sent"] == 0


def test_unclear_send_is_never_retried(engine, boards):
    db = engine.db
    job_id = _job_with_named_manager(engine, boards)
    cid = contacts.discover_for_job(db, engine.fetcher, job_id)["contact_ids"][0]
    contacts.ensure_draft(db, cid, engine.profiles.profile(), None)
    contacts.save_settings(db, {"autosend": True, "job_ids": [job_id]})

    class Timeout(FakeSender):
        def send(self, contact, text):
            self.sent.append(1)
            raise TimeoutError("no answer")
    s = Timeout()
    contacts.send_due(db, s)
    contacts.send_due(db, s)
    assert len(s.sent) == 1 and db.scalar("SELECT state FROM outreach") == "send_unknown"


def test_model_draft_is_checked_before_it_replaces_the_template(engine, boards, fake_model):
    db = engine.db
    job_id = _job_with_named_manager(engine, boards)
    cid = contacts.discover_for_job(db, engine.fetcher, job_id)["contact_ids"][0]
    contacts.ensure_draft(db, cid, engine.profiles.profile(), None)
    fact = contacts.pick_fact(engine.profiles.profile(), db.one("SELECT * FROM jobs WHERE id = ?", (job_id,)), None)
    fake_model.replies["Write a LinkedIn connection note"] = {
        "note": "Hi Meera, I saw the Strategy Manager role at Synthetic Startup E (fixture) and would value a short chat.",
        "message": "Hi Meera, I'm applying for the Strategy Manager role at Synthetic Startup E (fixture). " + fact["text"],
        "detail_used": "D1", "fact_used": fact["id"], "injection_seen": False}
    assert engine.analyse("outreach_draft", cid) == "queued"
    drain(engine)
    o = db.one("SELECT * FROM outreach WHERE contact_id = ?", (cid,))
    assert o["drafted_by"] == "model" and "Synthetic Startup E" in o["message_text"]
    with pytest.raises(ValueError):
        contacts.validate_draft({"note": "Huge fan of your work!", "message": "Synthetic Startup E (fixture)", "fact_used": fact["id"]},
                                db.one("SELECT * FROM contacts WHERE id = ?", (cid,)), db.one("SELECT * FROM jobs WHERE id = ?", (job_id,)), fact)


# ---------------------------------------------------------------- funding extraction rules
@pytest.mark.parametrize("case", FX["announcements"], ids=lambda c: c["id"])
def test_announcement_reading(case):
    r = funding.extract_round(case["title"], case["text"])
    assert r["company"] == case["expected"]["company"]
    if case["expected"]["company"]:
        assert r["round"] == case["expected"]["round"]
        assert bool(r["india_evidence"]) == case["expected"]["india"]


def test_existing_saved_states_survive_a_refresh(engine, boards):
    db = engine.db
    add_company(db, "Synthetic Startup F (fixture)", "synthf")
    boards.routes["https://boards-api.greenhouse.io/v1/boards/synthf/"] = (200, greenhouse([{"id": 601, "title": "Chief of Staff"}]))
    collect.collect_jobs(db, engine.fetcher, engine.profiles.prefs())
    db.run("UPDATE jobs SET status = 'Applied' WHERE ext_id = 'gh:601'")
    first_seen = db.scalar("SELECT first_seen_at FROM jobs WHERE ext_id = 'gh:601'")
    collect.collect_jobs(db, engine.fetcher, engine.profiles.prefs())
    row = db.one("SELECT status, first_seen_at, change_state FROM jobs WHERE ext_id = 'gh:601'")
    assert row["status"] == "Applied" and row["first_seen_at"] == first_seen and row["change_state"] == "unchanged"
