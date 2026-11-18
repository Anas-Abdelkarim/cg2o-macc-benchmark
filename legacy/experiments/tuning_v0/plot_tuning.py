#!/usr/bin/env python3
"""Plots of an IPOPT tuning run (results/tuning/<folder>, written by tune_ipopt_cold.py).

    python3 experiments/plot_tuning.py results/tuning/<folder> [--show]

tuning_progress.png     score of every candidate and the best score so far (1 = starting setting, lower is better)
tuning_options.png      effect of each option: best score reached with any value of it in the first sweep
tuning_iterations.png   mean iterations per step for the starting setting and the best setting, per horizon
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from macc_exp import style  # noqa: E402

plt = style.plt


def load(folder: Path):
    return [json.loads(line) for line in open(folder / "log.jsonl") if line.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder", type=Path)
    p.add_argument("--show", action="store_true", help="open the PNG files afterwards")
    p.add_argument("--palette", default="clean", choices=["paper", "clean"])
    a = p.parse_args()
    col = style.apply(a.palette, False)
    rows = load(a.folder)
    screen = [r for r in rows if r["stage"] != "validation"]
    if not screen:
        print("empty log")
        return 1
    score = np.array([r["score"] if r["score"] is not None and not isinstance(r["score"], str) else math.inf
                      for r in screen], dtype=float)
    ok = np.isfinite(score)
    best = np.minimum.accumulate(np.where(ok, score, np.inf))
    x = np.arange(len(screen))
    out = []

    # 1. progress ---------------------------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(6.5, 3.2), constrained_layout=True)
    ax.plot(x[ok], score[ok], "o", ms=2.5, color=style.MUTED, label="candidate")
    ymax = (np.nanmax(score[ok]) if ok.any() else 1) * 1.05
    if (~ok).any():
        ax.plot(x[~ok], np.full((~ok).sum(), ymax), "x", ms=3, color="#e34948", label="rejected")
    fin = np.isfinite(best)
    ax.step(x[fin], best[fin], where="post", color=col["a"] if a.palette == "paper" else col["accent"], lw=1.4,
            label="best so far")
    ax.axhline(1.0, color="0.5", lw=0.6, ls="--")
    for stage in ("pass1", "pass2", "random"):
        idx = [i for i, r in enumerate(screen) if r["stage"] == stage]
        if idx:
            ax.axvline(idx[0] - 0.5, color="0.7", lw=0.5)
            ax.text(idx[0], ymax, stage, fontsize=6, va="bottom", color="0.4")
    ax.set_xlabel("evaluation")
    ax.set_ylabel("score (baseline = 1)")
    ax.legend(frameon=False, fontsize=7, loc="lower left")
    style.dense_grid(ax)
    out.append(a.folder / "tuning_progress.png")
    fig.savefig(out[-1], bbox_inches="tight")
    plt.close(fig)

    # 2. effect of every option -------------------------------------------------------------------------------
    eff: dict[str, tuple[float, str]] = {}
    for r, s in zip(screen, score):
        if r["stage"] == "pass1" and "=" in r["change"] and np.isfinite(s):
            name, val = r["change"].split("=", 1)
            if name not in eff or s < eff[name][0]:
                eff[name] = (s, val)
    tried = {r["change"].split("=", 1)[0] for r in screen if r["stage"] == "pass1" and "=" in r["change"]}
    if tried:
        names = sorted(tried, key=lambda n: eff.get(n, (math.inf, ""))[0])
        vals = [eff[n][0] if n in eff else np.nan for n in names]
        fig, ax = plt.subplots(figsize=(6.5, 0.25 * len(names) + 0.9), constrained_layout=True)
        y = np.arange(len(names))
        ax.barh(y, [v if np.isfinite(v) else 0 for v in vals], color=style.GOOD, height=0.65)
        for yi, n, v in zip(y, names, vals):
            ax.text(v if np.isfinite(v) else 0, yi, f"  {n} = {eff[n][1]}" if n in eff else f"  {n}: all rejected",
                    va="center", fontsize=6)
        ax.axvline(1.0, color="0.4", lw=0.6, ls="--")
        ax.set_yticks([])
        ax.invert_yaxis()
        ax.set_xlabel("best score with this option changed alone (baseline = 1)")
        style.dense_grid(ax)
        out.append(a.folder / "tuning_options.png")
        fig.savefig(out[-1], bbox_inches="tight")
        plt.close(fig)

    # 3. iterations: baseline vs best ---------------------------------------------------------------------------
    base = next((r for r in rows if r["stage"] == "baseline"), None)
    cand = [r for r in rows if r["stage"] == "validation" and np.isfinite(float(r["score"]))] or \
           [r for r, s in zip(screen, score) if np.isfinite(s)]
    if base and cand:
        bestr = min(cand, key=lambda r: float(r["score"]))
        hs = list(base["per_horizon"])
        fig, ax = plt.subplots(figsize=(4.2, 2.8), constrained_layout=True)
        w = 0.36
        xi = np.arange(len(hs))
        b = [base["per_horizon"][h].get("iter", np.nan) for h in hs]
        t = [bestr["per_horizon"][h].get("iter", np.nan) for h in hs]
        ax.bar(xi - w / 2, b, w, color=style.MUTED, label="starting setting")
        ax.bar(xi + w / 2, t, w, color=style.GOOD, label="best setting")
        for xx, v in zip(xi - w / 2, b):
            ax.text(xx, v, f"{v:.0f}", ha="center", va="bottom", fontsize=6)
        for xx, v in zip(xi + w / 2, t):
            ax.text(xx, v, f"{v:.0f}", ha="center", va="bottom", fontsize=6)
        ax.set_xticks(xi, [f"N = {h}" for h in hs])
        ax.set_ylabel("mean iterations per MPC step")
        ax.legend(frameon=False, fontsize=7)
        style.dense_grid(ax)
        out.append(a.folder / "tuning_iterations.png")
        fig.savefig(out[-1], bbox_inches="tight")
        plt.close(fig)

    for f in out:
        print(f)
    if a.show:
        import shutil
        import subprocess
        for f in out:
            opener = "wslview" if shutil.which("wslview") else "xdg-open"
            subprocess.Popen([opener, str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
