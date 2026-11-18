"""Plots of a tuning folder (reads log.jsonl and meta.json): progress, parameter effects, before/after of the primary metric."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List

import numpy as np

SKIP = ("baseline", "full", "full_baseline", "validation", "validation_baseline")


def _load(folder: Path) -> List[dict]:
    return [json.loads(line) for line in open(folder / "log.jsonl") if line.strip()]


def make_plots(folder: Path) -> List[Path]:
    from macc_exp import style              # plain matplotlib style helpers shared with the experiment figures
    col = style.apply("clean", False)
    plt = style.plt
    meta = json.loads((folder / "meta.json").read_text()) if (folder / "meta.json").exists() else {}
    primary, label = meta.get("primary", "iter_mean"), meta.get("primary_label", "primary metric")
    rows = _load(folder)
    screen = [r for r in rows if r["stage"] not in SKIP]
    base = next((r for r in rows if r["stage"] == "baseline"), None)
    out: List[Path] = []
    if not screen:
        return out
    score = np.array([r["score"] if r["score"] is not None else np.inf for r in screen], float)
    ok = np.isfinite(score)
    best = np.minimum.accumulate(np.where(ok, score, np.inf))
    x = np.arange(len(screen))

    fig, ax = plt.subplots(figsize=(6.5, 3.2), constrained_layout=True)
    ax.plot(x[ok], score[ok], "o", ms=2.5, color=style.MUTED, label="accepted candidate")
    top = (np.nanmax(score[ok]) if ok.any() else 1.0) * 1.05
    if (~ok).any():
        ax.plot(x[~ok], np.full((~ok).sum(), top), "x", ms=3, color="#e34948", label="rejected")
    fin = np.isfinite(best)
    ax.step(x[fin], best[fin], where="post", color=col["accent"], lw=1.4, label="best so far")
    if base and base["score"] is not None:
        ax.axhline(base["score"], color="0.5", lw=0.6, ls="--", label="starting setting")
    ax.set_xlabel("evaluation")
    ax.set_ylabel("score (lower is better)")
    ax.legend(frameon=False, fontsize=7)
    style.dense_grid(ax)
    out.append(folder / "tuning_progress.png")
    fig.savefig(out[-1], bbox_inches="tight")
    plt.close(fig)

    effects = []
    for k in sorted({k for r in screen for k in r["values"]}):
        pts = [(r["values"][k], r["score"]) for r in screen if k in r["values"] and r["score"] is not None]
        if len(pts) < 8 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v, _ in pts):
            continue
        v, sc = np.array([p[0] for p in pts], float), np.array([p[1] for p in pts], float)
        if np.ptp(v) == 0:
            continue
        effects.append((abs(float(np.corrcoef(v.argsort().argsort(), sc.argsort().argsort())[0, 1])), k, v, sc))
    effects = sorted(effects, key=lambda t: -t[0])[:6]
    if effects:
        fig, axes = plt.subplots(2, 3, figsize=(7.1, 4.2), constrained_layout=True, squeeze=False)
        for ax, (_, k, v, sc) in zip(axes.ravel(), effects):
            ax.plot(v, sc, "o", ms=2.5, color=col["accent"], alpha=0.6)
            if v.min() > 0 and v.max() / v.min() > 50:
                ax.set_xscale("log")
            ax.set_title(k.rsplit(".", 1)[-1], fontsize=7)
            style.dense_grid(ax)
        for ax in axes.ravel()[len(effects):]:
            ax.set_visible(False)
        fig.supylabel("score")
        out.append(folder / "tuning_parameters.png")
        fig.savefig(out[-1], bbox_inches="tight")
        plt.close(fig)

    vb = next((r for r in rows if r["stage"] == "validation_baseline"), None)
    vals = [r for r in rows if r["stage"] == "validation" and r["score"] is not None]
    b, w = (vb, min(vals, key=lambda r: r["score"])) if vb and vals else (
        base, min([r for r in screen if r["score"] is not None], key=lambda r: r["score"], default=None))
    if b and w:
        cases = list(b["per_case"])
        get = lambda r, c: (r["per_case"].get(c, {}).get("values", {}).get(primary) or np.nan)  # noqa: E731
        fig, ax = plt.subplots(figsize=(4.2, 2.8), constrained_layout=True)
        xi, wd = np.arange(len(cases)), 0.36
        bi, wi = [get(b, c) for c in cases], [get(w, c) for c in cases]
        ax.bar(xi - wd / 2, bi, wd, color=style.MUTED, label="starting setting")
        ax.bar(xi + wd / 2, wi, wd, color=style.GOOD, label="best setting")
        for xx, v in list(zip(xi - wd / 2, bi)) + list(zip(xi + wd / 2, wi)):
            if not math.isnan(v):
                ax.text(xx, v, f"{v:.3g}", ha="center", va="bottom", fontsize=6)
        ax.set_xticks(xi, [str(c) for c in cases])
        ax.set_ylabel(label)
        ax.legend(frameon=False, fontsize=7)
        style.dense_grid(ax)
        out.append(folder / "tuning_primary.png")
        fig.savefig(out[-1], bbox_inches="tight")
        plt.close(fig)
    return out
