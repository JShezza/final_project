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

import requests

API_ROOT = "http://ws.audioscrobbler.com/2.0/"
CACHE_STORE = Path(__file__).parent / "data" / "lastfm_cache" / "lastfm_cache.sqlite"
CACHE_SECONDS_TTL = 7 * 24 * 3600
GAP_SECONDS = 0.25  # 4 requests a second


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
            "SELECT response, fetched_at FROM cache WHERE key = ?", (key,)
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

    # HTTP LAyer
    def _get(self, method: str, **params) -> dict:
        """Call a method from Last.fm API using the cache first"""
        key = (
            method
            + "|"
            + "|".join(f"{k}={str(v).lower()}" for k, v in sorted(params.items()))
        )

        cached = self._cache_get(key)
        if cached is not None:
            return cached

        # rate limiting
        wait = GAP_SECONDS - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)

        resp = requests.get(
            API_ROOT,
            params={
                "method": method,
                "api_key": self.api_key,
                "format": "json",
                **params,
            },
            timeout=10,
        )

        self._last_request = time.time()
        resp.raise_for_status()
        payload = resp.json()
        self._cache_put(key, payload)

        return payload

    # Signal methods
    def similar_tracks(self, artist: str, track: str, limit: int = 20) -> list[dict]:
        """
        Collab signal.
        Returns a list of {artist, name, matches} dicts, where a match is the 0-1 from last.fm scoring
        Returns empty [] if track is unknown.
        """

        payload = self._get(
            "track.getSimilar", artist=artist, track=track, limit=limit, autocorrect=1
        )

        # Handle unknown tracks
        if "error" in payload:
            return []

        raw = payload.get("similartracks", {}).get("track", [])
        return [
            {
                "artist": t.get("artist", {}).get("name", ""),
                "name": t.get("name", ""),
                "match": float(t.get("match", 0.0)),
                # data for novelty
                "playcount": int(t.get("playcount", 0) or 0),
            }
            for t in raw
        ]

    def popularity(self, artist: str, track: str) -> dict | None:
        """
        Grab popularity data for novelty parameter.
        Returns { playcount, listeners } or None
        """

        payload = self._get("track.getInfo", artist=artist, track=track, autocorrect=1)

        if "error" in payload or "track" not in payload:
            return None

        info = payload["track"]

        return {
            "playcount": int(info.get("playcount", 0)),
            "listeners": int(info.get("listeners", 0)),
        }


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    key = os.environ.get("LASTFM_API_KEY")
    # error handle no env
    if not key:
        raise SystemExit("No LASTFM_API_KEY in .env")

    adapter = LastFmAdapter(api_key=key)
    # Simple test for chef believe
    print("Similar to Kendrick Lamar - HUMBLE.:")
    for t in adapter.similar_tracks("Kendrick Lamar", "HUMBLE.", limit=5):
        print(f"{t['match']:.3f} {t['name']} - {t['artist']}")
    print("\nPopularirty:", adapter.popularity("Kendrick Lamar", "HUMBLE."))
