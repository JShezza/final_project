"""
sim_study.py

runs a simulated rating study against the API

Usage:
python -m studies.sim_study
"""

import argparse
import hashlib
import json
import random
from pathlib import Path

import requests

from ab_router import assign_variant
from blender import VARIANTS

API = "http://127.0.0.1:8000"
SEEDS_FILE = Path(__file__).parent.parent / "benchmarks" / "benchmark_seeds.json"
SESSION_MAP = Path(__file__).parent / "session_map.json"
COMPARE = ("audio_only", "full_hybrid")

VALENCE_IDX, ENERGY_IDX = 7, 1


def session_keys(rater: int, variants) -> dict[str, str]:
    """
    Find  a session key per variant for a rater

    Assign a has so keyhs are search until lands on a wanted variant
    """
    keys, attempt = {}, 0
    while len(keys) < len(variants):
        candidate = f"sim-r{rater:03d}-{attempt}"

        variant = assign_variant(candidate)
        if variant in variants and variant not in keys:
            keys[variant] = candidate

        attempt += 1
        if attempt > 5000:
            raise RuntimeError("Could not find keys for variant")

    return keys


def features(track_id: str) -> dict:
    r = requests.get(f"{API}/tracks/{track_id}/features", timeout=10)
    r.raise_for_status()

    return r.json()["features"]


class Rater:
    """A simulated listener via one explicit theory for a recommendation"""

    def __init__(self, profile: str, rng: random.Random) -> None:
        self.profile = profile
        self.rng = rng

    def score(self, seed_feats: dict, track_feats: dict, track: dict) -> float:
        """Return satisfaction score [0, 1]"""
        if self.profile == "similarity":
            # close in energy and valence to the seed = good
            gap = abs(seed_feats["energy"] - track_feats["energy"]) + abs(
                seed_feats["valence"] - track_feats["valence"]
            )

            return max(0.0, 1 - gap)

        if self.profile == "discovery":
            # Reward tracks the collab signal didn't supply
            collaborative = track["rationale"].get("collaborative", 0.0)

            return 0.75 if collaborative == 0 else 0.35

        return max(0.0, 1 - abs(seed_feats["energy"] - track_feats["energy"]))

    def rate(self, score: float) -> str:
        """Turn a score into upvote downvote skip"""
        roll = self.rng.random()
        if roll < score * 0.8:
            return "up"
        if roll < score * 0.8 + 0.25:
            return "skip"
        return "down"


def run(raters: int, seeds_per_rater: int, limit: int, seed: int) -> dict:
    rng = random.Random(seed)
    all_seeds = [s for group in json.load(open(SEEDS_FILE)).values() for s in group]
    profiles = ["similarity", "discovery", "mood"]

    for variant in COMPARE:
        if variant not in VARIANTS:
            raise SystemExit(f"Unkown variant in compare: {variant}")

    submitted = 0
    session_map = {}

    for r in range(raters):
        rater = Rater(profiles[r % len(profiles)], random.Random(seed + r))
        keys = session_keys(r, COMPARE)

        for key in keys.values():
            hashed = hashlib.sha256(key.encode("utf-8")).hexdigest()
            session_map[hashed] = f"rater{r:03d}"

        chosen = rng.sample(all_seeds, seeds_per_rater)

        for s in chosen:
            seed_feats = features(s["id"])

            for variant, key in keys.items():
                resp = requests.post(
                    f"{API}/recommend",
                    json={
                        "seed_tracks": [s["id"]],
                        "user_id": key,
                        "limit": limit,
                        "parameters": {"novelty": 0.5},
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                body = resp.json()
                assert body["variant"] == variant, (body["variant"], variant)

                for track in body["results"]:
                    score = rater.score(seed_feats, features(track["id"]), track)
                    requests.post(
                        f"{API}/feedback",
                        json={
                            "request_id": body["request_id"],
                            "track_id": track["id"],
                            "rating": rater.rate(score),
                        },
                        timeout=10,
                    ).raise_for_status()
                    submitted += 1
        print(f"  rater {r+1}/{raters} ({rater.profile}) done")

    json.dump(session_map, open(SESSION_MAP, "w"), indent=2)
    return {"raters": raters, "ratings": submitted, "map": str(SESSION_MAP)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raters", type=int, default=30)
    ap.add_argument("--seeds", type=int, default=4, help="seed tracks per rater")
    ap.add_argument("--limit", type=int, default=5, help="tracks rated per request")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed")
    args = ap.parse_args()

    print(f"SIMULATED study: {' vs '.join(COMPARE)}")
    print(
        "Synthetic raters. Results describe the rating rules in this file. Not human preference\n"
    )

    result = run(args.raters, args.seeds, args.limit, args.seed)
    print(
        f"\n{result['ratings']} simulated ratings sumbitted by: {result['raters']} raters."
    )
    print(f"Session key map written to {SESSION_MAP.name}")
    print("Analyse with: analyse_study.py")


if __name__ == "__main__":
    main()
