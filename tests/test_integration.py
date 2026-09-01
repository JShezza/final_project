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
    assert "Killing In the Name" in names[:2], names
    killing = next(t for t in body["results"] if t["name"] == "Killing In the Name")
    assert killing["rationale"]["collaborative"] > 0
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
def test_report_contract():
    """Defaults and fields are set"""
    main.adapter = None

    # No limit = 1 track
    r = client.post("/recommend", json={"seed_tracks": [SEED]})
    assert r.status_code == 200, r.text

    body = r.json()
    assert len(body["results"])
    assert "request_id" in body and body["request_id"]

    # target_mood is part of the contract
    r2 = client.post(
        "/recommend",
        json={"seed_tracks": [SEED], "parameters": {"target_mood": "calm"}},
    )
    assert r2.status_code == 200, r2.text

    bad = client.post(
        "/recommend",
        json={"seed_tracks": [SEED], "parameters": {"target_mood": "angry"}},
    )
    assert bad.status_code == 422
    print("pass: Contract matches (limit default 1, target_mood)")


def test_outcome_logging_feedback():
    """A/B loop closes properly: request logged -> feedback conkoined via request_id"""

    main.adapter = None
    r = client.post(
        "/recommend", json={"seed_tracks": [SEED], "user_id": "stinky", "limit": 3}
    )

    body = r.json()
    rid, track = body["request_id"], body["results"][0]["id"]

    row = main.logger.db.execute(
        "SELECT variant, results FROM requests WHERE request_id =?", (rid,)
    ).fetchone()
    assert row is not None, "request wasn't logged"
    assert row[0] == body["variant"]
    import hashlib
    import json as _json

    assert track in _json.loads(row[1])

    # user_id stored only as a hash and not raw
    raw = main.logger.db.execute(
        "SELECT user_key FROM requests WHERE request_id = ?", (rid,)
    ).fetchone()[0]
    assert raw == hashlib.sha256(b"stinky").hexdigest() and raw != "stinky"

    fb = client.post(
        "/feedback", json={"request_id": rid, "track_id": track, "rating": "up"}
    )
    assert fb.status_code == 200, (fb.status_code, fb.text)
    assert (
        main.logger.db.execute(
            "SELECT rating FROM feedback WHERE request_id = ?", (rid,)
        ).fetchone()[0]
        == "up"
    )

    assert (
        client.post(
            "/feedback", json={"request_id": "nope", "track_id": track, "rating": "up"}
        ).status_code
        == 404
    )

    m = client.post(
        "/experiments/blend-test/metrics",
        json={"user_id": "stinky", "metric": "session_length", "value": 4.0},
    )
    assert m.status_code == 200 and m.json()["variant"] == assign_variant("stinky")
    print("PASS: outcome logger + feedback + metrics close the A/B loop")


if __name__ == "__main__":
    test_audio_only_fallback()
    test_hybrid_blend_over_http()
    test_novelty_over_http()
    test_variant_assignment()
    test_report_contract()
    test_outcome_logging_feedback()
    print("\nAll integration tests passed")
