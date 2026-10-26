"""Résumé parser for PDF, DOCX, TXT and Markdown files."""

import logging
import re
from pathlib import Path
from typing import Callable, Dict, List, Tuple, Union

from pypdf import PdfReader

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 20

_DEHYPHEN_RE = re.compile(
    r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])-\s*\n\s*(?=[a-zà-öø-ÿ])"
)


def _clean_extracted_text(text: str) -> str:
    """Normalize line endings, de-hyphenate line breaks and collapse whitespace."""
    text = text.replace("\x00", " ").replace("\u00a0", " ").replace("\u200b", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _DEHYPHEN_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def find_resume_files(
    directory: Union[str, Path], recursive: bool = False
) -> List[Path]:
    """Supported résumé files in *directory*, sorted; optionally recursive."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    files = []
    for path in iterator:
        if not path.is_file():
            continue
        if path.name.startswith(("~$", ".")):
            continue
        if path.suffix.lower() in ResumeParser.SUPPORTED_EXTENSIONS:
            files.append(path)
    return sorted(files)


def read_text_best_effort(path: Path) -> str:
    """Decode a text file as UTF-8, falling back to cp1252."""
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(
            f"{path.name} is {len(data) / 1048576:.1f} MB, over the "
            f"{MAX_FILE_BYTES // 1048576} MB cap"
        )
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore").strip()


class ResumeParser:
    """Extracts plain text from résumé files, dispatching on file extension."""

    SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".markdown")

    def parse(self, file_path: Union[str, Path]) -> str:
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        extractors: Dict[str, Callable[[Path], str]] = {
            ".pdf": self._extract_pdf,
            ".docx": self._extract_docx,
            ".txt": self._extract_txt,
            ".md": self._extract_txt,
            ".markdown": self._extract_txt,
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

        text = _clean_extracted_text(extractors[suffix](file_path))
        if not text:
            logger.warning("No text extracted from %s", file_path.name)
        return text

    def parse_directory(
        self, directory: Union[str, Path], recursive: bool = False
    ) -> List[Tuple[Path, str]]:
        results: List[Tuple[Path, str]] = []
        for file_path in find_resume_files(directory, recursive=recursive):
            try:
                results.append((file_path, self.parse(file_path)))
            except Exception as exc:
                logger.error("Failed to parse %s: %s", file_path.name, exc)
        return results

    def _extract_pdf(self, file_path: Path) -> str:
        text = ""
        with open(file_path, "rb") as file:
            pdf_reader = PdfReader(file)
            if getattr(pdf_reader, "is_encrypted", False):
                try:
                    pdf_reader.decrypt("")
                except Exception as exc:
                    raise ValueError(
                        f"{file_path.name} is an encrypted PDF"
                    ) from exc
                if getattr(pdf_reader, "is_encrypted", False):
                    raise ValueError(f"{file_path.name} is an encrypted PDF")
            pages = pdf_reader.pages[:MAX_PDF_PAGES]
            for page in pages:
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                if page_text:
                    text += page_text + "\n"
        return text.strip()

    def _extract_docx(self, file_path: Path) -> str:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(file_path)
        chunks: List[str] = []

        def emit_block(block) -> None:
            if isinstance(block, Paragraph):
                if block.text.strip():
                    chunks.append(block.text)
            elif isinstance(block, Table):
                for row in block.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        chunks.append(" | ".join(cells))

        body = doc.element.body
        for child in body.iterchildren():
            if child.tag == qn("w:p"):
                emit_block(Paragraph(child, doc))
            elif child.tag == qn("w:tbl"):
                emit_block(Table(child, doc))

        for section in doc.sections:
            for container in (section.header, section.footer):
                for paragraph in container.paragraphs:
                    if paragraph.text.strip():
                        chunks.append(paragraph.text)

        return "\n".join(chunks).strip()

    def _extract_txt(self, file_path: Path) -> str:
        return read_text_best_effort(file_path)


def parse_resume_file(file_path: str) -> Tuple[str, str, str]:
    """Parse one file for the process pool."""
    try:
        text = ResumeParser().parse(Path(file_path))
        if not text.strip():
            return file_path, "", "empty"
        return file_path, text, ""
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", file_path, exc)
        return file_path, "", str(exc)
