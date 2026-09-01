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
from blender import (
    VARIANTS,
    Blender,
    catalogue_lookup,
    collaborative_pool,
    normalise_title,
)
from main import CANDIDATE_POOL
from recommender import Recommender
from scipy.stats import wilcoxon

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
    variant_names = list(VARIANTS) + ["random"]
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

            for variant in variant_names:
                for novelty in NOVELTY_SETTINGS:
                    if variant == "random":
                        ids = RNG.sample(all_ids, TOP_N)
                    else:
                        blended = Blender(VARIANTS[variant]).blend(
                            {"audio": audio, "collaborative": collab},
                            popularity=popularity or None,
                            novelty=novelty,
                            limit=TOP_N,
                        )
                        ids = [b["id"] for b in blended]
                    if len(ids) < 2:
                        continue
                    known_pops = [popularity[i] for i in ids if i in popularity]
                    rows.append(
                        {
                            "genre": genre,
                            "seed": s["title"],
                            "variant": variant,
                            "novelty": novelty,
                            "coherence": coherence(rec, seed_id, ids),
                            "diversity": diversity(rec, ids),
                            "mean_log_playcount": (
                                float(np.mean([math.log1p(p) for p in known_pops]))
                                if known_pops
                                else float("nan")
                            ),
                            "pop_coverage": len(known_pops) / len(ids),
                        }
                    )
        print(f"done: {genre}")

    import pandas as pd

    df = pd.DataFrame(rows)
    df.to_csv(OUT_FILE, index=False)

    base = df[df["novelty"] == 0.0]
    print(f"\nMEAN METRICS OVER {len(seeds) * 10} seeds (novelty=0)")
    print(f"{'variant':>12} | {'coherence':>9} | {'diversity':>9} | {'pop  cov':>7}")
    for v in variant_names:
        g = base[base["variant"] == v]
        print(
            f"{v:>12} | {g['coherence'].mean():>9.3f} | "
            f"{g['diversity'].mean():>9.3f} | {g['pop_coverage'].mean():>7.1%}"
        )

    print("\n Wilcoxon signed-rank (coherence, novelty=0, paired  per seed)")
    pairs = [
        ("balanced", "audio-only"),
        ("balanced", "random"),
        ("audio_only", "random"),
    ]

    for a, b in pairs:
        sub_a = base.loc[base["variant"] == a].sort_values("seed")
        sub_b = base.loc[base["variant"] == b].sort_values("seed")
        xa = sub_a["coherence"].to_numpy(dtype=float)
        xb = sub_b["coherence"].to_numpy(dtype=float)
        n = min(len(xa), len(xb))
        if n < 10 or np.allclose(xa[:n], xb[:n]):
            print(f"{a} vs {b}: skipped - identical or too few pairs")
            continue
        stat, p = wilcoxon(xa[:n], xb[:n])
        print(
            f"{a} vs {b}: W={stat:.0f}, p={p:.2e} "
            f"(means {xa[:n].mean():.3f} vs {xb[:n].mean():.3f})"
        )

    print("\n Novelty Param effect (balanced)")
    for nov in NOVELTY_SETTINGS:
        g = df.loc[(df["variant"] == "balanced") & (df["novelty"] == nov)]
        mlp = g["mean_log_playcount"].dropna()
        label = f"{mlp.mean():.2f}" if len(mlp) else "n/a (no popularity data)"
        print(f"novelty={nov}: mean log-playcount of recommendations = {label}")

    print(f"\nPer-seed rows written to {OUT_FILE.name}")


if __name__ == "__main__":
    main()
