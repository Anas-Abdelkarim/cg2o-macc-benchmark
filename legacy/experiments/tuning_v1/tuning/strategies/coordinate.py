"""Coordinate descent: change one parameter at a time (all its candidate values are tried in parallel), keep the best,
then random perturbations of 2-4 parameters of the best setting."""
from __future__ import annotations

import random

from . import Strategy, strategy


@strategy("cd")
class CoordinateDescent(Strategy):
    help = "one parameter at a time, then random perturbations (robust, easy to read, ignores interactions)"

    @classmethod
    def add_arguments(cls, g) -> None:
        g.add_argument("--passes", type=int, default=2, help="cd: sweeps over all parameters")
        g.add_argument("--random-refine", type=int, default=20, help="cd: random perturbations of the best setting at the end")
        g.add_argument("--min-gain", type=float, default=0.005, help="cd: a change must lower the score by this much")
        g.add_argument("--grid-points", type=int, default=5, help="cd: candidate values per continuous parameter")

    def run(self) -> None:
        a, s = self.args, self.study
        best_vals, best = dict(s.start), s.baseline
        for sweep in range(1, a.passes + 1):
            improved = False
            for p in s.space:
                if s.out_of_time():
                    break
                cands = []
                for v in p.candidates(a.grid_points):
                    if best_vals.get(p.key) == v:
                        continue
                    c = dict(best_vals)
                    c[p.key] = v
                    cands.append(c)
                if p.optional and p.key in best_vals:       # also try "unset"
                    c = dict(best_vals)
                    del c[p.key]
                    cands.append(c)
                if not cands:
                    continue
                evs = s.evaluate_many(cands, f"cd{sweep}")
                top = min(evs, key=lambda e: e.score)
                if top.score < best.score - a.min_gain:
                    best, best_vals, improved = top, dict(top.values), True
                    s.say(f"[pass {sweep}] {p.name} -> {best_vals.get(p.key, '<unset>')}")
            if not improved:
                break
        rng = random.Random(a.seed)
        names = list(s.space)
        for _ in range(a.random_refine):
            if s.out_of_time():
                break
            c = dict(best_vals)
            for p in rng.sample(names, k=min(len(names), rng.choice([2, 3, 4]))):
                c[p.key] = p.sample(rng)
            if c == best_vals:
                continue
            ev = s.evaluate(c, "random-refine")
            if ev.accepted and ev.score < best.score - a.min_gain:
                best, best_vals = ev, dict(c)
