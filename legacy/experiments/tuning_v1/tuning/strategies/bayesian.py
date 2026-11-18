"""Bayesian optimisation with Optuna's TPE sampler (multivariate, so interactions between parameters are modelled).

The first trial is the starting setting. The study is stored in <out>/study.db (SQLite), so a stopped run can be continued
with `--resume <folder>`. Rejected candidates get the value REJECTED_VALUE, which teaches the sampler to avoid them.
"""
from __future__ import annotations

import threading
import warnings

from . import Strategy, strategy

REJECTED_VALUE = 10.0     # a normal score is about 0.5 - 1.5


@strategy("bo")
class Bayesian(Strategy):
    help = "Bayesian optimisation (Optuna TPE): all parameters together, learns from every trial"

    @classmethod
    def add_arguments(cls, g) -> None:
        g.add_argument("--startup", type=int, default=30, help="bo: random trials before the model is used")

    @staticmethod
    def _suggest(trial, p):
        if p.optional and not trial.suggest_categorical(f"{p.key}__set", [False, True]):
            return None
        if p.kind == "cat":
            return trial.suggest_categorical(p.key, list(p.choices))
        if p.kind == "int":
            return trial.suggest_int(p.key, int(p.low), int(p.high))
        if p.kind == "float":
            from ..params import sig
            return sig(trial.suggest_float(p.key, p.low, p.high))
        from ..params import sig
        x = sig(trial.suggest_float(p.key, p.low, p.high, log=True))
        return x if p.kind == "log" else round(1.0 - x, 6)

    def run(self) -> None:
        import optuna
        warnings.filterwarnings("ignore", category=optuna.exceptions.ExperimentalWarning)
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        a, s = self.args, self.study
        sampler = optuna.samplers.TPESampler(seed=a.seed, multivariate=True, group=True, n_startup_trials=a.startup,
                                             constant_liar=a.jobs > 1)
        ostudy = optuna.create_study(study_name=s.spec.name, direction="minimize", sampler=sampler,
                                     storage=f"sqlite:///{s.out / 'study.db'}", load_if_exists=True)
        if not ostudy.trials:      # trial 0 = the starting setting
            enq = {}
            for p in s.space:
                if p.key in s.start:
                    enq[p.key] = s.start[p.key] if p.kind != "one_minus_log" else min(max(1.0 - s.start[p.key], p.low), p.high)
                if p.optional:
                    enq[f"{p.key}__set"] = p.key in s.start
            ostudy.enqueue_trial(enq, skip_if_exists=True)
        done = sum(t.state == optuna.trial.TrialState.COMPLETE for t in ostudy.trials)
        todo = max(0, a.trials - done)
        s.say(f"{done} trials already done, running {todo} more with {a.jobs} parallel, {a.startup} random start-up trials")
        lock, issued = threading.Lock(), [0]

        def worker():
            while True:
                with lock:
                    if issued[0] >= todo or s.out_of_time():
                        return
                    issued[0] += 1
                trial = ostudy.ask()
                try:
                    values = {}
                    for p in s.space:
                        v = self._suggest(trial, p)
                        if v is not None:
                            values[p.key] = v
                    ev = s.evaluate(values, "bo")
                    ostudy.tell(trial, ev.score if ev.accepted else REJECTED_VALUE)
                except BaseException:
                    ostudy.tell(trial, state=optuna.trial.TrialState.FAIL)
                    raise

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, a.jobs))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
