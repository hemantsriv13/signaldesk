"""Text helpers: HTML to plain text, hashing, dedupe keys and flags for retrieved content."""
from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "blockquote", "pre", "table"}
_SKIP = {"script", "style", "noscript", "svg", "iframe", "form", "button", "nav", "footer", "head", "template"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
        elif tag in _BLOCK:
            self.out.append("\n")
        if tag == "li":
            self.out.append("- ")

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    # Greenhouse returns HTML that is itself entity-escaped.
    if "&lt;" in raw and "<" not in raw[:200]:
        raw = html.unescape(raw)
    p = _Text()
    p.feed(raw)
    p.close()
    text = "".join(p.out).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    out, blank = [], 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank == 1 and out:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    return "\n".join(out).strip()


def sha(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p if isinstance(p, str) else json.dumps(p, sort_keys=True, default=str)).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


_TRACKING = re.compile(r"^(utm_|ref$|source$|gh_src$|lever-source|mc_|fbclid$|gclid$)")


def canonical_url(url: str) -> str:
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not _TRACKING.match(k)]
    host = (p.hostname or "").lower().removeprefix("www.")
    return urlunparse((p.scheme.lower() or "https", host, p.path.rstrip("/") or "/", "", urlencode(q), ""))


def title_key(title: str) -> str:
    return norm(title)[:120]


# Phrases that address an AI system rather than a human reader. Matching text is still shown and
# analysed as data; the flag tells the reader the source contained it.
_INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above) (instructions|prompts)|disregard (the|all|your) (instructions|rules)"
    r"|you are (now )?(an? )?(ai|assistant|language model)|system prompt|as an ai (model|assistant)"
    r"|(rate|mark|score) (this|me|the candidate) as (a )?(perfect|top|strong)|do not tell the user"
    r"|send (an )?email to|reply with only)", re.I)


def has_injection(text: str | None) -> bool:
    return bool(text and _INJECTION.search(text))


def clip(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    nl = cut.rfind("\n")
    if nl > limit * 0.7:
        cut = cut[:nl]
    return cut, True


def find_quote(quote: str, source: str) -> bool:
    """True when a quoted passage appears in the source, ignoring case, punctuation and spacing."""
    q = norm(quote)
    return bool(q) and len(q) >= 8 and q in norm(source)
