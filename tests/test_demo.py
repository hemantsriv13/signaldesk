"""Demo mode (python -m signaldesk --demo) makes no network requests, calls no model and never touches
your data folder. Every socket entry point is replaced with one that records and refuses."""
from __future__ import annotations

import socket
import threading

import pytest
import uvicorn
from fastapi.testclient import TestClient

from signaldesk import __main__ as cli
from signaldesk import demo


@pytest.fixture
def no_network(monkeypatch):
    """Records and refuses every outgoing connection, including to the local model server on 127.0.0.1.
    The one exception is socket.socketpair(), which the event loop uses on Windows to wake itself: it
    connects two sockets inside this process and sends nothing anywhere."""
    attempts: list[str] = []
    inside = threading.local()
    real_pair, real_connect = socket.socketpair, socket.socket.connect

    def pair(*a, **k):
        inside.on = True
        try:
            return real_pair(*a, **k)
        finally:
            inside.on = False

    def refuse(name, real=None):
        def _refuse(*a, **k):
            if real and getattr(inside, "on", False):
                return real(*a, **k)
            attempts.append(f"{name}{a[1:2] or a[:1]}")
            raise OSError(f"test: network use is not allowed ({name})")
        return _refuse
    monkeypatch.setattr(socket, "socketpair", pair)
    monkeypatch.setattr(socket, "getaddrinfo", refuse("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", refuse("create_connection"))
    monkeypatch.setattr(socket.socket, "connect", refuse("connect", real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", refuse("connect_ex"))
    return attempts


@pytest.fixture
def demo_app(tmp_path, monkeypatch, no_network):
    """Runs the real --demo start-up path; only the final uvicorn.run is replaced, to hand back the app."""
    real_home = tmp_path / "your-data-folder"
    monkeypatch.setenv("SIGNALDESK_HOME", str(real_home))
    monkeypatch.setenv("SIGNALDESK_SUPABASE_URL", "https://cloud.fixture.example")      # must be ignored in demo mode
    monkeypatch.setattr(demo, "start_home", lambda: tmp_path / "demo")
    served = {}
    monkeypatch.setattr(uvicorn.Server, "run", lambda self: served.setdefault("config", self.config))
    assert cli.main(["--demo"]) == 0
    assert not real_home.exists()                     # your data folder is never read or created
    app = served["config"].app
    assert served["config"].host == "127.0.0.1"
    return app, no_network


GETS = ["/api/status", "/api/jobs", "/api/jobs?view=review", "/api/top", "/api/articles", "/api/cases", "/api/digests", "/api/runs",
        "/api/usage", "/api/sources", "/api/sweep", "/api/hiring", "/api/funding", "/api/outreach", "/api/profile", "/api/settings",
        "/api/delivery", "/api/feedback/suggestions", "/"]
REFUSED = [("POST", "/api/runs", {"agent": "all"}), ("POST", "/api/sweep", {"scope": "full"}), ("POST", "/api/digests/generate", {"regenerate": True, "confirm": True}),
           ("POST", "/api/jobs/1/recheck", None), ("POST", "/api/jobs/1/analyse", None), ("POST", "/api/jobs/1/contacts/discover", None),
           ("POST", "/api/articles/1/analyse", None), ("POST", "/api/cases/import", {"url": "https://example.com/a"}),
           ("POST", "/api/jobs/import", {"url": "https://example.com/j", "text": "x"}), ("POST", "/api/sources/discover", {"url": "https://example.com"}),
           ("POST", "/api/sources/companies/1/test", None), ("POST", "/api/sources/feeds/1/test", None), ("POST", "/api/delivery/sync", None),
           ("POST", "/api/hiring/company/refresh?key=c1", None), ("PUT", "/api/schedule", {"enabled": True, "time": "08:00"})]


def test_demo_serves_synthetic_data_without_any_network_request(demo_app):
    app, attempts = demo_app
    c = TestClient(app)
    for path in GETS:
        assert c.get(path).status_code == 200, path
    st = c.get("/api/status").json()
    assert st["demo"] is True and st["model"]["ready"] is False and "Demo mode" in st["model"]["message"]
    jobs = c.get("/api/jobs").json()["jobs"]
    assert jobs and all("fixture" in j["employer"].lower() for j in jobs)
    assert st["latestDigest"]["jobs"], "a briefing is there to show"
    detail = c.get(f"/api/jobs/{jobs[0]['id']}").json()
    assert detail["fit"] is None or detail["fit"]["model_id"] == demo.MODEL_ID
    for method, path, body in REFUSED:
        r = c.request(method, path, json=body)
        assert r.status_code == 403 and "Demo data" in r.json()["detail"], (path, r.status_code)
    assert attempts == []


def test_the_guard_catches_a_model_server_call(no_network):
    """The guard itself works: a request to the local model address is caught, not let through."""
    import httpx
    with pytest.raises(httpx.HTTPError):
        httpx.get("http://127.0.0.1:8000/v1/models", timeout=2)
    assert no_network


def test_demo_fetcher_and_model_refuse_everything(tmp_path, no_network):
    cfg = demo.build(tmp_path)
    f, m = demo.DemoFetcher(cfg.fetch), demo.DemoModel(cfg.model)
    with pytest.raises(Exception, match="Demo mode"):
        f.get("https://example.com")
    with pytest.raises(Exception, match="Demo mode"):
        m.chat("s", "u")
    assert m.status()["ready"] is False and no_network == []


def test_demo_data_is_built_only_from_invented_fixtures(tmp_path, no_network):
    from signaldesk.db import DB
    cfg = demo.build(tmp_path)
    db = DB(cfg.db_path)
    assert {r["name"] for r in db.all("SELECT name FROM companies")} <= {"Fixture Co"} | {f"Synthetic Startup {c} (fixture)" for c in "ABCDEFGH"}
    assert all(".example" in (r["official_url"] or "") for r in db.all("SELECT official_url FROM jobs"))
    assert all(".example" in r["url"] for r in db.all("SELECT url FROM articles"))
    assert {r["model_id"] for r in db.all("SELECT model_id FROM analyses")} == {demo.MODEL_ID}
    assert not db.scalar("SELECT COUNT(*) FROM contacts") and not db.scalar("SELECT COUNT(*) FROM model_calls")
