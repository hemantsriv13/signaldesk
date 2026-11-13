"""LAN sign-in, side-panel scope, URL hardening and the side-panel workflow. All offline and mocked.
All companies and listings are SYNTHETIC."""
from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from signaldesk import auth, collect, lan, netsafe
from signaldesk.delivery import public_snapshot
from signaldesk.profile import DEFAULT_PREFS
from signaldesk.server import create_app

from conftest import add_company, greenhouse

LAN = "https://signaldesk.test:8443"
ORIGIN = {"origin": LAN}
PASSWORD = "correct horse battery staple"


def lan_client(engine) -> TestClient:
    engine.cfg.lan.hostnames = ["signaldesk.test"]
    engine.cfg.lan.port = 8443
    auth.set_password(engine.cfg.auth_path, PASSWORD)
    return TestClient(create_app(engine), base_url=LAN)


# ---------------------------------------------------------------- URL hardening
def never_resolve(*a, **k):
    raise AssertionError("no DNS lookup or request should happen")


@pytest.mark.parametrize("url", ["http://[::ffff:127.0.0.1]/", "http://[::ffff:192.168.1.1]/", "http://[64:ff9b::7f00:1]/", "http://[2002:c0a8:101::1]/",
                                 "http://192.168.1.1/", "http://169.254.169.254/latest/", "http://intranet/", "http://2130706433/", "http://router.home.arpa/"])
def test_private_destinations_rejected_before_any_request(url):
    with pytest.raises(netsafe.BlockedURL):
        netsafe.check_url(url, never_resolve)


def test_connection_goes_only_to_validated_public_address():
    def res(host, port, proto=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]
    with pytest.raises(netsafe.BlockedURL):
        netsafe.PinnedBackend(res).connect_tcp("rebinding.example", 443)

    used = []
    backend = netsafe.PinnedBackend(lambda h, p, proto=0: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", p))])
    backend._inner = type("Inner", (), {"connect_tcp": lambda self, host, port, **kw: used.append(host) or "stream"})()
    assert backend.connect_tcp("public.example", 443) == "stream" and used == ["93.184.216.34"]


def test_imported_linkedin_url_is_never_fetched(engine, boards):
    with pytest.raises(ValueError, match="does not fetch"):
        collect.import_job(engine.db, engine.fetcher, DEFAULT_PREFS, url="https://www.linkedin.com/jobs/view/123456789")
    with pytest.raises(ValueError):
        collect.import_job(engine.db, engine.fetcher, DEFAULT_PREFS, url="https://192.168.1.1.nip.io/job")
    assert not boards.hits


# ---------------------------------------------------------------- LAN sign-in
def test_signed_out_device_cannot_read_or_trigger(engine):
    c = lan_client(engine)
    assert c.get("/api/jobs").status_code == 401
    assert c.get("/api/outreach").status_code == 401
    assert c.get("/api/funding").status_code == 401
    assert c.post("/api/sweep", json={"scope": "full"}).status_code == 403            # no allowed Origin
    assert c.post("/api/sweep", json={"scope": "full"}, headers=ORIGIN).status_code == 401
    assert c.get("/api/auth/session").json() == {"required": True, "authenticated": False, "csrf": None, "passwordSet": True}
    assert TestClient(create_app(engine), base_url="https://evil.example:8443").get("/api/jobs").status_code == 403   # wrong host name


def test_sign_in_csrf_logout_and_revocation(engine):
    c = lan_client(engine)
    r = c.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert r.status_code == 200 and auth.COOKIE in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"] and "Secure" in r.headers["set-cookie"]
    csrf = r.json()["csrf"]
    assert c.get("/api/jobs").status_code == 200
    assert c.put("/api/preferences", json={}, headers=ORIGIN).status_code == 403                    # missing CSRF token
    assert c.put("/api/preferences", json={}, headers={**ORIGIN, "x-csrf-token": csrf}).status_code == 200
    assert c.put("/api/preferences", json={}, headers={"origin": "https://evil.example", "x-csrf-token": csrf}).status_code == 403
    assert c.post("/api/auth/logout", headers={**ORIGIN, "x-csrf-token": csrf}).status_code == 200
    assert c.get("/api/jobs").status_code == 401
    c.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    auth.revoke_sessions(engine.db)
    assert c.get("/api/jobs").status_code == 401


def test_login_is_throttled(engine):
    c = lan_client(engine)
    codes = [c.post("/api/auth/login", json={"password": "wrong password!"}, headers=ORIGIN).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    assert c.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN).status_code == 429   # still locked


def test_loopback_app_is_unchanged(engine):
    c = TestClient(create_app(engine))
    assert c.get("/api/status").status_code == 200 and c.get("/api/auth/session").json()["required"] is False


def test_lan_mode_fails_closed(engine):
    engine.cfg.lan.bind, engine.cfg.lan.hostnames = "0.0.0.0", []
    errors, _ = lan.check(engine.cfg)
    text = " ".join(errors)
    assert "not a private" in text and "hostnames is empty" in text and "cert_file not found" in text and "password" in text


# ---------------------------------------------------------------- side-panel token scope
def test_panel_token_only_reaches_panel_routes_and_revocation_stops_it(engine):
    c = TestClient(create_app(engine))
    tid, token = auth.create_panel_token(engine.db, "test panel", 90)
    h = {"authorization": f"Bearer {token}"}
    assert c.get("/api/panel/ping", headers=h).status_code == 200
    for path in ("/api/settings", "/api/outreach", "/api/jobs", "/api/panel/tokens", "/api/profile"):
        assert c.get(path, headers=h).status_code == 403, path
    assert c.post("/api/sweep", json={}, headers=h).status_code == 403
    assert c.get("/api/panel/ping", headers={"authorization": "Bearer sdp_not-a-real-token"}).status_code == 401
    auth.revoke_panel_token(engine.db, tid)
    assert c.get("/api/panel/ping", headers=h).status_code == 401
    assert c.get("/api/status").status_code == 200                 # the app itself keeps working


# ---------------------------------------------------------------- side-panel workflow
CARDS = """Founder's Office Associate
Founder's Office Associate with verification
Synthetic Startup G (fixture)
Bengaluru, Karnataka, India (On-site)
Promoted
Easy Apply
Special Projects Lead
Synthetic Startup H (fixture)
Bengaluru, Karnataka, India (Hybrid)
1 week ago
"""


def panel(engine):
    c = TestClient(create_app(engine))
    _tid, token = auth.create_panel_token(engine.db, "test", 90)
    return c, {"authorization": f"Bearer {token}"}


def test_compare_two_pasted_listings_and_repeat_paste_keeps_decision(engine):
    c, h = panel(engine)
    listings = c.post("/api/panel/parse", json={"text": CARDS}, headers=h).json()["listings"]
    assert [(l["title"], l["company"]) for l in listings] == [("Founder's Office Associate", "Synthetic Startup G (fixture)"),
                                                            ("Special Projects Lead", "Synthetic Startup H (fixture)")]
    res = c.post("/api/panel/import", json={"label": "Founder's Office Bengaluru", "listings": listings}, headers=h).json()["results"]
    assert len(res) == 2 and all(r["state"] == "need_full_description" and r["eligible"] and r["manual_import"] for r in res)
    first = res[0]["id"]
    assert c.post(f"/api/panel/jobs/{first}/decision", json={"decision": "shortlist"}, headers=h).json()["decision"] == "shortlisted"
    again = c.post("/api/panel/import", json={"label": "Founder's Office Bengaluru", "listings": listings}, headers=h).json()["results"]
    assert {r["id"] for r in again} == {r["id"] for r in res}
    assert next(r for r in again if r["id"] == first)["decision"] == "shortlisted"
    m = c.get("/api/panel/metrics", headers=h).json()
    row = m["labels"][0]
    assert (row["reviewed"], row["eligible"], row["assessable"], row["shortlisted"]) == (2, 2, 0, 1) and row["small_sample"]
    assert m["overall"]["reviewed"] == 2
    desc = "About the role. " + "You will report directly to the founder and own cross-functional launches. " * 12
    refreshed = c.post(f"/api/panel/jobs/{first}/description", json={"description": desc}, headers=h).json()
    assert refreshed["id"] == first and refreshed["state"].startswith("queued") and refreshed["decision"] == "shortlisted"


def test_pasted_listing_dedupes_against_employer_board(engine, boards):
    add_company(engine.db, "Synthetic Startup H (fixture)", "synthh")
    boards.routes["https://boards-api.greenhouse.io/v1/boards/synthh/"] = (200, greenhouse([{"id": 801, "title": "Special Projects Lead"}]))
    collect.collect_jobs(engine.db, engine.fetcher, engine.profiles.prefs())
    board_id = engine.db.scalar("SELECT id FROM jobs WHERE ext_id = 'gh:801'")
    c, h = panel(engine)
    listing = {"title": "Special Projects Lead", "company": "Synthetic Startup H (fixture)", "location": "Bengaluru",
               "url": "https://www.linkedin.com/jobs/view/4000000001", "description": ""}
    r = c.post("/api/panel/import", json={"label": "Special Projects Bengaluru", "listings": [listing]}, headers=h).json()["results"][0]
    assert r["id"] == board_id and r["on_employer_board"] and "manual_import" in r["found_on"]
    assert not boards.hits or all("linkedin" not in u for u in boards.hits)


def test_manual_imports_stay_off_the_cloud_by_default():
    content = {"generated_at": "2026-11-13T00:00:00+00:00", "jobs": [{"type": "job", "id": 1, "title": "A", "origin": "manual"},
                                                                   {"type": "job", "id": 2, "title": "B", "origin": "board"}], "articles": [], "notes": []}
    assert [j["id"] for j in public_snapshot(content)["jobs"]] == [2]
    assert len(public_snapshot(content, include_manual=True)["jobs"]) == 2


# ---------------------------------------------------------------- regressions found while exercising the real entry points
FULL_A = ("Special Projects Lead\nSynthetic Startup K (fixture) · Bengaluru, Karnataka, India · 2 days ago · 40 applicants\nAbout the job\n"
          "You will report directly to the founder and own cross-functional launches.\n" + "Synthetic filler sentence for length. " * 20)
FULL_B = ("Chief of Staff\nSynthetic Startup L (fixture) · Remote - US · 1 week ago\nAbout the job\n"
          "Partner with the CEO. Must be based in the United States.\n" + "Synthetic filler sentence for length. " * 20)


def test_require_login_on_this_pc_protects_reads_and_writes(engine):
    engine.cfg.auth.require_login_local = True
    auth.set_password(engine.cfg.auth_path, PASSWORD)
    c = TestClient(create_app(engine))
    for path in ("/api/status", "/api/jobs", "/api/outreach", "/api/digests", "/api/settings"):
        assert c.get(path).status_code == 401, path
    assert c.post("/api/sweep", json={"scope": "contacts"}).status_code == 401
    assert c.get("/api/auth/session").json()["required"] is True


def test_panel_token_cannot_write_admin_or_outreach(engine):
    c, h = panel(engine)
    assert c.post("/api/contacts", json={"company": "x", "name": "Synthetic Person"}, headers=h).status_code == 403
    assert c.put("/api/outreach/settings", json={"autosend": True}, headers=h).status_code == 403
    assert c.put("/api/preferences", json={}, headers=h).status_code == 403
    assert c.post("/api/panel/tokens", json={"label": "escalate"}, headers=h).status_code == 403


def test_expired_panel_token_is_refused(engine):
    c = TestClient(create_app(engine))
    tid, token = auth.create_panel_token(engine.db, "old", 1)
    engine.db.run("UPDATE panel_tokens SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (tid,))
    assert c.get("/api/panel/ping", headers={"authorization": f"Bearer {token}"}).status_code == 401


def test_two_full_descriptions_compare_and_model_offline_keeps_job_queued(engine, fake_model):
    fake_model.up = False
    engine.check_model()
    c, h = panel(engine)
    listings = c.post("/api/panel/parse", json={"text": FULL_A + "\n---\n" + FULL_B}, headers=h).json()["listings"]
    assert [(l["title"], l["company"], l["location"]) for l in listings] == [
        ("Special Projects Lead", "Synthetic Startup K (fixture)", "Bengaluru, Karnataka, India"),
        ("Chief of Staff", "Synthetic Startup L (fixture)", "Remote - US")]
    res = c.post("/api/panel/import", json={"label": "Special Projects Bengaluru", "listings": listings}, headers=h).json()["results"]
    states = {r["title"]: r["state"] for r in res}
    assert states == {"Special Projects Lead": "queued_model_offline", "Chief of Staff": "location_not_eligible"}
    assert res[0]["title"] == "Special Projects Lead"
    jid = res[0]["id"]
    assert engine.db.scalar("SELECT status FROM tasks WHERE kind = 'job_fit' AND target_id = ?", (jid,)) == "queued"
    assert not engine.db.scalar("SELECT COUNT(*) FROM tasks WHERE target_id = ?", (res[1]["id"],))   # no model call for an ineligible location
    assert fake_model.calls == []


def test_private_url_import_through_the_api_makes_no_request(engine, boards):
    c = TestClient(create_app(engine))
    r = c.post("/api/jobs/import", json={"url": "http://192.168.1.1/job/1"})
    assert r.status_code == 400 and not boards.hits


def test_lan_start_fails_closed_through_main(tmp_path, capsys):
    from signaldesk.__main__ import main
    assert main(["--home", str(tmp_path), "--lan"]) == 2
    out = capsys.readouterr().out
    assert "LAN mode was not started" in out and "password" in out
