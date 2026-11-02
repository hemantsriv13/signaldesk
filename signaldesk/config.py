"""Configuration: one TOML file in the data directory, with defaults for everything.

The data directory holds the database, profile, preferences, logs and generated digests. It is
%SIGNALDESK_HOME% when set, otherwise D:\\LocalAI\\signaldesk on Windows (./data elsewhere).
Nothing in it is committed to Git.
"""
from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


def default_home() -> Path:
    env = os.environ.get("SIGNALDESK_HOME")
    if env:
        return Path(env)
    if sys.platform == "win32" and Path("D:/").exists():
        return Path("D:/LocalAI/signaldesk")
    return Path(__file__).resolve().parent.parent / "data"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8780


@dataclass
class ModelConfig:
    base_url: str = "http://127.0.0.1:8000/v1"
    model_id: str = "qwen3-4b-instruct-2507-q4km"
    context_tokens: int = 2048
    max_output_tokens: int = 512
    prompt_char_budget: int = 6000
    request_timeout_seconds: float = 180
    max_attempts: int = 3


@dataclass
class FetchConfig:
    concurrency: int = 4
    timeout_seconds: float = 20
    per_host_interval_seconds: float = 1.0
    max_bytes: int = 40_000_000
    user_agent: str = "SignalDesk/0.1 (personal job and reading tracker; local use)"


@dataclass
class LimitsConfig:
    max_job_analyses_per_run: int = 12
    max_article_cards_per_run: int = 10
    max_case_studies_per_run: int = 2
    items_per_feed: int = 8


@dataclass
class Config:
    home: Path
    server: ServerConfig = field(default_factory=ServerConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    fetch: FetchConfig = field(default_factory=FetchConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)

    @property
    def db_path(self) -> Path:
        return self.home / "signaldesk.db"

    @property
    def profile_path(self) -> Path:
        return self.home / "profile.json"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def digests_dir(self) -> Path:
        return self.home / "digests"

    @property
    def evals_dir(self) -> Path:
        return self.home / "evals"


def _apply(obj, values: dict) -> None:
    names = {f.name: f for f in fields(obj)}
    for key, value in values.items():
        if key in names:
            setattr(obj, key, type(getattr(obj, key))(value))


def load_config(home: Path | None = None) -> Config:
    home = Path(home) if home else default_home()
    cfg = Config(home=home)
    path = home / "config.toml"
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for section in ("server", "model", "fetch", "limits"):
            _apply(getattr(cfg, section), data.get(section, {}))
    for d in (cfg.home, cfg.logs_dir, cfg.digests_dir, cfg.evals_dir):
        d.mkdir(parents=True, exist_ok=True)
    return cfg
