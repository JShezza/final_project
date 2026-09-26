"""
Generate a png for a figure in report
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

nprobe = [1, 8, 16, 32, 64]
recall = [0.650, 0.991, 0.999, 1.000, 1.000]
ms = [0.006, 0.008, 0.010, 0.020, 0.035]
EXACT_MS = 0.343

plt.rcParams.update({"font.family": "serif", "font.size": 9})
fig, ax1 = plt.subplots(figsize=(6.4, 3.5))

ax1.plot(nprobe, recall, "o-", color="#2a6db0", lw=1.8)
ax1.set_xscale("log", base=2)
ax1.set_xticks(nprobe)
ax1.set_xticklabels(nprobe)
ax1.set_xlabel("nprobe (cells probed)")
ax1.set_ylabel("recall@10 vs exact search", color="#2a6db0")
ax1.tick_params(axis="y", labelcolor="#2a6db0")
ax1.set_ylim(0.6, 1.03)
ax1.axvline(16, color="#888888", ls="--", lw=1)
ax1.annotate(
    "default nprobe = 16:\nrecall 0.999, 33.4× faster",
    xy=(16, 0.999),
    xytext=(2.2, 0.80),
    fontsize=8,
    arrowprops=dict(arrowstyle="->", color="#555555"),
)

ax2 = ax1.twinx()
ax2.plot(nprobe, ms, "s--", color="#b0562a", lw=1.5)
ax2.set_ylabel("mean latency (ms / query)", color="#b0562a")
ax2.tick_params(axis="y", labelcolor="#b0562a")
ax2.set_ylim(0, 0.04)

ax1.set_title(
    f"IVF index accuracy against speed (1,000 query tracks; exact search {EXACT_MS} ms)",
    fontsize=9,
)

fig.tight_layout()
fig.savefig("fig4_faiss.png", dpi=300)

print("written fig4_faiss.svg and .png")
