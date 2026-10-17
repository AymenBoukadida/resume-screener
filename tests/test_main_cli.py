"""End-to-end tests for the command-line pipeline."""

import shutil
from pathlib import Path

import pandas as pd

import main as main_module
from main import _csv_safe, main

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_sample_run_ranks_alice_first(tmp_path):
    rc = main([
        "--jd", str(PROJECT_ROOT / "data" / "sample_jd.txt"),
        "--input", str(PROJECT_ROOT / "input" / "sample_resumes"),
        "--output", str(tmp_path),
    ])
    assert rc == 0
    csv_path = tmp_path / "ranked_resumes.csv"
    assert csv_path.is_file()
    results = pd.read_csv(csv_path)
    assert results.iloc[0]["Resume"] == "alice_strong_match.txt"
    # Column percentages must follow the loaded weights, not hardcoded values.
    assert "Required (50%)" in results.columns


def test_formula_filenames_are_neutralised_in_csv(tmp_path):
    input_dir = tmp_path / "resumes"
    input_dir.mkdir()
    shutil.copy(
        PROJECT_ROOT / "input" / "sample_resumes" / "alice_strong_match.txt",
        input_dir / "=1+1.txt",
    )
    rc = main([
        "--jd", str(PROJECT_ROOT / "data" / "sample_jd.txt"),
        "--input", str(input_dir),
        "--output", str(tmp_path / "out"),
    ])
    assert rc == 0
    raw = (tmp_path / "out" / "ranked_resumes.csv").read_text(encoding="utf-8-sig")
    assert "'=1+1.txt" in raw  # apostrophe prefix keeps Excel from executing it


def test_csv_safe_prefixes_formula_characters():
    for dangerous in ("=cmd()", "+SUM(A1)", "-1+1", "@WEBSERVICE(\"x\")"):
        assert _csv_safe(dangerous).startswith("'")
    assert _csv_safe("alice_cv.txt") == "alice_cv.txt"


def test_missing_jd_fails_cleanly(tmp_path, capsys):
    rc = main(["--jd", str(tmp_path / "nope.txt"), "--input", str(tmp_path)])
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_main_module_importable():
    # Guards the multiprocessing Pool path on Windows (spawn re-imports).
    assert callable(main_module.main)
