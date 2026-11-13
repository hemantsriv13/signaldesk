"""Sign-in, sessions, CSRF, login throttling and side-panel tokens. Standard library only.

* One owner password, stored as a salted scrypt hash in <data dir>/auth.json (never in the repo).
  Set it with:  python -m signaldesk auth set-password
* Sessions are random 32-byte tokens in a __Host- cookie (Secure, HttpOnly, SameSite=Strict) on the
  HTTPS entry point. Only their SHA-256 is stored. Idle and absolute expiry; logout deletes the row;
  "sign out other devices" deletes the rest.
* Writes with a session need the session's CSRF token in X-CSRF-Token and an allowed Origin.
* Failed sign-ins are limited per address and overall, in memory.
* Side-panel tokens are separate, revocable, expiring credentials that only reach /api/panel/*.
  The token is shown once; only its hash is stored. They never grant settings, exports, outreach,
  runs or any other route.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import DB, now_iso

COOKIE = "__Host-sd_session"
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- password
def set_password(path: Path, password: str) -> None:
    if len(password) < 12:
        raise ValueError("Use at least 12 characters.")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, maxmem=64 * 1024 * 1024, dklen=32, **SCRYPT)
    data = {"scrypt": {**SCRYPT, "salt": base64.b64encode(salt).decode(), "hash": base64.b64encode(digest).decode()}, "set_at": now_iso()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


def password_set(path: Path) -> bool:
    return path.exists()


def check_password(path: Path, password: str) -> bool:
    if not path.exists():
        return False
    s = json.loads(path.read_text(encoding="utf-8"))["scrypt"]
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(s["salt"]), n=s["n"], r=s["r"], p=s["p"],
                            maxmem=64 * 1024 * 1024, dklen=32)
    return hmac.compare_digest(digest, base64.b64decode(s["hash"]))


# ---------------------------------------------------------------- throttling
class Throttle:
    """At most `per_ip` failures per address and `overall` failures in total per window."""

    def __init__(self, per_ip: int = 5, overall: int = 30, window_s: int = 900):
        self.per_ip, self.overall, self.window = per_ip, overall, window_s
        self.fails: dict[str, deque] = {}
        self.all: deque = deque()
        self.lock = threading.Lock()

    def _trim(self, q: deque, now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()

    def blocked(self, ip: str) -> int:
        """Seconds to wait, or 0."""
        now = time.monotonic()
        with self.lock:
            q = self.fails.setdefault(ip, deque())
            self._trim(q, now)
            self._trim(self.all, now)
            if len(q) >= self.per_ip:
                return int(self.window - (now - q[0])) + 1
            if len(self.all) >= self.overall:
                return int(self.window - (now - self.all[0])) + 1
            return 0

    def fail(self, ip: str) -> None:
        now = time.monotonic()
        with self.lock:
            self.fails.setdefault(ip, deque()).append(now)
            self.all.append(now)

    def ok(self, ip: str) -> None:
        with self.lock:
            self.fails.pop(ip, None)


# ---------------------------------------------------------------- sessions
def create_session(db: DB, *, max_days: float, ip: str | None, user_agent: str | None) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = _now()
    db.insert("sessions", {"token_hash": _h(token), "csrf": csrf, "created_at": _iso(now), "last_seen_at": _iso(now),
                           "expires_at": _iso(now + timedelta(days=max_days)), "ip": ip, "user_agent": (user_agent or "")[:200]})
    return token, csrf


def session(db: DB, token: str | None, *, idle_hours: float) -> dict | None:
    if not token:
        return None
    row = db.one("SELECT * FROM sessions WHERE token_hash = ?", (_h(token),))
    if not row:
        return None
    now = _now()
    if datetime.fromisoformat(row["expires_at"]) < now or now - datetime.fromisoformat(row["last_seen_at"]) > timedelta(hours=idle_hours):
        db.run("DELETE FROM sessions WHERE id = ?", (row["id"],))
        return None
    if now - datetime.fromisoformat(row["last_seen_at"]) > timedelta(minutes=5):
        db.run("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (_iso(now), row["id"]))
    return row


def end_session(db: DB, token: str | None) -> None:
    if token:
        db.run("DELETE FROM sessions WHERE token_hash = ?", (_h(token),))


def revoke_sessions(db: DB, *, keep_id: int | None = None) -> int:
    n = db.scalar("SELECT COUNT(*) FROM sessions WHERE id IS NOT ?", (keep_id,))
    db.run("DELETE FROM sessions WHERE id IS NOT ?", (keep_id,))
    return n


def list_sessions(db: DB) -> list[dict]:
    return db.all("SELECT id, created_at, last_seen_at, expires_at, ip, user_agent FROM sessions ORDER BY last_seen_at DESC")


# ---------------------------------------------------------------- side-panel tokens
PANEL_PREFIX = "sdp_"


def create_panel_token(db: DB, label: str, days: int) -> tuple[int, str]:
    token = PANEL_PREFIX + secrets.token_urlsafe(32)
    now = _now()
    tid = db.insert("panel_tokens", {"label": (label or "Edge side panel")[:80], "token_hash": _h(token), "hint": token[-4:],
                                     "created_at": _iso(now), "expires_at": _iso(now + timedelta(days=days))})
    return tid, token


def panel_token(db: DB, token: str | None) -> dict | None:
    if not token or not token.startswith(PANEL_PREFIX):
        return None
    row = db.one("SELECT * FROM panel_tokens WHERE token_hash = ?", (_h(token),))
    if not row or row["revoked_at"] or datetime.fromisoformat(row["expires_at"]) < _now():
        return None
    if not row["last_used_at"] or _now() - datetime.fromisoformat(row["last_used_at"]) > timedelta(minutes=5):
        db.run("UPDATE panel_tokens SET last_used_at = ? WHERE id = ?", (now_iso(), row["id"]))
    return row


def revoke_panel_token(db: DB, tid: int | None = None) -> int:
    if tid is None:
        n = db.scalar("SELECT COUNT(*) FROM panel_tokens WHERE revoked_at IS NULL")
        db.run("UPDATE panel_tokens SET revoked_at = ? WHERE revoked_at IS NULL", (now_iso(),))
        return n
    db.run("UPDATE panel_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL", (now_iso(), tid))
    return 1


def list_panel_tokens(db: DB) -> list[dict]:
    return db.all("SELECT id, label, hint, created_at, expires_at, last_used_at, revoked_at FROM panel_tokens ORDER BY id DESC")


# Routes a side-panel token may reach. Everything else is refused for panel tokens, including
# settings, exports, outreach, contacts, runs, sources and token management.
def panel_route(path: str) -> bool:
    return path.startswith("/api/panel/") and not path.startswith("/api/panel/tokens")
