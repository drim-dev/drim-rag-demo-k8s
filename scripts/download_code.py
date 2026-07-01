"""Pile 1 (code): pkg/scheduler/**.go from kubernetes/kubernetes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CODE_DIR, CODE_PATH, K8S_REPO, SKIP_GO_TESTS, encode_path  # noqa: E402
from github import download_raw, walk_contents  # noqa: E402


def main() -> None:
    CODE_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0
    for entry in walk_contents(K8S_REPO, CODE_PATH):
        path = entry["path"]
        if not path.endswith(".go"):
            continue
        if SKIP_GO_TESTS and path.endswith("_test.go"):
            continue
        dest = CODE_DIR / encode_path(path)  # encoded path is the filename; ext stays .go
        dest.write_text(download_raw(entry["download_url"]))
        saved += 1
        print(f"  [{saved}] {path}")
    print(f"\nSaved {saved} Go files to {CODE_DIR}")


if __name__ == "__main__":
    main()
