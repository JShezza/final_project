"""
test_integration

end-to-end tests for trhe full pipeline via HTTP with FastAPI TestClient
"""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

import main
from ab_router import assign_variant
from blender import VARIANTS

# Seed from the dataset.
SEED = "7lmeHLHBe4nmXzuXc0HDjk"


class FakeAdapter:
    """Stand-in for the Last.fm adapter."""

    def similar_tracks(self, artist, track, limit=20):
        return [
            {
                "name": "Killing In The Name",
                "artist": "Rage Against The Machine",
                "match": 1.0,
                "playcount": 9_000_000,
            },
            {
                "name": "Bulls On Parade",
                "artist": "Rage Against The Machine",
                "match": 0.9,
                "playcount": 5_000_000,
            },
            {
                "name": "Some Song We Do Not Have",
                "artist": "Nobody",
                "match": 0.8,
                "playcount": 100,
            },
        ]


@pytest.fixture
def client(monkeypatch):
    """Use a fresh client and restore the app's adapter after each test."""
    monkeypatch.setattr(main, "adapter", None)
    test_client = TestClient(main.app)
    try:
        yield test_client
    finally:
        test_client.close()


def test_audio_only_fallback(client):
    """Without an adapter, the API returns an audio-only rationale."""
    response = client.post("/recommend", json={"seed_tracks": [SEED], "limit": 5})
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["variant"] == "balanced"

    top = body["results"][0]
    assert top["rationale"].get("collaborative", 0.0) == 0.0
    assert top["rationale"]["audio"] > 0


def test_hybrid_blend_over_http(client, monkeypatch):
    """Collaborative results join the blend."""
    monkeypatch.setattr(main, "adapter", FakeAdapter())
    response = client.post(
        "/recommend",
        json={"seed_tracks": [SEED], "limit": 5, "parameters": {"novelty": 0.0}},
    )
    assert response.status_code == 200, response.text

    body = response.json()
    names = [track["name"] for track in body["results"]]
    assert "Killing In the Name" in names[:2], names
    killing = next(
        track for track in body["results"] if track["name"] == "Killing In the Name"
    )
    assert killing["rationale"]["collaborative"] > 0
    assert "Some Song We Do Not Have" not in names


def test_novelty_over_http(client, monkeypatch):
    """Novelty=1 reduces the popular collaborative hit's score."""
    monkeypatch.setattr(main, "adapter", FakeAdapter())

    def top_score_of(novelty):
        response = client.post(
            "/recommend",
            json={
                "seed_tracks": [SEED],
                "limit": 5,
                "parameters": {"novelty": novelty},
            },
        )
        assert response.status_code == 200, response.text
        for track in response.json()["results"]:
            if track["name"] == "Killing In the Name":
                return track["score"]
        return 0.0

    assert top_score_of(1.0) < top_score_of(0.0)


def test_variant_assignment(client):
    """A user always receives the same valid variant."""
    variant = assign_variant("stinky")
    assert variant == assign_variant("stinky") == assign_variant("stinky")
    assert variant in VARIANTS
    assert assign_variant(None) == "balanced"

    response = client.get(
        "/experiments/blend-test/variant", params={"user_id": "stinky"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["variant"] == variant

    recommendation = client.post(
        "/recommend", json={"seed_tracks": [SEED], "user_id": "stinky", "limit": 1}
    )
    assert recommendation.status_code == 200, recommendation.text
    assert recommendation.json()["variant"] == variant


def test_report_contract(client):
    """The API returns results and a request ID, and validates target_mood."""
    response = client.post("/recommend", json={"seed_tracks": [SEED]})
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["results"]
    assert "request_id" in body and body["request_id"]

    calm = client.post(
        "/recommend",
        json={"seed_tracks": [SEED], "parameters": {"target_mood": "calm"}},
    )
    assert calm.status_code == 200, calm.text

    bad = client.post(
        "/recommend",
        json={"seed_tracks": [SEED], "parameters": {"target_mood": "angry"}},
    )
    assert bad.status_code == 422


def test_outcome_logging_feedback(client):
    """Requests, feedback, and metrics complete the A/B loop."""
    response = client.post(
        "/recommend", json={"seed_tracks": [SEED], "user_id": "stinky", "limit": 3}
    )
    assert response.status_code == 200, response.text

    body = response.json()
    request_id, track = body["request_id"], body["results"][0]["id"]

    row = main.logger.db.execute(
        "SELECT variant, results FROM requests WHERE request_id = ?", (request_id,)
    ).fetchone()
    assert row is not None, "request wasn't logged"
    assert row[0] == body["variant"]
    assert track in json.loads(row[1])

    # Store only the user ID's hash.
    user_key = main.logger.db.execute(
        "SELECT user_key FROM requests WHERE request_id = ?", (request_id,)
    ).fetchone()[0]
    assert user_key == hashlib.sha256(b"stinky").hexdigest()
    assert user_key != "stinky"

    feedback = client.post(
        "/feedback",
        json={"request_id": request_id, "track_id": track, "rating": "up"},
    )
    assert feedback.status_code == 200, (feedback.status_code, feedback.text)
    assert (
        main.logger.db.execute(
            "SELECT rating FROM feedback WHERE request_id = ?", (request_id,)
        ).fetchone()[0]
        == "up"
    )

    assert (
        client.post(
            "/feedback", json={"request_id": "nope", "track_id": track, "rating": "up"}
        ).status_code
        == 404
    )

    metrics = client.post(
        "/experiments/blend-test/metrics",
        json={"user_id": "stinky", "metric": "session_length", "value": 4.0},
    )
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["variant"] == assign_variant("stinky")
