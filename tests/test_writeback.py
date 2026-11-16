"""Write-back into project clones, with real git on throwaway repositories (a bare 'GitHub' remote and a
clone). The repo's own checks are replaced by small commands; the real ones run only on your clones."""
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from signaldesk import projects, writeback
from signaldesk.config import ProjectConfig, load_config
from signaldesk.db import DB
from test_projects import NOW, tutor_sheet


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout.strip()


def make_repo(tmp_path, name, fill):
    remote = tmp_path / f"{name}-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    clone = tmp_path / name
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True, capture_output=True)
    git(clone, "config", "user.name", "Owner Fixture"); git(clone, "config", "user.email", "owner@example.invalid")
    git(clone, "config", "core.autocrlf", "false")           # exact bytes, whatever this machine's git does
    git(clone, "checkout", "-q", "-b", "main")
    fill(clone)
    (clone / "README.md").write_text("x\nthe held-out Opus false pass below is still present.\n", encoding="utf-8")
    git(clone, "add", "-A"); git(clone, "commit", "-q", "-m", "fixture")
    git(clone, "push", "-q", "origin", "main")
    return clone, remote


def pushback_files(clone):
    folder = clone / "labels"; folder.mkdir()
    rows = [projects.LABEL_COLUMNS] + [[f"r{i}", "test", "m", "p", "s", "Keep 12.", "n", "Say 15,\nplease", "It is 12.", "pass" if i == 0 else "", ""] for i in range(3)]
    out = io.StringIO(newline=""); csv.writer(out, lineterminator="\r\n").writerows(rows)
    (folder / "sheet.csv").write_bytes(b"\xef\xbb\xbf" + out.getvalue().encode())
    (folder / "sheet_data.md").write_text("## p\nThe count is 12.\n", encoding="utf-8")


def setup(tmp_path, monkeypatch, kind="pushback"):
    clone, remote = make_repo(tmp_path, kind, pushback_files if kind == "pushback" else (lambda c: tutor_sheet(c)))
    cfg = load_config(tmp_path / "home")
    cfg.project.append(ProjectConfig(kind, str(clone), kind))
    db = DB(cfg.db_path)
    monkeypatch.setattr(projects, "git_facts", lambda root: {"branch": "main", "last_commit_at": NOW.isoformat(), "dirty": False, "git_error": None})
    monkeypatch.setattr(writeback, "checks", lambda kind, wt, py, files: [("fixture check", [sys.executable, "-c", "print('ok')"])])
    return cfg, db, clone, remote


def answer_all(cfg, db, verdicts):
    tasks = projects.prepare(cfg, db, NOW)["tasks"]
    for t, v in zip(tasks, verdicts):
        projects.respond(db, t["id"], v, "Checked, line one\nline two")
    return tasks


def test_nothing_is_written_until_the_repo_is_approved(tmp_path, monkeypatch):
    cfg, db, clone, remote = setup(tmp_path, monkeypatch)
    answer_all(cfg, db, ["fail"])
    [r] = writeback.run(cfg, db)
    assert r["status"] == "needs-approval" and "[writeback] write" in r["message"]
    assert "phone-review" not in git(clone, "branch", "-a")


def test_approved_write_changes_only_human_cells_on_phone_review_and_does_not_push(tmp_path, monkeypatch):
    cfg, db, clone, remote = setup(tmp_path, monkeypatch)
    before = (clone / "labels" / "sheet.csv").read_bytes()
    answer_all(cfg, db, ["fail", "unclear"])
    cfg.writeback.write = ["pushback"]
    [r] = writeback.run(cfg, db)
    assert r["status"] == "written" and r["written"] == 2 and not r["pushed"], r
    # Your open clone: same branch, same file, no changes.
    assert git(clone, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert (clone / "labels" / "sheet.csv").read_bytes() == before and git(clone, "status", "--porcelain") == ""
    # The worktree commit: one file, only human columns, format kept (BOM, CRLF, quoted newlines).
    wt = cfg.home / "project-worktrees" / "pushback"
    assert git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "phone-review"
    assert git(wt, "show", "--name-only", "--format=", "HEAD") == "labels/sheet.csv"
    msg = git(wt, "log", "-1", "--format=%an <%ae>%n%B")
    assert msg.startswith("Owner Fixture <owner@example.invalid>") and "from SignalDesk review" in msg
    after = (wt / "labels" / "sheet.csv").read_bytes()
    assert after.startswith(b"\xef\xbb\xbf") and b"\r\n" in after
    old = list(csv.reader(io.StringIO(before.decode("utf-8-sig"), newline="")))
    new = list(csv.reader(io.StringIO(after.decode("utf-8-sig"), newline="")))
    li, ni = old[0].index("human_label"), old[0].index("human_note")
    for o, n in zip(old, new):
        assert [x for i, x in enumerate(o) if i not in (li, ni)] == [x for i, x in enumerate(n) if i not in (li, ni)]
    assert [r[li] for r in new[1:]] == ["pass", "fail", "unclear"] and new[2][ni] == "Checked, line one line two"
    # Not pushed: the remote has main only, unchanged.
    assert "phone-review" not in git(remote, "branch") and git(remote, "rev-parse", "main") == git(clone, "rev-parse", "main")
    # Running again writes nothing more.
    assert writeback.run(cfg, db) == [] or writeback.write_project(cfg, db, cfg.project[0])["status"] == "nothing"


def test_push_goes_to_phone_review_only_and_main_on_github_is_untouched(tmp_path, monkeypatch):
    cfg, db, clone, remote = setup(tmp_path, monkeypatch)
    main_before = git(remote, "rev-parse", "main")
    answer_all(cfg, db, ["fail"])
    cfg.writeback.write = cfg.writeback.push = ["pushback"]
    [r] = writeback.run(cfg, db)
    assert r["pushed"] and r["status"] == "written"
    assert git(remote, "rev-parse", "main") == main_before
    assert git(remote, "rev-parse", "phone-review") == git(cfg.home / "project-worktrees" / "pushback", "rev-parse", "HEAD")
    assert db.scalar("SELECT COUNT(*) FROM project_writes WHERE pushed_at IS NOT NULL") == 1


def test_uncommitted_work_in_the_clone_stops_everything(tmp_path, monkeypatch):
    cfg, db, clone, remote = setup(tmp_path, monkeypatch)
    answer_all(cfg, db, ["fail"])
    (clone / "scratch.txt").write_text("work in progress", encoding="utf-8")
    cfg.writeback.write = ["pushback"]
    [r] = writeback.run(cfg, db)
    assert r["status"] == "stopped" and "uncommitted work" in r["message"]
    assert not (cfg.home / "project-worktrees").exists() and db.scalar("SELECT COUNT(*) FROM project_writes") == 0


def test_failed_repo_check_commits_nothing_and_discards_the_edit(tmp_path, monkeypatch):
    cfg, db, clone, remote = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(writeback, "checks", lambda *a: [("fixture tests", [sys.executable, "-c", "raise SystemExit(1)"])])
    answer_all(cfg, db, ["fail"])
    cfg.writeback.write = ["pushback"]
    [r] = writeback.run(cfg, db)
    wt = cfg.home / "project-worktrees" / "pushback"
    assert r["status"] == "stopped" and "fixture tests failed" in r["message"]
    assert git(wt, "status", "--porcelain") == "" and git(wt, "rev-parse", "HEAD") == git(clone, "rev-parse", "main")
    assert db.scalar("SELECT COUNT(*) FROM project_writes") == 0          # retried next time


def test_existing_human_label_is_never_overwritten(tmp_path, monkeypatch):
    cfg, db, clone, remote = setup(tmp_path, monkeypatch)
    answer_all(cfg, db, ["fail"])
    # Someone labelled the row in the repo after collection.
    path = clone / "labels" / "sheet.csv"
    rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))
    rows[2][rows[0].index("human_label")] = "pass"                 # r1, the row this task asked about
    out = io.StringIO(newline=""); csv.writer(out, lineterminator="\r\n").writerows(rows)
    path.write_bytes(b"\xef\xbb\xbf" + out.getvalue().encode())
    git(clone, "commit", "-qam", "labelled elsewhere")
    cfg.writeback.write = ["pushback"]
    [r] = writeback.run(cfg, db)
    assert r["conflicts"] == 1 and r["written"] == 0 and "conflict" in r["message"]
    assert db.scalar("SELECT result FROM project_writes") == "conflict"


def test_nextword_verdict_and_note_lines_only(tmp_path, monkeypatch):
    cfg, db, clone, remote = setup(tmp_path, monkeypatch, "nextword")
    sheet = clone / "evals/local_ai/human_review/fixture.md"
    sheet.write_bytes(sheet.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")); git(clone, "commit", "-q", "--allow-empty", "-am", "crlf")
    before = sheet.read_bytes()
    answer_all(cfg, db, ["wrong"])
    cfg.writeback.write = ["nextword"]
    [r] = writeback.run(cfg, db)
    assert r["written"] == 1, (r["status"], r["message"])
    after = (cfg.home / "project-worktrees/nextword/evals/local_ai/human_review/fixture.md").read_bytes()
    changed = [(a, b) for a, b in zip(before.split(b"\r\n"), after.split(b"\r\n")) if a != b]
    assert changed == [(b"Verdict: ", b"Verdict: wrong"), (b"Note: ", b"Note: Checked, line one line two")]
    assert after.count(b"\r\n") == before.count(b"\r\n")


def test_allow_list_rejects_code_probes_and_run_files():
    assert writeback.outside_allow_list("pushback", ["labels/sheet.csv"]) == []
    for bad in ("pushback/cli.py", "probes/x.yaml", "runs/r.json", "reports/grader-agreement.md", "labels/../cli.py", "README.md"):
        assert writeback.outside_allow_list("pushback", [bad]) == [bad]
    assert writeback.outside_allow_list("nextword", ["evals/local_ai/human_review/key.json", "evals/local_ai/results/x.json"]) != []


def test_signaldesk_answers_are_never_committed(tmp_path, monkeypatch):
    cfg = load_config(tmp_path / "home")
    db = DB(cfg.db_path)
    r = writeback.write_project(cfg, db, ProjectConfig("signaldesk", str(tmp_path), "signaldesk"))
    assert r["status"] == "skipped"
