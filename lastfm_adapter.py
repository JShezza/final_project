"""
Last.FM adapter

Collaborative signal - The adapter for Last.fm API

What we use from last.fm api:

    - track.getSimilar: Get the similar track for this track on Last.fm, based on listening data.
        This works as "listeners who listen to X also play Y", also scored from 0-1.
        Requires, a track, artist and api_key

    - track.getInfo: Get the metadata for a track on last fm using artist/track name
        returns playcount, listeners (popularity needed for the novelty paramater for bias against)

Design:
    - Last.fm has a rate limit for clients. Every response will need to be cached

"""

import json
import sqlite3
import time
from pathlib import Path

API_ROOT = "http://ws.audioscrobbler.com/2.0/"
CACHE_STORE = Path(__file__).parent / "data" / "lastfm_cache" / "lastfm_cache.sqlite"
CACHE_SECONDS_TTL = 7 * 24 * 3600


class LastFmAdapter:
    def __init__(self, api_key: str, cache_path: Path = CACHE_STORE):
        self.api_key = api_key
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(cache_path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "   key TEXT PRIMARY KEY,"
            "   response TEXT NOT NULL,"
            "   fetched_at REAL NOT NULL)"
        )
        self.db.commit()
        self._last_request = 0.0

    # Cache logic
    def _cache_get(self, key: str):
        row = self.db.execute(
            "SELECT response, fetch_at FROM cache WHERE key = ?", (key,)
        ).fetchone()

        if row is None:
            return None

        response, fetched_at = row
        if time.time() - fetched_at > CACHE_SECONDS_TTL:
            return None

        return json.loads(response)

    def _cache_put(self, key: str, payload: dict):
        self.db.execute(
            "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
            (key, json.dumps(payload), time.time()),
        )
        self.db.commit()


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    key = os.environ.get("LASTFM_API_KEY")
    # error handle no env
    if not key:
        raise SystemExit("No LASTFM_API_KEY in .env")

    adapter = LastFmAdapter(api_key=key)
