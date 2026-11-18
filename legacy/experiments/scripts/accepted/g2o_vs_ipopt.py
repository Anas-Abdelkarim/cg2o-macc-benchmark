import os
from pathlib import Path
import re
import argparse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator
from data_saver.data_loader import DataLoader

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

colors_code = [ "#1eff00","#fa000095"]
color_host = "#0000ffff"
color_preceding = "#fa00faff"
color_difference = "#0000ffff"

# ============================================================
# ================== MATPLOTLIB SETTINGS =====================
# ============================================================

 

plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman'],
    'text.usetex': True,        # Set to False if LaTeX is not installed
    'font.size': 9.5,
    'axes.titlesize': 7.5,
    'axes.labelsize': 7.5,
    'xtick.labelsize': 7.5,
    'ytick.labelsize': 7.5,
    'legend.fontsize': 6.5,
    'figure.dpi': 600,
})

# ============================================================
# ===================== UTILITIES ============================
# ============================================================

def safe_get(results, key, default):
    return results.get(key, default)

def extract_horizon_from_filename(path: str):
    m = re.search(r"_(\d+)\.bin$", os.path.basename(path))
    return int(m.group(1)) if m else None

def load_signals_from_bin(bin_path: str) -> dict:
    with DataLoader(bin_path) as loader:
        results = loader.load_all()

    def arr(name):
        return np.array(safe_get(results, name, []), dtype=float)

    out = {
        "v_h": arr("v_h_signal"),
        "v_p": arr("v_p_signal"),
        "d_h": arr("d_h_signal"),
        "u":   arr("u_input_signal"),
        "iters": arr("num_iterations_signal"),
        "t_ms":  arr("cal_time_signal"),
        "cost":  arr("cost_level_signal"),
        "iters_lang": arr("num_iterations_signal_lang"),
        "t_ms_lang":  arr("cal_time_signal_lang"),
        "cost_lang":  arr("cost_level_signal_lang"),
    }

    if out["t_ms"].size > 0:
        mask = out["t_ms"] > 0
        L = np.sum(mask)
        for k in out:
            if out[k].size >= L:
                out[k] = out[k][:L]

    return out

def stack_mean(runs, key):
    series = [r[key] for r in runs if r[key].size > 0]
    if not series:
        return np.array([])
    L = min(s.size for s in series)
    if L == 0:
        return np.array([])
    M = np.vstack([s[:L] for s in series])
    return np.nanmean(M, axis=0)

def median(arr):
    arr = np.array(arr)
    n = len(arr)
    if n == 0:
        return np.nan
    arr_sorted = np.sort(arr)
    mid = n // 2
    if n % 2 == 0:
        return 0.5 * (arr_sorted[mid - 1] + arr_sorted[mid])
    else:
        return arr_sorted[mid]

def mean_without_outliers(data):
    data = np.array(data)
    if data.size == 0:
        return np.nan
    sorted_data = np.sort(data)
    n = len(sorted_data)
    half = n // 2
    if n % 2 == 0:
        Q1 = median(sorted_data[:half])
        Q3 = median(sorted_data[half:])
    else:
        Q1 = median(sorted_data[:half])
        Q3 = median(sorted_data[half+1:])
    IQR = Q3 - Q1
    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR
    filtered = sorted_data[(sorted_data >= lower) & (sorted_data <= upper)]
    if filtered.size == 0:
        return np.nan
    return np.mean(filtered)

def stack_mean_no_outliers(runs, key):
    series = [r[key] for r in runs if r[key].size > 0]
    if not series:
        return np.array([])
    L = min(s.size for s in series)
    if L == 0:
        return np.array([])
    M = np.vstack([s[:L] for s in series])
    mean_clean = np.array([mean_without_outliers(M[:, i]) for i in range(L)])
    return mean_clean

def apply_dense_grid(ax):
    ax.minorticks_on()
    ax.xaxis.set_minor_locator(AutoMinorLocator(X_MINOR_DENSITY))
    ax.yaxis.set_minor_locator(AutoMinorLocator(Y_MINOR_DENSITY))
    ax.grid(True, which='major', linewidth=GRID_MAJOR_LW, alpha=GRID_MAJOR_ALPHA)
    ax.grid(True, which='minor', linewidth=GRID_MINOR_LW, alpha=GRID_MINOR_ALPHA)


# ============================================================
# ========================= MAIN =============================
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path,
                    default=Path(__file__).resolve().parent / "data" / "g2o_vs_ipopt")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "figures" / "g2o_vs_ipopt")
    args = ap.parse_args()

    data_dir = args.dir.expanduser().resolve()
    all_bins = sorted(data_dir.glob("*.bin"))
    if not all_bins:
        raise FileNotFoundError(f"No .bin files in {data_dir}")

    grouped_paths = {N: [] for N in HORIZONS}

    for p in all_bins:
        N = extract_horizon_from_filename(p)
        if N in grouped_paths:
            grouped_paths[N].append(p)

    for N in HORIZONS:
        if not grouped_paths[N]:
            raise FileNotFoundError(f"No files for horizon N={N}")

    runs = {N: [load_signals_from_bin(p) for p in grouped_paths[N]] for N in HORIZONS}

    # --- Compute averages, cost_diff, and cost_min for all horizons ---
    avg = {}
    for N in HORIZONS:
        avg[N] = {
            "v_h": stack_mean(runs[N], "v_h"),
            "v_p": stack_mean(runs[N], "v_p"),
            "d_h": stack_mean(runs[N], "d_h"),
            "u":   stack_mean(runs[N], "u"),
            "iters": stack_mean(runs[N], "iters"),
            "t_ms":  stack_mean_no_outliers(runs[N], "t_ms"),
            "cost":  stack_mean(runs[N], "cost"),
            "iters_lang": stack_mean(runs[N], "iters_lang"),
            "t_ms_lang":  stack_mean_no_outliers(runs[N], "t_ms_lang"),
            "cost_lang":  stack_mean(runs[N], "cost_lang"),
        }

        if avg[N]["cost"].size and avg[N]["cost_lang"].size:
            L = min(len(avg[N]["cost"]), len(avg[N]["cost_lang"]))
            cost = avg[N]["cost"][:L]
            cost_lang = avg[N]["cost_lang"][:L]
            avg[N]["cost_diff"] = cost - cost_lang
            avg[N]["cost_min"] = (cost < cost_lang).astype(int)
        else:
            avg[N]["cost_diff"] = np.array([])
            avg[N]["cost_min"] = np.array([])

    # --- Plot ---
    fig, axes = plt.subplots(5, 3, figsize=(FIG_W_IN, FIG_H_IN))
    fig, axes = plt.subplots(5, 3, figsize=(FIG_W_IN, FIG_H_IN), constrained_layout=True)
    Ns = HORIZONS

    # Row 1: N=30 reference
    Nref = 30
    axes[0, 0].plot(avg[Nref]["v_p"], 'r', color=color_preceding, linewidth=LINE_WIDTH)
    axes[0, 0].plot(avg[Nref]["v_h"], color=color_host, linewidth=LINE_WIDTH)
    axes[0, 0].set_ylabel("Velocity [m/s]")
    axes[0, 0].legend(
        [r"$v_p$", r"$v_h$"],
        loc="upper left",          # anchor point of legend
        bbox_to_anchor=(-.028, 1.1),  # x=0, y=1.05 → slightly above the top
        frameon=False,
        ncol=2
    )
    apply_dense_grid(axes[0, 0])

    axes[0, 1].plot(avg[Nref]["d_h"], color=color_host, linewidth=LINE_WIDTH)
    axes[0, 1].legend([r"$d_h$ [m]"],
                      loc="upper left", 
                      bbox_to_anchor=(-.02, 1.1),  # x=0, y=1.05 → slightly above the top
                      frameon=False)
    apply_dense_grid(axes[0, 1])

    axes[0, 2].plot(avg[Nref]["u"] / 1000,color=color_host, linewidth=LINE_WIDTH)
    axes[0, 2].legend([r"$Force [kN]$"],
                      loc="upper right",
                      bbox_to_anchor=(.95, 1.08),  # x=0, y=1.05 → slightly above the top
                      frameon=False)
    apply_dense_grid(axes[0, 2])

    # Rows 2–4: Proposed vs IPOPT
    for j, N in enumerate(Ns):
        # Iterations
        iters_mean = np.nanmean(avg[N]["iters"]) if avg[N]["iters"].size > 0 else np.nan
        iters_lang_mean = np.nanmean(avg[N]["iters_lang"]) if avg[N]["iters_lang"].size > 0 else np.nan
        axes[1, j].plot(avg[N]["iters"], colors_code[0], linewidth=LINE_WIDTH)
        axes[1, j].axhline(
            y=iters_mean,
            color=colors_code[0], 
            linestyle='--',
            label="_nolegend_",
            linewidth=LINE_WIDTH
        )
        axes[1, j].plot(avg[N]["iters_lang"],colors_code[1], linewidth=LINE_WIDTH)
        axes[1, j].axhline(
            y=iters_lang_mean,
            color=colors_code[1], linestyle='--', linewidth=LINE_WIDTH
        )
        
        print(f"Horizon N={N}: iters mean = {iters_mean:.1f}, iters_lang mean = {iters_lang_mean:.1f}")
        iters_max = np.nanmax(avg[N]["iters"]) if avg[N]["iters"].size > 0 else np.nan
        iters_lang_max = np.nanmax(avg[N]["iters_lang"]) if avg[N]["iters_lang"].size > 0 else np.nan
        print(f"Horizon N={N}: iters max = {iters_max:.1f}, iters_lang max = {iters_lang_max:.1f}")
       
        axes[1, j].text(0.45, 1.20, f"N={N}", transform=axes[1, j].transAxes, verticalalignment='top')
        if j == 0:
            axes[1, j].set_ylabel("Iterations")
        apply_dense_grid(axes[1, j])
    
        if j==1:
            axes[1, j].legend([r"Our", r"IPOPT"],
                                loc="upper left",          # anchor point of legend
                                bbox_to_anchor=(0.08, 1.1),  # x=0, y=1.05 → slightly above the top
                                frameon=False,
                                ncol=2
                                )


        # Time
        t_mean = np.nanmean(avg[N]["t_ms"]) if avg[N]["t_ms"].size > 0 else np.nan
        t_lang_mean = np.nanmean(avg[N]["t_ms_lang"]) if avg[N]["t_ms_lang"].size > 0 else np.nan
        axes[2, j].plot(avg[N]["t_ms"], colors_code[0], linewidth=LINE_WIDTH)
        axes[2, j].axhline(y=t_mean,
                           color=colors_code[0],
                           linestyle='--', 
                           label="_nolegend_",
                           linewidth=LINE_WIDTH)
        axes[2, j].plot(avg[N]["t_ms_lang"], colors_code[1], linewidth=LINE_WIDTH)
        axes[2, j].axhline(y=t_lang_mean,
                           color=colors_code[1], linestyle='--', linewidth=LINE_WIDTH)
        
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
        if j==0:
            axes[2, j].legend(["Our", "IPOPT"],
                                loc="upper left",          # anchor point of legend
                                bbox_to_anchor=(.03, 1.05 ),  # x=0, y=1.05 → slightly above the top
                                frameon=False,
                                ncol=2
                                )

        # Cost
        axes[3, j].plot(avg[N]["cost"] / 1e6, colors_code[0],
                        linewidth=LINE_WIDTH)
        axes[3, j].plot(avg[N]["cost_lang"] / 1e6, colors_code[1],  
                             linestyle='None',
                        marker='o',
                        markerfacecolor='none',
                        markeredgewidth=0.2,
                        markersize=4,
                        markevery=20,                   
                        linewidth=LINE_WIDTH)
        if j == 2:
            axes[3, j].legend([r"Our", r"IPOPT"],
                                loc="upper left",          # anchor point of legend
                                bbox_to_anchor=(-.02, 1.07),  # x=0, y=1.05 → slightly above the top
                                frameon=False,
                                ncol=2
                                )
        if j == 0:
            axes[3, j].set_ylabel(r"Cost [$\times 10^6$]")
        apply_dense_grid(axes[3, j])

        # Cost min binary
        axes[4, j].plot(avg[N]["cost_min"], color=color_difference, linewidth=LINE_WIDTH)
        # always the ranges between 0 and 1, so no need to plot dashed lines
        axes[4, j].set_ylim(-0.1, 1.1)
        if j == 0: 
            axes[4, j].set_ylabel(r"Cost Better")
        axes[4, j].set_xlabel("Step")
        apply_dense_grid(axes[4, j])
        if j==1:
            axes[4, j].legend(
                [r"1: Our $<$ IPOPT"],
                frameon=False,
                bbox_to_anchor=(.4,0 ),  # x=0, y=1.05 → slightly above the top
                loc="lower center"
            )

    # Remove X labels except last row
    for i in range(4):
        for j in range(3):
            axes[i, j].set_xticklabels([])

    # Save figure
    out_pdf = args.out.with_suffix(".pdf")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    print("Saving to:", out_pdf.resolve())
  #  fig.subplots_adjust(
 #   left=0.10,    # left margin
  #  right=0.985,  # right margin
   # top=0.95,     # top margin
    #bottom=0.07,  # bottom margin
   # hspace=0.15,  # vertical space between rows
    #wspace=0.17   # horizontal space between columns
    #)

    fig.savefig(out_pdf, format="pdf", bbox_inches="tight")


if __name__ == "__main__":
    main()