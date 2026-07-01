"""Shared retrieval: Qdrant hybrid (dense + sparse, server-side RRF) + local rerank.

One code path used by the Streamlit UI (later), the MCP server (phase 3), and eval.

Modes:
  dense   — pure vector search (semantic; misses exact identifiers)
  sparse  — pure BM25 (exact tokens; misses paraphrase)
  hybrid  — dense + sparse fused with Reciprocal Rank Fusion (Qdrant-native)
Optional rerank: cross-encoder BAAI/bge-reranker-base over the fused candidates.

CLI (the "naive vs hybrid" beat):
  uv run python retrieval.py "why doesn't preemption guarantee the node" --mode dense
  uv run python retrieval.py "NominatedNodeName" --mode dense          # vector misses it
  uv run python retrieval.py "NominatedNodeName" --mode hybrid --rerank # BM25 catches it
"""

import argparse
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import models

from config import COLLECTION
from embeddings import embed_dense, embed_sparse_query
from store import get_client


@dataclass
class RetrievedChunk:
    id: str
    text: str
    score: float
    pile: str
    path: str
    method: str
    payload: dict


@lru_cache(maxsize=1)
def _reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder("BAAI/bge-reranker-base")


def _build_filter(pile: str | None, path: str | None) -> models.Filter | None:
    must = []
    if pile:
        must.append(models.FieldCondition(key="pile", match=models.MatchValue(value=pile)))
    if path:
        must.append(models.FieldCondition(key="path", match=models.MatchValue(value=path)))
    return models.Filter(must=must) if must else None


class Retriever:
    def __init__(self):
        self.client = get_client()

    @staticmethod
    def _to_chunk(point, method: str) -> RetrievedChunk:
        payload = point.payload or {}
        return RetrievedChunk(
            id=str(point.id),
            text=payload.get("text", ""),
            score=float(point.score) if point.score is not None else 0.0,
            pile=payload.get("pile", ""),
            path=payload.get("path", ""),
            method=method,
            payload=payload,
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        mode: str = "hybrid",
        pile: str | None = None,
        path: str | None = None,
        rerank: bool = False,
        candidates: int = 30,
    ) -> list[RetrievedChunk]:
        flt = _build_filter(pile, path)
        fetch = candidates if rerank else top_k

        if mode == "dense":
            dense = embed_dense([query])[0]
            res = self.client.query_points(
                COLLECTION, query=dense, using="dense",
                limit=fetch, query_filter=flt, with_payload=True,
            )
        elif mode == "sparse":
            idx, val = embed_sparse_query(query)
            res = self.client.query_points(
                COLLECTION, query=models.SparseVector(indices=idx, values=val), using="sparse",
                limit=fetch, query_filter=flt, with_payload=True,
            )
        elif mode == "hybrid":
            dense = embed_dense([query])[0]
            idx, val = embed_sparse_query(query)
            res = self.client.query_points(
                COLLECTION,
                prefetch=[
                    models.Prefetch(query=dense, using="dense", limit=fetch),
                    models.Prefetch(
                        query=models.SparseVector(indices=idx, values=val),
                        using="sparse", limit=fetch,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=fetch, query_filter=flt, with_payload=True,
            )
        else:
            raise ValueError(f"unknown mode: {mode}")

        chunks = [self._to_chunk(p, mode) for p in res.points]
        if rerank and chunks:
            chunks = self._rerank(query, chunks, top_k)
        return chunks[:top_k]

    def _rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        scores = _reranker().predict([[query, c.text] for c in chunks])
        for c, s in zip(chunks, scores):
            c.score = float(s)
            c.method += "+rerank"
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks[:top_k]


def _label(c: RetrievedChunk) -> str:
    p = c.payload
    if c.pile == "code":
        return f"{p.get('symbol_type', '')} {p.get('symbol_name', '')} @ {c.path}"
    if c.pile == "issue":
        return f"#{p.get('number', '')} ({p.get('kind', '')}) {p.get('title', '')[:50]}"
    return f"{p.get('section', p.get('title', ''))} @ {c.path}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--mode", choices=["dense", "sparse", "hybrid"], default="hybrid")
    parser.add_argument("--pile", choices=["code", "kep", "issue", "docs"], default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()

    results = Retriever().search(
        args.query, top_k=args.top_k, mode=args.mode, pile=args.pile, rerank=args.rerank,
    )
    print(f"\nmode={args.mode}{'+rerank' if args.rerank else ''}  query={args.query!r}\n")
    for i, c in enumerate(results, 1):
        snippet = " ".join(c.text.split())[:160]
        print(f"[{i}] score={c.score:.4f}  pile={c.pile}")
        print(f"    {_label(c)}")
        print(f"    {snippet}\n")


if __name__ == "__main__":
    main()
