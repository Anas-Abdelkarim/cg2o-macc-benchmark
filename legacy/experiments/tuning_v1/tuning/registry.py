"""Registries. Algorithms (`algorithms/<name>.py`, `register(AlgorithmSpec(...))`) and experiments (`experiments/<name>.py`,
`@register_experiment`) register themselves at import; importing the two packages is what discovers them."""
from __future__ import annotations

from typing import Dict, List, Type

from .experiment import EXPERIMENTS, Experiment
from .spec import AlgorithmSpec

_ALGORITHMS: Dict[str, AlgorithmSpec] = {}


def register(spec: AlgorithmSpec) -> AlgorithmSpec:
    if spec.name in _ALGORITHMS:
        raise ValueError(f"algorithm {spec.name!r} is already registered")
    _ALGORITHMS[spec.name] = spec
    return spec


def _discover() -> None:
    from . import experiments, algorithms  # noqa: F401  (importing registers everything)


def get(name: str) -> AlgorithmSpec:
    _discover()
    try:
        return _ALGORITHMS[name]
    except KeyError:
        raise KeyError(f"unknown algorithm {name!r}; available: {', '.join(names())}") from None


def names() -> List[str]:
    _discover()
    return sorted(_ALGORITHMS)


def experiment_class(name: str) -> Type[Experiment]:
    _discover()
    try:
        return EXPERIMENTS[name]
    except KeyError:
        raise KeyError(f"unknown experiment {name!r}; available: {', '.join(sorted(EXPERIMENTS))}") from None


def experiment_names() -> List[str]:
    _discover()
    return sorted(EXPERIMENTS)
