"""Search strategies. A strategy gets a started `Study` and proposes parameter sets; it only uses

    study.space                       ParamSpace to search
    study.start / study.baseline      starting values / their Evaluation
    study.best                        best accepted Evaluation so far
    study.evaluate(values, stage)     one evaluation (logged, tracked, promoted)
    study.evaluate_many(list, stage)  several evaluations in parallel (args.jobs workers)
    study.out, study.args             output folder, parsed command line

Add a strategy: write `strategies/<name>.py` with a class decorated by @strategy("<cli name>") (see random_search.py).
"""
from __future__ import annotations

from typing import Dict, Type

STRATEGIES: Dict[str, Type["Strategy"]] = {}


class Strategy:
    help = ""

    @classmethod
    def add_arguments(cls, group) -> None:
        """Add the strategy's own command line options to an argparse (argument) group."""

    def __init__(self, study, args):
        self.study, self.args = study, args

    def run(self) -> None:
        raise NotImplementedError


def strategy(name: str):
    def deco(cls):
        STRATEGIES[name] = cls
        cls.name = name
        return cls
    return deco


from . import bayesian, coordinate, random_search  # noqa: E402,F401  (register the built-in strategies)
