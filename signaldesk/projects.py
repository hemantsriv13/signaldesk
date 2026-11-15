"""Project Coach: read-only collectors, templates, a daily human queue and staged exports.

No model, network, sibling imports or repository writes. Content is data, never code.
Only the selected SignalDesk home receives tasks, answers and exports.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import pipeline
from .config import Config, load_config
from .db import DB, now_iso

VERDICTS = {"label_reply": ["pass", "fail", "unclear"],
            "review_answer": ["correct", "minor", "wrong"],
            "judge_analysis": ["agree", "disagree", "unsure"], "laptop_reminder": []}
LABEL_COLUMNS = ["item_id", "split", "model", "probe", "step", "what_counts_as_pass",
                 "notes_on_correct_answer", "user_message", "model_reply", "human_label", "human_note"]
ANSWER = re.compile(r"^<!-- answer: (\S+) -->\s*$", re.M)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _readable(value, depth=0) -> str:
    """Keep saved content verbatim, with readable field names instead of raw JSON."""
    if isinstance(value, dict):
        return "\n\n".join(f"{str(k).replace('_', ' ').capitalize()}:\n{_readable(v, depth + 1)}"
                            for k, v in value.items())
    if isinstance(value, list):
        return "\n\n".join("• " + _readable(v, depth + 1) for v in value) or "None recorded"
    if value is None:
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _age(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Review reference leaves its project")
    return path


def git_facts(path: Path) -> dict:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_OPTIONAL_LOCKS": "0"}
    def git(*args):
        result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                                 "-c", "core.untrackedCache=false", "-C", str(path), *args],
                                capture_output=True, text=True, timeout=15, env=env,
                                encoding="utf-8", errors="replace")
        if result.returncode:
            raise ValueError("Git metadata unavailable")
        return result.stdout.strip()
    try:
        top = Path(git("rev-parse", "--show-toplevel")).resolve()
        if top != path.resolve():
            raise ValueError("Configured path is not a clone root")
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        return {"branch": branch, "last_commit_at": git("log", "-1", "--format=%cI"),
                "dirty": bool(git("status", "--porcelain", "--untracked-files=normal")), "git_error": None}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"branch": None, "last_commit_at": None, "dirty": None,
                "git_error": "Could not read Git metadata; check path and Git access."}


def _task(project, key, kind, title, text, criteria, what, why, unlocks, age, export=None, evidence="", blocking=True):
    return {"project": project, "source_key": key, "type": kind, "title": title,
            "text": text, "pass_criteria": criteria, "what_this_is": what, "why_it_matters": why,
            "unlocks_next": unlocks, "evidence": evidence, "source_at": age,
            "result_blocking": blocking, "explanation_by": "template", "verdicts": VERDICTS[kind],
            "_export": export or {}}


def _reminder(name, key, text, age, why):
    return _task(name, key, "laptop_reminder", "On your laptop", text, "Read only",
                 "This is a laptop action. It cannot be completed with a phone verdict.", why,
                 "Return to the project on your laptop.", age)


def _csv_rows(path):
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    first = text.splitlines()[0] if text else ""
    return list(csv.DictReader(io.StringIO(text), delimiter=";" if first.count(";") > first.count(",") else ","))


def pushback(name, root):
    candidates, answered = {}, set()
    for sheet in sorted((root / "labels").glob("*.csv")):
        for row in _csv_rows(sheet):
            if not row.get("item_id"):
                continue
            key = f"reply:{row['item_id']}"
            if row.get("human_label", "").strip():
                answered.add(key)
                continue
            if not row.get("model_reply") or not row.get("what_counts_as_pass"):
                raise ValueError("Incomplete Pushback review row")
            # Allowlist only. Extra grader fields must not enter snapshots OR exports.
            clean = {c: row.get(c, "") for c in LABEL_COLUMNS}
            evidence_path = sheet.with_name(sheet.stem + "_data.md")
            evidence = evidence_path.read_text(encoding="utf-8-sig") if evidence_path.exists() else ""
            candidates.setdefault(key, _task(name, key, "label_reply", "Judge a reply under pressure",
                f"User message:\n{clean['user_message']}\n\nReply:\n{clean['model_reply']}",
                clean["what_counts_as_pass"],
                "This is a saved reply from a model evaluation. Judge it against the supplied data and pass rule.",
                "Pushback's README reports a held-out false pass: the grader accepted a reply the owner rejected. Your label checks the grader and builds evaluation experience you can discuss in interviews.",
                "A labelled row can enter the existing grader-agreement report.", _age(sheet),
                {"kind": "pushback", "row": clean}, evidence=evidence or "Source data sheet missing; choose unclear if the supplied rule is insufficient."))
    return [v for k, v in candidates.items() if k not in answered]


def _sheet_marks(text):
    found, current = {}, None
    for line in text.splitlines():
        m = ANSWER.fullmatch(line)
        if m:
            current = m[1]
            found[current] = {"verdict": "", "note": ""}
        elif line.startswith("## "):
            current = None
        elif current:
            m = re.fullmatch(r"(Verdict|Note):[ \t]*(.*)", line)
            if m:
                field = m[1].lower()
                if not found[current].get("_" + field):
                    found[current][field] = m[2].strip()
                    found[current]["_" + field] = True
    return found


def nextword(name, root):
    base = root / "evals" / "local_ai"
    key_path = base / "human_review" / "key.json"
    if not key_path.exists():
        return []
    key = _json(key_path)["answers"]
    out, cache = [], {}
    for sheet in sorted((base / "human_review").glob("*.md")):
        # The existing blank verdict marker is the project's awaiting-human-review state.
        for aid, mark in _sheet_marks(sheet.read_text(encoding="utf-8-sig")).items():
            if mark["verdict"] or aid not in key:
                continue
            meta = key[aid]
            result = _inside(base, meta["file"])
            if not result.is_relative_to((base / "results").resolve()):
                raise ValueError("Expected an evaluation result")
            if result not in cache:
                cache[result] = _json(result)
            data = cache[result]
            parts = aid.split("/")
            if len(parts) != 3 or parts[0] != sheet.stem:
                raise ValueError("Invalid NextWord answer identity")
            records = data.get("cases") if isinstance(data.get("cases"), list) else data.get("runs")
            if not isinstance(records, list):
                records = data.get("results", [])
            record = next((r for r in records if r.get("id") == parts[1]
                           and r.get("repeat", 1) == meta.get("repeat", 1)), None)
            if record is None:
                raise ValueError("Review sheet has no matching saved answer")
            turns, facts = [], []
            if record.get("facts") is not None:
                facts.append(record["facts"])
            for t in record.get("turns", []):
                turns.append({k: t.get(k) for k in ("action", "question", "answer", "refused")})
                if t.get("facts") is not None and t["facts"] not in facts:
                    facts.append(t["facts"])
                if t.get("calculations"):
                    facts.append({"engine_calculations": t["calculations"]})
            if not facts or not turns:
                raise ValueError("Saved answer lacks engine facts or turns")
            source_key = f"answer:{meta['file']}:{parts[1]}:{meta.get('repeat', 1)}"
            out.append(_task(name, source_key, "review_answer", "Check a tutor answer",
                "\n\n".join(f"Request: {t['question'] or t['action']}\nAnswer: {t['answer'] or '(No answer)'}" for t in turns),
                "Correct: every turn agrees with the engine facts and answers the learner. Minor: a harmless flaw. Wrong: a false or unanswered claim; the worst turn decides.",
                "This is a recorded tutor conversation. Check every turn against the engine facts below.",
                f"NextWord's HUMAN_REVIEW.md requires a verdict for {sheet.stem} before reporting human-review results. Checking these explanations builds evidence-checking skills and gives you a concrete interview example.",
                "The existing comparison can count your verdict beside the automatic checks.",
                _age(result), {"kind": "nextword", "answer_id": aid, "sheet": sheet.name,
                               "key": meta, "result_sha256": hashlib.sha256(result.read_bytes()).hexdigest()}, evidence=_readable(facts)))
    return out


def signaldesk(name, root, db, now):
    out = []
    for a in db.all("SELECT * FROM analyses WHERE kind IN ('job_fit','case_study') ORDER BY created_at,id"):
        key = f"analysis:{a['id']}"
        inputs, output = json.loads(a["inputs_json"]), json.loads(a["output_json"])
        if inputs.get("human_verdict") or output.get("human_verdict"):
            continue
        table = "jobs" if a["kind"] == "job_fit" else "articles"
        target = db.one(f"SELECT * FROM {table} WHERE id=?", (a["target_id"],))
        if not target:
            continue
        text = target.get("description_text") if table == "jobs" else target.get("content_text")
        why = (f"SignalDesk's README lists human job-fit review as not done. Checking analysis {a['id']} practises testing claims against evidence. It also helps you decide which project results to trust during your job search."
               if a["kind"] == "job_fit" else
               f"Case-study card {a['id']} separates source facts, vendor claims and inferences. Checking those labels practises evaluating evidence. A checked card gives you a more reliable deployment example to discuss in interviews.")
        out.append(_task(name, key, "judge_analysis", f"Review: {target['title']}", _readable(output),
            "Agree if the claims and conclusion are supported by the source and supplied facts. Disagree if a material claim is unsupported. Unsure if evidence is missing.",
            "This is a saved analysis from SignalDesk. Compare its claims with the source and the facts recorded with it.",
            why,
            "A recorded human verdict separates checked claims from unchecked model output.", a["created_at"],
            {"kind": "signaldesk", "analysis_id": a["id"], "analysis_kind": a["kind"], "target_id": a["target_id"]},
            evidence=_readable({"source_text": text or "Source text unavailable", "recorded_inputs": inputs})))
    for item in pipeline.needs_action(db, now):
        out.append(_reminder(name, f"pipeline:{item['kind']}:{item['job_id']}:{item.get('followup_id', '')}",
                    f"{item['title']} at {item['employer']}: {item['why']}. Open Pipeline on your laptop.",
                    item.get("since") or now.isoformat(),
                    f"Pipeline records this action for job {item['job_id']}: {item['why']}. Taking it advances your application."))
    return out


def collect(cfg: Config, db: DB, now: datetime):
    statuses, candidates = [], []
    for p in cfg.project:
        try:
            root = Path(p.path).expanduser()
            root = (root if root.is_absolute() else cfg.home / root).resolve()
            available = root.is_dir()
        except (OSError, RuntimeError):
            available = False
        status = {"name": p.name, "kind": p.kind, "available": available, "open_reviews": 0,
                  "branch": None, "last_commit_at": None, "dirty": None, "git_error": None, "notice": None}
        statuses.append(status)
        if not status["available"]:
            status["notice"] = "Project path is missing or unavailable. Check [[project]] in config.toml."
            candidates.append(_reminder(p.name, "missing-path", status["notice"], now.isoformat(),
                              f"The configured {p.kind} clone could not be read; no reviews can be collected."))
            continue
        status.update(git_facts(root))
        try:
            if p.kind == "signaldesk":
                items = signaldesk(p.name, root, db, now)
            else:
                items = (pushback if p.kind == "pushback" else nextword)(p.name, root)
            status["open_reviews"] = sum(i["type"] != "laptop_reminder" for i in items)
            candidates.extend(items)
            if not status["open_reviews"] and p.kind in ("pushback", "nextword"):
                message = ("No rows with an empty human_label. Generate a new label sheet on your laptop from saved runs; no model was run."
                           if p.kind == "pushback" else "No mapped tutor answers awaiting human review. Check or generate the human-review sheets from saved results on your laptop.")
                status["notice"] = message
                candidates.append(_reminder(p.name, "new-sheet", message, now.isoformat(),
                    f"{p.kind} has no reviewable rows in its current sheets; a sheet is needed before more human evaluation."))
        except (OSError, ValueError, KeyError, TypeError):
            # No exception text: it may contain source text or private paths.
            status["notice"] = "Review files could not be read safely. Check their format and access on your laptop."
            candidates.append(_reminder(p.name, "invalid-review", status["notice"], now.isoformat(),
                              f"The {p.kind} review adapter could not read the expected format; no verdicts were invented."))
    return statuses, candidates


def prepare(cfg: Config, db: DB, now: datetime | None = None):
    now = now or datetime.now().astimezone()
    day = now.date().isoformat()
    if not cfg.project:
        return today(db, now)
    if db.scalar("SELECT 1 FROM project_days WHERE day=?", (day,)):
        return today(db, now)
    statuses, candidates = collect(cfg, db, now)
    with db.immediate() as con:
        if con.execute("SELECT 1 FROM project_days WHERE day=?", (day,)).fetchone():
            return today(db, now)
        answered = {(r[0], r[1]) for r in con.execute("SELECT project,source_key FROM project_responses")}
        candidates = [c for c in candidates if (c["project"], c["source_key"]) not in answered]
        unique = {(c["project"], c["source_key"]): c for c in candidates}
        rank = lambda c: (not c["result_blocking"], c["source_at"], c["project"], c["source_key"])
        phone = sorted((c for c in unique.values() if c["type"] != "laptop_reminder"), key=rank)
        chosen, seen = [], set()
        for c in phone:
            if c["project"] not in seen and len(chosen) < 3:
                chosen.append(c)
                seen.add(c["project"])
        for c in phone:
            if len(chosen) < 3 and c not in chosen:
                chosen.append(c)
        reminders = sorted((c for c in unique.values() if c["type"] == "laptop_reminder"), key=rank)[:3]
        stamp = now.isoformat()
        con.execute("INSERT INTO project_days VALUES (?,?,?)", (day, stamp, _dump(statuses)))
        for c in chosen + reminders:
            payload = {k: v for k, v in c.items() if k != "_export"}
            con.execute("INSERT INTO project_tasks(id,day,project,kind,source_key,payload_json,export_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), day, c["project"], c["type"], c["source_key"], _dump(payload), _dump(c["_export"]), stamp))
    return today(db, now)


def today(db: DB, now: datetime | None = None):
    now = now or datetime.now().astimezone()
    day = now.date().isoformat()
    saved = db.one("SELECT * FROM project_days WHERE day=?", (day,))
    tasks, reminders = [], []
    for t in db.all("SELECT t.*,r.verdict,r.note,r.created_at answered_at FROM project_tasks t LEFT JOIN project_responses r ON r.task_id=t.id WHERE t.day=? ORDER BY t.rowid", (day,)):
        public = {**json.loads(t["payload_json"]), "id": t["id"], "skipped_at": t["skipped_at"],
                  "response": {"verdict": t["verdict"], "note": t["note"], "at": t["answered_at"], "input_origin": "human"} if t["verdict"] else None}
        (reminders if t["kind"] == "laptop_reminder" else tasks).append(public)
    start = datetime.combine((now - timedelta(days=now.weekday())).date(), datetime.min.time(), tzinfo=now.tzinfo).astimezone(timezone.utc).isoformat()
    progress = {r["project"]: r["n"] for r in db.all("SELECT project,COUNT(*) n FROM project_responses WHERE julianday(created_at)>=julianday(?) GROUP BY project", (start,))}
    return {"day": day, "prepared": bool(saved), "projects": json.loads(saved["projects_json"]) if saved else [],
            "tasks": tasks, "reminders": reminders, "done_this_week": progress}


def respond(db: DB, task_id: str, verdict: str, note: str):
    if len(note) > 4000:
        raise ValueError("Keep your note to 4,000 characters or fewer")
    with db.immediate() as con:
        task = con.execute("SELECT * FROM project_tasks WHERE id=?", (task_id,)).fetchone()
        if task is None:
            raise ValueError("Task not found")
        if verdict not in VERDICTS[task["kind"]]:
            raise ValueError("Choose an allowed verdict; laptop reminders are read only")
        old = con.execute("SELECT * FROM project_responses WHERE project=? AND source_key=?", (task["project"], task["source_key"])).fetchone()
        if old:
            if old["verdict"] == verdict and old["note"] == note.strip():
                return {"id": old["id"], "saved": True, "duplicate": True}
            raise ValueError("This item already has a human verdict; it was not overwritten")
        response_id = str(uuid.uuid4())
        con.execute("INSERT INTO project_responses VALUES (?,?,?,?,?,?,?,?)",
                    (response_id, task_id, task["project"], task["source_key"], verdict, note.strip(), now_iso(), "human"))
    return {"id": response_id, "saved": True, "duplicate": False}


def skip(db: DB, task_id: str):
    with db.immediate() as con:
        task = con.execute("SELECT * FROM project_tasks WHERE id=?", (task_id,)).fetchone()
        if not task or task["kind"] == "laptop_reminder":
            raise ValueError("Answerable task not found")
        if con.execute("SELECT 1 FROM project_responses WHERE task_id=?", (task_id,)).fetchone():
            raise ValueError("This task is already answered")
        con.execute("UPDATE project_tasks SET skipped_at=COALESCE(skipped_at,?) WHERE id=?", (now_iso(), task_id))
    return {"skipped": True}


def export_responses(cfg: Config, db: DB):
    """One file per configured project in a new private export folder. Never write clones."""
    base = (cfg.home / "project-exports").resolve()
    for p in cfg.project:
        root = Path(p.path).expanduser()
        root = (root if root.is_absolute() else cfg.home / root).resolve()
        if p.kind != "signaldesk" and base.is_relative_to(root):
            raise ValueError("Export home must be outside configured project clones")
    directory = base / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".pending")
    directory.mkdir(parents=True)
    paths = []
    for p in cfg.project:
        rows = db.all("SELECT r.*,t.export_json,t.kind FROM project_responses r JOIN project_tasks t ON t.id=r.task_id WHERE r.project=? ORDER BY r.created_at,r.id", (p.name,))
        stem = re.sub(r"[^a-zA-Z0-9_-]", "_", p.name) + "-" + hashlib.sha256(p.name.encode()).hexdigest()[:8]
        if p.kind == "pushback":
            path = directory / f"{stem}.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=LABEL_COLUMNS + ["human_at", "input_origin"])
                writer.writeheader()
                for r in rows:
                    item = json.loads(r["export_json"])["row"]
                    writer.writerow({**item, "human_label": r["verdict"], "human_note": r["note"],
                                     "human_at": r["created_at"], "input_origin": "human"})
        elif p.kind == "nextword":
            # One project archive retains all original consumer filenames and key.json.
            root = Path(p.path).expanduser()
            root = (root if root.is_absolute() else cfg.home / root).resolve()
            source = root / "evals" / "local_ai" / "human_review"
            path = directory / f"{stem}.zip"
            marks = {json.loads(r["export_json"])["answer_id"]: r for r in rows}
            current_key = _json(source / "key.json")["answers"] if rows else {}
            for aid, r in marks.items():
                metadata = json.loads(r["export_json"])
                if current_key.get(aid) != metadata["key"]:
                    raise ValueError("NextWord answer mapping changed since collection")
                result = _inside(source.parent, metadata["key"]["file"])
                if hashlib.sha256(result.read_bytes()).hexdigest() != metadata["result_sha256"]:
                    raise ValueError("NextWord saved answer changed since collection")
            exported_ids = set()
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for sheet in sorted(source.glob("*.md")):
                    original = sheet.read_text(encoding="utf-8-sig")
                    chunks = re.split(r"(^<!-- answer: \S+ -->\s*$)", original, flags=re.M)
                    for i in range(1, len(chunks), 2):
                        aid = ANSWER.fullmatch(chunks[i].strip())[1]
                        r = marks.get(aid)
                        if r:
                            exported_ids.add(aid)
                            existing = _sheet_marks(chunks[i] + chunks[i+1])[aid]
                            if existing["verdict"] and existing["verdict"] != r["verdict"]:
                                raise ValueError("NextWord sheet already contains a different verdict")
                            if existing["note"] and existing["note"] != " ".join(r["note"].splitlines()):
                                raise ValueError("NextWord sheet already contains a different note")
                            chunks[i+1] = re.sub(r"^Verdict:[^\n]*", lambda _: "Verdict: " + r["verdict"], chunks[i+1], count=1, flags=re.M)
                            chunks[i+1] = re.sub(r"^Note:[^\n]*", lambda _: "Note: " + " ".join(r["note"].splitlines()), chunks[i+1], count=1, flags=re.M)
                    z.writestr(sheet.name, "".join(chunks))
                if (source / "key.json").exists():
                    z.writestr("key.json", (source / "key.json").read_bytes())
                z.writestr("signaldesk-human-input.json", _dump([{k: r[k] for k in ("id", "source_key", "verdict", "note", "created_at", "input_origin")} for r in rows]))
            if exported_ids != set(marks):
                raise ValueError("NextWord review sheet no longer contains a reviewed answer")
        else:
            path = directory / f"{stem}.json"
            path.write_text(_dump({"format": "signaldesk-project-responses-v1", "responses": [
                {**{k: r[k] for k in ("id", "source_key", "verdict", "note", "created_at", "input_origin")},
                 **json.loads(r["export_json"])} for r in rows]}), encoding="utf-8")
        paths.append(path.name)
    final = directory.with_suffix("")
    directory.rename(final)
    return {"directory": str(final), "files": paths}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Project Coach: local review tasks and staged human exports")
    parser.add_argument("action", choices=["collect", "export"])
    parser.add_argument("--home", required=True, type=Path, help="Explicit copied data home; never use live data for verification")
    args = parser.parse_args(argv)
    cfg = load_config(args.home)
    db = DB(cfg.db_path)
    try:
        if args.action == "collect":
            result = prepare(cfg, db)
            print(f"Daily batch: {len(result['tasks'])} review tasks, {len(result['reminders'])} laptop reminders. No model called.")
        else:
            result = export_responses(cfg, db)
            print(f"Wrote {len(result['files'])} project export files under the selected data home. No clone changed.")
    except (OSError, ValueError, KeyError, TypeError):
        print("Project Coach could not complete safely. Check data-home access and review formats; private content was not logged.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
