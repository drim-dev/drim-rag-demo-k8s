"""Pile 4 (docs): kube-scheduler pages from kubernetes/website."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DOCS_DIR, DOCS_PATHS, WEB_REPO, encode_path  # noqa: E402
from github import download_raw, walk_contents  # noqa: E402


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0
    for path in DOCS_PATHS:
        try:
            entries = list(walk_contents(WEB_REPO, path))
        except Exception as e:  # a configured path may not exist on this branch
            print(f"  [skip] {path}: {e}")
            continue
        for entry in entries:
            if not entry["name"].endswith(".md"):
                continue
            dest = DOCS_DIR / encode_path(entry["path"])
            dest.write_text(download_raw(entry["download_url"]))
            saved += 1
            print(f"  [{saved}] {entry['path']}")
    print(f"\nSaved {saved} doc files to {DOCS_DIR}")


if __name__ == "__main__":
    main()
