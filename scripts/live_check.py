"""Live check, read-only: fetch every enabled job board and feed once and ask the model server what it
is serving. Nothing is written to the database. Use it to tell a source problem from an app problem.

    .venv\\Scripts\\python scripts\\live_check.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signaldesk.config import load_config  # noqa: E402
from signaldesk.llm import LocalModel  # noqa: E402
from signaldesk.netsafe import FetchError, Fetcher  # noqa: E402
from signaldesk.seeds import COMPANIES, READING_SOURCES  # noqa: E402
from signaldesk.sources import ats, feeds  # noqa: E402


def main() -> int:
    cfg = load_config()
    fetcher = Fetcher(cfg.fetch)
    if cfg.db_path.exists():
        con = sqlite3.connect(cfg.db_path)
        companies = con.execute("SELECT name, ats, ats_id FROM companies WHERE enabled = 1 AND ats != 'manual'").fetchall()
        sources = con.execute("SELECT name, feed_url FROM reading_sources WHERE enabled = 1").fetchall()
    else:
        companies = [(n, a, i) for n, _u, a, i, on, _v in COMPANIES if on]
        sources = [(n, f) for n, _s, f, _k, on, _note in READING_SOURCES if on]
    failed = 0
    print("Job boards")
    for name, kind, board in companies:
        try:
            jobs = ats.fetch_board(fetcher, kind, board)
            print(f"  ok      {name}: {len(jobs)} listings")
        except FetchError as e:
            failed += 1
            print(f"  FAILED  {name}: {e}")
    print("Feeds")
    for name, url in sources:
        try:
            items = feeds.fetch_feed(fetcher, url, 5)
            basis = {b: sum(i['content_basis'] == b for i in items) for b in ("full", "excerpt", "metadata")}
            print(f"  ok      {name}: {len(items)} items {basis}")
        except FetchError as e:
            failed += 1
            print(f"  FAILED  {name}: {e}")
    st = LocalModel(cfg.model).status()
    print(f"Model server: {st['message']}")
    print(f"\n{failed} source(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
