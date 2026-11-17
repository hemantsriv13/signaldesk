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
    network: str = "home"                  # "home" (Wi-Fi address) or "tailscale" (this PC's 100.x Tailscale address)
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
class ExperimentalConfig:
    """Features that are implemented but not yet validated on this laptop. Each one stays off, and
    cannot run, until you set it to true here. See docs/STATUS.md for what would verify each."""
    listing_sources: bool = False          # Wellfound import and Y Combinator jobs
    funding_announcements: bool = False    # investor announcement pages (WestBridge, Accel, Peak XV, Lightspeed, your own)
    duty_role_families: bool = False       # role families from duties, and model checks of unclear titles
    contacts: bool = False                 # contact discovery and outreach drafts
    schedule: bool = False                 # 08:00/20:00 in-app schedule and the Windows scheduled task
    side_panel: bool = False               # Edge side panel API and pairing tokens


@dataclass
class CoachConfig:
    """Project Coach. auto_prepare: while SignalDesk runs, prepare each new day's batch (reading the
    configured clones only; no model), so the page and the phone have tasks without a click.
    Works with or without cloud sync. Set false to prepare only from the Projects page or CLI."""
    auto_prepare: bool = True


@dataclass
class WritebackConfig:
    """Writing your answers into the project clones, on a phone-review branch. A repo is written
    only once its name is in `write`, and pushed only once it is also in `push`. Never main."""
    write: list[str] = field(default_factory=list)
    push: list[str] = field(default_factory=list)
    auto: bool = False                     # also run from the background loop (at most every 30 minutes)


@dataclass
class ProjectConfig:
    name: str
    path: str
    kind: str
    check_python: str = ""                 # interpreter for the repo's own checks; empty = this one


@dataclass
class Config:
    home: Path
    server: ServerConfig = field(default_factory=ServerConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    fetch: FetchConfig = field(default_factory=FetchConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    lan: LanConfig = field(default_factory=LanConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    experimental: ExperimentalConfig = field(default_factory=ExperimentalConfig)
    coach: CoachConfig = field(default_factory=CoachConfig)
    writeback: WritebackConfig = field(default_factory=WritebackConfig)
    demo: bool = False                     # set only by --demo: synthetic data, no fetching, no model calls
    project: list[ProjectConfig] = field(default_factory=list)

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
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))   # Notepad and PowerShell 5 save UTF-8 with a BOM
        for section in ("server", "model", "fetch", "limits", "lan", "auth", "experimental", "coach", "writeback"):
            _apply(getattr(cfg, section), data.get(section, {}))
        seen = set()
        for item in data.get("project", []):
            if not all(isinstance(item.get(k), str) and item[k].strip() for k in ("name", "path", "kind")):
                raise ValueError("Each [[project]] needs name, path and kind")
            if item["kind"] not in ("pushback", "nextword", "signaldesk") or item["name"] in seen:
                raise ValueError("Project names must be unique; kinds: pushback, nextword, signaldesk")
            seen.add(item["name"])
            if not isinstance(item.get("check_python", ""), str):
                raise ValueError("check_python must be a path to a Python interpreter")
            cfg.project.append(ProjectConfig(**{k: item[k] for k in ("name", "path", "kind")}, check_python=item.get("check_python", "")))
    for d in (cfg.home, cfg.logs_dir, cfg.digests_dir, cfg.evals_dir):
        d.mkdir(parents=True, exist_ok=True)
    return cfg
