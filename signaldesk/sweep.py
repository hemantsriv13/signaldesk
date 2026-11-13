"""One entry point for manual and scheduled sweeps, and the lock they share.

The lock is a lease row in the database, taken inside an IMMEDIATE transaction, so two triggers
in the same app or in two processes (the app and a Windows scheduled task) produce one active
sweep. A lease older than `limits.sweep_lock_minutes` is treated as abandoned.

    python -m signaldesk sweep [--scope full|jobs|funding|contacts|reading|source:KEY] [--trigger schedule]

If SignalDesk is already running on this computer, the command asks it to sweep (one process, one
lock). Otherwise it runs the sweep itself, waits for it to finish, uploads any configured cloud
copies once, and exits.
"""
from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .db import DB, now_iso

LEASE_KEY = "run_lock"
SCOPES = {
    "full": ("funding_scout", "job_scout", "reading_scout", "case_analyst", "contact_scout", "digest_editor"),
    "jobs": ("job_scout", "contact_scout"),
    "funding": ("funding_scout",),
    "hiring": ("funding_scout", "job_scout"),   # discover companies and their boards, then collect every board
    "contacts": ("contact_scout",),
    "reading": ("reading_scout", "case_analyst"),
}


def agents_for(scope: str) -> tuple[str, ...]:
    if scope.startswith("source:"):
        return ("source_refresh",)
    if scope not in SCOPES:
        raise ValueError(f"Unknown scope '{scope}'. Use one of: {', '.join(SCOPES)} or source:KEY.")
    return SCOPES[scope]


HEARTBEAT_STALE_MINUTES = 10


def _expired(lease: dict, minutes: int) -> bool:
    """Abandoned when its process stopped beating (crash, restart, sleep) or it ran far too long."""
    now = datetime.now(timezone.utc)
    started = datetime.fromisoformat(lease["at"])
    beat = datetime.fromisoformat(lease.get("beat") or lease["at"])
    return now - started > timedelta(minutes=minutes) or now - beat > timedelta(minutes=HEARTBEAT_STALE_MINUTES)


def beat(db: DB, owner: str) -> None:
    with db.immediate() as conn:
        row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (LEASE_KEY,)).fetchone()
        lease = json.loads(row[0]) if row else None
        if lease and lease.get("owner") == owner:
            lease["beat"] = now_iso()
            conn.execute("UPDATE settings SET value_json = ? WHERE key = ?", (json.dumps(lease), LEASE_KEY))


def stale(lease: dict) -> bool:
    return _expired(lease, 10 ** 6)


def acquire(db: DB, owner: str, *, scope: str, trigger: str, minutes: int) -> dict | None:
    """Take the lease. Returns None when it was taken, else the lease that is holding it."""
    with db.immediate() as conn:
        row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (LEASE_KEY,)).fetchone()
        lease = json.loads(row[0]) if row else None
        if lease and lease.get("owner") and not _expired(lease, minutes):
            return lease
        new = {"owner": owner, "pid": os.getpid(), "host": socket.gethostname(), "at": now_iso(), "scope": scope, "trigger": trigger}
        conn.execute("INSERT INTO settings (key, value_json) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                     (LEASE_KEY, json.dumps(new)))
    return None


def release(db: DB, owner: str) -> None:
    with db.immediate() as conn:
        row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (LEASE_KEY,)).fetchone()
        lease = json.loads(row[0]) if row else None
        if lease and lease.get("owner") == owner:
            conn.execute("UPDATE settings SET value_json = ? WHERE key = ?", (json.dumps({"owner": None, "released_at": now_iso(), "last": lease}), LEASE_KEY))


def holder(db: DB) -> dict | None:
    lease = db.get_setting(LEASE_KEY)
    return lease if lease and lease.get("owner") else None


# ---------------------------------------------------------------- command line
def load_env_file(home: Path) -> int:
    """Load SIGNALDESK_* values from <data dir>/delivery.env, as scripts/start-v2.ps1 does."""
    path = home / "delivery.env"
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip().startswith("SIGNALDESK_"):
            os.environ.setdefault(k.strip(), v.strip())
            n += 1
    return n


def ask_running_app(port: int, scope: str, trigger: str) -> dict | None:
    """If SignalDesk is running here, let it do the sweep. None when no app answers."""
    try:
        r = httpx.post(f"http://127.0.0.1:{port}/api/sweep", json={"scope": scope, "trigger": trigger}, timeout=10,
                       headers={"origin": f"http://127.0.0.1:{port}"})
    except httpx.HTTPError:
        return None
    return r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}: {r.text[:200]}"}


def run_headless(cfg, scope: str, trigger: str, wait_minutes: int) -> int:
    from .delivery import Delivery
    from .engine import Engine
    from .llm import LocalModel
    from .netsafe import Fetcher
    from .seeds import seed

    load_env_file(cfg.home)
    db = DB(cfg.db_path)
    seed(db)
    engine = Engine(cfg, db, LocalModel(cfg.model), Fetcher(cfg.fetch))
    res = engine.start_all(trigger=trigger, scope=scope)
    if not res.get("started"):
        print(res.get("skipped") or "Nothing started.")
        return 0
    print(f"Sweep {res.get('group')} started ({scope}, {trigger}).", flush=True)
    deadline = time.monotonic() + wait_minutes * 60
    while time.monotonic() < deadline:
        if not engine.active_runs():
            break
        time.sleep(5)
    left = engine.active_runs()
    if left:
        print(f"Stopped waiting after {wait_minutes} min; {len(left)} run(s) still active. Queued analysis resumes the next time SignalDesk runs.")
    delivery = Delivery(engine)
    if delivery.config()["cloud_configured"]:
        delivery.tick()
        print(f"Cloud copies: {(db.get_setting('sync_status') or {}).get('state', 'not checked')}.")
    engine.stop_flag.set()
    print("Done.")
    return 0


def main(cfg, scope: str, trigger: str, wait_minutes: int) -> int:
    agents_for(scope)
    answer = ask_running_app(cfg.server.port, scope, trigger)
    if answer is not None:
        print(f"SignalDesk is running; it took the request: {json.dumps(answer)[:400]}")
        return 0 if "error" not in answer else 1
    return run_headless(cfg, scope, trigger, wait_minutes)
