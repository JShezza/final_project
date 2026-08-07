"""
Test lastfm adapter

Offline testing for the adapater.
No internet connection or api key

Checks for the three fail points:
    - Parsing: similar tracks and popularity payloads map to their dicts cleanly
    - Unknown tracks: error returns to [] or None. Not a crash
    - Cache: Duplicate calls are served from SQLite instead of the network
"""

import tempfile
from pathlib import Path

from lastfm_adapter import LastFmAdapter

# Last FM shape for responses
# https://ws.audioscrobbler.com/2.0/?method=track.getsimilar&artist=Kendrick%20Lamar&track=HUMBLE.&api_key=LAST_FM_API_KEY&format=json
# Above url to get the results for similartracks
SIMILAR_GOOD = {
    "similartracks": {
        "track": [
            {"name": "DNA.", "match": "1.0", "artist": {"name": "Kendrick Lamar"}},
            {"name": "N95", "match": "0.565109", "artist": {"name": "Kendrick Lamar"}},
            {"name": "The Box", "match": "0.363724", "artist": {"name": "Roddy Ricch"}},
            {
                "name": "No Role Modelz",
                "match": "0.338553",
                "artist": {"name": "J. Cole"},
            },
        ],
        "@attr": {"artist": "Kendrick Lamar"},
    }
}

# https://ws.audioscrobbler.com/2.0/?method=track.getInfo&artist=Kendrick%20Lamar&track=HUMBLE.&api_key=LAST_FM_API_KEY&format=json
INFO_GOOD = {
    "track": {"name": "HUMBLE.", "playcount": "32147319", "listeners": "2325228"}
}

UNKNOWN = {"error": 6, "message": "Track not found"}


class TestAdapter(LastFmAdapter):
    """Network call swapped with a fixture lookup"""

    def __init__(self, cache_path):
        super().__init__(api_key="fake-key", cache_path=cache_path)
        self.network_calls = 0
        self.fixtures = {}

    def _get(self, method, **params):
        # Same logic as the original class but with fixture dict instead
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


def main():
    tmp = Path(tempfile.mkdtemp()) / "test_cache.sqlite"
    adp = TestAdapter(cache_path=tmp)

    # Parse similar tracks
    adp.fixtures["track.getSimilar"] = SIMILAR_GOOD
    sim = adp.similar_tracks("Kendrick Lamar", "HUMBLE.")
    assert len(sim) == 4, sim
    assert sim[0] == {"artist": "Kendrick Lamar", "name": "DNA.", "match": 1.0}
    assert isinstance(sim[1]["match"], float)
    print("PASS: similar_tracks payload parsed")

    # Parse popularity
    adp.fixtures["track.getInfo"] = INFO_GOOD
    pop = adp.popularity("Kendrick Lamar", "HUMBLE.")
    assert pop == {"playcount": 32147319, "listeners": 2325228}

    print("PASS: Popularity payload parsed")

    # Unknown Tracks fails properly
    adp.fixtures["track.getSimilar"] = UNKNOWN
    assert adp.similar_tracks("Nobody", "No Song") == []
    adp.fixtures["track.getInfo"] = UNKNOWN
    assert adp.popularity("Nobody", "No Song") is None
    print("PASS: Unknown tracks return empty results without a crash.")

    # Cache - Use sql cache instead of the API
    before = adp.network_calls
    adp.fixtures["tracks.getSimilar"] = SIMILAR_GOOD
    adp.similar_tracks("Kendrick Lamar", "HUMBLE.")
    assert adp.network_calls == before, "expected a cache call"
    print(
        "PASS: Duplicate calls served via Cache " f"({adp.network_calls} calls total)"
    )

    # Cache is used for a new adapter instance (saved to disk)
    backupAdp = TestAdapter(cache_path=tmp)
    backupAdp.fixtures = {}
    sim2 = backupAdp.similar_tracks("Kendrick Lamar", "HUMBLE.")
    assert sim2[0]["name"] == "DNA."
    assert backupAdp.network_calls == 0
    print("PASS: Cache is used across restarts.")

    print("\nTests Complete")


if __name__ == "__main__":
    main()
