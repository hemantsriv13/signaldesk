"""Readers for public discovery pages: job listing pages, investor announcement pages and
portfolio pages. They read only what the page states; they run no scripts and log in nowhere.

A page that answers but contains nothing recognisable raises FetchError, so a changed layout or a
blocked request shows up as "temporarily unavailable", never as "zero jobs found".
"""
from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from ..discovery import board_from_url
from ..netsafe import FetchError, Fetcher
from ..text import html_to_text
from . import feeds

SOCIAL = re.compile(r"(^|\.)(linkedin|twitter|x|facebook|instagram|youtube|medium|github|crunchbase|angel|wellfound|google|apple|t)\.(com|co|me)$", re.I)
_BLOCK = {"li", "article", "tr", "section", "div", "p", "h1", "h2", "h3", "h4", "td", "dd", "figure"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_TEXT = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b|\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,\s*(\d{4})\b")


def parse_date(text: str | None) -> str | None:
    """A publication date as YYYY-MM-DD, or None. Only explicit dates count."""
    if not text:
        return None
    m = DATE_TEXT.search(text)
    if not m:
        return None
    try:
        if m.group(1):
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif m.group(4):
            d = date(int(m.group(6)), MONTHS[m.group(5)[:3].lower()], int(m.group(4)))
        else:
            d = date(int(m.group(9)), MONTHS[m.group(7)[:3].lower()], int(m.group(8)))
    except (KeyError, ValueError):
        return None
    return d.isoformat() if 2000 <= d.year <= date.today().year + 1 else None


class _Page(HTMLParser):
    """Plain-text stream with the position of every link and every <time datetime>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stream: list[str] = []
        self.size = 0
        self.links: list[dict] = []
        self.times: list[tuple[int, str]] = []
        self._a: dict | None = None
        self._skip = 0

    def _add(self, s: str) -> None:
        self.stream.append(s)
        self.size += len(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg", "template"):
            self._skip += 1
        elif tag in _BLOCK:
            self._add("\n")
        if tag == "a" and a.get("href"):
            self._a = {"href": a["href"], "start": self.size, "text": "", "aria": a.get("aria-label") or a.get("title") or ""}
        if tag == "img" and self._a is not None and a.get("alt"):
            self._a["text"] += " " + a["alt"]
        if tag == "time" and a.get("datetime"):
            self.times.append((self.size, a["datetime"]))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template") and self._skip:
            self._skip -= 1
        elif tag in _BLOCK:
            self._add("\n")
        if tag == "a" and self._a is not None:
            self._a["end"] = self.size
            self.links.append(self._a)
            self._a = None

    def handle_data(self, data):
        if self._skip:
            return
        self._add(data)
        if self._a is not None:
            self._a["text"] += data

    def text(self) -> str:
        return "".join(self.stream)


def read_page(fetcher: Fetcher, url: str) -> tuple[str, "_Page", str]:
    r = fetcher.get(url, check_robots=True, accept="text/html,application/xhtml+xml")
    if r.status != 200:
        raise FetchError(f"HTTP {r.status} from {urlsplit(url).hostname}")
    p = _Page()
    p.feed(r.text)
    p.close()
    return r.url, p, r.text


def _block(p: _Page, link: dict, before: int = 250, after: int = 250) -> str:
    full = p.text()
    return re.sub(r"\s+", " ", full[max(0, link["start"] - before): link.get("end", link["start"]) + after]).strip()


def _near_date(p: _Page, link: dict) -> str | None:
    best = None
    for pos, value in p.times:
        dist = abs(pos - link["start"])
        if dist < 600 and (best is None or dist < best[0]):
            best = (dist, value)
    if best:
        return parse_date(best[1])
    full = p.text()
    return parse_date(full[max(0, link["start"] - 160): link.get("end", link["start"]) + 160])


# ---------------------------------------------------------------- job listing pages
def job_listings(fetcher: Fetcher, url: str) -> dict:
    """Read a public job listing page (YC jobs, an investor's portfolio job board).
    Returns {"postings": [...], "boards": [...]} where boards are employer ATS boards it links to."""
    final, page, raw = read_page(fetcher, url)
    postings, boards, seen = [], {}, set()
    for d in feeds._jsonld(raw):
        if "JobPosting" in str(d.get("@type")) and d.get("title"):
            org = d.get("hiringOrganization") or {}
            loc = d.get("jobLocation")
            locs = loc if isinstance(loc, list) else [loc] if loc else []
            postings.append({"url": urljoin(final, d.get("url") or final), "title": html_to_text(str(d["title"])),
                             "employer": org.get("name", "") if isinstance(org, dict) else "",
                             "location": ", ".join(filter(None, ((l.get("address") or {}).get("addressLocality") for l in locs if isinstance(l, dict)))),
                             "apply_url": "", "description": html_to_text(d.get("description")) if d.get("description") else ""})
    for link in page.links:
        href = urljoin(final, link["href"])
        board = board_from_url(href)
        if board:
            name = re.sub(r"\s+", " ", (link["text"] or link["aria"]).strip())[:120]
            boards[(board["ats"], board["ats_id"])] = {**board, "name": name or board["ats_id"], "found_on": final}
            continue
        m = re.search(r"/companies/([a-z0-9-]+)/jobs/([A-Za-z0-9-]+)", href)
        title = re.sub(r"\s+", " ", link["text"]).strip()
        if m and title and href not in seen and len(title) < 160:
            seen.add(href)
            block = _block(p=page, link=link)
            postings.append({"url": href, "title": title, "employer": "", "employer_slug": m.group(1),
                             "location": _location_hint(block), "apply_url": "", "description": ""})
    if not postings and not boards:
        raise FetchError("The page answered but showed no recognisable job listings; its layout may have changed or it needs scripts.")
    return {"postings": postings, "boards": list(boards.values()), "final_url": final}


CITY = re.compile(r"\b(bengaluru|bangalore|mumbai|delhi|gurugram|gurgaon|noida|hyderabad|pune|chennai|india|remote[^,;|]{0,20})\b", re.I)


def _location_hint(block: str) -> str:
    return ", ".join(dict.fromkeys(m.group(0).strip() for m in CITY.finditer(block)))[:120]


# ---------------------------------------------------------------- announcements
def announcements(fetcher: Fetcher, url: str, limit: int = 40) -> list[dict]:
    """Dated items from an investor's or company's news page or feed: {url, title, date}. Only a
    publication date counts; an "updated" date or today's date is never used."""
    if re.search(r"(feed|rss|atom)(\.xml)?/?$|\.xml$", url, re.I):
        items = feeds.fetch_feed(fetcher, url, limit)
        return [{"url": i["url"], "title": i["title"], "date": (i.get("published_at") or "")[:10] or None, "text": i.get("content_text") or ""} for i in items]
    final, page, _raw = read_page(fetcher, url)
    host = urlsplit(final).hostname
    out, seen = [], set()
    for link in page.links:
        href = urljoin(final, link["href"]).split("#")[0]
        title = re.sub(r"\s+", " ", link["text"] or link["aria"]).strip()
        if urlsplit(href).hostname != host or href in seen or href.rstrip("/") == final.rstrip("/") or not (20 <= len(title) <= 220):
            continue
        seen.add(href)
        out.append({"url": href, "title": title, "date": _near_date(page, link), "text": ""})
    if not out:
        raise FetchError("The page answered but listed no recognisable announcements; its layout may have changed or it needs scripts.")
    return out[:limit]


def article(fetcher: Fetcher, url: str) -> dict:
    """One announcement page: text, publication date (JSON-LD datePublished or article meta), outbound links."""
    final, page, raw = read_page(fetcher, url)
    published = None
    for d in feeds._jsonld(raw):
        if d.get("datePublished"):
            published = parse_date(str(d["datePublished"]))
            break
    if not published:
        m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|datePublished|date)["\'][^>]+content=["\']([^"\']+)', raw, re.I)
        published = parse_date(m.group(1)) if m else None
    if not published and page.times:
        published = parse_date(page.times[0][1])
    host = urlsplit(final).hostname
    links = []
    for link in page.links:
        href = urljoin(final, link["href"])
        h = urlsplit(href).hostname or ""
        if h and h != host and not SOCIAL.search(h):
            links.append({"href": href, "host": h.removeprefix("www."), "text": re.sub(r"\s+", " ", link["text"]).strip()})
    title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    return {"url": final, "title": html_to_text(title.group(1)) if title else "", "text": html_to_text(raw), "date": published,
            "links": links, "people_links": [{"href": urljoin(final, l["href"]), "block": _block(page, l, 160, 160)} for l in page.links
                                             if "linkedin.com/in/" in l["href"]]}


# ---------------------------------------------------------------- portfolio pages
def portfolio(fetcher: Fetcher, url: str) -> list[dict]:
    """Companies listed on a portfolio page: {name, website or None, detail_url or None}.
    Listing on a portfolio page says nothing about when a company was funded."""
    final, page, _raw = read_page(fetcher, url)
    host = urlsplit(final).hostname
    out, seen = [], set()
    for link in page.links:
        href = urljoin(final, link["href"]).split("#")[0]
        name = re.sub(r"\s+", " ", (link["text"] or link["aria"])).strip()
        h = urlsplit(href).hostname or ""
        if not name or len(name) > 80 or href in seen:
            continue
        if h == host and re.search(r"/companies/[a-z0-9-]+/?$", href):
            seen.add(href)
            out.append({"name": name.split(" ")[0] if len(name) > 60 else name, "website": None, "detail_url": href})
        elif h and h != host and not SOCIAL.search(h):
            seen.add(href)
            out.append({"name": name, "website": f"https://{h.removeprefix('www.')}", "detail_url": None})
    if not out:
        raise FetchError("The page answered but listed no recognisable companies; its layout may have changed or it needs scripts.")
    return out


def company_website(fetcher: Fetcher, detail_url: str) -> str | None:
    """The website a portfolio detail page links as the company's own. None when it does not say."""
    final, page, _raw = read_page(fetcher, detail_url)
    host = urlsplit(final).hostname
    for link in page.links:
        href = urljoin(final, link["href"])
        h = urlsplit(href).hostname or ""
        label = (link["text"] + " " + link["aria"]).lower()
        if h and h != host and not SOCIAL.search(h) and (re.search(r"website|visit|homepage", label) or label.strip() in (h, h.removeprefix("www."))):
            return f"https://{h.removeprefix('www.')}"
    return None
