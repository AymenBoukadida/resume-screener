"""Weighted scoring engine for candidate ranking."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

from parsers.jd_parser import JobRequirements


def round_half_up(value: float, digits: int = 1) -> float:
    """Round half away from zero, matching JavaScript's Math.round."""
    factor = 10 ** digits
    return math.floor(value * factor + 0.5) / factor


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "config.json"

COMPONENT_LABELS = {
    "required_skills": "Required Skills",
    "preferred_skills": "Preferred Skills",
    "experience": "Experience",
    "keywords": "Keywords",
}

WEIGHT_KEYS = ("required_skills", "preferred_skills", "experience", "keywords")


def validate_config(config: object) -> dict:
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    weights = config.get("weights", {})
    if not isinstance(weights, dict):
        raise ValueError("config.weights must be an object")
    missing = [key for key in WEIGHT_KEYS if key not in weights]
    if missing:
        raise ValueError(f"config.json is missing weight(s): {', '.join(missing)}")
    try:
        numeric = {key: float(weights[key]) for key in WEIGHT_KEYS}
    except (TypeError, ValueError) as exc:
        raise ValueError("weights must be numbers") from exc
    total_weight = sum(numeric.values())
    if abs(total_weight - 1.0) > 0.001:
        raise ValueError(
            f"weights in config.json must sum to 1.0 (currently {total_weight:.2f})"
        )
    years = int(config.get("default_expected_years", 0))
    if years < 0:
        raise ValueError("default_expected_years must be >= 0")
    return {"weights": numeric, "default_expected_years": years}


def active_weights(
    base: Dict[str, float],
    requirements: JobRequirements,
    *,
    include_experience: bool = True,
) -> Dict[str, float]:
    """Zero empty categories and re-normalize so active weights still sum to 1."""
    used = {
        "required_skills": bool(requirements.required_skills),
        "preferred_skills": bool(requirements.preferred_skills),
        "keywords": bool(requirements.keywords),
        "experience": include_experience,
    }
    scaled = {key: (base[key] if used[key] else 0.0) for key in WEIGHT_KEYS}
    total = sum(scaled.values())
    if total <= 0:
        return {key: 0.0 for key in WEIGHT_KEYS}
    return {key: scaled[key] / total for key in WEIGHT_KEYS}


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
    missing_preferred: Set[str] = field(default_factory=set)
    matched_keywords: Set[str] = field(default_factory=set)
    evidence: Dict[str, str] = field(default_factory=dict)
    applied_weights: Dict[str, float] = field(default_factory=dict)
    dropped_components: List[str] = field(default_factory=list)
    parse_status: str = "ok"
    parse_note: str = ""
    fields: Dict[str, object] = field(default_factory=dict)


class ScoringEngine:
    """Computes weighted scores for candidates and ranks them."""

    def __init__(
        self,
        config_path: Union[str, Path] = DEFAULT_CONFIG_PATH,
        config: Optional[dict] = None,
    ) -> None:
        if config is None:
            try:
                with open(config_path, "r", encoding="utf-8") as file:
                    config = json.load(file)
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"could not load config from {config_path}: {exc}") from exc
        validated = validate_config(config)
        self.weights = validated["weights"]
        self.default_expected_years = validated["default_expected_years"]

    @staticmethod
    def _coverage(matched: Set[str], target: Set[str]) -> float:
        if not target:
            return 0.0
        return len(matched & target) / len(target)

    def score_candidate(
        self,
        filename: str,
        resume_skills: Set[str],
        resume_years: int,
        requirements: JobRequirements,
        evidence: Optional[Dict[str, str]] = None,
        parse_status: str = "ok",
        parse_note: str = "",
        fields: Optional[Dict[str, object]] = None,
    ) -> CandidateScore:
        weights = active_weights(self.weights, requirements)
        dropped = [
            key for key in WEIGHT_KEYS
            if self.weights[key] > 0 and weights[key] == 0
        ]

        required_score = self._coverage(resume_skills, requirements.required_skills)
        preferred_score = self._coverage(resume_skills, requirements.preferred_skills)
        keyword_score = self._coverage(resume_skills, requirements.keywords)

        target_years = requirements.experience_years or self.default_expected_years
        if target_years:
            experience_score = min(resume_years / target_years, 1.0)
        else:
            experience_score = 1.0
            weights = active_weights(self.weights, requirements, include_experience=False)
            dropped = [
                key for key in WEIGHT_KEYS
                if self.weights[key] > 0 and weights[key] == 0
            ]

        total = 100 * (
            weights["required_skills"] * required_score
            + weights["preferred_skills"] * preferred_score
            + weights["experience"] * experience_score
            + weights["keywords"] * keyword_score
        )

        return CandidateScore(
            filename=filename,
            total=round_half_up(total, 1),
            required_score=required_score,
            preferred_score=preferred_score,
            experience_score=experience_score,
            keyword_score=keyword_score,
            experience_years=resume_years,
            matched_required=resume_skills & requirements.required_skills,
            missing_required=requirements.required_skills - resume_skills,
            matched_preferred=resume_skills & requirements.preferred_skills,
            missing_preferred=requirements.preferred_skills - resume_skills,
            matched_keywords=resume_skills & requirements.keywords,
            evidence=evidence or {},
            applied_weights=weights,
            dropped_components=dropped,
            parse_status=parse_status,
            parse_note=parse_note,
            fields=fields or {},
        )

    @staticmethod
    def rank(candidates: List[CandidateScore]) -> List[CandidateScore]:
        """Highest score first; filename breaks ties (deterministic)."""
        return sorted(
            candidates,
            key=lambda candidate: (-candidate.total, candidate.filename.lower()),
        )
