"""
Freeze for A/B experiemtn config for user study

variant assignment via user_id mod len(VARIANTS) over the variant names. Add, Remove
or renaming variant reassigns every existing participant

Test pin the variant set, weights and  assignment of known keys. If fail experiment config
has changed - revert it, or start a new experiment without pooling the reuslts with
the previous one
"""

import pytest

from ab_router import DEFAULT_VARIANT, assign_variant
from blender import VARIANTS

FROZEN_WEIGHTS = {
    "audio_only": {"audio": 1.0, "collaborative": 0.0, "lyric": 0.0},
    "collab_only": {"audio": 0.0, "collaborative": 1.0, "lyric": 0.0},
    "balanced": {"audio": 0.5, "collaborative": 0.5, "lyric": 0.0},
    "audio_heavy": {"audio": 0.75, "collaborative": 0.25, "lyric": 0.0},
    "full_hybrid": {"audio": 0.4, "collaborative": 0.4, "lyric": 0.2},
}

FROZEN_ASSIGNMENTS = {
    "rater01": "audio_only",
    "rater02": "audio_only",
    "rater03": "balanced",
    "alice": "audio_heavy",
    "stinky": "full_hybrid",
}


def test_variant_set_unchanged():
    assert set(VARIANTS) == set(FROZEN_WEIGHTS), (
        "The variant set changed. All participant's assignment moved; "
        "ratings collected cannot be pooled with later ones"
    )


@pytest.mark.parametrize("name", sorted(FROZEN_WEIGHTS))
def test_variant_weights_unchanged(name):
    assert VARIANTS[name] == FROZEN_WEIGHTS[name], (
        f"Weights for '{name}' changed: No longer the strategy that "
        f"earlier ratings were colled as."
    )


@pytest.mark.parametrize("user_id, expected", sorted(FROZEN_ASSIGNMENTS.items()))
def test_assignment_unchanged(user_id, expected):
    assert assign_variant(user_id) == expected


def test_assignment_is_deterministic():
    """Same key maps to the same variant across runs"""
    assert assign_variant("rater01") == assign_variant("rater01")
    assert assign_variant(None) == DEFAULT_VARIANT
    assert assign_variant("") == DEFAULT_VARIANT
