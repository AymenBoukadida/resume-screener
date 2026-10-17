"""Tests for PDF/DOCX/TXT text extraction and its hardening."""

from pathlib import Path

import pytest

import parsers.resume_parser as resume_parser_module
from parsers.resume_parser import ResumeParser

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def parser():
    return ResumeParser()


class TestTxtDecoding:
    def test_utf8_with_bom(self, parser, tmp_path):
        path = tmp_path / "cv.txt"
        path.write_bytes(b"\xef\xbb\xbfPython developer")
        assert parser.parse(path) == "Python developer"

    def test_cp1252_fallback_preserves_accents(self, parser, tmp_path):
        # A cp1252-encoded French CV: errors="ignore" alone would mangle
        # "Génie" into "Gnie".
        path = tmp_path / "cv.txt"
        path.write_bytes("Génie logiciel - Python".encode("cp1252"))
        assert parser.parse(path) == "Génie logiciel - Python"


class TestSizeCap:
    def test_oversized_file_rejected(self, parser, tmp_path, monkeypatch):
        path = tmp_path / "huge.txt"
        path.write_text("x" * 100)
        monkeypatch.setattr(resume_parser_module, "MAX_FILE_BYTES", 10)
        with pytest.raises(ValueError, match="MB cap"):
            parser.parse(path)


class TestUnsupportedType:
    def test_rejected_with_clear_message(self, parser, tmp_path):
        path = tmp_path / "photo.rtf"
        path.write_text("anything")
        with pytest.raises(ValueError, match="Unsupported file type"):
            parser.parse(path)


class TestCommittedSamples:
    def test_pdf_sample(self, parser):
        path = PROJECT_ROOT / "input" / "sample_resumes" / "emma_pdf_candidate.pdf"
        assert "Emma Novak" in parser.parse(path)

    def test_docx_sample(self, parser):
        path = PROJECT_ROOT / "input" / "sample_resumes" / "david_docx_candidate.docx"
        assert "David Okafor" in parser.parse(path)
