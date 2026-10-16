"""Keyword extractor: matches text against a predefined skills taxonomy.

Matching is accent-insensitive and case-insensitive, so English and French
text ("développement web", "DEVELOPPEMENT WEB") all match the same
accent-free variations stored in the taxonomy.
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

DEFAULT_TAXONOMY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "skills_taxonomy.json"
)

# "3+ years", "5 ans", "3 années", "3-5 years" (first number wins).
# Covers English and French forms; text is de-accented before matching.
_YEARS_RE = re.compile(r"(\d{1,2})\s*(?:\+|to|-|–)?\s*(?:years?|ans?|annee?s?)\b")
_WORD_YEARS_RE_TEMPLATE = r"\b({word})\s*(?:\+|to|-|–)?\s*(?:years?|ans?|annee?s?)\b"
_WORD_NUMBERS = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    # French
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}


def normalize_text(text: str) -> str:
    """Lowercase, remove accents (é → e) and normalise apostrophes.

    Taxonomy variations and section headers are stored accent-free, so both
    "développement" and "DEVELOPPEMENT" match "developpement".
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.replace("\u2019", "'")


class KeywordExtractor:
    """Finds skills (and experience indicators) in résumé or JD text.

    Matching is case-insensitive and uses word boundaries so that, for
    example, "Java" does not match inside "JavaScript".
    """

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
        self.skills_taxonomy = taxonomy
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile one regex per variation, flattened across categories."""
        self._patterns: List = []
        for _category, skills_dict in self.skills_taxonomy.items():
            for skill_name, variations in skills_dict.items():
                for variation in variations:
                    # Lookarounds instead of \b so that variations ending in
                    # non-word characters ("c++", "c#", "node.js") still match.
                    pattern = re.compile(
                        r"(?<![a-z0-9])"
                        + re.escape(normalize_text(variation))
                        + r"(?![a-z0-9])"
                    )
                    self._patterns.append((skill_name, pattern))

    def extract_skills(self, text: str) -> Set[str]:
        """Return the set of taxonomy skill names present in *text*."""
        text_norm = normalize_text(text)
        found_skills = set()

        for skill_name, pattern in self._patterns:
            if pattern.search(text_norm):
                found_skills.add(skill_name)

        return found_skills

    def extract_experience_years(self, text: str) -> int:
        """Return the highest number of years of experience mentioned."""
        text_norm = normalize_text(text)
        years = [int(value) for value in _YEARS_RE.findall(text_norm)]
        for word, value in _WORD_NUMBERS.items():
            word_re = re.compile(
                _WORD_YEARS_RE_TEMPLATE.format(word=word), re.IGNORECASE
            )
            if word_re.search(text_norm):
                years.append(value)
        return max(years, default=0)
