from pathlib import Path

import faiss
import numpy as np
import pandas as pd

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
