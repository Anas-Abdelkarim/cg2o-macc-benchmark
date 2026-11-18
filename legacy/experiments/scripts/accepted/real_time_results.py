#!/usr/bin/env python3
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

# ============================================================
# ===================== STYLE CONTROL ========================
# ============================================================

FIG_W_IN = 7.1
FIG_H_IN = 3.7
LINE_WIDTH = 1.15

# ----- GRID CONTROL -----
GRID_MAJOR_LW = 0.8
GRID_MINOR_LW = 0.4
GRID_MAJOR_ALPHA = 0.5
GRID_MINOR_ALPHA = 0.2
X_MINOR_DENSITY = 4
Y_MINOR_DENSITY = 4

# ----- COLORS (close to first script style) -----
COLOR_HOST = "#0000ffff"
COLOR_PRECEDING = "#fa00faff"
COLOR_MAIN = "#2d8b3d"
COLOR_COMPARE = "#fa0000e2"
COLOR_FORCE = "#086b6b"
COLOR_MEAN = "#ff0f0f67"
COLOR_ITERATION = "#310b99"

# ============================================================
# ================== MATPLOTLIB SETTINGS =====================
# ============================================================

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman"],
    "text.usetex": True,   # Set False if needed
    "font.size": 7,
    "axes.titlesize": 7,
    "axes.labelsize": 6.5,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 6,
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


def extract_zip(zip_path: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dst_dir)


def find_csvs(folder: Path) -> dict:
    csvs = {}
    for p in folder.rglob("*.csv"):
        csvs[p.stem] = p
    return csvs


def load_case_series_auto(
    csv_path: Path,
    preferred_y: Optional[str] = None,
    n_cases: int = 3
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Load (t, y) for each case from a CSV.

    Expected column pattern:
      time_s, time_s.1, time_s.2
      y,     y.1,      y.2
    """
    df = pd.read_csv(csv_path)

    if preferred_y and preferred_y in df.columns:
        base = preferred_y
    elif "data" in df.columns:
        base = "data"
    else:
        candidates = [c for c in df.columns if not c.startswith("time_s")]
        if not candidates:
            raise ValueError(
                f"Could not find a y-column in {csv_path.name}. "
                f"Columns: {list(df.columns)}"
            )
        base = candidates[0]

    cases: List[Tuple[np.ndarray, np.ndarray]] = []
    for i in range(n_cases):
        tcol = "time_s" if i == 0 else f"time_s.{i}"
        ycol = base if i == 0 else f"{base}.{i}"

        if tcol not in df.columns or ycol not in df.columns:
            raise ValueError(
                f"Missing columns in {csv_path.name}: "
                f"need '{tcol}' and '{ycol}'. "
                f"Columns: {list(df.columns)}"
            )

        t = pd.to_numeric(df[tcol], errors="coerce").to_numpy()
        y = pd.to_numeric(df[ycol], errors="coerce").to_numpy()

        m = np.isfinite(t) & np.isfinite(y)
        t, y = t[m], y[m]

        if t.size and np.any(np.diff(t) < 0):
            idx = np.argsort(t)
            t, y = t[idx], y[idx]

        cases.append((t, y))

    return cases


def hide_top_row_xticklabels(axes):
    for j in range(3):
        for i in range(4):
            axes[i, j].set_xticklabels([])


# ============================================================
# ========================= PLOTTING =========================
# ============================================================

def plot_5x3(
    csvs: dict,
    out_pdf: Path,
    case_labels: List[str],
    auto_s_to_ms: bool = True,
) -> None:
    # Load signals
    vh_cases = load_case_series_auto(csvs["v_h"], preferred_y="v_h")
    vp_cases = load_case_series_auto(csvs["v_p"], preferred_y="v_p")
    dh_cases = load_case_series_auto(csvs["d_h"], preferred_y="d_h")
    u_cases = load_case_series_auto(csvs["input_force"])
    it_cases = load_case_series_auto(csvs["num_iterations"])
    st_cases = load_case_series_auto(csvs["solve_time"])

    # Convert force N -> kN
    u_cases = [(t, y / 1000.0) for (t, y) in u_cases]

    # Convert solve time to ms if data seems to be in seconds
    if auto_s_to_ms:
        converted = []
        for (t, y) in st_cases:
            y2 = y * 1000.0 if np.nanmedian(y) < 1.0 else y
            converted.append((t, y2))
        st_cases = converted

    # Use same layout philosophy as first script
    fig, axes = plt.subplots(
        5, 3,
        figsize=(FIG_W_IN, FIG_H_IN),
        constrained_layout=True
    )

    # ========================================================
    # Row 1: Velocity
    # ========================================================
    for j in range(3):
        t_vh, y_vh = vh_cases[j]
        t_vp, y_vp = vp_cases[j]

        axes[0, j].plot(t_vp, y_vp, color=COLOR_PRECEDING, linewidth=LINE_WIDTH)
        axes[0, j].plot(t_vh, y_vh, color=COLOR_HOST, linewidth=LINE_WIDTH)

        axes[0, j].text(
            0.45, 1.20, case_labels[j],
            transform=axes[0, j].transAxes,
            verticalalignment="top"
        )

        if j == 0:
            axes[0, j].set_ylabel("Velocity [m/s]")

        apply_dense_grid(axes[0, j])

    axes[0, 0].legend(
        [r"$v_p$", r"$v_h$"],
        loc="upper left",
        bbox_to_anchor=(.4, 1.13),
        frameon=False,
        ncol=2,
        columnspacing=0.6,
        handletextpad=0.3,
    )

    # ========================================================
    # Row 2: Distance
    # ========================================================
    for j in range(3):
        t, y = dh_cases[j]
        axes[1, j].plot(t, y, color=COLOR_HOST, linewidth=LINE_WIDTH)

        if j == 0:
            axes[1, j].set_ylabel("Distance [m]")

        apply_dense_grid(axes[1, j])

    axes[1, 0].legend(
        [r"$d_h$"],
        loc="upper left",
        bbox_to_anchor=(-0.02, 1.10),
        frameon=False
    )

    # ========================================================
    # Row 3: Input Force
    # ========================================================
    for j in range(3):
        t, y = u_cases[j]
        axes[2, j].plot(t, y, color=COLOR_FORCE, linewidth=LINE_WIDTH)

        if j == 0:
            axes[2, j].set_ylabel("Force [kN]")

        apply_dense_grid(axes[2, j])

    axes[2, 0].legend(
        [r"$u$"],
        loc="upper left",
        bbox_to_anchor=(-0.02, 1.10),
        frameon=False
    )

    # ========================================================
    # Row 4: Iterations
    # ========================================================
    for j in range(3):
        t, y = it_cases[j]
        y_mean = np.nanmean(y) if y.size > 0 else np.nan

        axes[3, j].plot(t, y, color=COLOR_ITERATION, linewidth=LINE_WIDTH)
        axes[3, j].axhline(
            y=y_mean,
            color=COLOR_COMPARE,
            linestyle="--",
            linewidth=LINE_WIDTH
        )

        if j == 0:
            axes[3, j].set_ylabel("Iterations")

        apply_dense_grid(axes[3, j])

    axes[3, 0].legend(
        [r"Signal", r"Mean"],
        loc="upper left",
        bbox_to_anchor=(0.475, 1.10),
        frameon=False,
        ncol=2,
        columnspacing=0.6,
        handletextpad=0.3,
    )

    # ========================================================
    # Row 5: Solve Time
    # ========================================================
    for j in range(3):
        t, y = st_cases[j]
        y_mean = np.nanmean(y) if y.size > 0 else np.nan

        axes[4, j].plot(t, y, color=COLOR_MAIN, linewidth=LINE_WIDTH)
        axes[4, j].axhline(
            y=y_mean,
            color=COLOR_COMPARE,
            linestyle="--",
            linewidth=LINE_WIDTH
        )

        if j == 0:
            axes[4, j].set_ylabel("Time [ms]")

        axes[4, j].set_xlabel("Time [s]")
        apply_dense_grid(axes[4, j])

    axes[4, 2].legend(
        [r"Signal", r"Mean"],
        loc="upper left",
        bbox_to_anchor=(0.475, 1.05),
        frameon=False,
        ncol=2,
        columnspacing=0.6,
        handletextpad=0.3,
    )

    # Remove x labels except bottom row
    hide_top_row_xticklabels(axes)

    # Save
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    print("Saving to:", out_pdf.resolve())
    fig.savefig(
        out_pdf,
        format="pdf",
        bbox_inches="tight",
        pad_inches=0.01
    )
    plt.close(fig)


# ============================================================
# =========================== MAIN ===========================
# ============================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="Plot real-time ACC results in 5x3 paper style.")
    ap.add_argument(
        "--zip",
        type=Path,
        default=Path("./data/signals_real_time.zip"),
        help="Path to signals zip."
    )
    ap.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Directory containing CSV files (optional)."
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("./figures/real_time_results"),
        help="Output base name without extension."
    )
    ap.add_argument(
        "--case-labels",
        nargs=3,
        default=["Case 1", "Case 2", "Case 3"],
        help="Labels for the three columns."
    )
    args = ap.parse_args()

    if args.dir is not None:
        src_dir = args.dir
    else:
        if not args.zip.exists():
            raise SystemExit(f"Zip not found: {args.zip}")

        extract_dir = args.zip.parent / args.zip.stem
        extract_zip(args.zip, extract_dir)
        src_dir = extract_dir

    csvs = find_csvs(src_dir)

    required = ["v_h", "v_p", "d_h", "input_force", "num_iterations", "solve_time"]
    missing = [k for k in required if k not in csvs]
    if missing:
        raise SystemExit(f"Missing required CSVs: {missing}. Found: {sorted(csvs.keys())}")

    out_pdf = Path(f"{args.out}.pdf")
    plot_5x3(csvs, out_pdf, list(args.case_labels))
    print(f"Wrote: {out_pdf}")


if __name__ == "__main__":
    main()