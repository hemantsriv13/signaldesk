"""The human-review kit (eval/review.py), on synthetic fixtures only: invented employers, an invented
profile and fake model replies. No real data folder is read; no verdict here is a real judgement."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from eval import review
from signaldesk import collect

from conftest import add_company, drain, greenhouse

POSTING = ("<p>About the role: build product analytics for an invented marketplace.</p>"
           "<p>Requirements:</p><ul><li>Strong SQL and Python.</li><li>Present findings to business stakeholders.</li></ul>"
           "<p>Preferred:</p><ul><li>Experience evaluating AI features is a plus.</li></ul>")
FIT_REPLY = {"essential": [{"req": "SQL and Python", "quote": "Strong SQL and Python."},
                           {"req": "Stakeholder communication", "quote": "Present findings to business stakeholders."}],
             "preferred": [{"req": "AI evaluation", "quote": "Experience evaluating AI features is a plus."}],
             "evidence": [{"req": "SQL and Python", "facts": ["P5"], "note": "uses SQL and Python"},
                          {"req": "Stakeholders", "facts": ["P4", "P99"], "note": "presented to stakeholders"}],
             "gaps": ["No stated AI evaluation work"], "unknowns": ["Team size"], "match": "potential match",
             "summary": "Analytics fit; AI evaluation unproven.", "injection_seen": False}


def saved_analysis(engine, boards, fake_model, ext=901, title="Product Analyst"):
    add_company(engine.db, "Lanternby Commerce (fixture)", f"lantern{ext}")
    boards.routes[f"https://boards-api.greenhouse.io/v1/boards/lantern{ext}/"] = (200, greenhouse([{"id": ext, "title": title, "content": POSTING}]))
    collect.collect_jobs(engine.db, engine.fetcher, engine.profiles.prefs())
    jid = engine.db.scalar("SELECT id FROM jobs WHERE ext_id = ?", (f"gh:{ext}",))
    fake_model.replies["Lanternby Commerce"] = FIT_REPLY
    engine.analyse("job_fit", jid)
    drain(engine)
    assert engine.db.scalar("SELECT COUNT(*) FROM analyses WHERE kind = 'job_fit' AND target_id = ?", (jid,)) == 1
    return jid


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_export_writes_the_sheet_to_the_data_folder_with_what_the_model_saw(engine, boards, fake_model):
    jid = saved_analysis(engine, boards, fake_model)
    before = digest(engine.cfg.db_path)
    path = review.export(engine.cfg.home, 10, [])
    assert path.parent == engine.cfg.evals_dir and path.suffix == ".csv"
    assert review.REPO not in path.resolve().parents
    assert digest(engine.cfg.db_path) == before                      # read-only: the app's database is unchanged
    (r,) = read(path)
    assert list(r) == review.COLUMNS
    assert r["item"] == f"saved-job-{jid}" and r["model"] == engine.cfg.model.model_id and r["source"] == "app database"
    # The requirement text is the exact excerpt sent, and the facts are the ones sent, with their text.
    sent = fake_model.calls[-1]["messages"][1]["content"]
    assert r["requirement_text_sent"] == review.source_text(sent) and "Strong SQL and Python." in r["requirement_text_sent"]
    assert r["requirement_text_status"].startswith("rebuilt; same length")
    assert "P5: Uses SQL, Python and BI tools." in r["profile_facts_sent"]
    assert "Strong SQL and Python." in r["essential"] and "AI evaluation" in r["preferred"] and "quote found" in r["preferred"]
    assert "- P5: SQL and Python" in r["cited_facts"]
    assert "P99" not in r["cited_facts"]                             # an invented fact id was removed by validation
    assert r["gaps"] == "- No stated AI evaluation work" and r["unknowns"] == "- Team size" and r["match_label"] == "potential match"
    assert "cited no profile fact" not in r["checks_notes"]
    assert all(r[c] == "" for c in review.VERDICT_COLUMNS)           # never pre-filled


def test_export_says_when_the_job_changed_after_the_analysis(engine, boards, fake_model):
    jid = saved_analysis(engine, boards, fake_model)
    engine.db.update("jobs", jid, {"description_text": "Requirements: completely different text now."})
    (r,) = read(review.export(engine.cfg.home, 10, []))
    assert r["requirement_text_status"].startswith("REBUILT FROM TODAY'S JOB TEXT")


def test_export_takes_the_most_recent_n(engine, boards, fake_model):
    for ext in (911, 912, 913):
        saved_analysis(engine, boards, fake_model, ext=ext, title=f"Product Analyst {ext}")
    rows = read(review.export(engine.cfg.home, 2, []))
    assert len(rows) == 2 and [r["review_id"] for r in rows] == ["R001", "R002"]


def test_export_refuses_to_write_inside_the_repository(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "REPO", tmp_path)
    with pytest.raises(review.ReviewError, match="outside the repository"):
        review.export(tmp_path / "data", 0, [str(run_file(tmp_path, "fixture-small", [fit_result("saved-job-1", "weak match")]))], include_saved=False)


def run_file(folder: Path, model: str, results: list[dict]) -> Path:
    p = folder / f"model-{model}.json"
    p.write_text(json.dumps({"model": model, "at": "20261114-090000", "results": results}), encoding="utf-8")
    return p


def fit_result(item: str, match: str, facts=("P1",)) -> dict:
    out = {**FIT_REPLY, "match": match, "essential": [{"req": "SQL", "quote": "Strong SQL and Python.", "quote_found": True}], "preferred": [],
           "evidence": [{"req": "SQL", "facts": list(facts), "note": "n"}]}
    return {"kind": "job_fit", "item": item, "title": f"Invented role {item}", "ok": True, "output": out, "validation": {"notes": []},
            "sent": {"requirements": "Requirements: Strong SQL and Python.", "facts": [{"id": "P1", "text": "Invented fact."}], "employer": "Lanternby (fixture)"}}


def test_two_models_on_the_same_items_are_scored_side_by_side(tmp_path):
    home = tmp_path / "data"
    small = run_file(tmp_path, "fixture-4b", [fit_result("saved-job-1", "potential match"), fit_result("saved-job-2", "weak match"),
                                             {"kind": "reading_card", "item": "x", "ok": True}])
    large = run_file(tmp_path, "fixture-9b", [fit_result("saved-job-1", "weak match"), fit_result("saved-job-3", "not a match")])
    old = run_file(tmp_path, "fixture-old", [{k: v for k, v in fit_result("saved-job-4", "unknown").items() if k != "sent"}])
    path = review.export(home, 0, [str(small), str(large), str(old)], include_saved=False)
    rows = read(path)
    assert [(r["item"], r["model"]) for r in rows] == [("saved-job-1", "fixture-4b"), ("saved-job-1", "fixture-9b"), ("saved-job-2", "fixture-4b"),
                                                       ("saved-job-3", "fixture-9b"), ("saved-job-4", "fixture-old")]
    assert rows[0]["requirement_text_status"] == "recorded by the run" and rows[-1]["requirement_text_status"].startswith("NOT RECORDED")

    # Synthetic verdicts, typed by the test (not a real review).
    fill = {("saved-job-1", "fixture-4b"): ("too generous", "partly"), ("saved-job-1", "fixture-9b"): ("Right", "yes"),
            ("saved-job-2", "fixture-4b"): ("right", "maybe"), ("saved-job-3", "fixture-9b"): ("", "")}
    for r in rows:
        r["verdict_match_label"], r["verdict_cited_facts"] = fill.get((r["item"], r["model"]), ("too harsh", "no"))
    write(path, rows)
    report, out = review.score(path)
    assert out.parent == path.parent and out.read_text(encoding="utf-8") == report
    assert "| fixture-4b | 2 | 1 | 1 | 0 | 0 | 0 |" in report             # right, too generous, too harsh, not reviewed, invalid
    assert "| fixture-9b | 2 | 1 | 0 | 0 | 1 | 0 |" in report
    assert "| fixture-4b | 2 | 0 | 1 | 0 | 0 | 1 |" in report             # facts: "maybe" is invalid
    assert 'R003 (saved-job-2, fixture-4b): verdict_cited_facts = "maybe"' in report
    assert "| saved-job-1 | Invented role saved-job-1 | potential match / too generous / partly | weak match / right / yes |" in report
    assert "you rated the label right: fixture-4b 0, fixture-9b 1. Same verdict for both models on 0." in report
    assert "saved-job-2 |" not in report.split("## Same item")[1].split("##")[0]   # only items both models answered


def test_score_refuses_a_file_that_is_not_a_review_sheet(tmp_path):
    p = tmp_path / "other.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(review.ReviewError, match="not a review sheet"):
        review.score(p)


def test_command_line_export_and_score(tmp_path, capsys):
    small = run_file(tmp_path, "fixture-4b", [fit_result("saved-job-1", "potential match")])
    assert review.main(["export", "--home", str(tmp_path / "data"), "--no-saved", "--run", str(small)]) == 0
    sheet = next((tmp_path / "data" / "evals").glob("review-*.csv"))
    assert review.main(["score", str(sheet)]) == 0
    assert "| fixture-4b | 1 | 0 | 0 | 0 | 1 | 0 |" in capsys.readouterr().out



def test_model_runs_record_exactly_what_each_job_fit_request_carried(tmp_path, monkeypatch, fake_model):
    """`run_eval model` (used for the 4B and 9B runs) keeps the requirement text and facts it sent."""
    import httpx

    from eval import run_eval
    from signaldesk.llm import LocalModel
    monkeypatch.setenv("SIGNALDESK_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(run_eval, "LocalModel", lambda cfg: LocalModel(cfg, transport=httpx.MockTransport(fake_model.handler)))
    assert run_eval.model(None, 0) == 0
    run = json.loads(next((tmp_path / "data" / "evals").glob("model-*.json")).read_text(encoding="utf-8"))
    fits = [r for r in run["results"] if r["kind"] == "job_fit"]
    prompts = [c["messages"][1]["content"] for c in fake_model.calls if "JOB:" in c["messages"][1]["content"]]
    assert fits and len(prompts) == len(fits)
    for r, prompt in zip(fits, prompts):
        assert r["sent"]["requirements"] == review.source_text(prompt) and r["sent"]["requirements"]
        assert all(f"{f['id']}: {f['text']}" in prompt for f in r["sent"]["facts"])
    rows = read(review.export(tmp_path / "data", 0, [str(next((tmp_path / "data" / "evals").glob("model-*.json")))], include_saved=False))
    assert {r["requirement_text_status"] for r in rows} == {"recorded by the run"}
