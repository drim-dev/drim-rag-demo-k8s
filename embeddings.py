"""Embeddings: dense via Ollama (nomic-embed-text), sparse via fastembed BM25.

Both are produced at index time so Qdrant holds named vectors {dense, sparse} and can
do server-side hybrid fusion (added in phase 2).
"""

from functools import lru_cache

import requests
from fastembed import SparseTextEmbedding

from config import DENSE_MODEL, OLLAMA_URL, SPARSE_MODEL


def embed_dense(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Dense embeddings via Ollama /api/embed (batched)."""
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": DENSE_MODEL, "input": batch},
            timeout=120,
        )
        resp.raise_for_status()
        out.extend(resp.json()["embeddings"])
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
