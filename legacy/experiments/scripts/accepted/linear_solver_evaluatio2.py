#!/usr/bin/env python3
import numpy as np
import matplotlib.pyplot as plt

# ============================================================
# ======================== INPUT DATA ========================
# ============================================================

data = {
    "Cholmod": {
        "N=3 (ms)":     [3.5, 7.3, 26.8],
        "N=30 (ms)":    [35.5, 37.9, 40.3],
        "N=3000 (s)":   [3.4, 3.19, 3.87],
        "N=30000 (s)":  [38.01, 38.56, 38.88],
    },
    "sparse": {
        "N=3 (ms)":     [3.3, 7.1, 27.5],
        "N=30 (ms)":    [34.4, 36.8, 39.1],
        "N=3000 (s)":   [3.226, 3.10, 3.66],
        "N=30000 (s)":  [35.93, 37.44, 37.90],
    },
    "eigenumfpacklu": {
        "N=3 (ms)":     [3.3, 7.1, 27.9],
        "N=30 (ms)":    [33.8, 36.4, 38.8],
        "N=3000 (s)":   [3.22, 3.05, 3.68],
        "N=30000 (s)":  [35.4, 36.1, 37.3],
    },
}

# ============================================================
# ===================== STYLE CONTROL ========================
# ============================================================

FIG_W_IN = 7.1
FIG_H_IN = 2.2

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman"],
    "text.usetex": False,   # change to True if your LaTeX setup works
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "figure.dpi": 300,
})

# ============================================================
# ====================== PREPARE DATA ========================
# ============================================================

solvers = list(data.keys())
horizons = list(next(iter(data.values())).keys())

means = {h: [] for h in horizons}
mins = {h: [] for h in horizons}
maxs = {h: [] for h in horizons}

for h in horizons:
    for solver in solvers:
        vals = np.array(data[solver][h], dtype=float)
        means[h].append(np.mean(vals))
        mins[h].append(np.min(vals))
        maxs[h].append(np.max(vals))

# ============================================================
# ========================= PLOTTING =========================
# ============================================================

fig, axes = plt.subplots(1, 4, figsize=(FIG_W_IN, FIG_H_IN), constrained_layout=True)

for j, h in enumerate(horizons):
    ax = axes[j]

    y = np.array(means[h])
    y_min = np.array(mins[h])
    y_max = np.array(maxs[h])

    # asymmetric error bars: mean to min / mean to max
    yerr = np.vstack([y - y_min, y_max - y])

    x = np.arange(len(solvers))

    bars = ax.bar(
        x,
        y,
        yerr=yerr,
        capsize=3,
        alpha=0.85
    )

    # overlay raw measurements as small markers
    for i, solver in enumerate(solvers):
        vals = np.array(data[solver][h], dtype=float)
        ax.plot(
            np.full_like(vals, x[i], dtype=float),
            vals,
            "o",
            markersize=3
        )

    ax.set_title(h)
    ax.set_xticks(x)
    ax.set_xticklabels(solvers, rotation=25, ha="right")

    if j == 0:
        ax.set_ylabel("Runtime")

    ax.grid(True, axis="y", alpha=0.35)

# Optional overall title
# fig.suptitle("Linear solver runtime comparison")

out = "linear_solver_comparison.pdf"
fig.savefig(out, bbox_inches="tight")
print(f"Saved to {out}")

plt.show()