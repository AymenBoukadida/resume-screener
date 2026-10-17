# Résumé Screening System

A bilingual (English / French) résumé screening tool that ranks candidates
against a job description using a fixed, transparent scoring formula — and
tells every candidate exactly how to improve their CV.

It ships as two frontends over one scoring engine:

| Interface | Stack | Best for |
|---|---|---|
| Command line (`main.py`) | Python, multiprocessing | Batch-screening a folder of résumés |
| Web app (`docs/`) | Static HTML/JS | Zero-install use in the browser |

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
uploaded anywhere. To publish it, serve the `docs/` folder with any static
host — the PDF and DOCX readers load from a CDN; TXT screening works fully
offline.

## Tech stack

- **CLI** — Python 3.9+; [pypdf](https://pypi.org/project/pypdf/) for PDF text
  extraction, [python-docx](https://pypi.org/project/python-docx/) for DOCX,
  [pandas](https://pypi.org/project/pandas/) for the CSV export, and
  `multiprocessing` for parallel batch parsing.
- **Web app** — vanilla HTML/CSS/JavaScript, no framework and no build step;
  [pdf.js](https://mozilla.github.io/pdf.js/) for PDF reading and
  [mammoth.js](https://github.com/mwilliamson/mammoth.js) for DOCX reading,
  both loaded from a CDN with Subresource Integrity pins (the pdf.js worker
  is vendored in `docs/vendor/`); deployable as plain static files.
- **Shared engine data** — a JSON skills taxonomy and a JSON weights config
  shared by both frontends (the web app serves synced copies from
  `docs/data/`).

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
