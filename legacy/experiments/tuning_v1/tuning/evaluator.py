"""Evaluator: parameter set -> Evaluation. Runs all cases in parallel through the Experiment, applies the constraints and the
objective. It knows nothing about the simulation behind the Experiment."""
from __future__ import annotations

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from .constraints import Constraint, check
from .experiment import Experiment
from .metrics import Evaluation, Metrics
from .objectives import OBJECTIVES, Context
from .params import Values


class Evaluator:
    def __init__(self, experiment: Experiment, constraints, cases, fidelity: int, objective: str, context: Context):
        if objective not in OBJECTIVES:
            raise KeyError(f"unknown objective {objective!r}; available: {', '.join(sorted(OBJECTIVES))}")
        self.experiment, self.constraints = experiment, tuple(constraints)
        self.cases, self.fidelity = tuple(cases), fidelity
        self.objective, self.context = objective, context
        self.n_runs = 0
        self._lock = threading.Lock()
        self._cache = {}

    def evaluate(self, values: Values, fidelity: Optional[int] = None, *, baseline: bool = False, use_cache: bool = True,
                 cases=None) -> Evaluation:
        fidelity = self.fidelity if fidelity is None else fidelity
        cases = tuple(cases or self.cases)
        key = json.dumps([sorted(values.items()), fidelity, [str(c) for c in cases]], default=str)
        if use_cache and key in self._cache:
            return self._cache[key]
        with self._lock:
            self.n_runs += len(cases)
            base_id = self.n_runs
        with ThreadPoolExecutor(max_workers=len(cases)) as ex:
            futs = {c: ex.submit(self._run, values, c, fidelity, f"t{base_id}_{self.experiment.case_label(c)}") for c in cases}
            per = {c: f.result() for c, f in futs.items()}
        # the starting setting is never rejected for its quality (it only needs to run); candidates are
        reason = "" if baseline and all(m.ok for m in per.values()) else check(self.constraints, per, self.experiment.case_label)
        score = math.inf if reason else OBJECTIVES[self.objective](per, self.context)
        ev = Evaluation(dict(values), per, fidelity, score, reason)
        if use_cache:
            self._cache[key] = ev
        return ev

    def _run(self, values, case, fidelity, tag) -> Metrics:
        try:
            return self.experiment.run(values, case, fidelity, tag)
        except Exception as e:      # a crashing experiment rejects the candidate, it does not stop the study
            return Metrics.failed(f"experiment raised {type(e).__name__}: {e}")
