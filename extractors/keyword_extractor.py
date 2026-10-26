"""Keyword extractor: matches text against a skills taxonomy."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from extractors.normalize import normalize_text

DEFAULT_TAXONOMY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "skills_taxonomy.json"
)

_NEGATION_RE = re.compile(
    r"\b(?:not|no|never|without|neither|"
    r"pas|sans|aucun(?:e|es)?|nul(?:le)?)\b"
)
_NEGATION_EXCEPTION_RE = re.compile(r"\bnot\s+only\b|\bpas\s+seulement\b")
_VERSION_SUFFIX = r"(?:[\s._-]*v?\d+(?:\.\d+){0,2})?"


def _is_negated(text_norm: str, start: int) -> bool:
    window = text_norm[max(0, start - 80):start]
    if _NEGATION_EXCEPTION_RE.search(window):
        return False
    tokens = window.split()[-6:]
    return bool(_NEGATION_RE.search(" ".join(tokens)))


def _snippet(text_norm: str, start: int, end: int, radius: int = 42) -> str:
    lo = max(0, start - radius)
    hi = min(len(text_norm), end + radius)
    chunk = text_norm[lo:hi].strip()
    if lo > 0:
        chunk = "…" + chunk
    if hi < len(text_norm):
        chunk = chunk + "…"
    return re.sub(r"\s+", " ", chunk)


def validate_taxonomy(taxonomy: object) -> Dict[str, Dict[str, List[str]]]:
    """Reject malformed taxonomy JSON before it silently scores nothing."""
    if not isinstance(taxonomy, dict) or not taxonomy:
        raise ValueError("taxonomy must be a non-empty object of categories")
    for category, skills in taxonomy.items():
        if not isinstance(category, str) or not isinstance(skills, dict) or not skills:
            raise ValueError(f"category {category!r} must map skill to variations")
        for skill, variations in skills.items():
            if not isinstance(skill, str) or not isinstance(variations, list) or not variations:
                raise ValueError(
                    f"skill {skill!r} in {category!r} must have a non-empty variations list"
                )
            if not all(isinstance(item, str) and item.strip() for item in variations):
                raise ValueError(f"variations for {skill!r} must be non-empty strings")
    return taxonomy  # type: ignore[return-value]


class KeywordExtractor:
    """Finds skills (and evidence snippets) in résumé or JD text."""

    def __init__(
        self,
        taxonomy: Optional[Dict[str, Dict[str, List[str]]]] = None,
        taxonomy_path: Union[str, Path] = DEFAULT_TAXONOMY_PATH,
    ) -> None:
        if taxonomy is None:
            try:
                with open(taxonomy_path, "r", encoding="utf-8") as file:
                    taxonomy = json.load(file)
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"could not load skills taxonomy from {taxonomy_path}: {exc}"
                ) from exc
        self.skills_taxonomy = validate_taxonomy(taxonomy)
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """One regex per variation; optional trailing version (Node 18)."""
        self._patterns: List[Tuple[str, re.Pattern[str]]] = []
        for _category, skills_dict in self.skills_taxonomy.items():
            for skill_name, variations in skills_dict.items():
                for variation in variations:
                    body = re.escape(normalize_text(variation))
                    pattern = re.compile(
                        r"(?<![a-z0-9])" + body + _VERSION_SUFFIX + r"(?![a-z0-9])"
                    )
                    self._patterns.append((skill_name, pattern))

    def extract_skills_detailed(self, text: str) -> Dict[str, str]:
        """Map each skill name to its first non-negated evidence snippet."""
        text_norm = normalize_text(text)
        found: Dict[str, str] = {}
        for skill_name, pattern in self._patterns:
            if skill_name in found:
                continue
            for match in pattern.finditer(text_norm):
                if _is_negated(text_norm, match.start()):
                    continue
                found[skill_name] = _snippet(text_norm, match.start(), match.end())
                break
        return found

    def extract_skills(self, text: str) -> Set[str]:
        """Return the set of taxonomy skill names present in *text*."""
        return set(self.extract_skills_detailed(text))

    def extract_experience_years(self, text: str, mode: str = "max") -> int:
        from extractors.experience import extract_experience_years as _years

        return _years(text, mode=mode)
