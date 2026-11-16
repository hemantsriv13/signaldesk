"""Project Coach cloud copy against an in-memory stand-in for the two Supabase tables.

Mocked: these prove the laptop side only. Row-level security is checked on the live project by
scripts/verify_cloud.py, never by these tests."""
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx

from signaldesk import coach_sync, projects
from signaldesk.delivery import Delivery
from test_projects import NOW, analysis, setup

OWNER = "11111111-2222-4333-8444-555555555555"
BASE = "https://fixture.supabase.co"


class FakeCloud:
    def __init__(self, missing=False):
        self.tasks, self.responses, self.missing, self.calls = {}, {}, missing, []

    def handler(self, request: httpx.Request):
        self.calls.append(request)
        if self.missing:
            return httpx.Response(404, json={"message": "relation does not exist"})
        q = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
        table = self.tasks if request.url.path.endswith("project_tasks") else self.responses
        if request.method == "POST":
            row = json.loads(request.content)
            table[row["id"]] = row
            return httpx.Response(201)
        if request.method == "DELETE":
            cut = q["day"].removeprefix("lt.")
            for k in [k for k, v in table.items() if v["day"] < cut]:
                del table[k]
            return httpx.Response(204)
        if request.method == "GET":
            rows = [r for r in table.values() if r["owner_id"] == q["owner_id"].removeprefix("eq.") and r.get("imported_at") is None]
            return httpx.Response(200, json=rows)
        if request.method == "PATCH":
            table[q["id"].removeprefix("eq.")].update(json.loads(request.content))
            return httpx.Response(204)
        return httpx.Response(405)

    def answer(self, task_id, verdict, note="", rid=None):
        rid = rid or str(uuid.uuid4())
        self.responses[rid] = {"id": rid, "owner_id": OWNER, "task_id": task_id, "verdict": verdict, "note": note,
                               "answered_at": "2026-11-16T06:00:00+00:00", "imported_at": None}
        return rid


def client(cloud):
    return httpx.Client(transport=httpx.MockTransport(cloud.handler))


def run(cfg, db, cloud):
    return coach_sync.sync(cfg, db, client(cloud), BASE, {"apikey": "fixture"}, OWNER, NOW)


def test_push_sends_phone_safe_cards_only(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch, ("pushback", "signaldesk"))
    aid = analysis(db)
    db.run("UPDATE analyses SET output_json=?, inputs_json=? WHERE id=?",
           (json.dumps({"match": "weak", "summary": "s", "essential": [], "evidence": [{"req": "R", "facts": ["P1"], "note": "PROFILE_SECRET_NOTE"}]}),
            json.dumps({"facts_sent": ["P1"], "profile_version": "PROFILE_VERSION_X"}), aid))
    db.run("UPDATE jobs SET description_text=?", ("POSTING " + "x" * 9000,))
    case = analysis(db, "case_study")
    db.run("UPDATE articles SET content_text='FULL_ARTICLE_BODY'")
    projects.prepare(cfg, db, NOW)
    cloud = FakeCloud()
    run(cfg, db, cloud)
    assert cloud.tasks, "tasks were pushed"
    raw = json.dumps(cloud.tasks)
    for forbidden in ("PROFILE_SECRET_NOTE", "PROFILE_VERSION_X", "FULL_ARTICLE_BODY", "recorded_inputs", '"phone"', "SECRET_GRADER", "_export"):
        assert forbidden not in raw, forbidden
    job = next(t for t in cloud.tasks.values() if t["project"] == "signaldesk" and "Posting text" in t["payload"]["evidence"])
    assert len(job["payload"]["evidence"]) < 4200 and "shown on your laptop only" in job["payload"]["text"]
    assert all(t["owner_id"] == OWNER and t["status"] == "open" for t in cloud.tasks.values())
    assert case and any("The full article stays on your laptop" in t["payload"]["evidence"] for t in cloud.tasks.values())
    # The laptop's own API still has the full version.
    full = projects.today(db, NOW)
    assert "PROFILE_SECRET_NOTE" in json.dumps(full) and '"phone"' not in json.dumps(full)


def test_phone_answer_is_imported_as_human_phone_input_and_status_returns(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch)
    task = projects.prepare(cfg, db, NOW)["tasks"][0]
    cloud = FakeCloud()
    run(cfg, db, cloud)
    rid = cloud.answer(task["id"], "fail", "Kept the old answer")
    result = run(cfg, db, cloud)
    assert result["pulled"]["saved"] == 1
    saved = projects.today(db, NOW)["tasks"][0]["response"]
    assert saved == {"verdict": "fail", "note": "Kept the old answer", "at": "2026-11-16T06:00:00+00:00", "input_origin": "human", "via": "phone"}
    assert db.scalar("SELECT id FROM project_responses") == rid
    assert cloud.responses[rid]["import_result"] == "saved" and cloud.responses[rid]["imported_at"]
    assert cloud.tasks[task["id"]]["status"] == "answered"
    assert run(cfg, db, cloud)["pulled"] == {"saved": 0, "duplicate": 0, "conflict": 0, "rejected": 0}


def test_conflicting_duplicate_and_invalid_phone_answers(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch)
    tasks = projects.prepare(cfg, db, NOW)["tasks"]
    projects.respond(db, tasks[0]["id"], "pass", "desktop")
    cloud = FakeCloud()
    conflict = cloud.answer(tasks[0]["id"], "fail", "phone")
    same = cloud.answer(tasks[1]["id"], "pass", "")
    bogus = cloud.answer(str(uuid.uuid4()), "pass")
    reminder_less = cloud.answer(tasks[2]["id"], "agree")          # not a verdict this task allows
    counts = run(cfg, db, cloud)["pulled"]
    assert counts == {"saved": 1, "duplicate": 0, "conflict": 1, "rejected": 2}
    assert db.scalar("SELECT verdict FROM project_responses WHERE task_id=?", (tasks[0]["id"],)) == "pass"
    assert db.get_setting("coach_conflicts")[0]["kept"] == "pass"
    assert {cloud.responses[r]["import_result"] for r in (conflict, same, bogus, reminder_less)} == {"conflict", "saved", "rejected"}
    # A retried identical upload of an already imported answer is harmless.
    cloud.responses[same]["imported_at"] = None
    assert run(cfg, db, cloud)["pulled"]["duplicate"] == 1


def test_missing_cloud_tables_do_not_break_briefing_sync(engine, monkeypatch):
    cfg, _ = setup(engine.cfg.home, monkeypatch)
    engine.cfg.project = cfg.project
    projects.prepare(engine.cfg, engine.db, datetime.now(timezone.utc).astimezone())
    cloud = FakeCloud(missing=True)
    env = {"SIGNALDESK_SUPABASE_URL": BASE, "SIGNALDESK_SUPABASE_SERVICE_KEY": "sb_secret_fixture", "SIGNALDESK_OWNER_ID": OWNER}
    d = Delivery(engine, env=env, client=client(cloud))
    d.sync_projects()
    status = engine.db.get_setting("coach_sync_status")
    assert status["state"] == "failed" and "project_coach.sql" in status["message"] and "fixture" not in status["message"]


def test_auto_prepare_is_off_by_default_and_prepares_once_when_on(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch)
    cloud = FakeCloud()
    run(cfg, db, cloud)
    assert not db.scalar("SELECT COUNT(*) FROM project_days") and not cloud.tasks
    cfg.coach.auto_prepare = True
    run(cfg, db, cloud)
    run(cfg, db, cloud)
    assert db.scalar("SELECT COUNT(*) FROM project_days") == 1 and len(cloud.tasks) == 3


def test_cards_prepared_before_phone_variants_never_send_laptop_evidence():
    old = {"type": "judge_analysis", "title": "Review: Role", "verdicts": ["agree"],
           "text": "Match: weak\n\nEvidence claimed from your profile:\n• R: PROFILE_NOTE (facts P1)\n• S: OTHER_NOTE (facts P2)\n\nGaps:\n• none",
           "evidence": "Source text:\nFULL POSTING\n\nRecorded inputs:\nPROFILE_VERSION"}
    card = projects.phone_card(old)
    raw = json.dumps(card)
    assert "PROFILE_NOTE" not in raw and "OTHER_NOTE" not in raw and "FULL POSTING" not in raw and "PROFILE_VERSION" not in raw
    assert "Gaps:" in card["text"] and "laptop" in card["evidence"]
