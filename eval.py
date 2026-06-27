import time
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from faiss.loader import approx_topk_by_mode

RNG = np.random.default_rng(42)
N_QUERIES = 1000  # random seed to eval over
K = 10  # top-K recommendations amount
NPROBE_VALUES = [1, 8, 16, 32, 64]

DATA_DIR = Path(__file__).parent / "data"


def load():
    index = faiss.read_index(str(DATA_DIR / "tracks.index"))
    index.make_direct_map()  # type: ignore
    meta = pd.read_pickle(DATA_DIR / "metadata.pkl")

    # Pull every vector out the index
    vectors = index.reconstruct_n(0, index.ntotal)

    return index, meta, vectors


def build_force(vectors):
    """brute force index = ground proof"""
    exact = faiss.IndexFlatL2(vectors.shape[1])
    exact.add(vectors)
    return exact


def recall_k(aprrox_ids, exact_ids):
    """Fraction of the top-K"""
    scores = []
    for a, e in zip(aprrox_ids, exact_ids):
        scores.append(len(set(a) & set(e)) / len(e))
    return float(np.mean(scores))


def main():
    print("Loading index and vectors")
    index, meta, vectors = load()
    exact = build_force(vectors)

    # random query with their vectors
    q_pos = RNG.choice(len(vectors), size=N_QUERIES, replace=False)
    queries = vectors[q_pos]

    # ground truth
    t0 = time.time()
    _, exact_idx = exact.search(queries, K + 1)
    exact_time = time.time() - t0
    exact_topk = [list(row[1:]) for row in exact_idx]  # Drop self

    # recall + latency nprobe settings
    print(f"\nApproximate vs exact search over {N_QUERIES} queries, K={K}")
    print(f"{'nprobe':>7} | {'recall@10':>9} | {'ms/query':>9} | {'speedup':>8}")
    print("-" * 44)

    exact_ms = exact_time / N_QUERIES * 1000
    for nprobe in NPROBE_VALUES:
        index.nprobe = nprobe  # type: ignore
        t0 = time.time()
        _, approx_idx = index.search(queries, K + 1)
        aprrox_time = time.time() - t0
        approx_topk = [list(row[1:]) for row in approx_idx]  # Drop self

        rec = recall_k(approx_topk, exact_topk)
        ms = aprrox_time / N_QUERIES * 1000
        print(f"{nprobe:>7} | {rec:9.3f} | {ms:>9.3f} | {exact_ms / ms:>7.1f}x")

    print(
        f"\nExact brute force: {exact_ms:.3f} ms/query"
        f"({1000 / exact_ms:.0f} queries/sec)"
    )
