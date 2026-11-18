#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

# ============================================================
# ===================== STYLE CONTROL ========================
# ============================================================

FIG_W_IN_SINGLE_COL = 3.45
FIG_H_IN_PER_VERTICAL = 1.75
FIG_H_IN_HORIZONTAL = 1.65
LINE_WIDTH = 1.15

GRID_MAJOR_LW = 0.8
GRID_MINOR_LW = 0.4
GRID_MAJOR_ALPHA = 0.5
GRID_MINOR_ALPHA = 0.2
X_MINOR_DENSITY = 4
Y_MINOR_DENSITY = 4

color_host = "#0000ffff"
color_preceding = "#fa00faff"

# ============================================================
# ================== MATPLOTLIB SETTINGS =====================
# ============================================================

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman"],
    "text.usetex": True,   # Set to False if LaTeX is not installed
    "font.size": 11.5,
    "axes.titlesize": 11.5,
    "axes.labelsize": 11.5,
    "xtick.labelsize": 11.5,
    "ytick.labelsize": 11.5,
    "legend.fontsize": 11.5,
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


def read_csv(path: Path) -> dict:
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


def extract_horizon_from_name(name: str):
    stem = Path(name).stem
    m = re.search(r"_(\d+)$", stem)
    return int(m.group(1)) if m else None


def prepare_axes(nplots: int, layout: str):
    if layout == "vertical":
        fig_w = FIG_W_IN_SINGLE_COL
        fig_h = FIG_H_IN_PER_VERTICAL * nplots
        fig, axes = plt.subplots(
            nplots, 1,
            figsize=(fig_w, fig_h),
            constrained_layout=True
        )
        if nplots == 1:
            axes = [axes]
        return fig, list(axes)

    fig_w = FIG_W_IN_SINGLE_COL * nplots
    fig_h = FIG_H_IN_HORIZONTAL
    fig, axes = plt.subplots(
        1, nplots,
        figsize=(fig_w, fig_h),
        constrained_layout=True
    )
    if nplots == 1:
        axes = [axes]
    return fig, list(axes)


# ============================================================
# ========================= MAIN =============================
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Plot v_p and v_h signals from selected CSV files."
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "established" / "closed_loop_failed",
        help="Directory containing the CSV files",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        required=True,
        help="CSV file basenames without .csv extension",
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        required=True,
        help="Labels for each file, same order as --files",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "figures" / "closed_loop_failed",
    )
    parser.add_argument(
        "--layout",
        choices=["vertical", "horizontal"],
        default="vertical",
        help="vertical -> N x 1, horizontal -> 1 x N",
    )
    args = parser.parse_args()

    if len(args.files) != len(args.labels):
        raise ValueError("--files and --labels must have the same length")

    data_dir = args.dir.expanduser().resolve()
    if not data_dir.is_dir():
        raise NotADirectoryError(f"Not a valid directory: {data_dir}")

    nplots = len(args.files)
    fig, axes = prepare_axes(nplots, args.layout)

    for i, (ax, file_base, label) in enumerate(zip(axes, args.files, args.labels)):
        csv_path = data_dir / f"{file_base}.csv"
        data = read_csv(csv_path)

        if "v_h_signal" not in data or "v_p_signal" not in data:
            raise KeyError(
                f"{csv_path.name} must contain 'v_h_signal' and 'v_p_signal' columns"
            )

        v_h = np.asarray(data["v_h_signal"], dtype=float)
        v_p = np.asarray(data["v_p_signal"], dtype=float)

        mask = ~(np.isnan(v_h) | np.isnan(v_p))
        v_h = v_h[mask]
        v_p = v_p[mask]

        L = min(len(v_h), len(v_p))
        v_h = v_h[:L]
        v_p = v_p[:L]

        N = extract_horizon_from_name(file_base)
        title_str = f"{label}, N={N}" if N is not None else label

        if L == 0:
            print(f"[WARN] No valid data in {csv_path.name}")
            ax.text(
                0.03, 0.95, title_str,
                transform=ax.transAxes,
                va="top", ha="left"
            )
            ax.set_ylabel("Velocity [m/s]")
            if args.layout == "vertical":
                if i == nplots - 1:
                    ax.set_xlabel("Step")
                else:
                    ax.tick_params(axis="x", labelbottom=False)
            else:
                ax.set_xlabel("Step")
                if i != 0:
                    ax.tick_params(axis="y", labelleft=False)
            apply_dense_grid(ax)
            continue

        ax.plot(v_p, color=color_preceding, linewidth=LINE_WIDTH, label=r"$v_p$")
        ax.plot(v_h, color=color_host, linewidth=LINE_WIDTH, label=r"$v_h$")

        ax.text(
            .02, 0.98, title_str,
            transform=ax.transAxes,
            va="top", ha="left"
        )

        if args.layout == "vertical":
            ax.set_ylabel("Velocity [m/s]")
            if i == nplots - 1:
                ax.set_xlabel("Step")
            else:
                ax.tick_params(axis="x", labelbottom=False)
        else:
            ax.set_xlabel("Step")
            if i == 0:
                ax.set_ylabel("Velocity [m/s]")
            if i == 1:
               ax.tick_params(axis="y", labelleft=False)
            else:
               pass #  ax.tick_params(axis="y", labelleft=False)
        if i == 2 :
                ax.legend(
                loc="center",
                bbox_to_anchor=(.67, .9),
                frameon=False,
                ncol=2,
                columnspacing=0.7
            )
        apply_dense_grid(ax)

        print(f"[OK] Plotted {csv_path.name} | label={label} | N={N}")

    out_pdf = args.out.with_suffix(".pdf")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    print(f"Saving to: {out_pdf.resolve()}")
    fig.savefig(out_pdf, format="pdf", bbox_inches="tight")


if __name__ == "__main__":
    main()