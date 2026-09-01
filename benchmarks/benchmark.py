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
import pandas as pd
from scipy.stats import wilcoxon

from blender import (
    VARIANTS,
    Blender,
    catalogue_lookup,
    collaborative_pool,
    normalise_title,
)
from recommender import Recommender

SEEDS_FILE = Path(__file__).parent / "benchmark_seeds.json"
OUT_FILE = Path(__file__).parent / "becnhmark_results.json"
TOP_N = 10
CANDIDATE_POOL = 50
NOVELTY_SETTINGS = [0.0, 1.0]
MODES = {"raw": False, "norm": True}
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


def paired(base, col, a, b):
    """Align two variants per seed values by genre seed"""
    key = ["genre", "seed"]
    xa = base.loc[base["variant"] == a, key + [col]]
    xb = base.loc[base["variant"] == b, key + [col]]
    m = xa.merge(xb, on=key, suffixes=("_a", "_b"))
    return m[f"{col}_a"].to_numpy(float), m[f"{col}_b"].to_numpy(float)


def report_wilcoxon(base, col, pairs):
    for a, b in pairs:
        xa, xb = paired(base, col, a, b)
        if len(xa) < 10:
            print(f" {a} vs {b}: skipped - only {len(xa)} paired seeds")
            continue
        if np.allclose(xa, xb):
            print(f"  {a} vs {b}: identical on every seed (means {xa.mean():.3f})")
            continue
        stat, p = wilcoxon(xa, xb)
        print(
            f" {a} vs {b}: W={stat:.0f}, p={p:.2e} "
            f"(means {xa.mean():.3f} vs {xb.mean():.3f},  n={len(xa)})"
        )


def main():
    rec = Recommender()
    lookup = catalogue_lookup(rec.meta)
    seeds = json.load(open(SEEDS_FILE))

    adapter = None
    if os.environ.get("LASTFM_API_KEY"):
        from lastfm_adapter import LastFmAdapter

        adapter = LastFmAdapter(api_key=os.environ["LASTFM_API_KEY"])
    else:
        print("NO LASTFM_API_KEY Collaborative pool will be empty. \n")

    all_ids = rec.meta["id"].tolist()
    rows = []

    for genre, tracks in seeds.items():
        for s in tracks:
            seed_id = s["id"]

            # Signal pools are built per seed and reused
            audio = {
                r["id"]: r["rationale"]["audio_similarity"]
                for r in rec.recommend([seed_id], limit=CANDIDATE_POOL)
            }
            collab, popularity = {}, {}
            if adapter is not None:
                similar = adapter.similar_tracks(
                    s["artist"], s["title"], limit=CANDIDATE_POOL
                )
                collab = collaborative_pool(similar, lookup)
                collab.pop(seed_id, None)
                for t in similar:
                    cid = lookup.get(normalise_title(t["name"], t["artist"]))
                    if cid and t.get("playcount"):
                        popularity[cid] = max(popularity.get(cid, 0), t["playcount"])

            def record(variant, mode, novelty, ids):
                if len(ids) < 2:
                    return
                known = [popularity[i] for i in ids if i in popularity]
                rows.append(
                    {
                        "genre": genre,
                        "seed": s["title"],
                        "variant": variant,
                        "mode": mode,
                        "novelty": novelty,
                        "coherence": coherence(rec, seed_id, ids),
                        "diversity": diversity(rec, ids),
                        "mean_log_playcount": (
                            float(np.mean([math.log1p(p) for p in known]))
                            if known
                            else float("nan")
                        ),
                    }
                )

            rand_ids = RNG.sample(all_ids, TOP_N)
            for mode in MODES:
                record("random", mode, 0.0, rand_ids)

            for variant, weights in VARIANTS.items():
                for mode, flag in MODES.items():
                    blender = Blender(weights, normalise=flag)
                    for novelty in NOVELTY_SETTINGS:
                        out = blender.blend(
                            {"audio": audio, "collaborative": collab},
                            popularity=popularity or None,
                            novelty=novelty,
                            limit=TOP_N,
                        )
                        record(variant, mode, novelty, [b["id"] for b in out])
        print(f"done: {genre}")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_FILE, index=False)
    n_seeds = sum(len(v) for v in seeds.values())

    # Summary of novelty at 0 raw vs normalised
    base = df[df["novelty"] == 0.0]
    for mode in MODES:
        print(f"\nMEAN METRICS OVER {n_seeds} seeds (novelty=0), mode={mode}")
        print(
            f"{'variant':>12} | {'coherence':>9} | {'diversity':>9} | {'pop  cov':>7}"
        )
        sub = base[base["mode"] == mode]
        for v in list(VARIANTS) + ["random"]:
            g = sub[sub["variant"] == v]
            print(
                f"{v:>12} | {g['coherence'].mean():>9.3f} | "
                f"{g['diversity'].mean():>9.3f} | {g['pop_coverage'].mean():>7.1%}"
            )

    print("\n Wilcoxon signed-rank (coherence, novelty=0, paired  per seed)")
    pairs = [
        ("balanced", "audio-only"),
        ("audio_heavy", "audio_only"),
        ("balanced", "random"),
        ("audio_only", "random"),
    ]

    for mode in MODES:
        print(f"\nWilcoxon signed rank on coherence(novelty=0, mode={mode})")
        report_wilcoxon(base[base["mode"] == mode], "coherence", pairs)

    print("\n Novelty Param effect (balanced, noramlised): Reach the tail?")
    print(f"{'novelty':>7} | {'pop cov':>7} | {'mean log-playcount (known)'}:>26")
    for nov in NOVELTY_SETTINGS:
        g = df[
            (df["variant"] == "balanced")
            & (df["mode"] == "norm")
            & (df["novelty"] == nov)
        ]
        mlp = g.loc[:, "mean_log_playcount"].dropna()
        lbl = f"{mlp.mean():.2f}" if len(mlp) else "n/a"
        print(f"{nov:>7.2f} | {g['pop_coverage'].mean():>7.1%} | {lbl:>26}")

    print(f"\nPer-seed rows written to {OUT_FILE.name}")


if __name__ == "__main__":
    main()
