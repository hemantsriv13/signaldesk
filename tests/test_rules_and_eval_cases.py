"""Deterministic checks on the hand-written evaluation cases (eval/cases.json) and the rules."""
import pytest

from signaldesk import analysis, collect, jobrules
from signaldesk.profile import DEFAULT_PREFS
from signaldesk.sources.feeds import content_basis
from signaldesk.text import html_to_text

from conftest import CASES


@pytest.mark.parametrize("case", CASES["jobs"], ids=lambda c: c["id"])
def test_job_case(case):
    p = {"title": case["title"], "location": case["location"], "workplace": None, "description_text": case["description"], "salary_extra": None}
    got = collect.classify(p, DEFAULT_PREFS)
    note = jobrules.compensation_note(got["salary_text"], got["salary_kind"], DEFAULT_PREFS["ctc_threshold_lakh"])
    for key, want in case["expect"].items():
        if key == "salary_kind_contains":
            assert want in (got["salary_kind"] or ""), got
        elif key == "compensation_note_contains":
            assert want in note, note
        elif key == "role_family":
            assert jobrules.role_family(case["title"]) == want
        else:
            assert got[key] == want, (key, got)


@pytest.mark.parametrize("case", CASES["articles"], ids=lambda c: c["id"])
def test_article_basis(case):
    raw = case["html_repeat"][0] * case["html_repeat"][1] if "html_repeat" in case else case["html"]
    assert content_basis(html_to_text(raw), raw) == case["expect"]["content_basis"]


@pytest.mark.parametrize("case", CASES["case_outputs"], ids=lambda c: c["id"])
def test_case_labels(case):
    art = {"content_text": case["text"], "source_kind": case["source_kind"], "content_basis": "full"}
    out, _ = analysis.validate_case(case["model_output_a"], case["model_output_b"], art)
    for key, want in case["expect"].items():
        node = out
        for part in key.split("."):
            node = node[part]
        assert node == want, (key, node)


def test_ctc_base_and_other_are_kept_apart():
    text, kind = jobrules.extract_salary("Base pay: ₹30 LPA. Total compensation includes a bonus and RSUs.")
    assert "base" in kind and "other components mentioned" in kind and "CTC" not in kind
    assert text == "Base pay: ₹30 LPA. Total compensation includes a bonus and RSUs."  # original wording kept
    assert "meets" in jobrules.compensation_note(text, kind, 22)


def test_missing_salary_is_not_a_reason_to_exclude():
    p = {"title": "Product Analyst", "location": "Bengaluru", "description_text": "No pay information.", "salary_extra": None}
    got = collect.classify(p, DEFAULT_PREFS)
    assert got["salary_text"] is None and got["bucket"] == "candidate"


def test_location_preference_changes_bucket():
    p = {"title": "Product Analyst", "location": "Remote - India", "description_text": "", "salary_extra": None}
    assert collect.classify(p, DEFAULT_PREFS)["bucket"] == "candidate"
    only_blr = {**DEFAULT_PREFS, "locations": ["bengaluru"]}
    assert collect.classify(p, only_blr)["bucket"] == "review"


def test_requirements_excerpt_keeps_requirements_when_clipped():
    desc = "Intro line.\n" + ("Company history paragraph. " * 200) + "\nRequirements:\n- SQL\n- Stakeholder management"
    excerpt, cov = analysis.requirements_excerpt(desc, 600)
    assert "Requirements:" in excerpt and not cov["complete"] and cov["chars_total"] == len(desc)


@pytest.mark.parametrize('location,workplace,description,expected', [
    ('', None, 'Must be based in Mumbai', 'india_other'),
    ('', None, 'Must be based in India', 'india_unspecified'),
    ('', None, 'Must be based in Bengaluru', 'bengaluru'),
    ('Remote', None, 'Candidates are not eligible to work in India', 'remote_unclear'),
    ('Remote - India', None, 'Must be based in the United States', 'remote_unclear'),
    ('Remote', None, 'Must be based in India\nMust be based in the US', 'remote_unclear'),
    ('Remote except India', None, '', 'remote_unclear'),
    ('India, Mumbai', None, '', 'india_other'),
    ('Remote - India', None, '', 'remote_india'),
    ('', 'remote', 'Must be based in India', 'remote_india'),
    ('Remote', None, 'Must be based in the US', 'remote_other'),
])
def test_location_requires_positive_unambiguous_evidence(location, workplace, description, expected):
    assert jobrules.classify_location(location, workplace, description).cls == expected


@pytest.mark.parametrize('salary', [
    'CTC ₹18–25 lakh per annum', 'CTC INR 18-25 LPA',
    'CTC ₹18 lakh to ₹25 lakh', 'CTC ₹1,800,000–₹2,500,000',
    'Base salary INR 200,000 per month', 'Base salary ₹2 lakh monthly',
    'CTC up to ₹25 lakh', 'CTC ₹25 lakh plus ₹5 lakh bonus',
])
def test_ambiguous_salary_is_not_promoted_to_confirmed_match(salary):
    kind = 'base' if salary.startswith('Base') else 'CTC'
    note = jobrules.compensation_note(salary, kind, 22)
    assert 'meets' not in note and 'below' not in note
    assert salary in note
    assert jobrules.inr_lakh(salary) is None


def test_clear_annual_ctc_still_compares():
    assert 'meets' in jobrules.compensation_note('CTC ₹25 lakh per annum', 'CTC', 22)
    assert 'below' in jobrules.compensation_note('CTC ₹18 lakh per annum', 'CTC', 22)


@pytest.mark.parametrize('location,description,expected', [
    ('Bangalore, India', '- Ability to maintain a productive collaboration between IST and US PST time zones', 'bengaluru'),
    ('Gurugram', "You'll report to a Director of Product Management based in Europe, working with partners across India, EMEA, and North America.", 'india_other'),
    ('Sydney, Australia', '- Operating cadences across APAC time zones (India to Japan, Korea and ANZ)', 'other'),
])
def test_onsite_location_field_not_overridden_by_team_description(location, description, expected):
    assert jobrules.classify_location(location, None, description).cls == expected
