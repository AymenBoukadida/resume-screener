"""Term mining for requirement phrases not covered by the skills taxonomy."""

import re
from collections import Counter
from typing import Dict, List, Optional, Sequence, Set, Tuple

from extractors.keyword_extractor import KeywordExtractor
from extractors.normalize import normalize_text

MAX_NGRAM = 3
BUCKET_CAPS = {"required": 14, "preferred": 6, "keywords": 10}
BUCKET_WEIGHTS = {"required": 3.0, "preferred": 2.0, "keywords": 1.0}
PROPER_BONUS = 2.0
LENGTH_BONUS = 0.15
EARLY_BONUS = 1.5

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
    "while", "at", "by", "for", "with", "without", "about", "into",
    "through", "during", "to", "from", "in", "on", "of", "off", "over",
    "under", "this", "that", "these", "those", "is", "are", "was", "were",
    "be", "been", "being", "am", "have", "has", "had", "having", "do",
    "does", "did", "doing", "will", "would", "shall", "should", "can",
    "could", "may", "might", "must", "as", "it", "its", "they", "them",
    "their", "we", "our", "you", "your", "he", "him", "his", "she", "her",
    "i", "me", "my", "who", "whom", "which", "what", "whose", "where",
    "why", "how", "not", "no", "nor", "so", "than", "too", "very", "just",
    "also", "only", "own", "same", "etc", "e.g", "i.e", "get", "got",
    "more", "out", "such", "most", "know", "known", "seeking",
    "le", "la", "les", "l", "un", "une", "des", "du", "d", "et", "ou",
    "mais", "donc", "ni", "car", "si", "quand", "lorsque", "au", "aux",
    "avec", "sans", "sur", "sous", "dans", "en", "entre", "chez", "vers",
    "par", "pour", "que", "qui", "quoi", "dont", "ce", "cet", "cette",
    "ces", "son", "sa", "ses", "leur", "leurs", "mon", "ma", "mes", "ton",
    "ta", "tes", "notre", "nos", "votre", "vos", "il", "elle", "ils",
    "elles", "je", "tu", "nous", "vous", "ne", "pas", "plus", "moins",
    "tres", "aussi", "chaque", "tout", "toute", "tous", "toutes",
    "autre", "autres", "meme", "tel", "telle", "etre", "avoir", "fait",
    "faire", "etait", "etaient", "sont", "sera", "seront", "atouts",
}

GENERIC_WORDS = {
    "job", "jobs", "role", "roles", "position", "positions", "posting",
    "postings", "opportunity", "opportunities", "career", "careers",
    "company", "companies", "employer", "workplace", "office", "location",
    "locations", "salary", "pay", "compensation", "benefit", "benefits",
    "perk", "perks", "vacation", "pension", "insurance", "equity",
    "stock", "visa", "sponsorship", "relocation", "interview",
    "interviews", "application", "applications", "apply", "applicant",
    "applicants", "candidate", "candidates", "resume", "resumes", "cv",
    "hiring", "recruitment", "recruiter", "recruiters",
    "team", "teams", "teammate", "teammates", "environment",
    "environments", "culture", "values", "mission", "vision", "people",
    "person", "daily", "time", "full", "part",
    "schedule", "schedules", "weekend", "weekends", "hour", "hours",
    "day", "days", "year", "years", "ans", "annual", "quarterly",
    "bonus",
    "certification", "certifications", "certificate", "degree", "diploma",
    "bachelor", "bachelors", "master", "masters", "phd", "school",
    "university", "college", "academy", "experience", "experiences",
    "skill", "skills", "knowledge", "abilities", "ability", "strong",
    "excellent", "good", "great", "solid", "proven", "including",
    "include", "includes", "various", "similar", "relevant", "following",
    "preferred", "required", "responsibilities", "responsibility",
    "requirement", "requirements", "qualification", "qualifications",
    "task", "tasks", "duty", "duties", "looking", "join", "help", "new",
    "well", "across", "within", "please", "contact", "check", "learn",
    "life", "us", "equal", "diversity", "inclusion", "accommodation",
    "request", "requests", "tool", "tools", "platform", "platforms",
    "solution", "solutions", "work", "working", "works", "worked",
    "based", "high", "level", "levels", "plus", "success", "successful",
    "growth", "training", "programs", "service",
    "services", "system", "systems", "software", "application",
    "applications", "business", "testing",
    "network", "networks", "user", "users", "product",
    "project", "projects", "process", "processes", "technical",
    "understanding", "ability",
    "nice", "ideally", "asset", "assets", "advantage", "advantages",
    "client", "clients", "customer", "customers", "linkedin",
    "instagram", "facebook", "twitter", "youtube", "tiktok",
    "north", "south", "east", "west", "northeast", "northwest",
    "southeast", "southwest", "america", "canada", "europe", "online",
    "senior", "junior",
    "alert", "alerts", "incident", "incidents", "long", "view",
    "support", "respond", "escalate", "monitor", "complete", "perform",
    "ensure", "maintain", "provide", "assist", "handle", "review",
    "identify", "coordinate", "friendly", "operational", "insertion",
    "poste", "postes", "emploi", "metier", "entreprise", "societe",
    "equipe", "equipes", "lieu", "salaire", "remuneration", "avantage",
    "avantages", "conges", "mutuelle", "entretien", "candidat",
    "candidats", "candidature", "recrutement", "recruteur", "recruteurs",
    "competence", "competences", "connaissance", "connaissances",
    "capacite", "aptitude", "taches", "responsabilites", "horaires",
    "quart", "quarts", "jour", "jours", "annee", "annees", "diplome",
    "bac", "licence", "formation", "travail", "travailler", "forte",
    "bon", "bonne", "compris", "gestion", "informatique", "systemes",
    "nouveaux", "comprehension",
}

_ROLE_AND_CONDITION_WORDS = {
    "nurse", "nurses", "welder", "welders", "developer", "developers",
    "engineer", "engineers", "analyst", "analysts", "manager", "managers",
    "specialist", "specialists", "technician", "technicians",
    "administrator", "administrators", "consultant", "consultants",
    "coordinator", "coordinators", "assistant", "assistants",
    "director", "directors", "officer", "officers", "intern", "interns",
    "student", "students", "teacher", "teachers", "professor", "professors",
    "accountant", "accountants", "lawyer", "lawyers", "doctor", "doctors",
    "pharmacist", "pharmacists", "electrician", "electricians",
    "plumber", "plumbers", "carpenter", "carpenters", "mechanic",
    "mechanics", "driver", "drivers", "clerk", "clerks", "receptionist",
    "receptionists", "secretary", "secretaries", "supervisor", "supervisors",
    "lead", "leads", "head", "heads", "chief", "chiefs", "president",
    "owner", "owners", "partner", "partners", "apprentice", "apprentices",
    "trainee", "trainees", "graduate", "graduates", "professional",
    "professionals", "expert", "experts", "scientist", "scientists",
    "researcher", "researchers", "designer", "designers", "writer",
    "writers", "editor", "editors", "marketer", "marketers", "recruiter",
    "recruiters", "therapist", "therapists", "dentist", "dentists",
    "surgeon", "surgeons", "veterinarian", "veterinarians", "chef", "chefs",
    "barista", "baristas", "cashier", "cashiers", "salesperson",
    "salespersons", "representative", "representatives", "agent", "agents",
    "broker", "brokers",
    "care", "hospital", "clinic", "ward", "unit", "department", "facility",
    "site", "shop", "store", "branch", "organization", "organisation",
    "institution", "agency", "firm", "division", "staff", "employee",
    "employees", "worker", "workers", "colleague", "colleagues",
    "shift", "shifts", "night", "nights", "overnight", "overnights",
    "rotation", "rotations", "rotating", "availability", "available",
    "onsite", "on-site", "remote", "hybrid", "commute", "commuting",
    "line", "certified", "registered", "licensed", "current", "valid",
    "proficiency", "proficient", "trained", "training", "trainings",
    "language", "languages", "langue", "langues", "fluent", "bilingual",
    "trilingual", "multilingual", "native", "courant", "bilingue",
    "degree", "degrees", "diploma", "diplomas", "certification",
    "certifications", "certificate", "certificates", "license", "licenses",
    "licence", "licences", "credential", "credentials", "accreditation",
    "accreditations", "course", "courses", "coursework", "school",
    "university", "college", "academy", "institute", "education",
    "formation", "etudes", "diplome", "diplomes",
}
GENERIC_WORDS |= _ROLE_AND_CONDITION_WORDS

_LOCATION_LINE_RE = re.compile(
    r"\b(?:based\s+in|located\s+in|location|relocat(?:e|ion)|"
    r"commut(?:e|ing)|address|city|province|state|country)\b",
    re.IGNORECASE,
)
_CITY_LINE_RE = re.compile(
    r"^\s*[A-Z][\w .'-]+,\s*(?:[A-Z]{2}|[A-Z][\w .'-]+)"
    r"(?:\s*\|.*)?\s*$"
)
_SALARY_RE = re.compile(
    r"(?:[$€£]\s?\d|\b\d[\d,.]*\s*(?:k|per\s+(?:hour|year|annum)|/h|/yr)\b)",
    re.IGNORECASE,
)
_CULTURE_RE = re.compile(
    r"\b(?:equal\s+opportunity|diversity|inclusion|accommodation|"
    r"why\s+work|perks?|vacation|pension|insurance|equity|"
    r"stock\s+options?|relocation|visa\s+sponsorship)\b",
    re.IGNORECASE,
)
_CONTACT_RE = re.compile(
    r"(?:https?://|www\.|@|linkedin\.com|github\.com)", re.IGNORECASE
)

_WORD_RE = re.compile(r"[a-z0-9]+(?:[.#'/&+-][a-z0-9]+)*")

_LANGUAGE_WORDS = {
    "english", "anglais", "french", "francais", "spanish", "espagnol",
    "german", "allemand", "arabic", "arabe", "mandarin", "cantonese",
    "cantonais", "portuguese", "portugais", "italian", "italien",
    "russian", "russe", "japanese", "japonais", "korean", "coreen",
    "hindi", "urdu", "ourdou", "turkish", "turc", "dutch", "neerlandais",
    "polish", "polonais", "vietnamese", "vietnamien", "tagalog", "farsi",
    "persian", "persan", "hebrew", "hebreu", "greek", "grec", "swedish",
    "suedois", "norwegian", "norvegien", "danish", "danois", "finnish",
    "finnois", "czech", "tcheque", "romanian", "roumain", "hungarian",
    "hongrois", "ukrainian", "ukrainien", "bengali", "tamil", "tamoul",
    "malay", "malais", "indonesian", "indonesien", "thai", "swahili",
    "amharic", "somali", "yoruba", "igbo", "hausa", "zulu", "afrikaans",
}


def _is_language_term(term: Sequence[str]) -> bool:
    """True when every token is just a language name (or a slash list)."""
    tokens: List[str] = []
    for token in term:
        tokens.extend(part for part in token.split("/") if part)
    return bool(tokens) and all(token in _LANGUAGE_WORDS for token in tokens)


def _is_non_requirement_line(text: str) -> bool:
    if _SALARY_RE.search(text) or _CULTURE_RE.search(text):
        return True
    if _CONTACT_RE.search(text):
        return True
    if _CITY_LINE_RE.match(text.strip()):
        return True
    if _LOCATION_LINE_RE.search(text) and len(text.split()) <= 30:
        return True
    return False

_Term = Tuple[str, ...]
_VariationIndex = List[Tuple[_Term, str]]


def _term_tokens(text: str) -> List[str]:
    """Content tokens of *text*: normalized, grammar words dropped."""
    normalized = normalize_text(text).replace("'", " ")
    return [t for t in _WORD_RE.findall(normalized) if t not in STOPWORDS]


def _content_runs(text: str) -> List[List[str]]:
    """Return maximal runs of adjacent content tokens."""
    norm = normalize_text(text).replace("'", " ")
    runs: List[List[str]] = []
    run: List[str] = []
    prev_end = None
    for match in _WORD_RE.finditer(norm):
        token = match.group(0)
        separated = prev_end is not None and bool(norm[prev_end:match.start()].strip())
        if token in STOPWORDS or len(token) < 2 or token.isdigit():
            if run:
                runs.append(run)
                run = []
        elif separated:
            if run:
                runs.append(run)
            run = [token]
        else:
            run.append(token)
        prev_end = match.end()
    if run:
        runs.append(run)
    return runs


EDGE_FILLER = {
    "skill", "skills", "experience", "experiences", "knowledge",
    "ability", "abilities", "strong", "proven", "excellent", "good",
    "great", "solid", "tool", "tools", "platform", "platforms",
    "certification", "certifications", "certificate", "including",
    "various", "similar", "relevant", "following", "preferred",
    "required", "understanding", "years", "work", "working", "works",
    "worked", "level", "levels", "plus", "based", "high", "new",
    "build", "builds", "building", "built", "create", "creates",
    "created", "creating", "develop", "develops", "developing",
    "developed", "design", "designs", "designing", "use", "uses",
    "using", "used", "manage", "manages", "managing", "managed",
    "lead", "leading", "led", "write", "writes", "writing", "written",
    "implement", "implements", "implementing", "implemented",
    "maintain", "maintaining", "test", "testing", "keep", "keeps",
    "keeping", "team", "teams", "support", "supporting", "background",
    "certified", "registered", "licensed", "current", "valid",
    "proficiency", "proficient", "trained", "training", "trainings",
    "scripting", "development", "professional",
}


def _strip_edges(term: Tuple[str, ...]) -> Optional[_Term]:
    """Remove generic filler from both ends of a term."""
    start, end = 0, len(term)
    while start < end and term[start] in EDGE_FILLER:
        start += 1
    while end > start and term[end - 1] in EDGE_FILLER:
        end -= 1
    if start >= end:
        return None
    return term[start:end]


def _proper_words(text: str) -> Set[str]:
    """Return words that appear capitalised mid-line."""
    caps: Counter = Counter()
    total: Counter = Counter()
    for line in text.splitlines():
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'#./&+-]*", line)
        n = len(words)
        in_short_run = [False] * n
        i = 1
        while i < n:
            if words[i][0].isupper():
                j = i
                while j < n and words[j][0].isupper():
                    j += 1
                if j - i <= 2:
                    for k in range(i, j):
                        in_short_run[k] = True
                i = j
            else:
                i += 1
        for i, word in enumerate(words):
            low = word.lower()
            total[low] += 1
            if in_short_run[i] or (
                i == 0 and len(word) <= 6 and word.isupper()
            ):
                caps[low] += 1
    return {
        word for word, count in total.items()
        if count and caps[word] / count >= 0.6 and re.search(r"[A-Za-z]", word)
    }


def _contains(big: _Term, small: _Term) -> bool:
    """True when *small* is a contiguous token subsequence of *big*."""
    n = len(small)
    return any(big[i:i + n] == small for i in range(len(big) - n + 1))


def build_variation_index(taxonomy: Dict) -> _VariationIndex:
    """Build stopword-stripped taxonomy variations."""
    index: _VariationIndex = []
    for skills_dict in taxonomy.values():
        for skill, variations in skills_dict.items():
            for variation in variations:
                tokens = tuple(_term_tokens(variation))
                if tokens:
                    index.append((tokens, skill))
    return index


def _canonical(
    term: _Term,
    index: _VariationIndex,
    proper: Optional[Set[str]] = None,
) -> Optional[str]:
    """Return the best canonical skill for a mined term."""
    proper = proper or set()
    best: Optional[str] = None
    best_rank = 0
    for variation, skill in index:
        if term == variation:
            rank = 3
        elif len(variation) >= 2 and _contains(term, variation):
            rank = 2
        elif (
            len(variation) == 1
            and len(term) > 1
            and variation[0] in proper
            and _contains(term, variation)
        ):
            rank = 2
        elif len(term) == 1 and len(variation) >= 2 and _contains(variation, term):
            rank = 1
        else:
            continue
        if rank > best_rank:
            best = skill
            best_rank = rank
    return best


def mine_terms(
    records: Sequence[Tuple[Optional[str], str, bool, int]],
    extractor: KeywordExtractor,
    existing: Set[str],
) -> Dict[str, List[Tuple[_Term, Optional[str]]]]:
    """Mine requirement phrases from classified JD lines."""
    content = "\n".join(text for _bucket, text, _b, _i in records)
    proper = _proper_words(content)
    index = build_variation_index(extractor.skills_taxonomy)

    total_lines = max(len(records), 1)
    early_cutoff = max(8, int(total_lines * 0.25))

    freq: Counter = Counter()
    first_idx: Dict[_Term, int] = {}
    first_bucket: Dict[_Term, Optional[str]] = {}
    bullet_in: Dict[str, Set[_Term]] = {"required": set(), "preferred": set()}
    section_of: Dict[_Term, str] = {}
    sentence_line = {
        idx for _b, text, _bl, idx in records
        if text[-1:] in ".!?" and len(text.split()) > 15
    }
    for bucket, text, is_bullet, idx in records:
        if _is_non_requirement_line(text):
            continue
        seen_in_line: Set[_Term] = set()
        for run in _content_runs(text):
            for start in range(len(run)):
                for n in range(1, MAX_NGRAM + 1):
                    if start + n > len(run):
                        break
                    term = _strip_edges(tuple(run[start:start + n]))
                    if term is None:
                        continue
                    if len(term) == 1 and n > 1:
                        continue
                    if term in seen_in_line:
                        continue
                    seen_in_line.add(term)
                    freq[term] += 1
                    if term not in first_idx or idx < first_idx[term]:
                        first_idx[term] = idx
                        first_bucket[term] = bucket
                    if bucket in bullet_in and len(text.split()) <= 12:
                        bullet_in[bucket].add(term)
                    if bucket in ("required", "preferred") and term not in section_of:
                        section_of[term] = bucket

    candidates = []
    existing_tokens = [
        tuple(_term_tokens(name)) for name in existing if name.strip()
    ]
    for term, count in freq.items():
        if any(len(token) < 2 or token.isdigit() for token in term):
            continue
        informative = [t for t in term if t not in GENERIC_WORDS]
        if not informative:
            continue
        if _is_language_term(tuple(informative)):
            continue
        if any(
            len(tokens) > len(term) and _contains(tokens, term)
            for tokens in existing_tokens
        ):
            continue
        informative_proper = [t for t in informative if t in proper]
        is_proper = bool(informative_proper)
        proper_count = len(informative_proper)
        early = (
            first_bucket.get(term) is None and first_idx[term] < early_cutoff
        )
        bullet = (term in bullet_in["required"]) or (term in bullet_in["preferred"])

        if len(term) == 1:
            if term[0] in GENERIC_WORDS:
                continue
            if count < 3 and term[0] not in proper:
                continue
        else:
            if len(informative) < 2 and not informative_proper:
                continue
            if not (count >= 2 or is_proper or bullet or early):
                continue
            if len(term) > 2 and not (
                count >= 2 or proper_count >= 2 or bullet or early
            ):
                continue

        bucket = section_of.get(term, "keywords")
        weight = BUCKET_WEIGHTS[bucket]
        if bucket == "keywords" and first_idx[term] in sentence_line:
            continue
        score = (
            count * weight
            * (PROPER_BONUS if is_proper else 1.0)
            * (1.0 + LENGTH_BONUS * (len(term) - 1))
            * (EARLY_BONUS if early else 1.0)
            * (0.5 if first_idx[term] in sentence_line else 1.0)
        )
        candidates.append((score, term, bucket))

    candidates.sort(
        key=lambda c: (
            0 if len(c[1]) == 1 and c[1][0] in proper else 1,
            -c[0],
            c[1],
        )
    )

    picked: Dict[str, List[Tuple[_Term, Optional[str]]]] = {
        "required": [], "preferred": [], "keywords": [],
    }
    claimed: Dict[str, Set[str]] = {b: set() for b in picked}
    for _score, term, bucket in candidates:
        if len(picked[bucket]) >= BUCKET_CAPS[bucket]:
            continue
        display = " ".join(term)
        canonical = _canonical(term, index, proper)
        if canonical and canonical in existing:
            continue
        if display in existing:
            continue
        informative = [t for t in term if t not in GENERIC_WORDS]
        claimed_count = sum(t in claimed[bucket] for t in informative)
        proper_claimed = any(
            t in proper and t in claimed[bucket] for t in informative
        )
        if not informative or proper_claimed or claimed_count >= 2:
            continue
        picked[bucket].append((term, canonical))
        claimed[bucket].update(informative)
    return picked


def _token_pattern(token: str) -> str:
    """Build a regex for one token with common inflections."""
    if token.endswith("ing") and len(token) >= 6:
        stem = token[:-3]
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            stem = stem[:-1]
            return (
                re.escape(stem)
                + r"(?:" + re.escape(stem[-1]) + r")?"
                + r"(?:ing|ed|er|ers|es|s|e)?"
            )
        return re.escape(stem) + r"(?:ing|ed|er|ers|es|s|e)?"
    if token.endswith("ed") and len(token) >= 5:
        stem = token[:-2]
        return re.escape(stem) + r"(?:ed|ing|er|ers|es|s|e)?"
    return re.escape(token)


def match_terms_detailed(text: str, terms: Set[str]) -> Dict[str, str]:
    """Return mined terms present in *text* with evidence snippets."""
    from extractors.keyword_extractor import _is_negated, _snippet

    if not terms:
        return {}
    norm = normalize_text(text)
    found: Dict[str, str] = {}
    for term in terms:
        parts = [_token_pattern(normalize_text(token)) for token in term.split(" ")]
        pattern = r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(parts) + r"(?![a-z0-9])"
        for match in re.finditer(pattern, norm):
            if _is_negated(norm, match.start()):
                continue
            found[term] = _snippet(norm, match.start(), match.end())
            break
    return found


def match_terms(text: str, terms: Set[str]) -> Set[str]:
    """Mined terms present in *text*."""
    return set(match_terms_detailed(text, terms))
