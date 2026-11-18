"""The Experiment interface: the ONE place that knows the simulation being tuned.

An Experiment turns a parameter set into Metrics:

    run(values, case, fidelity, tag) -> Metrics

`values`   {param key: value} chosen by a strategy (the keys are whatever the algorithm's Params use),
`case`     one scenario to run (e.g. a prediction horizon, a road, a random seed),
`fidelity` how long / how detailed the run is (a short screening run or the full one; 0 = full),
`tag`      a unique string for temporary files.
Everything else (constraints, objectives, strategies, reports, plots) works on Metrics only. To tune something else than the
MACC closed loop, write one Experiment subclass (see experiments/toy.py, 60 lines) and register it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Type

from .metrics import Metrics
from .params import ParamSpace, Values


@dataclass(frozen=True)
class Column:
    """A metric shown in trials.csv / status / reports."""
    metric: str
    header: str
    fmt: str = "{:.2f}"


class Experiment(ABC):
    name = ""
    description = ""
    primary = ""                   # the metric reported as "the" result in status / plots (e.g. iter_mean)
    primary_label = ""             # its name for people (e.g. iterations)
    columns: Sequence[Column] = ()
    case_option_aliases: Sequence[str] = ()      # extra names of --cases / --full-cases, e.g. ("--horizons",)

    def __init__(self, args, spec, work_dir: Path):
        self.args, self.spec, self.work_dir = args, spec, Path(work_dir)

    # --- command line -----------------------------------------------------------------------------------------------
    @classmethod
    def add_arguments(cls, group) -> None:
        """Options of this experiment (added to `tune.py run`)."""

    # --- what to run ------------------------------------------------------------------------------------------------
    def cases(self) -> tuple:
        """The cases evaluated for every candidate (run in parallel). Default: the algorithm's setup['cases']."""
        given = getattr(self.args, "cases", None)
        if given:
            return tuple(self.parse_case(str(c)) for c in given)
        return tuple(self.spec.setup.get("cases", (None,)))

    def parse_case(self, text: str) -> Any:
        return int(text) if text.lstrip("-").isdigit() else text

    def case_label(self, case: Any) -> str:
        return str(case)

    @abstractmethod
    def run(self, values: Values, case: Any, fidelity: int, tag: str) -> Metrics:
        """Run the simulation for one case and return its metrics (Metrics.failed(...) if it could not run)."""

    # --- optional hooks ---------------------------------------------------------------------------------------------
    def current_values(self, space: ParamSpace) -> Values:
        """Values the system currently uses (e.g. read from a config file); keys that are not set are omitted."""
        return {}

    def start_values(self, space: ParamSpace) -> Values:
        """The starting setting of a study: current values, the Params' defaults for the rest (optional ones stay unset)."""
        cur = self.current_values(space)
        out: Values = {}
        for p in space:
            v = cur.get(p.key)
            if v is None:
                if p.optional or p.default is None:
                    continue
                v = p.default
            v = p.snap(v)
            if v is not None:
                out[p.key] = v
        return out

    def context_extras(self) -> Dict[str, Any]:
        """Extra data objectives may use (e.g. numbers from a paper)."""
        return {}

    def reference_note(self, case: Any, metrics: Metrics) -> str:
        """Text appended to a case's line in the report (e.g. the paper's numbers)."""
        return ""

    def overrides_text(self, values: Values) -> str:
        """The result as text to hand to the system (written to best_overrides.txt)."""
        return " ".join(f"{k}={v}" for k, v in values.items())

    @classmethod
    def apply(cls, nested_result: dict, args) -> int:
        """Merge a result into the system's configuration (`tune.py apply`). Default: not supported."""
        raise NotImplementedError(f"{cls.name}: apply is not implemented for this experiment")


EXPERIMENTS: Dict[str, Type[Experiment]] = {}


def register_experiment(cls: Type[Experiment]) -> Type[Experiment]:
    if not cls.name:
        raise ValueError("an Experiment needs a name")
    EXPERIMENTS[cls.name] = cls
    return cls
