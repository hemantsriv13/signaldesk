"""The profile (facts about you) and preferences (what to look for). Both live in the data
directory, never in source files. Each has a version hash that is part of every cache key that
depends on it, so editing either one makes the affected analyses stale."""
from __future__ import annotations

import json
from pathlib import Path

from .text import sha

# A neutral template. On first run it is copied to the data directory (profile.json), where you
# replace it with your own facts in Profile and settings. Personal facts never live in source files.
STARTER_PROFILE = {
    "name": "",
    "summary": "",
    "facts": [
        {"id": "P1", "text": "Replace with a fact about your work history, e.g. employer, dates and titles."},
        {"id": "P2", "text": "Replace with the areas you worked in."},
        {"id": "P3", "text": "Replace with the tools you use."},
    ],
    "not_claimed": [
        "Years of experience for individual skills beyond the dates above.",
    ],
}

DEFAULT_PREFS = {
    "locations": ["bengaluru", "remote_india"],
    "role_families": ["applied_ai_product", "solutions", "product_analytics", "founders_office", "strategy_ops"],
    "ctc_threshold_lakh": 22,
    "reading_interests": ["applied AI", "enterprise adoption", "evaluation", "AI product development", "operational use cases"],
    "reading_level": "any",            # any | prefer_less_technical
    "muted_sources": [],               # reading source ids
    "muted_terms": [],                 # words that lower an article or job in the digest
    "digest": {"jobs": 3, "case_studies": 1, "articles": 2},
}


class ProfileStore:
    def __init__(self, path: Path, db):
        self.path = path
        self.db = db

    def profile(self) -> dict:
        if not self.path.exists():
            self.path.write_text(json.dumps(STARTER_PROFILE, indent=2), encoding="utf-8")
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save_profile(self, data: dict) -> dict:
        facts = []
        for i, f in enumerate(data.get("facts", []), 1):
            text = str(f.get("text", "")).strip()
            if text:
                facts.append({"id": f"P{i}", "text": text[:400]})
        clean = {
            "name": str(data.get("name", ""))[:120],
            "summary": str(data.get("summary", ""))[:600],
            "facts": facts[:30],
            "not_claimed": [str(x)[:300] for x in data.get("not_claimed", []) if str(x).strip()][:10],
        }
        self.path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
        return clean

    def profile_version(self) -> str:
        p = self.profile()
        return sha(p["facts"], p.get("not_claimed", []))[:12]

    def prefs(self) -> dict:
        stored = self.db.get_setting("preferences") or {}
        return {**DEFAULT_PREFS, **stored}

    def save_prefs(self, data: dict) -> dict:
        merged = {**self.prefs(), **{k: v for k, v in data.items() if k in DEFAULT_PREFS}}
        merged["ctc_threshold_lakh"] = float(merged["ctc_threshold_lakh"])
        self.db.set_setting("preferences", merged)
        return merged

    def prefs_version(self, keys: tuple[str, ...]) -> str:
        p = self.prefs()
        return sha({k: p.get(k) for k in keys})[:12]
