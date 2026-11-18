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
FIG_H_IN = 4.0
LINE_WIDTH = 1.15

# ----- GRID CONTROL -----
GRID_MAJOR_LW = 0.8
GRID_MINOR_LW = 0.4
GRID_MAJOR_ALPHA = 0.5
GRID_MINOR_ALPHA = 0.2
X_MINOR_DENSITY = 4
Y_MINOR_DENSITY = 4

# Horizons
HORIZONS = [3, 15, 30]

# Keep exactly the same color style as your IPOPT plot
colors_code = ["#1eff00", "#fa000095"]
colors_code1 = ["#ffdc18", "#fa000067"]
color_host = "#0000ffff"
color_preceding = "#fa00faff"
color_difference = "#0000ffff"

# ============================================================
# ================== MATPLOTLIB SETTINGS =====================
# ============================================================

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman"],
    "text.usetex": True,        # Set to False if LaTeX is not installed
    "font.size": 9.5,
    "axes.titlesize": 7.5,
    "axes.labelsize": 7.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 6.5,
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

# ============================================================
# ========================= MAIN =============================
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "ispd_vs_bipm"
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "figures" / "g2o_vs_bipm"
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Plot full 5-row figure. Default: only iterations and time rows."
    )
    args = ap.parse_args()

    data_dir = args.dir.expanduser().resolve()

    avg = {}
    for N in HORIZONS:
        csv_path_ispd = data_dir / f"ISPD_{N}.csv"
        csv_path_bipm = data_dir / f"BIPM_{N}.csv"

        avg[N] = {}
        avg_ispd = read_avg_csv(csv_path_ispd)
        avg_bipm = read_avg_csv(csv_path_bipm)

        # Keep naming style identical to your IPOPT plot script:
        # plain signal = cg2o / ISPD
        # *_lang = Barrier-IPM
        avg[N]["v_h"] = avg_ispd["v_h"]
        avg[N]["v_p"] = avg_ispd["v_p"]
        avg[N]["d_h"] = avg_ispd["d_h"]
        avg[N]["u"] = avg_ispd["u"]
        avg[N]["iters"] = avg_ispd["iters"]
        avg[N]["t_ms"] = avg_ispd["t_ms"]
        avg[N]["cost"] = avg_ispd["cost"]

        avg[N]["u_lang"] = avg_bipm["u"]
        avg[N]["iters_lang"] = avg_bipm["iters"]
        avg[N]["t_ms_lang"] = avg_bipm["t_ms"]
        avg[N]["cost_lang"] = avg_bipm["cost"]

        # recreate cost_diff and cost_min exactly like the IPOPT script
        if avg[N]["cost"].size and avg[N]["cost_lang"].size:
            L = min(len(avg[N]["cost"]), len(avg[N]["cost_lang"]))
            cost = avg[N]["cost"][:L]
            cost_lang = avg[N]["cost_lang"][:L]
            avg[N]["cost_diff"] = cost - cost_lang
            avg[N]["cost_min"] = (cost < cost_lang).astype(int)
        else:
            avg[N]["cost_diff"] = np.array([])
            avg[N]["cost_min"] = np.array([])

    # ========================================================
    # ======================== PLOT ===========================
    # ========================================================

    if args.all:
        fig, axes = plt.subplots(5, 3, figsize=(FIG_W_IN, FIG_H_IN), constrained_layout=True)
        Ns = HORIZONS

        # Row 1: N=30 reference
        Nref = 30
        axes[0, 0].plot(avg[Nref]["v_p"], "r", color=color_preceding, linewidth=LINE_WIDTH)
        axes[0, 0].plot(avg[Nref]["v_h"], color=color_host, linewidth=LINE_WIDTH)
        axes[0, 0].set_ylabel("Velocity [m/s]")
        axes[0, 0].legend(
            [r"$v_p$", r"$v_h$"],
            loc="upper left",
            bbox_to_anchor=(-.032, 1.13),
            frameon=False,
            ncol=2
        )
        apply_dense_grid(axes[0, 0])

        axes[0, 1].plot(avg[Nref]["d_h"], color=color_host, linewidth=LINE_WIDTH)
        axes[0, 1].legend(
            [r"$d_h$ [m]"],
            loc="upper left",
            bbox_to_anchor=(-.02, 1.1),
            frameon=False
        )
        apply_dense_grid(axes[0, 1])

        axes[0, 2].plot(avg[Nref]["u"] / 1000, color=color_host, linewidth=LINE_WIDTH)
        axes[0, 2].plot(avg[Nref]["u_lang"] / 1000, color=colors_code1[1],
                         linewidth=LINE_WIDTH)
        axes[0, 2].text(1750,3.5, "$Force [kN]$", verticalalignment='baseline')

        axes[0, 2].legend(
            [r"cg2o", r"Barrier-IPM"],
            loc="lower left",
            bbox_to_anchor=(0.05,-.12),
            ncol=2,
            frameon=False)
        apply_dense_grid(axes[0, 2])

        # Rows 2–5
        for j, N in enumerate(Ns):
            # Iterations
            iters_mean = np.nanmean(avg[N]["iters"]) if avg[N]["iters"].size > 0 else np.nan
            iters_lang_mean = np.nanmean(avg[N]["iters_lang"]) if avg[N]["iters_lang"].size > 0 else np.nan

            axes[1, j].plot(avg[N]["iters"], colors_code[0], linewidth=LINE_WIDTH)
            axes[1, j].axhline(
                y=iters_mean,
                color=colors_code[0],
                linestyle="--",
                label="_nolegend_",
                linewidth=LINE_WIDTH
            )
            axes[1, j].plot(avg[N]["iters_lang"], colors_code[1], linewidth=LINE_WIDTH)
            axes[1, j].axhline(
                y=iters_lang_mean,
                color=colors_code[1],
                linestyle="--",
                linewidth=LINE_WIDTH
            )

            print(f"Horizon N={N}: iters mean = {iters_mean:.1f}, iters_lang mean = {iters_lang_mean:.1f}")
            iters_max = np.nanmax(avg[N]["iters"]) if avg[N]["iters"].size > 0 else np.nan
            iters_lang_max = np.nanmax(avg[N]["iters_lang"]) if avg[N]["iters_lang"].size > 0 else np.nan
            print(f"Horizon N={N}: iters max = {iters_max:.1f}, iters_lang max = {iters_lang_max:.1f}")

            axes[1, j].text(0.45, 1.20, f"N={N}", transform=axes[1, j].transAxes, verticalalignment="top")
            if j == 0:
                axes[1, j].set_ylabel("Iterations")
            apply_dense_grid(axes[1, j])

            if j == 0:
                axes[1, j].legend(
                    [r"cg2o", r"Barrier-IPM"],
                    loc="upper left",
                    bbox_to_anchor=(0.08, 1.1),
                    frameon=False,
                    ncol=2
                )

            # Time
            t_mean = np.nanmean(avg[N]["t_ms"]) if avg[N]["t_ms"].size > 0 else np.nan
            t_lang_mean = np.nanmean(avg[N]["t_ms_lang"]) if avg[N]["t_ms_lang"].size > 0 else np.nan

            axes[2, j].plot(avg[N]["t_ms"], colors_code[0], linewidth=LINE_WIDTH)
            axes[2, j].axhline(
                y=t_mean,
                color=colors_code[0],
                linestyle="--",
                label="_nolegend_",
                linewidth=LINE_WIDTH
            )
            axes[2, j].plot(avg[N]["t_ms_lang"], colors_code[1], linewidth=LINE_WIDTH)
            axes[2, j].axhline(
                y=t_lang_mean,
                color=colors_code[1],
                linestyle="--",
                linewidth=LINE_WIDTH
            )

            t_final = np.nanmax(avg[N]["t_ms"]) if avg[N]["t_ms"].size > 0 else np.nan
            t_min = np.nanmin(avg[N]["t_ms"]) if avg[N]["t_ms"].size > 0 else np.nan
            t_lang_max = np.nanmax(avg[N]["t_ms_lang"]) if avg[N]["t_ms_lang"].size > 0 else np.nan
            t_lang_min = np.nanmin(avg[N]["t_ms_lang"]) if avg[N]["t_ms_lang"].size > 0 else np.nan
            print(f"Horizon N={N}: t_mean = {t_mean:.1f}, t_lang_mean = {t_lang_mean:.1f}")
            print(f"Horizon N={N}: t_final = {t_final:.1f}, t_lang_max = {t_lang_max:.1f}")
            print(f"Horizon N={N}: t_min = {t_min:.1f}, t_lang_min = {t_lang_min:.1f}")

            if j == 0:
                axes[2, j].set_ylabel("Time [ms]")
            apply_dense_grid(axes[2, j])

            if j == 0:
                axes[2, j].legend(
                    ["cg2o", "Barrier-IPM"],
                    loc="upper left",
                    bbox_to_anchor=(.03, 1.05),
                    frameon=False,
                    ncol=2
                )

            # Cost
            axes[3, j].plot(avg[N]["cost"] / 1e6, colors_code[0], linewidth=LINE_WIDTH)
            axes[3, j].plot(
                avg[N]["cost_lang"] / 1e6,
                colors_code[1],
                linestyle="None",
                marker="o",
                markerfacecolor="none",
                markeredgewidth=0.2,
                markersize=4,
                markevery=20,
                linewidth=LINE_WIDTH
            )

            if j == 2:
                axes[3, j].legend(
                    [r"cg2o", r"Barrier-IPM"],
                    loc="upper left",
                    bbox_to_anchor=(-.02, 1.07),
                    frameon=False,
                    ncol=2
                )
            if j == 0:
                axes[3, j].set_ylabel(r"Cost [$\times 10^6$]")
            apply_dense_grid(axes[3, j])

            # Cost min binary
            axes[4, j].plot(avg[N]["cost_min"], color=color_difference, linewidth=LINE_WIDTH)
            axes[4, j].set_ylim(-0.1, 1.1)
            if j == 0:
                axes[4, j].set_ylabel(r"Cost Better")
            axes[4, j].set_xlabel("Step")
            apply_dense_grid(axes[4, j])

            if j == 1:
                axes[4, j].legend(
                    [r"1: cg2o $<$ Barrier-IPM"],
                    frameon=False,
                    bbox_to_anchor=(.4, 0),
                    loc="lower center"
                )

        for i in range(4):
            for j in range(3):
                axes[i, j].set_xticklabels([])

    else:
        fig, axes = plt.subplots(2, 3, figsize=(FIG_W_IN, 1.95), constrained_layout=True)
        Ns = HORIZONS

        for j, N in enumerate(Ns):
            # Iterations
            iters_mean = np.nanmean(avg[N]["iters"]) if avg[N]["iters"].size > 0 else np.nan
            iters_lang_mean = np.nanmean(avg[N]["iters_lang"]) if avg[N]["iters_lang"].size > 0 else np.nan

            axes[0, j].plot(avg[N]["iters"], colors_code[0], linewidth=LINE_WIDTH)
            axes[0, j].axhline(
                y=iters_mean,
                color=colors_code[0],
                linestyle="--",
                label="_nolegend_",
                linewidth=LINE_WIDTH
            )
            axes[0, j].plot(avg[N]["iters_lang"], colors_code[1], linewidth=LINE_WIDTH)
            axes[0, j].axhline(
                y=iters_lang_mean,
                color=colors_code[1],
                linestyle="--",
                linewidth=LINE_WIDTH
            )

            axes[0, j].text(0.45, 1.20, f"N={N}", transform=axes[0, j].transAxes, verticalalignment="top")
            if j == 0:
                axes[0, j].set_ylabel("Iterations")
            apply_dense_grid(axes[0, j])

            if j == 0:
                axes[0, j].legend(
                    [r"cg2o", r"Barrier-IPM"],
                    loc="upper left",
                    bbox_to_anchor=(0.08, 1.1),
                    frameon=False,
                    ncol=2
                )

            # Time
            t_mean = np.nanmean(avg[N]["t_ms"]) if avg[N]["t_ms"].size > 0 else np.nan
            t_lang_mean = np.nanmean(avg[N]["t_ms_lang"]) if avg[N]["t_ms_lang"].size > 0 else np.nan

            axes[1, j].plot(avg[N]["t_ms"], colors_code[0], linewidth=LINE_WIDTH)
            axes[1, j].axhline(
                y=t_mean,
                color=colors_code[0],
                linestyle="--",
                label="_nolegend_",
                linewidth=LINE_WIDTH
            )
            axes[1, j].plot(avg[N]["t_ms_lang"], colors_code[1], linewidth=LINE_WIDTH)
            axes[1, j].axhline(
                y=t_lang_mean,
                color=colors_code[1],
                linestyle="--",
                linewidth=LINE_WIDTH
            )

            if j == 0:
                axes[1, j].set_ylabel("Time [ms]")
            axes[1, j].set_xlabel("Step")
            apply_dense_grid(axes[1, j])

            if j == 0:
                axes[1, j].legend(
                    ["cg2o", "Barrier-IPM"],
                    loc="upper left",
                    bbox_to_anchor=(.03, 1.05),
                    frameon=False,
                    ncol=2
                )

        for j in range(3):
            axes[0, j].set_xticklabels([])

    # Save figure
    out_pdf = args.out.with_suffix(".pdf")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    print("Saving to:", out_pdf.resolve())
    fig.savefig(out_pdf, format="pdf", bbox_inches="tight")

if __name__ == "__main__":
    main()
