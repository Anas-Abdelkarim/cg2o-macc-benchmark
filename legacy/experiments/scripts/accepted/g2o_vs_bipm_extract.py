#!/usr/bin/env python3
import os
import argparse
from pathlib import Path
import numpy as np
from data_saver.data_loader import DataLoader

# ============================================================
# ===================== DEFAULT SETTINGS =====================
# ============================================================

HORIZONS = [3, 15, 30]
SOLVERS = ["ISPD", "BIPM"]

# ============================================================
# ===================== UTILITIES ============================
# ============================================================

def safe_get(results, key, default):
    return results.get(key, default)

def median(arr):
    arr = np.array(arr, dtype=float)
    n = len(arr)
    if n == 0:
        return np.nan
    arr_sorted = np.sort(arr)
    mid = n // 2
    if n % 2 == 0:
        return 0.5 * (arr_sorted[mid - 1] + arr_sorted[mid])
    return arr_sorted[mid]

def mean_without_outliers(data):
    data = np.array(data, dtype=float)
    if data.size == 0:
        return np.nan

    sorted_data = np.sort(data)
    n = len(sorted_data)
    half = n // 2

    if n % 2 == 0:
        q1 = median(sorted_data[:half])
        q3 = median(sorted_data[half:])
    else:
        q1 = median(sorted_data[:half])
        q3 = median(sorted_data[half + 1:])

    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    filtered = sorted_data[(sorted_data >= lower) & (sorted_data <= upper)]
    if filtered.size == 0:
        return np.nan
    return np.mean(filtered)

def extract_solver_and_horizon_from_filename(path: str):
    """
    Examples:
      260416_1138_G2O_ISPD_gn_GN_14_3.bin              -> ISPD, 3
      260416_1141_G2O_ISPD_gn_GN_14_15.bin             -> ISPD, 15
      260416_1227_G2O_BIPM_gn_GN_14_3_alpha_default.bin -> BIPM, 3
    """
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    parts = stem.split("_")

    solver = None
    if "ISPD" in parts:
        solver = "ISPD"
    elif "BIPM" in parts:
        solver = "BIPM"

    horizon = None
    for token in reversed(parts):
        if token.isdigit():
            horizon = int(token)
            break

    return solver, horizon

def load_signals_from_bin(bin_path: str) -> dict:
    with DataLoader(bin_path) as loader:
        results = loader.load_all()

    def arr(name):
        return np.array(safe_get(results, name, []), dtype=float)

    out = {
        "v_h": arr("v_h_signal"),
        "v_p": arr("v_p_signal"),
        "d_h": arr("d_h_signal"),
        "u": arr("u_input_signal"),
        "iters": arr("num_iterations_signal"),
        "t_ms": arr("cal_time_signal"),
        "cost": arr("cost_level_signal"),
    }

    # Same trimming idea as your g2o_vs_ipopt_extract.py:
    # trim all signals to the number of positive timing samples
    if out["t_ms"].size > 0:
        mask = out["t_ms"] > 0
        L = int(np.sum(mask))
        if L > 0:
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


def stack_mean_no_outliers(runs, key):
    series = [r[key] for r in runs if r[key].size > 0]
    if not series:
        return np.array([])

    L = min(s.size for s in series)
    if L == 0:
        return np.array([])

    M = np.vstack([s[:L] for s in series])

    if M.shape[0] == 1:
        return M[0].copy()

    mean_clean = np.array([mean_without_outliers(M[:, i]) for i in range(L)])
    return mean_clean

def compute_avg_for_group(runs: list[dict]) -> dict:
    avg = {
        "v_h": stack_mean(runs, "v_h"),
        "v_p": stack_mean(runs, "v_p"),
        "d_h": stack_mean(runs, "d_h"),
        "u": stack_mean(runs, "u"),
        "iters": stack_mean(runs, "iters"),
        "t_ms": stack_mean_no_outliers(runs, "t_ms"),
        "cost": stack_mean(runs, "cost"),
    }

    lengths = [len(v) for v in avg.values() if isinstance(v, np.ndarray) and v.size > 0]
    Lmin = min(lengths) if lengths else 0
    if Lmin > 0:
        for k, v in avg.items():
            if isinstance(v, np.ndarray) and v.size > 0:
                avg[k] = v[:Lmin]

    return avg

def write_csv(path: Path, avg: dict):
    cols = ["step", "v_p", "v_h", "d_h", "u", "iters", "t_ms", "cost"]

    L = 0
    for k in ["v_p", "v_h", "d_h", "u", "iters", "t_ms", "cost"]:
        if isinstance(avg.get(k), np.ndarray) and avg[k].size > 0:
            L = len(avg[k])
            break

    if L == 0:
        raise RuntimeError(f"No data to write for {path.name}")

    step = np.arange(L, dtype=int)

    def col(name):
        a = avg.get(name, np.array([]))
        if not isinstance(a, np.ndarray) or a.size == 0:
            return np.full(L, np.nan, dtype=float)
        return a[:L]

    data = np.column_stack([
        step,
        col("v_p"),
        col("v_h"),
        col("d_h"),
        col("u"),
        col("iters"),
        col("t_ms"),
        col("cost"),
    ])

    header = ",".join(cols)
    np.savetxt(path, data, delimiter=",", header=header, comments="", fmt="%.18g")

# ============================================================
# ========================= MAIN =============================
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "ispd_vs_bipm",
        help="Directory containing .bin files for ISPD and BIPM runs"
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory for CSV files (default: same as --dir)"
    )
    ap.add_argument(
        "--debug",
        action="store_true",
        help="Print detected solver and horizon for each file"
    )
    args = ap.parse_args()

    data_dir = args.dir.expanduser().resolve()
    out_dir = args.out.expanduser().resolve() if args.out else data_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    all_bins = sorted(data_dir.glob("*.bin"))
    if not all_bins:
        raise FileNotFoundError(f"No .bin files found in {data_dir}")

    grouped = {(solver, N): [] for solver in SOLVERS for N in HORIZONS}

    for p in all_bins:
        solver, N = extract_solver_and_horizon_from_filename(str(p))
        if args.debug:
            print(f"{p.name} -> solver={solver}, horizon={N}")
        if solver in SOLVERS and N in HORIZONS:
            grouped[(solver, N)].append(p)

    for solver in SOLVERS:
        for N in HORIZONS:
            files = grouped[(solver, N)]
            if not files:
                print(f"[WARN] No files found for {solver}, N={N}")
                continue

            runs = [load_signals_from_bin(str(p)) for p in files]
            avg = compute_avg_for_group(runs)

            out_csv = out_dir / f"{solver}_{N}.csv"
            write_csv(out_csv, avg)
            print(f"[OK] Wrote: {out_csv}")

if __name__ == "__main__":
    main()