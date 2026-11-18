"""Serializable mixed/conditional search spaces; samples retain full precision."""

from __future__ import annotations
from dataclasses import dataclass, asdict, field
import math
import random
from typing import Any


@dataclass(frozen=True)
class Parameter:
    key: str
    kind: str
    low: float | None = None
    high: float | None = None
    choices: tuple = ()
    default: Any = None
    grid: tuple = ()
    optional: bool = False
    active_if: dict = field(default_factory=dict)
    doc: str = ""

    def __post_init__(self):
        if not self.key or self.key.startswith("__tuning__"):
            raise ValueError("parameter keys must be nonempty and not use __tuning__")
        if self.kind not in ("float", "log", "int", "cat", "one_minus_log"):
            raise ValueError(f"{self.key}: unknown kind {self.kind}")
        if self.kind == "cat":
            if not self.choices or any(
                type(x) not in (str, bool, int, float) for x in self.choices
            ):
                raise ValueError(
                    f"{self.key}: categorical choices must be scalar values"
                )
            if any(isinstance(x, float) and not math.isfinite(x) for x in self.choices):
                raise ValueError("categorical values must be finite")
            if len({(type(x), x) for x in self.choices}) != len(self.choices):
                raise ValueError(f"{self.key}: repeated choice")
        else:
            if (
                self.low is None
                or self.high is None
                or not (
                    math.isfinite(self.low)
                    and math.isfinite(self.high)
                    and self.low < self.high
                )
            ):
                raise ValueError(f"{self.key}: finite low < high required")
            if self.kind in ("log", "one_minus_log") and self.low <= 0:
                raise ValueError("log bounds must be positive")
            if self.kind == "one_minus_log" and self.high >= 1:
                raise ValueError("one_minus_log bounds describe 1-x and must be < 1")
            if self.kind == "int" and (
                int(self.low) != self.low or int(self.high) != self.high
            ):
                raise ValueError("integer bounds required")
        for value in self.grid:
            self.validate(value)

    def active(self, values):
        return all(
            parent in values and values[parent] in allowed
            for parent, allowed in self.active_if.items()
        )

    def repair(self, value):
        """A valid replacement for an invalid value: the declared default if it is valid, else the value clipped to
        the bounds (integers rounded into them), else the first choice."""
        if self.default is not None:
            try:
                self.validate(self.default)
                return self.default
            except ValueError:
                pass
        if self.kind == "cat":
            return self.choices[0]
        lo, hi = (
            (1 - self.high, 1 - self.low)
            if self.kind == "one_minus_log"
            else (self.low, self.high)
        )
        try:
            v = min(max(float(value), lo), hi)
        except (TypeError, ValueError):
            v = lo
        if not math.isfinite(v):
            v = lo
        return int(min(max(round(v), math.ceil(lo)), math.floor(hi))) if self.kind == "int" else v

    def validate(self, value):
        if value is None:
            if self.optional:
                return
            raise ValueError(f"{self.key}: not optional")
        if self.kind == "cat":
            if not any(type(value) is type(x) and value == x for x in self.choices):
                raise ValueError(f"{self.key}: value not in choices")
            return
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{self.key}: finite number required")
        if self.kind == "int" and int(value) != value:
            raise ValueError(f"{self.key}: integer required")
        lo, hi = (
            (1 - self.high, 1 - self.low)
            if self.kind == "one_minus_log"
            else (self.low, self.high)
        )
        if not lo <= value <= hi:
            raise ValueError(f"{self.key}: {value} outside [{lo}, {hi}]")

    def sample(self, rng):
        if self.kind == "cat":
            return rng.choice(self.choices)
        if self.kind == "int":
            return rng.randint(int(self.low), int(self.high))
        if self.kind == "float":
            return rng.uniform(self.low, self.high)
        x = math.exp(rng.uniform(math.log(self.low), math.log(self.high)))
        return (
            min(self.high, max(self.low, x))
            if self.kind == "log"
            else 1 - min(self.high, max(self.low, x))
        )

    def candidates(self, n=5):
        if n < 2:
            raise ValueError("grid_points must be at least 2")
        if self.grid:
            result = list(self.grid)
        elif self.kind == "cat":
            result = list(self.choices)
        elif self.kind == "int":
            result = sorted(
                {
                    round(self.low + i * (self.high - self.low) / (n - 1))
                    for i in range(n)
                }
            )
        elif self.kind == "float":
            result = [self.low + i * (self.high - self.low) / (n - 1) for i in range(n)]
        else:
            result = [
                math.exp(
                    math.log(self.low) + i * math.log(self.high / self.low) / (n - 1)
                )
                for i in range(n)
            ]
            result[0], result[-1] = self.low, self.high
            if self.kind == "one_minus_log":
                result = [1 - x for x in result]
        return ([None] if self.optional else []) + result


def Float(key, low, high, **kw):
    return Parameter(key, "float", low, high, **kw)


def Log(key, low, high, **kw):
    return Parameter(key, "log", low, high, **kw)


def Int(key, low, high, **kw):
    return Parameter(key, "int", low, high, **kw)


def Cat(key, choices, **kw):
    return Parameter(key, "cat", choices=tuple(choices), **kw)


def OneMinusLog(key, low, high, **kw):
    return Parameter(key, "one_minus_log", low, high, **kw)


@dataclass(frozen=True)
class Relation:
    """Cross-parameter bound; skipped if an optional/conditional operand is absent."""

    left: str
    right: str
    op: str = "<="

    def __post_init__(self):
        if self.op not in ("<=", ">=", "<", ">", "=="):
            raise ValueError("invalid parameter relation")

    def check(self, values):
        if self.left not in values or self.right not in values:
            return
        a, b = values[self.left], values[self.right]
        okay = {
            "<=": lambda: a <= b,
            ">=": lambda: a >= b,
            "<": lambda: a < b,
            ">": lambda: a > b,
            "==": lambda: a == b,
        }[self.op]()
        if not okay:
            raise ValueError(
                f"parameter relation failed: {self.left} {self.op} {self.right}"
            )


class Space:
    def __init__(self, parameters, relations=()):
        self.parameters = tuple(parameters)
        self.relations = tuple(relations)
        keys = [p.key for p in self.parameters]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("space must be nonempty with unique keys")
        if any(r.left not in keys or r.right not in keys for r in self.relations):
            raise ValueError("parameter relations must reference declared keys")
        seen = set()
        for p in self.parameters:
            if any(k not in seen for k in p.active_if):
                raise ValueError(
                    f"{p.key}: conditions must reference earlier parameters"
                )
            seen.add(p.key)

    def __iter__(self):
        return iter(self.parameters)

    def __len__(self):
        return len(self.parameters)

    @property
    def keys(self):
        return tuple(p.key for p in self)

    def to_dict(self):
        return [asdict(p) for p in self]

    @classmethod
    def from_dict(cls, rows, relations=()):
        return cls(
            (
                Parameter(
                    **{
                        **r,
                        "choices": tuple(r.get("choices", ())),
                        "grid": tuple(r.get("grid", ())),
                    }
                )
                for r in rows
            ),
            relations=relations,
        )

    def defaults(self):
        return {p.key: p.default for p in self if p.default is not None}

    def normalize(self, values):
        unknown = set(values) - set(self.keys)
        if unknown:
            raise ValueError(f"unknown parameters: {sorted(unknown)}")
        result = {}
        for p in self:
            if p.active(result):
                value = values.get(p.key, None if p.optional else p.default)
                p.validate(value)
                if value is not None:
                    result[p.key] = value
        for relation in self.relations:
            relation.check(result)
        return result

    def repair(self, values):
        """Make a supplied setting (e.g. a baseline read from a configuration file) valid for this space.

        Returns (repaired values, list of (key, old, new, reason)). Values that are present but invalid are replaced
        (Parameter.repair); missing values stay missing (the program keeps its own default). Operands of a broken
        relation are reset to their declared defaults; if the relation still fails, ValueError is raised.
        """
        result, changes = {}, []
        for p in self:
            if p.key not in values or values[p.key] is None:
                continue
            value = values[p.key]
            if p.kind != "cat" and isinstance(value, str):
                try:  # YAML 1.1 reads 1e-3 / 5e5 (no decimal point) as text: same number, not a repair
                    value = int(value) if p.kind == "int" and value.strip().lstrip("+-").isdigit() else float(value)
                except ValueError:
                    pass
            try:
                p.validate(value)
                result[p.key] = value
            except ValueError as e:
                new = p.repair(value)
                p.validate(new)
                result[p.key] = new
                changes.append((p.key, value, new, str(e)))
        for relation in self.relations:
            try:
                relation.check(result)
            except ValueError as e:
                for key in (relation.left, relation.right):
                    d = next(p.default for p in self if p.key == key)
                    if d is not None and result.get(key) != d:
                        changes.append((key, result[key], d, str(e)))
                        result[key] = d
                relation.check(result)  # still broken: the caller must fix the configuration or the space
        return result, changes

    def sample(self, rng: random.Random):
        values = {}
        for p in self:
            if p.active(values) and not (p.optional and rng.random() < 0.5):
                values[p.key] = p.sample(rng)
        return values
