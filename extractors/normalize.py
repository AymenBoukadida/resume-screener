"""Accent-insensitive text normalisation shared by matching and mining."""

import re
import unicodedata


def normalize_text(text: str) -> str:
    """Lowercase, remove accents and fold possessives."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = stripped.replace("\u2019", "'")
    return re.sub(r"([a-z])'s\b", r"\1", stripped)
