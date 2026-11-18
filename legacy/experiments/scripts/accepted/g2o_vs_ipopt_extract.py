#!/usr/bin/env python3
import os
from pathlib import Path
import re
import argparse
import numpy as np
from data_saver.data_loader import DataLoader

# ============================================================
# ===================== DEFAULT SETTINGS =====================
# ============================================================

# Horizons
HORIZONS = [3, 15, 30]

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
        "u_lang":   arr("u_input_signal_lang"),
        "iters_lang": arr("num_iterations_signal_lang"),
        "t_ms_lang":  arr("cal_time_signal_lang"),
        "cost_lang":  arr("cost_level_signal_lang"),
    }

    # Keep your original trimming logic: based on positive t_ms
    if out["t_ms"].size > 0:
        mask = out["t_ms"] > 0
        L = int(np.sum(mask))
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

def compute_avg_for_horizon(runs_for_N: list[dict]) -> dict:
    avgN = {
        "v_h": stack_mean(runs_for_N, "v_h"),
        "v_p": stack_mean(runs_for_N, "v_p"),
        "d_h": stack_mean(runs_for_N, "d_h"),
        "u":   stack_mean(runs_for_N, "u"),
        "iters": stack_mean(runs_for_N, "iters"),
        "t_ms":  stack_mean_no_outliers(runs_for_N, "t_ms"),
        "cost":  stack_mean(runs_for_N, "cost"),
        "u_lang":   stack_mean(runs_for_N, "u_lang"),
        "iters_lang": stack_mean(runs_for_N, "iters_lang"),
        "t_ms_lang":  stack_mean_no_outliers(runs_for_N, "t_ms_lang"),
        "cost_lang":  stack_mean(runs_for_N, "cost_lang"),
    }

    if avgN["cost"].size and avgN["cost_lang"].size:
        L = min(len(avgN["cost"]), len(avgN["cost_lang"]))
        cost = avgN["cost"][:L]
        cost_lang = avgN["cost_lang"][:L]
        avgN["cost_diff"] = cost - cost_lang
        avgN["cost_min"] = (cost < cost_lang).astype(int)
    else:
        avgN["cost_diff"] = np.array([])
        avgN["cost_min"] = np.array([])

    # Also enforce consistent lengths (for clean CSV writing)
    lengths = [len(v) for v in avgN.values() if isinstance(v, np.ndarray) and v.size > 0]
    Lmin = min(lengths) if lengths else 0
    if Lmin > 0:
        for k, v in avgN.items():
            if isinstance(v, np.ndarray) and v.size > 0:
                avgN[k] = v[:Lmin]
    return avgN

def write_csv(path: Path, avgN: dict):
    """
    Writes a CSV with one row per step and columns matching what we plot.
    """
    cols = [
        "step",
        "v_p", "v_h", "d_h", "u", "u_lang",
        "iters", "iters_lang",
        "t_ms", "t_ms_lang",
        "cost", "cost_lang",
        "cost_min",
    ]
    L = 0
    for k in ["v_p","v_h","d_h","u", "u_lang","iters","iters_lang","t_ms","t_ms_lang","cost","cost_lang","cost_min"]:
        if isinstance(avgN.get(k), np.ndarray) and avgN[k].size > 0:
            L = len(avgN[k])
            break

    if L == 0:
        raise RuntimeError(f"No data to write for {path.name}")

    step = np.arange(L, dtype=int)

    def col(name):
        a = avgN.get(name, np.array([]))
        if not isinstance(a, np.ndarray) or a.size == 0:
            return np.full(L, np.nan, dtype=float)
        return a[:L]

    data = np.column_stack([
        step,
        col("v_p"),
        col("v_h"),
        col("d_h"),
        col("u"),
        col("u_lang"),
        col("iters"),
        col("iters_lang"),
        col("t_ms"),
        col("t_ms_lang"),
        col("cost"),
        col("cost_lang"),
        col("cost_min"),
    ])

    header = ",".join(cols)
    np.savetxt(path, data, delimiter=",", header=header, comments="", fmt="%.18g")

# ============================================================
# ========================= MAIN =============================
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path,
                    default=Path(__file__).resolve().parent / "data" / "g2o_vs_ipopt")
    args = ap.parse_args()

    data_dir = args.dir.expanduser().resolve()
    all_bins = sorted(data_dir.glob("*.bin"))
    if not all_bins:
        raise FileNotFoundError(f"No .bin files in {data_dir}")

    grouped_paths = {N: [] for N in HORIZONS}
    for p in all_bins:
        N = extract_horizon_from_filename(str(p))
        if N in grouped_paths:
            grouped_paths[N].append(p)

    for N in HORIZONS:
        if not grouped_paths[N]:
            raise FileNotFoundError(f"No files for horizon N={N}")

    # Load and compute avg per horizon, then write CSV next to the .bin files
    for N in HORIZONS:
        runsN = [load_signals_from_bin(str(p)) for p in grouped_paths[N]]
        avgN = compute_avg_for_horizon(runsN)

        out_csv = data_dir / f"g2o_vs_ipopt_avg_N{N}.csv"
        write_csv(out_csv, avgN)
        print(f"[OK] Wrote: {out_csv}")

if __name__ == "__main__":
    main()