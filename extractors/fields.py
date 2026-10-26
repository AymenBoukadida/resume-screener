"""Structured field extraction from résumé text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Set, Tuple

from extractors.normalize import normalize_text

_EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])"
)
_PHONE_RE = re.compile(
    r"(?<![\w])(?:\+\d{1,3}[\s.\-]?)?"
    r"(?:\(\d{1,4}\)[\s.\-]?|\d{1,4}[\s.\-]){1,5}\d{2,4}(?![\w])"
)
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s|,;<>\"']+", re.IGNORECASE)
_BARE_URL_RE = re.compile(
    r"\b(?:[\w-]+\.)+(?:com|org|net|io|dev|me|co|fr|ca|uk|de|tn|ly)\b"
    r"(?:/\S*)?",
    re.IGNORECASE,
)
_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in|pub)/[^\s|,;<>\"']+",
    re.IGNORECASE,
)
_GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[^\s|,;<>\"']+", re.IGNORECASE
)

_BULLET_PREFIX_RE = re.compile(
    r"^(?:[-*•·▪‣–—]+|\d+[.)]\s+|[a-z][.)]\s+)\s*", re.IGNORECASE
)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

_NAME_LABEL_RE = re.compile(
    r"^(?:full\s+name|name|nom(?:\s+complet)?|pr[ée]nom\s+et\s+nom)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_HEADLINE_LABEL_RE = re.compile(
    r"^(?:headline|title|job\s+title|current\s+(?:title|role)|poste|titre|"
    r"fonction|intitul[ée]\s+du\s+poste)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_LOCATION_LABEL_RE = re.compile(
    r"^(?:location|based\s+in|address|city|lieu|ville|adresse)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_EDUCATION_LABEL_RE = re.compile(
    r"^(?:education|educational\s+background|academic\s+background|"
    r"academic\s+qualifications?|formation|etudes|parcours\s+academique)"
    r"\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_CERTIFICATION_LABEL_RE = re.compile(
    r"^(?:certifications?|certificates?|licen[cs]es?|credentials?|"
    r"accreditations?|certificats?|habilitations?)"
    r"\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_LANGUAGE_LABEL_RE = re.compile(
    r"^(?:languages?|language\s+skills?|langues?|"
    r"competences?\s+linguistiques?)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_CITY_COUNTRY_RE = re.compile(
    r"^([A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ .'’\-]{1,40}),\s*"
    r"([A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ .'’\-]{1,40})$"
)

_SECTION_HEADERS = {
    "summary", "professional summary", "profile", "objective", "about",
    "about me", "contact", "contact details", "skills", "technical skills",
    "core skills", "key skills", "experience", "work experience",
    "professional experience", "employment", "employment history",
    "education", "educational background", "academic background",
    "certifications", "certificates", "licenses", "licences",
    "languages", "projects", "awards", "publications", "volunteer",
    "interests", "references", "resume", "cv", "curriculum vitae",
    "profil", "objectif", "contact", "competences",
    "competences techniques", "experience", "experiences",
    "experiences professionnelles", "formation", "etudes", "langues",
    "certifications", "certificats", "projets", "distinctions",
}

_ROLE_WORDS = {
    "engineer", "developer", "programmer", "architect", "analyst",
    "manager", "director", "consultant", "specialist", "technician",
    "administrator", "coordinator", "assistant", "officer", "intern",
    "student", "teacher", "professor", "nurse", "doctor", "pharmacist",
    "accountant", "lawyer", "paralegal", "welder", "electrician",
    "plumber", "carpenter", "mechanic", "driver", "clerk", "receptionist",
    "secretary", "supervisor", "lead", "head", "chief", "president",
    "owner", "partner", "apprentice", "trainee", "graduate", "scientist",
    "researcher", "designer", "writer", "editor", "marketer", "recruiter",
    "therapist", "dentist", "surgeon", "veterinarian", "chef", "barista",
    "cashier", "salesperson", "representative", "agent", "broker",
    "developpeur", "developpeuse", "ingenieur", "ingenieure", "analyste",
    "gestionnaire", "directeur", "directrice", "consultant", "consultante",
    "specialiste", "technicien", "technicienne", "administrateur",
    "administratrice", "coordonnateur", "coordonnatrice", "assistant",
    "assistante", "infirmier", "infirmiere", "medecin", "comptable",
    "avocat", "avocate", "soudeur", "soudeuse", "electricien",
    "electricienne", "plombier", "mecanicien", "chauffeur", "secretaire",
    "superviseur", "stagiaire", "etudiant", "etudiante", "professeur",
    "chercheur", "chercheuse", "concepteur", "conceptrice", "redacteur",
    "redactrice", "recruteur", "recruteuse", "therapeute", "dentiste",
    "chirurgien", "chef", "caissier", "caissiere", "vendeur", "vendeuse",
}

_PARTICLES = {
    "de", "da", "van", "von", "der", "la", "le", "del", "di", "bin", "al",
    "el", "dos", "das", "du", "des", "ter", "ten",
}

_INSTITUTION_WORDS = {
    "hospital", "university", "college", "school", "institute", "academy",
    "company", "corp", "corporation", "inc", "ltd", "llc", "gmbh", "sas",
    "sarl", "plc", "group", "agency", "clinic", "centre", "center",
    "hopital", "universite", "ecole", "institut", "entreprise", "societe",
}

_EDUCATION_HEADER_RE = re.compile(
    r"^(?:education|educational\s+background|academic\s+background|"
    r"academic\s+qualifications|qualifications?\s+academiques?|"
    r"formation|etudes|parcours\s+academique)\s*:?$",
    re.IGNORECASE,
)
_CERTIFICATION_HEADER_RE = re.compile(
    r"^(?:certifications?|certificates?|licen[cs]es?|credentials?|"
    r"accreditations?|certificats?|habilitations?|licences?\s+"
    r"professionnelles?)\s*:?$",
    re.IGNORECASE,
)
_LANGUAGE_HEADER_RE = re.compile(
    r"^(?:languages?|language\s+skills?|langues?|"
    r"competences?\s+linguistiques?)\s*:?$",
    re.IGNORECASE,
)
_OTHER_SECTION_RE = re.compile(
    r"^(?:summary|profile|objective|about|skills|technical\s+skills|"
    r"core\s+skills|key\s+skills|experience|work\s+experience|"
    r"professional\s+experience|employment|projects?|awards?|"
    r"publications?|volunteer|interests?|references?|resume|cv|"
    r"profil|objectif|competences|experiences?|projets?|distinctions?)\s*:?$",
    re.IGNORECASE,
)

_DEGREE_RE = re.compile(
    r"\b(?:bachelor(?:'s)?|bachelors|master(?:'s)?|masters|ph\.?d|"
    r"doctorate|doctoral|associate(?:'s)?|diploma|licence|"
    r"baccalaureat|b\.?\s?sc|m\.?\s?sc|b\.?\s?a\.?|m\.?\s?a\.?|"
    r"mba|b\.?\s?tech|m\.?\s?tech|llb|llm|md|dds|pharmd|dut|bts|"
    r"dep|aep|asp|cegep|"
    r"ingenieur|engineer(?:'s)?\s+degree)\b",
    re.IGNORECASE,
)
_HIGH_SCHOOL_RE = re.compile(
    r"\b(?:high\s+school|secondary\s+school|baccalaureat|bac)\b",
    re.IGNORECASE,
)
_ASSOCIATE_RE = re.compile(
    r"\b(?:associate(?:'s)?|dut|bts|dep|aep|asp|diploma)\b", re.IGNORECASE
)
_BACHELOR_RE = re.compile(
    r"\b(?:bachelor(?:'s)?|bachelors|b\.?\s?sc|b\.?\s?a\.?|b\.?\s?tech|"
    r"llb|licence|bac\+3)\b",
    re.IGNORECASE,
)
_MASTER_RE = re.compile(
    r"\b(?:master(?:'s)?|masters|mba|m\.?\s?sc|m\.?\s?a\.?|m\.?\s?tech|"
    r"llm|master\s+2|bac\+5)\b",
    re.IGNORECASE,
)
_PHD_RE = re.compile(
    r"\b(?:ph\.?d|doctorate|doctoral|doctorat)\b", re.IGNORECASE
)

_CERT_WORD_RE = re.compile(
    r"\b(?:certified|certification|certificate|licensed|licence|license|"
    r"registration|registered)\b",
    re.IGNORECASE,
)
_CERT_ACRONYM_RE = re.compile(
    r"\b(?:bls|acls|pals|cpr|first\s+aid|cpa|cfa|cma|pmp|prince2|capm|"
    r"cissp|ccna|ccnp|security\+|comptia|itil(?:v\d)?|oscp|ceh|"
    r"osha|six\s+sigma|lean\s+six\s+sigma|cdl|servsafe|food\s+safety|"
    r"shrm|phr|rn|lpn|cna|md|dds|pharmd|aws\s+certified|"
    r"azure\s+certified|google\s+cloud\s+certified)\b",
    re.IGNORECASE,
)

_LANGUAGES = {
    "english": "English", "anglais": "English",
    "french": "French", "francais": "French",
    "spanish": "Spanish", "espagnol": "Spanish",
    "german": "German", "allemand": "German",
    "arabic": "Arabic", "arabe": "Arabic",
    "mandarin": "Mandarin", "cantonese": "Cantonese", "cantonais": "Cantonese",
    "portuguese": "Portuguese", "portugais": "Portuguese",
    "italian": "Italian", "italien": "Italian",
    "russian": "Russian", "russe": "Russian",
    "japanese": "Japanese", "japonais": "Japanese",
    "korean": "Korean", "coreen": "Korean",
    "hindi": "Hindi", "urdu": "Urdu", "ourdou": "Urdu",
    "turkish": "Turkish", "turc": "Turkish",
    "dutch": "Dutch", "neerlandais": "Dutch",
    "polish": "Polish", "polonais": "Polish",
    "vietnamese": "Vietnamese", "vietnamien": "Vietnamese",
    "tagalog": "Tagalog", "farsi": "Farsi", "persian": "Persian",
    "persan": "Persian", "hebrew": "Hebrew", "hebreu": "Hebrew",
    "greek": "Greek", "grec": "Greek",
    "swedish": "Swedish", "suedois": "Swedish",
    "norwegian": "Norwegian", "norvegien": "Norwegian",
    "danish": "Danish", "danois": "Danish",
    "finnish": "Finnish", "finnois": "Finnish",
    "czech": "Czech", "tcheque": "Czech",
    "romanian": "Romanian", "roumain": "Romanian",
    "hungarian": "Hungarian", "hongrois": "Hungarian",
    "ukrainian": "Ukrainian", "ukrainien": "Ukrainian",
    "bengali": "Bengali", "tamil": "Tamil", "tamoul": "Tamil",
    "malay": "Malay", "malais": "Malay",
    "indonesian": "Indonesian", "indonesien": "Indonesian",
    "thai": "Thai", "swahili": "Swahili", "amharic": "Amharic",
    "somali": "Somali", "yoruba": "Yoruba", "igbo": "Igbo",
    "hausa": "Hausa", "zulu": "Zulu", "afrikaans": "Afrikaans",
}
_LANGUAGE_CONTEXT_RE = re.compile(
    r"\b(?:languages?|langues?|fluent|bilingual|trilingual|multilingual|"
    r"native|mother\s+tongue|courant|bilingue|trilingue|multilingue|"
    r"proficiency|proficient|intermediate|advanced|beginner|basic|"
    r"professional\s+working|maitrise|niveau)\b",
    re.IGNORECASE,
)


@dataclass
class CandidateFields:
    """Contact and background fields extracted from one CV."""

    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    headline: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    education_level: str = ""
    education: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "location": self.location,
            "headline": self.headline,
            "linkedin": self.linkedin,
            "github": self.github,
            "website": self.website,
            "education_level": self.education_level,
            "education": list(self.education),
            "certifications": list(self.certifications),
            "languages": list(self.languages),
        }


_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_MD_EMPHASIS_RE = re.compile(r"(\*\*|__)(.+?)\1")


def _strip_markdown(line: str) -> str:
    """Remove Markdown heading and bold markers."""
    line = _MD_HEADING_RE.sub("", line.strip())
    return _MD_EMPHASIS_RE.sub(r"\2", line)


def _clean_line(line: str) -> str:
    line = _BULLET_PREFIX_RE.sub("", _strip_markdown(line))
    line = re.sub(r"^[*_`]+|[*_`]+$", "", line).strip()
    return re.sub(r"\s+", " ", line)


def _clean_value(value: str) -> str:
    value = _clean_line(value)
    return value.strip(" -–—|,;")


def _valid_phone(raw: str, text: str, start: int) -> bool:
    digits = re.sub(r"\D", "", raw)
    if not (7 <= len(digits) <= 15):
        return False
    if re.fullmatch(r"(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}", raw.strip()):
        return False
    around = text[max(0, start - 30):start + len(raw) + 30].lower()
    if re.search(r"\b(?:present|current|now|today|aujourd.?hui)\b", around):
        return False
    if re.search(r"\b(?:19|20)\d{2}\b", raw):
        return False
    return True


def extract_email(text: str) -> str:
    match = _EMAIL_RE.search(text)
    return match.group(1).strip().lower() if match else ""


def extract_phone(text: str) -> str:
    for match in _PHONE_RE.finditer(text):
        raw = re.sub(r"\s+", " ", match.group(0)).strip()
        if _valid_phone(raw, text, match.start()):
            return raw
    return ""


def extract_links(text: str) -> Tuple[str, str, str]:
    linkedin = ""
    github = ""
    website = ""
    match = _LINKEDIN_RE.search(text)
    if match:
        linkedin = match.group(0).rstrip(".,;")
    match = _GITHUB_RE.search(text)
    if match:
        github = match.group(0).rstrip(".,;")
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;")
        lowered = url.lower()
        if "linkedin.com" in lowered or "github.com" in lowered:
            continue
        if _EMAIL_RE.search(url):
            continue
        website = url
        break
    return linkedin, github, website


def _looks_like_name(line: str) -> bool:
    line = _clean_line(line)
    if not line or len(line) > 70:
        return False
    if _EMAIL_RE.search(line) or _PHONE_RE.search(line) or _URL_RE.search(line):
        return False
    if re.search(r"\d", line):
        return False
    if any(ch in line for ch in "|@/\\"):
        return False
    if normalize_text(line).strip(" :") in _SECTION_HEADERS:
        return False
    base = line.split(",", 1)[0].strip()
    words = re.findall(
        r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.\-]*", base
    )
    if not (2 <= len(words) <= 5):
        return False
    if any(normalize_text(word) in _ROLE_WORDS for word in words):
        return False
    for word in words:
        if normalize_text(word) in _PARTICLES:
            continue
        if not (word[0].isupper() or word.isupper()):
            return False
    return True


def _normalise_name(raw: str) -> str:
    raw = _clean_value(raw)
    if not raw:
        return ""
    if "," in raw:
        left, right = (part.strip() for part in raw.split(",", 1))
        left_name = _looks_like_name(left)
        right_name = _looks_like_name(right)
        if left_name and not right_name:
            raw = left
        elif right_name and not left_name:
            raw = right
        elif left_name and right_name:
            raw = f"{right} {left}"
        elif len(left.split()) == 1 and len(right.split()) == 1:
            raw = f"{right} {left}"
        else:
            raw = left
    raw = re.sub(r"\s+", " ", raw).strip(" -–—,;")
    if raw.isupper() or raw.islower():
        raw = raw.title()
    return raw


def extract_name(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:12]:
        match = _NAME_LABEL_RE.match(_clean_line(line))
        if match:
            name = _normalise_name(match.group(1))
            if name:
                return name
    for line in lines[:8]:
        if _looks_like_name(line):
            return _normalise_name(line)
    return ""


def _looks_like_role(line: str) -> bool:
    line = _clean_line(line)
    if not line or len(line) > 100:
        return False
    if _EMAIL_RE.search(line) or _PHONE_RE.search(line) or _URL_RE.search(line):
        return False
    if any(ch in line for ch in "|@/\\"):
        return False
    if normalize_text(line).strip(" :") in _SECTION_HEADERS:
        return False
    if re.search(r"[.!?]$", line):
        return False
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.\-]*", line)
    if not words or len(words) > 10:
        return False
    if any(normalize_text(word) in _ROLE_WORDS for word in words):
        return True
    return False


def extract_headline(text: str, name: str = "") -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:12]:
        match = _HEADLINE_LABEL_RE.match(_clean_line(line))
        if match:
            return _clean_value(match.group(1))
    for raw in lines[:10]:
        cleaned = _clean_line(raw)
        if not cleaned:
            continue
        if name and cleaned.lower() == name.lower():
            continue
        if _BULLET_PREFIX_RE.match(_strip_markdown(raw.strip())):
            continue
        normalised = normalize_text(cleaned).strip(" :")
        if normalised in _SECTION_HEADERS:
            break
        for part in re.split(r"[|•·/]", cleaned):
            part = _clean_value(part)
            if _looks_like_role(part):
                return part
    return ""


def _looks_like_location(value: str) -> bool:
    value = _clean_value(value)
    if not value or len(value) > 80:
        return False
    if _EMAIL_RE.search(value) or _PHONE_RE.search(value) or _URL_RE.search(value):
        return False
    if _looks_like_name(value):
        return False
    if _YEAR_RE.search(value) or re.search(r"\d", value):
        return False
    if _DEGREE_RE.search(value) or _CERT_WORD_RE.search(value):
        return False
    normalised = normalize_text(value)
    if any(word in normalised for word in _INSTITUTION_WORDS):
        return False
    if any(word in normalised.split() for word in _ROLE_WORDS):
        return False
    return bool(_CITY_COUNTRY_RE.fullmatch(value))


def extract_location(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:15]:
        match = _LOCATION_LABEL_RE.match(_clean_line(line))
        if match:
            return _clean_value(match.group(1))
    for line in lines[:10]:
        if not (_EMAIL_RE.search(line) or _PHONE_RE.search(line) or _URL_RE.search(line)):
            continue
        for part in re.split(r"[|•·]", line):
            if _looks_like_location(part):
                return _clean_value(part)
    for line in lines[:6]:
        if _looks_like_location(line):
            return _clean_value(line)
    return ""


def _collect_section(
    lines: Sequence[str], header_re: re.Pattern[str]
) -> List[str]:
    collected: List[str] = []
    inside = False
    for raw in lines:
        line = _clean_line(raw)
        if not line:
            continue
        normalised = normalize_text(line).strip(" :")
        if header_re.match(normalised):
            inside = True
            continue
        if not inside:
            continue
        if _OTHER_SECTION_RE.match(normalised) or _EDUCATION_HEADER_RE.match(normalised) \
                or _CERTIFICATION_HEADER_RE.match(normalised) \
                or _LANGUAGE_HEADER_RE.match(normalised):
            break
        if len(line) <= 200:
            collected.append(line)
        if len(collected) >= 8:
            break
    return collected


def _dedupe(items: Sequence[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for item in items:
        key = normalize_text(item).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _degree_level(text: str) -> str:
    normalised = normalize_text(text)
    if _PHD_RE.search(normalised):
        return "PhD"
    if _MASTER_RE.search(normalised):
        return "Master"
    if _BACHELOR_RE.search(normalised):
        return "Bachelor"
    if _ASSOCIATE_RE.search(normalised):
        return "Associate/Diploma"
    if _HIGH_SCHOOL_RE.search(normalised):
        return "High school"
    return ""


def extract_education(text: str) -> Tuple[str, List[str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    collected: List[str] = []
    for line in lines:
        match = _EDUCATION_LABEL_RE.match(_clean_line(line))
        if match:
            value = _clean_value(match.group(1))
            if value:
                collected.append(value)
    collected.extend(_collect_section(lines, _EDUCATION_HEADER_RE))
    if not collected:
        for line in lines:
            cleaned = _clean_line(line)
            if not cleaned or len(cleaned) > 200:
                continue
            if _DEGREE_RE.search(cleaned) and not _CERT_WORD_RE.search(cleaned):
                if _YEAR_RE.search(cleaned) or any(
                    word in cleaned.lower() for word in
                    ("university", "college", "institute", "school",
                     "universite", "ecole", "institut", "cegep",
                     "centre de formation")
                ) or _DEGREE_RE.fullmatch(cleaned):
                    collected.append(cleaned)
    collected = _dedupe(collected)[:4]
    level = ""
    for item in collected:
        candidate = _degree_level(item)
        if _LEVEL_RANK.get(candidate, 0) > _LEVEL_RANK.get(level, 0):
            level = candidate
    return level, collected


_LEVEL_RANK = {
    "": 0, "High school": 1, "Associate/Diploma": 2,
    "Bachelor": 3, "Master": 4, "PhD": 5,
}


def extract_certifications(text: str) -> List[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    labelled: List[str] = []
    for line in lines:
        match = _CERTIFICATION_LABEL_RE.match(_clean_line(line))
        if match:
            value = _clean_value(match.group(1))
            if value:
                labelled.append(value)
    collected = labelled + [
        line for line in _collect_section(lines, _CERTIFICATION_HEADER_RE)
        if not (_EMAIL_RE.search(line) or _URL_RE.search(line)
                or _BARE_URL_RE.search(line)
                or normalize_text(line).startswith("badges"))
        and not (
            len(line.split()) <= 2
            and normalize_text(line) in _ROLE_WORDS
        )
    ]
    if not collected:
        for line in lines:
            cleaned = _clean_line(line)
            if not cleaned or len(cleaned) > 140:
                continue
            if _EMAIL_RE.search(cleaned) or _URL_RE.search(cleaned) \
                    or _BARE_URL_RE.search(cleaned):
                continue
            if len(cleaned.split()) <= 2 and normalize_text(cleaned) in _ROLE_WORDS:
                continue
            if _CERT_WORD_RE.search(cleaned):
                words = [
                    normalize_text(word)
                    for word in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", cleaned)
                ]
                if any(word in _ROLE_WORDS for word in words) and not re.search(
                    r"certification|certificate|license|licence|certified",
                    cleaned, re.IGNORECASE,
                ):
                    continue
                collected.append(cleaned)
            elif _CERT_ACRONYM_RE.search(cleaned) and len(cleaned.split()) <= 6:
                words = [
                    normalize_text(word)
                    for word in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", cleaned)
                ]
                if any(word in _ROLE_WORDS for word in words):
                    continue
                collected.append(cleaned)
    return _dedupe(collected)[:6]


def _language_names_in(text: str) -> List[str]:
    normalised = normalize_text(text)
    found: List[str] = []
    for name, display in _LANGUAGES.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", normalised):
            if display not in found:
                found.append(display)
    return found


def extract_languages(text: str) -> List[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    collected: List[str] = []
    for line in lines:
        match = _LANGUAGE_LABEL_RE.match(_clean_line(line))
        if not match:
            continue
        detail = _clean_value(match.group(1))
        names = _language_names_in(detail)
        if not names:
            continue
        if len(names) == 1 and len(detail) <= 60 and re.search(
            r"\(|fluent|native|courant|bilingue|intermediate|basic|advanced",
            detail, re.IGNORECASE,
        ):
            collected.append(detail)
        else:
            collected.extend(names)
    for line in _collect_section(lines, _LANGUAGE_HEADER_RE):
        names = _language_names_in(line)
        if names:
            detail = _clean_line(line)
            if len(names) == 1 and len(detail) <= 60 and re.search(
                r"\(|fluent|native|courant|bilingue|intermediate|basic|advanced",
                detail, re.IGNORECASE,
            ):
                collected.append(detail)
            else:
                collected.extend(names)
    if not collected:
        for line in lines:
            cleaned = _clean_line(line)
            if not cleaned or len(cleaned) > 160:
                continue
            names = _language_names_in(cleaned)
            if not names:
                continue
            if _LANGUAGE_CONTEXT_RE.search(cleaned):
                if len(names) == 1 and len(cleaned) <= 60:
                    collected.append(cleaned)
                else:
                    collected.extend(names)
            elif len(names) >= 2 and len(cleaned.split()) <= 8:
                collected.extend(names)
    return _dedupe(collected)[:8]


def extract_fields(text: str) -> CandidateFields:
    """Extract contact and background fields from one résumé."""
    email = extract_email(text)
    phone = extract_phone(text)
    linkedin, github, website = extract_links(text)
    name = extract_name(text)
    headline = extract_headline(text, name)
    location = extract_location(text)
    education_level, education = extract_education(text)
    certifications = extract_certifications(text)
    languages = extract_languages(text)
    return CandidateFields(
        name=name,
        email=email,
        phone=phone,
        location=location,
        headline=headline,
        linkedin=linkedin,
        github=github,
        website=website,
        education_level=education_level,
        education=education,
        certifications=certifications,
        languages=languages,
    )
