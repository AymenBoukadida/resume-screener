"""Tests for CV-improvement tip generation."""

from matcher.feedback import generate_feedback
from matcher.scorer import CandidateScore
from parsers.jd_parser import JobRequirements


def make_candidate(**overrides):
    defaults = dict(
        filename="cv.txt",
        total=10.0,
        required_score=0.0,
        preferred_score=0.0,
        experience_score=0.0,
        keyword_score=0.0,
        experience_years=0,
        matched_required=set(),
        missing_required=set(),
        matched_preferred=set(),
        matched_keywords=set(),
    )
    defaults.update(overrides)
    return CandidateScore(**defaults)


def test_missing_required_skill_produces_named_tip():
    candidate = make_candidate(missing_required={"python"})
    requirements = JobRequirements(required_skills={"python"})
    tips = generate_feedback(candidate, requirements)
    assert any('"python"' in tip for tip in tips)


def test_strong_match_yields_single_positive_tip():
    candidate = make_candidate(
        matched_required={"python"},
        matched_preferred={"react"},
        experience_years=5,
        total=100.0,
    )
    requirements = JobRequirements(
        required_skills={"python"},
        preferred_skills={"react"},
        experience_years=5,
    )
    tips = generate_feedback(candidate, requirements)
    assert tips == ["Strong match — no changes needed for this job description."]


def test_nothing_detected_flags_scanned_image():
    candidate = make_candidate()
    requirements = JobRequirements(required_skills={"python"})
    tips = generate_feedback(candidate, requirements)
    assert any("scanned image" in tip for tip in tips)
    assert any("years of experience" in tip for tip in tips)
