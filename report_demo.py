"""
report_demo.py - the two measurements the final report still needs (Sections 4.9 and 5.3).

Writes figs/fig3_e2e_rationale.png and results/report_demo.json.
Requests are logged as user:<strategy>, which analyse_study.py already excludes.
"""

import json
import random
import statistics
import sys
import time
from pathlib import Path

import requests

API = "http://127.0.0.1:8000"
SEED = "7lmeHLHBe4nmXzuXc0HDjk"
EXAMPLE_VARIANT = "full_hybrid"
NOVELTY = (0.0, 0.75)
TOP = 5
LATENCY_VARIANTS = ("audio_only", "full_hybrid")
SEEDS_PER_CONDITION = 12
SEARCH_TERMS = [
    "love",
    "night",
    "blue",
    "fire",
    "dream",
    "rain",
    "heart",
    "summer",
    "gold",
    "river",
    "home",
    "light",
    "wild",
    "city",
    "sun",
    "time",
]
BENCH_SEEDS = Path("benchmarks/benchmark_seeds.json")
FIG = Path("e2e_rationale.png")
OUT = Path("results/report_demo.json")
COLOURS = {
    "audio": "#d08c2e",
    "collaborative": "#2a9d8f",
    "lyric": "#7b5ea7",
    "novelty": "#c0392b",
    "mood": "#8e8e8e",
}


def check_api():
    try:
        health = requests.get(f"{API}/health", timeout=5).json()
    except requests.RequestException:
        sys.exit(f"API not reachable at {API}. Start it first")
    if health.get("ab_testing", False):
        sys.exit(
            "A/B testing is ON, so a strategy cannot be chosen.\nSet AB_TESTING=false in .env, fully restart uvicorn, then re-run."
        )


def recommend(seed, strategy, novelty, limit):
    body = {
        "seed_tracks": [seed],
        "limit": limit,
        "strategy": strategy,
        "parameters": {"novelty": novelty, "target_mood": "any", "exclude_seen": True},
    }
    t0 = time.perf_counter()
    r = requests.post(f"{API}/recommend", json=body, timeout=300)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    out = r.json()
    if out.get("variant") != strategy:
        sys.exit(
            f"Asked for {strategy} but the API used {out.get('variant')}. Is AB_TESTING off?"
        )
    return elapsed_ms, out


def artists(track):
    a = track.get("artists", "")
    return ", ".join(a) if isinstance(a, list) else str(a)


def short(track, width=36):
    s = f"{track.get('name') or track['id']} - {artists(track)}"
    return s if len(s) <= width else s[: width - 3] + "..."


def rows_from(body):
    rows = []
    for rank, t in enumerate(body["results"], 1):
        rat = {k: float(v) for k, v in t["rationale"].items()}
        rows.append(
            {
                "rank": rank,
                "id": t["id"],
                "name": t.get("name"),
                "artists": artists(t),
                "score": float(t["score"]),
                "rationale": rat,
                "sums_to_score": abs(sum(rat.values()) - float(t["score"])) < 1e-6,
            }
        )
    return rows


def part1():
    print(f"\n--- PART 1: one {EXAMPLE_VARIANT} request, seed {SEED} ---")
    lists = {}
    for nov in NOVELTY:
        _, body = recommend(SEED, EXAMPLE_VARIANT, nov, TOP)
        lists[nov] = rows_from(body)
        print(f"\nnovelty {nov:.2f}")
        print(
            f"{'#':>2} | {'track':<36} | {'score':>6} | "
            f"{'audio':>6} {'collab':>6} {'lyric':>6} {'novel':>6} {'mood':>6} | sum=score"
        )
        for r in lists[nov]:
            g = r["rationale"].get
            print(
                f"{r['rank']:>2} | {short(r):<36} | {r['score']:>6.3f} | "
                f"{g('audio', 0):>6.3f} {g('collaborative', 0):>6.3f} {g('lyric', 0):>6.3f} "
                f"{g('novelty', 0):>6.3f} {g('mood', 0):>6.3f} | {r['sums_to_score']}"
            )

    # Where did the tracks that left the top five go? Look deeper at novelty 0.75.
    _, deep = recommend(SEED, EXAMPLE_VARIANT, NOVELTY[1], 20)
    deep_rows = {r["id"]: r for r in rows_from(deep)}
    kept = {r["id"] for r in lists[NOVELTY[1]]}
    dropped = [r for r in lists[NOVELTY[0]] if r["id"] not in kept]
    print(f"\nLeft the top five at novelty {NOVELTY[1]}:")
    movement = []
    for r in dropped:
        new = deep_rows.get(r["id"])
        where = (
            f"now rank {new['rank']}, novelty penalty {new['rationale'].get('novelty', 0):.3f}"
            if new
            else "now outside the top 20"
        )
        print(
            f"  {short(r, 50)} (was rank {r['rank']}, collaborative {r['rationale'].get('collaborative', 0):.3f}) -> {where}"
        )
        movement.append(
            {
                "id": r["id"],
                "track": short(r, 60),
                "old_rank": r["rank"],
                "new_rank": new["rank"] if new else None,
                "novelty_penalty": new["rationale"].get("novelty") if new else None,
            }
        )
    for nov in NOVELTY:
        n = sum(1 for r in lists[nov] if r["rationale"].get("collaborative", 0) > 0)
        print(f"Tracks with a collaborative term at novelty {nov:.2f}: {n} of {TOP}")
    return {
        "seed": SEED,
        "variant": EXAMPLE_VARIANT,
        "lists": {str(k): v for k, v in lists.items()},
        "left_top_five": movement,
    }, lists


def figure(lists):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
    except ImportError:
        print("\nmatplotlib is not installed")
        return
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.8), sharex=True)
    seen = set()
    for ax, nov in zip(axes, NOVELTY):
        rows = lists[nov]
        for y, row in enumerate(rows):
            pos, neg = 0.0, 0.0
            for key, val in row["rationale"].items():
                seen.add(key)
                colour = COLOURS.get(key, "#555555")
                if val >= 0:
                    ax.barh(
                        y, val, left=pos, color=colour, edgecolor="white", height=0.62
                    )
                    pos += val
                else:
                    ax.barh(
                        y,
                        val,
                        left=neg,
                        color=colour,
                        edgecolor="white",
                        height=0.62,
                        hatch="///",
                    )
                    neg += val
            ax.plot(row["score"], y, marker="D", color="black", ms=6, zorder=5)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([f"{r['rank']}. {short(r)}" for r in rows], fontsize=8)
        ax.invert_yaxis()
        ax.axvline(0, color="black", lw=0.8)
        ax.grid(axis="x", alpha=0.25)
        ax.set_title(f"novelty = {nov:g}", fontsize=10)
        ax.set_xlabel("contribution to score (penalties are negative)", fontsize=8.5)
    handles = [Patch(color=COLOURS[k], label=k) for k in COLOURS if k in seen]
    handles.append(
        Line2D([], [], marker="D", color="black", ls="none", label="final score")
    )
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(handles),
        fontsize=8,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    FIG.parent.mkdir(exist_ok=True)
    fig.savefig(FIG, dpi=220)
    print(f"\nFigure 3 written to {FIG}")


def search_ids(term):
    for limit in (50, 20, None):
        params = {"q": term} if limit is None else {"q": term, "limit": limit}
        r = requests.get(f"{API}/tracks/search", params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = data.get("results", []) if isinstance(data, dict) else data
            return [t["id"] for t in items if isinstance(t, dict) and t.get("id")]
    return []


def fresh_seeds(n, exclude, rng):
    pool = []
    for term in SEARCH_TERMS:
        pool += [i for i in search_ids(term) if i not in exclude]
    pool = list(dict.fromkeys(pool))
    rng.shuffle(pool)
    if len(pool) < n:
        sys.exit(
            "Not enough search results to pick fresh seeds; add words to SEARCH_TERMS."
        )
    return pool[:n]


def part2():
    print(
        f"\n--- PART 2: end-to-end latency, {SEEDS_PER_CONDITION} fresh seeds per variant ---"
    )
    rng = random.Random(2026)
    used = {SEED}
    if BENCH_SEEDS.exists():
        used |= {
            s["id"] for group in json.load(open(BENCH_SEEDS)).values() for s in group
        }
    out = {}
    for variant in LATENCY_VARIANTS:
        seeds = fresh_seeds(SEEDS_PER_CONDITION, used, rng)
        used |= set(seeds)
        cold, warm, with_collab, with_lyric = [], [], 0, 0
        for i, seed in enumerate(seeds, 1):
            cold_ms, body = recommend(seed, variant, 0.5, 10)
            warm_ms = statistics.median(
                recommend(seed, variant, 0.5, 10)[0] for _ in range(3)
            )
            cold.append(cold_ms)
            warm.append(warm_ms)
            terms = [t["rationale"] for t in body["results"]]
            with_collab += any(r.get("collaborative", 0) > 0 for r in terms)
            with_lyric += any(r.get("lyric", 0) > 0 for r in terms)
            print(
                f"  {variant:<12} seed {i:>2}/{len(seeds)}: cold {cold_ms:8.0f} ms   warm {warm_ms:7.0f} ms"
            )
        out[variant] = {
            "n": len(seeds),
            "seeds": seeds,
            "cold_ms": cold,
            "warm_ms": warm,
            "cold_median": statistics.median(cold),
            "cold_max": max(cold),
            "warm_median": statistics.median(warm),
            "warm_max": max(warm),
            "seeds_with_collab_results": with_collab,
            "seeds_with_lyric_results": with_lyric,
        }
    print(f"\n{'variant':<12} {'cache':<5} {'median ms':>10} {'max ms':>9}")
    for v, s in out.items():
        print(f"{v:<12} {'cold':<5} {s['cold_median']:>10.0f} {s['cold_max']:>9.0f}")
        print(f"{v:<12} {'warm':<5} {s['warm_median']:>10.0f} {s['warm_max']:>9.0f}")
    for v, s in out.items():
        print(
            f"{v}: {s['seeds_with_collab_results']}/{s['n']} seeds had Last.fm results, "
            f"{s['seeds_with_lyric_results']}/{s['n']} had lyric terms"
        )
    return out


if __name__ == "__main__":
    check_api()
    example, lists = part1()
    figure(lists)
    latency = part2()
    OUT.parent.mkdir(exist_ok=True)
    json.dump({"example": example, "latency": latency}, open(OUT, "w"), indent=2)
    print(f"\nAll numbers saved to {OUT}..")
