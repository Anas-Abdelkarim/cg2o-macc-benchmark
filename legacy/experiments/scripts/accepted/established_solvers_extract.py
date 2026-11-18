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

HORIZONS = [3, 15, 30]
DEFAULT_SOLVER_DIRS = {
    "ipopt": "ipopt",
    "knitro": "knitro",
    "conopt": "conopt",
    "loqo": "loqo",
    "minos": "minos",
    "snopt": "snopt",
}

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
        "u": arr("u_input_signal"),
        "iters": arr("num_iterations_signal"),
        "t_ms": arr("cal_time_signal"),
        "cost": arr("cost_level_signal"),
        "u_lang": arr("u_input_signal_lang"),
        "iters_lang": arr("num_iterations_signal_lang"),
        "t_ms_lang": arr("cal_time_signal_lang"),
        "cost_lang": arr("cost_level_signal_lang"),
    }

    # Keep original trimming logic based on positive t_ms
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
    return arr_sorted[mid]


def mean_without_outliers(data):
    data = np.array(data)
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


def stack_mean_no_outliers(runs, key):
    series = [r[key] for r in runs if r[key].size > 0]
    if not series:
        return np.array([])
    L = min(s.size for s in series)
    if L == 0:
        return np.array([])
    M = np.vstack([s[:L] for s in series])
    return np.array([mean_without_outliers(M[:, i]) for i in range(L)])


def compute_avg_for_horizon(runs_for_N: list[dict]) -> dict:
    avgN = {
        "v_h": stack_mean(runs_for_N, "v_h"),
        "v_p": stack_mean(runs_for_N, "v_p"),
        "d_h": stack_mean(runs_for_N, "d_h"),
        "u": stack_mean(runs_for_N, "u"),
        "iters": stack_mean(runs_for_N, "iters"),
        "t_ms": stack_mean_no_outliers(runs_for_N, "t_ms"),
        "cost": stack_mean(runs_for_N, "cost"),
        "u_lang": stack_mean(runs_for_N, "u_lang"),
        "iters_lang": stack_mean(runs_for_N, "iters_lang"),
        "t_ms_lang": stack_mean_no_outliers(runs_for_N, "t_ms_lang"),
        "cost_lang": stack_mean(runs_for_N, "cost_lang"),
    }

    lengths = [len(v) for v in avgN.values() if isinstance(v, np.ndarray) and v.size > 0]
    Lmin = min(lengths) if lengths else 0

    if Lmin > 0:
        for k, v in avgN.items():
            if isinstance(v, np.ndarray) and v.size > 0:
                avgN[k] = v[:Lmin]

    return avgN


def write_csv(path: Path, data_dict: dict, use_lang: bool):
    """
    Writes CSV with:
    step,v_p,v_h,d_h,u,iters,t_ms,cost
    If use_lang=False -> normal signals
    If use_lang=True  -> *_lang signals
    """
    cols = ["step", "v_p", "v_h", "d_h", "u", "iters", "t_ms", "cost"]

    if use_lang:
        keys = {
            "u": "u_lang",
            "iters": "iters_lang",
            "t_ms": "t_ms_lang",
            "cost": "cost_lang",
        }
    else:
        keys = {
            "u": "u",
            "iters": "iters",
            "t_ms": "t_ms",
            "cost": "cost",
        }

    L = 0
    candidate_keys = ["v_p", "v_h", "d_h", keys["u"], keys["iters"], keys["t_ms"], keys["cost"]]
    for k in candidate_keys:
        if isinstance(data_dict.get(k), np.ndarray) and data_dict[k].size > 0:
            L = len(data_dict[k])
            break

    if L == 0:
        raise RuntimeError(f"No data to write for {path.name}")

    step = np.arange(L, dtype=int)

    def col(name):
        a = data_dict.get(name, np.array([]))
        if not isinstance(a, np.ndarray) or a.size == 0:
            return np.full(L, np.nan, dtype=float)
        return a[:L]

    data = np.column_stack([
        step,
        col("v_p"),
        col("v_h"),
        col("d_h"),
        col(keys["u"]),
        col(keys["iters"]),
        col(keys["t_ms"]),
        col(keys["cost"]),
    ])

    header = ",".join(cols)
    np.savetxt(path, data, delimiter=",", header=header, comments="", fmt="%.18g")


def collect_grouped_paths(data_dir: Path):
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
            raise FileNotFoundError(f"No files for horizon N={N} in {data_dir}")

    return grouped_paths


# ============================================================
# ========================= MAIN =============================
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dir",
        type=Path,
        required=True,
        help="Base directory containing solver subfolders",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory for CSV files. Default: <base-dir>/csv_out",
    )

    # Optional folder name overrides
    ap.add_argument("--ipopt-folder", type=str, default=DEFAULT_SOLVER_DIRS["ipopt"])
    ap.add_argument("--knitro-folder", type=str, default=DEFAULT_SOLVER_DIRS["knitro"])
    ap.add_argument("--conopt-folder", type=str, default=DEFAULT_SOLVER_DIRS["conopt"])
    ap.add_argument("--loqo-folder", type=str, default=DEFAULT_SOLVER_DIRS["loqo"])
    ap.add_argument("--minos-folder", type=str, default=DEFAULT_SOLVER_DIRS["minos"])
    ap.add_argument("--snopt-folder", type=str, default=DEFAULT_SOLVER_DIRS["snopt"])

    args = ap.parse_args()

    base_dir = args.dir.expanduser().resolve()
    out_dir = args.out.expanduser().resolve() if args.out else (base_dir / "csv_out")
    out_dir.mkdir(parents=True, exist_ok=True)

    solver_dirs = {
        "ipopt": args.ipopt_folder,
        "knitro": args.knitro_folder,
        "conopt": args.conopt_folder,
        "loqo": args.loqo_folder,
        "minos": args.minos_folder,
        "snopt": args.snopt_folder,
    }

    our_written = False

    for solver_name, folder_name in solver_dirs.items():
        solver_dir = base_dir / folder_name

        if not solver_dir.is_dir():
            print(f"[WARN] Missing folder for {solver_name}: {solver_dir}")
            continue

        grouped = collect_grouped_paths(solver_dir)

        for N in HORIZONS:
            runsN = [load_signals_from_bin(str(p)) for p in grouped[N]]
            avgN = compute_avg_for_horizon(runsN)

            if not our_written:
                out_our = out_dir / f"our_N{N}.csv"
                write_csv(out_our, avgN, use_lang=False)
                print(f"[OK] Wrote: {out_our}")

            out_solver = out_dir / f"{solver_name}_N{N}.csv"
            write_csv(out_solver, avgN, use_lang=True)
            print(f"[OK] Wrote: {out_solver}")

        our_written = True


if __name__ == "__main__":
    main()