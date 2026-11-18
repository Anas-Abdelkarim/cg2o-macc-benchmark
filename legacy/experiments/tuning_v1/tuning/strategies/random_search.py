"""Random search: sample every parameter independently. A baseline for the other strategies, and a template for new ones."""
from __future__ import annotations

import random

from . import Strategy, strategy


@strategy("random")
class RandomSearch(Strategy):
    help = "independent random samples of all parameters"

    def run(self) -> None:
        rng = random.Random(self.args.seed)
        s = self.study
        todo = self.args.trials
        while todo > 0 and not s.out_of_time():
            batch = []
            for _ in range(min(todo, max(1, self.args.jobs))):
                v = {}
                for p in s.space:
                    if p.optional and rng.random() < 0.5:
                        continue
                    v[p.key] = p.sample(rng)
                batch.append(v)
            s.evaluate_many(batch, "random")
            todo -= len(batch)
