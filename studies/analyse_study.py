"""
anaylse_study.py

anaylses a rating around the outcome log. Works on participants ratings and on simulated ones
reads data/outcomes.sqlite and doesn't know which produced it.


per rater and variant compues a satisfaction rating:
    (ups - downs) / rated in [-1, 1]

skips count in the denominator but not numerator: classed as disinteerest not a rejection

usage
    python -m studies.analyse_study
    python -m studies.analyse_study --experiment "round 1"
"""

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

DB_PATH = Path(__file__).parent.parent / "data" / "outcomes.sqlite"
SESSION_MAP = Path(__file__).parent / "session_map.json"


def load(db_path: Path):
    """join feedback to the request that it produced"""
    db = sqlite3.connect(db_path)
    rows = db.execute("""
        SELECT r.user_key, r.variant, f.rating
        FROM feedback f
        JOIN requests r ON r.request_id = f.request_id
        WHERE r.user_key IS NOT NULL
        """).fetchall()

    db.close()
    return rows


def satisfaction(rows, key_to_rater=None):
    """
    {rater: {variant: (satisfaction, n_rated)}}

    A rater uses one  session key per variant and log only stores the keys hash
    """

    counts = defaultdict(lambda: defaultdict(lambda: {"up": 0, "down": 0, "skip": 0}))

    for user_key, variant, rating in rows:
        rater = (key_to_rater or {}).get(user_key, user_key)
        counts[rater][variant][rating] += 1

    out = {}
    for user_key, by_variant in counts.items():
        out[user_key] = {}
        for variant, c in by_variant.items():
            n = c["up"] + c["down"] + c["skip"]

            if n:
                out[user_key][variant] = ((c["up"] - c["down"]) / n, n)

    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--experiment", default="round 1", help="label for output")
    ap.add_argument(
        "--out", type=Path, default=Path(__file__).parent / "study_results.json"
    )
    ap.add_argument(
        "--session-map",
        type=Path,
        default=SESSION_MAP,
        help="hashed session key -> rater",
    )
    args = ap.parse_args()

    rows = load(args.db)
    if not rows:
        raise SystemExit("No ratings joined requests. Run study before this.")

    key_to_rater = {}
    if args.session_map.exists():
        key_to_rater = json.load(open(args.session_map))
        print(
            f"Pairing by rater using {args.session_map.name} ({len(key_to_rater)} keys)\n"
        )

    per_user = satisfaction(rows, key_to_rater)
    variants = sorted({v for u in per_user.values() for v in u})

    print(
        f"--- {args.experiment}: {len(rows)} ratings from {len(per_user)} raters ---\n"
    )
    print(f"{'variant':>12} | {'rater':>6} | {'ratings':>7}")

    summary = {}
    for variant in variants:
        scores = [u[variant][0] for u in per_user.values() if variant in u]
        rated = sum(u[variant][1] for u in per_user.values() if variant in u)
        summary[variant] = {
            "mean_satisfaction": float(np.mean(scores)),
            "raters": len(scores),
            "ratings": rated,
        }
        print(
            f"{variant:>12} | {np.mean(scores):>12.3f} | {len(scores):>6} | {rated:>7}"
        )

    # Pair raters who rated in both variants
    print("\nPaired comparison (wilcoxon)")
    tests = {}
    for i, a in enumerate(variants):
        for b in variants[i + 1 :]:
            xa, xb = [], []
            for key, by_variant in per_user.items():
                if a in by_variant and b in by_variant:
                    xa.append(by_variant[a][0])
                    xb.append(by_variant[b][0])

            if len(xa) < 6:
                print(f" {a} vs {b}: only {len(xa)} raters rated both - skipped")
                continue

            if np.allclose(xa, xb):
                print(f" {a} vs {b}: indentical on every rater")
                continue

            result = wilcoxon(xa, xb)
            stat = float(result.statistic)  # type: ignore[attr-defined]
            p = float(result.pvalue)  # type: ignore[attr-defined]
            verdict = "significant" if p < 0.05 else "not significant"
            print(
                f"  {a} vs {b}: w={stat:.0f}, p={p:.3g}, n={len(xa)} "
                f"(means {np.mean(xa):.3f} vs {np.mean(xb):.3f}) - {verdict}"
            )
            tests[f"{a}_vs_{b}"] = {
                "W": float(stat),
                "p": float(p),
                "n": len(xa),
                "mean_a": float(np.mean(xa)),
                "mean_b": float(np.mean(xb)),
            }

    json.dump(
        {"experiment": args.experiment, "summary": summary, "tests": tests},
        open(args.out, "w"),
        indent=2,
    )
    print(f"\nWritten to {args.out.name}")


if __name__ == "__main__":
    main()
