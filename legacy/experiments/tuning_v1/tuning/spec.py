"""An algorithm to tune: its parameters, which experiment tunes it and how results are judged.

The spec holds no simulation details: `setup` is a free dict that only the named experiment interprets
(for the MACC closed loop: target / driver / init / cases / paper_key ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from .constraints import Constraint
from .params import ParamSpace


@dataclass
class AlgorithmSpec:
    name: str                                   # registry key and CLI name
    description: str
    params: ParamSpace                          # what can be tuned and in which range
    experiment: str                             # name of the registered Experiment that evaluates it
    setup: Dict[str, Any] = field(default_factory=dict)          # interpreted by the experiment only
    constraints: Tuple[Constraint, ...] = ()    # a candidate that violates one is rejected (score = inf)
    default_groups: Tuple[str, ...] = ("main",)
    default_objective: str = ""
    promote_gain: float = 0.0                   # default of --promote-gain (0 = no promotion to full-length runs)
    notes: str = ""
