"""
Blender - the weighted portion of the hybrid design
Each signal produces a candidate in their pool and scores them {track_id: score}
THe score is [0,1]

"""

import math

# A/B Variants
VARIANTS = {
    "audio_only": {"audio": 1.0, "collaborative": 0.0},
    "collab_only": {"audio": 0.0, "collaborative": 1.0},
    "balanced": {"audio": 0.5, "collaborative": 0.5},
    "audio_heavy": {"audio": 0.75, "collaborative": 0.25},
}


class Blender:
    def __init__(self, weights: dict[str, float]):
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("At least one weight must be greater than 0.")

        # Noramlise to stay between [0,1]
        self.weights = {k: v / total for k, v in weights.items()}

    def blend(
        self,
        signal_pools: dict[str, dict[str, float]],
        popularity: dict[str, float] | None = None,
        novelty: float = 0.0,
        limit: int = 10,
    ) -> list[dict]:
        """
        signal_pools: {"audio": {track_id: score}, "collaborative": {...}}
        popularity:   optional {track_id: playcount} for the novelty bias
        novelty:      0 = ignore popularity, 1 = maximum bias to the long tail
        """
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
                    "scoure": round(score, 4),
                    # Signals actual contribution to the blend
                    "rationale": {s: round(c, 4) for s, c in contributions.items()},
                }
            )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]
