#!/usr/bin/env python3
import argparse
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

# ============================================================
# ===================== STYLE CONTROL ========================
# ============================================================

FIG_W_IN = 7.1
FIG_H_IN = 2.0
LINE_WIDTH = 1.15

# ----- GRID CONTROL -----
GRID_MAJOR_LW = 0.8
GRID_MINOR_LW = 0.4
GRID_MAJOR_ALPHA = 0.5
GRID_MINOR_ALPHA = 0.2
X_MINOR_DENSITY = 4
Y_MINOR_DENSITY = 4

HORIZONS = [3, 15, 30]

COLOR_OUR = "#1eff00"
COLOR_KNITRO = "#fa000067"
COLOR_LOQO = "#00d4fa42"

# ============================================================
# ================== MATPLOTLIB SETTINGS =====================
# ============================================================

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman"],
    "text.usetex": True,   # set to False if LaTeX is not installed
    "font.size": 9,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7,
    "figure.dpi": 600,
})

# ============================================================
# ===================== UTILITIES ============================
# ============================================================

def apply_dense_grid(ax):
    ax.minorticks_on()
    ax.xaxis.set_minor_locator(AutoMinorLocator(X_MINOR_DENSITY))
    ax.yaxis.set_minor_locator(AutoMinorLocator(Y_MINOR_DENSITY))
    ax.grid(True, which="major", linewidth=GRID_MAJOR_LW, alpha=GRID_MAJOR_ALPHA)
    ax.grid(True, which="minor", linewidth=GRID_MINOR_LW, alpha=GRID_MINOR_ALPHA)


def read_avg_csv(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing CSV: {path}")

    with path.open("r", encoding="utf-8") as f:
        header = f.readline().strip()

    if header.startswith("#"):
        header = header[1:].strip()

    cols = [c.strip() for c in header.split(",")]

    data = np.loadtxt(path, delimiter=",", skiprows=1)
    if data.ndim == 1:
        data = data.reshape(1, -1)

    out = {}
    for i, c in enumerate(cols):
        out[c] = data[:, i]
    return out


def print_stats(label: str, data: dict, N: int):
    iters = data.get("iters", np.array([]))
    t_ms = data.get("t_ms", np.array([]))

    if iters.size == 0:
        print(f"N={N} | {label} | iters: no data")
    elif np.all(np.isnan(iters)):
        print(f"N={N} | {label} | iters: all values are NaN")
    else:
        print(
            f"N={N} | {label} | iters: "
            f"mean={np.nanmean(iters):.3f}, "
            f"max={np.nanmax(iters):.3f}, "
            f"min={np.nanmin(iters):.3f}"
        )

    if t_ms.size == 0:
        print(f"N={N} | {label} | time [ms]: no data")
    elif np.all(np.isnan(t_ms)):
        print(f"N={N} | {label} | time [ms]: all values are NaN")
    else:
        print(
            f"N={N} | {label} | time [ms]: "
            f"mean={np.nanmean(t_ms):.3f}, "
            f"max={np.nanmax(t_ms):.3f}, "
            f"min={np.nanmin(t_ms):.3f}"
        )
# ============================================================
# ========================= MAIN =============================
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "established_results",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "figures" / "established_iterations",
    )
    args = ap.parse_args()

    data_dir = args.dir.expanduser().resolve()

    our = {}
    knitro = {}
    loqo = {}

    for N in HORIZONS:
        our[N] = read_avg_csv(data_dir / f"our_N{N}.csv")
        knitro[N] = read_avg_csv(data_dir / f"knitro_N{N}.csv")
        loqo[N] = read_avg_csv(data_dir / f"loqo_N{N}.csv")

    fig, axes = plt.subplots(1, 3, figsize=(FIG_W_IN, FIG_H_IN), constrained_layout=True)

    for j, N in enumerate(HORIZONS):
        # Print stats
        print_stats("Our", our[N], N)
        print_stats("Knitro", knitro[N], N)
        print_stats("Loqo", loqo[N], N)
        print("-" * 60)

        # Means
        our_mean = np.nanmean(our[N]["iters"]) if our[N]["iters"].size > 0 else np.nan
        knitro_mean = np.nanmean(knitro[N]["iters"]) if knitro[N]["iters"].size > 0 else np.nan
        loqo_mean = np.nanmean(loqo[N]["iters"]) if loqo[N]["iters"].size > 0 else np.nan

        # Plot
        axes[j].plot(our[N]["iters"], color=COLOR_OUR, linewidth=LINE_WIDTH, label="cg2o")
        axes[j].axhline(
            y=our_mean,
            color=COLOR_OUR,
            linestyle="--",
            linewidth=LINE_WIDTH,
            label="_nolegend_",
        )

        axes[j].plot(knitro[N]["iters"], color=COLOR_KNITRO, linewidth=LINE_WIDTH, label="KNITRO")
        axes[j].axhline(
            y=knitro_mean,
            color=COLOR_KNITRO,
            linestyle="--",
            linewidth=LINE_WIDTH,
            label="_nolegend_",
        )

        axes[j].plot(loqo[N]["iters"], color=COLOR_LOQO, linewidth=LINE_WIDTH, label="LOQO")
        axes[j].axhline(
            y=loqo_mean,
            color=COLOR_LOQO,
            linestyle="--",
            linewidth=LINE_WIDTH,
            label="_nolegend_",
        )

        axes[j].text(
            0.43,
            1.08,
            f"N={N}",
            transform=axes[j].transAxes,
            verticalalignment="top",
        )

        axes[j].set_xlabel("Step")
        if j == 0:
            axes[j].set_ylabel("Iterations")

        apply_dense_grid(axes[j])

        if j == 1:
            axes[j].legend(
                loc="upper center",
                bbox_to_anchor=(0.5, 1.22),
                frameon=False,
                ncol=3,
            )

    out_pdf = args.out.with_suffix(".pdf")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    print(f"Saving to: {out_pdf.resolve()}")
    fig.savefig(out_pdf, format="pdf", bbox_inches="tight")


if __name__ == "__main__":
    main()
