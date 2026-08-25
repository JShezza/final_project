"""
test_blender

Offline tests for the weighted blender. Entirely logic, no fixtures for network response
"""

import pandas as pd

from blender import (
    VARIANTS,
    Blender,
    catalogue_lookup,
    collaborative_pool,
    normalise_title,
)


def test_weighted_union():
    """Unioned signal candiates; weight split the score"""
    audio = {"A": 1.0, "B": 0.5}  # Never saw C
    collab = {"B": 1.0, "C": 0.8}  # Never saw A

    b = Blender({"audio": 0.5, "collaborative": 0.5})
    out = b.blend({"audio": audio, "collaborative": collab}, limit=3)

    scores = {r["id"]: r["score"] for r in out}
    # Hand count:
    # A = .5*1.0 + .5*0 = 0.50
    # B = .5*0.5 + .5*1.0  = 0.75
    # C = .5*0   + .5*0.8  = 0.40
    assert scores == {"B": 0.75, "A": 0.5, "C": 0.4}, scores
    assert out[0]["id"] == "B"  # Correct rank
    assert out[0]["rationale"] == {"audio": 0.25, "collaborative": 0.5}

    print("PASS: union + weighted sum + rationale")


def test_weight_normalisation():
    """Weights 3 and 1 behave like 0.75 and 0.25"""
    pools = {"audio": {"A": 1.0}, "collaborative": {"A": 1.0}}
    big = Blender({"audio": 3, "collaborative": 1}).blend(pools)
    small = Blender({"audio": 0.75, "collaborative": 0.25}).blend(pools)
    assert big == small
    print("PASS: Weights are normalised")


def test_zero_weight_disables_signal():
    """Any signal can be turned off by setting weight to 0"""
    pools = {"audio": {"A": 0.2}, "collaborative": {"B": 1.0}}
    out = Blender(VARIANTS["audio_only"]).blend(pools, limit=2)
    scores = {r["id"]: r["score"] for r in out}
    assert scores["B"] == 0.0
    assert out[0]["id"] == "A"

    print("PASS: Weight 0 disables a signal")


def test_novelty_damping():
    """When novelty is on the popular drops below a niche one"""
    pools = {"audio": {"hit": 0.9, "niche": 0.8}}
    popularity = {"hit": 10_000_000, "niche": 500}
    b = Blender({"audio": 1.0})

    plain = b.blend(pools, limit=2)
    assert plain[0]["id"] == "hit"

    novel = b.blend(pools, popularity=popularity, novelty=0.5, limit=2)
    assert novel[0]["id"] == "niche", novel
    print("PASS: novelty re-ranks toward the long tail.")


def test_normalise_title():
    a = normalise_title("HUMBLE.", "Kendrick Lamar")
    b = normalise_title("Humble", "kendrick lamar")
    assert a == b == ("humble", "kendrick lamar")
    c = normalise_title("Bohemian Rhapsody - Remastered 2011", "Queen")
    assert c == ("bohemian rhapsody", "queen")

    print("PASS: title normalised (case, punctuation, suffixes)")


def test_lastfm_to_catalogue_mapping():
    meta = pd.DataFrame(
        [
            {"id": "id1", "name": "DNA.", "artists": "Kendrick Lamar"},
            {"id": "id2", "name": "Mask Off", "artists": "Future"},
        ]
    )
    lookup = catalogue_lookup(meta)
    similar = [
        {"name": "DNA.", "artist": "Kendrick Lamar", "match": 1.0},
        {"name": "Mask Off", "artist": "Future", "match": 0.7},
        {"name": "Some Unknown Song", "artist": "Nobody", "match": 0.9},
    ]

    pool = collaborative_pool(similar, lookup)
    # matched tracks map to catalogue ids. Unknowns are dropped
    assert pool == {"id1": 1.0, "id2": 0.7}, pool
    print(
        "PASS: Last.fm results connect to the catalogue IDs with unmatched ones dropped"
    )


if __name__ == "__main__":
    test_weighted_union()
    test_weight_normalisation()
    test_zero_weight_disables_signal()
    test_novelty_damping()
    test_normalise_title()
    test_lastfm_to_catalogue_mapping()
    print("\nAll blender tests passed")
