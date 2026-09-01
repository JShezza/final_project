"""
benchmark.py

offline variant benchmark

ruyn every A/B variant over a fixed set of seed tracks (40 tracks, 4 genres)
Comapres the top 10 output  on three metrics, coherence, diversity (pairwise distance mean),
novelty (mean log playcount of recommended tracks that have last.fm data)

compared per seed with Wilcoxon signed ranked tests

collab signial is read cache first run with a lastfm api key
"""

import json
import math
import os
import random
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

from blender import (
    VARIANTS,
    Blender,
    catalogue_lookup,
    collaborative_pool,
    normalise_title,
)
from main import CANDIDATE_POOL
from recommender import Recommender

SEEDS_FILE = Path(__file__).parent / "benchmark_seeds.json"
OUT_FILE = Path(__file__).parent / "becnhmark_results.json"
TOP_N = 10
CANDIDATE_POOL = 50
NOVELTY_SETTINGS = [0.0, 1.0]
RNG = random.Random(42)


def feature_vectors(rec, ids):
    return np.array([rec.index.reconstruct(rec.id_to_pos[i]) for i in ids])


def coherence(rec, seed_id, rec_ids):
    """Mean 1/(1+dist) between seed and recommended track"""
    seed = feature_vectors(rec, [seed_id])[0]
    vecs = feature_vectors(rec, rec_ids)
    dists = np.linalg.norm(vecs - seed, axis=1)

    return float(np.mean(1 / (1 + dists)))


def diversity(rec, rec_ids):
    """intralist diversity mean pairwise distance within list"""
    vecs = feature_vectors(rec, rec_ids)
    d = np.linalg.norm(vecs[:, None] - vecs[None, :], axis=-1)
    return float(d[np.triu_indices(len(vecs), k=1)].mean())


def main():
    return


if __name__ == "__main__":
    main()
