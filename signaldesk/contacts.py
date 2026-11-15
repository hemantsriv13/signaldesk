"""Contacts and outreach for shortlisted roles.

Where people come from (public sources only, in order of preference):
  1. the job posting itself (a named hiring manager or "you will report to ..."),
  2. the company's own team or about page,
  3. a funding announcement that names the founders,
  4. your own entry (a LinkedIn URL or export you paste in).

Rules that keep this honest:
  * A person is stored only with the page that names them next to the company.
  * A profile URL is stored only when that same page links it beside the name, or you enter it.
    No profile URL is ever guessed, and no one is matched on name alone.
  * No logged-in scraping, no LinkedIn crawling, no access-control workarounds.
  * There is no supported LinkedIn people-search or messaging integration available to this project,
    so discovery uses the public fallback and sending is off: drafts, Copy and Mark sent (with the date).
  * A draft is never a sent message. An unclear send is never retried automatically.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .db import DB, now_iso
from .netsafe import FetchError, Fetcher
from .sources import web
from .text import find_quote, norm, sha

MAX_PER_JOB = 3
# Two or three words; a later word may be an initial ("Vishwanath T R", "Priya K."), common in Indian names.
NAME = r"([A-Z][a-z]+(?:[ -](?:[A-Z][a-z'’]+|[A-Z]\.?(?![a-z]))){1,2})"
POSTING_PATTERNS = [
    (re.compile(rf"\b(?:report(?:s|ing)?|reporting line)\s+(?:directly\s+)?(?:in)?to\s+{NAME}(?:\s*,\s*(?:our\s+)?([A-Z][^.,;\n]{{2,60}}))?"), "named in the posting as the person this role reports to", 10),
    (re.compile(rf"\bhiring manager(?: is|:)?\s+{NAME}(?:\s*,\s*([A-Z][^.,;\n]{{2,60}}))?"), "named in the posting as the hiring manager", 5),
    (re.compile(rf"\b(?:work(?:ing)? (?:closely |directly )?with|partner with)\s+{NAME}\s*,\s*(?:our\s+)?((?i:(?:co-?)?founder[^.,;\n]{{0,40}}|ceo|cto|coo|head of [^.,;\n]{{2,40}}|vp [^.,;\n]{{2,40}}))"), "named in the posting as someone this role works with", 15),
]
FOUNDER_PATTERNS = [
    re.compile(rf"{NAME}\s*,\s*((?i:(?:co-?)?founder(?:\s+(?:and|&)\s+(?:ceo|cto|coo|chief [a-z ]+))?|ceo))\b"),
    re.compile(rf"\b((?i:(?:co-?)?founder(?:\s+(?:and|&)\s+(?:ceo|cto|coo))?|ceo))\s+{NAME}"),
    re.compile(rf"\bfounded by\s+{NAME}(?:\s+and\s+{NAME})?"),
]
TITLE_WORDS = re.compile(r"\b(co-?founder|founder|ceo|cto|coo|chief [a-z]+ officer|chief of staff|head of [a-z &]+|vp[ ,][a-z &]+|vice president[a-z ,&]*|"
                         r"director[a-z ,&]*|recruit(er|ing)[a-z ]*|talent[a-z ]*|people (partner|team|operations)|hiring manager)\b", re.I)
NOT_A_NAME = re.compile(r"^(Our|The|This|Your|You|We|Team|Head|Chief|Senior|Lead|Product|Strategy|Operations|Founder|Co Founder|Hiring|About|Join)\b")
BANNED = re.compile(r"huge fan|big fan|love (what|your)|i('ve| have) been (using|following)|your (amazing|incredible|inspiring)|hope this (message|email|note) finds you|"
                    r"i came across your profile|synerg|passionate about|game[- ]changer|rockstar|ninja|thrilled to connect|would love to (connect|chat)|"
                    r"i appreciate your (work|leadership|vision)|exchange insights", re.I)
FALSE_SELF = re.compile(r"\bI(?:'m| am| was| have been| worked as| served as)\s+(?:a |an |the )?(?:former\s+)?(product manager|\bpm\b|chief of staff|"
                        r"ml engineer|machine learning engineer|data scientist)|production (ml|machine learning)|deployed (ml|machine learning) models", re.I)


def recipient_key(name: str, company: str, profile_url: str | None) -> str:
    if profile_url and "linkedin.com/in/" in profile_url:
        return "li:" + urlsplit(profile_url).path.rstrip("/").lower()
    return "nc:" + sha(norm(name), norm(company))[:16]


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _person(name: str, title: str | None, *, origin: str, evidence_url: str, evidence: str, why: str, rank: int, profile_url: str | None = None) -> dict | None:
    name = re.sub(r"\s+", " ", name).strip(" ,.")
    if NOT_A_NAME.search(name) or len(name.split()) < 2:
        return None
    return {"name": name, "title": (title or "").strip(" ,.")[:120] or None, "origin": origin, "evidence_url": evidence_url,
            "evidence_text": evidence[:300], "why": why, "rank": rank, "profile_url": profile_url}


def from_posting(job: dict) -> list[dict]:
    text, out = job.get("description_text") or "", []
    for pat, why, rank in POSTING_PATTERNS:
        for m in pat.finditer(text):
            p = _person(m.group(1), m.group(2) if m.lastindex and m.lastindex >= 2 else None, origin="posting",
                        evidence_url=job.get("official_url") or "", evidence=m.group(0), why=f"{why}", rank=rank)
            if p:
                out.append(p)
    return out


def from_announcement(text: str, url: str, company: str) -> list[dict]:
    """Founders named in a funding announcement about this company."""
    if company.lower() not in (text or "").lower():
        return []
    out = []
    for pat in FOUNDER_PATTERNS:
        for m in pat.finditer(text or ""):
            groups = [g for g in m.groups() if g]
            names = [g for g in groups if re.fullmatch(NAME, g)]
            titles = [g for g in groups if not re.fullmatch(NAME, g)]
            for n in names:
                p = _person(n, (titles[0] if titles else "Founder"), origin="announcement", evidence_url=url, evidence=m.group(0),
                            why="Named as a founder in the funding announcement", rank=30)
                if p:
                    out.append(p)
    return out


# A name must start a word: "LinkedIn Corwin Ashdale" must not give "In Corwin Ashdale".
NAME_AT = rf"(?<![A-Za-z'’]){NAME}"
NAME_LINE = re.compile(rf"^{NAME}$")
TEAM_ROLE = (r"(?:co-?)?founder[^\n]{0,30}|ceo|cto|coo|head of [^\n]{2,40}|vp [^\n]{2,40}|director [^\n]{2,40}|"
             r"[a-z ]*recruit[^\n]{0,30}|talent [^\n]{2,30}")


def _names_in(card: str) -> list[str]:
    """People named in one page element: a line that is only a name, or "Name, Title" on one line."""
    names = []
    for line in (ln.strip() for ln in card.splitlines()):
        m = NAME_LINE.match(line) or re.match(rf"^{NAME}\s*,", line)
        if m and not NOT_A_NAME.search(m.group(1)) and not TITLE_WORDS.fullmatch(m.group(1)):
            names.append(m.group(1))
    return list(dict.fromkeys(names))


def _other_company(title: str, company: str) -> bool:
    """A title like "Founder and CEO, Lightspeed" names another company: a customer quote, not staff."""
    own = norm(company)
    for part in title.split(",")[1:]:
        part = part.strip()
        if part and not TITLE_WORDS.search(part) and not DEPARTMENT.fullmatch(part) and norm(part) not in own and own not in norm(part):
            return True
    return False


# What may follow a title after a comma without naming another company: "Co-founder, Engineering".
DEPARTMENT = re.compile(r"(?i)(engineering|product|design|sales|marketing|operations|ops|finance|people|hr|legal|research|growth|strategy|"
                        r"technology|tech|business|customer success|partnerships|data|ai|ml|gtm|go-to-market|platform|infrastructure|"
                        r"india|apac|emea|americas|asia|global)( (and|&) [a-z ]+)?")


def _home_page(url: str) -> bool:
    """The site's home page, or a country home page such as /in or /en-gb."""
    path = urlsplit(url).path.rstrip("/").lower()
    return path == "" or bool(re.fullmatch(r"/[a-z]{2}(-[a-z]{2})?", path))


# Job boards host careers pages for many companies; their own team is never the employer's team.
ATS_HOSTS = re.compile(r"(^|\.)(greenhouse\.io|lever\.co|ashbyhq\.com|workable\.com|smartrecruiters\.com|myworkdayjobs\.com|"
                       r"bamboohr\.com|recruitee\.com|teamtailor\.com|keka\.com|zohorecruit\.\w+|freshteam\.com)$", re.I)


def from_team_page(fetcher: Fetcher, domain: str, company: str) -> list[dict]:
    """People listed on the company's own about/team page.

    A page reached by a redirect to some other address (for example the home page) is ignored: what it
    lists is not the team. A LinkedIn link goes to a person only when the smallest page element around
    the link names exactly that one person; if it names several, the link is dropped, never guessed. A
    title that names another company (a customer testimonial) is not a member of this team."""
    out = []
    for path in ("/about", "/team", "/about-us", "/company", "/people"):
        url = f"https://{domain}{path}"
        try:
            page = web.article(fetcher, url)
        except FetchError:
            continue
        if _home_page(page["url"]):
            continue                       # redirected to the home page: what it shows is not the team
        linked: dict[str, str] = {}
        for pl in page["people_links"]:
            for card in pl.get("cards", []):
                names = _names_in(card)
                if names:
                    if len(names) == 1:
                        linked.setdefault(names[0], pl["href"].split("?")[0])
                    break
        for m in re.finditer(rf"{NAME_AT}\s*[\n,–—-]\s*((?i:{TEAM_ROLE}))", page.get("stream") or page["text"]):
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            if _other_company(title, company):
                continue
            p = _person(m.group(1), title, origin="team_page", evidence_url=page["url"], evidence=m.group(0),
                        why=f"Listed on {company}'s own team page", rank=20 if m.group(1) in linked else 25,
                        profile_url=linked.get(m.group(1)))
            if p:
                out.append(p)
        if out:
            break
    return out


def rank_for_job(people: list[dict], job: dict, small_company: bool) -> list[dict]:
    """Posting-named people first, then a relevant functional leader or recruiter, then founders.
    For a small startup or a founder's-office role, a founder moves up."""
    fams = json.loads(job.get("role_families") or "[]") or [job.get("role_family") or ""]
    founder_role = "founders_office" in fams
    focus = {"founders_office": r"ceo|founder|chief of staff", "strategy_ops": r"strategy|operations|coo|ceo",
             "applied_ai_product": r"product|ai|cto|ml", "product_analytics": r"analytics|data|product", "solutions": r"solutions|customer|deploy"}
    pat = "|".join(focus.get(f, "") for f in fams if focus.get(f)) or r"$^"
    for p in people:
        t = (p.get("title") or "").lower()
        if p["origin"] == "posting":
            continue
        if re.search(r"founder|ceo", t) and (founder_role or small_company):
            p["rank"], p["why"] = 8, f"{p['why']}. Founder of a {'small company' if small_company else 'company'}; best placed for a {'founder-facing' if founder_role else 'small-team'} role"
        elif re.search(pat, t):
            p["rank"], p["why"] = min(p["rank"], 18), f"{p['why']}. Leads the function this role sits in"
        elif re.search(r"recruit|talent|people", t):
            p["rank"], p["why"] = min(p["rank"], 22), f"{p['why']}. Handles hiring"
    seen, out = set(), []
    for p in sorted(people, key=lambda x: x["rank"]):
        k = norm(p["name"])
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out[:MAX_PER_JOB]


def save_contacts(db: DB, people: list[dict], *, job_id: int | None, startup_id: int | None, company: str) -> list[int]:
    ids = []
    for p in people:
        key = recipient_key(p["name"], company, p.get("profile_url"))
        row = db.one("SELECT id FROM contacts WHERE job_id IS ? AND recipient_key = ?", (job_id, key))
        values = {"title": p.get("title"), "evidence_url": p["evidence_url"], "evidence_text": p["evidence_text"], "why": p["why"],
                  "rank": p["rank"], "verified_at": _today(), "status": "verified" if p["evidence_url"] else "unresolved"}
        if p.get("profile_url"):
            values["profile_url"] = p["profile_url"]
        if row:
            db.update("contacts", row["id"], values)
            ids.append(row["id"])
        else:
            ids.append(db.insert("contacts", {**values, "job_id": job_id, "startup_id": startup_id, "company": company, "name": p["name"],
                                              "profile_url": p.get("profile_url"), "origin": p["origin"], "recipient_key": key,
                                              "created_at": now_iso()}))
    return ids


LINKEDIN_PROFILE = re.compile(r"^https://(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9\-_%]{3,100})/?(?:[?#].*)?$", re.I)


def linkedin_profile(url: str) -> str:
    """A LinkedIn profile address you pasted, in one form: https://www.linkedin.com/in/<name>. Tracking
    parameters are dropped, so the same person pasted twice is the same contact. Nothing is fetched."""
    m = LINKEDIN_PROFILE.match(url.strip())
    if not m:
        raise ValueError("Paste a LinkedIn profile address like https://www.linkedin.com/in/their-name (not a search, company or post link).")
    return f"https://www.linkedin.com/in/{m.group(1)}"


def add_manual(db: DB, *, job_id: int | None, startup_id: int | None, company: str, name: str, title: str = "", profile_url: str = "",
               evidence_url: str = "") -> int:
    """Your own entry, e.g. from a LinkedIn page you opened yourself. Stored as you typed it."""
    if not name.strip() or not company.strip():
        raise ValueError("Add the person's name and company.")
    for u in (profile_url, evidence_url):
        if u and not u.strip().startswith("https://"):
            raise ValueError("Links must start with https://")
    profile_url = linkedin_profile(profile_url) if profile_url and "linkedin.com" in profile_url.lower() else profile_url.strip()
    status = "added_by_you" if (profile_url or evidence_url) else "unresolved"
    p = {"name": name.strip(), "title": title.strip() or None, "origin": "manual", "evidence_url": evidence_url or profile_url, "evidence_text": "Added by you",
         "why": "Added by you", "rank": 1, "profile_url": profile_url or None}
    cid = save_contacts(db, [p], job_id=job_id, startup_id=startup_id, company=company.strip())[0]
    db.update("contacts", cid, {"status": status, "origin": "manual"})
    return cid


def discover_for_job(db: DB, fetcher: Fetcher, job_id: int) -> dict:
    job = db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if not job:
        raise ValueError("Job not found")
    startup = db.one("SELECT * FROM startups WHERE company_id = ?", (job["company_id"],)) if job["company_id"] else None
    startup = startup or db.one("SELECT * FROM startups WHERE name_key = ?", (norm(job["employer"]),))
    people = from_posting(job)
    domain = (startup or {}).get("domain")
    if not domain and job["company_id"]:
        careers = db.scalar("SELECT careers_url FROM companies WHERE id = ?", (job["company_id"],)) or ""
        host = urlsplit(careers).hostname or ""
        domain = None if ATS_HOSTS.search(host) else host.removeprefix("www.").removeprefix("careers.").removeprefix("jobs.") or None
    tried = ["posting"]
    if len(people) < MAX_PER_JOB and domain:
        people += from_team_page(fetcher, domain, job["employer"])
        tried.append("team page")
    if len(people) < MAX_PER_JOB and startup:
        for ann in db.all("SELECT a.url, a.text FROM funding_events e JOIN announcements a ON a.url = e.announcement_url "
                          "WHERE e.startup_id = ? ORDER BY e.announced_on DESC LIMIT 2", (startup["id"],)):
            people += from_announcement(ann["text"] or "", ann["url"], job["employer"])
        tried.append("funding announcement")
    small = bool(startup) and (funding_small(db, startup["id"]))
    ranked = rank_for_job(people, job, small)
    ids = save_contacts(db, ranked, job_id=job_id, startup_id=startup["id"] if startup else None, company=job["employer"])
    return {"found": len(ranked), "contact_ids": ids, "checked": tried}


def funding_small(db: DB, startup_id: int) -> bool:
    r = db.scalar("SELECT round FROM funding_events WHERE startup_id = ? ORDER BY announced_on DESC LIMIT 1", (startup_id,))
    return r in ("pre_seed", "seed", "angel", "pre_series_a", "series_a")


# ---------------------------------------------------------------- drafts
# A draft says three true things: the role, one sentence quoted word for word from the posting, and at
# most two facts from your profile. Every claim about you must map to one of those facts; anything else
# is rejected and the template, built from the same facts, is kept.
MAX_FACTS = 2
NOTE_LIMIT = 300
MESSAGE_LIMIT = 1200
CLAIM_VERB = re.compile(r"\b(worked|work on|built|build|led|lead|ran|run|managed|manage|delivered|developed|created|designed|analy[sz]ed|owned|"
                        r"drove|launched|spent|used|presented|partnered|handled|grew|improved|reduced|increased|shipped|implemented|"
                        r"automated|experience in|experience with|background in|years? (of|in|at))\b", re.I)
SELF = re.compile(r"\b(I|I've|I'm|I'd|my|me)\b")
WORD = re.compile(r"[a-z][a-z0-9+#]{3,}")
DUTY = re.compile(r"\b(you will|you'll|responsib|own|lead|drive|build|work with|partner|requirements?|experience|must|looking for)\b", re.I)
GENERIC_WORDS = {"role", "team", "your", "with", "this", "that", "would", "like", "have", "been", "work", "worked", "interested", "applying",
                 "also", "about", "from", "which", "their", "there", "where", "into", "over", "years", "year", "past", "recent", "recently"}


def pick_facts(profile: dict, job: dict, fit: dict | None, limit: int = MAX_FACTS) -> list[dict]:
    """Facts the fit analysis tied to this job's requirements first, then the best keyword overlap."""
    facts = {f["id"]: f for f in profile.get("facts", [])}
    out: list[dict] = []
    for ev in (fit or {}).get("output", {}).get("evidence", []):
        for fid in ev.get("facts", []):
            if fid in facts and facts[fid] not in out:
                out.append(facts[fid])
    words = set(WORD.findall(f"{job['title']} {job.get('description_text') or ''}".lower()))
    for f in sorted(facts.values(), key=lambda f: -len(words & set(WORD.findall(f["text"].lower())))):
        if f not in out:
            out.append(f)
    return out[:limit]


def pick_fact(profile: dict, job: dict, fit: dict | None) -> dict | None:
    facts = pick_facts(profile, job, fit, 1)
    return facts[0] if facts else None


# A full stop after these is not the end of a sentence ("on time (e.g. board decks)").
SENTENCE_END = re.compile(r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)(?<!\bvs\.)(?<!\bInc\.)(?<!\bLtd\.)(?<!\bNo\.)(?<=[.!?])\s+|\n+")
CULTURE = re.compile(r"^(we|we're|our|at \w+|join|about us|why )\b|\b(we are|our (mission|culture|values))\b", re.I)


def _sentences(text: str) -> list[str]:
    out = []
    for p in SENTENCE_END.split(text or ""):
        p = p.strip(" -•*\t")
        if 25 <= len(p) <= 160 and p.count("(") == p.count(")"):
            out.append(p)
    return out


def pick_detail(job: dict, facts: list[dict], page_text: str | None = None) -> str | None:
    """One sentence, word for word from the posting (else the company page), about the work itself: a
    duty or requirement, not the company's description of its culture. Among those, the one that shares
    the most words with your facts. None when nothing suitable exists."""
    fact_words = set(WORD.findall(" ".join(f["text"] for f in facts).lower()))
    for text in (job.get("description_text"), page_text):
        cands = [s for s in _sentences(text or "") if DUTY.search(s) and not CULTURE.search(s)
                 and not re.search(r"https?://|@|\bapply\b|\bbenefits?\b|\bequal opportunity\b", s, re.I)]
        if cands:
            return max(cands, key=lambda s: (len(fact_words & set(WORD.findall(s.lower()))), -abs(len(s) - 90)))
    return None


def _short_fact(f: dict, limit: int = 120) -> str:
    """The fact itself if short, else its opening clause (up to the first ";" or ", "), unchanged."""
    text = _fact_line(f)
    if len(text) <= limit:
        return text
    # Clause ends outside brackets ("(Business Intelligence, 2022-2025)" stays whole). Keep adding clauses
    # until the text says what was done, not only where and when; stop at a semicolon.
    ends, depth = [], 0
    for i, ch in enumerate(text):
        depth += (ch == "(") - (ch == ")")
        if depth == 0 and (text.startswith(", ", i) or ch == ";"):
            ends.append((i, ch == ";"))
    best = ""
    for i, hard in ends:
        head = text[:i].strip()
        if len(head) > limit:
            break
        best = head
        if hard or (len(head) >= 50 and CLAIM_VERB.search(head) or re.search(r"\b(was|led|owned|built|ran|designed)\b", head)):
            break
    return best if len(best) >= 20 and re.search(r"\b(was|led|owned|built|ran|designed|worked|managed|delivered|developed|created)\b|\w+ed\b", best) else ""


def _fragment(detail: str, limit: int = 110) -> str:
    """The start of the quoted sentence, cut at a word, for a note that has no room for all of it."""
    if len(detail) <= limit:
        return detail
    return detail[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def detail_for(contact: dict, job: dict) -> str:
    """Where the quoted detail comes from, for the record."""
    return pick_detail(job, []) or f"The {job['title']} opening at {job['employer']}"


def _fact_line(f: dict) -> str:
    return f["text"].strip().rstrip(".")


def _as_list(facts) -> list[dict]:
    if isinstance(facts, dict):
        return [facts]
    return list(facts or [])


def template_draft(contact: dict, job: dict, facts, detail: str | None = None) -> tuple[str, str]:
    """Built only from the role, the quoted detail and your facts, so it always passes the checks."""
    facts = _as_list(facts)
    first = contact["name"].split()[0]
    # The note goes to someone at the company, so it names the role, not the company; the message names both.
    lead = f"Hi {first}, I'm interested in your {job['title']} role."
    ask = " Would you be open to a short chat?"
    shorts = [s for s in (_short_fact(f) for f in facts) if s]
    # The note carries the quote and one fact when they fit in 300 characters: the whole fact, else its
    # opening clause; the whole quote, else its start. Without room for both, the quote alone.
    space = NOTE_LIMIT - len(lead) - len(ask)
    fact_texts = [t for t in [_fact_line(f) for f in facts[:1]] + shorts[:1] + [_short_fact(facts[0], space // 2) if facts else ""] if t]

    def build(fact_text: str) -> str | None:
        mine = f" My background: {fact_text}." if fact_text else ""
        if not detail:
            return lead + mine + ask if len(lead + mine + ask) <= NOTE_LIMIT else None
        room = space - len(mine) - len(' The posting says: "".')
        if room < 45:                       # too little left to quote anything meaningful
            return None
        d = detail if len(detail) <= room else _fragment(detail, room - 1)
        q = f' The posting says: "{d}"' + ("" if d.endswith((".", "!", "?", "…")) else ".")
        return lead + q + mine + ask

    note = next((n for n in (build(t) for t in [*fact_texts, ""]) if n and len(n) <= NOTE_LIMIT), (lead + ask)[:NOTE_LIMIT])
    lines = [f"Hi {first},", "",
             f"I'm applying for the {job['title']} role at {job['employer']} and wanted to reach out directly"
             + (f", given your role as {contact['title']}." if contact.get("title") else ".")]
    if detail:
        lines += ["", f'The posting says: "{detail}"']
    if facts:
        lines += ["", "From my background:", *(f"- {_fact_line(f)}." for f in facts)]
    lines += ["", "If you're open to it, I'd value 15 minutes to understand what the team needs most from this hire.", "", "Thanks,"]
    return note, "\n".join(lines)[:MESSAGE_LIMIT]


def draft_prompt(contact: dict, job: dict, facts, profile: dict, detail: str | None = None) -> str:
    facts = _as_list(facts)
    not_claimed = "; ".join(profile.get("not_claimed", []))
    fact_lines = "\n".join(f"{f['id']}: {f['text']}" for f in facts) or "none"
    return (
        "Write a LinkedIn connection note and a longer first message from a job seeker.\n"
        f"ROLE: {job['title']} at {job['employer']}\n"
        f"RECIPIENT: {contact['name']}, {contact.get('title') or 'title unknown'}\n"
        f"D1 (one sentence from the posting; quote it word for word, in quotation marks, once): <<<SOURCE\n{detail or 'none'}\nSOURCE>>>\n"
        f"FACTS ABOUT THE SENDER (the only things you may say about the sender):\n{fact_lines}\n"
        f"The sender does NOT claim: {not_claimed or 'nothing listed'}. Never say the sender held a product manager or chief of staff title, "
        "has production machine-learning experience, used the recipient's product, or knows the recipient. Add no numbers.\n"
        "No generic praise. Name the role and the company. In \"claims\", list every sentence that says something about the sender, "
        "each with the fact id it comes from.\n"
        "Schema: {\"note\": str (under 280 characters), \"message\": str (under 900 characters), "
        "\"claims\": [{\"text\": str, \"fact\": \"P1\"}], \"quote\": str (the D1 words you quoted), \"injection_seen\": bool}. "
        "Write compact JSON on one line."
    )


def unbacked_claims(text: str, facts) -> list[str]:
    """Sentences that claim experience for the sender but share too little with every fact given, or
    carry a number no fact contains. Empty when every claim about you maps to a fact."""
    facts = _as_list(facts)
    bad = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        sent = sent.strip(" -•")
        if not sent or not CLAIM_VERB.search(sent):
            continue
        about_me = SELF.search(sent) or re.match(r"(Worked|Built|Led|Ran|Managed|Delivered|Developed|Created|Designed|Owned|Drove)\b", sent)
        if not about_me:
            continue
        words = set(WORD.findall(sent.lower())) - GENERIC_WORDS
        nums = set(re.findall(r"\d+(?:\.\d+)?", sent))
        fact_words = [set(WORD.findall(f["text"].lower())) for f in facts]
        union = set().union(*fact_words) if fact_words else set()
        # Backed: most of what the sentence says comes from the facts given, it shares at least two words
        # with one of them, and every number in it appears in a fact.
        backed = (bool(words) and len(words & union) / len(words) >= 0.6 and any(len(words & fw) >= 2 for fw in fact_words)
                  and nums <= set(re.findall(r"\d+(?:\.\d+)?", " ".join(f["text"] for f in facts))))
        if not backed:
            bad.append(sent[:160])
    return bad


def claims_the_job(text: str, job: dict) -> bool:
    """"I'm an Implementation Manager at <the company>": the sender claims the role being applied for, or
    claims to work at the company already. Seen in a local-model draft on real data."""
    title, employer = re.escape(job["title"].lower()), re.escape(job["employer"].lower())
    t = text.lower()
    return bool(re.search(rf"\bi(?:'m| am)\s+(?:an?\s+|the\s+|currently\s+)?{title}\b", t)
                or re.search(rf"\bi(?:'m| am|'ve been| have been)?\s+(?:currently\s+)?(?:work|working|employed)\b[^.\n]{{0,40}}\bat {employer}\b", t)
                or re.search(rf"\bmy (role|work|team|time) at {employer}\b", t))


def validate_draft(data: dict, contact: dict, job: dict, facts, detail: str | None = None) -> tuple[str, str]:
    facts = _as_list(facts)
    note, msg = str(data.get("note") or "").strip(), str(data.get("message") or "").strip()
    both = note + "\n" + msg
    problems = []
    if not note or len(note) > NOTE_LIMIT:
        problems.append(f"note missing or over {NOTE_LIMIT} characters")
    if not msg or len(msg) > MESSAGE_LIMIT:
        problems.append("message missing or too long")
    if job["employer"].lower() not in msg.lower():
        problems.append("message does not name the company")
    if BANNED.search(both):
        problems.append("generic praise or invented familiarity")
    if FALSE_SELF.search(both):
        problems.append("claims a title or experience the profile does not support")
    if claims_the_job(both, job):
        problems.append("says the sender already holds this role or works at this company")
    ids = {f["id"] for f in facts}
    claims = data.get("claims") if isinstance(data.get("claims"), list) else []
    if any(not isinstance(c, dict) or c.get("fact") not in ids for c in claims):
        problems.append("a claim cites a fact id that was not given")
    unbacked = unbacked_claims(both, facts)
    if unbacked:
        problems.append(f"a claim about you is not backed by a profile fact: \"{unbacked[0]}\"")
    quote = str(data.get("quote") or "")
    if detail and not find_quote(quote, detail):
        problems.append("did not quote the posting detail word for word")
    elif detail and norm(quote) not in norm(both):
        problems.append("the quoted detail is not in the note or message")
    if problems:
        raise ValueError("Draft rejected: " + "; ".join(problems))
    return note, msg


def ensure_draft(db: DB, contact_id: int, profile: dict, fit: dict | None) -> int:
    """Create a usable template draft right away (no model needed). The model may improve it later."""
    c = db.one("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    job = db.one("SELECT * FROM jobs WHERE id = ?", (c["job_id"],)) if c["job_id"] else None
    if not job:
        raise ValueError("Drafts are written for a specific role.")
    row = db.one("SELECT id FROM outreach WHERE contact_id = ?", (contact_id,))
    if row:
        return row["id"]
    from .gaps import accepted_order
    facts = accepted_order(db, profile, job["id"])[:MAX_FACTS] or pick_facts(profile, job, fit)
    detail = pick_detail(job, facts)
    note, msg = template_draft(c, job, facts, detail)
    now = now_iso()
    return db.insert("outreach", {"contact_id": contact_id, "job_id": job["id"], "recipient_key": c["recipient_key"], "note_text": note,
                                  "message_text": msg, "drafted_by": "template",
                                  "inputs_json": json.dumps({"facts": facts, "detail": detail, "detail_source": job.get("official_url")}),
                                  "state": "drafted", "created_at": now, "updated_at": now})


# ---------------------------------------------------------------- follow-ups and marking sent
FOLLOWUP_DAYS = (5, 12)


def followup_text(contact: dict, job: dict, facts: list[dict], n: int) -> str:
    """Short follow-ups from the same facts. Day 5 adds one fact; day 12 asks for a pointer and stops."""
    first = contact["name"].split()[0]
    if n == 1:
        extra = f" In short: {_fact_line(facts[0])}." if facts else ""
        return (f"Hi {first}, following up on my note about the {job['title']} role at {job['employer']}.{extra} "
                "Happy to share more if it's useful.")[:NOTE_LIMIT]
    return (f"Hi {first}, one last note on the {job['title']} role at {job['employer']}. If someone else is better placed to talk "
            "about it, I'd be grateful for a pointer. Thanks either way.")[:NOTE_LIMIT]


def mark_sent(db: DB, outreach_id: int, at: str | None = None) -> dict:
    """You sent the note yourself. Record the date, move the role to Contact made (never backwards),
    and write the day-5 and day-12 follow-up drafts, due from that date."""
    from datetime import date, timedelta

    from . import pipeline
    o = db.one("SELECT * FROM outreach WHERE id = ?", (outreach_id,))
    if not o:
        raise ValueError("Draft not found")
    if o["state"] in ("sent", "contacted"):
        return {"state": o["state"], "sent_at": o["sent_at"]}
    when = pipeline._when(at)
    db.update("outreach", outreach_id, {"state": "contacted", "sent_at": when, "updated_at": now_iso()})
    if o["job_id"]:
        pipeline.record(db, o["job_id"], "Contact made", at=when[:10], origin="outreach", advance_only=True)
        c = db.one("SELECT * FROM contacts WHERE id = ?", (o["contact_id"],))
        job = db.one("SELECT * FROM jobs WHERE id = ?", (o["job_id"],))
        inputs = json.loads(o["inputs_json"] or "{}")
        facts = inputs.get("facts") or ([inputs["fact"]] if inputs.get("fact") else [])
        sent_day = date.fromisoformat(when[:10])
        for n, days in enumerate(FOLLOWUP_DAYS, 1):
            if not db.scalar("SELECT 1 FROM outreach_followups WHERE outreach_id = ? AND n = ?", (outreach_id, n)):
                db.insert("outreach_followups", {"outreach_id": outreach_id, "n": n, "due_on": (sent_day + timedelta(days=days)).isoformat(),
                                                 "text": followup_text(c, job, facts, n), "state": "drafted", "created_at": now_iso()})
    return {"state": "contacted", "sent_at": when}


def mark_followup_sent(db: DB, followup_id: int, at: str | None = None) -> dict:
    from . import pipeline
    f = db.one("SELECT * FROM outreach_followups WHERE id = ?", (followup_id,))
    if not f:
        raise ValueError("Follow-up not found")
    when = pipeline._when(at)
    db.update("outreach_followups", followup_id, {"state": "sent", "sent_at": when})
    return {"state": "sent", "sent_at": when}


def followups_due(db: DB, today: str) -> list[dict]:
    """Follow-ups due on or before `today` for roles still waiting: no reply yet, not ended. The day-12
    one waits until the day-5 one is sent."""
    return db.all(
        "SELECT f.id, f.n, f.due_on, f.text, o.id AS outreach_id, o.job_id, c.name, c.company, j.title FROM outreach_followups f "
        "JOIN outreach o ON o.id = f.outreach_id JOIN contacts c ON c.id = o.contact_id JOIN jobs j ON j.id = o.job_id "
        "WHERE f.state = 'drafted' AND f.due_on <= ? AND j.status IN ('Interested', 'Investigate', 'Applied', 'Contact made') "
        "AND NOT (f.n = 2 AND EXISTS (SELECT 1 FROM outreach_followups g WHERE g.outreach_id = f.outreach_id AND g.n = 1 "
        "AND g.state = 'drafted')) ORDER BY f.due_on", (today,))


# ---------------------------------------------------------------- sending
class NoMessaging:
    """No authorised messaging integration is configured. Sending is unavailable."""
    name = None
    available = False
    reason = "No authorised messaging integration is configured. LinkedIn does not offer messaging access to personal tools."

    def send(self, contact: dict, text: str) -> str:   # pragma: no cover - never called
        raise RuntimeError(self.reason)


DEFAULT_SETTINGS = {"autosend": False, "daily_cap": 5, "stopped": False, "job_ids": []}


def settings(db: DB) -> dict:
    return {**DEFAULT_SETTINGS, **(db.get_setting("outreach_settings") or {})}


def save_settings(db: DB, data: dict) -> dict:
    s = settings(db)
    if "autosend" in data:
        s["autosend"] = bool(data["autosend"])
    if "stopped" in data:
        s["stopped"] = bool(data["stopped"])
    if "daily_cap" in data:
        s["daily_cap"] = max(0, min(25, int(data["daily_cap"])))
    if "job_ids" in data:
        s["job_ids"] = [int(x) for x in data["job_ids"]][:200]
    db.set_setting("outreach_settings", s)
    return s


def send_due(db: DB, provider) -> dict:
    """Send eligible drafts for the opportunities you selected, within the daily cap. Each recipient
    is contacted at most once. The state is saved as 'sending' before the call, so a crash or timeout
    leaves 'send_unknown', which is never retried automatically."""
    s = settings(db)
    if not getattr(provider, "available", False):
        return {"sent": 0, "reason": getattr(provider, "reason", "No messaging integration")}
    if s["stopped"] or not s["autosend"]:
        return {"sent": 0, "reason": "Automatic sending is off or stopped"}
    today = _today()
    sent_today = db.scalar("SELECT COUNT(*) FROM outreach WHERE state IN ('sent', 'sending', 'send_unknown') AND substr(sent_at, 1, 10) = ?", (today,)) or 0
    done = {r["recipient_key"] for r in db.all("SELECT recipient_key FROM outreach WHERE state IN ('sent', 'sending', 'send_unknown', 'contacted')")}
    out = {"sent": 0, "failed": 0, "unknown": 0}
    for o in db.all("SELECT * FROM outreach WHERE state = 'drafted' ORDER BY id"):
        if sent_today >= s["daily_cap"]:
            break
        if o["job_id"] not in s["job_ids"] or o["recipient_key"] in done:
            continue
        contact = db.one("SELECT * FROM contacts WHERE id = ?", (o["contact_id"],))
        if contact["status"] not in ("verified", "added_by_you"):
            continue
        now = now_iso()
        db.update("outreach", o["id"], {"state": "sending", "sent_at": now, "updated_at": now, "channel": provider.name})
        done.add(o["recipient_key"])
        sent_today += 1
        try:
            result = provider.send(contact, o["note_text"])
        except Exception as e:  # noqa: BLE001 - unclear outcome: never retried blindly
            db.update("outreach", o["id"], {"state": "send_unknown", "error": str(e)[:300], "updated_at": now_iso()})
            out["unknown"] += 1
            continue
        state = "sent" if result == "sent" else "failed"
        db.update("outreach", o["id"], {"state": state, "error": None if state == "sent" else str(result)[:300], "updated_at": now_iso()})
        out["sent" if state == "sent" else "failed"] += 1
    return out
