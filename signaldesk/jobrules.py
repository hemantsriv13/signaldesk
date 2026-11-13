"""Deterministic job rules: location class, salary wording, role family and the review bucket.

These run on every listing without the model. The model never decides location or salary; it
only explains fit, and its view never overrides these fields.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

BLR = re.compile(r"\b(bengaluru|bangalore|blr)\b", re.I)
INDIA = re.compile(r"\b(india|indian|bengaluru|bangalore|mumbai|delhi|new delhi|gurugram|gurgaon|noida|hyderabad|pune|chennai|kolkata|ahmedabad|jaipur|kochi)\b", re.I)
REMOTE = re.compile(r"\b(remote|work from home|wfh|distributed|anywhere)\b", re.I)
WORLDWIDE = re.compile(r"\b(anywhere|worldwide|global(ly)?|any location|any country)\b", re.I)
OTHER_REGION = re.compile(
    r"\b(us|u\.s\.|usa|united states|canada|mexico|brazil|latam|uk|united kingdom|ireland|europe|emea|eu|germany|france|spain|"
    r"netherlands|poland|portugal|switzerland|sweden|israel|uae|dubai|singapore|japan|tokyo|korea|seoul|australia|sydney|"
    r"new zealand|philippines|vietnam|indonesia|malaysia|san francisco|new york|seattle|london|berlin|paris|amsterdam|toronto|"
    r"austin|boston|chicago|denver|dublin|zurich|munich|tel aviv|bay area|nyc|sf)\b", re.I)
RESTRICT_LINE = re.compile(r"(must|need to|required to|should) (be )?(be )?(based|located|reside|live|work)|eligible to work in|work authori[sz]ation|right to work|time ?zone|based in|located in|open to candidates in|hiring in", re.I)


@dataclass
class LocationVerdict:
    cls: str          # bengaluru | remote_india | remote_unclear | india_other | india_unspecified | remote_other | other | unknown
    evidence: str     # the original wording the verdict rests on


LOCATION_LABEL = {
    "bengaluru": "Bengaluru",
    "remote_india": "Remote, India stated",
    "remote_unclear": "Remote, eligibility unclear",
    "india_other": "India, other city",
    "india_unspecified": "India, city not stated",
    "remote_other": "Remote, other countries",
    "other": "Other location",
    "unknown": "Location not stated",
}


# The views the app shows: Bengaluru (incl. explicitly Bengaluru-based hybrid), remote open to India,
# uncertain (kept out of top matches until there is evidence) and elsewhere.
LOCATION_GROUP = {"bengaluru": "bengaluru", "remote_india": "remote_india", "remote_unclear": "uncertain", "india_unspecified": "uncertain",
                  "unknown": "uncertain", "india_other": "elsewhere", "remote_other": "elsewhere", "other": "elsewhere"}
GROUP_LABEL = {"bengaluru": "Bengaluru", "remote_india": "Remote, open to India", "uncertain": "Location uncertain", "elsewhere": "Elsewhere"}


def classify_location(location: str | None, workplace: str | None = None, description: str | None = None) -> LocationVerdict:
    loc = (location or "").strip()
    both = f"{loc} {workplace or ''}".strip()
    remote = bool(REMOTE.search(both))
    restrictions = [line.strip() for line in (description or "").splitlines()
                    if len(line) < 400 and RESTRICT_LINE.search(line)]
    evidence = " | ".join([both, *restrictions]).strip(" |")
    # Negated eligibility and conflicting geography require review. A keyword
    # alone is never positive evidence that a candidate can work from India.
    # An on-site role with a stated location is placed by that field. Its
    # description lines ("collaborate across US time zones", "report to a
    # director based in Europe") describe the team, not where you may work.
    relevant = [both, *restrictions] if remote or not loc else [both]
    if any(INDIA.search(line) and re.search(
            r"\b(not|no|outside|except|excluding|ineligible|cannot|can't)\b", line, re.I)
           for line in relevant):
        return LocationVerdict("remote_unclear" if remote else "unknown", evidence)
    india_evidence = any(INDIA.search(line) for line in relevant)
    foreign_evidence = any(OTHER_REGION.search(line) for line in relevant)
    if india_evidence and foreign_evidence:
        return LocationVerdict("remote_unclear" if remote else "unknown", evidence)
    # Do not infer remote work merely because a description mentions India.
    if remote:
        if re.search(r"\b(not remote|no remote|on[- ]site only)\b", evidence, re.I):
            return LocationVerdict("unknown", evidence)
        if foreign_evidence:
            return LocationVerdict("remote_other", evidence)
        if india_evidence:
            return LocationVerdict("remote_india", evidence)
        return LocationVerdict("remote_unclear", evidence)
    place = loc if INDIA.search(loc) else " | ".join(restrictions) if not loc else loc
    if BLR.search(place):
        return LocationVerdict("bengaluru", place)
    if INDIA.search(place):
        cities = [m.group(0).lower() for m in INDIA.finditer(place)
                  if m.group(0).lower() not in ("india", "indian")]
        return LocationVerdict("india_other" if cities else "india_unspecified", place)
    return LocationVerdict("other" if loc or foreign_evidence else "unknown", evidence)


# ---------------------------------------------------------------- salary
MONEY = re.compile(r"(₹|\binr\b|\brs\.?|\blakh|\blpa\b|\bcrore|\bctc\b|\$|\busd\b|€|\beur\b|£|\bgbp\b)", re.I)
NUMBERISH = re.compile(r"\d")


def extract_salary(description: str | None, extra: str | None = None) -> tuple[str | None, str | None]:
    """Return (original wording, kind). Kind lists what the wording says it is: CTC, base, OTE, total, unspecified."""
    lines = []
    if extra:
        lines.append(extra.strip())
    for line in (description or "").splitlines():
        line = line.strip()
        if len(line) < 400 and MONEY.search(line) and NUMBERISH.search(line):
            if re.search(r"salary|pay|compensation|ctc|range|lpa|lakh|base|ote|per (year|annum)|annual|\bk\b|,000", line, re.I):
                lines.append(line)
    if not lines:
        return None, None
    text = " | ".join(dict.fromkeys(lines))[:600]
    kinds = []
    if re.search(r"\bctc\b|cost to company", text, re.I):
        kinds.append("CTC")
    if re.search(r"\bbase\b", text, re.I):
        kinds.append("base")
    if re.search(r"\bote\b|on[- ]target", text, re.I):
        kinds.append("OTE")
    if re.search(r"total (compensation|rewards|pay)|\bequity\b|\bbonus\b|\brsu", text, re.I):
        kinds.append("other components mentioned")
    return text, ", ".join(kinds) or "unspecified"


def inr_lakh(text: str | None) -> float | None:
    """Best-effort annual INR amount in lakh, from the first INR figure. None when not INR or unclear."""
    if not text or not re.search(r"₹|\binr\b|\brs\.?|lakh|lpa|crore", text, re.I):
        return None
    # Ranges, multiple amounts, bounds and non-annual rates cannot safely
    # become a single annual salary. Preserve their wording for manual review.
    if (len(re.findall(r"\d[\d,]*(?:\.\d+)?", text)) != 1
            or re.search(r"per\s+(month|week|day|hour)|/(month|mo|week|day|hour)\b|"
                         r"monthly|weekly|daily|hourly|p\.?m\.?\b|up to|at least|"
                         r"starting|from\s|minimum|maximum|\+", text, re.I)):
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lpa|lakh|l\b)", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*crore", text, re.I)
    if m:
        return float(m.group(1)) * 100
    m = re.search(r"(?:₹|inr|rs\.?)\s*([\d,]{6,})", text, re.I)
    if m:
        return int(m.group(1).replace(",", "")) / 100000
    return None


def compensation_note(salary_text: str | None, salary_kind: str | None, threshold_lakh: float) -> str:
    if not salary_text:
        return "Not disclosed"
    if not re.search(r"₹|\binr\b|\brs\.?|lakh|lpa|crore", salary_text, re.I):
        return "Disclosed, not in INR lakh: compare by hand"
    if "CTC" in (salary_kind or "") and "base" in (salary_kind or ""):
        return f"Multiple pay components: compare by hand. {salary_text}"
    amount = inr_lakh(salary_text)
    if amount is None:
        return f"Disclosed, but can't be compared automatically (amount, range or pay period): {salary_text}"
    kind = salary_kind or "unspecified"
    if "CTC" in kind:
        return f"CTC about ₹{amount:g}L: {'meets' if amount >= threshold_lakh else 'below'} your ₹{threshold_lakh:g}L preference"
    if "base" in kind:
        if amount >= threshold_lakh:
            return f"Base about ₹{amount:g}L: CTC would be at least this, so it meets your preference"
        return f"Base about ₹{amount:g}L: CTC unknown, so it can't be compared to your preference"
    return f"About ₹{amount:g}L, type not stated (CTC or base unknown)"


# ---------------------------------------------------------------- role family
FAMILIES = [
    ("applied_ai_product", "AI product and evaluations",
     r"\b(ai|ml|genai|gen ai|llm|machine learning|agents?)\b.{0,30}\bproduct\b|\bproduct\b.{0,40}\b(ai|ml|genai|llm|agents?)\b"
     r"|\b(ai|llm|ml|model) evals?\b|\b(ai|llm|ml|model) evaluations?\b|\bevals? (lead|manager|engineer|specialist|analyst|strategist)"),
    ("solutions", "Solutions and implementation",
     r"solutions? (engineer|architect|consultant|lead|manager|specialist)|forward[- ]deployed|implementation|deployment (engineer|strategist|lead|manager)"
     r"|customer engineer|technical (consultant|solutions)|professional services|onboarding (engineer|manager|specialist)"
     r"|applied ai (engineer|specialist|consultant|strategist|lead)|ai (deployment|solutions|strategist|consultant|adoption)|value engineer"),
    ("product_analytics", "Product analytics",
     r"product analy|analytics (lead|manager)|data analyst|business analyst|insights (analyst|manager|lead)|decision scien|analytics engineer|business intelligence|bi (analyst|engineer|developer)"),
    ("founders_office", "Founder's office and chief of staff",
     r"founder'?s'? office|founders office|office of the (ceo|founders?)|chief of staff"),
    ("strategy_ops", "Strategy and business operations",
     r"strategy (and|&) operations|\bs ?& ?o\b|biz ?ops|business operations|strategic (initiatives|operations|projects)"
     r"|product strategy|strategy (manager|lead|associate|analyst|director|head)|\bstrategy\b"),
]
GENERAL_PM = r"product manager|product lead|product owner|\bapm\b|product management"
AMBIGUOUS = (r"data scientist|program manager|customer success|technical account manager|operations (manager|lead|analyst)|consultant|strategist|"
             r"product specialist|research (analyst|associate)|partner (manager|engineer)|enablement|revenue operations|gtm")
TOO_JUNIOR = r"\bintern(ship)?\b|\btrainee\b|\bapprentice"
TOO_SENIOR = r"\b(director|vp|vice president|head of|chief (?!of staff)|principal|staff)\b"

FAMILY_LABEL = {k: label for k, label, _ in FAMILIES} | {"product_management": "Product management", "ambiguous": "Possibly related", "other": "Other roles"}


def role_family(title: str) -> str:
    for key, _label, pat in FAMILIES:
        if re.search(pat, title, re.I):
            return key
    if re.search(GENERAL_PM, title, re.I):
        return "product_management"
    if re.search(AMBIGUOUS, title, re.I):
        return "ambiguous"
    return "other"


def bucket(title: str, family: str | list[str], loc_cls: str, wanted_families: list[str]) -> tuple[str, str]:
    """Return (candidate | review | outside, reason in plain words). `family` may be one family or
    the job's full list of families; the job is a target when any of them is wanted."""
    fams = [f for f in (family if isinstance(family, list) else [family]) if f] or ["other"]
    if re.search(TOO_JUNIOR, title, re.I):
        return "outside", "Internship or trainee role"
    if loc_cls in ("remote_other", "other", "india_other"):
        return "outside", f"Location: {LOCATION_LABEL[loc_cls].lower()}"
    if fams == ["other"]:
        return "outside", "Title and duties outside your role families"
    hits = [f for f in fams if f in wanted_families]
    lead = hits[0] if hits else fams[0]
    loc_ok = loc_cls in ("bengaluru", "remote_india")
    if hits and loc_ok:
        if re.search(TOO_SENIOR, title, re.I):
            return "review", "Seniority in the title may be above your experience"
        return "candidate", f"{' + '.join(FAMILY_LABEL[f] for f in hits)} role, {LOCATION_LABEL[loc_cls]}"
    if not hits and not set(fams) & {"ambiguous", "product_management"}:
        return "outside", f"{FAMILY_LABEL[lead]} is not in your selected role families"
    reasons = []
    if not loc_ok:
        reasons.append(LOCATION_LABEL[loc_cls])
    if not hits:
        reasons.append(f"title is {FAMILY_LABEL[lead].lower()}")
    return "review", "Check: " + "; ".join(reasons)


# ---------------------------------------------------------------- roles from duties
# Titles alone mislead in both directions: "Special Projects" reporting to the founder is a
# founder's-office role; "account strategy" in a sales posting is not a strategy role.
SALES_TITLE = re.compile(r"\b(sales|account (executive|manager|director|lead)|business development|\bbdr\b|\bsdr\b|inside sales|key account|"
                         r"customer success|partnerships? (manager|executive|associate))\b", re.I)
ASSISTANT_TITLE = re.compile(r"\b(executive assistant|personal assistant|administrative|admin assistant|office manager|receptionist|\bea\b)\b", re.I)
EXPLICIT_FOUNDER = re.compile(r"chief of staff|founder'?s'? office|founders office|office of the (ceo|founders?)", re.I)
FOUNDER_DUTIES = [
    r"report(s|ing)? (directly )?(in)?to (the |our )?(co-?)?founders?\b|report(s|ing)? (directly )?to (the |our )?ceo\b",
    r"work(s|ing)? (closely|directly|side by side|hand in hand) with (the |our )?((co-?)?founders?|ceo)\b",
    r"office of the (ceo|founders?)",
    r"(own|owns|owning|drive|drives|driving|lead|leads|leading|run|runs|running)\b.{0,40}\b(cross-functional|company-wide|strategic)\b.{0,20}\b(initiatives?|projects?|launch(es)?|programs?)",
    r"special projects",
    r"\b(zero to one|0 ?(to|->|→) ?1)\b",
    r"(ceo|founders?)'?s? (priorities|agenda|initiatives|top priorities)",
]
STRATEGY_DUTIES = [
    r"(business|strategic|annual|quarterly) (planning|reviews?)|operating (cadence|plan|rhythm)|\bokrs?\b|board (decks?|meetings?|materials)",
    r"market (sizing|entry|research)|go-to-market strategy|pricing strategy|(company|business|growth) strategy|competitive (analysis|landscape)",
    r"unit economics|\bp&l\b|business cases?|investment memos?",
]
AI_DUTIES = [r"\b(llms?|genai|gen ai|large language models?|ai agents?|foundation models?)\b",
             r"\bevals?\b|evaluation (sets?|frameworks?|pipelines?|harness)|model (quality|behaviou?r)|\bai products?\b"]
ASSISTANT_DUTIES = re.compile(r"\b(calendar|scheduling meetings|travel (arrangements|bookings?)|expense reports?|inbox management|meeting logistics)\b", re.I)
PRODUCTISH_TITLE = re.compile(r"\b(product|operations|ops|associate|analyst|manager|lead|generalist|special projects|program)\b", re.I)


def _sentences(text: str | None) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip(" -•*\t") for p in parts if 12 <= len(p.strip()) <= 400]


def _duty_hits(sentences: list[str], patterns: list[str]) -> tuple[int, list[str]]:
    matched, lines = set(), []
    for pat in patterns:
        for s in sentences:
            if re.search(pat, s, re.I):
                matched.add(pat)
                if s not in lines:
                    lines.append(s)
                break
    return len(matched), lines


def classify_roles(title: str, description: str | None = None) -> tuple[list[str], list[str], bool]:
    """Return (families, evidence sentences, ambiguous). Several families can apply to one job.
    `ambiguous` marks a job worth one local-model look when its location already qualifies."""
    fams = [key for key, _label, pat in FAMILIES if re.search(pat, title, re.I)]
    sales, assistant = bool(SALES_TITLE.search(title)), bool(ASSISTANT_TITLE.search(title))
    explicit = bool(EXPLICIT_FOUNDER.search(title))
    if (sales or assistant) and not explicit:
        # "Account strategy", "strategic accounts" or an EA to the CEO are not these roles.
        fams = [f for f in fams if f not in ("founders_office", "strategy_ops")]
    sents = _sentences(description)
    evidence: list[str] = []
    if not (sales or assistant):
        n, lines = _duty_hits(sents, FOUNDER_DUTIES)
        assisting = sum(bool(ASSISTANT_DUTIES.search(s)) for s in sents)
        needed = 1 if re.search(r"special projects", title, re.I) else 2
        if n >= needed and assisting < 2 and "founders_office" not in fams:
            fams.append("founders_office")
            evidence += lines[:2]
        n, lines = _duty_hits(sents, STRATEGY_DUTIES)
        if n >= 2 and PRODUCTISH_TITLE.search(title) and "strategy_ops" not in fams:
            fams.append("strategy_ops")
            evidence += lines[:2]
    if "applied_ai_product" not in fams and re.search(r"\bproduct\b|operations|\bops\b|strategy|founder|chief of staff", title, re.I):
        n, lines = _duty_hits(sents, AI_DUTIES)
        if n >= 2:
            fams.append("applied_ai_product")
            evidence += lines[:1]
    if not fams:
        legacy = role_family(title)
        blocked = ("founders_office", "strategy_ops") if (sales or assistant) and not explicit else ()
        fams = [] if legacy == "other" or legacy in blocked else [legacy]
    ambiguous = (not fams or fams == ["ambiguous"]) and not (sales or assistant) and bool(
        _duty_hits(sents, FOUNDER_DUTIES)[0] or _duty_hits(sents, STRATEGY_DUTIES)[0])
    return (fams or ["other"]), list(dict.fromkeys(evidence))[:3], ambiguous


# ---------------------------------------------------------------- pay against the target
UNIT_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|l\b|cr(?:ores?)?\b)?\s*(?:-|–|—|to)\s*(?:₹|\binr\b|\brs\.?)?\s*(\d+(?:\.\d+)?)\s*(lpa|lakhs?|l\b|cr(?:ores?)?\b)", re.I)
UNIT_ONE = re.compile(r"(\d+(?:\.\d+)?)\s*(lpa|lakhs?|l\b|cr(?:ores?)?\b)", re.I)
RUPEES = re.compile(r"(?:₹|\binr\b|\brs\.?)\s*([\d,]{6,})(?:\s*(?:-|–|—|to)\s*(?:₹|\binr\b|\brs\.?)?\s*([\d,]{6,}))?", re.I)
NON_ANNUAL = re.compile(r"per\s+(month|week|day|hour)|/(month|mo|week|day|hour)\b|monthly|weekly|daily|hourly|p\.?m\.?\b|stipend", re.I)


def _lakh(value: str, unit: str) -> float:
    return float(value) * (100 if unit.lower().startswith("cr") else 1)


def inr_range_lakh(text: str | None) -> tuple[float, float] | None:
    """(low, high) annual INR in lakh from one figure or one range. None when unclear."""
    if not text or not re.search(r"₹|\binr\b|\brs\.?|lakh|lpa|crore", text, re.I) or NON_ANNUAL.search(text):
        return None
    m = UNIT_RANGE.search(text)
    if m:
        return _lakh(m.group(1), m.group(3)), _lakh(m.group(2), m.group(3))
    m = RUPEES.search(text)
    if m:
        lo = int(m.group(1).replace(",", "")) / 100000
        hi = int(m.group(2).replace(",", "")) / 100000 if m.group(2) else lo
        return lo, hi
    found = UNIT_ONE.findall(text)
    if len(found) == 1:
        v = _lakh(*found[0])
        return v, v
    return None


BAND_LABEL = {"above": "Confirmed above target", "overlaps": "Range overlaps target", "below": "Below target", "unknown": "Pay unknown"}


def comp_band(salary_text: str | None, salary_kind: str | None, target_lakh: float) -> tuple[str, str]:
    """Return (above | overlaps | below | unknown, plain explanation). Base and CTC stay distinct:
    a base below target says nothing about CTC, so it is unknown, never below."""
    if not salary_text:
        return "unknown", "Not disclosed"
    if not re.search(r"₹|\binr\b|\brs\.?|lakh|lpa|crore", salary_text, re.I):
        return "unknown", "Disclosed in another currency: compare by hand"
    kind = salary_kind or "unspecified"
    if "CTC" in kind and "base" in kind:
        return "unknown", "Several pay components stated: compare by hand"
    rng = inr_range_lakh(salary_text)
    if rng is None:
        return "unknown", "Disclosed, but the amount, range or pay period can't be compared automatically"
    lo, hi = rng
    span = f"₹{lo:g}L" if lo == hi else f"₹{lo:g}–{hi:g}L"
    if "base" in kind:
        if lo > target_lakh:
            return "above", f"Base {span}: CTC is at least this, above your ₹{target_lakh:g}L target"
        if hi > target_lakh:
            return "overlaps", f"Base {span} overlaps your ₹{target_lakh:g}L target; CTC would be higher"
        return "unknown", f"Base {span}; CTC not stated, so it can't be compared to your target"
    label = "CTC" if "CTC" in kind else "Pay (type not stated)"
    if lo > target_lakh:
        return "above", f"{label} {span}, above your ₹{target_lakh:g}L target"
    if hi < target_lakh:
        return "below", f"{label} {span}, below your ₹{target_lakh:g}L target"
    return "overlaps", f"{label} {span} overlaps your ₹{target_lakh:g}L target"
