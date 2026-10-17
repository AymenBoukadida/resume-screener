"""JD parser: extracts required skills, preferred skills, experience and
keywords from a job description.

A JavaScript mirror of this module lives in docs/app.js (parseJd,
splitSections) — keep the two in sync when changing parsing behaviour.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from extractors.keyword_extractor import KeywordExtractor, normalize_text

BULLET_CHARS = "-*•·▪‣–—"

# Section labels in priority order: the first pattern that matches a header
# line wins. Patterns match de-accented text (English + French forms).
SECTION_PATTERNS = [
    ("required", re.compile(
        r"\b(required|requirements?|must[\s-]?haves?|essential|qualifications?|"
        r"what\s+you\s+(?:will\s+)?bring|what\s+we(?:'re|\s+are)\s+looking\s+for|"
        r"your\s+profile|about\s+you|a\s+propos\s+de\s+vous|who\s+you\s+are|"
        r"ce\s+que\s+vous\s+apportez|profil\s+recherche|"
        r"requises?|requis|exigees?|exigences?|essentielles?|obligatoires?|"
        r"indispensables?|necessaires?)\b",
        re.IGNORECASE,
    )),
    ("preferred", re.compile(
        r"\b(preferred|nice[\s-]?to[\s-]?haves?|good[\s-]?to[\s-]?haves?|bonus|"
        r"desirable|pluses?|what\s+makes\s+you|"
        r"souhaitees?|souhaite|atouts?|appreciees?|apprecie|"
        r"seraient un plus)\b",
        re.IGNORECASE,
    )),
    ("experience", re.compile(
        r"\b(experience|responsibilit(?:y|ies)|what\s+you.{0,3}ll\s+do|"
        r"(?:a\s+)?day\s+in\s+the\s+life|day[\s-]?to[\s-]?day|your\s+mission|"
        r"duties|missions|taches|au\s+quotidien)\b",
        re.IGNORECASE,
    )),
]

# Lines starting with these (de-accented) words are sentences, not headers —
# "We value experience" must not hijack section parsing. Pronoun openers only,
# so real headers like "Relevant experience" or "Le profil requis" still pass.
_SENTENCE_OPENERS = {
    "we", "you", "your", "our", "i", "nous", "vous", "votre", "notre",
}


@dataclass
class JobRequirements:
    """Structured requirements extracted from a job description."""

    required_skills: Set[str] = field(default_factory=set)
    preferred_skills: Set[str] = field(default_factory=set)
    keywords: Set[str] = field(default_factory=set)
    experience_years: int = 0
    # True only when the JD itself declared Required/Preferred sections.
    # Set before the unstructured fallback fills required_skills, which must
    # not flip this flag (the web app's "treated as required" hint reads it).
    has_explicit_sections: bool = False


class JDParser:
    """Turns raw job-description text into a :class:`JobRequirements`."""

    def __init__(self, extractor: Optional[KeywordExtractor] = None) -> None:
        self.extractor = extractor or KeywordExtractor()

    def parse(self, jd_text: str) -> JobRequirements:
        sections = self._split_sections(jd_text)

        required = self.extractor.extract_skills("\n".join(sections["required"]))
        preferred = self.extractor.extract_skills("\n".join(sections["preferred"]))

        has_explicit_sections = bool(required or preferred)
        # Fallback for JDs without explicit sections.
        if not required and not preferred:
            required = self.extractor.extract_skills(jd_text)

        # Domain keywords: every skill mentioned in the JD that is not already
        # classified as required or preferred.
        all_mentioned = self.extractor.extract_skills(jd_text)
        keywords = all_mentioned - required - preferred

        return JobRequirements(
            required_skills=required,
            preferred_skills=preferred,
            keywords=keywords,
            # A "3-5 years" JD is met at 3 years, so the JD threshold is the
            # lowest figure mentioned (résumés keep the highest).
            experience_years=self.extractor.extract_experience_years(
                jd_text, mode="min"
            ),
            has_explicit_sections=has_explicit_sections,
        )

    def _split_sections(self, jd_text: str) -> dict:
        sections: dict = {"required": [], "preferred": [], "experience": []}
        current: Optional[str] = None

        for raw_line in jd_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            is_bullet = line[0] in BULLET_CHARS
            if is_bullet:
                line = line.lstrip(BULLET_CHARS).strip()
            line_norm = normalize_text(line)

            # Inline header: "Required skills: Python" /
            # "Compétences requises : Python".
            if not is_bullet and ":" in line_norm:
                left, _, right = line_norm.partition(":")
                label = self._match_section_label(left)
                if label:
                    current = label
                    if right.strip():
                        sections[label].append(right.strip())
                    continue

            # Standalone header line, e.g. "Preferred Skills:"
            if not is_bullet:
                header = self._match_header(line_norm)
                if header:
                    current = header
                    continue
                # A short "Label:" line that matches no known header still
                # ends the current section ("Why Work at Long View:") so its
                # content cannot leak into the previous bucket. Lines with
                # text after the colon ("Location: Calgary") stay content.
                if line_norm.endswith(":") and len(line_norm[:-1].split()) <= 5:
                    current = None
                    continue

            if current:
                sections[current].append(line)

        return sections

    @staticmethod
    def _match_section_label(text: str) -> Optional[str]:
        for label, pattern in SECTION_PATTERNS:
            if pattern.search(text):
                return label
        return None

    @staticmethod
    def _match_header(line: str) -> Optional[str]:
        """A header is a short line like 'Required Skills:' — sentences that
        merely contain the word 'experience' must not qualify.

        A line is accepted when it ends with ':' (the strong header signal,
        any length), or when it is short, free of sentence-ending punctuation
        and does not open with a pronoun like "we"/"vous"."""
        if line.endswith(":"):
            return JDParser._match_section_label(line)
        if len(line.split()) > 3 or line[-1] in ".!?;,":
            return None
        if line.split()[0] in _SENTENCE_OPENERS:
            return None
        return JDParser._match_section_label(line)
