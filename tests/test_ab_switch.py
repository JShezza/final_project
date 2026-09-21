"""
Tests for A/B testing switch
On (default): router assigns each request a strategy and choosing one is rejected
Off: user can choose and every request is logged as user:<name> so it doesn't touch study
"""

import pytest
from fastapi.testclient import TestClient

import main
from blender import VARIANTS
from studies.analyse_study import DB_PATH, load

SEED = "7lmeHLHBe4nmXzuXc0HDjk"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "adapter", None)
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def ab_off(monkeypatch):
    monkeypatch.setattr(main, "AB_TESTING", False)


def _logged_variant(request_id):
    return main.logger.db.execute(
        "SELECT variant FROM requests WHERE request_id = ?", (request_id,)
    ).fetchone()[0]


def test_ab_on_assigns_strategy(client):
    body = client.post("/recommend", json={"seed_tracks": [SEED]}).json()
    assert body["assigned"] is True


def test_ab_on_rejects_chosen_strategy(client):
    r = client.post(
        "/recommend", json={"seed_tracks": [SEED], "strategy": "full_hybrid"}
    )
    assert r.status_code == 409
    assert "AB_TESTING" in r.json()["detail"]


@pytest.mark.parametrize("strategy", sorted(VARIANTS))
def test_ab_off_honours_every_strategy(client, ab_off, strategy):
    r = client.post("/recommend", json={"seed_tracks": [SEED], "strategy": strategy})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["variant"] == strategy
    assert body["assigned"] is False


def test_ab_off_defaults_when_none_chosen(client, ab_off):
    body = client.post("/recommend", json={"seed_tracks": [SEED]}).json()
    assert body["variant"] == "balanced"
    assert body["assigned"] is False


def test_ab_off_ignores_session_key(client, ab_off):
    """With a/b off a session key no longer decides strategy"""
    body = client.post(
        "/recommend",
        json={"seed_tracks": [SEED], "user_id": "stinky", "strategy": "audio_only"},
    ).json()
    assert body["variant"] == "audio_only"


def test_ab_off_logs_separtely(client, ab_off):
    body = client.post(
        "/recommend", json={"seed_tracks": [SEED], "strategy": "full_hybrid"}
    ).json()
    assert _logged_variant(body["request_id"]) == "user:full_hybrid"


def test_ab_off_ratings_excluded_from_analysis(client, ab_off):
    body = client.post(
        "/recommend",
        json={
            "seed_tracks": [SEED],
            "user_id": "ab-off-check",
            "strategy": "full_hybrid",
        },
    ).json()

    client.post(
        "/feedback",
        json={
            "request_id": body["request_id"],
            "track_id": body["results"][0]["id"],
            "rating": "up",
        },
    )

    variants_seen = {variant for _, variant, _ in load(DB_PATH)}
    assert not any(v.startswith("user:") for v in variants_seen)


def test_unknown_strategy_rejected(client, ab_off):
    r = client.post("/recommend", json={"seed_tracks": [SEED], "strategy": "nope"})
    assert r.status_code == 422


def test_health_reports_ab_state(client, monkeypatch):
    assert client.get("/health").json()["ab_testing"] is True
    monkeypatch.setattr(main, "AB_TESTING", False)
    assert client.get("/health").json()["ab_testing"] is False
