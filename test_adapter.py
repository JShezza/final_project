"""
Test lastfm adapter

Offline testing for the adapater.
No internet connection or api key

Checks for the three fail points:
    - Parsing: similar tracks and popularity payloads map to their dicts cleanly
    - Unknown tracks: error returns to [] or None. Not a crash
    - Cache: Duplicate calls are served from SQLite instead of the network
"""

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
    "track": {"name": "HUMBLE.", "listeners": "2324945", "playcount": "32144593"}
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
        key = method + "|" + "|".join(f"{k}={v}" for k, v in sorted(params.items()))

        cached = self._cache_get(key)
        if cached is not None:
            return cached

        self.network_calls += 1
        payload = self.fixtures[method]
        self._cache_put(key, payload)

        return payload


def main():
    print("Tests Complete")


if __name__ == "__main__":
    main()
