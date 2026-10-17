"""Tests for the weighted scoring engine."""

import json

import pytest

from matcher.scorer import CandidateScore, ScoringEngine, round_half_up
from parsers.jd_parser import JobRequirements


@pytest.fixture()
def engine():
    return ScoringEngine()  # repo config: 0.5 / 0.25 / 0.15 / 0.1


class TestConfigValidation:
    def test_weights_must_sum_to_one(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "weights": {
                "required_skills": 0.5, "preferred_skills": 0.25,
                "experience": 0.15, "keywords": 0.05,
            }
        }))
        with pytest.raises(ValueError, match="sum to 1.0"):
            ScoringEngine(config_path=config)

    def test_missing_weight_key_rejected(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"weights": {"required_skills": 1.0}}))
        with pytest.raises(ValueError, match="missing weight"):
            ScoringEngine(config_path=config)


class TestRounding:
    def test_half_rounds_up_like_the_web_app(self):
        # Python's built-in round() would give 87.2 here (banker's rounding).
        assert round_half_up(87.25, 1) == 87.3
        assert round(87.25, 1) != 87.3  # documents why the helper exists

    def test_non_half_values_unchanged(self):
        assert round_half_up(57.483, 1) == 57.5


class TestScoring:
    def test_known_values(self, engine):
        requirements = JobRequirements(
            required_skills={"python", "docker"},
            preferred_skills=set(),
            keywords={"sql"},
            experience_years=4,
        )
        candidate = engine.score_candidate(
            "cv.txt", {"python"}, 2, requirements
        )
        # required 1/2 = 0.5; preferred target empty = 1.0; keywords 0/1 = 0;
        # experience 2/4 = 0.5 → 100 * (0.5*0.5 + 0.25*1.0 + 0.15*0.5) = 57.5
        assert candidate.total == 57.5
        assert candidate.matched_required == {"python"}
        assert candidate.missing_required == {"docker"}

    def test_experience_capped_at_one(self, engine):
        requirements = JobRequirements(experience_years=3)
        candidate = engine.score_candidate("cv.txt", set(), 9, requirements)
        assert candidate.experience_score == 1.0

    def test_coverage_of_empty_target_is_one(self):
        assert ScoringEngine._coverage(set(), set()) == 1.0

    def test_rank_orders_by_total_descending(self):
        candidates = [
            CandidateScore("low.txt", 12.0, 0, 0, 0, 0, 0),
            CandidateScore("high.txt", 91.0, 0, 0, 0, 0, 0),
            CandidateScore("mid.txt", 57.5, 0, 0, 0, 0, 0),
        ]
        ranked = ScoringEngine.rank(candidates)
        assert [c.filename for c in ranked] == ["high.txt", "mid.txt", "low.txt"]
