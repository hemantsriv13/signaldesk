import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from signaldesk.db import now_iso
from signaldesk.scheduler import TZ, Scheduler, decide
from signaldesk.server import create_app


def at(day, hh, mm):
    return datetime(2026, 11, day, hh, mm, tzinfo=TZ)


def test_schedule_decisions():
    s = {"enabled": True, "time": "07:30", "last_slot": at(1, 7, 30).isoformat()}
    assert decide(at(2, 7, 31), {**s, "enabled": False}, False)[0] == "wait"
    assert decide(at(2, 7, 31), s, False)[0] == "run"
    # Laptop off for three days: one catch-up for the latest slot only.
    action, slot = decide(at(5, 10, 0), s, False)
    assert action == "catch-up" and slot == at(5, 7, 30)
    assert decide(at(5, 10, 1), {**s, "last_slot": slot.isoformat()}, False)[0] == "wait"
    assert decide(at(2, 7, 31), s, True)[0] == "skip-busy"


def test_scheduler_tick_never_overlaps(engine):
    sch = Scheduler(engine)
    sch.update(True, "07:30")
    s = engine.db.get_setting("schedule")
    s["last_slot"] = (datetime.fromisoformat(s["last_slot"]) - timedelta(days=1)).isoformat()
    engine.db.set_setting("schedule", s)
    engine.db.insert("runs", {"agent": "job_scout", "trigger": "manual", "status": "analysing", "started_at": now_iso()})
    assert sch.tick() == "skip-busy"
    assert "Skipped" in engine.db.get_setting("schedule")["last_result"]
    assert sch.tick() == "wait"


def test_schedule_is_off_by_default(engine):
    assert Scheduler(engine).describe()["enabled"] is False


def client(engine):
    return TestClient(create_app(engine))


def test_api_guards_host_and_origin(engine):
    c = client(engine)
    assert c.get("/api/status", headers={"host": "evil.example"}).status_code == 403
    assert c.post("/api/runs", json={"agent": "job_scout"}, headers={"origin": "https://evil.example"}).status_code == 403


def test_status_works_with_model_offline(engine, fake_model):
    fake_model.up = False
    r = client(engine).get("/api/status").json()
    assert r["model"]["reachable"] is False and r["latestDigest"] is None and r["runs"] == []


def test_regenerate_needs_confirmation(engine):
    c = client(engine)
    assert c.post("/api/digests/generate", json={"regenerate": True}).status_code == 400


def test_feedback_suggests_but_does_not_change_preferences(engine):
    db = engine.db
    c = client(engine)
    for i in range(2):
        aid = db.insert("articles", {"url": f"https://e.com/{i}", "title": f"t{i}", "retrieved_at": now_iso(), "content_basis": "full", "content_hash": str(i), "dedupe_key": str(i)})
        c.post("/api/feedback", json={"item_type": "article", "item_id": aid, "verdict": "too_technical"})
    sugg = c.get("/api/feedback/suggestions").json()
    assert [s["id"] for s in sugg] == ["less_technical"]
    assert engine.profiles.prefs()["reading_level"] == "any"
    c.post("/api/feedback/suggestions/less_technical")
    assert engine.profiles.prefs()["reading_level"] == "prefer_less_technical"


def test_quiet_day_digest_is_short_and_says_so(engine, fake_model):
    from conftest import drain
    rid = engine.start_run("digest_editor")["id"]
    import time
    for _ in range(100):
        if engine.db.scalar("SELECT status FROM runs WHERE id = ?", (rid,)) != "collecting":
            break
        time.sleep(0.02)
    drain(engine)
    d = json.loads(engine.db.one("SELECT content_json FROM digests")["content_json"])
    assert d["quiet"] and d["jobs"] == [] and d["action"] is None and fake_model.calls == []


def test_usage_reports_no_invented_numbers(engine):
    u = client(engine).get("/api/usage").json()
    assert u["all"]["modelRequests"] == 0 and u["all"]["tokensIn"] is None and u["paidApis"] == "disabled"


def test_reading_first_load_with_blank_filters(engine):
    """Regression: Reading's first load sends every filter blank ("All sources", "Any", "Any").
    `source=` used to fail integer parsing with HTTP 422."""
    db = engine.db
    sid = db.insert("reading_sources", {"name": "Blog", "feed_url": "https://blog.example.com/feed", "kind": "substack", "enabled": 1, "created_at": "x"})
    other = db.insert("reading_sources", {"name": "Other", "feed_url": "https://other.example.com/feed", "kind": "substack", "enabled": 1, "created_at": "x"})
    for i, (src, basis) in enumerate([(sid, "full"), (sid, "excerpt"), (other, "full")]):
        db.insert("articles", {"url": f"https://e.com/r{i}", "title": f"r{i}", "source_id": src, "retrieved_at": now_iso(),
                               "content_basis": basis, "content_hash": f"r{i}", "dedupe_key": f"r{i}"})
    c = client(engine)
    r = c.get("/api/articles?q=&source=&basis=&analysed=")          # the exact first-load request
    assert r.status_code == 200, r.text
    assert len(r.json()["articles"]) == 3 and {s["name"] for s in r.json()["sources"]} == {"Blog", "Other"}
    assert c.get("/api/articles").status_code == 200                 # the page now omits blank filters
    assert len(c.get(f"/api/articles?source={sid}").json()["articles"]) == 2
    assert len(c.get("/api/articles?basis=full").json()["articles"]) == 2
    assert c.get("/api/articles?source=abc").status_code == 400


def test_app_page_is_rechecked_so_updates_show(engine):
    """index.html names the current build's hashed assets; a cached copy would keep loading an old build."""
    from signaldesk import server
    if not (server.WEB / "index.html").exists():
        import pytest
        pytest.skip("web app not built")
    r = client(engine).get("/reading")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
