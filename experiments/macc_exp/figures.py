"""Paper-style comparison figures (Fig. 2: cg2o vs BIPM, Fig. 3: cg2o vs IPOPT)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

import matplotlib
import matplotlib.colors

from . import style
from .runner import RunResult

plt = style.plt

ROW_LABELS = {
    "iter": "Iterations",
    "time": "Time [ms]",
    "tpi": "Time / iteration [ms]",
    "cost": r"Cost [$\times 10^6$]",
    "better": "Cost better",
}

#: relative cost difference below which two costs are considered equal
COST_TOL = 1e-6


def _col(run: RunResult, solver: str, what: str, hide_failed: bool = False) -> np.ndarray:
    """Per-step values of a solver; with hide_failed, steps the solver failed are NaN (not drawn, not averaged)."""
    y = np.asarray(run.steps()[f"{solver}_{what}"], dtype=float)
    ok = run.steps().get(f"{solver}_success")
    if hide_failed and ok is not None:
        y = np.where(np.asarray(ok) > 0, y, np.nan)
    return y


def _has_result(run: RunResult, solver: str) -> bool:
    """The solver solved at least one step successfully in this run."""
    ok = run.steps().get(f"{solver}_success")
    return f"{solver}_iterations" in run.steps() and (ok is None or bool(np.any(np.asarray(ok) > 0)))


def _numbers(ax, lines: Sequence[tuple]) -> None:
    """Mean values in the colour of each solver, top right of the panel (lines: (text, colour))."""
    for i, (txt, c) in enumerate(lines):
        bg = matplotlib.colors.to_rgb(c)
        ax.text(0.99, 0.97 - 0.19 * i, txt, transform=ax.transAxes, ha="right", va="top", fontsize=5.8,
                color="black", zorder=5,
                bbox=dict(boxstyle="round,pad=0.2", fc=(*bg, 0.35), ec=bg, lw=0.8))


def comparison_figure(runs: Dict[int, RunResult], a: str, b: str, labels: Dict[str, str],
                      rows: Sequence[str], out_stem: Path, *, palette: str = "paper",
                      latex: bool = False, formats: Sequence[str] = ("pdf", "png"),
                      note: str = "", hide_failed: bool = False, numbers: bool = True) -> List[Path]:
    """Compare solvers `a` (the proposed one) and `b` on every horizon in `runs`.

    rows: any of 'traj' (velocity / distance / force, taken from the largest horizon),
          'iter', 'time', 'tpi' (time per iteration), 'cost', 'better'.
    hide_failed: steps a solver failed are not drawn or averaged, and a horizon where a solver has no
          successful step is left out (failed / timed-out runs are never in `runs`).
    numbers: write the means in the panels (iterations mean and max, time, time per iteration and its
          ratio to solver a), in the colour of each solver.
    """
    col = style.apply(palette, latex)
    if hide_failed:
        runs = {n: r for n, r in runs.items() if _has_result(r, a) and _has_result(r, b)}
        if not runs:
            raise ValueError(f"no horizon where both {a} and {b} have results")
    horizons = sorted(runs)
    ncol = max(len(horizons), 3 if "traj" in rows else 1)
    nrow = len(rows)
    height = {"traj": 1.15, "iter": 1.0, "time": 1.0, "tpi": 1.0, "cost": 1.0, "better": 1.0}
    fig, axes = plt.subplots(nrow, ncol, figsize=(7.1, 0.55 + sum(height[r] for r in rows)),
                             constrained_layout=True,
                             gridspec_kw={"height_ratios": [height[r] for r in rows]},
                             squeeze=False)
    # unused panels (fewer horizons than columns) are hidden
    for i, r in enumerate(rows):
        if r != "traj":
            for j in range(len(horizons), ncol):
                axes[i, j].set_visible(False)

    lw = style.LINE_WIDTH
    for i, r in enumerate(rows):
        if r == "traj":
            ref = runs[horizons[-1]]
            st = ref.steps()
            k = st["k"]
            ax = axes[i, 0]
            ax.plot(k, st["v_p"], color=col["preceding"], lw=lw, label=r"$v_p$")
            ax.plot(k, st["v_h"], color=col["host"], lw=lw, label=r"$v_h$")
            ax.set_ylabel("Velocity [m/s]")
            ax.legend(loc="upper left", frameon=False, ncol=2, borderaxespad=0.2, handlelength=1.4)
            style.dense_grid(ax)
            ax = axes[i, 1]
            ax.plot(k, st["d_h"], color=col["host"], lw=lw)
            ax.set_ylabel(r"Distance $d_h$ [m]")
            style.dense_grid(ax)
            ax = axes[i, 2]
            ax.plot(k, _col(ref, a, "u") / 1000.0, color=col["a"], lw=lw, label=labels[a])
            ax.plot(k, _col(ref, b, "u") / 1000.0, color=col["b"], lw=lw, label=labels[b])
            ax.set_ylabel("Force [kN]")
            style.dense_grid(ax)
            axes[i, 0].set_title(f"Trajectories, N = {horizons[-1]}", loc="left", fontsize=7.5)
            for j in range(3, ncol):
                axes[i, j].set_visible(False)
            continue

        for j, n in enumerate(horizons):
            run = runs[n]
            ax = axes[i, j]
            k = run.steps()["k"]
            if r in ("iter", "time", "tpi"):
                key = {"iter": "iterations", "time": "time_ms", "tpi": "ms_per_iter"}[r]
                ya, yb = _col(run, a, key, hide_failed), _col(run, b, key, hide_failed)
                ax.plot(k, ya, color=col["a"], lw=lw, label=labels[a])
                ax.plot(k, yb, color=col["b"], lw=lw, label=labels[b])
                for y, c in ((ya, col["a"]), (yb, col["b"])):
                    ax.axhline(np.nanmean(y), color=c, ls="--", lw=lw)
                if numbers:
                    ma = np.nanmean(ya)
                    if r == "iter":
                        txt = [f"{np.nanmean(y):.1f}, max {np.nanmax(y):.0f}" for y in (ya, yb)]
                    elif r == "time":
                        txt = [f"{np.nanmean(y):.3g} ms" for y in (ya, yb)]
                    else:
                        txt = [f"{np.nanmean(y):.3g} ms/it  x{np.nanmean(y) / ma:.2f}" for y in (ya, yb)]
                    _numbers(ax, list(zip(txt, (col["a"], col["b"]))))
            elif r == "cost":
                ya, yb = _col(run, a, "cost", hide_failed) / 1e6, _col(run, b, "cost", hide_failed) / 1e6
                ax.plot(k, ya, color=col["a"], lw=lw, label=labels[a])
                ax.plot(k, yb, color=col["b"], lw=0, marker="o", markerfacecolor="none",
                        markeredgewidth=0.4, markersize=3.5, markevery=20, label=labels[b])
            elif r == "better":
                ca, cb = _col(run, a, "cost"), _col(run, b, "cost")
                rel = (ca - cb) / np.maximum(np.abs(cb), 1e-12)
                # 1: equal (|rel. diff| <= COST_TOL), 0.5: second solver has the lower cost, 0: first solver has the lower cost
                state = np.where(rel < -COST_TOL, 0.0, np.where(rel > COST_TOL, 0.5, 1.0))
                ax.fill_between(k, 0, state, step="mid", color=col["accent"], alpha=0.35, lw=0)
                ax.step(k, state, where="mid", color=col["accent"], lw=0.6)
                ax.set_ylim(-0.1, 1.15)
                ax.set_yticks([0, 0.5, 1])
                ax.set_yticklabels([a, b, "equal"], fontsize=5.5)
                ax.set_title(f"equal {100 * np.mean(state == 1):.0f}% | {a} lower {100 * np.mean(state == 0):.0f}% | "
                             f"{b} lower {100 * np.mean(state == 0.5):.0f}%", loc="left", fontsize=5.5, pad=2)
            style.dense_grid(ax)
            if j == 0:
                ax.set_ylabel(ROW_LABELS[r])
            if i == 0 or (rows[0] == "traj" and i == 1):
                ax.set_title(f"N = {n}", fontsize=8)
            if i == nrow - 1:
                ax.set_xlabel("Step")
            else:
                ax.tick_params(labelbottom=False)

    handles = [plt.Line2D([], [], color=col["a"], lw=lw), plt.Line2D([], [], color=col["b"], lw=lw)]
    fig.legend(handles, [labels[a], labels[b]], loc="outside upper center", ncol=2, frameon=False,
               fontsize=7.5, title=note or None, title_fontsize=7)
    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for fmt in formats:
        p = out_stem.with_suffix("." + fmt)
        fig.savefig(p, bbox_inches="tight")
        written.append(p)
    plt.close(fig)
    return written
