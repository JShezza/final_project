"""
Blender - the weighted portion of the hybrid design
Each signal produces a candidate in their pool and scores them {track_id: score}
THe score is [0,1]

"""

import math
import re
from collections.abc import Mapping

# A/B Variants
VARIANTS = {
    "audio_only": {"audio": 1.0, "collaborative": 0.0},
    "collab_only": {"audio": 0.0, "collaborative": 1.0},
    "balanced": {"audio": 0.5, "collaborative": 0.5},
    "audio_heavy": {"audio": 0.75, "collaborative": 0.25},
}


def min_max(pool: Mapping[str, float]) -> dict[str, float]:
    """
    Rescale signal to [0,1]
    """
    if not pool:
        return {}
    lo, hi = min(pool.values()), max(pool.values())
    if hi == lo:
        return {k: 1.0 for k in pool}
    return {k: (v - lo) / (hi - lo) for k, v in pool.items()}


class Blender:
    def __init__(self, weights: dict[str, float], normalise: bool = False):
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("At least one weight must be greater than 0.")

        # Noramlise to stay between [0,1]
        self.weights = {k: v / total for k, v in weights.items()}
        self.normalise = normalise

    def blend(
        self,
        signal_pools: dict[str, dict[str, float]],
        popularity: Mapping[str, float] | None = None,
        novelty: float = 0.0,
        limit: int = 10,
    ) -> list[dict]:
        """
        signal_pools: {"audio": {track_id: score}, "collaborative": {...}}
        popularity:   optional {track_id: playcount} for the novelty bias
        novelty:      0 = ignore popularity, 1 = maximum bias to the long tail
        """
        if self.normalise:
            signal_pools = {s: min_max(p) for s, p in signal_pools.items()}

        # Create a union of candiates for every processed signal
        candidates = set()
        for pool in signal_pools.values():
            candidates.update(pool)

        # normalise popularity (Playcounts are scewed towards popular artists, linear would make everything "niche")
        max_log_pop = 1.0
        if popularity:
            max_log_pop = max(math.log1p(p) for p in popularity.values()) or 1.0

        results = []
        for track_id in candidates:
            # weighted sum. If missing signal = 0
            contributions = {
                signal: self.weights.get(signal, 0.0) * pool.get(track_id, 0.0)
                for signal, pool in signal_pools.items()
            }
            score = sum(contributions.values())

            # Novelty dumbing. Popularity a % of novelty up * 100%
            if novelty > 0 and popularity and track_id in popularity:
                pop_norm = math.log1p(popularity[track_id]) / max_log_pop
                score *= 1 - novelty * pop_norm

            results.append(
                {
                    "id": track_id,
                    "score": round(score, 4),
                    # Signals actual contribution to the blend
                    "rationale": {s: round(c, 4) for s, c in contributions.items()},
                }
            )

        results.sort(
            key=lambda r: (
                -r["score"],
                -sum(1 for c in r["rationale"].values() if c > 0),
                r["id"],
            )
        )
        return results[:limit]


def normalise_title(name: str, artist: str) -> tuple[str, str]:
    """
    Reduce pairs to a form for Last.fm results to be matched against catalogue rows
    (Case, punctuation, style suffixes)
    """

    def clean(s: str) -> str:
        s = s.lower()
        s = re.sub(r"\s*[-(\[].*?(remaster|live|version|edit|mono|stereo).*", "", s)
        s = re.sub(r"[^\w\s]", "", s)  # get rid of punctuation
        return re.sub(r"\s+", " ", s).strip()  # handle whitespace

    return clean(name), clean(artist)


def catalogue_lookup(meta) -> dict[tuple[str, str], str]:
    """
    Build a map: {(normalised name, normalised first artist): track_id} for last.fms (artist, title) results
    """
    lookup = {}
    for row in meta.itertuples(index=False):
        first_artist = str(row.artists).split(",")[0]
        key = normalise_title(str(row.name), first_artist)
        lookup.setdefault(key, row.id)

    return lookup


def collaborative_pool(
    similar: list[dict], lookup: dict[tuple[str, str], str]
) -> dict[str, float]:
    """
    Convert Last.fm adapter similar_tracks into a track_id: match_score pool with only tracks in the catalogue.
    Drop tracks that can't be matched
    """
    pool = {}
    for t in similar:
        key = normalise_title(t["name"], t["artist"])
        track_id = lookup.get(key)
        if track_id is not None:
            # If song is returned twice, use the best score.
            pool[track_id] = max(pool.get(track_id, 0.0), t["match"])

    return pool
