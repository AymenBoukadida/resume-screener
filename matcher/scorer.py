"""Scoring engine: ranks candidates with a weighted formula.

Total Score = (Required Skills × 50%)
            + (Preferred Skills × 25%)
            + (Experience × 15%)
            + (Keywords × 10%)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set, Union

from parsers.jd_parser import JobRequirements

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "config.json"

COMPONENT_LABELS = {
    "required_skills": "Required Skills",
    "preferred_skills": "Preferred Skills",
    "experience": "Experience",
    "keywords": "Keywords",
}


@dataclass
class CandidateScore:
    """Score and breakdown for one résumé."""

    filename: str
    total: float
    required_score: float
    preferred_score: float
    experience_score: float
    keyword_score: float
    experience_years: int
    matched_required: Set[str] = field(default_factory=set)
    missing_required: Set[str] = field(default_factory=set)
    matched_preferred: Set[str] = field(default_factory=set)
    matched_keywords: Set[str] = field(default_factory=set)


class ScoringEngine:
    """Computes weighted scores for candidates and ranks them."""

    REQUIRED_WEIGHT_KEYS = ("required_skills", "preferred_skills", "experience", "keywords")

    def __init__(self, config_path: Union[str, Path] = DEFAULT_CONFIG_PATH) -> None:
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                config = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not load config from {config_path}: {exc}") from exc
        self.weights = config.get("weights", {})

        missing = [key for key in self.REQUIRED_WEIGHT_KEYS if key not in self.weights]
        if missing:
            raise ValueError(
                f"config.json is missing weight(s): {', '.join(missing)}"
            )
        total_weight = sum(self.weights[key] for key in self.REQUIRED_WEIGHT_KEYS)
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(
                f"weights in config.json must sum to 1.0 "
                f"(currently {total_weight:.2f})"
            )

        self.default_expected_years = int(config.get("default_expected_years", 3))

    @staticmethod
    def _coverage(matched: Set[str], target: Set[str]) -> float:
        """Fraction of *target* skills that were matched (1.0 if no target)."""
        if not target:
            return 1.0
        return len(matched & target) / len(target)

    def score_candidate(
        self,
        filename: str,
        resume_skills: Set[str],
        resume_years: int,
        requirements: JobRequirements,
    ) -> CandidateScore:
        required_score = self._coverage(resume_skills, requirements.required_skills)
        preferred_score = self._coverage(resume_skills, requirements.preferred_skills)
        keyword_score = self._coverage(resume_skills, requirements.keywords)

        target_years = (
            requirements.experience_years or self.default_expected_years
        )
        experience_score = min(resume_years / target_years, 1.0) if target_years else 1.0

        total = 100 * (
            self.weights["required_skills"] * required_score
            + self.weights["preferred_skills"] * preferred_score
            + self.weights["experience"] * experience_score
            + self.weights["keywords"] * keyword_score
        )

        return CandidateScore(
            filename=filename,
            total=round(total, 1),
            required_score=required_score,
            preferred_score=preferred_score,
            experience_score=experience_score,
            keyword_score=keyword_score,
            experience_years=resume_years,
            matched_required=resume_skills & requirements.required_skills,
            missing_required=requirements.required_skills - resume_skills,
            matched_preferred=resume_skills & requirements.preferred_skills,
            matched_keywords=resume_skills & requirements.keywords,
        )

    @staticmethod
    def rank(candidates: List[CandidateScore]) -> List[CandidateScore]:
        """Sort candidates by total score, highest first."""
        return sorted(candidates, key=lambda candidate: candidate.total, reverse=True)
