"""
Assemble the folder that is pushed to a Hugging Face Space: the API code,
migrations, requirements, the Space files in this directory, and a checksum
list of the three model files (the models themselves go to a separate private
model repository -- see docs/deploy-huggingface.md).

    python deploy/huggingface/build_space.py --out C:/Dev/oralsentinel-space
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MODELS = ["resnet50_oral_cancer_v7.pt", "oral_photo_gate_v1.pt", "resnet50_dysplasia_grade_v2.pt"]
# Needed only to download the models at start-up.
EXTRA_REQUIREMENTS = ["huggingface_hub==0.34.4"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    out = Path(ap.parse_args().out)
    if out.exists() and any(p.name != ".git" for p in out.iterdir()):
        for p in out.iterdir():
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "uploads")
    shutil.copytree(ROOT / "backend" / "app", out / "app", ignore=ignore)
    shutil.copytree(ROOT / "backend" / "alembic", out / "alembic", ignore=ignore)
    shutil.copy(ROOT / "backend" / "alembic.ini", out / "alembic.ini")
    reqs = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").rstrip("\n")
    (out / "requirements.txt").write_text(reqs + "\n" + "\n".join(EXTRA_REQUIREMENTS) + "\n", encoding="utf-8", newline="\n")
    for name in ("Dockerfile", "entrypoint.sh", "fetch_models.py", "README.md"):
        text = (HERE / name).read_text(encoding="utf-8")
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    (out / ".gitattributes").write_text("*.sh text eol=lf\nDockerfile text eol=lf\n", encoding="utf-8", newline="\n")

    sums = {name: sha256(ROOT / "ml" / "artifacts" / name) for name in MODELS}
    (out / "models.sha256.json").write_text(json.dumps(sums, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Space folder ready: {out}")
    print("Model files to upload to the private model repository:")
    for name in MODELS:
        print(f"  {ROOT / 'ml' / 'artifacts' / name}")


if __name__ == "__main__":
    main()
