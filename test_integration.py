"""
test_integration

end-to-end tests for trhe full pipeline via HTTP with FastAPI TestClient
"""

from fastapi.testclient import TestClient

import main
from ab_router import assign_variant
from blender import VARIANTS

client = TestClient(main.app)

# SEED FROM THE DATASET, first results
SEED = "7lmeHLHBe4nmXzuXc0HDjk"


class FakeAdapter:
    """Standin for lastfm adapter"""

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


def test_audio_only_fallback():
    """No adapter but api still works. Rationale is audio only"""
    main.adapter = None

    r = client.post("/recommend", json={"seed_tracks": [SEED], "limit": 5})
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["variant"] == "balanced"  # default

    top = body["results"][0]
    assert top["rationale"].get("collaborative", 0.0) == 0.0
    assert top["rationale"]["audio"] > 0
    print("PASS Audio-only fallback")


def test_hybrid_blend_over_http():
    """Collab results join the blend"""
    main.adapter = FakeAdapter()
    r = client.post(
        "/recommend",
        json={"seed_tracks": [SEED], "limit": 5, "parameters": {"novelty": 0.0}},
    )
    assert r.status_code == 200, r.text

    body = r.json()
    names = [t["name"] for t in body["results"]]
    # Collab fav tops a balanced blend
    assert names[0] == "Killing In the Name", names
    assert body["results"][0]["rationale"]["collaborative"] > 0
    # track in the catalogue does not appear
    assert "Some Song We Do Not Have" not in names
    print("PASS: Hybrid blend over HTTP (collab candidate ranked first)")


def test_novelty_over_http():
    """Novelty=1 crushes the popular collab hit score"""
    main.adapter = FakeAdapter()

    def top_score_of(novelty):
        r = client.post(
            "/recommend",
            json={
                "seed_tracks": [SEED],
                "limit": 5,
                "parameters": {"novelty": novelty},
            },
        )
        body = r.json()
        for t in body["results"]:
            if t["name"] == "Killing In the Name":
                return t["score"]
        return 0.0

    assert top_score_of(1.0) < top_score_of(0.0)
    print("PASS: novelty parameter dampens the popular hit via API")


def test_variant_assignment():
    """Same user_id -> same variant 100% of the time. Result is a real variant"""
    a = assign_variant("stinky")
    assert a == assign_variant("stinky") == assign_variant("stinky")
    assert a in VARIANTS
    assert assign_variant(None) == "balanced"

    r = client.get("/experiments/blend-test/variant", params={"user_id": "stinky"})
    assert r.json()["variant"] == a

    main.adapter = None
    rec = client.post(
        "/recommend", json={"seed_tracks": [SEED], "user_id": "stinky", "limit": 1}
    )
    assert rec.json()["variant"] == a
    print(f"PASS: A/B assignment stable")


# to do report contract, outcome and feedback

if __name__ == "__main__":
    test_audio_only_fallback()
    test_hybrid_blend_over_http()
    test_variant_assignment()
