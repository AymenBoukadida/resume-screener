"""Copy the taxonomy, config, sample JD and sample résumés into docs/ so the
static web app (GitHub Pages) serves the same data the Python CLI uses.

Run this after editing anything in data/ or input/sample_resumes/.
"""

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

COPY_JOBS = [
    (PROJECT_ROOT / "data" / "config.json", PROJECT_ROOT / "docs" / "data" / "config.json"),
    (PROJECT_ROOT / "data" / "skills_taxonomy.json", PROJECT_ROOT / "docs" / "data" / "skills_taxonomy.json"),
    (PROJECT_ROOT / "data" / "sample_jd.txt", PROJECT_ROOT / "docs" / "data" / "sample_jd.txt"),
    (PROJECT_ROOT / "data" / "sample_jd_fr.txt", PROJECT_ROOT / "docs" / "data" / "sample_jd_fr.txt"),
]

SAMPLES_SRC = PROJECT_ROOT / "input" / "sample_resumes"
SAMPLES_DST = PROJECT_ROOT / "docs" / "samples"


def main() -> int:
    for src, dst in COPY_JOBS:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"copied {src.relative_to(PROJECT_ROOT)} -> {dst.relative_to(PROJECT_ROOT)}")

    SAMPLES_DST.mkdir(parents=True, exist_ok=True)
    for src in sorted(SAMPLES_SRC.iterdir()):
        if src.suffix.lower() in {".pdf", ".docx", ".txt"}:
            shutil.copy2(src, SAMPLES_DST / src.name)
            print(f"copied {src.relative_to(PROJECT_ROOT)} -> {(SAMPLES_DST / src.name).relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
