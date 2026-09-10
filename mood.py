"""
mood.py

derived from audio features (value and energy).
Positive/negative on an axis, aactivated/calm on the other.
happy = high valence, sad = low
energetic = high energy, calm = low energy

doesn't need new data. valence and energy are stored in the data from FAISS
"""

import numpy as np

VALENCE_IDX = 7
ENERGY_IDX = 1


MOOD_TARGETS = {
    "happy": (0.80, 0.70),
    "sad": (0.15, 0.30),
    "energetic": (0.60, 0.90),
    "calm": (0.40, 0.15),
}


class MoodScorer:
    """Scores how well a candidate track matches a request mood"""

    def __init__(self, recommender):
        self.rec = recommender

        scaler = recommender.scaler
        self.mean = np.asarray(scaler.mean_, dtype="float32")
        self.scale = np.asarray(scaler.scale_, dtype="float32")

    def _target_vector(self, mood: str) -> np.ndarray:
        valence, energy = MOOD_TARGETS[mood]
        return np.array(
            [
                (valence - self.mean[VALENCE_IDX]) / self.scale[VALENCE_IDX],
                (energy - self.mean[ENERGY_IDX]) / self.scale[ENERGY_IDX],
            ],
            dtype="float32",
        )

    def query_targets(self, mood: str) -> dict[int, float]:
        """
        Standardised target values for valence and energy dimensions
        """

        if mood not in MOOD_TARGETS:
            return {}
        target = self._target_vector(mood)
        return {VALENCE_IDX: float(target[0]), ENERGY_IDX: float(target[1])}

    def fit_scores(self, track_ids, mood: str) -> dict[str, float]:
        """
        return track_id: in [0,1] where 1 is the closet to mood
        """

        if mood not in MOOD_TARGETS or not track_ids:
            return {}

        ids = [t for t in track_ids if t in self.rec.id_to_pos]
        if not ids:
            return {}

        target = self._target_vector(mood)
        points = np.array(
            [
                self.rec.index.reconstruct(self.rec.id_to_pos[t])[
                    [VALENCE_IDX, ENERGY_IDX]
                ]
                for t in ids
            ],
            dtype="float32",
        )

        distances = np.linalg.norm(points - target, axis=1)

        lo, hi = float(distances.min()), float(distances.max())

        if hi == lo:
            return {t: 1.0 for t in ids}

        return {t: float(1 - (d - lo) / (hi - lo)) for t, d in zip(ids, distances)}
