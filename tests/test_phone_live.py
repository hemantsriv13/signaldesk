"""Live phone access over the signed-in HTTPS listener (Tailscale or home Wi-Fi). Mocked transport:
the real tunnel, certificate and phone are checked by hand (docs/LAN_AND_PANEL.md)."""
import json
import uuid

from fastapi.testclient import TestClient

from signaldesk import auth, lan, projects
from signaldesk.server import create_app
from test_projects import analysis, setup

HOST = "laptop.tail1234.ts.net"
APP_ORIGIN = "https://localhost"


def client(engine, monkeypatch, https=True):
    cfg, _ = setup(engine.cfg.home, monkeypatch)
    engine.cfg.project = cfg.project
    engine.cfg.lan.hostnames, engine.cfg.lan.port = [HOST], 8443
    base = f"https://{HOST}:8443" if https else "http://127.0.0.1"
    return TestClient(create_app(engine, delivery_env={}), base_url=base)


def test_phone_routes_refuse_plain_loopback_and_missing_tokens(engine, monkeypatch):
    c = client(engine, monkeypatch)
    local = TestClient(c.app, base_url="http://127.0.0.1")
    assert local.get("/api/phone/projects").status_code == 403
    r = c.get("/api/phone/projects", headers={"origin": APP_ORIGIN})
    assert r.status_code == 401 and r.headers["access-control-allow-origin"] == APP_ORIGIN
    _, panel = auth.create_panel_token(engine.db, "panel", 30)
    assert c.get("/api/phone/projects", headers={"authorization": "Bearer " + panel}).status_code == 401


def test_cors_only_for_the_app_shell(engine, monkeypatch):
    c = client(engine, monkeypatch)
    ok = c.options("/api/phone/projects", headers={"origin": APP_ORIGIN, "access-control-request-method": "GET"})
    assert ok.status_code == 204 and ok.headers["access-control-allow-origin"] == APP_ORIGIN
    evil = c.options("/api/phone/projects", headers={"origin": "https://evil.example", "access-control-request-method": "GET"})
    assert "access-control-allow-origin" not in evil.headers


def test_phone_token_reads_phone_safe_cards_and_reaches_nothing_else(engine, monkeypatch):
    c = client(engine, monkeypatch)
    aid = analysis(engine.db)
    engine.db.run("UPDATE analyses SET inputs_json=? WHERE id=?", (json.dumps({"profile_version": "PROFILE_VERSION_X"}), aid))
    projects.prepare(engine.cfg, engine.db)
    _, token = auth.create_phone_token(engine.db, "test phone", 30)
    h = {"authorization": "Bearer " + token, "origin": APP_ORIGIN}
    r = c.get("/api/phone/projects", headers=h)
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == APP_ORIGIN
    body = r.text
    assert "PROFILE_VERSION_X" not in body and '"phone"' not in body and "SECRET_GRADER" not in body
    assert json.loads(body)["tasks"]
    for path in ("/api/projects", "/api/jobs", "/api/panel/tokens", "/api/auth/sessions", "/api/projects/phone-token"):
        assert c.get(path, headers=h).status_code in (401, 403, 405), path


def test_phone_answer_is_human_phone_input_and_immutable(engine, monkeypatch):
    c = client(engine, monkeypatch)
    task = projects.prepare(engine.cfg, engine.db)["tasks"][0]
    _, token = auth.create_phone_token(engine.db, "test phone", 30)
    h = {"authorization": "Bearer " + token, "origin": APP_ORIGIN}
    rid = str(uuid.uuid4())
    body = {"id": rid, "verdict": "fail", "note": "phone", "answered_at": "2026-11-16T06:00:00+00:00"}
    assert c.post(f"/api/phone/projects/{task['id']}/answer", json=body, headers=h).json()["duplicate"] is False
    assert c.post(f"/api/phone/projects/{task['id']}/answer", json=body, headers=h).json()["duplicate"] is True
    assert c.post(f"/api/phone/projects/{task['id']}/answer", json={**body, "id": str(uuid.uuid4()), "verdict": "pass"}, headers=h).status_code == 409
    assert engine.db.one("SELECT via, id FROM project_responses") == {"via": "phone", "id": rid}
    assert c.get("/api/phone/projects", headers=h).json()["answered"] == {task["id"]: rid}


def test_revoked_phone_token_stops_working(engine, monkeypatch):
    c = client(engine, monkeypatch)
    tid, token = auth.create_phone_token(engine.db, "lost phone", 30)
    auth.revoke_panel_token(engine.db, tid)
    assert c.get("/api/phone/projects", headers={"authorization": "Bearer " + token}).status_code == 401


def test_tailscale_mode_binds_only_a_tailnet_address_and_ts_net_name(engine):
    cfg = engine.cfg
    cfg.lan.network, cfg.lan.hostnames = "tailscale", [HOST]
    for bad in ("192.168.1.10", "0.0.0.0", "127.0.0.1", "8.8.8.8", ""):
        cfg.lan.bind = bad
        assert any("Tailscale address" in e for e in lan.check(cfg)[0]), bad
    cfg.lan.bind = "100.101.102.103"
    errors = lan.check(cfg)[0]
    assert not any("bind" in e for e in errors) and any("cert_file not found" in e and "tailscale cert" in e for e in errors)
    cfg.lan.hostnames = ["192.168.1.10"]
    assert any("Tailscale name" in e for e in lan.check(cfg)[0])


def test_phone_codes_are_listed_and_revoked_from_projects_without_the_side_panel(engine, monkeypatch):
    c = client(engine, monkeypatch)
    local = TestClient(c.app, base_url="http://127.0.0.1")
    _, panel = auth.create_panel_token(engine.db, "panel", 30)
    token = local.post("/api/projects/phone-token", json={"label": "Pixel"}).json()["token"]
    [t] = local.get("/api/projects/phone-tokens").json()["tokens"]
    assert t["label"] == "Phone: Pixel"
    panel_id = engine.db.scalar("SELECT id FROM panel_tokens WHERE label='panel'")
    assert local.delete(f"/api/projects/phone-tokens/{panel_id}").status_code == 404      # cannot touch panel tokens
    assert local.delete(f"/api/projects/phone-tokens/{t['id']}").json()["tokens"] == []
    assert c.get("/api/phone/projects", headers={"authorization": "Bearer " + token}).status_code == 401
