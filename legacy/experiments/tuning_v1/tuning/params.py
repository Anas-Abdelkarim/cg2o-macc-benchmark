"""Tunable parameters.

A `Param` names one entry of config/config.yaml by its dotted key (e.g. `bipm_settings.kappa_initial`,
`ipopt_settings.options.tol`), its type and its search range. Algorithms list their Params in
`tuning/algorithms/<name>.py`; the search strategies only see `Param` / `ParamSpace`.

Kinds:  float          uniform in [low, high]
        log            log-uniform in [low, high]
        int            integer in [low, high]
        cat            one of `choices` (strings, numbers)
        one_minus_log  1 - x with x log-uniform in [low, high] (a value close to 1, e.g. IPOPT tau_min)

A parameter value set is a plain dict {dotted key: value}. A key that is absent means "not set" (the solver default).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

KINDS = ("float", "log", "int", "cat", "one_minus_log")
Values = Dict[str, Any]


def sig(v: float, digits: int = 3) -> float:
    """Round to a few significant digits so that option files stay readable."""
    return float(f"{v:.{digits}g}")


def _geomspace(lo: float, hi: float, n: int) -> List[float]:
    if n <= 1:
        return [lo]
    r = (hi / lo) ** (1.0 / (n - 1))
    return [lo * r ** i for i in range(n)]


@dataclass(frozen=True)
class Param:
    key: str                       # dotted path in config.yaml
    kind: str
    low: Optional[float] = None
    high: Optional[float] = None
    choices: tuple = ()
    default: Any = None            # used as starting value when the config does not set the key
    grid: tuple = ()               # explicit candidate values for coordinate search (default: derived from the range)
    optional: bool = False         # the search may also leave it unset (solver default is computed from other options)
    group: str = "main"            # "main" | "shared" (options other algorithms use too) | any name you like
    doc: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.key}: unknown kind {self.kind!r}")
        if self.kind == "cat" and not self.choices:
            raise ValueError(f"{self.key}: kind cat needs choices")
        if self.kind != "cat" and (self.low is None or self.high is None or not self.low < self.high):
            raise ValueError(f"{self.key}: needs low < high")
        if self.kind in ("log", "one_minus_log") and self.low <= 0:
            raise ValueError(f"{self.key}: log ranges need low > 0")

    @property
    def name(self) -> str:
        return self.key.rsplit(".", 1)[-1]

    # --- values --------------------------------------------------------------------------------------------------
    def snap(self, v: Any) -> Any:
        """Map a config value onto this parameter's domain (clip numbers, normalise yes/no); None if not possible."""
        if self.kind == "cat":
            if isinstance(v, bool) and "yes" in self.choices:
                v = "yes" if v else "no"
            return v if v in self.choices else None
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        if self.kind == "int":
            return int(min(max(round(x), self.low), self.high))
        if self.kind == "one_minus_log":
            return min(max(x, 1.0 - self.high), 1.0 - self.low)
        return min(max(x, self.low), self.high)

    def sample(self, rng: random.Random) -> Any:
        if self.kind == "cat":
            return rng.choice(self.choices)
        if self.kind == "int":
            return rng.randint(int(self.low), int(self.high))
        if self.kind == "float":
            return sig(rng.uniform(self.low, self.high))
        x = math.exp(rng.uniform(math.log(self.low), math.log(self.high)))
        return sig(x) if self.kind == "log" else round(1.0 - sig(x), 6)

    def candidates(self, n: int = 5) -> list:
        """Values tried by coordinate search."""
        if self.grid:
            return list(self.grid)
        if self.kind == "cat":
            return list(self.choices)
        if self.kind == "int":
            span = int(self.high) - int(self.low) + 1
            if span <= n:
                return list(range(int(self.low), int(self.high) + 1))
            return sorted({int(round(self.low + i * (self.high - self.low) / (n - 1))) for i in range(n)})
        if self.kind == "float":
            return [sig(self.low + i * (self.high - self.low) / (n - 1)) for i in range(n)]
        g = [sig(v) for v in _geomspace(self.low, self.high, n)]
        return g if self.kind == "log" else [round(1.0 - v, 6) for v in g]

    def describe_range(self) -> str:
        if self.kind == "cat":
            return "{" + ", ".join(str(c) for c in self.choices) + "}"
        tag = {"float": "", "log": " (log)", "int": " (int)", "one_minus_log": " (1 - log)"}[self.kind]
        if self.kind == "one_minus_log":
            return f"[{1 - self.high:g}, {1 - self.low:g}]{tag}"
        return f"[{self.low:g}, {self.high:g}]{tag}"


# short constructors ---------------------------------------------------------------------------------------------------
def Float(key, low, high, default=None, **kw): return Param(key, "float", low, high, default=default, **kw)
def Log(key, low, high, default=None, **kw): return Param(key, "log", low, high, default=default, **kw)
def Int(key, low, high, default=None, **kw): return Param(key, "int", low, high, default=default, **kw)
def Cat(key, choices: Sequence, default=None, **kw): return Param(key, "cat", choices=tuple(choices), default=default, **kw)
def OneMinusLog(key, low, high, default=None, **kw): return Param(key, "one_minus_log", low, high, default=default, **kw)


def config_get(cfg: dict, dotted: str) -> Any:
    d: Any = cfg
    for part in dotted.split("."):
        d = d.get(part) if isinstance(d, dict) else None
        if d is None:
            return None
    return d


class ParamSpace:
    """An ordered collection of Params."""

    def __init__(self, params: Iterable[Param]):
        self.params: List[Param] = list(params)
        keys = [p.key for p in self.params]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate parameter keys: " + ", ".join(sorted({k for k in keys if keys.count(k) > 1})))

    def __iter__(self):
        return iter(self.params)

    def __len__(self):
        return len(self.params)

    def __getitem__(self, key: str) -> Param:
        for p in self.params:
            if p.key == key or p.name == key:
                return p
        raise KeyError(key)

    def select(self, groups: Optional[Sequence[str]] = None, names: Optional[Sequence[str]] = None) -> "ParamSpace":
        ps = self.params
        if groups:
            ps = [p for p in ps if p.group in groups]
        if names:
            unknown = [n for n in names if not any(n in (p.key, p.name) for p in self.params)]
            if unknown:
                raise KeyError("unknown parameters: " + ", ".join(unknown))
            ps = [p for p in self.params if p.key in names or p.name in names]
        return ParamSpace(ps)

    def start_values(self, config: dict) -> Values:
        """Starting point = the values in the config; defaults for keys it lacks; optional keys it lacks stay unset."""
        out: Values = {}
        for p in self.params:
            v = config_get(config, p.key)
            if v is None:
                if p.optional or p.default is None:
                    continue
                v = p.default
            v = p.snap(v)
            if v is not None:
                out[p.key] = v
        return out


def fmt_value(v: Any) -> str:
    """Text of a value on the macc_run command line (`--set key=value`)."""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return repr(v)
    return str(v)
