"""Optional daily schedule in Asia/Kolkata. Off by default.

It only works while this app is running on the laptop; no system task is created. If the app was
off at the scheduled time, it runs once when it next starts (a single catch-up), however many days
were missed. A slot is skipped, not queued, when a run is already in progress.
"""
from __future__ import annotations

import threading
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kolkata")
ON_TIME_MINUTES = 15
DEFAULT = {"enabled": False, "time": "07:30", "last_slot": None, "last_result": None}


def latest_slot(now: datetime, at: str) -> datetime:
    hh, mm = (int(x) for x in at.split(":"))
    local = now.astimezone(TZ)
    slot = datetime.combine(local.date(), time(hh, mm), TZ)
    return slot if slot <= local else slot - timedelta(days=1)


def next_slot(now: datetime, at: str) -> datetime:
    return latest_slot(now, at) + timedelta(days=1)


def decide(now: datetime, settings: dict, busy: bool) -> tuple[str, datetime | None]:
    """Return (action, slot): action is 'wait', 'run', 'catch-up' or 'skip-busy'."""
    if not settings.get("enabled"):
        return "wait", None
    slot = latest_slot(now, settings["time"])
    last = settings.get("last_slot")
    if last and datetime.fromisoformat(last) >= slot:
        return "wait", None
    if busy:
        return "skip-busy", slot
    late = now.astimezone(TZ) - slot > timedelta(minutes=ON_TIME_MINUTES)
    return ("catch-up" if late else "run"), slot


class Scheduler:
    def __init__(self, engine):
        self.engine = engine
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="signaldesk-scheduler", daemon=True)

    def settings(self) -> dict:
        return {**DEFAULT, **(self.engine.db.get_setting("schedule") or {})}

    def update(self, enabled: bool, at: str) -> dict:
        hh, mm = at.split(":")
        if not (0 <= int(hh) < 24 and 0 <= int(mm) < 60):
            raise ValueError("Use a 24-hour time such as 07:30.")
        s = self.settings()
        if enabled and not s["enabled"]:
            # Turning it on does not trigger a run for a slot that has already passed today.
            s["last_slot"] = latest_slot(datetime.now(TZ), at).isoformat()
        s.update(enabled=enabled, time=f"{int(hh):02d}:{int(mm):02d}")
        self.engine.db.set_setting("schedule", s)
        return self.describe()

    def describe(self) -> dict:
        s = self.settings()
        now = datetime.now(TZ)
        return {**s, "timezone": "Asia/Kolkata", "next_run": next_slot(now, s["time"]).isoformat() if s["enabled"] else None}

    def tick(self, now: datetime | None = None) -> str:
        now = now or datetime.now(TZ)
        s = self.settings()
        action, slot = decide(now, s, bool(self.engine.active_runs()))
        if action == "wait":
            return action
        s["last_slot"] = slot.isoformat()
        if action == "skip-busy":
            s["last_result"] = f"Skipped the {slot:%d %b %H:%M} run: another run was in progress."
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
