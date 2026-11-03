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
    ("applied_ai_product", "Applied AI product",
     r"\b(ai|ml|genai|gen ai|llm|machine learning|agents?)\b.{0,30}\bproduct\b|\bproduct\b.{0,40}\b(ai|ml|genai|llm|agents?)\b"),
    ("solutions", "Solutions and implementation",
     r"solutions? (engineer|architect|consultant|lead|manager|specialist)|forward[- ]deployed|implementation|deployment (engineer|strategist|lead|manager)"
     r"|customer engineer|technical (consultant|solutions)|professional services|onboarding (engineer|manager|specialist)"
     r"|applied ai (engineer|specialist|consultant|strategist|lead)|ai (deployment|solutions|strategist|consultant|adoption)|value engineer"),
    ("product_analytics", "Product analytics",
     r"product analy|analytics (lead|manager)|data analyst|business analyst|insights (analyst|manager|lead)|decision scien|analytics engineer|business intelligence|bi (analyst|engineer|developer)"),
    ("founders_office", "Founder's office and strategy",
     r"founder'?s'? office|chief of staff|strategy (and|&) operations|biz ?ops|business operations|strategy (manager|lead|associate|analyst)|special projects|strategic (initiatives|operations)"),
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


def bucket(title: str, family: str, loc_cls: str, wanted_families: list[str]) -> tuple[str, str]:
    """Return (candidate | review | outside, reason in plain words)."""
    if re.search(TOO_JUNIOR, title, re.I):
        return "outside", "Internship or trainee role"
    if loc_cls in ("remote_other", "other", "india_other"):
        return "outside", f"Location: {LOCATION_LABEL[loc_cls].lower()}"
    if family == "other":
        return "outside", "Title outside your role families"
    target = family in wanted_families
    loc_ok = loc_cls in ("bengaluru", "remote_india")
    if target and loc_ok:
        if re.search(TOO_SENIOR, title, re.I):
            return "review", "Seniority in the title may be above your experience"
        return "candidate", f"{FAMILY_LABEL[family]} role, {LOCATION_LABEL[loc_cls]}"
    if not target and family not in ("ambiguous", "product_management"):
        return "outside", f"{FAMILY_LABEL[family]} is not in your selected role families"
    reasons = []
    if not loc_ok:
        reasons.append(LOCATION_LABEL[loc_cls])
    if not target:
        reasons.append(f"title is {FAMILY_LABEL[family].lower()}")
    return "review", "Check: " + "; ".join(reasons)
