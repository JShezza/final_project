"""
Audio similarity recommend.
Loads artifacts that were built by prepare_data.py
turns a list of seed track ids into a ranked list of tracks
"""

import pickle
from pathlib import Path
from re import RegexFlag
from typing import cast

import faiss
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"


class Recommender:
    def __init__(self, nprobe: int = 16):
        self.index = faiss.read_index(str(DATA_DIR / "tracks.index"))

        # nprobe = amount of cells FAISS searches. Higher = slower but more accurate
        self.index.nprobe = nprobe  # type: ignore
        with open(DATA_DIR / "scaler.pkl", "rb") as f:
            self.scaler = pickle.load(f)

        with open(DATA_DIR / "id_to_pos.pkl", "rb") as f:
            self.id_to_pos = pickle.load(f)

        self.meta = cast(pd.DataFrame, pd.read_pickle(DATA_DIR / "metadata.pkl"))

        # Pull all the vectors back from the index by id.
        self.index.make_direct_map()  # type: ignore

    def _vector_for(self, track_id: str) -> np.ndarray:
        """Return the standardised vector for a known track"""
        pos = self.id_to_pos[track_id]

        return self.index.reconstruct(pos)

    def recommend(self, seed_tracks, limit=10, exclude_seen=True):
        # Only seeds in the data
        known = [t for t in seed_tracks if t in self.id_to_pos]
        if not known:
            return []

        # Avg seed vectors in a query vector
        seed_vects = np.array([self._vector_for(t) for t in known], dtype="float32")
        query = seed_vects.mean(axis=0, keepdims=True)

        # overfetch ensuring enough after removing seeds
        k = limit + len(known)
        distances, idxs = self.index.search(query, k)

        seed_pos = {self.id_to_pos[t] for t in known} if exclude_seen else set()
        results = []

        for dist, pos in zip(distances[0], idxs[0]):
            if pos == -1 or pos in seed_pos:
                continue
            row = self.meta.iloc[pos]
            results.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "artists": row["artists"],
                    "year": int(row["year"]),
                    "rationale": {"audio_similarity": round(float(1 / (1 + dist)), 4)},
                }
            )
            if len(results) >= limit:
                break
        return results

    def search(
        self,
        query: str,
        limit: int = 10,
    ):
        """Search the catalogue by artistortrack name"""
        words = [w for w in query.lower().split() if w]
        if not words:
            return []

        haystack = (self.meta["artists"] + " " + self.meta["name"]).str.lower()
        mask = pd.Series(True, index=self.meta.index)

        for w in words:
            mask &= haystack.str.contains(w, regex=False, na=False)

        hits = self.meta[mask].copy()
        artist_hit = hits["artists"].str.lower().str.contains(words[0], regex=False)  # type: ignore

        hits["_rank"] = (~artist_hit).astype(int)
        hits = hits.sort_values("_rank", kind="stable").head(limit)  # type: ignore

        return hits.drop(columns="_rank").to_dict(orient="records")


if __name__ == "__main__":
    rec = Recommender()
    seed = rec.meta.iloc[0]

    print(f"Seed: {seed['name']} - {seed['artists']}\n")
    for r in rec.recommend([seed["id"]], limit=5):
        print(
            f"  {r['rationale']['audio_similarity']:.3f}  "
            f"{r['name']} - {r['artists']} ({r['year']})"
        )
