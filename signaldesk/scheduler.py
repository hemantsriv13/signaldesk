"""Optional in-app schedule in Asia/Kolkata, by default 08:00 and 20:00. Off until you turn it on.

It works only while this app is running. For collection while the app is closed, install the
opt-in Windows task (scripts\\schedule-install.ps1), which uses the same sweep entry point and lock.
If the app was off at a scheduled time, it runs once when it next starts (a single catch-up),
however many slots were missed. A slot is skipped, not queued, when a sweep is already in progress.
"""
from __future__ import annotations

import threading
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kolkata")
ON_TIME_MINUTES = 15
DEFAULT_TIMES = ["08:00", "20:00"]
DEFAULT = {"enabled": False, "times": DEFAULT_TIMES, "last_slot": None, "last_result": None}


def _times(settings: dict) -> list[str]:
    """Stored times, accepting the older single 'time' setting."""
    t = settings.get("times") or ([settings["time"]] if settings.get("time") else DEFAULT_TIMES)
    return sorted({x for x in t if x})


def latest_slot(now: datetime, at: str | list[str]) -> datetime:
    """The most recent scheduled moment at or before now, across all configured times."""
    local = now.astimezone(TZ)
    best = None
    for t in ([at] if isinstance(at, str) else at):
        hh, mm = (int(x) for x in t.split(":"))
        slot = datetime.combine(local.date(), time(hh, mm), TZ)
        if slot > local:
            slot -= timedelta(days=1)
        best = slot if best is None or slot > best else best
    return best


def next_slot(now: datetime, at: str | list[str]) -> datetime:
    local = now.astimezone(TZ)
    best = None
    for t in ([at] if isinstance(at, str) else at):
        hh, mm = (int(x) for x in t.split(":"))
        slot = datetime.combine(local.date(), time(hh, mm), TZ)
        if slot <= local:
            slot += timedelta(days=1)
        best = slot if best is None or slot < best else best
    return best


def decide(now: datetime, settings: dict, busy: bool) -> tuple[str, datetime | None]:
    """Return (action, slot): action is 'wait', 'run', 'catch-up' or 'skip-busy'."""
    if not settings.get("enabled"):
        return "wait", None
    slot = latest_slot(now, _times(settings))
    last = settings.get("last_slot")
    if last and datetime.fromisoformat(last) >= slot:
        return "wait", None
    if busy:
        return "skip-busy", slot
    late = now.astimezone(TZ) - slot > timedelta(minutes=ON_TIME_MINUTES)
    return ("catch-up" if late else "run"), slot


def parse_times(at: str | list[str]) -> list[str]:
    parts = at if isinstance(at, list) else [p.strip() for p in str(at).replace(";", ",").split(",")]
    out = []
    for p in parts:
        if not p:
            continue
        hh, mm = p.split(":")
        if not (0 <= int(hh) < 24 and 0 <= int(mm) < 60):
            raise ValueError("Use 24-hour times such as 08:00, 20:00.")
        out.append(f"{int(hh):02d}:{int(mm):02d}")
    if not out or len(out) > 6:
        raise ValueError("Give between one and six times, such as 08:00, 20:00.")
    return sorted(set(out))


class Scheduler:
    def __init__(self, engine):
        self.engine = engine
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="signaldesk-scheduler", daemon=True)

    def settings(self) -> dict:
        s = {**DEFAULT, **(self.engine.db.get_setting("schedule") or {})}
        s["times"] = _times(s)
        return s

    def update(self, enabled: bool, at: str | list[str]) -> dict:
        times = parse_times(at)
        s = self.settings()
        if enabled and not s["enabled"]:
            # Turning it on does not trigger a run for a slot that has already passed today.
            s["last_slot"] = latest_slot(datetime.now(TZ), times).isoformat()
        s.update(enabled=enabled, times=times, time=times[0])
        self.engine.db.set_setting("schedule", s)
        return self.describe()

    def describe(self) -> dict:
        s = self.settings()
        now = datetime.now(TZ)
        return {**s, "time": s["times"][0], "timezone": "Asia/Kolkata",
                "next_run": next_slot(now, s["times"]).isoformat() if s["enabled"] else None}

    def tick(self, now: datetime | None = None) -> str:
        now = now or datetime.now(TZ)
        s = self.settings()
        action, slot = decide(now, s, bool(self.engine.active_runs()))
        if action == "wait":
            return action
        s["last_slot"] = slot.isoformat()
        if action == "skip-busy":
            s["last_result"] = f"Skipped the {slot:%d %b %H:%M} run: another sweep was in progress."
        else:
            res = self.engine.start_all(trigger="schedule" if action == "run" else "catch-up")
            s["last_result"] = (f"{'Ran' if action == 'run' else 'Caught up once for'} the {slot:%d %b %H:%M} slot"
                                f"{'' if res.get('started') else ': ' + str(res.get('skipped'))}.")
        self.engine.db.set_setting("schedule", s)
        return action

    def _loop(self) -> None:
        while not self.stop.wait(30):
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                pass
