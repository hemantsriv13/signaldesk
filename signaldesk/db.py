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


# Numbered, additive migrations. Each runs once (PRAGMA user_version) and never drops data, so
# existing briefings, jobs and their saved/applied/dismissed statuses survive the upgrade.
V3_TABLES = """
CREATE TABLE IF NOT EXISTS job_sources (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL REFERENCES jobs(id),
  source TEXT NOT NULL,              -- greenhouse | lever | ashby | wellfound | yc_jobs | <registry key> | manual
  url TEXT NOT NULL,                 -- canonical listing URL on that source
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  UNIQUE(source, url)
);
CREATE INDEX IF NOT EXISTS job_sources_job ON job_sources(job_id);
CREATE TABLE IF NOT EXISTS startups (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  name_key TEXT NOT NULL UNIQUE,     -- normalised name, the stable identity
  domain TEXT,                       -- official domain, only when a source linked it
  domain_evidence TEXT,
  india_link TEXT NOT NULL DEFAULT 'unknown',   -- india_based | hiring_in_india | unknown
  india_evidence TEXT,
  india_evidence_url TEXT,
  careers_url TEXT,
  careers_status TEXT NOT NULL DEFAULT 'unchecked',  -- unchecked | board_found | page_only | not_found | failed | no_domain
  careers_note TEXT,
  careers_checked_at TEXT,
  company_id INTEGER REFERENCES companies(id),
  watch_source TEXT,                 -- portfolio source that listed it (membership is not funding)
  watch_url TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  last_checked_at TEXT
);
CREATE TABLE IF NOT EXISTS funding_events (
  id INTEGER PRIMARY KEY,
  startup_id INTEGER NOT NULL REFERENCES startups(id),
  investor TEXT,
  round TEXT,                        -- normalised: seed | series_a | ... | unknown
  amount_text TEXT,                  -- as written; never converted
  announced_on TEXT NOT NULL,        -- date the announcement was published (YYYY-MM-DD)
  announcement_url TEXT NOT NULL,
  title TEXT,
  source TEXT NOT NULL,
  other_reports_json TEXT NOT NULL DEFAULT '[]',   -- syndicated reports of the same round
  first_seen_at TEXT NOT NULL,
  UNIQUE(announcement_url)
);
CREATE INDEX IF NOT EXISTS funding_by_startup ON funding_events(startup_id, announced_on);
CREATE TABLE IF NOT EXISTS announcements (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  title TEXT,
  listed_date TEXT,                  -- date shown next to the link, if any
  published_on TEXT,                 -- publication date from the page itself
  text TEXT,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | parsed | not_funding | needs_model | undated
  note TEXT,
  first_seen_at TEXT NOT NULL,
  processed_at TEXT
);
CREATE INDEX IF NOT EXISTS announcements_status ON announcements(source, status);
CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY,
  job_id INTEGER REFERENCES jobs(id),
  startup_id INTEGER REFERENCES startups(id),
  company TEXT NOT NULL,
  name TEXT NOT NULL,
  title TEXT,
  profile_url TEXT,                  -- only a URL the evidence page itself linked, or one you entered
  evidence_url TEXT,
  evidence_text TEXT,
  why TEXT,
  rank INTEGER NOT NULL DEFAULT 50,
  status TEXT NOT NULL DEFAULT 'verified',   -- verified | unresolved | added_by_you
  origin TEXT NOT NULL,              -- posting | team_page | announcement | manual | integration
  recipient_key TEXT NOT NULL,       -- dedupes one person across jobs
  verified_at TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(job_id, recipient_key)
);
CREATE INDEX IF NOT EXISTS contacts_job ON contacts(job_id);
CREATE TABLE IF NOT EXISTS outreach (
  id INTEGER PRIMARY KEY,
  contact_id INTEGER NOT NULL REFERENCES contacts(id),
  job_id INTEGER REFERENCES jobs(id),
  recipient_key TEXT NOT NULL,
  note_text TEXT NOT NULL,
  message_text TEXT NOT NULL,
  drafted_by TEXT NOT NULL,          -- template | model
  inputs_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'drafted',   -- drafted | sending | sent | failed | send_unknown | contacted
  channel TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  sent_at TEXT,
  UNIQUE(contact_id)
);
CREATE INDEX IF NOT EXISTS outreach_state ON outreach(state);
CREATE TABLE IF NOT EXISTS source_status (
  key TEXT PRIMARY KEY,
  last_attempt_at TEXT,
  last_success_at TEXT,
  last_error TEXT,
  last_error_at TEXT,
  last_counts_json TEXT NOT NULL DEFAULT '{}',
  checkpoint_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS jobs_bucket ON jobs(bucket, listing_state);
"""

V3_COLUMNS = {
    "jobs": [("role_families", "TEXT"), ("role_evidence", "TEXT"), ("role_source", "TEXT"),
             ("verification_state", "TEXT NOT NULL DEFAULT 'board'")],   # board | unverified
    "companies": [("origin", "TEXT NOT NULL DEFAULT 'seed'"), ("tie", "TEXT")],
    "runs": [("options_json", "TEXT NOT NULL DEFAULT '{}'")],
}


def _migrate_v3(conn: sqlite3.Connection) -> None:
    conn.executescript(V3_TABLES)
    for table, cols in V3_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    # Strategy roles used to sit inside the founder's-office family. Keep them selected for
    # anyone who had that family on, so the split does not silently drop matches.
    row = conn.execute("SELECT value_json FROM settings WHERE key = 'preferences'").fetchone()
    if row:
        prefs = json.loads(row[0])
        fams = prefs.get("role_families") or []
        if "founders_office" in fams and "strategy_ops" not in fams:
            prefs["role_families"] = [*fams, "strategy_ops"]
            conn.execute("UPDATE settings SET value_json = ? WHERE key = 'preferences'", (json.dumps(prefs),))


V4_TABLES = """
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,   -- SHA-256 of the cookie value; the value itself is never stored
  csrf TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  ip TEXT,
  user_agent TEXT
);
CREATE TABLE IF NOT EXISTS panel_tokens (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,   -- SHA-256; the token is shown once and never stored
  hint TEXT NOT NULL,                -- last 4 characters, to tell tokens apart
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS panel_batches (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL,
  created_at TEXT NOT NULL,
  pasted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS panel_items (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL,               -- the search you ran, e.g. "Founder's Office Bengaluru"
  job_id INTEGER NOT NULL REFERENCES jobs(id),
  first_batch_id INTEGER REFERENCES panel_batches(id),
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  times_pasted INTEGER NOT NULL DEFAULT 1,
  UNIQUE(label, job_id)              -- a job counts once per search, however often it is pasted
);
"""


def _migrate_v4(conn: sqlite3.Connection) -> None:
    conn.executescript(V4_TABLES)


MIGRATIONS = [_migrate_v3, _migrate_v4]


class DB:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._local = threading.local()
        self.write_lock = threading.RLock()
        with self.write_lock:
            self.conn.executescript(SCHEMA)
            self.migrate()

    def migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        for number, step in enumerate(MIGRATIONS, 1):
            if version < number:
                step(self.conn)
                self.conn.execute(f"PRAGMA user_version = {number}")
                self.conn.commit()

    @contextmanager
    def immediate(self):
        """One write transaction that also locks the database file against other processes."""
        with self.write_lock:
            self.conn.commit()
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise

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
