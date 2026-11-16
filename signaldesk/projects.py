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


def _analysis_text(kind: str, o: dict, for_phone: bool = False) -> str:
    """The claims to judge, one line each, instead of a raw dump of every stored field."""
    lines = []
    if kind == "job_fit":
        lines += [f"Match: {o.get('match') or 'not given'}", f"Summary: {o.get('summary') or 'none'}", "", "Essential requirements (quoted from the posting):"]
        for r in o.get("essential") or []:
            found = "" if r.get("quote_found") else "  [quote NOT found in posting]"
            lines.append(f"• {r.get('req')}: \"{r.get('quote') or ''}\"{found}")
        if o.get("preferred"):
            lines += ["", "Preferred:"] + [f"• {r.get('req') if isinstance(r, dict) else r}" for r in o["preferred"]]
        if o.get("evidence") and for_phone:
            lines += ["", f"Evidence claimed from your profile: {len(o['evidence'])} item(s), shown on your laptop only."]
        elif o.get("evidence"):
            lines += ["", "Evidence claimed from your profile:"]
            lines += [f"• {e.get('req')}: {e.get('note') or ''} (facts {', '.join(e.get('facts') or []) or 'none'})" for e in o["evidence"]]
        for key, title in (("gaps", "Gaps"), ("unknowns", "Unknowns")):
            if o.get(key):
                lines += ["", f"{title}:"] + [f"• {g}" for g in o[key]]
    else:
        lines.append(f"Suitability: {o.get('suitability') or 'not given'}. {o.get('suitability_reason') or ''}".strip())
        for key, value in o.items():
            if isinstance(value, dict) and "text" in value:
                quote = f' Quote: "{value["quote"]}"' if value.get("quote") else ""
                lines.append(f"• {key.replace('_', ' ').capitalize()} [{value.get('label') or 'unlabelled'}]: {value['text']}{quote}")
    if o.get("injection_seen"):
        lines += ["", "Note: wording aimed at AI tools was flagged in the source."]
    return "\n".join(lines)


PHONE_FIELDS = ("project", "type", "title", "text", "pass_criteria", "what_this_is", "why_it_matters", "why_sources",
                "unlocks_next", "evidence", "verdicts", "source_at")
PHONE_EVIDENCE_CHARS = 4000


def _phone_variant(kind: str, output: dict, target: dict, text: str | None) -> dict:
    """What the cloud copy may hold for a SignalDesk card: no profile-fact notes, no full article,
    the public posting capped. The laptop page keeps the full version."""
    if kind == "job_fit":
        posting = (text or "Posting text unavailable")[:PHONE_EVIDENCE_CHARS]
        evidence = f"Posting text (first {PHONE_EVIDENCE_CHARS:,} characters):\n{posting}"
    else:
        evidence = f"The full article stays on your laptop. Original: {target.get('url') or 'not recorded'}"
    return {"text": _analysis_text(kind, output, for_phone=True), "evidence": evidence}


def phone_card(payload: dict) -> dict:
    """The phone-safe card for one stored task payload."""
    card = {k: payload.get(k) for k in PHONE_FIELDS}
    if payload.get("phone"):
        card.update(payload["phone"])
    elif payload.get("type") == "judge_analysis":
        # Prepared before phone variants existed: never fall back to the laptop's full evidence.
        card["text"] = re.sub(r"\nEvidence claimed from your profile:\n(?:•[^\n]*\n?)*",
                              "\nEvidence claimed from your profile: shown on your laptop only.\n\n", card.get("text") or "")
        card["evidence"] = "The source for this card is on your laptop."
    card["evidence"] = (card.get("evidence") or "")[:20000]
    return card


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


# ---------------------------------------------------------------- sourced facts for "Why it matters"
# Every answerable task's reason must quote a README line that exists now, or a count computed now
# from the data home or the clone. Templates only arrange these facts; they never supply one.
README_FACTS = {
    "pushback": [("README.md", r"the held-out Opus false pass below is still present", "problem"),
                 ("README.md", r"### Agreement with human labels", "result")],
    "nextword": [("README.md", r"Human review has not been done yet", "problem"),
                 ("README.md", r"went from \d+ to \d+ correct of \d+ \(AI review\)", "result")],
    "signaldesk": [("README.md", r"Your review of the job-fit judgements \| Not done", "problem"),
                   ("README.md", r"Each point is labelled source fact, vendor claim, inference or missing", "case")],
}
ROLE_KEYWORDS = {"pushback": ("evaluation", r"\bevaluat\w*|\bevals?\b"),
                 "nextword": ("LLM", r"\bLLMs?\b|\blanguage models?\b"),
                 "signaldesk": ("agent", r"\bagents?\b|\bagentic\b")}
SHORTLISTED = ("Interested", "Investigate")


class ExportBlocked(ValueError):
    """An export check failed. Messages are fixed text from this module: no paths or file content."""


class UnsourcedExplanation(ValueError):
    """A "Why it matters" text that does not carry a verifiable fact."""


def readme_facts(kind: str, root: Path) -> dict:
    """{role: fact} for each configured README pattern that matches a line in the clone today."""
    out = {}
    for rel, pattern, role in README_FACTS.get(kind, []):
        try:
            lines = _inside(root, rel).read_text(encoding="utf-8-sig").splitlines()
        except (OSError, ValueError):
            continue
        for n, line in enumerate(lines, 1):
            m = re.search(pattern, line)
            if m:
                quote = m[0].strip()
                out[role] = {"kind": "readme", "file": rel, "line": n, "quote": quote,
                             "text": f'{rel} line {n}: "{quote.lstrip("# ")}"'}
                break
    return out


def count_fact(value: int, text: str, source: str) -> dict:
    return {"kind": "count", "value": value, "text": text, "source": source}


def role_fact(db: DB, kind: str) -> dict | None:
    """Shortlisted roles in the data home, and how many postings mention this project's skill."""
    rows = db.all(f"SELECT description_text FROM jobs WHERE status IN ({','.join('?' * len(SHORTLISTED))})", SHORTLISTED)
    if not rows:
        return None
    word, pattern = ROLE_KEYWORDS[kind]
    k = sum(bool(re.search(pattern, r["description_text"] or "", re.I)) for r in rows)
    return count_fact(k, f'{k} of your {len(rows)} shortlisted roles mention "{word}" in the posting',
                      "jobs table, shortlisted statuses")


def check_why(text: str, facts: list[dict], root: Path | None = None) -> None:
    """Reject an explanation unless it cites at least one fact, every cited fact appears verbatim,
    counts carry their number, and README quotes are still on the cited line."""
    if not text or not facts:
        raise UnsourcedExplanation("No sourced fact supports this explanation")
    for f in facts:
        if f.get("text") not in text:
            raise UnsourcedExplanation("A cited fact is missing from the explanation")
        if f["kind"] == "count":
            if not isinstance(f.get("value"), int) or not re.search(rf"(?<!\d){f['value']}(?!\d)", f["text"]):
                raise UnsourcedExplanation("A count fact does not state its number")
        elif f["kind"] == "readme":
            if root is None:
                raise UnsourcedExplanation("A README fact cannot be checked without its clone")
            try:
                lines = _inside(root, f["file"]).read_text(encoding="utf-8-sig").splitlines()
            except (OSError, ValueError):
                raise UnsourcedExplanation("The cited README could not be read") from None
            if not (0 < f["line"] <= len(lines) and f["quote"] in lines[f["line"] - 1]):
                raise UnsourcedExplanation("The cited README line no longer says this")
        else:
            raise UnsourcedExplanation("Unknown fact kind")


def _sentence(*parts) -> str:
    return " ".join(p.rstrip(".") + "." for p in parts if p)


def _task(project, key, kind, title, text, criteria, what, why, unlocks, age, export=None, evidence="", blocking=True,
          facts=None, root=None, phone=None):
    if kind != "laptop_reminder":
        check_why(why, facts or [], root)
    return {"project": project, "source_key": key, "type": kind, "title": title,
            "text": text, "pass_criteria": criteria, "what_this_is": what, "why_it_matters": why,
            "why_sources": [{k: f[k] for k in ("kind", "text", "source", "file", "line") if k in f} for f in facts or []],
            "unlocks_next": unlocks, "evidence": evidence, "source_at": _utc(age),
            "result_blocking": blocking, "explanation_by": "template", "verdicts": VERDICTS[kind],
            "phone": phone, "_export": export or {}}


def _utc(at: str) -> str:
    """Normalise timestamps so "oldest first" compares instants, not strings with different offsets."""
    try:
        d = datetime.fromisoformat(at)
    except (TypeError, ValueError):
        return at
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


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


def _probe_section(text: str, probe: str) -> str:
    """Only this row's probe from the data sheet: the "## <probe>" section, or the whole sheet if absent."""
    m = re.search(rf"^## {re.escape(probe)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S) if probe else None
    return f"## {probe}{m[1].rstrip()}" if m else text


def pushback(name, root, db=None):
    rows, answered, totals = [], set(), {}
    for sheet in sorted((root / "labels").glob("*.csv")):
        sheet_rows = [r for r in _csv_rows(sheet) if r.get("item_id")]
        totals[sheet.name] = len(sheet_rows)
        for row in sheet_rows:
            key = f"reply:{row['item_id']}"
            if row.get("human_label", "").strip():
                answered.add(key)
            else:
                rows.append((sheet, key, row))
    open_keys = {k for _, k, _ in rows if k not in answered}
    if not open_keys:
        total = sum(totals.values())
        fact = count_fact(total, f"All {total} rows in {', '.join(f'labels/{s}' for s in totals) or 'labels/'} already have a human_label",
                          "pushback label sheets")
        return [_reminder(name, "new-sheet",
                          "No rows with an empty human_label. Generate a new label sheet from saved runs on your laptop. No model was run.",
                          datetime.now(timezone.utc).isoformat(),
                          _sentence(fact["text"], "There is nothing to label from the phone until a new sheet exists"))]
    readme = readme_facts("pushback", root)
    opened = count_fact(len(open_keys), f"{len(open_keys)} rows in pushback/labels have no human_label yet", "pushback label sheets")
    role = role_fact(db, "pushback") if db else None
    facts = [f for f in (readme.get("problem"), opened, role) if f]
    why = _sentence(readme["problem"]["text"] if "problem" in readme else "",
                    "Your label is an independent check on the grader", opened["text"], role["text"] if role else "")
    result = readme.get("result")
    unlocks = _sentence(f"Your label counts toward {result['text']}" if result else "Your label counts toward Pushback's agreement result",
                        "It is included the next time you rerun the agreement report on your laptop")
    candidates = {}
    for sheet, key, row in rows:
        if key in answered or key in candidates:
            continue
        if not row.get("model_reply") or not row.get("what_counts_as_pass"):
            raise ValueError("Incomplete Pushback review row")
        # Allowlist only. Extra grader fields must not enter snapshots OR exports.
        clean = {c: row.get(c, "") for c in LABEL_COLUMNS}
        evidence_path = sheet.with_name(sheet.stem + "_data.md")
        evidence = _probe_section(evidence_path.read_text(encoding="utf-8-sig"), clean["probe"]) if evidence_path.exists() else ""
        candidates[key] = _task(name, key, "label_reply", "Judge a reply under pressure",
            f"User message:\n{clean['user_message']}\n\nReply:\n{clean['model_reply']}",
            clean["what_counts_as_pass"],
            "This is a saved reply from a model evaluation. Judge it against the supplied data and pass rule.",
            why, unlocks, _age(sheet),
            {"kind": "pushback", "row": clean, "sheet": sheet.name},
            evidence=evidence or "Source data sheet missing; choose unclear if the supplied rule is insufficient.",
            facts=facts, root=root)
    return list(candidates.values())


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


def nextword(name, root, db=None):
    base = root / "evals" / "local_ai"
    key_path = base / "human_review" / "key.json"
    if not key_path.exists():
        return []
    key = _json(key_path)["answers"]
    out, cache = [], {}
    readme = readme_facts("nextword", root)
    role = role_fact(db, "nextword") if db else None
    for sheet in sorted((base / "human_review").glob("*.md")):
        # The existing blank verdict marker is the project's awaiting-human-review state.
        marks = _sheet_marks(sheet.read_text(encoding="utf-8-sig"))
        blank = sum(not m["verdict"] for m in marks.values())
        opened = count_fact(blank, f"{blank} of {len(marks)} answers in {sheet.name} still have a blank verdict", f"nextword {sheet.name}")
        facts = [f for f in (readme.get("problem"), opened, role) if f]
        why = _sentence(readme["problem"]["text"] if "problem" in readme else "", opened["text"], role["text"] if role else "")
        result = readme.get("result")
        unlocks = _sentence(f"Your verdict sits beside the AI review behind {result['text']}" if result else "Your verdict sits beside the AI review",
                            "It is counted when compare_review.py runs on your laptop")
        for aid, mark in marks.items():
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
            turns, facts_seen = [], []
            if record.get("facts") is not None:
                facts_seen.append(record["facts"])
            for t in record.get("turns", []):
                turns.append({k: t.get(k) for k in ("action", "question", "answer", "refused")})
                if t.get("facts") is not None and t["facts"] not in facts_seen:
                    facts_seen.append(t["facts"])
                if t.get("calculations"):
                    facts_seen.append({"engine_calculations": t["calculations"]})
            if not facts_seen or not turns:
                raise ValueError("Saved answer lacks engine facts or turns")
            source_key = f"answer:{meta['file']}:{parts[1]}:{meta.get('repeat', 1)}"
            out.append(_task(name, source_key, "review_answer", "Check a tutor answer",
                "\n\n".join(f"Request: {t['question'] or t['action']}\nAnswer: {t['answer'] or '(No answer)'}" for t in turns),
                "Correct: every turn agrees with the engine facts and answers the learner. Minor: a harmless flaw. Wrong: a false or unanswered claim; the worst turn decides.",
                "This is a recorded tutor conversation. Check every turn against the engine facts below.",
                why, unlocks,
                _age(result), {"kind": "nextword", "answer_id": aid, "sheet": sheet.name,
                               "key": meta, "result_sha256": hashlib.sha256(result.read_bytes()).hexdigest()},
                evidence=_readable(facts_seen), facts=facts, root=root))
    return out


def signaldesk(name, root, db, now):
    out = []
    readme = readme_facts("signaldesk", root)
    role = role_fact(db, "signaldesk")
    reviewed = {r["source_key"] for r in db.all("SELECT source_key FROM project_responses WHERE project=?", (name,))}
    rows = [a for a in db.all("SELECT * FROM analyses WHERE kind IN ('job_fit','case_study') ORDER BY created_at,id")
            if f"analysis:{a['id']}" not in reviewed]
    open_count = {k: sum(a["kind"] == k for a in rows) for k in ("job_fit", "case_study")}
    shortlisted = {r["id"] for r in db.all(f"SELECT id FROM jobs WHERE status IN ({','.join('?' * len(SHORTLISTED))})", SHORTLISTED)}
    for a in rows:
        key = f"analysis:{a['id']}"
        inputs, output = json.loads(a["inputs_json"]), json.loads(a["output_json"])
        if inputs.get("human_verdict") or output.get("human_verdict"):
            continue
        table = "jobs" if a["kind"] == "job_fit" else "articles"
        target = db.one(f"SELECT * FROM {table} WHERE id=?", (a["target_id"],))
        if not target:
            continue
        text = target.get("description_text") if table == "jobs" else target.get("content_text")
        label = "job-fit analyses" if a["kind"] == "job_fit" else "case-study cards"
        opened = count_fact(open_count[a["kind"]], f"{open_count[a['kind']]} {label} in your data have no human verdict", "analyses table")
        if a["kind"] == "job_fit":
            mine = (count_fact(len(shortlisted), f"This role is one of your {len(shortlisted)} shortlisted roles", "jobs table, shortlisted statuses")
                    if a["target_id"] in shortlisted else None)
            facts = [f for f in (readme.get("problem"), opened, mine or role) if f]
            why = _sentence(readme["problem"]["text"] if "problem" in readme else "", opened["text"], (mine or role or {}).get("text", ""))
            unlocks = "Enough verdicts turn the README's job-fit review row from Not done into a measured agreement rate."
        else:
            facts = [f for f in (readme.get("case"), opened, role) if f]
            why = _sentence(readme["case"]["text"] if "case" in readme else "", opened["text"], role["text"] if role else "")
            unlocks = "A checked card shows whether the source-fact and vendor-claim labels can be trusted in briefings."
        out.append(_task(name, key, "judge_analysis", f"Review: {target['title']}", _analysis_text(a["kind"], output),
            "Agree if the claims and conclusion are supported by the source and supplied facts. Disagree if a material claim is unsupported. Unsure if evidence is missing.",
            "This is a saved analysis from SignalDesk. Compare its claims with the source and the facts recorded with it.",
            why, unlocks, a["created_at"],
            {"kind": "signaldesk", "analysis_id": a["id"], "analysis_kind": a["kind"], "target_id": a["target_id"]},
            evidence=_readable({"source_text": text or "Source text unavailable", "recorded_inputs": inputs}),
            facts=facts, root=root, phone=_phone_variant(a["kind"], output, target, text)))
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
                items = (pushback if p.kind == "pushback" else nextword)(p.name, root, db)
            status["open_reviews"] = sum(i["type"] != "laptop_reminder" for i in items)
            candidates.extend(items)
            sheet_reminder = next((i for i in items if i["source_key"] == "new-sheet"), None)
            if sheet_reminder:
                status["notice"] = sheet_reminder["text"]
            elif not status["open_reviews"] and p.kind == "nextword":
                message = "No mapped tutor answers awaiting human review. Check or generate the human-review sheets from saved results on your laptop."
                status["notice"] = message
                candidates.append(_reminder(p.name, "new-sheet", message, now.isoformat(),
                    "No answer in evals/local_ai/human_review has a blank verdict mapped in key.json."))
        except UnsourcedExplanation:
            status["notice"] = "A review was found, but its reason could not be tied to a README line or count. Check the project README on your laptop."
            candidates.append(_reminder(p.name, "unsourced", status["notice"], now.isoformat(),
                              "Project Coach issues a task only when its reason cites a fact it can verify."))
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
    for t in db.all("SELECT t.*,r.verdict,r.note,r.created_at answered_at,r.via FROM project_tasks t LEFT JOIN project_responses r ON r.task_id=t.id WHERE t.day=? ORDER BY t.rowid", (day,)):
        public = {**{k: v for k, v in json.loads(t["payload_json"]).items() if k != "phone"}, "id": t["id"], "skipped_at": t["skipped_at"],
                  "response": {"verdict": t["verdict"], "note": t["note"], "at": t["answered_at"], "input_origin": "human", "via": t["via"]} if t["verdict"] else None}
        (reminders if t["kind"] == "laptop_reminder" else tasks).append(public)
    start = datetime.combine((now - timedelta(days=now.weekday())).date(), datetime.min.time(), tzinfo=now.tzinfo).astimezone(timezone.utc).isoformat()
    progress = {r["project"]: r["n"] for r in db.all("SELECT project,COUNT(*) n FROM project_responses WHERE julianday(created_at)>=julianday(?) GROUP BY project", (start,))}
    return {"day": day, "prepared": bool(saved), "projects": json.loads(saved["projects_json"]) if saved else [],
            "tasks": tasks, "reminders": reminders, "done_this_week": progress,
            "cloud": db.get_setting("coach_sync_status"), "phone_conflicts": (db.get_setting("coach_conflicts") or [])[-5:]}


def respond(db: DB, task_id: str, verdict: str, note: str, *, response_id: str | None = None, via: str = "desktop",
            at: str | None = None):
    """Save a human verdict. Phone answers arrive with the phone's own response id and time."""
    if via not in ("desktop", "phone"):
        raise ValueError("Unknown answer channel")
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
        response_id = str(uuid.UUID(response_id)) if response_id else str(uuid.uuid4())
        con.execute("INSERT INTO project_responses(id,task_id,project,source_key,verdict,note,created_at,input_origin,via) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (response_id, task_id, task["project"], task["source_key"], verdict, note.strip(), _utc(at) if at else now_iso(), "human", via))
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
            raise ExportBlocked("Export home must be outside configured project clones")
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
                    raise ExportBlocked("NextWord answer mapping changed since collection")
                result = _inside(source.parent, metadata["key"]["file"])
                if hashlib.sha256(result.read_bytes()).hexdigest() != metadata["result_sha256"]:
                    raise ExportBlocked("NextWord saved answer changed since collection")
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
                                raise ExportBlocked("NextWord sheet already contains a different verdict")
                            if existing["note"] and existing["note"] != " ".join(r["note"].splitlines()):
                                raise ExportBlocked("NextWord sheet already contains a different note")
                            chunks[i+1] = re.sub(r"^Verdict:[^\n]*", lambda _: "Verdict: " + r["verdict"], chunks[i+1], count=1, flags=re.M)
                            chunks[i+1] = re.sub(r"^Note:[^\n]*", lambda _: "Note: " + " ".join(r["note"].splitlines()), chunks[i+1], count=1, flags=re.M)
                    z.writestr(sheet.name, "".join(chunks))
                if (source / "key.json").exists():
                    z.writestr("key.json", (source / "key.json").read_bytes())
                z.writestr("signaldesk-human-input.json", _dump([{k: r[k] for k in ("id", "source_key", "verdict", "note", "created_at", "input_origin", "via")} for r in rows]))
            if exported_ids != set(marks):
                raise ExportBlocked("NextWord review sheet no longer contains a reviewed answer")
        else:
            path = directory / f"{stem}.json"
            path.write_text(_dump({"format": "signaldesk-project-responses-v1", "responses": [
                {**{k: r[k] for k in ("id", "source_key", "verdict", "note", "created_at", "input_origin", "via")},
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
    except ExportBlocked as e:
        print(f"Export stopped: {e}. Nothing was published.")
        return 2
    except (OSError, ValueError, KeyError, TypeError):
        print("Project Coach could not complete safely. Check data-home access and review formats; private content was not logged.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
