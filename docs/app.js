/* Résumé Screening System - static web app. */
"use strict";

// Bump this whenever docs/app.js or docs/data/* changes. It is used both as a
// cache-busting query string and as the build label in the footer, so a stale
// cached app is visible instead of silently producing old scores.
const APP_VERSION = "2026-10-26";

const state = {
  config: null,
  taxonomy: null,
  patterns: [],
  pendingFiles: [],
  lastResults: null,
  requirements: null,
  extractTimer: null,
};

/* ---------------- text normalization ---------------- */

function normalizeText(s) {
  return s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\u2019/g, "'")
    .replace(/([a-z])'s\b/g, "$1");
}

/* ---------------- regex helpers ----------------------------------------- */

const BULLET_CHARS = "-*•·▪‣–—";
const WORD_NUMBERS = {
  one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  un: 1, une: 1, deux: 2, trois: 3, quatre: 4, cinq: 5,
  six: 6, sept: 7, huit: 8, neuf: 9, dix: 10,
};

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const NEGATION_RE = /\b(?:not|no|never|without|neither|pas|sans|aucun(?:e|es)?|nul(?:le)?)\b/;
const NEGATION_EXCEPTION_RE = /\bnot\s+only\b|\bpas\s+seulement\b/;
const VERSION_SUFFIX = "(?:[\\s._-]*v?\\d+(?:\\.\\d+){0,2})?";

function isNegated(textNorm, start) {
  const window = textNorm.slice(Math.max(0, start - 80), start);
  if (NEGATION_EXCEPTION_RE.test(window)) return false;
  const tokens = window.trim().split(/\s+/).slice(-6);
  return NEGATION_RE.test(tokens.join(" "));
}

function evidenceSnippet(textNorm, start, end, radius = 42) {
  const lo = Math.max(0, start - radius);
  const hi = Math.min(textNorm.length, end + radius);
  let chunk = textNorm.slice(lo, hi).trim();
  if (lo > 0) chunk = "…" + chunk;
  if (hi < textNorm.length) chunk = chunk + "…";
  return chunk.replace(/\s+/g, " ");
}

function buildPatterns(taxonomy) {
  const patterns = [];
  for (const skillsDict of Object.values(taxonomy)) {
    for (const [skillName, variations] of Object.entries(skillsDict)) {
      for (const variation of variations) {
        patterns.push([
          skillName,
          new RegExp(
            "(^|[^a-z0-9])" + escapeRe(normalizeText(variation)) +
              VERSION_SUFFIX + "(?![a-z0-9])",
            "g"
          ),
        ]);
      }
    }
  }
  return patterns;
}

function extractSkillsDetailed(text) {
  const norm = normalizeText(text);
  const found = {};
  for (const [skillName, pattern] of state.patterns) {
    if (found[skillName]) continue;
    pattern.lastIndex = 0;
    let m;
    while ((m = pattern.exec(norm)) !== null) {
      const start = m.index + m[1].length;
      if (isNegated(norm, start)) continue;
      found[skillName] = evidenceSnippet(norm, start, m.index + m[0].length);
      break;
    }
  }
  return found;
}

function extractSkills(text) {
  return new Set(Object.keys(extractSkillsDetailed(text)));
}

const YEARS_UNIT = "(?:years?|ans?|annee?s?)";
const YEARS_DIGIT_RE = new RegExp(
  "(^|[^\\d.,])(\\d{1,2}(?:[.,]\\d)?)" +
    "(?:\\s*(?:\\+|to|-|–)(?:\\s*(\\d{1,2}(?:[.,]\\d)?))?)?" +
    "\\s*" + YEARS_UNIT + "\\b",
  "g"
);
const FALSE_YEAR_RE = new RegExp(
  "(?:^|[^\\d.,])(\\d{1,2}(?:[.,]\\d)?)\\s*" + YEARS_UNIT +
    "[\\s-]*(?:old|agee?s?)\\b" +
    "|(?:founded|etablie?|cree?e?|created)\\s+(?:(?:il\\s+y\\s+a|ago)\\s+)?" +
    "(\\d{1,2}(?:[.,]\\d)?)\\s*" + YEARS_UNIT +
    "|(?:il\\s+y\\s+a)\\s+(\\d{1,2}(?:[.,]\\d)?)\\s*" + YEARS_UNIT,
  "gi"
);
const MONTHS = {
  jan: 1, january: 1, janv: 1, janvier: 1,
  feb: 2, february: 2, fevr: 2, fevrier: 2, fev: 2,
  mar: 3, march: 3, mars: 3,
  apr: 4, april: 4, avr: 4, avril: 4,
  may: 5, mai: 5,
  jun: 6, june: 6, juin: 6,
  jul: 7, july: 7, juil: 7, juillet: 7,
  aug: 8, august: 8, aout: 8, aou: 8,
  sep: 9, sept: 9, september: 9, septembre: 9,
  oct: 10, october: 10, octobre: 10,
  nov: 11, november: 11, novembre: 11,
  dec: 12, december: 12, decembre: 12,
};
const MONTH_ALT = Object.keys(MONTHS).sort((a, b) => b.length - a.length).join("|");
const YEAR_RE = "(?:19|20)\\d{2}";
const PRESENT_RE = "(?:present|current|now|aujourd.?hui|actuel(?:le)?|date)";
const RANGE_RE = new RegExp(
  "(?:(" + MONTH_ALT + ")\\.?\\s+)?(" + YEAR_RE + ")\\s*" +
    "(?:[-–—]|to|a|au|until|jusqu.?a)\\s*" +
    "(?:(" + MONTH_ALT + ")\\.?\\s+)?(" + PRESENT_RE + "|" + YEAR_RE + ")",
  "gi"
);
const SINCE_RE = new RegExp(
  "\\b(?:since|from|depuis)\\s+(?:(" + MONTH_ALT + ")\\.?\\s+)?(" + YEAR_RE + ")\\b",
  "gi"
);

function falsePositiveSpans(norm) {
  const spans = [];
  FALSE_YEAR_RE.lastIndex = 0;
  let m;
  while ((m = FALSE_YEAR_RE.exec(norm)) !== null) {
    spans.push([m.index, m.index + m[0].length]);
  }
  return spans;
}

function covered(index, spans) {
  return spans.some(([a, b]) => index >= a && index < b);
}

function mergedSpan(intervals) {
  if (!intervals.length) return 0;
  const ordered = intervals.slice().sort((a, b) => a[0] - b[0]);
  const merged = [[ordered[0][0], ordered[0][1]]];
  for (const [start, end] of ordered.slice(1)) {
    if (start <= merged[merged.length - 1][1]) {
      merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], end);
    } else {
      merged.push([start, end]);
    }
  }
  return merged.reduce((sum, [a, b]) => sum + (b - a), 0);
}

function employmentSpan(norm, today) {
  const intervals = [];
  RANGE_RE.lastIndex = 0;
  let m;
  while ((m = RANGE_RE.exec(norm)) !== null) {
    const y0 = parseInt(m[2], 10);
    const m0 = m[1] ? (MONTHS[normalizeText(m[1])] || 1) : 1;
    const present = new RegExp("^" + PRESENT_RE + "$", "i").test(m[4]);
    let y1, m1;
    if (present) {
      y1 = today.getFullYear();
      m1 = today.getMonth() + 1;
    } else {
      y1 = parseInt(m[4], 10);
      m1 = m[3] ? (MONTHS[normalizeText(m[3])] || 12) : 12;
    }
    const start = y0 + (m0 - 1) / 12;
    const end = y1 + m1 / 12;
    if (end > start) intervals.push([start, end]);
  }
  SINCE_RE.lastIndex = 0;
  while ((m = SINCE_RE.exec(norm)) !== null) {
    const month = m[1] ? (MONTHS[normalizeText(m[1])] || 1) : 1;
    const start = parseInt(m[2], 10) + (month - 1) / 12;
    const end = today.getFullYear() + (today.getMonth() + 1) / 12;
    if (end > start) intervals.push([start, end]);
  }
  return mergedSpan(intervals);
}

function extractYears(text, mode = "max", today = new Date()) {
  const norm = normalizeText(text);
  const skipped = falsePositiveSpans(norm);
  const values = [];
  YEARS_DIGIT_RE.lastIndex = 0;
  let m;
  while ((m = YEARS_DIGIT_RE.exec(norm)) !== null) {
    if (covered(m.index, skipped)) continue;
    for (const bound of [m[2], m[3]]) {
      if (bound) values.push(parseFloat(bound.replace(",", ".")));
    }
  }
  for (const [word, value] of Object.entries(WORD_NUMBERS)) {
    const wordRe = new RegExp("\\b(" + word + ")\\s*(?:\\+|to|-|–)?\\s*" + YEARS_UNIT + "\\b", "gi");
    while ((m = wordRe.exec(norm)) !== null) {
      if (!covered(m.index, skipped)) values.push(value);
    }
  }
  if (mode === "min") {
    if (!values.length) return 0;
    return Math.floor(Math.min(...values));
  }
  const span = employmentSpan(norm, today);
  if (span) values.push(span);
  if (!values.length) return 0;
  return Math.floor(Math.max(...values));
}

/* ---------------- JD parsing -------------------------------------------- */

const SECTION_PATTERNS = [
  ["preferred", /^(?:preferred(?:\s+(?:skills?|qualifications?|experience|requirements?))?|(?:nice|good)[\s-]?to[\s-]?haves?(?:\s+skills?)?|bonus(?:\s+(?:skills?|points?))?(?:\s+if\s+you\s+have)?|desirable|desired(?:\s+skills?)?|pluses?|a\s+plus|assets?|advantages?|certifications?\s*\([^)]*\b(?:advantage|asset|preferred|plus)\b[^)]*\)|what\s+makes\s+you(?:\s+[a-z]+){0,4}|optional(?:\s+(?:skills?|qualifications?))?|(?:stand\s+out|extra\s+credit|even\s+better\s+if|you\s+might\s+also\s+have)|additional\s+(?:skills?|qualifications?)|souhaite(?:e|es|s)?|atouts?|apprecie(?:e|es|s)?|serait\s+un\s+plus|un\s+plus|les\s+plus|optionnel(?:le)?s?|competences?\s+(?:souhaitees?|recherchees?|desirables?)|qualifications?\s+souhaitees?)$/i],
  ["required", /^(?:required(?:\s+(?:skills?|qualifications?|experience|education|certifications?))?|requirements?|technical\s+requirements?|key\s+requirements?|must[\s-]?haves?(?:\s+skills?)?|essential|(?:minimum|basic|preferred|additional|desired)\s+(?:qualifications?|requirements?)|qualifications?|qualifications?\s+(?:and|&)\s+experience|requirements?\s+(?:and|&)\s+qualifications?|what\s+you(?:\s+will)?\s+(?:bring|need|have|offer)|what\s+you(?:'ll|\s+will)\s+(?:bring|need|have|offer)|what\s+we(?:'re|\s+are)\s+looking\s+for|what\s+we\s+need|your\s+(?:profile|background)|about\s+you|who\s+you\s+are|you\s+(?:have|bring|offer)|profile|background|the\s+ideal\s+candidate|ideal\s+candidate|candidate\s+profile|skills?(?:\s+(?:and|&)\s+experience)?|experience\s+(?:and|&)\s+skills?|(?:technical|soft|hard|key|core)\s+skills?(?:\s+required)?|competencies|proficiencies|expertise|education(?:\s+(?:and|&)\s+(?:certifications?|training))?|educational\s+background|academic\s+background|certifications?(?:\s+(?:and|&)\s+licen[cs]es?)?|certificates?|licen[cs]es?|credentials?|languages?|language\s+skills?|ce\s+que\s+vous\s+(?:apportez|offrez)|profil(?:\s+recherche)?|votre\s+profil|a\s+propos\s+de\s+vous|requises?|requis|exigees?|exigences?|essentielles?|obligatoires?|indispensables?|necessaires?|prerequis|competences(?:\s+(?:requises?|et\s+experience))?|formation(?:\s+requise)?|diplomes?(?:\s+requis)?|certifications?\s+requises?|langues?|competences?\s+linguistiques?)$/i],
  ["experience", /^(?:experience|experiences|responsibilit(?:y|ies)|what\s+you.{0,3}ll\s+do|what\s+you\s+will\s+do|(?:a\s+)?day\s+in\s+the\s+life|day[\s-]?to[\s-]?day|your\s+mission|your\s+missions|duties|missions|taches|au\s+quotidien|ce\s+que\s+vous\s+(?:ferez|allez\s+faire)|vos\s+missions)$/i],
];
const MIN_SIGNAL_SKILLS = 2;
const BULLET_PREFIX_RE = /^(?:[-*•·▪‣–—]+|\d+[.)]\s+|[a-z][.)]\s+)/i;

const REQUIRED_CUE_RE = /\b(?:must[\s-]?have|required|requirements?|essential|proficien(?:t|cy)\s+(?:in|with)|experience\s+(?:working\s+)?(?:with|in)|knowledge\s+of|familiarity\s+with|ability\s+to|skilled\s+in|expertise\s+in|hands[\s-]?on\s+experience|working\s+knowledge|certification\s+in|degree\s+in|bilingual|fluent\s+in|qualified\s+in|strong\s+background\s+in|solid\s+understanding\s+of|demonstrated\s+experience|proven\s+experience|track\s+record\s+(?:in|of)|(?:\d{1,2}(?:[.,]\d)?\s*(?:\+|to|-|–)?\s*(?:years?|ans?|annees?))|maitrise\s+de|connaissance\s+de|experience\s+(?:avec|en)|capacite\s+a|diplome\s+en|bilingue|courant\s+en)\b/i;
const PREFERRED_CUE_RE = /\b(?:preferred|nice[\s-]?to[\s-]?have|good[\s-]?to[\s-]?have|bonus|desirable|a\s+plus|asset|advantage|ideally|souhaite(?:e|es|s)?|atout|apprecie(?:e|es|s)?|un\s+plus|serait\s+un\s+plus|optionnel(?:le)?s?)\b/i;

function matchSectionLabel(text) {
  for (const [label, pattern] of SECTION_PATTERNS) {
    if (pattern.test(text)) return label;
  }
  return null;
}

const SECTION_SEARCH_PATTERNS = SECTION_PATTERNS.map(([label, pattern]) => {
  let source = pattern.source;
  if (source.startsWith("^")) source = source.slice(1);
  if (source.endsWith("$")) source = source.slice(0, -1);
  return [label, new RegExp(source, pattern.flags)];
});

function matchInlineLabel(text) {
  for (const [label, pattern] of SECTION_SEARCH_PATTERNS) {
    if (pattern.test(text)) return label;
  }
  return null;
}

function cueBucket(lineNorm) {
  if (PREFERRED_CUE_RE.test(lineNorm)) return "preferred";
  if (REQUIRED_CUE_RE.test(lineNorm)) return "required";
  return null;
}

const SENTENCE_SPLIT_RE = /[.!?]\s+(?=[A-Z0-9])/g;

function iterLineParts(line) {
  const parts = [];
  let last = 0;
  let m;
  SENTENCE_SPLIT_RE.lastIndex = 0;
  while ((m = SENTENCE_SPLIT_RE.exec(line)) !== null) {
    parts.push(line.slice(last, m.index + 1).trim());
    last = m.index + m[0].length;
  }
  parts.push(line.slice(last).trim());
  const filtered = parts.filter(Boolean);
  if (filtered.length <= 1 || filtered.some(part => part.length < 12)) {
    return [line];
  }
  return filtered;
}

const SUBHEADING_SMALL_WORDS = new Set([
  "and", "or", "of", "the", "for", "to", "in", "on", "with", "&",
]);

function looksLikeSubheading(line) {
  if (line.split(/\s+/).length > 6 || ".!?;,".includes(line[line.length - 1])) {
    return false;
  }
  if (/\d/.test(line)) return false;
  const words = line.match(/[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*/g) || [];
  if (words.length < 2) return false;
  const significant = words.filter(word => !SUBHEADING_SMALL_WORDS.has(word.toLowerCase()));
  return significant.length > 0 &&
    significant.every(word => word[0] === word[0].toUpperCase());
}

function matchHeader(line) {
  const candidate = line.trim().replace(/[\s:：]+$/, "");
  if (!candidate) return null;
  if (candidate.split(/\s+/).length > 8) return null;
  if (/\d/.test(candidate)) return null;
  if (/[.!?;,]/.test(candidate.slice(-1))) return null;
  return matchSectionLabel(candidate);
}

/* ---------------- term mining ---------------- */

const MAX_NGRAM = 3;
const BUCKET_CAPS = { required: 14, preferred: 6, keywords: 10 };
const BUCKET_WEIGHTS = { required: 3.0, preferred: 2.0, keywords: 1.0 };
const PROPER_BONUS = 2.0;
const LENGTH_BONUS = 0.15;
const EARLY_BONUS = 1.5;

const MINING_STOPWORDS = new Set([
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
]);

const GENERIC_WORDS = new Set([
  "job", "jobs", "role", "roles", "position", "positions", "posting",
  "postings", "opportunity", "opportunities", "career", "careers",
  "company", "companies", "employer", "workplace", "office", "location",
  "locations", "salary", "pay", "compensation", "benefit", "benefits",
  "perk", "perks", "vacation", "pension", "insurance", "equity",
  "stock", "visa", "sponsorship", "relocation", "interview",
  "interviews", "application", "applications", "apply", "applicant",
  "applicants", "candidate", "candidates", "resume", "resumes", "cv",
  "hiring", "recruitment", "recruiter", "recruiters", "team", "teams",
  "teammate", "teammates", "group", "groups", "environment", "environments", "culture",
  "values", "mission", "vision", "people", "person", "daily", "time",
  "full", "part", "schedule", "schedules", "weekend", "weekends",
  "hour", "hours", "day", "days", "year", "years", "annual",
  "quarterly", "bonus", "certification", "certifications",
  "certificate", "degree", "diploma", "bachelor", "bachelors",
  "master", "masters", "phd", "school", "university", "college",
  "academy", "experience", "experiences", "skill", "skills",
  "knowledge", "abilities", "ability", "strong", "excellent", "good",
  "great", "solid", "proven", "including", "include", "includes",
  "various", "similar", "relevant", "related", "continuous", "following",
  "preferred", "required", "considered", "responsibilities",
  "responsibility", "requirement", "requirements", "qualification",
  "qualifications", "policy", "policies", "task", "tasks", "duty",
  "duties", "activities", "initiatives", "looking", "join", "help",
  "new", "well", "across",
  "within", "please", "contact", "check", "learn", "life", "us",
  "equal", "diversity", "inclusion", "accommodation", "request",
  "requests", "tool", "tools", "platform", "platforms", "solution",
  "solutions", "work", "working", "works", "worked", "based", "high",
  "level", "levels", "plus", "success", "successful", "growth",
  "training", "programs", "service", "services",
  "system", "systems", "software", "application", "applications",
  "business", "testing",
  "network", "networks", "user", "users", "product", "security",
  "project", "projects", "process", "processes", "technical",
  "understanding",
  "nice", "ideally", "asset", "assets", "advantage", "advantages",
  "alert", "alerts", "incident", "incidents", "long", "view",
  "finding", "findings", "risk", "risks",
  "client", "clients", "customer", "customers", "vendor", "vendors",
  "third-party", "linkedin",
  "instagram", "facebook", "twitter", "youtube", "tiktok",
  "north", "south", "east", "west", "northeast", "northwest",
  "southeast", "southwest", "america", "canada", "europe", "online",
  "senior", "junior",
  "support", "respond", "escalate", "monitor", "complete", "perform",
  "participate", "ensure", "maintain", "provide", "assist", "handle",
  "review", "reviews", "identify", "coordinate", "friendly",
  "operational", "insertion",
  "poste", "postes", "emploi", "metier", "entreprise", "societe",
  "equipe", "equipes", "lieu", "salaire", "remuneration", "avantage",
  "avantages", "conges", "mutuelle", "entretien", "candidat",
  "candidats", "candidature", "recrutement", "recruteur", "recruteurs",
  "competence", "competences", "connaissance", "connaissances",
  "capacite", "aptitude", "taches", "responsabilites", "horaires",
  "quart", "quarts", "jour", "jours", "annee", "annees", "ans",
  "diplome", "bac", "licence", "formation", "travail", "travailler",
  "forte", "bon", "bonne", "compris", "gestion", "informatique",
  "systemes", "nouveaux", "comprehension",
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
]);

const EDGE_FILLER = new Set([
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
]);

const MINING_WORD_RE = /[a-z0-9]+(?:[.#'/&+-][a-z0-9]+)*/g;

const LANGUAGE_WORDS = new Set([
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
]);

function isLanguageTerm(term) {
  const tokens = [];
  for (const token of term) {
    for (const part of token.split("/")) {
      if (part) tokens.push(part);
    }
  }
  return tokens.length > 0 && tokens.every(token => LANGUAGE_WORDS.has(token));
}

const LOCATION_LINE_RE = /\b(?:based\s+in|located\s+in|location|relocat(?:e|ion)|commut(?:e|ing)|address|city|province|state|country)\b/i;
const CITY_LINE_RE = /^\s*[A-Z][\w .'-]+,\s*(?:[A-Z]{2}|[A-Z][\w .'-]+)(?:\s*\|.*)?\s*$/;
const SALARY_RE = /(?:[$€£]\s?\d|\b\d[\d,.]*\s*(?:k|per\s+(?:hour|year|annum)|\/h|\/yr)\b)/i;
const CULTURE_RE = /\b(?:equal\s+opportunity|diversity|inclusion|accommodation|why\s+work|perks?|vacation|pension|insurance|equity|stock\s+options?|relocation|visa\s+sponsorship)\b/i;
const CONTACT_RE = /(?:https?:\/\/|www\.|@|linkedin\.com|github\.com)/i;

function isNonRequirementLine(text) {
  if (SALARY_RE.test(text) || CULTURE_RE.test(text)) return true;
  if (CONTACT_RE.test(text)) return true;
  if (CITY_LINE_RE.test(text.trim())) return true;
  if (LOCATION_LINE_RE.test(text) && text.split(/\s+/).length <= 30) return true;
  return false;
}

function miningTokens(text) {
  return (normalizeText(text).replace(/'/g, " ").match(MINING_WORD_RE) || [])
    .filter(t => !MINING_STOPWORDS.has(t));
}

function contentRuns(text) {
  const norm = normalizeText(text).replace(/'/g, " ");
  const runs = [];
  let run = [];
  let prevEnd = null;
  const re = /[a-z0-9]+(?:[.#/&+-][a-z0-9]+)*/g;
  let m;
  while ((m = re.exec(norm)) !== null) {
    const token = m[0];
    const separated =
      prevEnd !== null && norm.slice(prevEnd, m.index).trim() !== "";
    if (MINING_STOPWORDS.has(token) || token.length < 2 || /^\d+$/.test(token)) {
      if (run.length) { runs.push(run); run = []; }
    } else if (separated) {
      if (run.length) runs.push(run);
      run = [token];
    } else {
      run.push(token);
    }
    prevEnd = m.index + token.length;
  }
  if (run.length) runs.push(run);
  return runs;
}

function properWords(text) {
  const caps = Object.create(null);
  const total = Object.create(null);
  for (const line of text.split("\n")) {
    const words = line.match(/[A-Za-z0-9][A-Za-z0-9'#./&+-]*/g) || [];
    const inShortRun = new Array(words.length).fill(false);
    let i = 1;
    while (i < words.length) {
      if (/[A-Z]/.test(words[i][0])) {
        let j = i;
        while (j < words.length && /[A-Z]/.test(words[j][0])) j++;
        if (j - i <= 2) {
          for (let k = i; k < j; k++) inShortRun[k] = true;
        }
        i = j;
      } else {
        i++;
      }
    }
    words.forEach((word, idx) => {
      const low = word.toLowerCase();
      total[low] = (total[low] || 0) + 1;
      if (inShortRun[idx] || (idx === 0 && word.length <= 6 && word === word.toUpperCase())) {
        caps[low] = (caps[low] || 0) + 1;
      }
    });
  }
  const proper = new Set();
  for (const word in total) {
    if ((caps[word] || 0) / total[word] >= 0.6 && /[A-Za-z]/.test(word)) {
      proper.add(word);
    }
  }
  return proper;
}

function stripEdges(term) {
  let start = 0;
  let end = term.length;
  while (start < end && EDGE_FILLER.has(term[start])) start++;
  while (end > start && EDGE_FILLER.has(term[end - 1])) end--;
  if (start >= end) return null;
  return term.slice(start, end);
}

function containsTokens(big, small) {
  const n = small.length;
  for (let i = 0; i + n <= big.length; i++) {
    let equal = true;
    for (let k = 0; k < n; k++) {
      if (big[i + k] !== small[k]) { equal = false; break; }
    }
    if (equal) return true;
  }
  return false;
}

function buildVariationIndex(taxonomy) {
  const index = [];
  for (const skillsDict of Object.values(taxonomy)) {
    for (const [skill, variations] of Object.entries(skillsDict)) {
      for (const variation of variations) {
        const normalized = normalizeText(variation).trim();
        if (!normalized) continue;
        if (!/[a-z0-9]/.test(normalized[0]) || !/[a-z0-9]/.test(normalized[normalized.length - 1])) {
          continue;
        }
        const tokens = miningTokens(variation);
        if (tokens.length) index.push([tokens, skill]);
      }
    }
  }
  return index;
}

function canonicalizeTerm(term, index, proper) {
  const properSet = proper || new Set();
  let best = null;
  let bestRank = 0;
  for (const [variation, skill] of index) {
    let rank = 0;
    if (term.length === variation.length && term.every((t, i) => t === variation[i])) {
      rank = 3;
    } else if (variation.length >= 2 && containsTokens(term, variation)) {
      rank = 2;
    } else if (
      variation.length === 1 && term.length > 1 &&
      properSet.has(variation[0]) && containsTokens(term, variation)
    ) {
      rank = 2;
    } else if (
      term.length === 1 && variation.length >= 2 &&
      !GENERIC_WORDS.has(term[0]) && containsTokens(variation, term)
    ) {
      rank = 1;
    }
    if (rank > bestRank) {
      best = skill;
      bestRank = rank;
    }
  }
  return best;
}

function compareTokenArrays(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return a.length - b.length;
}

function mineTerms(records, existing) {
  const content = records.map(r => r.text).join("\n");
  const proper = properWords(content);
  const index = buildVariationIndex(state.taxonomy);

  const totalLines = Math.max(records.length, 1);
  const earlyCutoff = Math.max(8, Math.floor(totalLines * 0.25));

  const sentenceLine = new Set(
    records
      .filter(r =>
        ".!?".includes((r.text.match(/.$/) || [""])[0]) &&
        r.text.split(/\s+/).length > 15)
      .map(r => r.idx)
  );

  const freq = new Map();
  const bulletIn = { required: new Set(), preferred: new Set() };
  const sectionOf = new Map();

  for (const { bucket, text, isBullet, idx } of records) {
    if (isNonRequirementLine(text)) continue;
    const seenInLine = new Set();
    const vouched =
      isBullet &&
      (bucket === "required" || bucket === "preferred") &&
      text.split(/\s+/).length <= 12;
    for (const run of contentRuns(text)) {
      for (let start = 0; start < run.length; start++) {
        for (let n = 1; n <= MAX_NGRAM; n++) {
          if (start + n > run.length) break;
          const term = stripEdges(run.slice(start, start + n));
          if (term === null) continue;
          if (term.length === 1 && n > 1) continue;
          const key = term.join(" ");
          if (seenInLine.has(key)) continue;
          seenInLine.add(key);
          const entry = freq.get(key);
          if (entry) {
            entry.count += 1;
            if (idx < entry.firstIdx) { entry.firstIdx = idx; entry.firstBucket = bucket; }
          } else {
            freq.set(key, { term, count: 1, firstIdx: idx, firstBucket: bucket });
          }
          if (vouched) bulletIn[bucket].add(key);
          if ((bucket === "required" || bucket === "preferred") && !sectionOf.has(key)) {
            sectionOf.set(key, bucket);
          }
        }
      }
    }
  }

  const candidates = [];
  const existingTokens = [...existing]
    .filter(name => name && name.trim())
    .map(name => miningTokens(name));
  for (const { term, count, firstIdx, firstBucket } of freq.values()) {
    if (term.some(t => t.length < 2 || /^\d+$/.test(t))) continue;
    const informative = term.filter(t => !GENERIC_WORDS.has(t));
    if (!informative.length) continue;
    if (isLanguageTerm(informative)) continue;
    if (existingTokens.some(tokens =>
      tokens.length > term.length && containsTokens(tokens, term))) continue;
    const informativeProper = informative.filter(t => proper.has(t));
    const isProper = informativeProper.length > 0;
    const properCount = informativeProper.length;
    const early = firstBucket == null && firstIdx < earlyCutoff;
    const bullet = bulletIn.required.has(term.join(" ")) ||
      bulletIn.preferred.has(term.join(" "));

    if (term.length === 1) {
      if (GENERIC_WORDS.has(term[0])) continue;
      if (count < 3 && !proper.has(term[0])) continue;
    } else {
      if (informative.length < 2 && !informativeProper.length) continue;
      if (!(count >= 2 || isProper || bullet || early)) continue;
      if (term.length > 2 &&
          !(count >= 2 || properCount >= 2 || bullet || early)) continue;
    }

    const bucket = sectionOf.get(term.join(" ")) || "keywords";
    if (bucket === "keywords" && sentenceLine.has(firstIdx)) continue;

    const weight = BUCKET_WEIGHTS[bucket];
    const score =
      count * weight *
      (isProper ? PROPER_BONUS : 1.0) *
      (1.0 + LENGTH_BONUS * (term.length - 1)) *
      (early ? EARLY_BONUS : 1.0) *
      (sentenceLine.has(firstIdx) ? 0.5 : 1.0);
    candidates.push({ score, term, bucket });
  }

  candidates.sort((a, b) => {
    const aUni = a.term.length === 1 && proper.has(a.term[0]) ? 0 : 1;
    const bUni = b.term.length === 1 && proper.has(b.term[0]) ? 0 : 1;
    if (aUni !== bUni) return aUni - bUni;
    if (b.score !== a.score) return b.score - a.score;
    return compareTokenArrays(a.term, b.term);
  });

  const picked = { required: [], preferred: [], keywords: [] };
  const claimed = { required: new Set(), preferred: new Set(), keywords: new Set() };
  for (const { term, bucket } of candidates) {
    if (picked[bucket].length >= BUCKET_CAPS[bucket]) continue;
    const display = term.join(" ");
    const canonical = canonicalizeTerm(term, index, proper);
    if (canonical && existing.has(canonical)) continue;
    if (existing.has(display)) continue;
    const informative = term.filter(t => !GENERIC_WORDS.has(t));
    const claimedCount = informative.filter(t => claimed[bucket].has(t)).length;
    const properClaimed = informative.some(t => proper.has(t) && claimed[bucket].has(t));
    if (!informative.length || properClaimed || claimedCount >= 2) continue;
    picked[bucket].push([term, canonical]);
    for (const t of informative) claimed[bucket].add(t);
  }
  return picked;
}

function tokenPattern(token) {
  if (token.endsWith("ing") && token.length >= 6) {
    let stem = token.slice(0, -3);
    if (stem.length >= 2 && stem[stem.length - 1] === stem[stem.length - 2]) {
      stem = stem.slice(0, -1);
      return escapeRe(stem) + "(?:" + escapeRe(stem[stem.length - 1]) + ")?" +
        "(?:ing|ed|er|ers|es|s|e)?";
    }
    return escapeRe(stem) + "(?:ing|ed|er|ers|es|s|e)?";
  }
  if (token.endsWith("ed") && token.length >= 5) {
    const stem = token.slice(0, -2);
    return escapeRe(stem) + "(?:ed|ing|er|ers|es|s|e)?";
  }
  return escapeRe(token);
}

function matchTermsDetailed(text, terms) {
  const found = {};
  if (!terms || !terms.size) return found;
  const norm = normalizeText(text);
  for (const term of terms) {
    const parts = term.split(" ").map(t => tokenPattern(normalizeText(t)));
    const re = new RegExp("(^|[^a-z0-9])" + parts.join("[^a-z0-9]+") + "(?![a-z0-9])", "g");
    let m;
    while ((m = re.exec(norm)) !== null) {
      const start = m.index + m[1].length;
      if (isNegated(norm, start)) continue;
      found[term] = evidenceSnippet(norm, start, m.index + m[0].length);
      break;
    }
  }
  return found;
}

function matchTerms(text, terms) {
  return new Set(Object.keys(matchTermsDetailed(text, terms)));
}

/* ---------------- structured CV fields --------------------------------- */

const FIELD_SECTION_HEADERS = new Set([
  "summary", "professional summary", "profile", "objective", "about",
  "about me", "contact", "contact details", "skills", "technical skills",
  "core skills", "key skills", "experience", "work experience",
  "professional experience", "employment", "employment history",
  "education", "educational background", "academic background",
  "certifications", "certificates", "licenses", "licences",
  "languages", "projects", "awards", "publications", "volunteer",
  "interests", "references", "resume", "cv", "curriculum vitae",
  "profil", "objectif", "competences", "competences techniques",
  "experiences", "experiences professionnelles", "formation", "etudes",
  "langues", "certificats", "projets", "distinctions",
]);

const FIELD_ROLE_WORDS = new Set([
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
  "gestionnaire", "directeur", "directrice", "consultante", "specialiste",
  "technicien", "technicienne", "administrateur", "administratrice",
  "coordonnateur", "coordonnatrice", "assistante", "infirmier",
  "infirmiere", "medecin", "comptable", "avocat", "avocate", "soudeur",
  "soudeuse", "electricien", "electricienne", "plombier", "mecanicien",
  "chauffeur", "secretaire", "superviseur", "stagiaire", "etudiant",
  "etudiante", "professeur", "chercheur", "chercheuse", "concepteur",
  "conceptrice", "redacteur", "redactrice", "recruteur", "recruteuse",
  "therapeute", "dentiste", "chirurgien", "caissier", "caissiere",
  "vendeur", "vendeuse",
]);

const FIELD_PARTICLES = new Set([
  "de", "da", "van", "von", "der", "la", "le", "del", "di", "bin", "al",
  "el", "dos", "das", "du", "des", "ter", "ten",
]);

const FIELD_INSTITUTION_WORDS = [
  "hospital", "university", "college", "school", "institute", "academy",
  "company", "corp", "corporation", "inc", "ltd", "llc", "gmbh", "sas",
  "sarl", "plc", "group", "agency", "clinic", "centre", "center",
  "hopital", "universite", "ecole", "institut", "entreprise", "societe",
];

const FIELD_EMAIL_RE = /(^|[^\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])/;
const FIELD_PHONE_SCAN_RE = /(^|[^\w])((?:\+\d{1,3}[\s.\-]?)?(?:\(\d{1,4}\)[\s.\-]?|\d{1,4}[\s.\-]){1,5}\d{2,4})(?![\w])/g;
const FIELD_LINKEDIN_RE = /(?:https?:\/\/)?(?:www\.)?linkedin\.com\/(?:in|pub)\/[^\s|,;<>"']+/i;
const FIELD_GITHUB_RE = /(?:https?:\/\/)?(?:www\.)?github\.com\/[^\s|,;<>"']+/i;
const FIELD_URL_RE = /(?:https?:\/\/|www\.)[^\s|,;<>"']+/gi;

const FIELD_NAME_LABEL_RE = /^(?:full\s+name|name|nom(?:\s+complet)?|pr[ée]nom\s+et\s+nom)\s*[:\-]\s*(.+)$/i;
const FIELD_HEADLINE_LABEL_RE = /^(?:headline|title|job\s+title|current\s+(?:title|role)|poste|titre|fonction|intitul[ée]\s+du\s+poste)\s*[:\-]\s*(.+)$/i;
const FIELD_LOCATION_LABEL_RE = /^(?:location|based\s+in|address|city|lieu|ville|adresse)\s*[:\-]\s*(.+)$/i;
const FIELD_EDUCATION_HEADER_RE = /^(?:education|educational\s+background|academic\s+background|academic\s+qualifications?|qualifications?\s+academiques?|formation|etudes|parcours\s+academique)\s*:?$/i;
const FIELD_EDUCATION_LABEL_RE = /^(?:education|educational\s+background|academic\s+background|academic\s+qualifications?|formation|etudes|parcours\s+academique)\s*[:\-]\s*(.+)$/i;
const FIELD_CERT_HEADER_RE = /^(?:certifications?|certificates?|licen[cs]es?|credentials?|accreditations?|certificats?|habilitations?|licences?\s+professionnelles?)\s*:?$/i;
const FIELD_CERT_LABEL_RE = /^(?:certifications?|certificates?|licen[cs]es?|credentials?|accreditations?|certificats?|habilitations?)\s*[:\-]\s*(.+)$/i;
const FIELD_LANGUAGE_HEADER_RE = /^(?:languages?|language\s+skills?|langues?|competences?\s+linguistiques?)\s*:?$/i;
const FIELD_LANGUAGE_LABEL_RE = /^(?:languages?|language\s+skills?|langues?|competences?\s+linguistiques?)\s*[:\-]\s*(.+)$/i;
const FIELD_OTHER_SECTION_RE = /^(?:summary|profile|objective|about|skills|technical\s+skills|core\s+skills|key\s+skills|experience|work\s+experience|professional\s+experience|employment|projects?|awards?|publications?|volunteer|interests?|references?|resume|cv|profil|objectif|competences|experiences?|projets?|distinctions?)\s*:?$/i;
const FIELD_CITY_COUNTRY_RE = /^([A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ .'’\-]{1,40}),\s*([A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ .'’\-]{1,40})$/;
const FIELD_DEGREE_RE = /\b(?:bachelor(?:'s)?|bachelors|master(?:'s)?|masters|ph\.?d|doctorate|doctoral|associate(?:'s)?|diploma|licence|baccalaureat|b\.?\s?sc|m\.?\s?sc|b\.?\s?a\.?|m\.?\s?a\.?|mba|b\.?\s?tech|m\.?\s?tech|llb|llm|md|dds|pharmd|dut|bts|dep|aep|asp|cegep|ingenieur|engineer(?:'s)?\s+degree)\b/i;
const FIELD_HIGH_SCHOOL_RE = /\b(?:high\s+school|secondary\s+school|baccalaureat|bac)\b/i;
const FIELD_ASSOCIATE_RE = /\b(?:associate(?:'s)?|dut|bts|dep|aep|asp|diploma)\b/i;
const FIELD_BACHELOR_RE = /\b(?:bachelor(?:'s)?|bachelors|b\.?\s?sc|b\.?\s?a\.?|b\.?\s?tech|llb|licence|bac\+3)\b/i;
const FIELD_MASTER_RE = /\b(?:master(?:'s)?|masters|mba|m\.?\s?sc|m\.?\s?a\.?|m\.?\s?tech|llm|master\s+2|bac\+5)\b/i;
const FIELD_PHD_RE = /\b(?:ph\.?d|doctorate|doctoral|doctorat)\b/i;
const FIELD_CERT_WORD_RE = /\b(?:certified|certification|certificate|licensed|licence|license|registration|registered)\b/i;
const FIELD_CERT_ACRONYM_RE = /\b(?:bls|acls|pals|cpr|first\s+aid|cpa|cfa|cma|pmp|prince2|capm|cissp|ccna|ccnp|security\+|comptia|itil(?:v\d)?|oscp|ceh|osha|six\s+sigma|lean\s+six\s+sigma|cdl|servsafe|food\s+safety|shrm|phr|rn|lpn|cna|md|dds|pharmd|aws\s+certified|azure\s+certified|google\s+cloud\s+certified)\b/i;
const FIELD_LANGUAGE_CONTEXT_RE = /\b(?:languages?|langues?|fluent|bilingual|trilingual|multilingual|native|mother\s+tongue|courant|bilingue|trilingue|multilingue|proficiency|proficient|intermediate|advanced|beginner|basic|professional\s+working|maitrise|niveau)\b/i;

const FIELD_LANGUAGES = {
  english: "English", anglais: "English",
  french: "French", francais: "French",
  spanish: "Spanish", espagnol: "Spanish",
  german: "German", allemand: "German",
  arabic: "Arabic", arabe: "Arabic",
  mandarin: "Mandarin", cantonese: "Cantonese", cantonais: "Cantonese",
  portuguese: "Portuguese", portugais: "Portuguese",
  italian: "Italian", italien: "Italian",
  russian: "Russian", russe: "Russian",
  japanese: "Japanese", japonais: "Japanese",
  korean: "Korean", coreen: "Korean",
  hindi: "Hindi", urdu: "Urdu", ourdou: "Urdu",
  turkish: "Turkish", turc: "Turkish",
  dutch: "Dutch", neerlandais: "Dutch",
  polish: "Polish", polonais: "Polish",
  vietnamese: "Vietnamese", vietnamien: "Vietnamese",
  tagalog: "Tagalog", farsi: "Farsi", persian: "Persian",
  persan: "Persian", hebrew: "Hebrew", hebreu: "Hebrew",
  greek: "Greek", grec: "Greek",
  swedish: "Swedish", suedois: "Swedish",
  norwegian: "Norwegian", norvegien: "Norwegian",
  danish: "Danish", danois: "Danish",
  finnish: "Finnish", finnois: "Finnish",
  czech: "Czech", tcheque: "Czech",
  romanian: "Romanian", roumain: "Romanian",
  hungarian: "Hungarian", hongrois: "Hungarian",
  ukrainian: "Ukrainian", ukrainien: "Ukrainian",
  bengali: "Bengali", tamil: "Tamil", tamoul: "Tamil",
  malay: "Malay", malais: "Malay",
  indonesian: "Indonesian", indonesien: "Indonesian",
  thai: "Thai", swahili: "Swahili", amharic: "Amharic",
  somali: "Somali", yoruba: "Yoruba", igbo: "Igbo",
  hausa: "Hausa", zulu: "Zulu", afrikaans: "Afrikaans",
};

const FIELD_LEVEL_RANK = {
  "": 0, "High school": 1, "Associate/Diploma": 2,
  "Bachelor": 3, "Master": 4, "PhD": 5,
};

function stripFieldMarkdown(line) {
  return line.trim()
    .replace(/^\s{0,3}#{1,6}\s+/, "")
    .replace(/(\*\*|__)(.+?)\1/g, "$2");
}

function cleanFieldLine(line) {
  return stripFieldMarkdown(line)
    .replace(BULLET_PREFIX_RE, "")
    .replace(/^[*_`]+|[*_`]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanFieldValue(value) {
  return cleanFieldLine(value).replace(/^[\s\-–—|,;]+|[\s\-–—|,;]+$/g, "");
}

function dedupeFieldItems(items) {
  const seen = new Set();
  const out = [];
  for (const item of items) {
    const key = normalizeText(item).trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

function looksLikeFieldName(line) {
  const value = cleanFieldLine(line);
  if (!value || value.length > 70) return false;
  if (FIELD_EMAIL_RE.test(value)) return false;
  if (/\d/.test(value)) return false;
  if (/[|@/\\]/.test(value)) return false;
  if (FIELD_SECTION_HEADERS.has(normalizeText(value).replace(/[ :]+$/g, ""))) return false;
  const base = value.split(",")[0].trim();
  const words = base.match(/[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.\-]*/g) || [];
  if (words.length < 2 || words.length > 5) return false;
  if (words.some(word => FIELD_ROLE_WORDS.has(normalizeText(word)))) return false;
  for (const word of words) {
    if (FIELD_PARTICLES.has(normalizeText(word))) continue;
    if (!/^[A-ZÀ-ÖØ-Þ]/.test(word)) return false;
  }
  return true;
}

function normaliseFieldName(raw) {
  let value = cleanFieldValue(raw);
  if (!value) return "";
  if (value.includes(",")) {
    const parts = value.split(",").map(part => part.trim());
    const left = parts[0];
    const right = parts.slice(1).join(", ");
    const leftName = looksLikeFieldName(left);
    const rightName = looksLikeFieldName(right);
    if (leftName && !rightName) value = left;
    else if (rightName && !leftName) value = right;
    else if (leftName && rightName) value = `${right} ${left}`;
    else if (left.split(/\s+/).length === 1 && right.split(/\s+/).length === 1) value = `${right} ${left}`;
    else value = left;
  }
  value = value.replace(/\s+/g, " ").replace(/^[\s\-–—,;]+|[\s\-–—,;]+$/g, "");
  if (value === value.toUpperCase() || value === value.toLowerCase()) {
    value = value.toLowerCase().replace(/(^|[\s\-'])([a-zà-öø-ÿ])/g,
      (m, prefix, letter) => prefix + letter.toUpperCase());
  }
  return value;
}

function extractFieldName(text) {
  const lines = text.split("\n").map(line => line.trim()).filter(Boolean);
  for (const line of lines.slice(0, 12)) {
    const match = cleanFieldLine(line).match(FIELD_NAME_LABEL_RE);
    if (match) {
      const name = normaliseFieldName(match[1]);
      if (name) return name;
    }
  }
  for (const line of lines.slice(0, 8)) {
    if (looksLikeFieldName(line)) return normaliseFieldName(line);
  }
  return "";
}

function extractFieldEmail(text) {
  const match = text.match(FIELD_EMAIL_RE);
  return match ? match[2].trim().toLowerCase() : "";
}

function extractFieldPhone(text) {
  FIELD_PHONE_SCAN_RE.lastIndex = 0;
  let match;
  while ((match = FIELD_PHONE_SCAN_RE.exec(text)) !== null) {
    const raw = match[2].replace(/\s+/g, " ").trim();
    const digits = raw.replace(/\D/g, "");
    if (digits.length < 7 || digits.length > 15) continue;
    if (/(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}/.test(raw)) continue;
    if (/\b(?:19|20)\d{2}\b/.test(raw)) continue;
    const around = text.slice(Math.max(0, match.index - 30), match.index + match[0].length + 30).toLowerCase();
    if (/\b(?:present|current|now|today|aujourd.?hui)\b/.test(around)) continue;
    return raw;
  }
  return "";
}

function extractFieldLinks(text) {
  const linkedinMatch = text.match(FIELD_LINKEDIN_RE);
  const githubMatch = text.match(FIELD_GITHUB_RE);
  const linkedin = linkedinMatch ? linkedinMatch[0].replace(/[.,;]+$/, "") : "";
  const github = githubMatch ? githubMatch[0].replace(/[.,;]+$/, "") : "";
  let website = "";
  FIELD_URL_RE.lastIndex = 0;
  let match;
  while ((match = FIELD_URL_RE.exec(text)) !== null) {
    const url = match[0].replace(/[.,;]+$/, "");
    const low = url.toLowerCase();
    if (low.includes("linkedin.com") || low.includes("github.com")) continue;
    if (FIELD_EMAIL_RE.test(url)) continue;
    website = url;
    break;
  }
  return { linkedin, github, website };
}

function looksLikeFieldRole(line) {
  const value = cleanFieldLine(line);
  if (!value || value.length > 100) return false;
  if (FIELD_EMAIL_RE.test(value)) return false;
  if (/https?:\/\/|www\./i.test(value)) return false;
  if (/[|@/\\]/.test(value)) return false;
  if (FIELD_SECTION_HEADERS.has(normalizeText(value).replace(/[ :]+$/g, ""))) return false;
  if (/[.!?]$/.test(value)) return false;
  const words = value.match(/[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.\-]*/g) || [];
  if (!words.length || words.length > 10) return false;
  return words.some(word => FIELD_ROLE_WORDS.has(normalizeText(word)));
}

function extractFieldHeadline(text, name) {
  const lines = text.split("\n").map(line => line.trim()).filter(Boolean);
  for (const line of lines.slice(0, 12)) {
    const match = cleanFieldLine(line).match(FIELD_HEADLINE_LABEL_RE);
    if (match) return cleanFieldValue(match[1]);
  }
  for (const raw of lines.slice(0, 10)) {
    const cleaned = cleanFieldLine(raw);
    if (!cleaned) continue;
    if (name && cleaned.toLowerCase() === name.toLowerCase()) continue;
    if (BULLET_PREFIX_RE.test(stripFieldMarkdown(raw))) continue;
    const norm = normalizeText(cleaned).replace(/[ :]+$/g, "");
    if (FIELD_SECTION_HEADERS.has(norm)) break;
    for (const part of cleaned.split(/[|•·/]/)) {
      const candidate = cleanFieldValue(part);
      if (looksLikeFieldRole(candidate)) return candidate;
    }
  }
  return "";
}

function looksLikeFieldLocation(value) {
  value = cleanFieldValue(value);
  if (!value || value.length > 80) return false;
  if (FIELD_EMAIL_RE.test(value)) return false;
  if (/https?:\/\/|www\./i.test(value)) return false;
  if (looksLikeFieldName(value)) return false;
  if (/\d/.test(value)) return false;
  if (FIELD_DEGREE_RE.test(value) || FIELD_CERT_WORD_RE.test(value)) return false;
  const norm = normalizeText(value);
  if (FIELD_INSTITUTION_WORDS.some(word => norm.includes(word))) return false;
  if (norm.split(/\s+/).some(word => FIELD_ROLE_WORDS.has(word))) return false;
  return FIELD_CITY_COUNTRY_RE.test(value);
}

function extractFieldLocation(text) {
  const lines = text.split("\n").map(line => line.trim()).filter(Boolean);
  for (const line of lines.slice(0, 15)) {
    const match = cleanFieldLine(line).match(FIELD_LOCATION_LABEL_RE);
    if (match) return cleanFieldValue(match[1]);
  }
  for (const line of lines.slice(0, 10)) {
    if (!(FIELD_EMAIL_RE.test(line) || /\d/.test(line) || /https?:\/\/|www\./i.test(line))) continue;
    for (const part of line.split(/[|•·]/)) {
      if (looksLikeFieldLocation(part)) return cleanFieldValue(part);
    }
  }
  for (const line of lines.slice(0, 6)) {
    if (looksLikeFieldLocation(line)) return cleanFieldValue(line);
  }
  return "";
}

function collectFieldSection(lines, headerRe) {
  const collected = [];
  let inside = false;
  for (const raw of lines) {
    const line = cleanFieldLine(raw);
    if (!line) continue;
    const norm = normalizeText(line).replace(/[ :]+$/g, "");
    if (headerRe.test(norm)) { inside = true; continue; }
    if (!inside) continue;
    if (FIELD_OTHER_SECTION_RE.test(norm) ||
        FIELD_EDUCATION_HEADER_RE.test(norm) ||
        FIELD_CERT_HEADER_RE.test(norm) ||
        FIELD_LANGUAGE_HEADER_RE.test(norm)) break;
    if (line.length <= 200) collected.push(line);
    if (collected.length >= 8) break;
  }
  return collected;
}

function fieldDegreeLevel(text) {
  const norm = normalizeText(text);
  if (FIELD_PHD_RE.test(norm)) return "PhD";
  if (FIELD_MASTER_RE.test(norm)) return "Master";
  if (FIELD_BACHELOR_RE.test(norm)) return "Bachelor";
  if (FIELD_ASSOCIATE_RE.test(norm)) return "Associate/Diploma";
  if (FIELD_HIGH_SCHOOL_RE.test(norm)) return "High school";
  return "";
}

function extractFieldEducation(text) {
  const lines = text.split("\n").map(line => line.trim()).filter(Boolean);
  let collected = [];
  for (const line of lines) {
    const match = cleanFieldLine(line).match(FIELD_EDUCATION_LABEL_RE);
    if (match) {
      const value = cleanFieldValue(match[1]);
      if (value) collected.push(value);
    }
  }
  collected = collected.concat(collectFieldSection(lines, FIELD_EDUCATION_HEADER_RE));
  if (!collected.length) {
    for (const line of lines) {
      const cleaned = cleanFieldLine(line);
      if (!cleaned || cleaned.length > 200) continue;
      if (FIELD_DEGREE_RE.test(cleaned) && !FIELD_CERT_WORD_RE.test(cleaned)) {
        if (/\b(?:19|20)\d{2}\b/.test(cleaned) ||
            /university|college|institute|school|universite|ecole|institut|cegep|centre de formation/i.test(cleaned)) {
          collected.push(cleaned);
        }
      }
    }
  }
  collected = dedupeFieldItems(collected).slice(0, 4);
  let level = "";
  for (const item of collected) {
    const candidate = fieldDegreeLevel(item);
    if ((FIELD_LEVEL_RANK[candidate] || 0) > (FIELD_LEVEL_RANK[level] || 0)) {
      level = candidate;
    }
  }
  return { level, education: collected };
}

function extractFieldCertifications(text) {
  const lines = text.split("\n").map(line => line.trim()).filter(Boolean);
  let collected = [];
  for (const line of lines) {
    const match = cleanFieldLine(line).match(FIELD_CERT_LABEL_RE);
    if (match) {
      const value = cleanFieldValue(match[1]);
      if (value) collected.push(value);
    }
  }
  collected = collected.concat(
    collectFieldSection(lines, FIELD_CERT_HEADER_RE).filter(line =>
      !(FIELD_EMAIL_RE.test(line) || /https?:\/\/|www\./i.test(line))
    )
  );
  if (!collected.length) {
    for (const line of lines) {
      const cleaned = cleanFieldLine(line);
      if (!cleaned || cleaned.length > 140) continue;
      if (FIELD_EMAIL_RE.test(cleaned) || /https?:\/\/|www\./i.test(cleaned)) continue;
      if (FIELD_CERT_WORD_RE.test(cleaned) ||
          (FIELD_CERT_ACRONYM_RE.test(cleaned) && cleaned.split(/\s+/).length <= 6)) {
        collected.push(cleaned);
      }
    }
  }
  return dedupeFieldItems(collected).slice(0, 6);
}

function fieldLanguageNamesIn(text) {
  const norm = normalizeText(text);
  const found = [];
  for (const [name, display] of Object.entries(FIELD_LANGUAGES)) {
    const re = new RegExp("(^|[^a-z0-9])" + escapeRe(name) + "(?![a-z0-9])");
    if (re.test(norm) && !found.includes(display)) found.push(display);
  }
  return found;
}

function extractFieldLanguages(text) {
  const lines = text.split("\n").map(line => line.trim()).filter(Boolean);
  let collected = [];
  for (const line of lines) {
    const match = cleanFieldLine(line).match(FIELD_LANGUAGE_LABEL_RE);
    if (!match) continue;
    const detail = cleanFieldValue(match[1]);
    const names = fieldLanguageNamesIn(detail);
    if (!names.length) continue;
    if (names.length === 1 && detail.length <= 60 &&
        /\(|fluent|native|courant|bilingue|intermediate|basic|advanced/i.test(detail)) {
      collected.push(detail);
    } else {
      collected = collected.concat(names);
    }
  }
  for (const line of collectFieldSection(lines, FIELD_LANGUAGE_HEADER_RE)) {
    const names = fieldLanguageNamesIn(line);
    if (!names.length) continue;
    const detail = cleanFieldLine(line);
    if (names.length === 1 && detail.length <= 60 &&
        /\(|fluent|native|courant|bilingue|intermediate|basic|advanced/i.test(detail)) {
      collected.push(detail);
    } else {
      collected = collected.concat(names);
    }
  }
  if (!collected.length) {
    for (const line of lines) {
      const cleaned = cleanFieldLine(line);
      if (!cleaned || cleaned.length > 160) continue;
      const names = fieldLanguageNamesIn(cleaned);
      if (!names.length) continue;
      if (FIELD_LANGUAGE_CONTEXT_RE.test(cleaned)) {
        if (names.length === 1 && cleaned.length <= 60) collected.push(cleaned);
        else collected = collected.concat(names);
      } else if (names.length >= 2 && cleaned.split(/\s+/).length <= 8) {
        collected = collected.concat(names);
      }
    }
  }
  return dedupeFieldItems(collected).slice(0, 8);
}

function extractFields(text) {
  const email = extractFieldEmail(text);
  const phone = extractFieldPhone(text);
  const links = extractFieldLinks(text);
  const name = extractFieldName(text);
  const headline = extractFieldHeadline(text, name);
  const location = extractFieldLocation(text);
  const education = extractFieldEducation(text);
  return {
    name,
    email,
    phone,
    location,
    headline,
    linkedin: links.linkedin,
    github: links.github,
    website: links.website,
    education_level: education.level,
    education: education.education,
    certifications: extractFieldCertifications(text),
    languages: extractFieldLanguages(text),
  };
}

function splitSections(jdText) {
  const sections = { required: [], preferred: [], experience: [], context: [] };
  const records = [];
  let current = null;
  let ordinal = 0;

  for (const rawLine of jdText.split("\n")) {
    let line = rawLine.trim();
    if (!line) continue;
    line = line.replace(/^#{1,6}\s+/, "").replace(/^[*_`]+|[*_`]+$/g, "").trim();
    if (!line) continue;

    const isBullet = BULLET_PREFIX_RE.test(line) || BULLET_CHARS.includes(line[0]);
    if (isBullet) line = line.replace(BULLET_PREFIX_RE, "").replace(/^[-*•·▪‣–—]+/, "").trim();
    if (!line) continue;

    for (const part of iterLineParts(line)) {
      const partNorm = normalizeText(part);
      if (!partNorm) continue;

      if (!isBullet && partNorm.includes(":")) {
        const idx = partNorm.indexOf(":");
        const left = partNorm.slice(0, idx).trim();
        const right = partNorm.slice(idx + 1).trim();
        const label = matchInlineLabel(left);
        if (label) {
          current = label;
          if (right) {
            sections[label].push(right);
            records.push({ bucket: label, text: right, isBullet: false, idx: ordinal++ });
          }
          continue;
        }
      }

      if (!isBullet) {
        const header = matchHeader(partNorm);
        if (header) {
          current = header;
          continue;
        }
        if (partNorm.endsWith(":") && partNorm.slice(0, -1).split(/\s+/).length <= 5) {
          current = null;
          continue;
        }
        if (looksLikeSubheading(part)) continue;
      }

      let bucket = current;
      if (bucket === null || bucket === "experience") {
        const cue = cueBucket(partNorm);
        if (cue) bucket = cue;
      } else if (bucket === "required") {
        const cue = cueBucket(partNorm);
        if (cue === "preferred") bucket = "preferred";
      } else if (bucket === "preferred") {
        const cue = cueBucket(partNorm);
        if (cue === "required") bucket = "required";
      }
      if (bucket) sections[bucket].push(part);
      else sections.context.push(part);
      records.push({ bucket, text: part, isBullet, idx: ordinal++ });
    }
  }
  return { sections, records };
}

function parseJd(jdText) {
  const { sections, records } = splitSections(jdText);
  let required = extractSkills(sections.required.join("\n"));
  const preferred = extractSkills(sections.preferred.join("\n"));
  for (const skill of required) preferred.delete(skill);

  const hasExplicitSections = sections.required.length > 0 || sections.preferred.length > 0;
  if (required.size === 0 && preferred.size === 0) {
    required = extractSkills(jdText);
  }

  const allMentioned = extractSkills(jdText);
  const keywords = new Set(
    [...allMentioned].filter(s => !required.has(s) && !preferred.has(s))
  );

  const minedTerms = new Set();
  const fallback = !hasExplicitSections;
  const existing = new Set([...required, ...preferred, ...keywords]);
  const mined = mineTerms(records, existing);
  const targets = { required, preferred, keywords };
  for (const bucketName of ["required", "preferred", "keywords"]) {
    const target = fallback && bucketName === "keywords" ? required : targets[bucketName];
    for (const [termTokens, canonical] of mined[bucketName]) {
      const name = canonical || termTokens.join(" ");
      if (canonical && existing.has(canonical)) continue;
      if (existing.has(name)) continue;
      target.add(name);
      existing.add(name);
      if (!canonical) minedTerms.add(name);
    }
  }

  const years = extractYears(jdText, "min");
  const warnings = [];
  const signalSize = required.size + preferred.size;
  if (!signalSize && !keywords.size) {
    warnings.push(
      "No skills could be extracted from this job description. Add a Required / Preferred section or import a custom taxonomy."
    );
  } else if (signalSize < MIN_SIGNAL_SKILLS) {
    warnings.push(
      `Only ${signalSize} required/preferred skill(s) were extracted. Review and edit them before ranking — scores will be brittle.`
    );
  }
  if (!hasExplicitSections) {
    warnings.push(
      "No Required/Preferred heading was detected. Every extracted skill was treated as required; reclassify preferred skills if needed."
    );
  }
  if (minedTerms.size && minedTerms.size >= signalSize) {
    warnings.push(
      "Most requirements came from phrases in the ad (not the skills taxonomy). Check they are real requirements, not duties or culture copy."
    );
  }
  return {
    required,
    preferred,
    keywords,
    minedTerms,
    years,
    hasExplicitSections,
    warnings,
  };
}

/* ---------------- scoring ------------------------------------------------ */

const WEIGHT_KEYS = ["required_skills", "preferred_skills", "experience", "keywords"];

function coverage(matched, target) {
  if (!target || target.size === 0) return 0;
  let hits = 0;
  for (const skill of target) if (matched.has(skill)) hits++;
  return hits / target.size;
}

function activeWeights(base, reqs, includeExperience = true) {
  const used = {
    required_skills: reqs.required && reqs.required.size > 0,
    preferred_skills: reqs.preferred && reqs.preferred.size > 0,
    keywords: reqs.keywords && reqs.keywords.size > 0,
    experience: includeExperience,
  };
  const scaled = {};
  let total = 0;
  for (const key of WEIGHT_KEYS) {
    scaled[key] = used[key] ? base[key] : 0;
    total += scaled[key];
  }
  if (total <= 0) {
    return Object.fromEntries(WEIGHT_KEYS.map(k => [k, 0]));
  }
  const out = {};
  for (const key of WEIGHT_KEYS) out[key] = scaled[key] / total;
  return out;
}

function weightPercent(weight) {
  return parseFloat((weight * 100).toPrecision(3));
}

function weightLabels(weights) {
  const w = weights || state.config.weights;
  return {
    required: `Required (${weightPercent(w.required_skills)}%)`,
    preferred: `Preferred (${weightPercent(w.preferred_skills)}%)`,
    experience: `Experience (${weightPercent(w.experience)}%)`,
    keywords: `Keywords (${weightPercent(w.keywords)}%)`,
  };
}

function scoringSummary() {
  const w = state.config.weights;
  return (
    `required skills ${weightPercent(w.required_skills)}% · ` +
    `preferred ${weightPercent(w.preferred_skills)}% · ` +
    `experience ${weightPercent(w.experience)}% · ` +
    `keywords ${weightPercent(w.keywords)}%`
  );
}

function intersection(a, b) {
  const out = new Set();
  for (const s of a) if (b.has(s)) out.add(s);
  return out;
}

function difference(a, b) {
  const out = new Set();
  for (const s of a) if (!b.has(s)) out.add(s);
  return out;
}

function scoreCandidate(filename, skills, years, reqs, extra = {}) {
  const config = state.config;
  let weights = activeWeights(config.weights, reqs);
  const requiredScore = coverage(skills, reqs.required);
  const preferredScore = coverage(skills, reqs.preferred);
  const keywordScore = coverage(skills, reqs.keywords);
  const targetYears = reqs.years || config.default_expected_years;
  let experienceScore;
  if (targetYears) {
    experienceScore = Math.min(years / targetYears, 1);
  } else {
    experienceScore = 1;
    weights = activeWeights(config.weights, reqs, false);
  }
  const dropped = WEIGHT_KEYS.filter(k => config.weights[k] > 0 && weights[k] === 0);

  const total = Math.round(
    100 *
      (weights.required_skills * requiredScore +
        weights.preferred_skills * preferredScore +
        weights.experience * experienceScore +
        weights.keywords * keywordScore) *
      10
  ) / 10;

  return {
    filename,
    total,
    requiredScore,
    preferredScore,
    experienceScore,
    keywordScore,
    years,
    matchedRequired: intersection(skills, reqs.required),
    missingRequired: difference(reqs.required, skills),
    matchedPreferred: intersection(skills, reqs.preferred),
    matchedKeywords: intersection(skills, reqs.keywords),
    evidence: extra.evidence || {},
    appliedWeights: weights,
    droppedComponents: dropped,
    parseStatus: extra.parseStatus || "ok",
    parseNote: extra.parseNote || "",
    fields: extra.fields || {},
  };
}

/* ---------------- feedback ------------------------------------------------ */

function generateFeedback(candidate, reqs, fields) {
  const tips = [];
  const targetYears = reqs.years || state.config.default_expected_years;
  const f = fields || candidate.fields || null;

  if (f) {
    const email = String(f.email || "").trim();
    const phone = String(f.phone || "").trim();
    const location = String(f.location || "").trim();
    const name = String(f.name || "").trim();
    const education = f.education_level || (f.education && f.education.length);
    const certifications = f.certifications && f.certifications.length;
    if (!name) {
      tips.push(
        "No candidate name was detected. Put your full name on its own line " +
        "at the very top of the CV, in plain text."
      );
    }
    if (!email && !phone) {
      tips.push(
        "No email address or phone number was detected. Add both in plain " +
        "text near the top (not inside an image or text box) so a recruiter " +
        "can contact you."
      );
    } else if (!email) {
      tips.push(
        "No email address was detected. Add a professional email in plain " +
        "text near the top of the CV."
      );
    } else if (!phone) {
      tips.push(
        "No phone number was detected. Add one in plain text near the top " +
        "of the CV, including the country code if relevant."
      );
    }
    if (!location) {
      tips.push(
        "No location was detected. Add your city and country (or region) " +
        'near your contact details, e.g. "Toronto, Canada".'
      );
    }
    if (!education && !certifications) {
      tips.push(
        "No education or certification details were detected. Add a short " +
        "Education section with the degree/diploma, institution and year, " +
        "plus any licences or certifications."
      );
    }
  }

  for (const skill of [...candidate.missingRequired].sort()) {
    tips.push(
      `Required skill "${skill}" was not detected. If you have used it, name ` +
      `it explicitly with that standard wording, ideally in a Skills section ` +
      `near the top.`
    );
  }

  const missingPreferred = [...difference(reqs.preferred, candidate.matchedPreferred)].sort();
  if (missingPreferred.length) {
    tips.push(
      `Preferred skills that would boost your score: ` +
      missingPreferred.map(s => `"${s}"`).join(", ") +
      `. Add them only if you genuinely have used them.`
    );
  }

  if (candidate.years < targetYears) {
    if (candidate.years) {
      tips.push(
        `We detected ${candidate.years} year(s) of experience but the role ` +
        `asks for ${targetYears}+. State it explicitly, e.g. "6+ years of ` +
        `professional Python development".`
      );
    } else {
      tips.push(
        `No years of experience were detected and the role asks for ` +
        `${targetYears}+. Add a line like "5+ years of ..." so it is ` +
        `unambiguous.`
      );
    }
  }

  const missingKeywords = [...difference(reqs.keywords, candidate.matchedKeywords)].sort();
  if (missingKeywords.length) {
    tips.push(
      `Domain terms from the job ad worth working naturally into your ` +
      `descriptions: ` + missingKeywords.map(s => `"${s}"`).join(", ") + `.`
    );
  }

  const matchedAny =
    candidate.matchedRequired.size || candidate.matchedPreferred.size ||
    candidate.matchedKeywords.size;
  if (!matchedAny) {
    tips.push(
      `No skills were detected at all. If this file is a scanned image or ` +
      `photo of a résumé, re-export it as a text-based PDF or DOCX so the ` +
      `text can actually be read.`
    );
  }

  if (!tips.length) {
    tips.push("Strong match — no changes needed for this job description.");
  }
  return tips;
}

/* ---------------- file parsing ----------------------------------------- */

const READ_TIMEOUT_MS = 30000;
const MAX_FILE_BYTES = 25 * 1024 * 1024;

function withTimeout(promise, ms, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(`${label} timed out after ${ms / 1000}s`)),
      ms
    );
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function cleanExtractedText(text) {
  return text
    .replace(/\0/g, " ")
    .replace(/\u00a0/g, " ")
    .replace(/\u200b/g, "")
    .replace(/\r\n?/g, "\n")
    .replace(/([A-Za-zÀ-ÖØ-öø-ÿ])-\s*\n\s*([a-zà-öø-ÿ])/g, "$1$2")
    .replace(/[ \t]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function pdfToText(arrayBuffer) {
  const doc = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  const pages = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    const lines = [];
    let line = "";
    let lastY = null;
    const flush = () => {
      const value = line.replace(/\s+/g, " ").trim();
      if (value) lines.push(value);
      line = "";
    };
    for (const item of content.items) {
      const str = typeof item.str === "string" ? item.str : "";
      if (!str) continue;
      const y = item.transform ? item.transform[5] : null;
      const lineHeight =
        typeof item.height === "number" && item.height > 0 ? item.height : 10;
      if (
        lastY !== null &&
        y !== null &&
        Math.abs(y - lastY) > Math.max(2, lineHeight * 0.6)
      ) {
        flush();
      }
      if (line && !/\s$/.test(line) && !/^\s/.test(str)) line += " ";
      line += str;
      if (item.hasEOL) {
        flush();
        lastY = null;
      } else {
        lastY = y;
      }
    }
    flush();
    pages.push(lines.join("\n"));
  }
  return pages.join("\n").trim();
}

async function fileToText(file) {
  if (file.size > MAX_FILE_BYTES) {
    throw new Error(
      `${(file.size / 1048576).toFixed(1)} MB is over the ` +
        `${MAX_FILE_BYTES / 1048576} MB cap`
    );
  }
  const name = file.name.toLowerCase();

  let textPromise;
  if (name.endsWith(".pdf")) {
    if (!window.pdfjsLib) throw new Error("PDF reader failed to load (offline?)");
    textPromise = pdfToText(await file.arrayBuffer());
  } else if (name.endsWith(".docx")) {
    if (!window.mammoth) throw new Error("DOCX reader failed to load (offline?)");
    textPromise = mammoth
      .extractRawText({ arrayBuffer: await file.arrayBuffer() })
      .then(result => result.value);
  } else {
    textPromise = file.text();
  }
  const text = await withTimeout(textPromise, READ_TIMEOUT_MS, `Reading ${file.name}`);
  return cleanExtractedText(text);
}

/* ---------------- pipeline --------------------------------------------- */

async function runScreening(jdText, files, requirements) {
  requirements = requirements || parseJd(jdText);
  if (
    !requirements.required.size &&
    !requirements.preferred.size &&
    !requirements.keywords.size
  ) {
    throw new Error(
      "No recognizable skills were found in the job description — paste a " +
      "fuller job ad (English or French). / Aucune compétence reconnue dans " +
      "l'offre — collez une offre plus complète."
    );
  }

  const candidates = [];
  const warnings = [...(requirements.warnings || [])];

  for (const file of files) {
    let text = "";
    let parseStatus = "ok";
    let parseNote = "";
    try {
      text = await fileToText(file);
      if (!text.trim()) {
        parseStatus = "empty";
        parseNote = "no readable text (scanned image?)";
        warnings.push(`${file.name}: no readable text`);
      }
    } catch (err) {
      console.error(err);
      parseStatus = "error";
      parseNote = err.message;
      warnings.push(`${file.name}: ${err.message}`);
    }
    const detailed = extractSkillsDetailed(text);
    const mined = matchTermsDetailed(text, requirements.minedTerms);
    const skills = new Set([...Object.keys(detailed), ...Object.keys(mined)]);
    const years = extractYears(text);
    const fields = extractFields(text);
    candidates.push(scoreCandidate(file.name, skills, years, requirements, {
      evidence: { ...detailed, ...mined },
      parseStatus,
      parseNote,
      fields,
    }));
  }

  if (!candidates.length) {
    throw new Error("No résumé files to screen.");
  }

  candidates.sort((a, b) => b.total - a.total || a.filename.localeCompare(b.filename));
  const feedback = candidates.map(c => generateFeedback(c, requirements, c.fields));
  return { requirements, candidates, feedback, warnings };
}

/* ---------------- UI ---------------------------------------------------- */

const els = {};

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function setStatus(message, kind) {
  els.status.textContent = message;
  els.status.className = "status" + (kind === "error" ? " error" : "");
}

function updateRunState() {
  els.run.disabled = !(els.jd.value.trim() && state.pendingFiles.length);
}

function renderFileList() {
  const list = els.fileList;
  list.hidden = state.pendingFiles.length === 0;
  list.innerHTML = state.pendingFiles
    .map(f => `<li>${esc(f.name)} (${(f.size / 1024).toFixed(1)} KB)</li>`)
    .join("");
}

function chip(skill, cls) {
  return `<span class="chip ${cls}">${esc(skill)}</span>`;
}

function setChips(container, skills, cls) {
  container.innerHTML = [...skills].sort().map(s => chip(s, cls)).join("") || '<span class="hint">none</span>';
}

function pctOrDash(score, weight) {
  if (!weight) return "—";
  return `${Math.round(score * 100)}%`;
}

function cloneRequirements(reqs) {
  return {
    required: new Set(reqs.required),
    preferred: new Set(reqs.preferred),
    keywords: new Set(reqs.keywords),
    minedTerms: new Set(reqs.minedTerms),
    years: reqs.years,
    hasExplicitSections: reqs.hasExplicitSections,
    warnings: [...(reqs.warnings || [])],
  };
}

function isCanonicalSkill(name) {
  if (!state.taxonomy) return false;
  for (const skills of Object.values(state.taxonomy)) {
    if (Object.prototype.hasOwnProperty.call(skills, name)) return true;
  }
  return false;
}

function extractFromJd() {
  const text = els.jd.value.trim();
  if (!text || !state.taxonomy) {
    state.requirements = null;
    renderInsight();
    return;
  }
  state.requirements = cloneRequirements(parseJd(text));
  renderInsight();
}

function bucketOf(skill, reqs) {
  if (reqs.required.has(skill)) return "required";
  if (reqs.preferred.has(skill)) return "preferred";
  if (reqs.keywords.has(skill)) return "keywords";
  return null;
}

function removeSkill(skill) {
  const reqs = state.requirements;
  if (!reqs) return;
  reqs.required.delete(skill);
  reqs.preferred.delete(skill);
  reqs.keywords.delete(skill);
  reqs.minedTerms.delete(skill);
  renderInsight();
}

function moveSkill(skill, target) {
  const reqs = state.requirements;
  if (!reqs) return;
  reqs.required.delete(skill);
  reqs.preferred.delete(skill);
  reqs.keywords.delete(skill);
  reqs[target].add(skill);
  if (!isCanonicalSkill(skill)) reqs.minedTerms.add(skill);
  renderInsight();
}

function addSkill(name, bucket) {
  const skill = name.trim().toLowerCase().replace(/\s+/g, " ");
  if (!skill || !state.requirements) return;
  moveSkill(skill, bucket);
}

function renderInsight() {
  const panel = els.insight;
  if (!panel) return;
  const reqs = state.requirements;
  panel.hidden = !reqs;
  if (!reqs) return;
  const weights = activeWeights(state.config.weights, reqs);
  els.weightNote.textContent =
    "Weights used: " +
    WEIGHT_KEYS.filter(k => weights[k] > 0)
      .map(k => `${k.replace("_", " ")} ${weightPercent(weights[k])}%`)
      .join(" · ") +
    (WEIGHT_KEYS.some(k => weights[k] === 0)
      ? ". Empty categories were dropped and the rest re-normalized to 100%."
      : ".");
  els.insightWarnings.innerHTML = (reqs.warnings || [])
    .map(w => `<p class="hint warn-line">${esc(w)}</p>`).join("");
  for (const bucket of ["required", "preferred", "keywords"]) {
    const row = document.getElementById("chips-" + bucket);
    const items = [...reqs[bucket]].sort();
    row.innerHTML = items.map(skill => `
      <span class="chip edit-chip">
        ${esc(skill)}
        <select aria-label="Move ${esc(skill)}" data-skill="${esc(skill)}" data-act="move">
          <option value="required"${bucket === "required" ? " selected" : ""}>Required</option>
          <option value="preferred"${bucket === "preferred" ? " selected" : ""}>Preferred</option>
          <option value="keywords"${bucket === "keywords" ? " selected" : ""}>Keyword</option>
        </select>
        <button type="button" class="chip-x" data-act="rm" data-skill="${esc(skill)}" aria-label="Remove ${esc(skill)}">×</button>
      </span>`).join("") || '<span class="hint">none — add below or they will be dropped from the score</span>';
  }
  const yearsEl = document.getElementById("insight-years");
  if (yearsEl) {
    const defaultYears = state.config.default_expected_years;
    yearsEl.textContent = reqs.years
      ? `${reqs.years}+ years`
      : (defaultYears
          ? `not specified (using ${defaultYears}+ default)`
          : "not specified (experience weight dropped)");
  }
}

function renderRequirements(reqs) {
  const fmt = set => [...set].sort().map(s => chip(s, "")).join("") || "-";
  const weights = reqs && state.lastResults && state.lastResults.candidates[0]
    ? state.lastResults.candidates[0].appliedWeights
    : null;
  const dropped = state.lastResults && state.lastResults.candidates[0]
    ? state.lastResults.candidates[0].droppedComponents
    : [];
  els.requirementsCard.innerHTML = `
    <h2>Requirements used for this ranking</h2>
    <div class="metric-row">
      <div class="metric"><div class="label">Required skills</div><div>${fmt(reqs.required)}</div></div>
      <div class="metric"><div class="label">Preferred skills</div><div>${fmt(reqs.preferred)}</div></div>
      <div class="metric"><div class="label">Keywords</div><div>${fmt(reqs.keywords)}</div></div>
      <div class="metric"><div class="label">Experience</div><div class="value">${reqs.years || "not specified"}</div></div>
    </div>
    ${dropped.length ? `<p class="hint">Dropped empty categories (weights re-normalized): ${dropped.join(", ")}.</p>` : ""}
    ${weights ? `<p class="hint">Applied weights: ${WEIGHT_KEYS.filter(k => weights[k]).map(k => `${k.replace("_skills", "")} ${weightPercent(weights[k])}%`).join(" · ")}.</p>` : ""}`;
}

function renderRanking(candidates) {
  const w = candidates[0] ? candidates[0].appliedWeights : state.config.weights;
  const rows = candidates.map((c, i) => `
    <tr class="${i === 0 ? "top" : ""}">
      <td>${i + 1}</td>
      <td>${esc(c.filename)}${c.parseStatus !== "ok" ? ` <span class="chip miss">${esc(c.parseStatus)}</span>` : ""}</td>
      <td class="score-cell">
        <span class="score-bar" style="width:${Math.round(c.total) * 0.6}px"></span>
        <strong>${c.total.toFixed(1)}</strong>
      </td>
      <td class="num">${pctOrDash(c.requiredScore, w.required_skills)}</td>
      <td class="num">${pctOrDash(c.preferredScore, w.preferred_skills)}</td>
      <td class="num">${pctOrDash(c.experienceScore, w.experience)}</td>
      <td class="num">${pctOrDash(c.keywordScore, w.keywords)}</td>
      <td class="num">${c.years}</td>
    </tr>`).join("");
  els.rankingBody.innerHTML = rows;
}

function evidenceList(skills, evidence) {
  const items = [...skills].sort().map(skill => {
    const snip = evidence && evidence[skill];
    return `<li><strong>${esc(skill)}</strong>${snip ? ` — <span class="hint">${esc(snip)}</span>` : ""}</li>`;
  });
  return items.length ? `<ul class="evidence">${items.join("")}</ul>` : '<span class="hint">none</span>';
}

function renderCandidateFields(fields) {
  if (!fields) return "";
  const rows = [];
  const add = (label, value) => {
    if (value) rows.push(`<li><strong>${esc(label)}:</strong> ${esc(value)}</li>`);
  };
  add("Name", fields.name);
  add("Email", fields.email);
  add("Phone", fields.phone);
  add("Location", fields.location);
  add("Headline", fields.headline);
  add("LinkedIn", fields.linkedin);
  add("GitHub", fields.github);
  add("Website", fields.website);
  add("Education level", fields.education_level);
  add("Education", (fields.education || []).join(" | "));
  add("Certifications", (fields.certifications || []).join(" | "));
  add("Languages", (fields.languages || []).join(", "));
  return rows.length
    ? `<p><strong>Extracted candidate details:</strong></p><ul class="evidence">${rows.join("")}</ul>`
    : "";
}

function renderDetails(candidates, feedback) {
  els.details.innerHTML = candidates.map((c, i) => {
    const labels = weightLabels(c.appliedWeights);
    return `
    <details class="candidate" ${i === 0 ? "open" : ""}>
      <summary>#${i + 1} — ${esc(c.filename)} — ${c.total.toFixed(1)} / 100</summary>
      <div class="body">
        <div class="metric-row">
          <div class="metric"><div class="label">${labels.required}</div><div class="value">${pctOrDash(c.requiredScore, c.appliedWeights.required_skills)}</div></div>
          <div class="metric"><div class="label">${labels.preferred}</div><div class="value">${pctOrDash(c.preferredScore, c.appliedWeights.preferred_skills)}</div></div>
          <div class="metric"><div class="label">${labels.experience}</div><div class="value">${pctOrDash(c.experienceScore, c.appliedWeights.experience)}</div></div>
          <div class="metric"><div class="label">${labels.keywords}</div><div class="value">${pctOrDash(c.keywordScore, c.appliedWeights.keywords)}</div></div>
          <div class="metric"><div class="label">Years detected</div><div class="value">${c.years}</div></div>
        </div>
        ${renderCandidateFields(c.fields)}
        <p><strong>Matched required (with evidence):</strong></p>
        ${evidenceList(c.matchedRequired, c.evidence)}
        <p><strong>Missing required:</strong></p><div id="req-miss-${i}"></div>
        <p><strong>Matched preferred:</strong></p>
        ${evidenceList(c.matchedPreferred, c.evidence)}
        <p><strong>Matched keywords:</strong></p><div id="kw-ok-${i}"></div>
        <h3 class="improve-title">✏️ How to improve this CV</h3>
        <ul class="tips">${feedback[i].map(t => `<li>${esc(t)}</li>`).join("")}</ul>
      </div>
    </details>`;
  }).join("");

  candidates.forEach((c, i) => {
    setChips(document.getElementById(`req-miss-${i}`), c.missingRequired, "miss");
    setChips(document.getElementById(`kw-ok-${i}`), c.matchedKeywords, "warn");
  });
}

/* ---------------- sample data ------------------------------------------ */

const SAMPLE_RESUMES = [
  "alice_strong_match.txt",
  "bob_partial_match.txt",
  "carol_frontend.txt",
  "david_docx_candidate.docx",
  "emma_pdf_candidate.pdf",
  "julie_french_cv.txt",
];

async function loadSampleJd(file = "data/sample_jd.txt") {
  const resp = await fetch(file, { cache: "no-store" });
  if (!resp.ok) throw new Error("sample JD not found");
  els.jd.value = await resp.text();
  extractFromJd();
  updateRunState();
}

async function loadSampleResumes() {
  const transfer = new DataTransfer();
  for (const name of SAMPLE_RESUMES) {
    const resp = await fetch("samples/" + name, { cache: "no-store" });
    if (!resp.ok) throw new Error("sample résumés missing");
    transfer.items.add(new File([await resp.arrayBuffer()], name));
  }
  els.files.files = transfer.files;
  els.files.dispatchEvent(new Event("change", { bubbles: true }));
  return SAMPLE_RESUMES.length;
}

/* ---------------- bootstrap -------------------------------------------- */

async function init() {
  els.jd = document.getElementById("jd-input");
  els.files = document.getElementById("resume-files");
  els.run = document.getElementById("run-btn");
  els.status = document.getElementById("status");
  els.results = document.getElementById("results");
  els.fileList = document.getElementById("file-list");
  els.requirementsCard = document.getElementById("requirements-card");
  els.rankingBody = document.querySelector("#ranking-table tbody");
  els.details = document.getElementById("details");
  els.insight = document.getElementById("jd-insight");
  els.weightNote = document.getElementById("weight-note");
  els.insightWarnings = document.getElementById("insight-warnings");
  els.appVersion = document.getElementById("app-version");
  if (els.appVersion) els.appVersion.textContent = `v${APP_VERSION}`;

  try {
    const [configResp, taxonomyResp] = await Promise.all([
      fetch(`data/config.json?v=${APP_VERSION}`, { cache: "no-store" }),
      fetch(`data/skills_taxonomy.json?v=${APP_VERSION}`, { cache: "no-store" }),
    ]);
    if (!configResp.ok || !taxonomyResp.ok) {
      throw new Error("data files missing");
    }
    state.config = await configResp.json();
    state.taxonomy = await taxonomyResp.json();
    state.patterns = buildPatterns(state.taxonomy);
    document.getElementById("scoring-summary").textContent = scoringSummary();
  } catch (err) {
    setStatus(`Failed to load scoring data: ${err.message}`, "error");
    return;
  }

  if (window.pdfjsLib) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdf.worker.min.js";
  }

  els.jd.addEventListener("input", () => {
    updateRunState();
    clearTimeout(state.extractTimer);
    state.extractTimer = setTimeout(extractFromJd, 500);
  });
  els.files.addEventListener("change", () => {
    state.pendingFiles = [...els.files.files];
    renderFileList();
    updateRunState();
  });

  document.getElementById("load-sample-jd").addEventListener("click", async () => {
    try { await loadSampleJd(); } catch (err) { setStatus(err.message, "error"); }
  });

  document.getElementById("load-sample-jd-fr").addEventListener("click", async () => {
    try { await loadSampleJd("data/sample_jd_fr.txt"); } catch (err) { setStatus(err.message, "error"); }
  });

  document.getElementById("load-sample-resumes").addEventListener("click", async () => {
    try {
      const count = await loadSampleResumes();
      setStatus(`Loaded ${count} sample résumés.`);
    } catch (err) {
      setStatus(`Could not load samples (your browser may block this): ${err.message}. Upload files manually instead.`, "error");
    }
  });

  els.run.addEventListener("click", async () => {
    els.run.disabled = true;
    els.results.hidden = true;
    setStatus("Processing resumes...");
    try {
      const jdText = els.jd.value;
      if (!state.requirements) extractFromJd();
      state.lastResults = await runScreening(jdText, state.pendingFiles, state.requirements);
      renderRequirements(state.lastResults.requirements);
      renderRanking(state.lastResults.candidates);
      renderDetails(state.lastResults.candidates, state.lastResults.feedback);
      els.results.hidden = false;
      const fileWarns = state.lastResults.warnings.filter(w => w.includes(":"));
      const warnNote = fileWarns.length
        ? ` (${fileWarns.length} warning(s))`
        : "";
      setStatus(`Screened ${state.pendingFiles.length} resume(s)${warnNote}.`);
    } catch (err) {
      console.error(err);
      setStatus(`Screening failed: ${err.message}`, "error");
    } finally {
      updateRunState();
    }
  });

  const insight = document.getElementById("jd-insight");
  if (insight) {
    insight.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-act='rm']");
      if (btn) removeSkill(btn.getAttribute("data-skill"));
    });
    insight.addEventListener("change", (event) => {
      const sel = event.target.closest("select[data-act='move']");
      if (sel) moveSkill(sel.getAttribute("data-skill"), sel.value);
    });
  }
  const reextract = document.getElementById("reextract-btn");
  if (reextract) reextract.addEventListener("click", extractFromJd);
  const extractBtn = document.getElementById("extract-jd-btn");
  if (extractBtn) extractBtn.addEventListener("click", extractFromJd);
  const addForm = document.getElementById("add-skill-form");
  if (addForm) {
    addForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const name = document.getElementById("add-skill-name");
      const bucket = document.getElementById("add-skill-bucket");
      addSkill(name.value, bucket.value);
      name.value = "";
    });
  }

  updateRunState();
}

init();

window.__rss = {
  state, appVersion: APP_VERSION, extractSkills, extractYears, parseJd,
  scoreCandidate, generateFeedback, runScreening, normalizeText, matchTerms,
  activeWeights, extractSkillsDetailed, extractFields,
};
