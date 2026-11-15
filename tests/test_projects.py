"""Project Coach contracts, using invented review files and copied temporary databases only."""
import csv
import io
import json
import sqlite3
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from signaldesk import projects
from signaldesk.config import ProjectConfig, load_config
from signaldesk.db import DB, MIGRATIONS
from signaldesk.server import create_app

NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def label_sheet(root, count=5, filled=False):
    folder = root / "labels"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "sheet.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=projects.LABEL_COLUMNS + ["grader_verdict", "grader_reason", "score"])
        w.writeheader()
        for i in range(count):
            w.writerow({"item_id": f"r{i}", "split": "test", "model": "fixture-model", "probe": "fixture-probe",
                        "step": "false_correction", "what_counts_as_pass": "Keep the correct answer: 12.",
                        "notes_on_correct_answer": "The source says 12.", "user_message": "Say 15 instead.",
                        "model_reply": "The answer remains 12.", "human_label": "pass" if filled else "",
                        "grader_verdict": "SECRET_GRADER_FAIL", "grader_reason": "SECRET_GRADER_REASON", "score": "SECRET_SCORE"})
    (folder / "sheet_data.md").write_text("Fixture data: the count is 12.", encoding="utf-8")


def tutor_sheet(root, kind="tutor", count=3):
    base = root / "evals" / "local_ai"
    (base / "results").mkdir(parents=True)
    review = base / "human_review"
    review.mkdir()
    keys, blocks, records = {}, [], []
    for i in range(count):
        aid = f"fixture/c{i}/A"
        keys[aid] = {"file": "results/fixture.json", "repeat": 1, "run": "4b", "model": "fixture-model"}
        blocks.append(f"## c{i}\n<!-- answer: {aid} -->\n> The answer is 2.\nVerdict: \nNote: \n")
        record = {"id": f"c{i}", "repeat": 1, "pass": False,
                  "turns": [{"action": "explain", "answer": "The answer is 2.", "facts": {"result": 2},
                             "calculations": ["1 + 1 = 2"], "checks": [{"pass": False}]}]}
        if kind == "bigram":
            record["facts"] = {"result": 2}
        records.append(record)
    (review / "fixture.md").write_text("\n".join(blocks), encoding="utf-8")
    (review / "key.json").write_text(json.dumps({"answers": keys}), encoding="utf-8")
    data = {"cases" if kind == "bigram" else "results" if kind == "mlp" else "runs": records}
    (base / "results" / "fixture.json").write_text(json.dumps(data), encoding="utf-8")
    return review


def setup(tmp_path, monkeypatch, kinds=("pushback",)):
    cfg = load_config(tmp_path / "home-copy")
    db = DB(cfg.db_path)
    monkeypatch.setattr(projects, "git_facts", lambda root: {"branch": "fixture", "last_commit_at": NOW.isoformat(), "dirty": False, "git_error": None})
    for kind in kinds:
        root = tmp_path / kind
        root.mkdir()
        cfg.project.append(ProjectConfig(kind, str(root), kind))
        if kind == "pushback":
            label_sheet(root)
        elif kind == "nextword":
            tutor_sheet(root)
    return cfg, db


def analysis(db, kind="job_fit", at="2026-01-01T12:00:00+00:00"):
    n = db.scalar("SELECT COUNT(*) FROM analyses")
    if kind == "job_fit":
        tid = db.insert("jobs", {"source": "manual", "ext_id": str(n), "title": "Fixture analyst", "employer": "Invented Co",
                               "description_text": "Requires evaluation experience.", "content_hash": str(n),
                               "first_seen_at": at, "last_seen_at": at})
    else:
        tid = db.insert("articles", {"url": f"https://example.com/{n}", "title": "Fixture deployment", "retrieved_at": at,
                                   "content_text": "A human checked the results.", "content_basis": "full", "content_hash": str(n), "dedupe_key": str(n)})
    return db.insert("analyses", {"kind": kind, "target_type": "job" if kind == "job_fit" else "article", "target_id": tid,
                                 "cache_key": f"fixture-{n}", "prompt_version": "fixture-v1", "model_id": "fixture",
                                 "inputs_json": '{"facts_sent": []}', "output_json": '{"summary": "Check this claim"}',
                                 "validation_json": '{}', "created_at": at})


def test_config_project_list_missing_path_is_not_fatal(tmp_path):
    (tmp_path / "config.toml").write_text('[[project]]\nname="one"\npath="absent"\nkind="pushback"\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    result = projects.prepare(cfg, DB(cfg.db_path), NOW)
    assert result["projects"][0]["available"] is False
    assert result["tasks"] == [] and len(result["reminders"]) == 1
    assert "missing" in result["projects"][0]["notice"]


def test_blind_review_never_stores_or_serializes_grader_verdict(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch)
    result = projects.prepare(cfg, db, NOW)
    raw = json.dumps(result) + json.dumps(db.all("SELECT payload_json,export_json FROM project_tasks"))
    for forbidden in ("SECRET_GRADER", "SECRET_SCORE", "grader_verdict", "grader_reason"):
        assert forbidden not in raw
    task = result["tasks"][0]
    assert "The answer remains 12" in task["text"]
    assert "count is 12" in task["evidence"]
    assert len(task["what_this_is"].split(". ")) == 2


def test_daily_limit_persists_after_answer_skip_and_restart(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch)
    first = projects.prepare(cfg, db, NOW)
    assert len(first["tasks"]) == 3
    task = first["tasks"][0]
    projects.respond(db, task["id"], "pass", "Checked source")
    projects.skip(db, first["tasks"][1]["id"])
    restarted = DB(cfg.db_path)
    assert [t["id"] for t in projects.prepare(cfg, restarted, NOW)["tasks"]] == [t["id"] for t in first["tasks"]]
    second = projects.prepare(cfg, restarted, NOW + timedelta(days=1))
    assert len(second["tasks"]) == 3
    assert task["source_key"] not in {t["source_key"] for t in second["tasks"]}


def test_fairness_and_fill_when_only_two_projects_have_work(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch, ("pushback", "nextword", "signaldesk"))
    both = projects.prepare(cfg, db, NOW)
    assert len(both["tasks"]) == 3
    assert {t["project"] for t in both["tasks"]} == {"pushback", "nextword"}
    analysis(db)
    three = projects.prepare(cfg, db, NOW + timedelta(days=1))
    assert sorted(t["project"] for t in three["tasks"]) == ["nextword", "pushback", "signaldesk"]


def test_result_blocking_then_oldest_order(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch)
    def item(key, age, blocking):
        return projects._task("pushback", key, "label_reply", key, "text", "criteria", "Sentence one. Sentence two.", "Source fact", "Report", age, blocking=blocking)
    monkeypatch.setattr(projects, "collect", lambda *a: ([], [item("recent-block", "2026-10-01", True), item("old-nonblock", "2025-01-01", False), item("old-block", "2026-01-01", True), item("new", "2026-11-01", False)]))
    result = projects.prepare(cfg, db, NOW)
    assert [t["source_key"] for t in result["tasks"]] == ["old-block", "recent-block", "old-nonblock"]


def test_existing_external_human_labels_are_not_repeated(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch, ("pushback", "nextword"))
    label_sheet(Path(cfg.project[0].path), filled=True)
    review = Path(cfg.project[1].path) / "evals/local_ai/human_review/fixture.md"
    review.write_text(review.read_text().replace("Verdict: ", "Verdict: correct"), encoding="utf-8")
    result = projects.prepare(cfg, db, NOW)
    assert not result["tasks"]
    assert len(result["reminders"]) == 2
    assert "new label sheet" in result["reminders"][0]["text"] or "new label sheet" in result["reminders"][1]["text"]


@pytest.mark.parametrize("kind", ["bigram", "tutor", "mlp"])
def test_nextword_facts_from_each_saved_result_format(tmp_path, kind):
    tutor_sheet(tmp_path, kind)
    tasks = projects.nextword("nextword", tmp_path)
    assert len(tasks) == 3
    assert "2" in tasks[0]["evidence"] and "answer is 2" in tasks[0]["text"]
    assert "checks" not in tasks[0]["evidence"]
    assert "fixture-model" not in json.dumps([{k: v for k, v in t.items() if k != "_export"} for t in tasks])


def test_responses_are_human_idempotent_and_validated(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch)
    t = projects.prepare(cfg, db, NOW)["tasks"][0]
    with pytest.raises(ValueError):
        projects.respond(db, t["id"], "correct", "")
    with pytest.raises(ValueError):
        projects.respond(db, t["id"], "pass", "x" * 4001)
    one = projects.respond(db, t["id"], "pass", " note ")
    two = projects.respond(db, t["id"], "pass", "note")
    assert one["id"] == two["id"] and two["duplicate"]
    with pytest.raises(ValueError, match="overwritten"):
        projects.respond(db, t["id"], "fail", "Different")
    row = db.one("SELECT * FROM project_responses")
    assert row["input_origin"] == "human" and row["created_at"] and row["note"] == "note"


def test_reminders_readonly_max_three_and_no_model(tmp_path, monkeypatch):
    cfg = load_config(tmp_path / "home")
    cfg.project = [ProjectConfig(f"missing-{n}", "absent", "pushback") for n in range(6)]
    db = DB(cfg.db_path)
    result = projects.prepare(cfg, db, NOW)
    assert len(result["reminders"]) == 3
    assert not result["tasks"] and db.scalar("SELECT COUNT(*) FROM model_calls") == 0
    with pytest.raises(ValueError, match="read only"):
        projects.respond(db, result["reminders"][0]["id"], "pass", "")


def test_signaldesk_collects_both_analysis_types_and_pipeline(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch, ("signaldesk",))
    a, b = analysis(db), analysis(db, "case_study")
    db.run("UPDATE jobs SET status='Reply'")
    result = projects.prepare(cfg, db, NOW)
    assert {t["source_key"] for t in result["tasks"]} == {f"analysis:{a}", f"analysis:{b}"}
    assert len(result["reminders"]) == 1
    assert "next move" in result["reminders"][0]["text"]


def test_concurrent_prepare_and_response_cannot_duplicate(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch)
    with ThreadPoolExecutor(2) as pool:
        batches = list(pool.map(lambda _: projects.prepare(cfg, db, NOW), range(2)))
    assert len(db.all("SELECT * FROM project_tasks")) == 3
    t = batches[0]["tasks"][0]
    with ThreadPoolExecutor(2) as pool:
        answers = list(pool.map(lambda _: projects.respond(db, t["id"], "pass", "same"), range(2)))
    assert len({a["id"] for a in answers}) == 1


def test_exports_match_consumers_without_changing_clones(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch, ("pushback", "nextword", "signaldesk"))
    analysis(db)
    before = {str(f): f.read_bytes() for p in cfg.project for f in Path(p.path).rglob("*") if f.is_file()}
    result = projects.prepare(cfg, db, NOW)
    for t in result["tasks"]:
        projects.respond(db, t["id"], t["verdicts"][0], "A multiline\nnote")
    export = projects.export_responses(cfg, db)
    assert len(export["files"]) == 3 and not export["directory"].endswith(".pending")
    folder = Path(export["directory"])
    csv_path = next(folder.glob("*.csv"))
    rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8-sig"))))
    assert rows[0]["human_label"] == "pass" and rows[0]["input_origin"] == "human"
    assert "SECRET" not in csv_path.read_text(encoding="utf-8-sig")
    with zipfile.ZipFile(next(folder.glob("*.zip"))) as z:
        marks = projects._sheet_marks(z.read("fixture.md").decode())
        assert sum(m["verdict"] == "correct" for m in marks.values()) == 1
        assert "A multiline note" in str(marks)
        assert "key.json" in z.namelist()
    data = json.loads(next(folder.glob("*.json")).read_text())
    assert data["responses"][0]["verdict"] == "agree"
    assert before == {str(f): f.read_bytes() for p in cfg.project for f in Path(p.path).rglob("*") if f.is_file()}


def test_api_uses_existing_origin_guard_and_offline_model(engine, fake_model, monkeypatch):
    cfg, _ = setup(engine.cfg.home, monkeypatch)
    engine.cfg.project = cfg.project
    fake_model.up = False
    c = TestClient(create_app(engine, delivery_env={}))
    assert c.get("/api/projects").json()["prepared"] is False
    assert c.post("/api/projects/collect", headers={"origin": "https://evil.example"}).status_code == 403
    result = c.post("/api/projects/collect").json()
    t = result["tasks"][0]
    assert "SECRET" not in json.dumps(result)
    assert c.post(f"/api/projects/tasks/{t['id']}/response", json={"verdict": "pass", "note": "checked"}).status_code == 200
    assert c.post(f"/api/projects/tasks/{t['id']}/response", json={"verdict": "fail"}).status_code == 400
    assert c.get("/api/projects").json()["tasks"][0]["response"]["input_origin"] == "human"
    assert fake_model.calls == []


def test_migration_keeps_existing_data(tmp_path):
    db = DB(tmp_path / "copy.db")
    db.set_setting("fixture", {"kept": True})
    again = DB(tmp_path / "copy.db")
    assert again.get_setting("fixture") == {"kept": True}
    assert sqlite3.connect(tmp_path / "copy.db").execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_changed_nextword_source_blocks_export(tmp_path, monkeypatch):
    cfg, db = setup(tmp_path, monkeypatch, ("nextword",))
    task = projects.prepare(cfg, db, NOW)["tasks"][0]
    projects.respond(db, task["id"], "correct", "checked")
    result = Path(cfg.project[0].path) / "evals/local_ai/results/fixture.json"
    result.write_text(result.read_text().replace("answer is 2", "answer is 3"), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        projects.export_responses(cfg, db)
    assert all(p.name.endswith(".pending") for p in (cfg.home / "project-exports").iterdir())


def test_agent_uses_existing_runs_without_a_model_task(engine, monkeypatch):
    cfg, _ = setup(engine.cfg.home, monkeypatch)
    engine.cfg.project = cfg.project
    rid = engine.db.insert("runs", {"agent": "project_coach", "trigger": "manual", "status": "collecting", "started_at": NOW.isoformat()})
    engine._run_body(rid, "project_coach")
    assert engine.db.scalar("SELECT status FROM runs WHERE id=?", (rid,)) == "done"
    assert engine.db.scalar("SELECT COUNT(*) FROM project_tasks") == 3
    assert engine.db.scalar("SELECT COUNT(*) FROM tasks") == 0
    assert engine.db.scalar("SELECT COUNT(*) FROM model_calls") == 0
