"""Copy canonical data/ and sample résumés into docs/ for the static app."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def main() -> None:
    data_src = ROOT / "data"
    data_dst = DOCS / "data"
    data_dst.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "skills_taxonomy.json", "sample_jd.txt", "sample_jd_fr.txt"):
        shutil.copy2(data_src / name, data_dst / name)

    samples_src = ROOT / "input" / "sample_resumes"
    samples_dst = DOCS / "samples"
    samples_dst.mkdir(parents=True, exist_ok=True)
    for path in samples_src.iterdir():
        if path.is_file():
            shutil.copy2(path, samples_dst / path.name)
    print("Synced data/ and sample résumés into docs/.")


if __name__ == "__main__":
    main()
