"""Pile 2 (kep): keps/sig-scheduling/** README.md from kubernetes/enhancements.

The KEPs are the "why" pile #1 — the documented rationale behind scheduler design.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ENH_REPO, KEP_DIR, KEP_PATH, encode_path  # noqa: E402
from github import download_raw, walk_contents  # noqa: E402


def main() -> None:
    KEP_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0
    for entry in walk_contents(ENH_REPO, KEP_PATH):
        name = entry["name"]
        # README.md carries the KEP text; kep.yaml carries number/status metadata.
        if name not in ("README.md", "kep.yaml"):
            continue
        dest = KEP_DIR / encode_path(entry["path"])
        dest.write_text(download_raw(entry["download_url"]))
        saved += 1
        print(f"  [{saved}] {entry['path']}")
    print(f"\nSaved {saved} KEP files to {KEP_DIR}")


if __name__ == "__main__":
    main()
