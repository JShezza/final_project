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
EFFECT_SIZES = [0.02, 0.05, 0.10, 0.15, 0.20]
RATER_COUNTS = [10, 20, 30, 50, 80, 100, 200]


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


def required_n(effect: float, sd: float, trials: int, rng) -> int | None:
    """Smallest rater count reaching TARGET_POWER searching upward"""
    for n in range(5, 1001, 5):
        if power_at(n, effect, sd, max(trials // 4, 100), rng) >= TARGET_POWER:
            return n
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--session-map", type=Path, default=SESSION_MAP)
    ap.add_argument(
        "--trials", type=int, default=1000, help="simulated studies per cell"
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--out", type=Path, default=Path(__file__).parent / "power_analysis.json"
    )
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    a, b, observed_diff, sd, n_raters = observed_spread(args.db, args.session_map)

    print("Power Analysis: How many raters would a study need?\n")
    print(f"Measured from {n_raters} raters in rating pipeline:")
    print(f"   comparison               : {a} vs {b}")
    print(f"   observed mean diff       : {observed_diff:+.3f}")
    print(f"   between-rater SD of that : {sd:.3f}")
    print(
        "\nThe SD is what determines power: the more raters disagree, the more of them needed to see a difference."
    )

    # Power grid
    print(
        f"Power (proportion of studies reading p < {ALPHA}), "
        f"{args.trials} simulated per cell"
    )
    header = f"{'raters':>7} | " + " | ".join(f"d={e:<5.2f}" for e in EFFECT_SIZES)
    print(header)
    print("-" * len(header))

    grid = {}
    for n in RATER_COUNTS:
        cells = [power_at(n, e, sd, args.trials, rng) for e in EFFECT_SIZES]
        grid[n] = dict(zip((str(e) for e in EFFECT_SIZES), cells))
        print(f"{n:7} | " + " | ".join(f"{c:>7.0%}" for c in cells))

    # sample sizes
    print(f"\nRaters needed for {TARGET_POWER:.0%} power:")
    needed = {}
    for e in EFFECT_SIZES:
        n = required_n(e, sd, args.trials, rng)
        needed[str(e)] = n
        label = f"{n} raters" if n else "more than 1000 raters"
        print(f"  difference of {e:.2f}: {label}")

    # details about the observed diff
    obs = abs(observed_diff)
    n_obs = required_n(obs, sd, args.trials, rng) if obs > 0.001 else None
    print(
        f"\nThe observed difference of {observed_diff:_.3f} would need "
        f"{n_obs if n_obs else 'more than 1000'} raters to detect reliably."
    )

    if n_obs is None or n_obs > 200:
        print("A diference that small is not worht designing a study.")
        print(
            "either the variance is close or the rating scale is too corase to seperate them"
        )
        print(
            "A finer scale (five-point Likert rather than up/down/skip) would reduce variance"
        )
        print("and cut the number of raters down.")

        json.dump(
            {
                "comparison": f"{a} vs {b}",
                "observed_mean_difference": observed_diff,
                "between_rater_sd": sd,
                "raters_measured": n_raters,
                "alpha": ALPHA,
                "target_power": TARGET_POWER,
                "power_grid": grid,
                "raters_required": needed,
            },
            open(args.out, "w"),
            indent=2,
        )
        print(f"\nWritten to {args.out.name}")


if __name__ == "__main__":
    main()
