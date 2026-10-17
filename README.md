# Résumé Screening System

A bilingual (English / French) résumé screening tool that ranks candidates
against a job description using a fixed, transparent scoring formula — and
tells every candidate exactly how to improve their CV.

It ships as two frontends over one scoring engine:

| Interface | Stack | Best for |
|---|---|---|
| Command line (`main.py`) | Python, multiprocessing | Batch-screening a folder of résumés |
| Web app (`docs/`) | Static HTML/JS | Zero-install use; deploys on GitHub Pages |

No data ever leaves the machine it runs on: the CLI works on local files, and
the web app parses and scores everything in the visitor's browser.

## Features

- **PDF, DOCX and TXT résumés** — text extracted per file, dispatching on format.
- **Structured job-description parsing** — required skills, preferred skills,
  experience expectations and domain keywords, from English or French JDs.
- **Weighted, auditable scoring** — every candidate is scored with the same
  formula and the same skill taxonomy; full per-candidate breakdowns are kept.
- **CV-improvement feedback** — concrete, per-candidate tips: which required
  skills to name explicitly, what experience to quantify, which domain terms
  to work in.
- **Fault tolerant** — unreadable files are reported and skipped; invalid
  configuration or a skill-less job description stops cleanly with a clear
  error instead of a traceback.
- **Parallel batch processing** — the CLI parses résumés across a process pool.

## How it works

```
                ┌────────────────────┐
 Résumés        │   Résumé Parser    │       plain text
 (PDF/DOCX/TXT) │ (pypdf / docx /    │ ─────────────────────┐
 ──────────────►│  pdf.js / mammoth) │                      ▼
                └────────────────────┘                      │
                ┌────────────────────┐       ┌──────────────────────────┐
 Job            │     JD Parser      │       │    Keyword Extractor     │
 description    │  required/preferred│──────►│ taxonomy matching +      │
 (TXT/PDF)      │  /experience       │       │ years-of-experience      │
                └────────────────────┘       └───────────┬──────────────┘
                                                         ▼
                                             ┌───────────────────────┐
                                             │    Scoring Engine     │
                                             │ weighted formula +    │
                                             │ CV-feedback generator │
                                             └───────────┬───────────┘
                                                         ▼
                                            Ranked results + CSV +
                                            improvement tips
```

1. **Résumé parser** extracts plain text from each file.
2. **JD parser** splits the job description into Required / Preferred /
   Experience sections and extracts the skills in each. Without explicit
   sections, every skill mentioned in the JD is treated as required, and any
   other taxonomy skills it mentions become keywords.
3. **Keyword extractor** matches text against the skill taxonomy
   case-insensitively and accent-insensitively, with word boundaries — so
   "Java" does not match inside "JavaScript", while "c++" and "c#" still
   match. It also detects years of experience ("5+ years", "5 ans", "cinq
   années", "1,5 an"), keeping the highest figure for a CV and the lowest
   for a JD's range ("3–5 years" asks for 3).
4. **Scoring engine** applies the weighted formula and ranks candidates.
5. **Feedback generator** converts each score breakdown into actionable CV
   advice, including a warning when a file looks like a scanned image with no
   readable text.

## Scoring model

```
Total Score = (Required Skills × 50%)
            + (Preferred Skills × 25%)
            + (Experience      × 15%)
            + (Keywords        × 10%)
```

| Component | Weight | What it measures |
|---|---|---|
| Required skills | 50% | Share of the JD's required skills found in the CV |
| Preferred skills | 25% | Share of the JD's preferred skills found in the CV |
| Experience | 15% | Years detected in the CV ÷ years requested in the JD (capped at 1.0); a JD range like "3–5 years" sets the bar at its lower bound |
| Keywords | 10% | Share of the JD's domain keywords found in the CV |

Each component is a coverage ratio between 0 and 1, so the total score is
always between 0 and 100. Because the same weights, taxonomy and formula
apply to every candidate, the ranking is consistent, reproducible and
auditable — the full breakdown (matched and missing skills per candidate) is
included in the CSV output.

## Bilingual support (English / Français)

- Matching is **accent-insensitive**: "développement", "DEVELOPPEMENT" and
  "developpement" are equivalent.
- The JD parser recognises French section headers: *Compétences requises*,
  *Compétences souhaitées*, *Atouts*, *Expérience*, and inline forms such as
  *Compétences requises : Python, Django*.
- The taxonomy contains French synonyms for most skills (*api rest*,
  *intégration continue*, *tests unitaires*, *travail d'équipe*, …).
- Experience detection understands "3+ years", "5 ans", "3 années",
  decimals ("1,5 an") and spelled-out numbers in both languages. A CV is
  credited with the highest figure it mentions; a JD range like "3–5 ans"
  sets its threshold at the lower bound.

## Getting started

### Prerequisites

- Python 3.9 or later (CLI only — the web app needs no runtime)
- A modern browser for the web app

### Installation

```powershell
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# macOS / Linux / Git Bash
python -m venv venv
source venv/bin/activate   # Git Bash on Windows: source venv/Scripts/activate
pip install -r requirements.txt
```

If PowerShell blocks `Activate.ps1`, either run
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once,
or call the venv's interpreter directly (`.\venv\Scripts\python.exe`).

### Command-line usage

```bash
python main.py --jd data/sample_jd.txt --input input/sample_resumes --output output
```

```text
Options:
  --jd       Path to the job description (TXT or PDF). Required.
  --input    Directory of résumés to screen (default: input).
  --output   Directory for ranked_resumes.csv (default: output).
  --workers  Parallel parse processes (default: CPU count, capped at 8).
```

The run prints the extracted requirements, the ranked table and per-candidate
improvement tips, then writes `ranked_resumes.csv` with columns for each
score component, matched/missing skills, and the tips.

Try it with the included samples:

```bash
python main.py --jd data/sample_jd.txt     --input input/sample_resumes   # English JD
python main.py --jd data/sample_jd_fr.txt  --input input/sample_resumes   # French JD
```

### Web app

Preview locally:

```bash
python -m http.server 8000 --directory docs
# open http://localhost:8000
```

The page loads the scoring data from `docs/data/`, parses the résumés you
choose (or the built-in samples) entirely in the browser, and renders the
ranking, per-candidate breakdowns and CV-improvement tips. Files are never
uploaded anywhere.

### Deploying the web app on GitHub Pages

1. Push this repository to GitHub.
2. **Settings → Pages → Build and deployment**: Source *Deploy from a branch*,
   branch `main`, folder `/docs`.
3. The site goes live at `https://<username>.github.io/<repo>/`.

The PDF and DOCX readers (pdf.js, mammoth.js) are loaded from a CDN with
Subresource Integrity pins — if the CDN is ever compromised and serves
different bytes, browsers refuse to execute them — and the pdf.js worker is
vendored in `docs/vendor/`, version-locked to the app. TXT screening works
fully offline. The page also ships a strict Content-Security-Policy that
only allows its own files plus the two pinned CDN libraries to load.

## Configuration

Everything tunable lives in `data/` — no code changes required.

| File | Purpose |
|---|---|
| `data/config.json` | Component weights (must sum to 1.0) and the default experience expectation when the JD doesn't state one |
| `data/skills_taxonomy.json` | The skills database: `category → skill → [synonym variations]`. Matching is accent-free; add a skill by adding one entry |

The weights are a live setting: the percentages shown in the CLI table, the
CSV columns and the web app are derived from `config.json` at run time, so
editing the weights updates every label automatically.

After editing either file, refresh the web app's copy:

```bash
python scripts/sync_web_data.py
```

Regenerate the sample DOCX/PDF résumés at any time:

```bash
python scripts/make_sample_data.py
```

## Tests

The CLI and the browser app implement the same engine twice (Python and
JavaScript), so the suite pins the shared behaviour: taxonomy matching,
years-of-experience extraction (ranges, decimals, French forms), JD section
splitting, scoring and rounding parity, feedback generation, file-decoding
fallbacks, and an end-to-end CLI run on the sample data.

```bash
pip install -r requirements-dev.txt
python -m pytest
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the suite on
Ubuntu and Windows against Python 3.9 and 3.13, and fails if the `docs/`
data copies have drifted from `data/`.

## Project structure

```
├── main.py                   # CLI: parallel screening, CSV export
├── parsers/
│   ├── resume_parser.py      # PDF/DOCX/TXT text extraction
│   └── jd_parser.py          # JD section splitting + skill extraction
├── extractors/
│   └── keyword_extractor.py  # Taxonomy matching, years-of-experience
├── matcher/
│   ├── scorer.py             # Weighted scoring and ranking
│   └── feedback.py           # CV-improvement tip generation
├── data/
│   ├── config.json           # Weights + default expected years
│   ├── skills_taxonomy.json  # Skills database (single source of truth)
│   ├── sample_jd.txt         # Sample job description (EN)
│   └── sample_jd_fr.txt      # Sample job description (FR)
├── docs/                     # Static web app (GitHub Pages root)
│   ├── index.html / app.js / style.css
│   ├── data/                 # Synced copies of the JSONs + sample JDs
│   ├── samples/              # Synced copies of the sample résumés
│   └── vendor/               # Vendored pdf.js worker (version-locked)
├── input/sample_resumes/     # Six sample résumés (EN + FR, txt/docx/pdf)
├── output/                   # ranked_resumes.csv (CLI output, gitignored)
├── tests/                    # Pytest suite (engine, parsers, CLI e2e)
├── scripts/
│   ├── make_sample_data.py   # Regenerates the DOCX/PDF samples
│   └── sync_web_data.py      # Refreshes docs/data + docs/samples
└── .github/workflows/ci.yml  # CI: tests + docs/ sync check
```

## Error handling

| Situation | Behaviour |
|---|---|
| Corrupt or empty résumé in the batch | Warning printed; file scored as empty; run continues |
| File format not supported | Skipped with a warning |
| Résumé larger than 25 MB | Skipped with a warning (browser and CLI) — protects against memory-exhaustion files such as zip-bomb DOCX |
| Job description unreadable or empty | Clean error, exit code 1 |
| No taxonomy skills found in the JD | Clean error, exit code 1 — no partial results |
| `config.json` invalid (bad JSON, missing weights, weights ≠ 1.0) | Clear `ValueError` before scoring starts |
| Output folder not writable | Clean error, exit code 1 |
| Filename crafted as a spreadsheet formula (e.g. `=WEBSERVICE(...)`) | Neutralised in the CSV export so Excel/Sheets show it as text |
| Browser: a résumé parser hangs or fails | 30 s cap covering the whole read (open + every page); the file becomes a warning and the rest of the batch is screened |

## Limitations and responsible use

- Screening is **keyword-based**: it does not understand context or negation
  ("I have not used Docker" counts as Docker), and it only finds skills that
  are in the taxonomy.
- Scanned or image-only PDFs contain no extractable text and will score near
  zero — the feedback flags this case explicitly.
- The scoring formula is deliberately simple and transparent. Use it as a
  consistent first pass to support human review, never as an automated
  rejection decision. A fixed formula reduces inconsistency, but bias can
  still enter through the taxonomy and the job description itself.

## License

Released under the [MIT License](LICENSE).
