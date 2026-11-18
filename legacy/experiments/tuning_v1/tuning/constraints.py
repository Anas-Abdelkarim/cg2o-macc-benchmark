"""Rejection rules: a candidate that violates one gets score = inf. Generic: a constraint is a bound on one metric."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Any

from .metrics import Metrics


@dataclass(frozen=True)
class Constraint:
    metric: str
    op: str = "<="                  # "<=" or ">="
    limit: float = 0.0
    label: str = ""                 # text in the rejection reason (default: the metric name)

    def violation(self, m: Metrics) -> str:
        v = m.get(self.metric)
        if not math.isfinite(v):
            return f"{self.label or self.metric}: not available"
        bad = v > self.limit if self.op == "<=" else v < self.limit
        return f"{self.label or self.metric} {v:.3g} {'>' if self.op == '<=' else '<'} {self.limit:g}" if bad else ""


def parse(text: str) -> Constraint:
    """'gap_median<=1e-3' -> Constraint (used by the --constraint option)."""
    for op in ("<=", ">="):
        if op in text:
            name, lim = text.split(op, 1)
            return Constraint(name.strip(), op, float(lim))
    raise ValueError(f"constraint must look like metric<=value or metric>=value, got {text!r}")


def merge(base: Iterable[Constraint], overrides: Iterable[Constraint]) -> list:
    """Overrides replace the base constraint of the same metric and operator."""
    over = {(c.metric, c.op): c for c in overrides}
    out = [over.pop((c.metric, c.op), c) for c in base]
    return out + list(over.values())


def check(constraints: Iterable[Constraint], per_case: Dict[Any, Metrics], label: Callable[[Any], str]) -> str:
    """Rejection reason over all cases ('' = accepted). A failed run is always a rejection."""
    why = []
    for case, m in per_case.items():
        if not m.ok:
            why.append(f"{label(case)}: {m.why}")
            continue
        why += [f"{label(case)}: {r}" for r in (c.violation(m) for c in constraints) if r]
    return "; ".join(why)
