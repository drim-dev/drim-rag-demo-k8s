"""Embeddings: dense via Ollama (nomic-embed-text), sparse via fastembed BM25.

Both are produced at index time so Qdrant holds named vectors {dense, sparse} and can
do server-side hybrid fusion (added in phase 2).
"""

from functools import lru_cache

import requests
from fastembed import SparseTextEmbedding

from config import DENSE_MODEL, OLLAMA_URL, SPARSE_MODEL


# nomic-embed-text holds 2048 tokens and Ollama's server-side truncate is unreliable
# on long inputs, so cap each text client-side as a first cut. Token density varies
# (dense markdown/code overflows even at this cap), so _embed_batch shrinks any
# offender further on a 400. The full text still lives in the payload and the BM25
# (sparse) vector, so dropping a dense-vector tail costs no retrieval signal.
MAX_EMBED_CHARS = 6000


def _embed_batch(batch: list[str]) -> list[list[float]]:
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": DENSE_MODEL, "input": batch, "truncate": True},
        timeout=120,
    )
    if resp.status_code == 400:
        if len(batch) > 1:
            mid = len(batch) // 2
            return _embed_batch(batch[:mid]) + _embed_batch(batch[mid:])
        return _embed_batch([batch[0][: max(1, len(batch[0]) // 2)]])
    resp.raise_for_status()
    return resp.json()["embeddings"]


def embed_dense(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Dense embeddings via Ollama /api/embed (batched, shrink-on-overflow)."""
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = [t[:MAX_EMBED_CHARS] for t in texts[i:i + batch_size]]
        out.extend(_embed_batch(batch))
    return out


@lru_cache(maxsize=1)
def _sparse_model() -> SparseTextEmbedding:
    return SparseTextEmbedding(model_name=SPARSE_MODEL)


def embed_sparse(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    """Sparse (BM25) embeddings for documents, as (indices, values) pairs."""
    result = []
    for emb in _sparse_model().embed(texts):
        result.append((emb.indices.tolist(), emb.values.tolist()))
    return result


def embed_sparse_query(text: str) -> tuple[list[int], list[float]]:
    """Sparse (BM25) embedding for a query (IDF applied server-side via modifier)."""
    emb = next(iter(_sparse_model().query_embed([text])))
    return emb.indices.tolist(), emb.values.tolist()
