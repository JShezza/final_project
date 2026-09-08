"""
lyrics_adapter.py

fetch plain lyrics from LRCLIB.net

never stored only cached for the look up to prevent querying constantly on req
"""

import sqlite3
import time
from pathlib import Path

import requests

API_ROOT = "https://lrclib.net/api/get"
USER_AGENT = "NextTrack/0.1 (student project)"
CACHE_STORE = Path(__file__).parent / "data" / "lyrics_cache" / "lyrics_lookup.sqlite"
GAP_SECONDS = 0.1
MISS_TTL_SECONDS = 30 * 24 * 3600

FOUND, MISSING, INSTRUMENTAL = "found", "missing", "instrumental"


class LyricsAdapter:
    def __init__(self, cache_path: Path = CACHE_STORE):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(cache_path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS lookups ("
            "   key        TEXT PRIMARY KEY,"
            "   status     TEXT NOT NULL,"  # found / missing / instrumental
            "   fetched_at REAL NOT NULL)"
        )
        self.db.commit()
        self._last_request = 0.0

    @staticmethod
    def _key(artist: str, title: str) -> str:
        return f"{artist.strip().lower()}|{title.strip().lower()}"

    def _status(self, key: str) -> str | None:
        row = self.db.execute(
            "SELECT status, fetched_at FROM lookups WHERE key = ?", (key,)
        ).fetchone()

        if row is None:
            return None

        status, fetched_at = row

        if status == MISSING and time.time() - fetched_at > MISS_TTL_SECONDS:
            return None
        return status

    def _remember(self, key: str, status: str):
        self.db.execute(
            "INSERT OR REPLACE INTO lookups VALUES (?, ?, ?)",
            (key, status, time.time()),
        )
        self.db.commit()

    def fetch_lyrics(self, artist: str, title: str) -> tuple[str, str | None]:
        """
        Return (status, lyrics). Lyrics is the plain text when status is found
        and None otherwise.
        """
        key = self._key(artist, title)
        known = self._status(key)
        if known in (MISSING, INSTRUMENTAL):
            return known, None

        wait = GAP_SECONDS - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)

        try:
            resp = requests.get(
                API_ROOT,
                params={"artist_name": artist, "track_name": title},
                headers={"User-Agent": USER_AGENT},
                timeout=8,
            )
        except requests.RequestException:
            return MISSING, None
        self._last_request = time.time()

        if resp.status_code == 404:
            self._remember(key, MISSING)
            return MISSING, None
        if resp.status_code != 200:
            return MISSING, None  # Don't cache

        payload = resp.json()
        if payload.get("instrumental"):
            self._remember(key, INSTRUMENTAL)
            return INSTRUMENTAL, None

        text = payload.get("plainLyrics")
        if not text:
            self._remember(key, MISSING)
            return MISSING, None

        self._remember(key, FOUND)

        return FOUND, text
