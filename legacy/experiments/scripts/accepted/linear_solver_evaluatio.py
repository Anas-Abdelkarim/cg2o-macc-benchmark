#!/usr/bin/env python3
import argparse

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# ============================================================
# ========================= DATA =============================
# ============================================================

raw_data = {
    "N=3": {
        "unit": "ms",
        "Cholmod": [3.5, 7.3, 26.8],
        "sparse": [3.3, 7.2, 28.8],
        "eigenumfpacklu": [3.3, 7.1, 25.8],
    },
    "N=30": {
        "unit": "ms",
        "Cholmod": [35.5, 37.9, 40.3],
        "sparse": [34.4, 36.8, 39.1],
        "eigenumfpacklu": [33.8, 36.4, 38.8],
    },
    "N=3000": {
        "unit": "s",
        "Cholmod": [ 3.19, 3.4, 3.87],
        "sparse": [ 3.10, 3.226, 3.66],
        "eigenumfpacklu": [3.05, 3.22, 3.68],
    },
    "N=30000": {
        "unit": "s",
        "Cholmod": [38.01, 38.56, 38.88],
        "sparse": [35.93, 37.44, 37.90],
        "eigenumfpacklu": [35.40, 36.10, 37.30],
    },
}

SOLVERS = ["Cholmod", "sparse", "eigenumfpacklu"]
SOLVER_LABELS = ["CHOLMOD", "CSparse", "UMFPACK LU"]

# ============================================================
# ===================== STYLE CONTROL ========================
# ============================================================

FIG_W_IN = 3.45   # single-column width
FIG_H_IN = 2.5   # compact height for partial-column figure
MARKER_SIZE = 2.5
LINE_WIDTH = 1.0
CAPSIZE = 2.0
ANNOT_SIZE = 3.8

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman"],
    "text.usetex": False,   # set True if LaTeX is available
    "font.size": 7,
    "axes.titlesize": 7,
    "axes.labelsize": 7,
    "xtick.labelsize": 6,
    "ytick.labelsize": 6,
    "legend.fontsize": 6,
    "figure.dpi": 600,
})

# ============================================================
# ===================== UTILITIES ============================
# ============================================================

def mean_min_max(values):
    arr = np.asarray(values, dtype=float)
    return arr[1], np.min(arr), np.max(arr)


def fmt_value(v, unit):
    if unit == "ms":
        return f"{v:.1f}"
    return f"{v:.2f}"


# ============================================================
# ========================= MAIN =============================
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "figures" / "linear_solver_scaling")
    args = ap.parse_args()
    
    out_path = args.out.with_suffix(".pdf")

    fig, axes = plt.subplots(
        2, 2,
        figsize=(FIG_W_IN, FIG_H_IN),
        constrained_layout=True
    )
    axes = axes.ravel()

    horizons = list(raw_data.keys())

    for ax, horizon in zip(axes, horizons):
        unit = raw_data[horizon]["unit"]
        x = np.arange(len(SOLVERS))

        for i, solver in enumerate(SOLVERS):
            mean_v, min_v, max_v = mean_min_max(raw_data[horizon][solver])
            yerr = np.array([[mean_v - min_v], [max_v - mean_v]])

            ax.errorbar(
                i,
                mean_v,
                yerr=yerr,
                fmt="o",
                markersize=MARKER_SIZE,
                capsize=CAPSIZE,
                linewidth=LINE_WIDTH,
            )

            ax.annotate(
                fmt_value(mean_v, unit),
                xy=(i, mean_v),
                xytext=(2, 2),
                textcoords="offset points",
                ha="left",
                va="bottom",
                fontsize=ANNOT_SIZE,
            )

        ax.set_xticks(x)
        ax.set_xticklabels(SOLVER_LABELS, rotation=18)
        ax.set_title(f"{horizon} [{unit}]")
        ax.set_ylabel(f"Time [{unit}]")

        ax.grid(True, axis="y", alpha=0.3, linewidth=0.6)
        ax.grid(True, axis="x", alpha=0.15, linewidth=0.4)

    fig.savefig(out_path, format="pdf", bbox_inches="tight")
    print(f"Saved to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
