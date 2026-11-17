"""Project Coach cloud copy: push today's phone-safe cards, pull phone answers.

Runs inside the existing delivery loop with the laptop's server-only key. Outbound HTTPS only.
Phone answers go through projects.respond, so they obey the same rules as desktop answers:
allowed verdicts, read-only reminders, one immutable answer per item. A phone answer that
disagrees with an existing answer is recorded as a conflict; the existing answer is kept.
Provider responses are never logged (they can echo payloads or credentials).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta

from . import projects
from .db import DB, now_iso

TASKS = "/rest/v1/signaldesk_project_tasks"
RESPONSES = "/rest/v1/signaldesk_project_responses"
KEEP_DAYS = 7


def _status(db: DB, task: dict) -> str:
    if db.scalar("SELECT 1 FROM project_responses WHERE task_id=?", (task["id"],)):
        return "answered"
    return "skipped" if task["skipped_at"] else "open"


def pull(db: DB, client, base: str, headers: dict, owner: str) -> dict:
    """Import phone answers not yet imported. Returns counts by result."""
    r = client.get(base + RESPONSES, headers=headers, params={
        "select": "id,task_id,verdict,note,answered_at", "owner_id": "eq." + owner,
        "imported_at": "is.null", "order": "received_at.asc", "limit": "200"})
    r.raise_for_status()
    counts = {"saved": 0, "duplicate": 0, "conflict": 0, "rejected": 0}
    conflicts = db.get_setting("coach_conflicts") or []
    for row in r.json():
        try:
            res = projects.respond(db, row["task_id"], row["verdict"], row.get("note") or "",
                                   response_id=row["id"], via="phone", at=row.get("answered_at"))
            result = "duplicate" if res["duplicate"] else "saved"
        except ValueError as e:
            result = "conflict" if "already has a human verdict" in str(e) else "rejected"
            if result == "conflict":
                task = db.one("SELECT project, payload_json FROM project_tasks WHERE id=?", (row["task_id"],))
                conflicts.append({"at": now_iso(), "task_id": row["task_id"], "project": task["project"] if task else None,
                                  "phone_verdict": row["verdict"],
                                  "kept": db.scalar("SELECT r.verdict FROM project_responses r JOIN project_tasks t ON t.project=r.project "
                                                    "AND t.source_key=r.source_key WHERE t.id=?", (row["task_id"],))})
        counts[result] += 1
        u = client.patch(base + RESPONSES, headers={**headers, "Prefer": "return=minimal"},
                         params={"id": "eq." + row["id"], "owner_id": "eq." + owner},
                         json={"imported_at": now_iso(), "import_result": result})
        u.raise_for_status()
    db.set_setting("coach_conflicts", conflicts[-50:])
    return counts


def push(db: DB, client, base: str, headers: dict, owner: str, today: date) -> int:
    """Upload today's and yesterday's tasks (status included); remove cloud tasks older than a week."""
    sent = 0
    days = (today.isoformat(), (today - timedelta(days=1)).isoformat())
    for t in db.all("SELECT * FROM project_tasks WHERE day IN (?,?) ORDER BY rowid", days):
        card = projects.phone_card(json.loads(t["payload_json"]))
        row = {"id": t["id"], "owner_id": owner, "day": t["day"], "project": t["project"], "kind": t["kind"],
               "status": _status(db, t), "payload": card, "created_at": t["created_at"], "synced_at": now_iso()}
        fingerprint = hashlib.sha256(json.dumps({k: v for k, v in row.items() if k != "synced_at"}, sort_keys=True).encode()).hexdigest()
        key = f"coach_task:{t['id']}"
        if db.get_setting(key) == fingerprint:
            continue
        r = client.post(base + TASKS, headers={**headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
                        params={"on_conflict": "id"}, json=row)
        r.raise_for_status()
        db.set_setting(key, fingerprint)
        sent += 1
    r = client.delete(base + TASKS, headers=headers,
                      params={"owner_id": "eq." + owner, "day": "lt." + (today - timedelta(days=KEEP_DAYS)).isoformat()})
    r.raise_for_status()
    return sent


def sync(cfg, db: DB, client, base: str, headers: dict, owner: str, now: datetime | None = None) -> dict:
    """One round: pull phone answers, then push task state. Daily preparation is Delivery.prepare_tick."""
    now = now or datetime.now().astimezone()
    pulled = pull(db, client, base, headers, owner)
    pushed = push(db, client, base, headers, owner, now.date())
    return {"pulled": pulled, "pushed": pushed}
