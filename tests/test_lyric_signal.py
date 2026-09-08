"""
test_lyric_signal.py

Offline tests for lyric-sentiment signal. LRCLIB network call is swapped for
fixture responses; VADER and teh cahces are real.

Checks: Parsing, copyright, scoring, reference, cache
"""

from unittest.mock import patch

import pytest

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
    """Replace LRCLIB responses with a fixture table keyed by title."""

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
        self.calls += 1
        with patch("requests.get") as get:
            get.side_effect = lambda *args, **kwargs: self.fixtures[
                kwargs["params"]["track_name"]
            ]
            return super().fetch_lyrics(artist, title)


@pytest.fixture
def adapter(tmp_path):
    return FakeAdapter(cache_path=tmp_path / "lookup.sqlite")


@pytest.fixture
def signal(adapter, tmp_path):
    return LyricSentiment(adapter, cache_path=tmp_path / "sentiment.sqlite")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("happy song", (FOUND, HAPPY)),
        ("nowhere", (MISSING, None)),
        ("drum solo", (INSTRUMENTAL, None)),
        ("blank", (MISSING, None)),
    ],
    ids=["found", "missing", "instrumental", "empty"],
)
def test_fetch_lyrics_parses_statuses(adapter, title, expected):
    assert adapter.fetch_lyrics("x", title) == expected


def test_lyrics_text_is_not_persisted(signal, tmp_path):
    # Populate both caches before checking their contents.
    signal.compound_for("h1", "x", "happy song")
    signal.compound_for("s1", "x", "sad song")

    for db_file in ("lookup.sqlite", "sentiment.sqlite"):
        raw = (tmp_path / db_file).read_bytes()
        assert b"Sunshine" not in raw and b"broken" not in raw, db_file


def test_compound_scores(signal):
    happy = signal.compound_for("h1", "x", "happy song")
    sad = signal.compound_for("s1", "x", "sad song")

    assert happy is not None and sad is not None
    assert happy > 0.3 and sad < -0.3, (happy, sad)
    assert signal.compound_for("n1", "x", "nowhere") is None


def test_pool_ranks_by_closeness_to_reference(signal):
    pool = signal.pool(
        [("h1", "x", "happy song"), ("s1", "x", "sad song"), ("n1", "x", "nowhere")],
        reference=0.6,
    )

    assert set(pool) == {"h1", "s1"}
    assert pool["h1"] > pool["s1"]


@pytest.mark.parametrize(
    ("scores", "mood", "expected"),
    [
        ([0.1, 0.5], "happy", 0.6),
        ([0.1, 0.5], "sad", -0.6),
        ([0.1, 0.5], "energetic", 0.3),
        ([0.1, None, 0.5], "any", 0.3),
        ([None, None], "any", None),
    ],
    ids=["happy-target", "sad-target", "seed-mean", "missing-seed", "no-scores"],
)
def test_reference_uses_mood_target_or_seed_mean(signal, scores, mood, expected):
    reference = signal.reference_for(scores, mood)

    if expected is None:
        assert reference is None
    else:
        assert reference == pytest.approx(expected, rel=0, abs=1e-9)


@pytest.mark.parametrize(
    ("track_id", "title"),
    [("h1", "happy song"), ("n1", "nowhere")],
    ids=["scored-track", "missing-track"],
)
def test_repeated_scores_use_cache(signal, adapter, track_id, title):
    first = signal.compound_for(track_id, "x", title)
    before = adapter.calls

    second = signal.compound_for(track_id, "x", title)

    assert second == first
    assert adapter.calls == before, "cached tracks should not hit the adapter"
