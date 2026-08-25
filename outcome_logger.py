"""
outcome_logger.py

Anonymised outcome logging:
data source ofr offline A/B analysis

every /recommend is written as one row (timestamp, anonymised user key, variant,
seeds, parameters and the returned track is.) each request gets a request_id that
is returned to the API response so feedback (thumbs up on X for Y request.)
That join is what makes the variants comparable on real outcomes


Anonymisation: user_id is stored only has a sha256 has. Opaque by design, hash means
key never sits in the log. No other user data exists to store

storage is SQLite
"""

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

from requests import request

DB_PATH = Path(__file__).parent / "data" / "outcomes.sqlite"


def _anon(user_id: str | None) -> str | None:
    if user_id is None:
        return None
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()


class OutcomeLogger:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY,
                ts         REAL NOT NULL,
                user_key   TEXT,
                variant    TEXT NOT NULL,
                seeds      TEXT NOT NULL,   -- JSON list of seed track ids
                params     TEXT NOT NULL,   -- JSON of preference parameters
                results    TEXT NOT NULL    -- JSON list of returned track ids
            );
            CREATE TABLE IF NOT EXISTS feedback (
                request_id TEXT NOT NULL,
                track_id   TEXT NOT NULL,
                rating     TEXT NOT NULL,   -- up / down / skip
                ts         REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metrics (
                experiment TEXT NOT NULL,
                ts         REAL NOT NULL,
                user_key   TEXT,
                variant    TEXT,
                metric     TEXT NOT NULL,
                value      REAL NOT NULL
            );
            """)
        self.db.commit()

    def log_request(self, user_id, variant, seeds, params, result_ids) -> str:
        """Write a request row and return the request_id"""
        request_id = uuid.uuid4().hex
        self.db.execute(
            "INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                request_id,
                time.time(),
                _anon(user_id),
                variant,
                json.dumps(seeds),
                json.dumps(params),
                json.dumps(result_ids),
            ),
        )
        self.db.commit()
        return request_id

    def log_feedback(self, request_id: str, track_id: str, rating: str) -> bool:
        """Record a rating. If false the request_id was never logged"""
        known = self.db.execute(
            "SELECT 1 FROM requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if known is None:
            return False

        self.db.execute(
            "INSERT INTO feedback VALUES (?, ?, ?, ?)",
            (request_id, track_id, rating, time.time()),
        )
        self.db.commit()

        return True

    def log_metric(self, experiment, user_id, variant, metric, value):
        self.db.execute(
            "INSERT INTO metrics VALUES (?, ?, ?, ?, ?, ?)",
            (experiment, time.time(), _anon(user_id), variant, metric, value),
        )
        self.db.commit()
