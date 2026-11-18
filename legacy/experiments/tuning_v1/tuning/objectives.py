"""Objectives: Metrics of all cases -> score (LOWER is better). Register one with @objective("name").

An objective gets `metrics: {case: Metrics}` and a `Context` (the starting setting's Metrics per case, and the extras the
experiment provides, e.g. reference numbers). `ratio_objective` builds the common kind: a metric relative to the starting
setting plus weighted penalties. Experiments register their own objectives in their module (see experiments/).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping

from .metrics import Metrics

OBJECTIVES: Dict[str, Callable[[Dict[Any, Metrics], "Context"], float]] = {}


@dataclass
class Context:
    baseline: Dict[Any, Metrics] = field(default_factory=dict)      # the starting setting, per case (empty while it is measured)
    extras: Dict[str, Any] = field(default_factory=dict)            # Experiment.context_extras()


def objective(name: str):
    def deco(fn):
        OBJECTIVES[name] = fn
        return fn
    return deco


def ratio_objective(name: str, metric: str, penalties: Mapping[str, float] = None, doc: str = ""):
    """score = mean over the cases of  metric / metric of the starting setting  +  sum(weight * penalty metric)."""
    penalties = dict(penalties or {})

    def fn(metrics: Dict[Any, Metrics], ctx: Context) -> float:
        parts = []
        for case, m in metrics.items():
            b = ctx.baseline.get(case)
            ref = b.get(metric) if b is not None and b.ok else m[metric]
            parts.append(m[metric] / ref + sum(w * m.get(k, 0.0) for k, w in penalties.items()))
        return statistics.mean(parts)

    fn.__doc__ = doc or f"{metric} relative to the starting setting" + (
        " + penalties " + ", ".join(f"{w:g}*{k}" for k, w in penalties.items()) if penalties else "")
    OBJECTIVES[name] = fn
    return fn
