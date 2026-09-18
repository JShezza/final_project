"""
power_analysis.py

How large of a difference between raters disagree with each other. Is the difference
big? Could a study of N people actually detect a large diffence between two variants
"""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

from .analyse_study import DB_PATH, SESSION_MAP, load, satisfaction

ALPHA = 0.05
TARGET_POWER = 0.80


def observed_spread(db_path: Path, session_map: Path):
    """
    mean and standard deviation of per rater difference between variants.
    """
    rows = load(db_path)
    if not rows:
        raise SystemExit("No ratings found. Run a study")

    keys_to_rater = json.load(open(session_map)) if session_map.exists() else {}
    per_rater = satisfaction(rows, keys_to_rater)

    variants = sorted({v for r in per_rater.values() for v in r})
    if len(variants) < 2:
        raise SystemExit(f"Need two variants to compare. Found: {variants}")

    a, b = variants[0], variants[1]

    diffs = [
        scores[a][0] - scores[b][0]
        for scores in per_rater.values()
        if a in scores and b in scores
    ]

    if len(diffs) < 3:
        raise SystemExit("Too few raters in both variants to measure spread")

    return a, b, float(np.mean(diffs)), float(np.std(diffs, ddof=1)), len(diffs)


def power_at(n: int, effect, sd: float, trials: int, rng):
    """proportion of simulated studies that detect effect with `n` raters."""
    detected = 0
    for _ in range(trials):
        diffs = rng.normal(loc=effect, scale=sd, size=n)
        if np.allclose(diffs, 0):
            continue
        try:
            p = float(wilcoxon(diffs).pvalue)  # type: ignore[attr-defined]
        except ValueError:
            continue
        if p < ALPHA:
            detected += 1

    return detected / trials


def require_n(effect: float, sd: float, trials: int, rng) -> int | None:
    """Smallest rater count reaching TARGET_POWER searching upward"""
    for n in range(5, 1001, 5):
        if power_at(n, effect, sd, max(trials // 4, 100), rng) >= TARGET_POWER:
            return n
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
