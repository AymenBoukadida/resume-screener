# Changelog

## Unreleased

### Highlights

- Screening now works for **any domain**, not only IT/security roles. A term
  miner promotes the job ad's own repeated, bulleted, capitalised or early
  phrases into requirements, and matches those phrases in CVs. The skills
  taxonomy was also expanded to 27 categories and 436 skills.
- Résumés now expose **structured fields** — name, email, phone, location,
  headline, LinkedIn/GitHub/website, education level and history,
  certifications and languages — in the console, CSV and JSON output. Fields
  are for review and do not affect the score.
- The JD parser handles more real-world layouts: whole-line section headers,
  inline labels, Markdown headings, numbered lists, mixed English/French
  headers, and explicit preferred cues inside Required sections.

### Job-description parsing

- Section headers are matched against whole header lines, never substrings,
  so requirement sentences such as "experience with Python" can no longer
  hijack section detection.
- "Preferred qualifications", "an asset", "nice to have" and similar cues
  are classified as preferred even when they appear under a Required heading.
- Skills present in both Required and Preferred are subtracted from
  Preferred, so the same evidence is not counted twice.
- Inline headers (`Required skills: Python, Django`,
  `Compétences requises : Python, Django`) and French headers such as
  `Compétences souhaitées` are supported.
- Inline labels with extra words (`Job Requirements & Knowledge:`) and
  parenthetical preferred headings (`Certifications (Considered an
  Advantage)`) are recognized.
- Thematic subheadings such as `Security Operations & Vulnerability
  Management` are treated as structure instead of requirements.
- Explicit degree and experience lines under a Preferred heading are moved
  back to Required.
- Markdown headings and numbered lists are treated as structure.
- Section-less JDs still fall back to treating every extracted skill as
  required.

### Extraction

- Added conservative English/French field extraction for names, emails,
  phones, locations, headlines, LinkedIn/GitHub/website links, education
  levels and history, certifications and languages. Inline labels
  (`Education: ...`, `Certifications: ...`, `Langues : ...`) and French
  credentials such as DEP, AEP, ASP and CÉGEP are recognised.
- Expanded `data/skills_taxonomy.json` to 27 categories / 436 unique skills,
  with French synonyms for most entries.
- The term miner now filters recruiting prose, role titles, work conditions,
  credential words, language-list terms (`french/english`), requirement
  phrasing (`nice`, `asset`, `ideally`), and fragments of skills already
  counted by the taxonomy.
- Term mining handles morphology, canonicalisation guards, line-initial
  all-caps acronyms (`CWB`, `BLS`) and French apostrophe elisions
  (`d'expérience` → `d` + `experience`).
- Generic single tokens no longer canonicalise to unrelated taxonomy skills
  (`security` → Security+, `activities` → ADL assistance, `policies` → HR
  policies). Symbol-only variations such as `C++` and `Security+` are left to
  exact taxonomy matching.
- Short non-bullet lines no longer count as bullet evidence when mining terms.
- Added Markdown résumé and job-description support.
- Text cleanup dehyphenates words split across line breaks
  (`Déve-\nloppement` → `Développement`).
- Résumé discovery can recurse into subdirectories and skips hidden files and
  Office lock files (`~$...`).

### Scoring

- Empty JD categories (no preferred skills, no keywords, or no stated
  experience requirement) no longer score as 100% coverage. Their weight is
  set to 0 and the remaining components are re-normalized to 1.0.
- The experience component is dropped when the JD specifies no years;
  `default_expected_years` is now `0` instead of `3`.
- Negated mentions (`no experience with Docker`,
  `pas d'expérience en Docker`, `I have not worked with Java`) no longer
  count as a match.
- Résumé years now also use merged employment date ranges
  (`2019 – present`), ignoring "5 years old" / "founded 10 years ago". JD
  thresholds still use the lowest explicit figure ("3–5 years" → 3).
- Optional version suffixes match (`Node 18` → `node.js`,
  `React 18` → `react`).
- Per-skill evidence snippets and the applied weights are retained and
  exported.

### CLI

- `--jd` accepts TXT, Markdown, PDF and DOCX.
- Added `--recursive` for résumé folders with subdirectories.
- Added `--json` for machine-readable output.
- CSV output includes contact details, links, education, certifications,
  languages and evidence snippets, plus the per-candidate tips.
- Console output shows extracted candidate fields, evidence snippets and
  contact/education feedback.
- Console output is reconfigured to UTF-8 on Windows so accents display
  correctly.

### Web app

- Mirrored the Python JD parsing, scoring, term mining and field extraction
  changes in `docs/app.js`, including preferred-cue overrides and
  preferred-minus-required subtraction.
- Candidate details now show extracted fields and contact-aware feedback.
- PDF text extraction now preserves line breaks, so names, headlines,
  locations and education are detected in browser-parsed PDFs instead of
  being flattened into one paragraph.
- Mirrored the CLI's text cleanup (de-hyphenation, invisible characters and
  whitespace squeezing) so the web app scores the same text the CLI would.
- The file picker accepts Markdown in addition to PDF, DOCX and TXT.
- Kept `docs/data/` in sync with the canonical `data/` files through
  `scripts/sync_web_data.py`.
- The app version is shown in the footer, and `app.js` plus the scoring data
  are loaded with a cache-busting version, so an old cached build cannot
  silently keep producing stale results.

### Tests and documentation

- Added regression tests for arbitrary-domain JDs, field extraction,
  morphology, preferred-cue overrides, Markdown résumés and scoring; the
  Python suite now has 20 passing tests.
- Updated README and CHANGELOG for the new formats, options, fields and
  scoring behaviour.
