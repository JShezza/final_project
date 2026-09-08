"""
test_lyric_signal.py

Offline tests for lyric-sentiment signal. LRCLIB network call is swapped for
fixture responses; VADER and teh cahces are real.

Checks: Parsing, copyright, scoring, reference, cache
"""

import sqlite3
import tempfile
from pathlib import Path

from lyric_signal import LyricSentiment
from lyrics_adapter import FOUND, INSTRUMENTAL, MISSING, LyricsAdapter

HAPPY = "Sunshine and laughter, we dance all night, everything is wonderful and bright"
SAD = (
    "I cry alone tonight, my heart is broken and hopeless, the pain and "
    "sorrow never end, I lost everything and I hate this misery"
)


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeAdapter(LyricsAdapter):
    """LRCLIB swapped for a fixture table keyd by title"""

    def __init__(self, cache_path):
        super().__init__(cache_path=cache_path)
        self.calls = 0
        self.fixtures = {
            "happy song": FakeResponse(200, {"plainLyrics": HAPPY}),
            "sad song": FakeResponse(200, {"plainLyrics": SAD}),
            "nowhere": FakeResponse(404),
            "drum solo": FakeResponse(200, {"instrumental": True}),
            "blank": FakeResponse(200, {"plainLyrics": ""}),
        }

    def fetch_lyrics(self, artist, title):
        import requests as _r

        self.calls += 1
        original = _r.get
        _r.get = lambda *a, **k: self.fixtures[k["params"]["track_name"]]
        try:
            return super().fetch_lyrics(artist, title)
        finally:
            _r.get = original


def main():
    tmp = Path(tempfile.mkdtemp())
    adapter = FakeAdapter(cache_path=tmp / "lookup.sqlite")
    signal = LyricSentiment(adapter, cache_path=tmp / "sentiment.sqlite")

    # Parsing
    assert adapter.fetch_lyrics("x", "happy song") == (FOUND, HAPPY)
    assert adapter.fetch_lyrics("x", "nowhere") == (MISSING, None)
    assert adapter.fetch_lyrics("x", "drum solo") == (INSTRUMENTAL, None)
    assert adapter.fetch_lyrics("x", "blank") == (MISSING, None)
    print("PASS: found / 404/ instrumental /empty handled")

    # copyright (no lyrics text in database)
    for db_file in ("lookup.sqlite", "sentiment.sqlite"):
        raw = open(tmp / db_file, "rb").read()
        assert b"Sunshine" not in raw and b"broken" not in raw, db_file
    print("PASS: lyrics text is never persisted")

    # Scoring
    happy = signal.compound_for("h1", "x", "happy song")
    sad = signal.compound_for("s1", "x", "sad song")
    assert happy is not None and sad is not None
    assert happy > 0.3 and sad < -0.3, (happy, sad)
    assert signal.compound_for("n1", "x", "nowhere") is None
    pool = signal.pool(
        [("h1", "x", "happy song"), ("s1", "x", "sad song"), ("n1", "x", "nowhere")],
        reference=0.6,
    )
    assert set(pool) == {"h1", "s1"}
    assert pool["h1"] > pool["s1"]
    print("PASS: sentiment scores and pool closeness make sense")

    # Reference point
    assert signal.reference_for([0.1, 0.5], "happy") == 0.6
    assert signal.reference_for([0.1, 0.5], "sad") == -0.6
    assert abs(signal.reference_for([0.1, 0.5], "energetic") - 0.3) < 1e-9  # type: ignore
    assert abs(signal.reference_for([0.1, None, 0.5], "any") - 0.3) < 1e-9  # type: ignore
    assert signal.reference_for([None, None], "any") is None
    print("PASS: reference is a mood target or the seeds' mean")

    # Cache: rescoring is free
    before = adapter.calls
    signal.compound_for("h1", "x", "happy song")
    signal.compound_for("n1", "x", "nowhere")
    assert adapter.calls == before, "cached tracks should not hit the adapter"
    print("PASS: scored tracks are served from cache")

    ("\nALll lyrics signal tests passed")


if __name__ == "__main__":
    main()
