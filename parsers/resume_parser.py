"""Résumé parser: extracts plain text from PDF, DOCX and TXT files.

A JavaScript mirror of this module (fileToText) lives in docs/app.js —
keep the two in sync when changing parsing behaviour.
"""

import logging
from pathlib import Path
from typing import Callable, Dict, List, Tuple, Union

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Oversized files are almost never legitimate résumés and can be crafted to
# exhaust memory (e.g. zip-bomb DOCX), so parsing refuses them outright.
# Keep in sync with MAX_FILE_BYTES in docs/app.js.
MAX_FILE_BYTES = 25 * 1024 * 1024


def read_text_best_effort(path: Path) -> str:
    """Decode a text file as UTF-8, falling back to cp1252.

    Windows French CVs and job descriptions are often cp1252, where
    errors="ignore" alone would silently eat accented characters mid-word.
    Bytes no codec can decode are dropped.
    """
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore").strip()


class ResumeParser:
    """Extracts plain text from résumé files, dispatching on file extension."""

    SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt")

    def parse(self, file_path: Union[str, Path]) -> str:
        """Parse a single résumé file and return its text content."""
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        extractors: Dict[str, Callable[[Path], str]] = {
            ".pdf": self._extract_pdf,
            ".docx": self._extract_docx,
            ".txt": self._extract_txt,
        }

        if suffix not in extractors:
            raise ValueError(
                f"Unsupported file type '{suffix}': {file_path.name}. "
                f"Supported types: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )

        size = file_path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ValueError(
                f"{file_path.name} is {size / 1048576:.1f} MB, over the "
                f"{MAX_FILE_BYTES // 1048576} MB cap"
            )

        text = extractors[suffix](file_path)
        if not text:
            logger.warning("No text extracted from %s", file_path.name)
        return text

    def parse_directory(self, directory: Union[str, Path]) -> List[Tuple[Path, str]]:
        """Parse every supported file in *directory* (non-recursive)."""
        directory = Path(directory)
        results: List[Tuple[Path, str]] = []
        for file_path in sorted(directory.iterdir()):
            if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue
            try:
                results.append((file_path, self.parse(file_path)))
            except Exception as exc:  # keep going when one file is corrupt
                logger.error("Failed to parse %s: %s", file_path.name, exc)
        return results

    def _extract_pdf(self, file_path: Path) -> str:
        text = ""
        with open(file_path, "rb") as file:
            pdf_reader = PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()

    def _extract_docx(self, file_path: Path) -> str:
        from docx import Document

        doc = Document(file_path)
        return "\n".join(
            para.text for para in doc.paragraphs
        ).strip()

    def _extract_txt(self, file_path: Path) -> str:
        return read_text_best_effort(file_path)


def parse_resume_file(file_path: str) -> Tuple[str, str]:
    """Top-level worker for multiprocessing.Pool (must stay picklable)."""
    try:
        return file_path, ResumeParser().parse(Path(file_path))
    except Exception as exc:
        print(f"[warn] Failed to parse {file_path}: {exc}")
        return file_path, ""
