"""Shared ingest: chunk → embed (dense+sparse) → upsert into Qdrant.

Used by both the batch indexer (index.py) and the live-update worker (worker.py),
so the indexing logic lives in exactly one place.
"""

import json

from qdrant_client import models

import chunking
from config import COLLECTION, ISSUE_DIR, K8S_REPO
from embeddings import embed_dense, embed_sparse
from github import API, gh_get, paginate
from store import make_point_id, upsert_points

BATCH = 64


def upsert_for_path(client, pile: str, path: str, chunks: list[dict]) -> int:
    """Replace all points for (pile, path) with freshly embedded chunks. Idempotent."""
    client.delete(
        collection_name=COLLECTION,
        points_selector=models.FilterSelector(filter=models.Filter(
            must=[models.FieldCondition(key="path", match=models.MatchValue(value=path))]
        )),
    )
    total = 0
    for start in range(0, len(chunks), BATCH):
        sub = chunks[start:start + BATCH]
        texts = [c["text"] for c in sub]
        dense = embed_dense(texts)
        sparse = embed_sparse(texts)
        points = []
        for i, c in enumerate(sub):
            points.append({
                "id": make_point_id(pile, path, start + i),
                "dense": dense[i],
                "sparse": sparse[i],
                "payload": {**c, "pile": pile, "path": path},
            })
        upsert_points(client, points)
        total += len(points)
    return total


def fetch_issue(number: int) -> dict:
    """Fetch a single issue/PR (body + comment thread) from GitHub."""
    issue = gh_get(f"{API}/repos/{K8S_REPO}/issues/{number}").json()
    kind = "pr" if "pull_request" in issue else "issue"
    comments = []
    if issue.get("comments", 0):
        for c in paginate(issue["comments_url"]):
            comments.append({"author": c["user"]["login"], "body": c["body"] or ""})
    return {
        "number": number,
        "kind": kind,
        "title": issue["title"],
        "state": issue["state"],
        "updated_at": issue["updated_at"],
        "author": issue["user"]["login"],
        "body": issue["body"] or "",
        "comments": comments,
    }


def index_issue_number(client, number: int) -> int:
    """Live-update path: fetch one issue/PR from GitHub, re-chunk, re-embed, upsert."""
    record = fetch_issue(number)
    ISSUE_DIR.mkdir(parents=True, exist_ok=True)
    (ISSUE_DIR / f"{number}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
    chunks = chunking.chunk_thread(record)
    if not chunks:
        return 0
    return upsert_for_path(client, "issue", str(number), chunks)
