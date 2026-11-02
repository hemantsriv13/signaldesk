"""RSS/Atom collection and single-page extraction for manually supplied article or job URLs.

Feeds are read as published. Paywalled posts usually carry a preview only; those are stored as
excerpts and labelled so. Nothing here tries to get around a paywall.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

import feedparser

from ..netsafe import FetchError, Fetcher
from ..text import html_to_text

# Wording Substack and others use where a post is cut for non-subscribers.
PAYWALL = re.compile(r"(keep reading with a 7-day free trial|this post is for paid subscribers|subscribe to (keep|continue) reading|"
                     r"upgrade to (paid|a paid subscription)|read the full (post|story|article)|continue reading|"
                     r"available (only )?to paid subscribers|read more\s*$)", re.I)
FULL_MIN_CHARS = 2500


def content_basis(text: str, raw_html: str = "") -> str:
    if not text.strip():
        return "metadata"
    if PAYWALL.search(text[-600:]) or PAYWALL.search(raw_html[-1500:] if raw_html else ""):
        return "excerpt"
    return "full" if len(text) >= FULL_MIN_CHARS else "excerpt"


def _when(entry, *keys) -> str | None:
    for k in keys:
        t = entry.get(k)
        if t:
            return datetime.fromtimestamp(time.mktime(t), timezone.utc).isoformat()
    return None


def fetch_feed(fetcher: Fetcher, url: str, limit: int) -> list[dict]:
    r = fetcher.get(url, accept="application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5")
    if r.status != 200:
        raise FetchError(f"HTTP {r.status} from the feed.")
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise FetchError("The feed could not be parsed.")
    items = []
    for e in feed.entries[:limit]:
        raw = max((c.get("value", "") for c in e.get("content", [])), key=len, default="") or e.get("summary", "")
        text = html_to_text(raw)
        link = e.get("link") or ""
        if not link:
            continue
        items.append({
            "guid": e.get("id") or link,
            "url": link,
            "title": html_to_text(e.get("title", "")) or "(untitled)",
            "author": e.get("author") or None,
            "published_at": _when(e, "published_parsed", "updated_parsed"),
            "content_text": text,
            "content_basis": content_basis(text, raw),
        })
    return items


def _jsonld(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                out.append(d)
                stack.extend(d.get("@graph", []) if isinstance(d.get("@graph"), list) else [])
    return out


def fetch_page(fetcher: Fetcher, url: str) -> dict:
    """Fetch one public page (robots.txt respected) and return its title, text and any JobPosting data."""
    r = fetcher.get(url, check_robots=True, accept="text/html,application/xhtml+xml")
    if r.status != 200:
        raise FetchError(f"HTTP {r.status} from the page.")
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "xml" not in ctype and "text" not in ctype:
        raise FetchError(f"Not a web page ({ctype or 'unknown type'}).")
    html = r.text
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    m = re.search(r"<(article|main)[^>]*>(.*?)</\1>", html, re.S | re.I)
    body = html_to_text(m.group(2) if m else html)
    posting = next((d for d in _jsonld(html) if "JobPosting" in str(d.get("@type"))), None)
    author = re.search(r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)', html, re.I)
    published = re.search(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)', html, re.I)
    return {
        "final_url": r.url,
        "title": html_to_text(title.group(1)) if title else url,
        "text": body,
        "author": author.group(1) if author else None,
        "published_at": published.group(1) if published else None,
        "job_posting": posting,
        "paywall_hint": bool(PAYWALL.search(body[-800:])),
    }
