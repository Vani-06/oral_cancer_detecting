"""
Download the three model files from a private Hugging Face model repository
at start-up and check each against the SHA-256 in models.sha256.json, so the
running analysis version is exactly the one that was tested.

Environment: MODEL_REPO (e.g. "your-name/oralsentinel-models"), HF_TOKEN (a
read-only token, set as a Space secret), MODEL_DIR (where to put the files).
Files already present and matching are not downloaded again.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = json.loads((HERE / "models.sha256.json").read_text(encoding="utf-8"))
DEST = Path(os.environ.get("MODEL_DIR", "/home/user/models"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def good(name: str) -> bool:
    path = DEST / name
    return path.is_file() and sha256(path) == EXPECTED[name]


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    missing = [name for name in EXPECTED if not good(name)]
    if not missing:
        print("Models already present and verified.")
        return
    repo = os.environ.get("MODEL_REPO")
    if not repo:
        sys.exit("MODEL_REPO is not set: add it as a Space variable (your-name/oralsentinel-models).")
    from huggingface_hub import hf_hub_download

    for name in missing:
        print(f"Downloading {name} from {repo} ...", flush=True)
        hf_hub_download(repo_id=repo, filename=name, local_dir=DEST, token=os.environ.get("HF_TOKEN"))
        if not good(name):
            sys.exit(f"{name} does not match the expected checksum: wrong or incomplete upload in {repo}.")
    print("Models downloaded and verified.")


if __name__ == "__main__":
    main()
