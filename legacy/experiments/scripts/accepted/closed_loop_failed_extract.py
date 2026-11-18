#!/usr/bin/env python3
import argparse
from pathlib import Path
import numpy as np
from data_saver.data_loader import DataLoader


def safe_get(results, key, default):
    return results.get(key, default)


def load_signals_from_bin(bin_path: Path) -> dict:
    with DataLoader(str(bin_path)) as loader:
        results = loader.load_all()

    return {
        "v_h_signal": np.array(safe_get(results, "v_h_signal", []), dtype=float),
        "d_h_signal": np.array(safe_get(results, "d_h_signal", []), dtype=float),
        "v_p_signal": np.array(safe_get(results, "v_p_signal", []), dtype=float),
        "a_p_signal": np.array(safe_get(results, "a_p_signal", []), dtype=float),
        "num_iterations_signal": np.array(safe_get(results, "num_iterations_signal", []), dtype=float),
        "cal_time_signal": np.array(safe_get(results, "cal_time_signal", []), dtype=float),
        "u_input_signal": np.array(safe_get(results, "u_input_signal", []), dtype=float),
    }


def write_csv(csv_path: Path, signals: dict) -> None:
    columns = [
        "v_h_signal",
        "d_h_signal",
        "v_p_signal",
        "a_p_signal",
        "num_iterations_signal",
        "cal_time_signal",
        "u_input_signal",
    ]

    max_len = max((len(signals[col]) for col in columns), default=0)
    if max_len == 0:
        raise RuntimeError(f"No data found to write for {csv_path.name}")

    data = np.full((max_len, len(columns)), np.nan, dtype=float)

    for j, col in enumerate(columns):
        arr = signals[col]
        if arr.size > 0:
            data[: len(arr), j] = arr

    header = ",".join(columns)
    np.savetxt(csv_path, data, delimiter=",", header=header, comments="", fmt="%.18g")


def main():
    parser = argparse.ArgumentParser(
        description="Loop through all .bin files in a directory, extract selected signals, and save one CSV per .bin file in the same folder."
    )
    parser.add_argument(
        "--dir",
        type=Path,
        required=True,
        help="Directory containing .bin files",
    )
    args = parser.parse_args()

    input_dir = args.dir.expanduser().resolve()
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Not a valid directory: {input_dir}")

    bin_files = sorted(input_dir.glob("*.bin"))
    if not bin_files:
        raise FileNotFoundError(f"No .bin files found in {input_dir}")

    for bin_file in bin_files:
        try:
            signals = load_signals_from_bin(bin_file)
            csv_path = bin_file.with_suffix(".csv")
            write_csv(csv_path, signals)
            print(f"[OK] Wrote {csv_path}")
        except Exception as exc:
            print(f"[ERROR] Failed for {bin_file.name}: {exc}")


if __name__ == "__main__":
    main()
