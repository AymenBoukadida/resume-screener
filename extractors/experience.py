"""Experience-year extraction from job descriptions and résumés."""

from __future__ import annotations

import re
from datetime import date
from typing import List, Optional, Tuple

from extractors.normalize import normalize_text

_MONTHS = {
    "jan": 1, "january": 1, "janv": 1, "janvier": 1,
    "feb": 2, "february": 2, "fevr": 2, "fevrier": 2, "fev": 2,
    "mar": 3, "march": 3, "mars": 3,
    "apr": 4, "april": 4, "avr": 4, "avril": 4,
    "may": 5, "mai": 5,
    "jun": 6, "june": 6, "juin": 6,
    "jul": 7, "july": 7, "juil": 7, "juillet": 7,
    "aug": 8, "august": 8, "aout": 8, "aou": 8,
    "sep": 9, "sept": 9, "september": 9, "septembre": 9,
    "oct": 10, "october": 10, "octobre": 10,
    "nov": 11, "november": 11, "novembre": 11,
    "dec": 12, "december": 12, "decembre": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_YEAR = r"(?:19|20)\d{2}"
_PRESENT = r"(?:present|current|now|aujourd.?hui|actuel(?:le)?|date)"

_YEARS_RE = re.compile(
    r"(?<![\d.,])(\d{1,2}(?:[.,]\d)?)"
    r"(?:\s*(?:\+|to|-|–)(?:\s*(\d{1,2}(?:[.,]\d)?))?)?"
    r"\s*(?:years?|ans?|annee?s?)\b"
)
_WORD_YEARS_RE_TEMPLATE = r"\b({word})\s*(?:\+|to|-|–)?\s*(?:years?|ans?|annee?s?)\b"
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}

_FALSE_YEAR_RE = re.compile(
    r"(?<![\d.,])(\d{1,2}(?:[.,]\d)?)\s*(?:years?|ans?|annee?s?)"
    r"[\s-]*(?:old|agee?s?)\b"
    r"|(?:founded|etablie?|cree?e?|created)\s+"
    r"(?:(?:il\s+y\s+a|ago)\s+)?"
    r"(\d{1,2}(?:[.,]\d)?)\s*(?:years?|ans?|annee?s?)"
    r"|(?:il\s+y\s+a)\s+(\d{1,2}(?:[.,]\d)?)\s*(?:years?|ans?|annee?s?)"
)

_RANGE_RE = re.compile(
    rf"(?:({_MONTH_ALT})\.?\s+)?({_YEAR})\s*"
    rf"(?:[-–—]|to|a|au|until|jusqu.?a)\s*"
    rf"(?:({_MONTH_ALT})\.?\s+)?({_PRESENT}|{_YEAR})",
    re.IGNORECASE,
)
_SINCE_RE = re.compile(
    rf"\b(?:since|from|from\s+since|depuis)\s+(?:({_MONTH_ALT})\.?\s+)?({_YEAR})\b",
    re.IGNORECASE,
)


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def _month_num(token: Optional[str]) -> int:
    if not token:
        return 1
    return _MONTHS.get(normalize_text(token).replace(".", ""), 1)


def _end_month(token: Optional[str], present: bool) -> int:
    if present:
        return 12
    if not token:
        return 12
    return _MONTHS.get(normalize_text(token).replace(".", ""), 12)


def _false_positive_spans(text_norm: str) -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in _FALSE_YEAR_RE.finditer(text_norm)]


def _covered(index: int, spans: List[Tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in spans)


def _explicit_years(text_norm: str) -> List[float]:
    skipped = _false_positive_spans(text_norm)
    years: List[float] = []
    for match in _YEARS_RE.finditer(text_norm):
        if _covered(match.start(), skipped):
            continue
        for bound in match.groups():
            if bound:
                years.append(_to_float(bound))
    for word, value in _WORD_NUMBERS.items():
        word_re = re.compile(
            _WORD_YEARS_RE_TEMPLATE.format(word=word), re.IGNORECASE
        )
        for match in word_re.finditer(text_norm):
            if not _covered(match.start(), skipped):
                years.append(float(value))
    return years


def _ranges(text_norm: str, today: date) -> List[Tuple[float, float]]:
    intervals: List[Tuple[float, float]] = []
    for match in _RANGE_RE.finditer(text_norm):
        start_month, start_year, end_month, end_raw = match.groups()
        y0 = int(start_year)
        m0 = _month_num(start_month)
        present = bool(re.match(_PRESENT + r"$", end_raw, re.I))
        if present:
            y1, m1 = today.year, today.month
        else:
            y1 = int(end_raw)
            m1 = _end_month(end_month, False)
        start = y0 + (m0 - 1) / 12.0
        end = y1 + m1 / 12.0
        if end > start:
            intervals.append((start, end))
    for match in _SINCE_RE.finditer(text_norm):
        month, year = match.groups()
        start = int(year) + (_month_num(month) - 1) / 12.0
        end = today.year + today.month / 12.0
        if end > start:
            intervals.append((start, end))
    return intervals


def _merged_span(intervals: List[Tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    ordered = sorted(intervals)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged)


def extract_experience_years(
    text: str,
    mode: str = "max",
    today: Optional[date] = None,
) -> int:
    """Return whole years of experience mentioned in *text*."""
    if mode not in ("min", "max"):
        raise ValueError(f"mode must be 'min' or 'max', got {mode!r}")
    today = today or date.today()
    text_norm = normalize_text(text)
    mentions = _explicit_years(text_norm)
    span = _merged_span(_ranges(text_norm, today))
    if mode == "min":
        if not mentions:
            return 0
        return int(min(mentions))
    values = list(mentions)
    if span:
        values.append(span)
    if not values:
        return 0
    return int(max(values))
