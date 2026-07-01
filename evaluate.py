"""Retrieval evaluation: question -> expected sources -> hit-rate / precision / recall / MRR.

Measures the RETRIEVAL layer (do we surface the right sources?), not generation. Use it
to compare modes — the lecture's "не на глаз" point:

    uv run python evaluate.py --mode dense
    uv run python evaluate.py --mode hybrid --rerank

A retrieved chunk is "relevant" if any expected substring appears in its `path`
(file path / KEP number / issue number).
"""

import argparse
import json
from pathlib import Path

from retrieval import Retriever

DATASET = Path(__file__).parent / "eval_dataset.json"


def _relevant(path: str, expected: list[str]) -> bool:
    return any(e in path for e in expected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dense", "sparse", "hybrid"], default="hybrid")
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    dataset = json.loads(DATASET.read_text())
    retriever = Retriever()
    k = args.top_k

    sum_hit = sum_prec = sum_rec = sum_mrr = 0.0
    print(f"\nmode={args.mode}{'+rerank' if args.rerank else ''}  top_k={k}  ({len(dataset)} questions)\n")

    for item in dataset:
        expected = item["expected"]
        results = retriever.search(item["question"], top_k=k, mode=args.mode, rerank=args.rerank)
        paths = [c.path for c in results]

        rel_flags = [_relevant(p, expected) for p in paths]
        n_rel = sum(rel_flags)
        matched = {e for e in expected if any(e in p for p in paths)}

        hit = 1.0 if n_rel else 0.0
        precision = n_rel / k
        recall = len(matched) / len(expected) if expected else 0.0
        mrr = 0.0
        for rank, flag in enumerate(rel_flags, 1):
            if flag:
                mrr = 1.0 / rank
                break

        sum_hit += hit
        sum_prec += precision
        sum_rec += recall
        sum_mrr += mrr

        mark = "✓" if hit else "✗"
        print(f"  {mark} hit={hit:.0f} P@{k}={precision:.2f} R={recall:.2f} MRR={mrr:.2f}  {item['question'][:64]}")

    n = len(dataset)
    print("\n  ── aggregate ──")
    print(f"  hit-rate   {sum_hit / n:.3f}")
    print(f"  precision  {sum_prec / n:.3f}")
    print(f"  recall     {sum_rec / n:.3f}")
    print(f"  MRR        {sum_mrr / n:.3f}")


if __name__ == "__main__":
    main()
