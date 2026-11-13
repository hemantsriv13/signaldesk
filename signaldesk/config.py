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
    concurrency: int = 1                 # simultaneous local model requests; one suits a 6 GB GPU
    # Optional larger local model for answers that fail validation or stay uncertain. Empty = off.
    # Use the exact id your Colibri server reports for it; SignalDesk never downloads a model.
    escalation_model_id: str = ""
    escalation_base_url: str = ""        # empty = same server as above


@dataclass
class FetchConfig:
    concurrency: int = 4
    timeout_seconds: float = 20
    per_host_interval_seconds: float = 1.0
    per_host_concurrency: int = 2
    max_bytes: int = 40_000_000
    user_agent: str = "SignalDesk/0.1 (personal job and reading tracker; local use)"


@dataclass
class LimitsConfig:
    max_job_analyses_per_run: int = 12
    max_article_cards_per_run: int = 10
    max_case_studies_per_run: int = 2
    items_per_feed: int = 8
    max_role_checks_per_run: int = 15    # ambiguous titles sent to the model; location must already qualify
    max_contact_jobs_per_run: int = 5    # shortlisted roles that get contact discovery each sweep
    sweep_lock_minutes: int = 180        # a run lock older than this is treated as abandoned


@dataclass
class LanConfig:
    """LAN mode: one authenticated HTTPS entry point on this PC's home-network address. Off by default.
    The app on 127.0.0.1 and Colibri stay on loopback."""
    enabled: bool = False
    bind: str = ""                         # this PC's private address, e.g. 192.168.1.10; never 0.0.0.0
    port: int = 8443
    hostnames: list = field(default_factory=list)   # names/addresses devices type, all covered by the certificate
    cert_file: str = ""                    # public certificate (PEM), in the data directory
    key_file: str = ""                     # private key (PEM), in the data directory, never in the repo


@dataclass
class AuthConfig:
    session_idle_hours: float = 12
    session_max_days: float = 7
    require_login_local: bool = False      # also require sign-in on http://127.0.0.1
    panel_token_days: int = 90


@dataclass
class Config:
    home: Path
    server: ServerConfig = field(default_factory=ServerConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    fetch: FetchConfig = field(default_factory=FetchConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    lan: LanConfig = field(default_factory=LanConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)

    @property
    def auth_path(self) -> Path:
        return self.home / "auth.json"

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
            current = getattr(obj, key)
            if isinstance(current, bool):
                value = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
            setattr(obj, key, type(current)(value))


def load_config(home: Path | None = None) -> Config:
    home = Path(home) if home else default_home()
    cfg = Config(home=home)
    path = home / "config.toml"
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for section in ("server", "model", "fetch", "limits", "lan", "auth"):
            _apply(getattr(cfg, section), data.get(section, {}))
    for d in (cfg.home, cfg.logs_dir, cfg.digests_dir, cfg.evals_dir):
        d.mkdir(parents=True, exist_ok=True)
    return cfg
