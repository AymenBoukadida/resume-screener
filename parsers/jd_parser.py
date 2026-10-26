"""Job-description parser for required skills, preferred skills and experience."""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

from extractors.keyword_extractor import KeywordExtractor
from extractors.normalize import normalize_text
from extractors.term_miner import mine_terms

BULLET_CHARS = "-*•·▪‣–—"
_BULLET_PREFIX_RE = re.compile(
    rf"^(?:[{re.escape(BULLET_CHARS)}]+|\d+[.)]\s+|[a-z][.)]\s+)",
    re.IGNORECASE,
)
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+")
_MD_WRAP_RE = re.compile(r"^[*_`]+|[*_`]+$")

SECTION_PATTERNS = [
    ("preferred", re.compile(
        r"(?:"
        r"preferred(?:\s+(?:skills?|qualifications?|experience|requirements?))?|"
        r"(?:nice|good)[\s-]?to[\s-]?haves?(?:\s+skills?)?|"
        r"bonus(?:\s+(?:skills?|points?))?(?:\s+if\s+you\s+have)?|"
        r"desirable|desired(?:\s+skills?)?|pluses?|a\s+plus|assets?|"
        r"advantages?|"
        r"what\s+makes\s+you(?:\s+[a-z]+){0,4}|"
        r"optional(?:\s+(?:skills?|qualifications?))?|"
        r"(?:stand\s+out|extra\s+credit|even\s+better\s+if|"
        r"you\s+might\s+also\s+have)|"
        r"additional\s+(?:skills?|qualifications?)|"
        r"souhaite(?:e|es|s)?|atouts?|apprecie(?:e|es|s)?|"
        r"serait\s+un\s+plus|un\s+plus|les\s+plus|optionnel(?:le)?s?|"
        r"competences?\s+(?:souhaitees?|recherchees?|desirables?)|"
        r"qualifications?\s+souhaitees?"
        r")",
        re.IGNORECASE,
    )),
    ("required", re.compile(
        r"(?:"
        r"required(?:\s+(?:skills?|qualifications?|experience|education|"
        r"certifications?))?|"
        r"requirements?|technical\s+requirements?|key\s+requirements?|"
        r"must[\s-]?haves?(?:\s+skills?)?|essential|"
        r"(?:minimum|basic|preferred|additional|desired)\s+"
        r"(?:qualifications?|requirements?)|"
        r"qualifications?|qualifications?\s+(?:and|&)\s+experience|"
        r"requirements?\s+(?:and|&)\s+qualifications?|"
        r"what\s+you(?:\s+will)?\s+(?:bring|need|have|offer)|"
        r"what\s+you(?:'ll|\s+will)\s+(?:bring|need|have|offer)|"
        r"what\s+we(?:'re|\s+are)\s+looking\s+for|what\s+we\s+need|"
        r"your\s+(?:profile|background)|about\s+you|who\s+you\s+are|"
        r"you\s+(?:have|bring|offer)|profile|background|"
        r"the\s+ideal\s+candidate|ideal\s+candidate|candidate\s+profile|"
        r"skills?(?:\s+(?:and|&)\s+experience)?|"
        r"experience\s+(?:and|&)\s+skills?|"
        r"technical\s+skills?|key\s+skills?|core\s+skills?|competencies|"
        r"proficiencies|expertise|"
        r"education(?:\s+(?:and|&)\s+(?:certifications?|training))?|"
        r"educational\s+background|academic\s+background|"
        r"certifications?(?:\s+(?:and|&)\s+licen[cs]es?)?|"
        r"certificates?|licen[cs]es?|credentials?|"
        r"languages?|language\s+skills?|"
        r"ce\s+que\s+vous\s+(?:apportez|offrez)|"
        r"profil(?:\s+recherche)?|votre\s+profil|"
        r"a\s+propos\s+de\s+vous|"
        r"requises?|requis|exigees?|exigences?|essentielles?|obligatoires?|"
        r"indispensables?|necessaires?|prerequis|"
        r"competences(?:\s+(?:requises?|et\s+experience))?|"
        r"formation(?:\s+requise)?|diplomes?(?:\s+requis)?|"
        r"certifications?\s+requises?|langues?|"
        r"competences?\s+linguistiques?"
        r")",
        re.IGNORECASE,
    )),
    ("experience", re.compile(
        r"(?:"
        r"experience|experiences|responsibilit(?:y|ies)|"
        r"what\s+you.{0,3}ll\s+do|what\s+you\s+will\s+do|"
        r"(?:a\s+)?day\s+in\s+the\s+life|day[\s-]?to[\s-]?day|"
        r"your\s+mission|your\s+missions|duties|missions|taches|au\s+quotidien|"
        r"ce\s+que\s+vous\s+(?:ferez|allez\s+faire)|vos\s+missions"
        r")",
        re.IGNORECASE,
    )),
]

_REQUIRED_CUE_RE = re.compile(
    r"\b(?:must[\s-]?have|required|requirements?|essential|"
    r"proficien(?:t|cy)\s+(?:in|with)|"
    r"experience\s+(?:working\s+)?(?:with|in)|"
    r"knowledge\s+of|familiarity\s+with|ability\s+to|skilled\s+in|"
    r"expertise\s+in|hands[\s-]?on\s+experience|working\s+knowledge|"
    r"certification\s+in|degree\s+in|bilingual|fluent\s+in|"
    r"qualified\s+in|strong\s+background\s+in|"
    r"solid\s+understanding\s+of|demonstrated\s+experience|"
    r"proven\s+experience|track\s+record\s+(?:in|of)|"
    r"\b\d{1,2}(?:[.,]\d)?\s*(?:\+|to|-|–)?\s*"
    r"(?:years?|ans?|annees?)\b|"
    r"maitrise\s+de|connaissance\s+de|experience\s+(?:avec|en)|"
    r"capacite\s+a|diplome\s+en|bilingue|courant\s+en)\b",
    re.IGNORECASE,
)
_PREFERRED_CUE_RE = re.compile(
    r"\b(?:preferred|nice[\s-]?to[\s-]?have|good[\s-]?to[\s-]?have|"
    r"bonus|desirable|a\s+plus|asset|advantage|ideally|"
    r"souhaite(?:e|es|s)?|atout|apprecie(?:e|es|s)?|un\s+plus|"
    r"serait\s+un\s+plus|optionnel(?:le)?s?)\b",
    re.IGNORECASE,
)

_HEADER_TRIM_RE = re.compile(r"[\s:：]+$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _iter_line_parts(line: str) -> List[str]:
    """Split a line into sentence-sized parts."""
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(line) if part.strip()]
    if len(parts) <= 1 or any(len(part) < 12 for part in parts):
        return [line]
    return parts

MIN_SIGNAL_SKILLS = 2


@dataclass
class JobRequirements:
    """Structured requirements extracted from a job description."""

    required_skills: Set[str] = field(default_factory=set)
    preferred_skills: Set[str] = field(default_factory=set)
    keywords: Set[str] = field(default_factory=set)
    experience_years: int = 0
    mined_terms: Set[str] = field(default_factory=set)
    has_explicit_sections: bool = False
    warnings: List[str] = field(default_factory=list)


class JDParser:
    """Turns raw job-description text into a :class:`JobRequirements`."""

    def __init__(self, extractor: Optional[KeywordExtractor] = None) -> None:
        self.extractor = extractor or KeywordExtractor()

    def parse(self, jd_text: str) -> JobRequirements:
        sections, records = self._split_sections(jd_text)

        required = self.extractor.extract_skills("\n".join(sections["required"]))
        preferred = self.extractor.extract_skills("\n".join(sections["preferred"]))
        preferred -= required

        has_explicit_sections = bool(sections["required"] or sections["preferred"])
        if not required and not preferred:
            required = self.extractor.extract_skills(jd_text)

        all_mentioned = self.extractor.extract_skills(jd_text)
        keywords = all_mentioned - required - preferred

        mined_terms: Set[str] = set()
        fallback = not has_explicit_sections
        buckets = {
            "required": required,
            "preferred": preferred,
            "keywords": keywords,
        }
        existing = set().union(*buckets.values())
        for bucket_name, terms in mine_terms(records, self.extractor, existing).items():
            target = buckets[
                "required" if fallback and bucket_name == "keywords" else bucket_name
            ]
            for term, canonical in terms:
                name = canonical or " ".join(term)
                if canonical and canonical in existing:
                    continue
                if name in existing:
                    continue
                target.add(name)
                existing.add(name)
                if not canonical:
                    mined_terms.add(name)

        warnings = _requirement_warnings(
            required, preferred, keywords, has_explicit_sections, mined_terms
        )
        return JobRequirements(
            required_skills=required,
            preferred_skills=preferred,
            keywords=keywords,
            mined_terms=mined_terms,
            experience_years=self.extractor.extract_experience_years(
                jd_text, mode="min"
            ),
            has_explicit_sections=has_explicit_sections,
            warnings=warnings,
        )

    def _split_sections(
        self, jd_text: str
    ) -> tuple:
        sections: dict = {
            "required": [], "preferred": [], "experience": [], "context": [],
        }
        records: List[Tuple[Optional[str], str, bool, int]] = []
        current: Optional[str] = None
        ordinal = 0

        for raw_line in jd_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            line = _MD_HEADING_RE.sub("", line).strip()
            line = _MD_WRAP_RE.sub("", line).strip()
            if not line:
                continue

            is_bullet = bool(_BULLET_PREFIX_RE.match(line)) or line[0] in BULLET_CHARS
            if is_bullet:
                line = _BULLET_PREFIX_RE.sub("", line).lstrip(BULLET_CHARS).strip()
            if not line:
                continue

            for part in _iter_line_parts(line):
                part = part.strip()
                if not part:
                    continue
                line_norm = normalize_text(part)

                if not is_bullet and ":" in line_norm:
                    left, _, right = line_norm.partition(":")
                    label = self._match_section_label(left)
                    if label:
                        current = label
                        if right.strip():
                            sections[label].append(right.strip())
                            records.append((label, right.strip(), False, ordinal))
                            ordinal += 1
                        continue

                if not is_bullet:
                    header = self._match_header(line_norm)
                    if header:
                        current = header
                        continue
                    if line_norm.endswith(":") and len(line_norm[:-1].split()) <= 5:
                        current = None
                        continue

                bucket = current
                if bucket is None or bucket == "experience":
                    cue = _cue_bucket(line_norm)
                    if cue:
                        bucket = cue
                elif bucket == "required":
                    cue = _cue_bucket(line_norm)
                    if cue == "preferred":
                        bucket = "preferred"
                if bucket:
                    sections[bucket].append(part)
                else:
                    sections["context"].append(part)
                records.append((bucket, part, is_bullet, ordinal))
                ordinal += 1

        return sections, records

    @staticmethod
    def _match_section_label(text: str) -> Optional[str]:
        for label, pattern in SECTION_PATTERNS:
            if pattern.search(text):
                return label
        return None

    @staticmethod
    def _match_header(line: str) -> Optional[str]:
        """Return the section for a whole-line header, else None."""
        candidate = _HEADER_TRIM_RE.sub("", line.strip())
        if not candidate:
            return None
        if len(candidate.split()) > 8:
            return None
        if re.search(r"\d", candidate):
            return None
        if candidate[-1] in ".!?;,":
            return None
        for label, pattern in SECTION_PATTERNS:
            if pattern.fullmatch(candidate):
                return label
        return None


def _cue_bucket(line_norm: str) -> Optional[str]:
    """Classify a line by requirement language ("must have", "an asset")."""
    if _PREFERRED_CUE_RE.search(line_norm):
        return "preferred"
    if _REQUIRED_CUE_RE.search(line_norm):
        return "required"
    return None


def _requirement_warnings(
    required: Set[str],
    preferred: Set[str],
    keywords: Set[str],
    has_explicit_sections: bool,
    mined_terms: Set[str],
) -> List[str]:
    warnings: List[str] = []
    signal = required | preferred
    if not signal and not keywords:
        warnings.append(
            "No skills could be extracted from this job description. "
            "Add a Required / Preferred section or import a custom taxonomy."
        )
    elif len(signal) < MIN_SIGNAL_SKILLS:
        warnings.append(
            f"Only {len(signal)} required/preferred skill(s) were extracted. "
            "Review and edit them before ranking — scores will be brittle."
        )
    if not has_explicit_sections:
        warnings.append(
            "No Required/Preferred heading was detected. Every extracted "
            "skill was treated as required; reclassify preferred skills if needed."
        )
    if mined_terms and len(mined_terms) >= len(signal):
        warnings.append(
            "Most requirements came from phrases in the ad (not the skills "
            "taxonomy). Check they are real requirements, not duties or culture copy."
        )
    return warnings
