"""SQLite storage. One file in the data directory; one connection per thread."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  careers_url TEXT NOT NULL,
  ats TEXT NOT NULL,              -- greenhouse | lever | ashby | manual
  ats_id TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  verification TEXT,              -- how the board was tied to the employer
  last_attempt_at TEXT,
  last_success_at TEXT,
  last_error TEXT,
  last_error_at TEXT,
  last_warning TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  company_id INTEGER REFERENCES companies(id),
  employer TEXT NOT NULL,
  source TEXT NOT NULL,           -- greenhouse | lever | ashby | manual
  ext_id TEXT NOT NULL,
  title TEXT NOT NULL,
  location_raw TEXT,
  workplace_raw TEXT,
  description_text TEXT,
  content_hash TEXT NOT NULL,
  official_url TEXT,
  apply_url TEXT,
  published_at TEXT,              -- from the source, when it says
  first_seen_at TEXT NOT NULL,    -- when SignalDesk first saw it
  last_seen_at TEXT NOT NULL,
  last_verified_at TEXT,          -- last successful fetch that listed it
  listing_state TEXT NOT NULL DEFAULT 'open',   -- open | no_longer_listed
  closed_at TEXT,
  change_state TEXT NOT NULL DEFAULT 'new',     -- new | changed | unchanged
  changed_at TEXT,
  salary_text TEXT,
  salary_kind TEXT,
  location_class TEXT,
  location_evidence TEXT,
  role_family TEXT,
  bucket TEXT,                    -- candidate | review | outside
  bucket_reason TEXT,
  duplicate_of INTEGER,
  injection_flag INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'New',
  is_demo INTEGER NOT NULL DEFAULT 0,
  UNIQUE(source, ext_id)
);
CREATE INDEX IF NOT EXISTS jobs_company ON jobs(company_id, listing_state);
CREATE TABLE IF NOT EXISTS job_versions (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL REFERENCES jobs(id),
  content_hash TEXT NOT NULL,
  title TEXT, location_raw TEXT, salary_text TEXT, description_text TEXT,
  seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reading_sources (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  site_url TEXT,
  feed_url TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL,             -- substack | blog | engineering | vendor
  enabled INTEGER NOT NULL DEFAULT 1,
  verification TEXT,
  last_attempt_at TEXT,
  last_success_at TEXT,
  last_error TEXT,
  last_error_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY,
  source_id INTEGER REFERENCES reading_sources(id),
  source_name TEXT,
  source_kind TEXT,
  guid TEXT,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  published_at TEXT,
  retrieved_at TEXT NOT NULL,
  content_text TEXT,
  content_basis TEXT NOT NULL,    -- full | excerpt | metadata
  content_hash TEXT NOT NULL,
  dedupe_key TEXT NOT NULL,
  duplicate_of INTEGER,
  injection_flag INTEGER NOT NULL DEFAULT 0,
  case_candidate INTEGER NOT NULL DEFAULT 0,
  origin TEXT NOT NULL DEFAULT 'feed',   -- feed | manual
  is_demo INTEGER NOT NULL DEFAULT 0,
  UNIQUE(url)
);
CREATE INDEX IF NOT EXISTS articles_dedupe ON articles(dedupe_key);
CREATE TABLE IF NOT EXISTS analyses (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,             -- job_fit | reading_card | case_study | digest_action
  target_type TEXT NOT NULL,
  target_id INTEGER NOT NULL,
  cache_key TEXT NOT NULL UNIQUE,
  prompt_version TEXT NOT NULL,
  model_id TEXT NOT NULL,
  inputs_json TEXT NOT NULL,      -- versions and sizes that went into the cache key
  output_json TEXT NOT NULL,
  validation_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS analyses_target ON analyses(kind, target_type, target_id, created_at);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,            -- job_scout | reading_scout | case_analyst | digest_editor
  trigger TEXT NOT NULL,          -- manual | schedule | catch-up | regenerate
  group_id TEXT,
  status TEXT NOT NULL,           -- collecting | analysing | done | done_with_errors | failed | cancelled
  started_at TEXT NOT NULL,
  finished_at TEXT,
  stats_json TEXT NOT NULL DEFAULT '{}',
  log_json TEXT NOT NULL DEFAULT '[]',
  cancel_requested INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY,
  run_id INTEGER REFERENCES runs(id),
  kind TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id INTEGER NOT NULL,
  cache_key TEXT,
  status TEXT NOT NULL,           -- queued | running | done | cached | failed | cancelled | skipped
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  error TEXT,
  note TEXT,
  priority INTEGER NOT NULL DEFAULT 50,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  next_attempt_at TEXT
);
CREATE INDEX IF NOT EXISTS tasks_queue ON tasks(status, priority, id);
CREATE TABLE IF NOT EXISTS model_calls (
  id INTEGER PRIMARY KEY,
  task_id INTEGER,
  run_id INTEGER,
  purpose TEXT,
  model_requested TEXT,
  model_served TEXT,
  started_at TEXT NOT NULL,
  duration_ms INTEGER,
  tokens_in INTEGER,              -- only when the server reported them
  tokens_out INTEGER,
  finish_reason TEXT,
  ok INTEGER NOT NULL,
  error TEXT
);
CREATE TABLE IF NOT EXISTS digests (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'saved',   -- saved | archived
  run_id INTEGER,
  content_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY,
  item_type TEXT NOT NULL,
  item_id INTEGER NOT NULL,
  verdict TEXT NOT NULL,          -- useful | not_relevant | known | too_technical
  created_at TEXT NOT NULL,
  UNIQUE(item_type, item_id, verdict)
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class DB:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._local = threading.local()
        self.write_lock = threading.RLock()
        with self.write_lock:
            self.conn.executescript(SCHEMA)

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

    def all(self, sql: str, args: Iterable[Any] = ()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, tuple(args)).fetchall()]

    def one(self, sql: str, args: Iterable[Any] = ()) -> dict | None:
        r = self.conn.execute(sql, tuple(args)).fetchone()
        return dict(r) if r else None

    def scalar(self, sql: str, args: Iterable[Any] = ()) -> Any:
        r = self.conn.execute(sql, tuple(args)).fetchone()
        return r[0] if r else None

    def run(self, sql: str, args: Iterable[Any] = ()) -> int:
        with self.write_lock:
            cur = self.conn.execute(sql, tuple(args))
            if not getattr(self._local, "batch", False):
                self.conn.commit()
            return cur.lastrowid

    @contextmanager
    def batch(self):
        """Group many writes into one transaction (one commit instead of thousands)."""
        with self.write_lock:
            self._local.batch = True
            try:
                yield
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise
            finally:
                self._local.batch = False

    def insert(self, table: str, row: dict) -> int:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        return self.run(f"INSERT INTO {table} ({cols}) VALUES ({marks})", row.values())

    def update(self, table: str, row_id: int, values: dict) -> None:
        if not values:
            return
        sets = ", ".join(f"{k} = ?" for k in values)
        self.run(f"UPDATE {table} SET {sets} WHERE id = ?", [*values.values(), row_id])

    def get_setting(self, key: str, default: Any = None) -> Any:
        v = self.scalar("SELECT value_json FROM settings WHERE key = ?", (key,))
        return json.loads(v) if v is not None else default

    def set_setting(self, key: str, value: Any) -> None:
        self.run("INSERT INTO settings (key, value_json) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                 (key, json.dumps(value)))
