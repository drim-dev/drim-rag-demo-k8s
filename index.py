"""Index the four piles into Qdrant (dense + sparse), incrementally.

Usage:
    uv run python index.py --source all
    uv run python index.py --source code --force
"""

import argparse
import hashlib
import json

import chunking
import ingest
from config import CODE_DIR, DOCS_DIR, ISSUE_DIR, KEP_DIR, PILES, STATE_FILE, decode_path
from store import COLLECTION, ensure_collection, get_client


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _file_chunks(pile: str, path: str, raw: str) -> list[dict]:
    """Return chunk dicts (text + payload extras, without pile/path) for one file."""
    if pile == "code":
        chunks = chunking.chunk_go(raw)
    elif pile in ("kep", "docs"):
        chunks = chunking.chunk_markdown(raw)
    elif pile == "issue":
        chunks = chunking.chunk_thread(json.loads(raw))
    else:
        chunks = []
    if pile == "kep":
        parts = path.split("/")
        kep_number = parts[2] if len(parts) > 2 else ""
        for c in chunks:
            c["kep_number"] = kep_number
    return chunks


def _iter_files(pile: str):
    """Yield (encoded_name, original_path, raw_text) for a pile's downloaded files."""
    dirs = {"code": CODE_DIR, "kep": KEP_DIR, "docs": DOCS_DIR, "issue": ISSUE_DIR}
    directory = dirs[pile]
    if not directory.exists():
        print(f"  no data for pile '{pile}' (run scripts/download_{pile}*.py)")
        return
    if pile == "issue":
        files = sorted(directory.glob("*.json"))
    elif pile == "code":
        files = sorted(directory.glob("*.go"))
    else:  # kep, docs — markdown bodies (KEP README.md + design proposals; docs *.md)
        files = sorted(directory.glob("*.md"))
    for f in files:
        if pile == "issue":
            path = f.stem  # the issue/PR number
        else:
            path = decode_path(f.name)
        yield f.name, path, f.read_text()


def index_pile(client, pile: str, state: dict, force: bool) -> int:
    total = 0
    for enc_name, path, raw in _iter_files(pile):
        key = f"{pile}:{enc_name}"
        digest = _sha(raw.encode())
        if not force and state.get(key) == digest:
            continue

        chunks = _file_chunks(pile, path, raw)
        if not chunks:
            state[key] = digest
            continue

        total += ingest.upsert_for_path(client, pile, path, chunks)
        state[key] = digest
        print(f"  [{pile}] {path} -> {len(chunks)} chunks")
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["all", *PILES], default="all")
    parser.add_argument("--force", action="store_true", help="reindex even if unchanged")
    args = parser.parse_args()

    client = get_client()
    ensure_collection(client)
    state = _load_state()

    piles = PILES if args.source == "all" else [args.source]
    grand = 0
    for pile in piles:
        print(f"Indexing pile: {pile}")
        grand += index_pile(client, pile, state, args.force)

    _save_state(state)
    print(f"\nDone. Upserted {grand} chunks into '{COLLECTION}'.")
    print("Knowledge map: http://localhost:6333/dashboard -> scheduler_memory -> Visualize (color by `pile`)")


if __name__ == "__main__":
    main()
