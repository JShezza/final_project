"""
test_routes.py

tests for supporting routes: similar, onboard, mood analyse/recommend
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

import main

SEED = "7lmeHLHBe4nmXzuXc0HDjk"


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)


@pytest.fixture()
def audio_only(monkeypatch):
    """Run without last.fm adapter. Results don't need a key"""
    monkeypatch.setattr(main, "adapter", None)


@pytest.fixture()
def admin_headers(client):
    tok = client.post(
        "/auth/login", json={"username": "admin", "password": "test-password"}
    )
    assert tok.status_code == 200, tok.text
    return {"Authorization": f"Bearer {tok.json()['access_token']}"}


# recommend/similar
def test_similar_returns_audio_neighbours(client):
    r = client.post("/recommend/similar", json={"track_id": SEED, "limit": 5})
    assert r.status_code == 200, r.text
    results = r.json()["results"]


def test_similar_unknown_track_404s(client):
    assert (
        client.post("/recommend/similar", json={"track_id": "nope"}).status_code == 404
    )


# /onboard
def test_onboard_seeds_from_artist(client):

    r = client.post(
        "/onboard", json={"artists": ["Rage Against The Machine"], "limit": 5}
    )

    assert r.status_code == 200, r.text
    seeds = r.json()["seeds"]
    assert 0 < len(seeds) <= 5
    assert all("Rage Against" in s["artists"] for s in seeds)


def test_onboard_accepts_mood(client):

    r = client.post(
        "/onboard",
        json={
            "artists": ["Rage Against The Machine"],
            "target_mood": "calm",
            "limit": 5,
        },
    )

    assert r.status_code == 200
    assert r.json()["target_mood"] == "calm"


def test_onboard_unknown_artist_404s(client):

    r = (
        client.post(
            "/onboard", json={"artists": ["piss shit and cum anton"]}
        ).status_code
        == 404
    )


# /mood/analyse
@pytest.mark.parametrize(
    "text, expected",
    [
        ("I feel amazing, best day ever!", "happy"),
        ("everything is awful and I feel hopeless", "sad"),
        ("the meeting is at three", "any"),
    ],
)
def test_mood_analyse_labels(client, text, expected):
    body = client.post("/mood/analyse", json={"text": text}).json()
    assert body["mood"] == expected
    if expected == "happy":
        assert body["compound"] > 0
    if expected == "sad":
        assert body["compound"] < 0


def test_mood_analyse_rejects_empty(client):
    assert client.post("/mood/analyse", json={"text": ""}).status_code == 422


# /mood/recommend


def test_mood_recommend_logs_derived_mood(client, audio_only):
    r = client.post(
        "/mood/recommend",
        json={
            "text": "I am so sad and lonely tonight",
            "seed_tracks": [SEED],
            "limit": 3,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["results"]) == 3 and body["request_id"]

    row = main.logger.db.execute(
        "SELECT params FROM requests WHERE request_id =?", (body["request_id"],)
    ).fetchone()
    assert json.loads(row[0])["target_mood"] == "sad"


# /tracks/{id}/info and features
def test_track_info(client):
    info = client.get(f"/tracks/{SEED}/info").json()
    assert info["name"] == "Testify"
    assert "Rage" in info["artists"]


def test_track_features_in_ranges(client):
    feats = client.get(f"/tracks/{SEED}/features").json()["features"]
    assert {"energy", "valence", "tempo", "loudness"} <= set(feats)
    # invert scaler must land in dataset ranges
    assert 0 <= feats["energy"] <= 1
    assert 0 <= feats["valence"] <= 1
    assert 0 < feats["tempo"] < 250
    assert feats["loudness"] < 0


def test_track_features_404(client):
    assert client.get("tracks/asdf_nope/features").status_code == 404


# adminjwt
@pytest.mark.parametrize("path", ["/admin/stats", "/admin/health"])
def test_admin_requires_token(client, path):
    assert client.get(path).status_code == 401


def test_admin_rejects_bad_token(client):
    r = client.get("/admin/stats", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401


def test_admin_routes_with_valid_token(client, admin_headers):
    stats = client.get("/admin/stats", headers=admin_headers)
    assert stats.status_code == 200
    assert "requests_by_variant" in stats.json()

    health = client.get("/admin/health", headers=admin_headers).json()
    assert health["signals"]["audio"] is True
    assert "full_hybrid" in health["variants"]


def test_admin_rejects_wrong_password(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
