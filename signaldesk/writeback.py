"""Write your answers back into the project clones, on a `phone-review` branch, for you to merge.

Safety rules (each is enforced here and tested):
- A repo is written only when its name is in [writeback] write, and pushed only when it is also in
  [writeback] push. The branch is always `phone-review`; main is never checked out, committed or pushed.
- Work happens in a separate git worktree under the data home, so your open clone's checked-out
  branch and files are never changed.
- Only allow-listed review files change, and only the human columns in them: pushback
  labels/*.csv (human_label, human_note); nextword evals/local_ai/human_review/*.md (Verdict, Note).
  Anything else changed means stop and discard.
- Stop, changing nothing, if the clone has uncommitted work, the branch cannot fast-forward from
  GitHub, a sheet would not round-trip byte for byte, or the repo's own checks fail.
- An existing human answer is never overwritten; a different one is reported as a conflict.
- SignalDesk's own answers stay in the data home: they hold job data and are never committed.
No model is called and no repository code runs except the repo's own test and scoring commands.
"""
from __future__ import annotations

import csv
import fnmatch
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, ProjectConfig
from .db import DB, now_iso

BRANCH = "phone-review"
FORBIDDEN_BRANCHES = {"main", "master"}
ALLOW = {"pushback": ["labels/*.csv"], "nextword": ["evals/local_ai/human_review/*.md"]}
HUMAN_COLUMNS = ("human_label", "human_note")
ANSWER_RE = re.compile(r"^<!-- answer: (\S+) -->[ \t\r]*$", re.M)   # any CRs: autocrlf can double them
AUTO_EVERY_SECONDS = 30 * 60


class Stop(Exception):
    """A rule stopped the write. The message is fixed text plus file names; no content."""


def _git(cwd: Path, *args, check=True, timeout=120) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace", env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and r.returncode:
        raise Stop(f"git {args[0]} failed")
    return r.stdout.strip()


def pending(db: DB, project: str) -> list[dict]:
    return db.all("SELECT r.*, t.export_json, t.kind FROM project_responses r JOIN project_tasks t ON t.id=r.task_id "
                  "WHERE r.project=? AND r.id NOT IN (SELECT response_id FROM project_writes) ORDER BY r.created_at, r.id", (project,))


# ---------------------------------------------------------------- file edits (human columns only)
def _read_csv(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    term = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if _write_csv_text(rows, term) != text:
        raise Stop(f"{path.name} would not keep its exact format; not written")
    return rows, bom, term


def _write_csv_text(rows, term) -> str:
    out = io.StringIO(newline="")
    csv.writer(out, lineterminator=term).writerows(rows)
    return out.getvalue()


def apply_pushback(root: Path, answers: list[dict]) -> tuple[dict, list[str]]:
    """Fill human_label/human_note for each answer. Returns {response_id: (result, file)} and changed files."""
    results, changed, sheets = {}, [], {}
    for a in answers:
        meta = json.loads(a["export_json"])
        item = meta["row"]["item_id"]
        names = [meta["sheet"]] if meta.get("sheet") else sorted(p.name for p in (root / "labels").glob("*.csv"))
        hit = None
        for name in names:
            path = root / "labels" / name
            if not path.is_file():
                continue
            if path not in sheets:
                sheets[path] = _read_csv(path)
            rows = sheets[path][0]
            head = rows[0]
            if not all(c in head for c in ("item_id", *HUMAN_COLUMNS)):
                raise Stop(f"{name} lacks the label columns")
            for row in rows[1:]:
                if row and row[head.index("item_id")] == item:
                    hit = (path, head, row)
                    break
            if hit:
                break
        if not hit:
            results[a["id"]] = ("missing", None)
            continue
        path, head, row = hit
        li, ni = head.index("human_label"), head.index("human_note")
        note = " ".join(a["note"].splitlines())
        if row[li].strip():
            results[a["id"]] = ("already" if row[li].strip() == a["verdict"] and row[ni].strip() == note else "conflict", path.name)
            continue
        row[li], row[ni] = a["verdict"], note
        results[a["id"]] = ("written", path.name)
        if path not in changed:
            changed.append(path)
    for path in changed:
        rows, bom, term = sheets[path]
        data = _write_csv_text(rows, term).encode("utf-8")
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
    return results, [f"labels/{p.name}" for p in changed]


def apply_nextword(root: Path, answers: list[dict]) -> tuple[dict, list[str]]:
    base = root / "evals" / "local_ai" / "human_review"
    results, changed = {}, []
    by_sheet: dict[str, list[dict]] = {}
    for a in answers:
        by_sheet.setdefault(json.loads(a["export_json"])["sheet"], []).append(a)
    for name, items in by_sheet.items():
        path = base / name
        if not path.is_file() or path.suffix != ".md":
            for a in items:
                results[a["id"]] = ("missing", None)
            continue
        raw = path.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        marks = list(ANSWER_RE.finditer(text))
        # Each answer's block runs from the end of its marker line to the next marker; marker lines
        # themselves (and their line endings) are never rewritten.
        spans = {m[1]: (m.end(), marks[i + 1].start() if i + 1 < len(marks) else len(text)) for i, m in enumerate(marks)}
        edits = {}
        for a in items:
            aid = json.loads(a["export_json"])["answer_id"]
            if aid not in spans:
                results[a["id"]] = ("missing", name)
                continue
            block = text[spans[aid][0]:spans[aid][1]]
            v = re.search(r"^Verdict:[ \t]*([^\r\n]*)", block, re.M)
            n = re.search(r"^Note:[ \t]*([^\r\n]*)", block, re.M)
            if not v or not n:
                results[a["id"]] = ("missing", name)
                continue
            note = " ".join(a["note"].splitlines())
            if v[1].strip():
                results[a["id"]] = ("already" if v[1].strip() == a["verdict"] and n[1].strip() == note else "conflict", name)
                continue
            block = block[:v.start()] + "Verdict: " + a["verdict"] + block[v.end():]
            n = re.search(r"^Note:[ \t]*([^\r\n]*)", block, re.M)
            block = block[:n.start()] + ("Note: " + note if note else n[0]) + block[n.end():]
            edits[spans[aid]] = block
            results[a["id"]] = ("written", name)
        if edits:
            out = text
            for (start, end), block in sorted(edits.items(), reverse=True):
                out = out[:start] + block + out[end:]
            path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + out.encode("utf-8"))
            changed.append(f"evals/local_ai/human_review/{name}")
    return results, changed


def changed_paths(wt: Path) -> list[str]:
    """Every changed or untracked path, exactly as git reports it (NUL-separated, no quoting)."""
    r = subprocess.run(["git", "-C", str(wt), "status", "--porcelain", "-z", "--untracked-files=all"],
                       capture_output=True, timeout=120)
    if r.returncode:
        raise Stop("git status failed")
    entries = r.stdout.decode("utf-8", "replace").split("\0")
    out, skip = [], False
    for e in entries:
        if skip or not e:
            skip = False
            continue
        out.append(e[3:])
        skip = e[0] in "RC"                     # a rename lists its old path next
    return out


def outside_allow_list(kind: str, paths: list[str]) -> list[str]:
    return [p for p in paths if not any(fnmatch.fnmatch(p.replace("\\", "/"), g) for g in ALLOW.get(kind, []))]


# ---------------------------------------------------------------- the repo's own checks
def checks(kind: str, wt: Path, python: str, files: list[str]) -> list[tuple[str, list[str]]]:
    if kind == "pushback":
        out = [("pushback tests", [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"])]
        for f in files:
            report = Path(tempfile.gettempdir()) / f"signaldesk-score-{Path(f).stem}.md"
            out.append((f"pushback labels score {f}", [python, "-c",
                "import sys; from pushback.cli import main; sys.exit(main(sys.argv[1:]))",
                "labels", "score", "--sheet", f, "--out", str(report)]))
        return out
    return [("nextword tests", [python, "-m", "unittest"]),
            ("nextword compare_review", [python, "evals/local_ai/compare_review.py"])]


def run_checks(kind: str, wt: Path, python: str, files: list[str]) -> list[str]:
    done = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for name, cmd in checks(kind, wt, python, files):
        try:
            r = subprocess.run(cmd, cwd=wt, capture_output=True, text=True, timeout=900, env=env, encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            raise Stop(f"{name} could not run") from None
        if r.returncode:
            raise Stop(f"{name} failed")
        done.append(name)
    return done


# ---------------------------------------------------------------- one repo
def _worktree(cfg: Config, p: ProjectConfig, root: Path) -> Path:
    wt = (cfg.home / "project-worktrees" / re.sub(r"[^A-Za-z0-9_-]", "_", p.name)).resolve()
    listed = _git(root, "worktree", "list", "--porcelain")
    if f"worktree {wt.as_posix()}" not in listed.replace("\\", "/") and not wt.exists():
        _git(root, "fetch", "origin", timeout=300)
        if _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH}", check=False):
            _git(root, "worktree", "add", str(wt), BRANCH)
        elif _git(root, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{BRANCH}", check=False):
            _git(root, "worktree", "add", "-b", BRANCH, str(wt), f"origin/{BRANCH}")
        else:
            base = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
            if base in FORBIDDEN_BRANCHES | {"HEAD"}:
                base = _git(root, "rev-parse", "HEAD")
            _git(root, "worktree", "add", "-b", BRANCH, str(wt), base)
    if _git(wt, "rev-parse", "--abbrev-ref", "HEAD") != BRANCH:
        raise Stop("the review worktree is not on phone-review")
    return wt


def _ahead(wt: Path) -> bool:
    remote = _git(wt, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{BRANCH}", check=False)
    return not remote or bool(_git(wt, "rev-list", f"origin/{BRANCH}..{BRANCH}", check=False))


def _push(db: DB, wt: Path) -> str:
    """Push phone-review only. Returns "" on success, else a sentence; the commit stays and is retried."""
    if BRANCH in FORBIDDEN_BRANCHES or _git(wt, "rev-parse", "--abbrev-ref", "HEAD") != BRANCH:
        return "; not pushed: the worktree is not on phone-review."
    r = subprocess.run(["git", "-C", str(wt), "push", "origin", f"refs/heads/{BRANCH}:refs/heads/{BRANCH}"],
                       capture_output=True, text=True, timeout=300, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if r.returncode:
        return "; committed, but the push failed (network or GitHub sign-in). It is retried next time."
    db.run("UPDATE project_writes SET pushed_at=? WHERE pushed_at IS NULL AND commit_sha IS NOT NULL AND branch=?", (now_iso(), BRANCH))
    return ""


def write_project(cfg: Config, db: DB, p: ProjectConfig, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    entry = {"at": now_iso(), "project": p.name, "branch": BRANCH, "files": [], "written": 0, "pushed": False,
             "commit": None, "checks": [], "conflicts": 0}
    if p.kind not in ALLOW:
        return {**entry, "status": "skipped", "message": "SignalDesk answers stay in the data folder; they are never committed."}
    answers = pending(db, p.name)
    unpushed = db.scalar("SELECT COUNT(*) FROM project_writes WHERE project=? AND commit_sha IS NOT NULL AND pushed_at IS NULL", (p.name,))
    if not answers and not (unpushed and p.name in cfg.writeback.push):
        return {**entry, "status": "nothing", "message": "No new answers to write."}
    if p.name not in cfg.writeback.write:
        return {**entry, "status": "needs-approval", "message": f"{len(answers)} answers wait. Add \"{p.name}\" to [writeback] write in config.toml to allow the first write."}
    root = Path(p.path).expanduser()
    root = (root if root.is_absolute() else cfg.home / root).resolve()
    wt = None
    try:
        if _git(root, "status", "--porcelain", "--untracked-files=normal"):
            raise Stop("the clone has uncommitted work; commit or stash it first")
        wt = _worktree(cfg, p, root)
        if changed_paths(wt):
            raise Stop("the review worktree has uncommitted changes")
        _git(wt, "fetch", "origin", timeout=300)
        if _git(wt, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{BRANCH}", check=False):
            r = subprocess.run(["git", "-C", str(wt), "merge", "--ff-only", f"origin/{BRANCH}"], capture_output=True, text=True)
            if r.returncode:
                raise Stop("phone-review on GitHub has changes that do not fast-forward; resolve them on the laptop")
        results, files = (apply_pushback if p.kind == "pushback" else apply_nextword)(wt, answers)
        bad = outside_allow_list(p.kind, changed_paths(wt))
        if bad:
            raise Stop("a file outside the allow-list changed: " + ", ".join(bad))
        written = [a for a in answers if results[a["id"]][0] == "written"]
        entry["conflicts"] = sum(r[0] == "conflict" for r in results.values())
        sha = None
        if written:
            python = p.check_python or sys.executable
            entry["checks"] = run_checks(p.kind, wt, python, files)
            bad = outside_allow_list(p.kind, changed_paths(wt))
            if bad:
                raise Stop("a check changed a file outside the allow-list: " + ", ".join(bad))
            phone = sum(a.get("via") == "phone" for a in written)
            _git(wt, "add", "--", *files)
            message = (f"Add {len(written)} human review answers from SignalDesk review\n\n"
                       f"Written by SignalDesk review write-back on {now.date().isoformat()}: {phone} answered on the phone, "
                       f"{len(written) - phone} on the laptop.\nOnly human columns changed in: {', '.join(files)}.\n"
                       f"Checks passed before this commit: {', '.join(entry['checks'])}.")
            _git(wt, "commit", "-q", "-m", message)
            sha = _git(wt, "rev-parse", "HEAD")
        with db.immediate() as con:
            for a in answers:
                result, file = results[a["id"]]
                if result in ("written", "already", "conflict", "missing"):     # each reported once, never retried
                    con.execute("INSERT OR IGNORE INTO project_writes VALUES (?,?,?,?,?,?,?,NULL)",
                                (a["id"], p.name, result, sha if result == "written" else None, BRANCH, file, now_iso()))
        entry.update(written=len(written), files=files, commit=sha[:10] if sha else None,
                     missing=sum(r[0] == "missing" for r in results.values()))
        push_note = ""
        if p.name in cfg.writeback.push and _ahead(wt):
            push_note = _push(db, wt)
            entry["pushed"] = push_note == ""
        status = "written" if sha else "nothing"
        msg = (f"{len(written)} answers committed to {BRANCH}" + (" and pushed." if entry["pushed"] else push_note or
               "; not pushed (add the repo to [writeback] push to allow it).") if sha else "Nothing new to write.")
        if entry["missing"]:
            msg += f" {entry['missing']} answers no longer match a row in the repo and were not written."
        if entry["conflicts"]:
            msg += f" {entry['conflicts']} answers conflict with an existing human answer in the repo and were not written."
        return {**entry, "status": status, "message": msg}
    except Stop as e:
        if wt and wt.exists():
            _git(wt, "reset", "-q", "--hard", "HEAD", check=False)       # discard partial edits in OUR worktree only
            _git(wt, "clean", "-q", "-fd", "--", *ALLOW[p.kind], check=False)
        return {**entry, "status": "stopped", "message": f"Stopped: {e}. Nothing was committed."}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as e:
        if wt and wt.exists():
            _git(wt, "reset", "-q", "--hard", "HEAD", check=False)
        return {**entry, "status": "stopped", "message": f"Stopped: {type(e).__name__}. Nothing was committed."}


def run(cfg: Config, db: DB) -> list[dict]:
    out = [write_project(cfg, db, p) for p in cfg.project]
    log = (db.get_setting("writeback_log") or []) + [e for e in out if e["status"] not in ("nothing", "skipped")]
    db.set_setting("writeback_log", log[-200:])
    db.set_setting("writeback_last_run", now_iso())
    return out


def today_summary(db: DB, day: str) -> list[dict]:
    return [e for e in (db.get_setting("writeback_log") or []) if e["at"][:10] == day]
