"""
Test lastfm adapter

Offline testing for the adapater.
No internet connection or api key

Checks for the three fail points:
    - Parsing: similar tracks and popularity payloads map to their dicts cleanly
    - Unknown tracks: error returns to [] or None. Not a crash
    - Cache: Duplicate calls are served from SQLite instead of the network
"""

import pytest

from lastfm_adapter import LastFmAdapter

SIMILAR_GOOD = {
    "similartracks": {
        "track": [
            {
                "name": "DNA.",
                "match": "1.0",
                "playcount": "41230567",
                "artist": {"name": "Kendrick Lamar"},
            },
            {
                "name": "N95",
                "match": "0.565109",
                "playcount": "28904411",
                "artist": {"name": "Kendrick Lamar"},
            },
            {
                "name": "The Box",
                "match": "0.363724",
                "playcount": "23928455",
                "artist": {"name": "Roddy Ricch"},
            },
            {
                "name": "No Role Modelz",
                "match": "0.338553",
                "artist": {"name": "J. Cole"},
            },
        ],
        "@attr": {"artist": "Kendrick Lamar"},
    }
}

INFO_GOOD = {
    "track": {"name": "HUMBLE.", "playcount": "32147319", "listeners": "2325228"}
}

UNKNOWN = {"error": 6, "message": "Track not found"}


class FakeAdapter(LastFmAdapter):
    """Replace network responses with fixtures while retaining the real cache."""

    def __init__(self, cache_path):
        super().__init__(api_key="fake-key", cache_path=cache_path)
        self.network_calls = 0
        self.fixtures = {}

    def _get(self, method, **params):
        key = (
            method
            + "|"
            + "|".join(f"{k}={str(v).lower()}" for k, v in sorted(params.items()))
        )

        cached = self._cache_get(key)
        if cached is not None:
            return cached

        self.network_calls += 1
        payload = self.fixtures[method]
        self._cache_put(key, payload)
        return payload


@pytest.fixture
def adapter(tmp_path):
    """Give each test a fresh adapter and its own temporary SQLite database."""
    return FakeAdapter(cache_path=tmp_path / "test_cache.sqlite")


def test_similar_tracks_payload_parsed(adapter):
    adapter.fixtures["track.getSimilar"] = SIMILAR_GOOD

    similar = adapter.similar_tracks("Kendrick Lamar", "HUMBLE.")

    assert len(similar) == 4, similar
    assert similar[0] == {
        "artist": "Kendrick Lamar",
        "name": "DNA.",
        "match": 1.0,
        "playcount": 41230567,
    }
    assert isinstance(similar[1]["match"], float)


def test_popularity_payload_parsed(adapter):
    adapter.fixtures["track.getInfo"] = INFO_GOOD

    popularity = adapter.popularity("Kendrick Lamar", "HUMBLE.")

    assert popularity == {"playcount": 32147319, "listeners": 2325228}, popularity


def test_unknown_track_returns_no_similar_tracks(adapter):
    adapter.fixtures["track.getSimilar"] = UNKNOWN

    assert adapter.similar_tracks("Nobody", "No Song") == []


def test_unknown_track_returns_no_popularity(adapter):
    adapter.fixtures["track.getInfo"] = UNKNOWN

    assert adapter.popularity("Nobody", "No Song") is None


def test_duplicate_calls_use_cache(adapter):
    adapter.fixtures["track.getSimilar"] = SIMILAR_GOOD
    first = adapter.similar_tracks("Kendrick Lamar", "HUMBLE.")
    before = adapter.network_calls

    # A cache miss now fails because no response fixture remains.
    adapter.fixtures.clear()
    second = adapter.similar_tracks("Kendrick Lamar", "HUMBLE.")

    assert second == first
    assert adapter.network_calls == before, "expected a cache call"


def test_cache_is_reused_by_new_adapter(adapter, tmp_path):
    adapter.fixtures["track.getSimilar"] = SIMILAR_GOOD
    first = adapter.similar_tracks("Kendrick Lamar", "HUMBLE.")

    restarted = FakeAdapter(cache_path=tmp_path / "test_cache.sqlite")
    second = restarted.similar_tracks("Kendrick Lamar", "HUMBLE.")

    assert second == first
    assert second[0]["name"] == "DNA."
    assert restarted.network_calls == 0
