/* Résumé Screening System — static web app.
 * Text extraction (PDF via pdf.js, DOCX via mammoth.js), skill matching,
 * scoring and CV feedback, all client-side. Data comes from docs/data/.
 *
 * The normalization, JD parsing, years extraction, scoring and feedback
 * logic MIRRORS the Python engine (extractors/keyword_extractor.py,
 * parsers/jd_parser.py, matcher/scorer.py, matcher/feedback.py) — change
 * both sides together.
 */
"use strict";

const state = {
  config: null,        // { weights: {...}, default_expected_years: n }
  taxonomy: null,      // { category: { skill: [variations] } }
  patterns: [],        // [skillName, RegExp]
  pendingFiles: [],    // File objects chosen by the user
  lastResults: null,   // { requirements, candidates: [ {score, feedback, ...} ] }
};

/* ---------------- text normalization (English + French) ---------------- */

// Lowercase, strip accents (é → e) and normalise apostrophes, so English and
// French text ("développement", "DEVELOPPEMENT") match the same accent-free
// variations stored in the taxonomy.
function normalizeText(s) {
  return s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\u2019/g, "'");
}

/* ---------------- regex helpers ----------------------------------------- */

const BULLET_CHARS = "-*•·▪‣–—";
const WORD_NUMBERS = {
  // English
  one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  // French
  un: 1, une: 1, deux: 2, trois: 3, quatre: 4, cinq: 5,
  six: 6, sept: 7, huit: 8, neuf: 9, dix: 10,
};

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildPatterns(taxonomy) {
  const patterns = [];
  for (const skillsDict of Object.values(taxonomy)) {
    for (const [skillName, variations] of Object.entries(skillsDict)) {
      for (const variation of variations) {
        // No lookbehind (unsupported in older Safari): no alphanumeric
        // immediately before or after the match.
        patterns.push([
          skillName,
          new RegExp(
            "(^|[^a-z0-9])" + escapeRe(normalizeText(variation)) + "(?![a-z0-9])"
          ),
        ]);
      }
    }
  }
  return patterns;
}

function extractSkills(text) {
  const norm = normalizeText(text);
  const found = new Set();
  for (const [skillName, pattern] of state.patterns) {
    if (pattern.test(norm)) found.add(skillName);
  }
  return found;
}

// "3+ years" / "5 ans" / "3-5 years" (both range bounds captured) /
// "cinq ans" / "1,5 an" (decimals truncated). mode "max" is the résumé
// heuristic (highest figure ≈ total experience), "min" the JD threshold
// (lowest figure the role accepts). No lookbehind (unsupported in older
// Safari): the leading group guards the left boundary instead.
const YEARS_UNIT = "(?:years?|ans?|annee?s?)";
const YEARS_DIGIT_RE = new RegExp(
  "(^|[^\\d.,])(\\d{1,2}(?:[.,]\\d)?)" +
    "(?:\\s*(?:\\+|to|-|–)(?:\\s*(\\d{1,2}(?:[.,]\\d)?))?)?" +
    "\\s*" + YEARS_UNIT + "\\b",
  "g"
);

function extractYears(text, mode = "max") {
  const norm = normalizeText(text);
  const values = [];
  let m;
  while ((m = YEARS_DIGIT_RE.exec(norm)) !== null) {
    for (const bound of [m[2], m[3]]) {
      if (bound) values.push(parseFloat(bound.replace(",", ".")));
    }
  }
  for (const [word, value] of Object.entries(WORD_NUMBERS)) {
    const wordRe = new RegExp("\\b(" + word + ")\\s*(?:\\+|to|-|–)?\\s*" + YEARS_UNIT + "\\b");
    if (wordRe.test(norm)) values.push(value);
  }
  if (!values.length) return 0;
  const pick = mode === "min" ? Math.min(...values) : Math.max(...values);
  return Math.floor(pick);
}

/* ---------------- JD parsing -------------------------------------------- */

const SECTION_PATTERNS = [
  ["required", /\b(required|requirements?|must[\s-]?haves?|essential|qualifications?|what\s+you\s+(?:will\s+)?bring|what\s+we(?:'re|\s+are)\s+looking\s+for|your\s+profile|about\s+you|a\s+propos\s+de\s+vous|who\s+you\s+are|ce\s+que\s+vous\s+apportez|profil\s+recherche|requises?|requis|exigees?|exigences?|essentielles?|obligatoires?|indispensables?|necessaires?)\b/i],
  ["preferred", /\b(preferred|nice[\s-]?to[\s-]?haves?|good[\s-]?to[\s-]?haves?|bonus|desirable|pluses?|what\s+makes\s+you|souhaitees?|souhaite|atouts?|appreciees?|apprecie|seraient un plus)\b/i],
  ["experience", /\b(experience|responsibilit(?:y|ies)|what\s+you.{0,3}ll\s+do|(?:a\s+)?day\s+in\s+the\s+life|day[\s-]?to[\s-]?day|your\s+mission|duties|missions|taches|au\s+quotidien)\b/i],
];

function matchSectionLabel(text) {
  for (const [label, pattern] of SECTION_PATTERNS) {
    if (pattern.test(text)) return label;
  }
  return null;
}

// Lines starting with these (de-accented) words are sentences, not headers —
// "We value experience" must not hijack section parsing. Pronoun openers only,
// so real headers like "Relevant experience" still pass.
const SENTENCE_OPENERS = new Set([
  "we", "you", "your", "our", "i", "nous", "vous", "votre", "notre",
]);

function matchHeader(line) {
  // A header ends with ":" (the strong signal, any length), or is short,
  // free of sentence-ending punctuation and does not open with a pronoun.
  if (line.endsWith(":")) return matchSectionLabel(line);
  if (line.split(/\s+/).length > 3) return null;
  if (/[.!?;,]$/.test(line)) return null;
  if (SENTENCE_OPENERS.has(line.split(/\s+/)[0])) return null;
  return matchSectionLabel(line);
}

function splitSections(jdText) {
  const sections = { required: [], preferred: [], experience: [] };
  let current = null;

  for (const rawLine of jdText.split("\n")) {
    let line = rawLine.trim();
    if (!line) continue;

    const isBullet = BULLET_CHARS.includes(line[0]);
    if (isBullet) line = line.replace(/^[-*•·▪‣–—]+/, "").trim();
    const lineNorm = normalizeText(line);

    // Inline header, e.g. "Required skills: Python, Django" or French
    // "Compétences requises : Python, Django".
    if (!isBullet && lineNorm.includes(":")) {
      const idx = lineNorm.indexOf(":");
      const left = lineNorm.slice(0, idx);
      const right = lineNorm.slice(idx + 1);
      const label = matchSectionLabel(left);
      if (label) {
        current = label;
        if (right.trim()) sections[label].push(right.trim());
        continue;
      }
    }

    if (!isBullet) {
      const header = matchHeader(lineNorm);
      if (header) {
        current = header;
        continue;
      }
      // A short "Label:" line that matches no known header still ends the
      // current section ("Why Work at Long View:") so its content cannot
      // leak into the previous bucket. Lines with text after the colon
      // ("Location: Calgary") stay content.
      if (lineNorm.endsWith(":") && lineNorm.slice(0, -1).split(/\s+/).length <= 5) {
        current = null;
        continue;
      }
    }

    if (current) sections[current].push(line);
  }
  return sections;
}

function parseJd(jdText) {
  const sections = splitSections(jdText);
  let required = extractSkills(sections.required.join("\n"));
  const preferred = extractSkills(sections.preferred.join("\n"));

  // True only when the JD declared sections — the fallback below fills
  // `required`, which must not flip this flag (the UI hint depends on it).
  const hasExplicitSections = required.size > 0 || preferred.size > 0;
  if (required.size === 0 && preferred.size === 0) {
    required = extractSkills(jdText); // unstructured JD fallback
  }

  const allMentioned = extractSkills(jdText);
  const keywords = new Set(
    [...allMentioned].filter(s => !required.has(s) && !preferred.has(s))
  );

  return {
    required,
    preferred,
    keywords,
    // A "3-5 years" JD is met at 3 years: the JD threshold is the lowest
    // figure mentioned (résumés keep the highest).
    years: extractYears(jdText, "min"),
    hasExplicitSections,
  };
}

/* ---------------- scoring ------------------------------------------------ */

function coverage(matched, target) {
  if (!target || target.size === 0) return 1.0;
  let hits = 0;
  for (const skill of target) if (matched.has(skill)) hits++;
  return hits / target.size;
}

// Percentages shown in the UI always derive from the loaded config, so
// editing docs/data/config.json weights can never leave stale labels.
function weightPercent(weight) {
  return parseFloat((weight * 100).toPrecision(3));
}

function weightLabels() {
  const w = state.config.weights;
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

function scoreCandidate(filename, skills, years, reqs) {
  const config = state.config;
  const requiredScore = coverage(skills, reqs.required);
  const preferredScore = coverage(skills, reqs.preferred);
  const keywordScore = coverage(skills, reqs.keywords);
  const targetYears = reqs.years || config.default_expected_years;
  const experienceScore = targetYears
    ? Math.min(years / targetYears, 1)
    : 1;

  const w = config.weights;
  const total = Math.round(
    100 *
      (w.required_skills * requiredScore +
        w.preferred_skills * preferredScore +
        w.experience * experienceScore +
        w.keywords * keywordScore) *
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
  };
}

/* ---------------- feedback ------------------------------------------------ */

function generateFeedback(candidate, reqs) {
  const tips = [];
  const targetYears = reqs.years || state.config.default_expected_years;

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
// Oversized files are almost never legitimate résumés and can be crafted to
// exhaust memory (e.g. zip-bomb DOCX). Keep in sync with parsers/resume_parser.py.
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

async function pdfToText(arrayBuffer) {
  const doc = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  let text = "";
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    text += content.items.map(item => item.str).join(" ") + "\n";
  }
  return text.trim();
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
  // The timeout wraps the whole read (document open + every page), not just
  // the initial fetch, so a pathological file cannot hang past the cap.
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
  return text.trim();
}

/* ---------------- pipeline --------------------------------------------- */

async function runScreening(jdText, files) {
  const requirements = parseJd(jdText);
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
  const warnings = [];

  for (const file of files) {
    let text = "";
    try {
      text = await fileToText(file);
      if (!text.trim()) {
        warnings.push(`${file.name}: no readable text`);
      }
    } catch (err) {
      console.error(err);
      warnings.push(`${file.name}: ${err.message}`);
    }
    const skills = extractSkills(text);
    const years = extractYears(text);
    candidates.push(scoreCandidate(file.name, skills, years, requirements));
  }

  if (!candidates.length) {
    throw new Error("No résumé files to screen.");
  }

  candidates.sort((a, b) => b.total - a.total);
  // Indexed by position: uploads can contain duplicate filenames.
  const feedback = candidates.map(c => generateFeedback(c, requirements));
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

function renderRequirements(reqs) {
  const fmt = set => [...set].sort().map(s => chip(s, "")).join("") || "-";
  els.requirementsCard.innerHTML = `
    <h2>Requirements extracted from the job description</h2>
    <div class="metric-row">
      <div class="metric"><div class="label">Required skills</div><div>${fmt(reqs.required)}</div></div>
      <div class="metric"><div class="label">Preferred skills</div><div>${fmt(reqs.preferred)}</div></div>
      <div class="metric"><div class="label">Keywords</div><div>${fmt(reqs.keywords)}</div></div>
      <div class="metric"><div class="label">Experience</div><div class="value">${reqs.years || "not specified"}</div></div>
    </div>
    ${reqs.hasExplicitSections ? "" :
      '<p class="hint">No Required/Preferred section detected — every skill found in the JD was treated as required.</p>'}`;
}

function renderRanking(candidates) {
  const rows = candidates.map((c, i) => `
    <tr class="${i === 0 ? "top" : ""}">
      <td>${i + 1}</td>
      <td>${esc(c.filename)}</td>
      <td class="score-cell">
        <span class="score-bar" style="width:${Math.round(c.total) * 0.6}px"></span>
        <strong>${c.total.toFixed(1)}</strong>
      </td>
      <td class="num">${(c.requiredScore * 100).toFixed(0)}%</td>
      <td class="num">${(c.preferredScore * 100).toFixed(0)}%</td>
      <td class="num">${(c.experienceScore * 100).toFixed(0)}%</td>
      <td class="num">${(c.keywordScore * 100).toFixed(0)}%</td>
      <td class="num">${c.years}</td>
    </tr>`).join("");
  els.rankingBody.innerHTML = rows;
}

function renderDetails(candidates, feedback) {
  const labels = weightLabels();
  els.details.innerHTML = candidates.map((c, i) => `
    <details class="candidate" ${i === 0 ? "open" : ""}>
      <summary>#${i + 1} — ${esc(c.filename)} — ${c.total.toFixed(1)} / 100</summary>
      <div class="body">
        <div class="metric-row">
          <div class="metric"><div class="label">${labels.required}</div><div class="value">${(c.requiredScore * 100).toFixed(0)}%</div></div>
          <div class="metric"><div class="label">${labels.preferred}</div><div class="value">${(c.preferredScore * 100).toFixed(0)}%</div></div>
          <div class="metric"><div class="label">${labels.experience}</div><div class="value">${(c.experienceScore * 100).toFixed(0)}%</div></div>
          <div class="metric"><div class="label">${labels.keywords}</div><div class="value">${(c.keywordScore * 100).toFixed(0)}%</div></div>
          <div class="metric"><div class="label">Years detected</div><div class="value">${c.years}</div></div>
        </div>
        <p><strong>Matched required:</strong></p><div id="req-ok-${i}"></div>
        <p><strong>Missing required:</strong></p><div id="req-miss-${i}"></div>
        <p><strong>Matched preferred:</strong></p><div id="pref-ok-${i}"></div>
        <p><strong>Matched keywords:</strong></p><div id="kw-ok-${i}"></div>
        <h3 class="improve-title">✏️ How to improve this CV</h3>
        <ul class="tips">${feedback[i].map(t => `<li>${esc(t)}</li>`).join("")}</ul>
      </div>
    </details>`).join("");

  candidates.forEach((c, i) => {
    setChips(document.getElementById(`req-ok-${i}`), c.matchedRequired, "good");
    setChips(document.getElementById(`req-miss-${i}`), c.missingRequired, "miss");
    setChips(document.getElementById(`pref-ok-${i}`), c.matchedPreferred, "good");
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
  const resp = await fetch(file);
  if (!resp.ok) throw new Error("sample JD not found");
  els.jd.value = await resp.text();
  updateRunState();
}

async function loadSampleResumes() {
  const transfer = new DataTransfer();
  for (const name of SAMPLE_RESUMES) {
    const resp = await fetch("samples/" + name);
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

  try {
    const [configResp, taxonomyResp] = await Promise.all([
      fetch("data/config.json"),
      fetch("data/skills_taxonomy.json"),
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
    // Vendored, version-locked next to the app: no CDN call at read time.
    pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdf.worker.min.js";
  }

  els.jd.addEventListener("input", updateRunState);
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
      state.lastResults = await runScreening(jdText, state.pendingFiles);
      renderRequirements(state.lastResults.requirements);
      renderRanking(state.lastResults.candidates);
      renderDetails(state.lastResults.candidates, state.lastResults.feedback);
      els.results.hidden = false;
      const warnNames = state.lastResults.warnings.map(w => w.split(":")[0]);
      const warnNote = warnNames.length
        ? ` (${warnNames.length} unreadable: ${warnNames.join(", ")})`
        : "";
      setStatus(`Screened ${state.pendingFiles.length} resume(s)${warnNote}.`);
    } catch (err) {
      console.error(err);
      setStatus(`Screening failed: ${err.message}`, "error");
    } finally {
      updateRunState();
    }
  });

  updateRunState();
}

init();

// Debug and testing hooks.
window.__rss = {
  state, extractSkills, extractYears, parseJd, scoreCandidate,
  generateFeedback, runScreening, normalizeText,
};
