"""Shared test fixtures. Everything here is mocked: no network, no model server.
Live verification is separate (scripts/live_check.py and the README's checks)."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import httpx
import pytest

from signaldesk.config import load_config
from signaldesk.db import DB
from signaldesk.engine import Engine
from signaldesk.llm import LocalModel
from signaldesk.netsafe import Fetcher

CASES = json.loads((Path(__file__).resolve().parent.parent / "eval" / "cases.json").read_text(encoding="utf-8"))


def public_resolver(host, port, proto=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


class FakeModel:
    """A stand-in for Colibri. `replies` maps a purpose keyword to JSON (or a callable)."""

    def __init__(self, served="qwen3-4b-instruct-2507-q4km"):
        self.served = served
        self.up = True
        self.calls: list[dict] = []
        self.replies: dict = {}
        self.fail_next = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("refused", request=request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": self.served, "context_length": 2048}]})
        body = json.loads(request.content)
        self.calls.append(body)
        if self.fail_next:
            self.fail_next -= 1
            return httpx.Response(500, text="engine error")
        prompt = body["messages"][1]["content"]
        reply = None
        for key, value in self.replies.items():
            if key in prompt:
                reply = value(prompt) if callable(value) else value
                break
        if reply is None:
            reply = {"essential": [], "preferred": [], "evidence": [], "gaps": [], "unknowns": [], "match": "unknown", "summary": "s",
                     "main_argument": "a", "evidence_items": [], "why_it_matters": "w", "limitations": "l", "concept": {"term": "t", "explanation": "e"},
                     "kind": "opinion", "action": "Do it", "ref": "J1"}
        return httpx.Response(200, json={"model": self.served, "choices": [{"message": {"content": json.dumps(reply)}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 20}})


@pytest.fixture
def home(tmp_path):
    return tmp_path


@pytest.fixture
def fake_model():
    return FakeModel()


@pytest.fixture
def boards():
    """Fake job boards and feeds: tests set `boards.routes[url_prefix] = (status, payload)`."""
    class Boards:
        routes: dict = {}
        hits: list = []

        def handler(self, request):
            url = str(request.url)
            self.hits.append(url)
            for prefix, (status, payload) in self.routes.items():
                if url.startswith(prefix):
                    if isinstance(payload, (dict, list)):
                        return httpx.Response(status, json=payload)
                    return httpx.Response(status, content=payload.encode() if isinstance(payload, str) else payload,
                                          headers={"content-type": "application/rss+xml" if "feed" in prefix else "text/html"})
            return httpx.Response(404, text="not found")
    b = Boards()
    b.routes, b.hits = {}, []
    return b


TEST_PROFILE = {"name": "", "summary": "", "facts": [{"id": f"P{i}", "text": t} for i, t in enumerate([
    "Analyst for four years at a consumer goods company.", "Worked on finance and supply-chain analytics.", "Built data products.",
    "Presented to business stakeholders.", "Uses SQL, Python and BI tools.", "Worked with cross-functional teams."], 1)],
    "not_claimed": ["Experience as a production machine learning engineer."]}


@pytest.fixture
def engine(home, fake_model, boards):
    (home / "profile.json").write_text(json.dumps(TEST_PROFILE), encoding="utf-8")
    cfg = load_config(home)
    cfg.fetch.per_host_interval_seconds = 0
    db = DB(cfg.db_path)
    fetcher = Fetcher(cfg.fetch, transport=httpx.MockTransport(boards.handler), resolve=public_resolver, sleep=lambda s: None)
    model = LocalModel(cfg.model, transport=httpx.MockTransport(fake_model.handler))
    eng = Engine(cfg, db, model, fetcher, start_worker=False)
    return eng


def drain(engine, limit=50):
    """Run the queue to completion in the test thread."""
    for _ in range(limit):
        if not engine.step():
            break


def greenhouse(jobs):
    return {"jobs": [{"id": j["id"], "title": j["title"], "location": {"name": j.get("location", "Bengaluru")}, "content": j.get("content", "<p>Requirements: SQL</p>"),
                      "absolute_url": f"https://example.com/jobs/{j['id']}", "first_published": "2026-10-30T10:00:00Z"} for j in jobs]}


def add_company(db, name="Fixture Co", ats_id="fixture"):
    from signaldesk.db import now_iso
    return db.insert("companies", {"name": name, "careers_url": "https://example.com/careers", "ats": "greenhouse", "ats_id": ats_id,
                                   "enabled": 1, "verification": "test", "created_at": now_iso()})
