"""Data that flows between the layers. Nothing here knows about a particular simulation.

    Metrics      what ONE run of an Experiment returns: ok / why and a dict {metric name: float}
    Evaluation   one parameter set evaluated on all cases: Metrics per case, score, rejection reason
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Metrics:
    ok: bool = False
    why: str = ""                                   # reason when not ok
    values: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def failed(cls, why: str) -> "Metrics":
        return cls(ok=False, why=why)

    def get(self, name: str, default: float = math.nan) -> float:
        return self.values.get(name, default)

    def __getitem__(self, name: str) -> float:
        return self.values[name]

    def as_dict(self) -> dict:
        return {"ok": self.ok, "why": self.why,
                "values": {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in self.values.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "Metrics":
        return cls(d["ok"], d.get("why", ""), {k: (math.nan if v is None else v) for k, v in d["values"].items()})


@dataclass
class Evaluation:
    values: Dict[str, Any]                          # the parameter set {param key: value}
    per_case: Dict[Any, Metrics]                    # case (e.g. a horizon, a scenario) -> Metrics
    fidelity: int                                   # simulation length of the runs (0 = the experiment's full length)
    score: float                                    # lower is better; inf = rejected
    rejected: str = ""
    index: int = 0
    stage: str = ""

    @property
    def accepted(self) -> bool:
        return math.isfinite(self.score)

    def to_dict(self) -> dict:
        return {"index": self.index, "stage": self.stage, "fidelity": self.fidelity,
                "score": self.score if math.isfinite(self.score) else None, "rejected": self.rejected,
                "values": self.values, "per_case": {str(c): m.as_dict() for c, m in self.per_case.items()}}
