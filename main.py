"""Command-line interface for batch résumé screening.

Résumés in a folder are parsed in parallel with multiprocessing, scored
against the job description, and exported as a ranked CSV.
"""

import argparse
import logging
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from extractors.keyword_extractor import KeywordExtractor
from matcher.feedback import generate_feedback
from matcher.scorer import CandidateScore, ScoringEngine, round_half_up
from parsers.jd_parser import JDParser, JobRequirements
from parsers.resume_parser import ResumeParser, parse_resume_file, read_text_best_effort

logger = logging.getLogger(__name__)


def load_jd_text(jd_path: Path) -> str:
    """Load a job description from a TXT or PDF file."""
    if jd_path.suffix.lower() == ".pdf":
        return ResumeParser().parse(jd_path)
    return read_text_best_effort(jd_path)


def run_screening(
    jd_text: str, resume_paths: List[Path], workers: int = 0
) -> Tuple[JobRequirements, List[CandidateScore], pd.DataFrame, dict]:
    """Parse, extract, score and rank résumés against the JD text.

    Uses a multiprocessing pool when *workers* > 1; otherwise parses
    sequentially. Returns the requirements, the ranked candidates, the
    results table and per-candidate improvement tips aligned by position
    with the ranked candidates (an input folder can hold duplicate
    basenames, so filenames are not safe keys).
    """
    extractor = KeywordExtractor()
    requirements = JDParser(extractor).parse(jd_text)
    engine = ScoringEngine()

    paths = [str(path) for path in resume_paths]
    if workers > 1 and len(paths) > 1:
        with Pool(processes=workers) as pool:
            parsed = pool.map(parse_resume_file, paths)
    else:
        # Per-file failures stay isolated, as with the pool.
        parsed = [parse_resume_file(path) for path in paths]

    unreadable = [
        Path(path_str).name for path_str, text in parsed if not text.strip()
    ]
    if unreadable:
        print(
            f"[warn] {len(unreadable)} file(s) could not be read and were "
            f"scored as empty: {', '.join(unreadable)}",
            file=sys.stderr,
        )

    candidates = []
    for path_str, text in parsed:
        skills = extractor.extract_skills(text)
        years = extractor.extract_experience_years(text)
        candidates.append(
            engine.score_candidate(Path(path_str).name, skills, years, requirements)
        )

    ranked = engine.rank(candidates)
    feedback = [
        generate_feedback(candidate, requirements, engine.default_expected_years)
        for candidate in ranked
    ]
    labels = _weight_labels(engine.weights)
    dataframe = pd.DataFrame(
        [
            _candidate_row(rank, candidate, tips, labels)
            for rank, (candidate, tips) in enumerate(zip(ranked, feedback), 1)
        ]
    )
    return requirements, ranked, dataframe, feedback


def _weight_labels(weights: dict) -> dict:
    """Column labels whose percentages always match the loaded weights."""
    names = {
        "required_skills": "Required",
        "preferred_skills": "Preferred",
        "experience": "Experience",
        "keywords": "Keywords",
    }
    return {key: f"{name} ({weights[key] * 100:g}%)" for key, name in names.items()}


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection: a cell starting with
    =, +, - or @ (e.g. a crafted filename) would execute as a formula when
    the CSV is opened in Excel or Google Sheets."""
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _candidate_row(
    rank: int, candidate: CandidateScore, feedback: List[str], labels: dict
) -> dict:
    return {
        "Rank": rank,
        "Resume": _csv_safe(candidate.filename),
        "Score": candidate.total,
        labels["required_skills"]: round_half_up(candidate.required_score * 100, 1),
        labels["preferred_skills"]: round_half_up(candidate.preferred_score * 100, 1),
        labels["experience"]: round_half_up(candidate.experience_score * 100, 1),
        labels["keywords"]: round_half_up(candidate.keyword_score * 100, 1),
        "Years": candidate.experience_years,
        "Matched required": _csv_safe(", ".join(sorted(candidate.matched_required))),
        "Missing required": _csv_safe(", ".join(sorted(candidate.missing_required))),
        "Matched preferred": _csv_safe(", ".join(sorted(candidate.matched_preferred))),
        "Suggestions": _csv_safe(" | ".join(feedback)),
    }


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank résumés against a job description (PDF/DOCX/TXT)."
    )
    parser.add_argument("--jd", required=True, help="Job description file (TXT or PDF)")
    parser.add_argument(
        "--input", default="input", help="Directory containing résumés (default: input)"
    )
    parser.add_argument(
        "--output", default="output", help="Directory for the ranked CSV (default: output)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(os.cpu_count() or 1, 8),
        help="Number of parallel worker processes (default: CPU count, capped at 8)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    jd_path = Path(args.jd)
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    if not jd_path.is_file():
        print(f"error: job description not found: {jd_path}", file=sys.stderr)
        return 1
    resume_files = sorted(
        path for path in input_dir.iterdir()
        if path.suffix.lower() in ResumeParser.SUPPORTED_EXTENSIONS
    ) if input_dir.is_dir() else []
    if not resume_files:
        print(f"error: no résumés found in {input_dir}", file=sys.stderr)
        return 1

    jd_text = ""
    try:
        jd_text = load_jd_text(jd_path)
    except Exception as exc:
        print(f"error: could not read the job description {jd_path}: {exc}",
              file=sys.stderr)
        return 1
    if not jd_text.strip():
        print(f"error: the job description file is empty: {jd_path}",
              file=sys.stderr)
        return 1

    try:
        start = time.perf_counter()
        requirements, ranked, dataframe, feedback = run_screening(
            jd_text, resume_files, args.workers
        )
        elapsed = time.perf_counter() - start
    except Exception as exc:
        print(f"error: screening failed: {exc}", file=sys.stderr)
        return 1

    if not (requirements.required_skills or requirements.preferred_skills
            or requirements.keywords):
        print(
            "error: no skills from the taxonomy were found in the job "
            "description, so candidates cannot be ranked. Check the JD text "
            "or extend data/skills_taxonomy.json.",
            file=sys.stderr,
        )
        return 1

    print("\n=== Job requirements extracted ===")
    print(f"  Required skills : {', '.join(sorted(requirements.required_skills)) or '-'}")
    print(f"  Preferred skills: {', '.join(sorted(requirements.preferred_skills)) or '-'}")
    print(f"  Keywords        : {', '.join(sorted(requirements.keywords)) or '-'}")
    print(f"  Experience      : {requirements.experience_years or 'not specified'}")

    print(f"\nScreened {len(ranked)} résumés with {args.workers} worker(s) "
          f"in {elapsed:.2f}s\n")
    print(dataframe.drop(columns=["Matched required", "Missing required",
                                  "Matched preferred", "Suggestions"]).to_string(index=False))

    print("\n=== How each candidate can improve their CV ===")
    for candidate, tips in zip(ranked, feedback):
        print(f"\n{candidate.filename} (score {candidate.total}):")
        for tip in tips:
            print(f"  - {tip}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "ranked_resumes.csv"
        dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")
    except OSError as exc:
        print(f"error: could not write results to {output_dir}: {exc}",
              file=sys.stderr)
        return 1
    print(f"\nFull results written to {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
