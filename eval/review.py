"""Human review of job-fit analyses: export a sheet to fill in, then score it.

  python -m eval.review export [--n 20] [--run FILE ...] [--no-saved] [--home DIR]
      Writes <data dir>/evals/review-<time>.csv. One row per (job, model): the requirement text sent
      to the model, the profile facts sent, the model's essential/preferred split, cited fact ids,
      gaps, unknowns and match label, plus empty columns for your verdicts. Rows come from the N most
      recent saved job-fit analyses in the app's database (opened read-only), and from any model or
      replay files written by `python -m eval.run_eval` (--run). The same job in two files, for
      example a 4B run and a 9B run, gets the same item id, so the two can be compared.

  python -m eval.review score SHEET.csv
      Counts your verdicts per model and, where two models answered the same item, puts your verdicts
      side by side. Writes score-<sheet name>.md next to the sheet.

Nothing here calls a model, a network or changes the app's database. The sheet is written to the
data folder, never into the repository. Rubric: docs/HUMAN_REVIEW.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from signaldesk import analysis
from signaldesk.config import load_config

REPO = Path(__file__).resolve().parent.parent
CASES = json.loads((Path(__file__).resolve().parent / "cases.json").read_text(encoding="utf-8"))

MATCH_VERDICTS = ("right", "too generous", "too harsh")
FACT_VERDICTS = ("yes", "partly", "no")
VERDICT_COLUMNS = ["verdict_match_label", "verdict_cited_facts", "note"]
COLUMNS = ["review_id", "item", "model", "source", "job_title", "employer", "analysed_at", "requirement_text_sent", "requirement_text_status",
           "profile_facts_sent", "essential", "preferred", "cited_facts", "gaps", "unknowns", "match_label", "checks_notes", *VERDICT_COLUMNS]


class ReviewError(Exception):
    pass


# ---------------------------------------------------------------- shared formatting
def source_text(prompt: str) -> str:
    """The delimited source block of a prompt: exactly the job text the model was given."""
    start, end = prompt.find("<<<SOURCE\n"), prompt.rfind("\nSOURCE>>>")
    return prompt[start + len("<<<SOURCE\n"):end] if start >= 0 and end > start else ""


def _reqs(items: list[dict]) -> str:
    return "\n".join(f"- {r.get('req')} | \"{r.get('quote')}\" ({'quote found' if r.get('quote_found') else 'quote NOT found'})" for r in items)


def _cited(evidence: list[dict]) -> str:
    return "\n".join(f"- {', '.join(e.get('facts') or [])}: {e.get('req')} ({e.get('note')})" for e in evidence)


def _facts(facts: list[dict]) -> str:
    return "\n".join(f"{f['id']}: {f['text']}" for f in facts)


def row(*, item: str, model: str, source: str, title: str, employer: str, at: str, sent: str, sent_status: str, facts: list[dict],
        out: dict, notes: list[str]) -> dict:
    return {"item": item, "model": model, "source": source, "job_title": title, "employer": employer, "analysed_at": at,
            "requirement_text_sent": sent, "requirement_text_status": sent_status, "profile_facts_sent": _facts(facts),
            "essential": _reqs(out.get("essential", [])), "preferred": _reqs(out.get("preferred", [])),
            "cited_facts": _cited(out.get("evidence", [])), "gaps": "\n".join(f"- {g}" for g in out.get("gaps", [])),
            "unknowns": "\n".join(f"- {u}" for u in out.get("unknowns", [])), "match_label": out.get("match", ""),
            "checks_notes": "\n".join(notes), **{c: "" for c in VERDICT_COLUMNS}}


# ---------------------------------------------------------------- rows from the app's database
def _readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise ReviewError(f"No database at {db_path}.")
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _rebuild_sent(job: dict, facts: list[dict], not_claimed: list[str], budget: int, chars_sent: int | None) -> tuple[str, str]:
    """Rebuild the requirement excerpt with the same code the app used. A retry sends less text
    (budget x 0.75 per earlier attempt), so try each attempt's budget and keep the one whose length
    matches what the app recorded. Exact only when the length matches."""
    tried = []
    for attempt in range(4):
        prompt, _cov = analysis.job_prompt(job, {"facts": facts, "not_claimed": not_claimed}, int(budget * 0.75 ** attempt))
        text = source_text(prompt)
        tried.append(text)
        if chars_sent is not None and len(text) == chars_sent:
            return text, "rebuilt; same length as the text the app sent" + (f" (attempt {attempt + 1})" if attempt else "")
    return tried[0], "REBUILT FROM TODAY'S JOB TEXT: the length differs from what was sent, so the job or settings changed since"


def saved_rows(home: Path, n: int) -> list[dict]:
    cfg = load_config(home)
    profile = json.loads(cfg.profile_path.read_text(encoding="utf-8")) if cfg.profile_path.exists() else {}
    con = _readonly(cfg.db_path)
    try:
        rows = con.execute(
            "SELECT a.*, j.title, j.employer, j.location_raw, j.description_text, j.content_hash FROM analyses a JOIN jobs j ON j.id = a.target_id "
            "WHERE a.kind = 'job_fit' AND a.target_type = 'job' AND a.id = (SELECT MAX(b.id) FROM analyses b WHERE b.kind = 'job_fit' "
            "AND b.target_id = a.target_id) ORDER BY a.created_at DESC, a.id DESC LIMIT ?", (n,)).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        inputs = json.loads(r["inputs_json"])
        facts = inputs.get("facts_sent") or []
        job = {"title": r["title"], "employer": r["employer"], "location_raw": r["location_raw"], "description_text": r["description_text"] or ""}
        sent, status = _rebuild_sent(job, facts, profile.get("not_claimed", []), cfg.model.prompt_char_budget,
                                     (inputs.get("coverage") or {}).get("chars_sent"))
        out.append(row(item=f"saved-job-{r['target_id']}", model=r["model_id"], source="app database", title=r["title"], employer=r["employer"],
                       at=r["created_at"], sent=sent, sent_status=status, facts=facts, out=json.loads(r["output_json"]),
                       notes=json.loads(r["validation_json"]).get("notes", [])))
    return out


# ---------------------------------------------------------------- rows from eval run files
def run_rows(path: Path) -> list[dict]:
    """job_fit results from a `run_eval model` or `run_eval replay` file. Runs written before this
    tool recorded only the output, so their sent text is marked as not recorded."""
    data = json.loads(path.read_text(encoding="utf-8"))
    model, out = data.get("model", "unknown"), []
    for r in data.get("results", []):
        if r.get("kind") != "job_fit" or not r.get("ok"):
            continue
        sent = r.get("sent") or {}
        case = next((c for c in CASES["jobs"] if c["id"] == r["item"]), None)
        out.append(row(item=r["item"], model=model, source=path.name, title=r.get("title", ""), employer=sent.get("employer") or (case or {}).get("employer", ""),
                       at=data.get("at", ""), sent=sent.get("requirements", ""),
                       sent_status="recorded by the run" if "requirements" in sent else "NOT RECORDED: this run predates recording; rerun it to see the text",
                       facts=sent.get("facts", []), out=r.get("output") or {}, notes=(r.get("validation") or {}).get("notes", [])))
    return out


# ---------------------------------------------------------------- export
def _outside_repo(path: Path) -> Path:
    p = path.resolve()
    if p == REPO or REPO in p.parents:
        raise ReviewError(f"Refusing to write {p}: review sheets hold your data and must stay outside the repository. Use a data folder.")
    return p


def export(home: Path | None, n: int, runs: list[str], include_saved: bool = True) -> Path:
    cfg = load_config(home)
    rows = saved_rows(cfg.home, n) if include_saved and n > 0 else []
    for r in runs:
        rows += run_rows(Path(r))
    if not rows:
        raise ReviewError("Nothing to review: no saved job-fit analyses and no job_fit results in the given files.")
    rows.sort(key=lambda x: (x["item"], x["model"], x["source"]))
    for i, r in enumerate(rows, 1):
        r["review_id"] = f"R{i:03d}"
    path = _outside_repo(cfg.evals_dir / f"review-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv")
    with path.open("w", encoding="utf-8-sig", newline="") as f:          # utf-8-sig: Excel opens it with the right characters
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


# ---------------------------------------------------------------- score
def _norm(v: str | None) -> str:
    return " ".join((v or "").strip().lower().split())


def score(sheet: str | Path) -> tuple[str, Path]:
    sheet = Path(sheet)
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    missing = [c for c in ("item", "model", *VERDICT_COLUMNS) if rows and c not in rows[0]]
    if not rows or missing:
        raise ReviewError(f"{sheet.name} is not a review sheet" + (f" (missing columns: {', '.join(missing)})" if missing else " (no rows)") + ".")
    per_model: dict[str, dict[str, Counter]] = defaultdict(lambda: {"match": Counter(), "facts": Counter()})
    invalid = []
    by_item: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        m, fct = _norm(r["verdict_match_label"]), _norm(r["verdict_cited_facts"])
        for value, allowed, col in ((m, MATCH_VERDICTS, "verdict_match_label"), (fct, FACT_VERDICTS, "verdict_cited_facts")):
            if value and value not in allowed:
                invalid.append(f"{r.get('review_id', '')} ({r['item']}, {r['model']}): {col} = \"{value}\" (use {' / '.join(allowed)})")
        per_model[r["model"]]["match"][m if m in MATCH_VERDICTS else ("not reviewed" if not m else "invalid")] += 1
        per_model[r["model"]]["facts"][fct if fct in FACT_VERDICTS else ("not reviewed" if not fct else "invalid")] += 1
        by_item[r["item"]].setdefault(r["model"], r)

    lines = [f"# Human review: {sheet.name}", "", "Your verdicts, counted. Nothing here is computed by a model.", "",
             "## Match label", "", "| Model | Rows | " + " | ".join(MATCH_VERDICTS) + " | not reviewed | invalid |", "|---|---|" + "---|" * 5]
    for model, c in sorted(per_model.items()):
        mc = c["match"]
        lines.append(f"| {model} | {sum(mc.values())} | " + " | ".join(str(mc[v]) for v in (*MATCH_VERDICTS, "not reviewed", "invalid")) + " |")
    lines += ["", "## Cited facts relevant", "", "| Model | Rows | " + " | ".join(FACT_VERDICTS) + " | not reviewed | invalid |", "|---|---|" + "---|" * 5]
    for model, c in sorted(per_model.items()):
        fc = c["facts"]
        lines.append(f"| {model} | {sum(fc.values())} | " + " | ".join(str(fc[v]) for v in (*FACT_VERDICTS, "not reviewed", "invalid")) + " |")

    shared = {item: ms for item, ms in by_item.items() if len(ms) >= 2}
    models = sorted({m for ms in shared.values() for m in ms})
    lines += ["", "## Same item, two models", ""]
    if not shared:
        lines.append("No item has rows from two different models. Export a 4B run and a 9B run together to compare them.")
    else:
        head = "| Item | Job | " + " | ".join(f"{m}: label / your verdict / facts" for m in models) + " |"
        lines += [head, "|---|---|" + "---|" * len(models)]
        for item, ms in sorted(shared.items()):
            cells = []
            for m in models:
                r = ms.get(m)
                cells.append(f"{r['match_label']} / {_norm(r['verdict_match_label']) or '-'} / {_norm(r['verdict_cited_facts']) or '-'}" if r else "not run")
            title = next(iter(ms.values()))["job_title"].replace("|", "/")
            lines.append(f"| {item} | {title} | " + " | ".join(c.replace("|", "/") for c in cells) + " |")
        agree = [ms for ms in shared.values() if len({_norm(r["verdict_match_label"]) for r in ms.values()} - {""}) == 1
                 and all(_norm(r["verdict_match_label"]) for r in ms.values())]
        right = {m: sum(_norm(ms[m]["verdict_match_label"]) == "right" for ms in shared.values() if m in ms) for m in models}
        lines += ["", f"On the {len(shared)} shared item(s), you rated the label right: " + ", ".join(f"{m} {right[m]}" for m in models) +
                  f". Same verdict for both models on {len(agree)}."]
    if invalid:
        lines += ["", "## Entries not counted", "", *(f"- {x}" for x in invalid)]
    report = "\n".join(lines) + "\n"
    out = _outside_repo(sheet.with_name(f"score-{sheet.stem}.md"))
    out.write_text(report, encoding="utf-8")
    return report, out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.review", description="Human review of job-fit analyses.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="write a review sheet to <data dir>/evals")
    e.add_argument("--n", type=int, default=20, help="how many saved job-fit analyses to include (most recent first)")
    e.add_argument("--run", action="append", default=[], help="also include job_fit results from an eval.run_eval model or replay file")
    e.add_argument("--no-saved", action="store_true", help="only the --run files, not the app's saved analyses")
    e.add_argument("--home", help="data directory (default: %%SIGNALDESK_HOME%% or D:/LocalAI/signaldesk)")
    s = sub.add_parser("score", help="count the verdicts in a filled sheet")
    s.add_argument("sheet")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "export":
            path = export(Path(args.home) if args.home else None, args.n, args.run, include_saved=not args.no_saved)
            print(f"Saved {path}\nFill in verdict_match_label ({' / '.join(MATCH_VERDICTS)}), verdict_cited_facts ({' / '.join(FACT_VERDICTS)}) "
                  "and note, save as CSV, then run:  python -m eval.review score " + str(path))
            return 0
        report, out = score(args.sheet)
        print(report)
        print(f"Saved {out}")
        return 0
    except ReviewError as err:
        print(err)
        return 2


if __name__ == "__main__":
    sys.exit(main())
