"""
ab_router.py

Simple A/B router assigning each request to a strategy variant

A variant is just a named blender weight (blender.VARIANTS)
mapped from user_id -> variant name

Requests without user_id can't be tracked across calls so they get the default variant
and are excluded from experiements
"""

import hashlib

from blender import VARIANTS

DEFAULT_VARIANT = "balanced"


def assign_variant(user_id: str | None) -> str:
    """Deterministically map user_id onto a named variant"""

    if not user_id:
        return DEFAULT_VARIANT

    names = sorted(VARIANTS)
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()

    return names[int(digest, 16) % len(names)]
