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
