# Résumé Screening System

A bilingual (English / French) résumé screening tool that ranks candidates
against a job description using a transparent weighted formula — and tells
every candidate exactly how to improve their CV.

It ships as two frontends over one scoring engine:

| Interface | Stack | Best for |
|---|---|---|
| Command line (`main.py`) | Python, multiprocessing | Batch-screening a folder of résumés |
| Web app (`docs/`) | Static HTML/JS | Zero-install use in the browser |

No data ever leaves the machine it runs on: the CLI works on local files, and
the web app parses and scores everything in the visitor's browser.

## Features

- **PDF, DOCX, TXT and Markdown files** — the CLI reads both résumés and job
  descriptions per file, dispatching on format. Markdown headings and lists
  are understood as structure.
- **Works beyond IT** — a broad, editable skills taxonomy (27 categories,
  400+ skills) plus a term miner that pulls domain-specific requirements
  straight from the ad. Nursing, trades, finance, marketing and niche roles
  produce useful requirements even when the taxonomy has never seen them.
- **Structured job-description parsing** — required skills, preferred skills,
  experience expectations and domain keywords, from English or French JDs.
  Explicit cues such as *preferred*, *an asset* or *nice to have* override a
  Required heading, and a skill listed in both buckets is counted once.
- **Structured CV fields** — name, email, phone, location, headline,
  LinkedIn/GitHub/website, education level and history, certifications and
  languages, exported alongside every score. They help recruiters review any
  CV, even one whose domain the taxonomy does not cover.
- **Weighted, auditable scoring** — every candidate is scored with the same
  formula and the same skill taxonomy; full per-candidate breakdowns, matched
  evidence snippets and applied weights are kept.
- **CV-improvement feedback** — concrete, per-candidate tips: which required
  skills to name explicitly, what experience to quantify, which domain terms
  to work in, and which contact details are missing.
- **Fault tolerant** — unreadable files are reported and skipped; invalid
  configuration or a skill-less job description stops cleanly with a clear
  error instead of a traceback.
- **Parallel batch processing** — the CLI parses résumés across a process pool,
  optionally recursing into subdirectories.

## How it works

```
                ┌────────────────────┐
 Résumés        │   Résumé Parser    │       plain text
 (PDF/DOCX/TXT/ │ (pypdf / docx /    │ ─────────────────────┐
  MD)           │  pdf.js / mammoth) │                      ▼
                └────────────────────┘       ┌──────────────────────────┐
                ┌────────────────────┐       │  Skill matcher +         │
 Job            │     JD Parser      │       │  term miner +            │
 description    │  required/preferred│──────►│  field extractor +       │
 (TXT/MD/PDF/   │  /experience       │       │  years-of-experience     │
  DOCX)         │  /keywords         │       └───────────┬──────────────┘
                └────────────────────┘                   ▼
                                             ┌───────────────────────┐
                                             │    Scoring Engine     │
                                             │ weighted formula +    │
                                             │ CV-feedback generator │
                                             └───────────┬───────────┘
                                                         ▼
                                            Ranked results + CSV/JSON +
                                            improvement tips
```

1. **Résumé parser** extracts plain text from each file. Markdown headings
   and lists, DOCX paragraphs/tables and PDF pages are supported; text cleanup
   joins words split across line breaks and removes repeated whitespace.
2. **JD parser** splits the job description into Required / Preferred /
   Experience sections, matching section labels against whole header lines
   only. Inline headers (*Required skills: Python, Django*), Markdown
   headings, numbered lists and mixed English/French layouts are understood.
   Explicit preferred cues override a Required section, and skills in both
   buckets are subtracted from Preferred. Without explicit sections, every
   skill mentioned in the JD is treated as required.
3. **Skill matcher + term miner** matches text against the taxonomy
   case-insensitively and accent-insensitively, with word boundaries — so
   "Java" does not match inside "JavaScript", while "c++" and "c#" still
   match. Negated mentions ("no experience with Docker") are ignored, and
   optional version suffixes ("Node 18") still match. For domains the
   taxonomy does not cover, the term miner promotes the ad's own repeated,
   bulleted, capitalised or early phrases into requirements and matches them
   in CVs. Years of experience are detected too ("5+ years", "5 ans", "cinq
   années", "1,5 an"), keeping the highest figure for a CV and the lowest for
   a JD's range ("3–5 years" asks for 3).
4. **Field extractor** pulls structured contact and background details from
   each CV. Fields are exported for review but do not affect the score.
5. **Scoring engine** applies the weighted formula, drops empty categories,
   and ranks candidates.
6. **Feedback generator** converts each score breakdown into actionable CV
   advice, including missing contact details and a warning when a file looks
   like a scanned image with no readable text.

## Scoring model

```
Total Score = (Required Skills × 50%)
            + (Preferred Skills × 25%)
            + (Experience      × 15%)
            + (Keywords        × 10%)
```

| Component | Default weight | What it measures |
|---|---|---|
| Required skills | 50% | Share of the JD's required skills found in the CV |
| Preferred skills | 25% | Share of the JD's preferred skills found in the CV |
| Experience | 15% | Years detected in the CV ÷ years requested in the JD (capped at 1.0); a JD range like "3–5 years" sets the bar at its lower bound |
| Keywords | 10% | Share of the JD's domain keywords found in the CV |

Each component is a coverage ratio between 0 and 1, so the total score is
always between 0 and 100. Empty categories are **not** free points: when a JD
has no preferred skills, no keywords, or no stated experience requirement,
that component is dropped and the remaining weights are re-normalized to
100%. The applied weights are shown in the console and exported per
candidate. Because the same weights, taxonomy and formula apply to every
candidate, the ranking is consistent, reproducible and auditable — the full
breakdown (matched and missing skills per candidate, with evidence snippets)
is included in the CSV and JSON output.

## Bilingual support (English / Français)

- Matching is **accent-insensitive**: "développement", "DEVELOPPEMENT" and
  "developpement" are equivalent.
- The JD parser recognises French section headers: *Compétences requises*,
  *Compétences souhaitées*, *Atouts*, *Expérience*, and inline forms such as
  *Compétences requises : Python, Django*.
- The taxonomy contains French synonyms for most skills (*api rest*,
  *intégration continue*, *tests unitaires*, *travail d'équipe*, …).
- Field extraction understands French labels and formats: *Formation*,
  *Certifications*, *Langues*, *Lieu*, *Poste*, and French credentials such
  as *DEP*, *AEP*, *ASP* and *CÉGEP*.
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
  --jd         Path to the job description (TXT, MD, PDF or DOCX). Required.
  --input      Directory of résumés to screen (default: input).
  --recursive  Also search subdirectories of --input.
  --output     Directory for ranked_resumes.csv (default: output).
  --workers    Parallel parse processes (default: CPU count, capped at 8).
  --taxonomy   Optional custom skills taxonomy JSON.
  --config     Optional custom weights JSON.
  --json       Print machine-readable JSON instead of the table.
```

The run prints the extracted requirements, the ranked table and per-candidate
improvement tips, then writes `ranked_resumes.csv` with columns for each
score component, matched/missing skills, evidence snippets, extracted CV
fields (contact details, links, education, certifications, languages) and the
tips. With `--json`, the full result is printed as JSON and the CSV export is
skipped.

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
ranking, per-candidate breakdowns, extracted CV fields and CV-improvement
tips. It accepts PDF, DOCX, TXT and Markdown files. Files are never uploaded
anywhere. To publish it, serve the `docs/` folder with any static host — the
PDF and DOCX readers load from a CDN; TXT/Markdown screening works fully
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

- Screening is **keyword- and phrase-based**. Simple negation ("no experience
  with Docker") is handled, but irony, implication and complex sentence
  context are not. Taxonomy matches only find skills in the taxonomy; term
  mining covers other domains, at the cost of occasionally promoting an
  unusual phrase from the ad.
- Field extraction is intentionally conservative: an empty field is preferred
  over a wrong one, so unusual layouts may leave some details blank. Review
  the extracted fields before relying on them.
- Scanned or image-only PDFs contain no extractable text and will score near
  zero — the feedback flags this case explicitly.
- The scoring formula is deliberately simple and transparent. Use it as a
  consistent first pass to support human review, never as an automated
  rejection decision. A fixed formula reduces inconsistency, but bias can
  still enter through the taxonomy and the job description itself.

## License

Released under the [MIT License](LICENSE).
