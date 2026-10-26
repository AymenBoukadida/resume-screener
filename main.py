"""Command-line interface for batch résumé screening."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from extractors.fields import extract_fields
from extractors.keyword_extractor import KeywordExtractor
from extractors.term_miner import match_terms_detailed
from matcher.feedback import generate_feedback
from matcher.scorer import (
    COMPONENT_LABELS,
    CandidateScore,
    ScoringEngine,
    round_half_up,
)
from parsers.jd_parser import JDParser, JobRequirements
from parsers.resume_parser import (
    ResumeParser,
    find_resume_files,
    parse_resume_file,
    read_text_best_effort,
)

PARSE_TIMEOUT_S = 30
DECISION_NOTICE = (
    "Decision-support only — not an automated hiring or rejection decision. "
    "A human must review every score."
)


JD_EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".markdown")


def load_jd_text(jd_path: Path) -> str:
    """Load a job description from TXT, Markdown, PDF or DOCX."""
    suffix = jd_path.suffix.lower()
    if suffix not in JD_EXTENSIONS:
        raise ValueError(
            f"unsupported job-description type '{suffix}'; use "
            f"{', '.join(JD_EXTENSIONS)}"
        )
    if suffix in (".pdf", ".docx"):
        return ResumeParser().parse(jd_path)
    return read_text_best_effort(jd_path)


def _parse_batch(paths: List[str], workers: int) -> List[Tuple[str, str, str]]:
    if workers > 1 and len(paths) > 1:
        parsed: List[Tuple[str, str, str]] = []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(parse_resume_file, path) for path in paths]
            for path, future in zip(paths, futures):
                try:
                    parsed.append(future.result(timeout=PARSE_TIMEOUT_S))
                except FuturesTimeout:
                    parsed.append((path, "", f"timed out after {PARSE_TIMEOUT_S}s"))
                except Exception as exc:
                    parsed.append((path, "", str(exc)))
        return parsed
    return [parse_resume_file(path) for path in paths]


def run_screening(
    jd_text: str,
    resume_paths: List[Path],
    workers: int = 0,
    extractor: KeywordExtractor | None = None,
    engine: ScoringEngine | None = None,
) -> Tuple[JobRequirements, List[CandidateScore], pd.DataFrame, list]:
    extractor = extractor or KeywordExtractor()
    engine = engine or ScoringEngine()
    requirements = JDParser(extractor).parse(jd_text)

    paths = [str(path) for path in resume_paths]
    parsed = _parse_batch(paths, workers)

    candidates = []
    for path_str, text, note in parsed:
        detailed = extractor.extract_skills_detailed(text)
        mined = match_terms_detailed(text, requirements.mined_terms)
        skills = set(detailed) | set(mined)
        evidence = {**detailed, **mined}
        years = extractor.extract_experience_years(text)
        fields = extract_fields(text).as_dict()
        if note == "empty":
            status, parse_note = "empty", "no readable text (scanned image?)"
        elif note:
            status, parse_note = "error", note
        else:
            status, parse_note = "ok", ""
        candidates.append(
            engine.score_candidate(
                Path(path_str).name,
                skills,
                years,
                requirements,
                evidence=evidence,
                parse_status=status,
                parse_note=parse_note,
                fields=fields,
            )
        )

    ranked = engine.rank(candidates)
    feedback = [
        generate_feedback(
            candidate,
            requirements,
            engine.default_expected_years,
            fields=candidate.fields,
        )
        for candidate in ranked
    ]
    labels = _weight_labels(
        ranked[0].applied_weights if ranked else engine.weights
    )
    dataframe = pd.DataFrame(
        [
            _candidate_row(rank, candidate, tips, labels)
            for rank, (candidate, tips) in enumerate(zip(ranked, feedback), 1)
        ]
    )
    return requirements, ranked, dataframe, feedback


def _weight_labels(weights: dict) -> dict:
    names = {
        "required_skills": "Required",
        "preferred_skills": "Preferred",
        "experience": "Experience",
        "keywords": "Keywords",
    }
    return {key: f"{name} ({weights[key] * 100:g}%)" for key, name in names.items()}


def _csv_safe(value: str) -> str:
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _evidence_cell(candidate: CandidateScore) -> str:
    parts = []
    for skill in sorted(candidate.matched_required | candidate.matched_preferred):
        snippet = candidate.evidence.get(skill, "")
        parts.append(f"{skill}: {snippet}" if snippet else skill)
    return _csv_safe(" | ".join(parts))


def _field_text(fields: dict, key: str) -> str:
    return _csv_safe(str(fields.get(key, "") or ""))


def _field_list(fields: dict, key: str) -> str:
    value = fields.get(key) or []
    if isinstance(value, (list, tuple)):
        return _csv_safe(" | ".join(str(item) for item in value))
    return _csv_safe(str(value))


def _candidate_row(
    rank: int, candidate: CandidateScore, feedback: List[str], labels: dict
) -> dict:
    fields = candidate.fields
    return {
        "Rank": rank,
        "Resume": _csv_safe(candidate.filename),
        "Name": _field_text(fields, "name"),
        "Email": _field_text(fields, "email"),
        "Phone": _field_text(fields, "phone"),
        "Location": _field_text(fields, "location"),
        "Headline": _field_text(fields, "headline"),
        "LinkedIn": _field_text(fields, "linkedin"),
        "GitHub": _field_text(fields, "github"),
        "Website": _field_text(fields, "website"),
        "Education level": _field_text(fields, "education_level"),
        "Education": _field_list(fields, "education"),
        "Certifications": _field_list(fields, "certifications"),
        "Languages": _field_list(fields, "languages"),
        "Score": candidate.total,
        "Status": candidate.parse_status,
        labels["required_skills"]: round_half_up(candidate.required_score * 100, 1),
        labels["preferred_skills"]: round_half_up(candidate.preferred_score * 100, 1),
        labels["experience"]: round_half_up(candidate.experience_score * 100, 1),
        labels["keywords"]: round_half_up(candidate.keyword_score * 100, 1),
        "Years": candidate.experience_years,
        "Matched required": _csv_safe(", ".join(sorted(candidate.matched_required))),
        "Missing required": _csv_safe(", ".join(sorted(candidate.missing_required))),
        "Matched preferred": _csv_safe(", ".join(sorted(candidate.matched_preferred))),
        "Evidence": _evidence_cell(candidate),
        "Suggestions": _csv_safe(" | ".join(feedback)),
        "Notice": DECISION_NOTICE,
    }


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank résumés against a job description (PDF/DOCX/TXT/MD)."
    )
    parser.add_argument(
        "--jd",
        required=True,
        help="Job description file (TXT, MD, PDF or DOCX)",
    )
    parser.add_argument(
        "--input", default="input", help="Directory containing résumés (default: input)"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Also search subdirectories of --input for résumés",
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
    parser.add_argument(
        "--taxonomy",
        help="Optional custom skills taxonomy JSON (replaces data/skills_taxonomy.json)",
    )
    parser.add_argument(
        "--config",
        help="Optional custom weights JSON (replaces data/config.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the table",
    )
    return parser.parse_args(argv)


def _configure_console_encoding() -> None:
    """Use UTF-8 for accents on Windows terminals when possible."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main(argv=None) -> int:
    _configure_console_encoding()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    jd_path = Path(args.jd)
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    if not jd_path.is_file():
        print(f"error: job description not found: {jd_path}", file=sys.stderr)
        return 1
    resume_files = find_resume_files(input_dir, recursive=args.recursive)
    if not resume_files:
        print(f"error: no résumés found in {input_dir}", file=sys.stderr)
        return 1

    try:
        extractor = (
            KeywordExtractor(taxonomy_path=args.taxonomy)
            if args.taxonomy
            else KeywordExtractor()
        )
        engine = ScoringEngine(config_path=args.config) if args.config else ScoringEngine()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

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
            jd_text, resume_files, args.workers, extractor, engine
        )
        elapsed = time.perf_counter() - start
    except Exception as exc:
        print(f"error: screening failed: {exc}", file=sys.stderr)
        return 1

    if not (requirements.required_skills or requirements.preferred_skills
            or requirements.keywords):
        print(
            "error: no skills were found in the job description, so candidates "
            "cannot be ranked. Add a Required section or pass --taxonomy.",
            file=sys.stderr,
        )
        return 1

    if args.json:
        payload = {
            "notice": DECISION_NOTICE,
            "warnings": requirements.warnings,
            "requirements": {
                "required": sorted(requirements.required_skills),
                "preferred": sorted(requirements.preferred_skills),
                "keywords": sorted(requirements.keywords),
                "experience_years": requirements.experience_years,
                "has_explicit_sections": requirements.has_explicit_sections,
            },
            "candidates": [
                {
                    "rank": i,
                    "filename": c.filename,
                    "score": c.total,
                    "status": c.parse_status,
                    "years": c.experience_years,
                    "matched_required": sorted(c.matched_required),
                    "missing_required": sorted(c.missing_required),
                    "evidence": c.evidence,
                    "fields": c.fields,
                    "tips": tips,
                    "applied_weights": c.applied_weights,
                }
                for i, (c, tips) in enumerate(zip(ranked, feedback), 1)
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"\n{DECISION_NOTICE}\n")
    print("=== Job requirements extracted ===")
    print(f"  Required skills : {', '.join(sorted(requirements.required_skills)) or '-'}")
    print(f"  Preferred skills: {', '.join(sorted(requirements.preferred_skills)) or '-'}")
    print(f"  Keywords        : {', '.join(sorted(requirements.keywords)) or '-'}")
    print(f"  Experience      : {requirements.experience_years or 'not specified'}")
    if ranked:
        weights = ranked[0].applied_weights
        print(
            "  Applied weights : "
            + ", ".join(
                f"{COMPONENT_LABELS[k]} {weights[k]*100:.1f}%"
                for k in weights if weights[k]
            )
        )
        if ranked[0].dropped_components:
            print(
                "  Dropped (empty) : "
                + ", ".join(ranked[0].dropped_components)
                + " — remaining weights re-normalized to 100%"
            )
    for warning in requirements.warnings:
        print(f"  [warn] {warning}", file=sys.stderr)

    print(f"\nScreened {len(ranked)} résumés with {args.workers} worker(s) "
          f"in {elapsed:.2f}s\n")
    display_cols = [
        col for col in dataframe.columns
        if col not in (
            "Matched required", "Missing required", "Matched preferred",
            "Suggestions", "Evidence", "Notice", "Phone", "Location",
            "Headline", "LinkedIn", "GitHub", "Website", "Education",
            "Certifications", "Languages",
        )
    ]
    print(dataframe[display_cols].to_string(index=False))

    print("\n=== How each candidate can improve their CV ===")
    for candidate, tips in zip(ranked, feedback):
        print(f"\n{candidate.filename} (score {candidate.total}, {candidate.parse_status}):")
        fields = candidate.fields
        details = []
        for label, key in (
            ("Name", "name"), ("Email", "email"), ("Phone", "phone"),
            ("Location", "location"), ("Headline", "headline"),
            ("Education", "education_level"),
        ):
            value = str(fields.get(key) or "").strip()
            if value:
                details.append(f"{label}: {value}")
        languages = fields.get("languages") or []
        if languages:
            details.append("Languages: " + ", ".join(str(x) for x in languages))
        if details:
            print("  " + " | ".join(details))
        for skill in sorted(candidate.matched_required)[:6]:
            snippet = candidate.evidence.get(skill)
            if snippet:
                print(f"  evidence [{skill}]: {snippet}")
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
