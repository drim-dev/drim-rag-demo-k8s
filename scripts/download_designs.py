"""Pile 2 supplement: canonical design proposals from kubernetes/design-proposals-archive.

These carry the documented rationale AND rejected approaches (the killer-demo target,
e.g. why cross-node preemption was turned down). Saved into the kep pile.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests  # noqa: E402

from config import DESIGN_FILES, DESIGN_REPO, KEP_DIR, encode_path  # noqa: E402
from github import download_raw  # noqa: E402


def _fetch(path: str) -> str:
    # The archive's default branch has varied; try main then master.
    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{DESIGN_REPO}/{branch}/{path}"
        try:
            return download_raw(url)
        except requests.HTTPError:
            continue
    raise RuntimeError(f"could not fetch {path} from {DESIGN_REPO} (main/master)")


def main() -> None:
    KEP_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0
    for path in DESIGN_FILES:
        dest = KEP_DIR / encode_path(path)
        dest.write_text(_fetch(path))
        saved += 1
        print(f"  [{saved}] {path}")
    print(f"\nSaved {saved} design proposals to {KEP_DIR}")


if __name__ == "__main__":
    main()
