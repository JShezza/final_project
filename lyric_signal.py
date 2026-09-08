"""
lyric_signal.py

lyric derived mood signal

VADER score per track scored in [-1, 1], keyed by track id. Lyrics aren't stored


Cost: one LRCLIB lookup for a lyric that hasn't been scored (cap set)
"""

import sqlite3
import time
from pathlib import Path

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

SCORE_CACHE = Path(__file__).parent / "data" / "lyrics_cache" / "sentiment.sqlite"

# Compound score for moods that are sentiment polarities
MOOD_TARGET_SENTIMENT = {"happy": 0.6, "sad": -0.6}


class LyricSentiment:
    def __init__(self, adapter, cache_path: Path = SCORE_CACHE):
        self.adapter = adapter
        self.analyser = SentimentIntensityAnalyzer()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(cache_path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS sentiment ("
            "   track_id  TEXT PRIMARY KEY,"
            "   compound  REAL,"  # NULL = no lyrics available
            "   scored_at REAL NOT NULL)"
        )
        self.db.commit()

    def score_text(self, lyrics: str) -> float:
        """VADER compound polarity of a lyric (-1 negative, +1 positive)"""
        return float(self.analyser.polarity_scores(lyrics)["compound"])

    def compound_for(self, track_id: str, artist: str, title: str) -> float | None:
        """Cached sentiment for a track. None when missing"""
        row = self.db.execute(
            "SELECT compound FROM sentiment WHERE track_id = ?", (track_id,)
        ).fetchone()

        if row is not None:
            return row[0]

        status, text = self.adapter.fetch_lyrics(artist, title)
        compound = self.score_text(text) if text else None

        self.db.execute(
            "INSERT OR REPLACE INTO sentiment VALUES (?, ?, ?)",
            (track_id, compound, time.time()),
        )

        self.db.commit()

        return compound

    def pool(self, candidates, reference: float) -> dict[str, float]:
        """Build a signal {track_id: closeness} for candidates give as (track_id, artist, title)"""
        out = {}
        for track_id, artist, title in candidates:
            compound = self.compound_for(track_id, artist, title)
            if compound is None:
                continue
            out[track_id] = 1 - abs(compound - reference) / 2

        return out

    def reference_for(self, seed_compounds, target_mood: str | None) -> float | None:
        """The point candiates are compared against:
        mood for happy/sad, else mean sentiment. None if nothing to go on
        """
        if target_mood in MOOD_TARGET_SENTIMENT:
            return MOOD_TARGET_SENTIMENT[target_mood]

        known = [c for c in seed_compounds if c is not None]
        if not known:
            return None

        return sum(known) / len(known)
