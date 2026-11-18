"""A toy experiment: an analytic function instead of a simulation. Two uses:
  * try a search strategy in seconds:  python3 experiments/tune.py run toy --method bo --trials 40
  * a TEMPLATE for porting the library to another simulation: subclass Experiment, implement run(), register it,
    then register an algorithm (algorithms/<name>.py) that names it. Nothing else changes.
"""
from __future__ import annotations

import math
from typing import Any

from ..experiment import Column, Experiment, register_experiment
from ..metrics import Metrics
from ..params import Values
from ..objectives import ratio_objective

ratio_objective("toy_loss", "loss", doc="loss relative to the starting setting")


@register_experiment
class ToyFunction(Experiment):
    name = "toy"
    description = "analytic test function, no simulation"
    primary, primary_label = "loss", "loss"
    columns = (Column("loss", "loss", "{:.4f}"), Column("violation", "violation", "{:.3f}"))

    def run(self, values: Values, case: Any, fidelity: int, tag: str) -> Metrics:
        x = values.get("toy.x", 0.0)
        y = values.get("toy.y", 1.0)
        n = values.get("toy.n", 5)
        shift = {"a": 0.0, "b": 0.3}.get(case, 0.0)              # two cases = two slightly different problems
        loss = 1.0 + (x - 2.0 + shift) ** 2 + 3.0 * (math.log10(y) + 1.0) ** 2 + 0.05 * (n - 7) ** 2
        loss += 0.0 if values.get("toy.mode", "slow") == "fast" else 0.5
        return Metrics(True, "", {"loss": loss, "violation": max(0.0, abs(x) - 4.0)})
