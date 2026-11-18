"""Study: one tuning session. Independent of the strategy AND of the simulation (it only sees an Experiment).

    baseline        the starting setting is evaluated first; its metrics normalise the score of every candidate
    evaluate*       every candidate evaluation is logged (log.jsonl, trials.csv), tracked as best, and may be PROMOTED
    promotion       a candidate whose screening score is `promote_gain` lower than the reference is re-run at full length
                    (`full_fidelity`, `full_cases`); if that confirms it, it becomes the new reference
    finish          the best `validate_top` candidates are re-run at `validate_fidelity` against the starting setting;
                    report.txt, best_config.yaml, best_overrides.txt are written
Nothing outside the study folder is modified.
"""
from __future__ import annotations

import csv
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from .evaluator import Evaluator
from .experiment import Experiment
from .metrics import Evaluation, Metrics
from .objectives import OBJECTIVES, Context
from .params import ParamSpace, Values
from .spec import AlgorithmSpec

SCREEN_SKIP = ("baseline", "full", "full_baseline", "validation", "validation_baseline")   # stages that are not search results


class Study:
    def __init__(self, spec: AlgorithmSpec, space: ParamSpace, experiment: Experiment, constraints, start: Values, out: Path,
                 args, method: str = "", command: str = ""):
        self.spec, self.space, self.experiment, self.constraints = spec, space, experiment, tuple(constraints)
        self.start, self.out, self.args, self.method, self.command = start, out, args, method, command
        self.cases = tuple(experiment.cases())
        self.full_cases = tuple(experiment.parse_case(str(c)) for c in (args.full_cases or self.cases))
        self.history: List[Evaluation] = []
        self.best: Optional[Evaluation] = None
        self.baseline: Optional[Evaluation] = None
        self.reference = math.inf
        self.promoted: List[Evaluation] = []
        self.evaluator: Optional[Evaluator] = None
        self.stopped = False        # set by an interrupt: strategies stop issuing evaluations
        self._full: Optional[Tuple[Evaluator, Evaluation]] = None
        self._lock = threading.RLock()
        self._log = open(out / "log.jsonl", "a")
        self.t0 = time.time()
        self._init_csv()

    # --- live table: <out>/trials.csv, one row per evaluation, appended and flushed at once ---------------------------
    #   lines 1-2 are comments (command, method, ...): read with pandas.read_csv(path, comment="#")
    def _all_cases(self) -> list:
        return list(dict.fromkeys(list(self.cases) + list(self.full_cases)))

    def _csv_names(self) -> Dict[str, str]:
        short = [p.name for p in self.space]
        return {p.key: (p.name if short.count(p.name) == 1 else p.key) for p in self.space}

    def _csv_columns(self) -> List[str]:
        cols = ["index", "time", "stage", "status", "score"]
        for c in self._all_cases():
            cols += [f"{self.experiment.case_label(c)}_{col.header}" for col in self.experiment.columns]
        return cols + list(self._csv_names().values()) + ["rejected_because"]

    def _init_csv(self) -> None:
        self._csv_path = self.out / "trials.csv"
        self._csv_new = not self._csv_path.exists()
        a = self.args
        head = (f"# command: {self.command or '-'} | algorithm: {self.spec.name} | experiment: {self.experiment.name} | "
                f"method: {self.method} | objective: {a.objective} | screening: cases {[str(c) for c in self.cases]}, "
                f"fidelity {a.steps or 'full'} | {'started' if self._csv_new else 'resumed'}: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"# score: lower is better; status REJECTED = violates a constraint (reason in the last column); "
                f"stage: baseline | <strategy> | full | validation\n")
        with self._lock, open(self._csv_path, "a", newline="") as f:
            f.write(head)
            if self._csv_new:
                csv.writer(f).writerow(self._csv_columns())

    def _csv_write(self, ev: Evaluation) -> None:
        row = [ev.index, datetime.now().strftime("%H:%M:%S"), ev.stage, "ok" if ev.accepted else "REJECTED",
               f"{ev.score:.4f}" if ev.accepted else ""]
        for c in self._all_cases():
            m = ev.per_case.get(c)
            for col in self.experiment.columns:
                row.append(col.fmt.format(m.get(col.metric)) if m is not None and m.ok and math.isfinite(m.get(col.metric)) else "")
        row += [ev.values.get(p.key, "") for p in self.space]
        row.append(ev.rejected)
        with self._lock, open(self._csv_path, "a", newline="") as f:
            csv.writer(f).writerow(row)

    # --- bookkeeping ----------------------------------------------------------------------------------------------
    def load_history(self) -> int:
        """Read the evaluations of an earlier session of this folder (log.jsonl)."""
        path = self.out / "log.jsonl"
        n = 0
        if not path.exists():
            return 0
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            per = {self.experiment.parse_case(c): Metrics.from_dict(m) for c, m in d["per_case"].items()}
            sc = math.inf if d["score"] is None else d["score"]
            ev = Evaluation(d["values"], per, d["fidelity"], sc, d["rejected"], len(self.history), d["stage"])
            self.history.append(ev)
            if self._csv_new:        # the folder has no live table yet: build it from the log
                self._csv_write(ev)
            n += 1
        return n

    def summary(self, ev: Evaluation) -> str:
        e = self.experiment
        vals = " / ".join(f"{m.get(e.primary):.1f}" if m.ok else "-" for m in ev.per_case.values())
        tail = f"  REJECTED: {ev.rejected}" if ev.rejected else ""
        return f"score {ev.score:.3f}  {e.primary_label} {vals}{tail}"

    def _prepare(self, fidelity: int, cases) -> Tuple[Evaluator, Evaluation]:
        """An Evaluator whose score is normalised by the starting setting run with the same fidelity / cases."""
        ctx = Context(extras=self.experiment.context_extras())
        ev = Evaluator(self.experiment, self.constraints, cases, fidelity, self.args.objective, ctx)
        base = ev.evaluate(self.start, baseline=True, use_cache=False)
        ctx.baseline = base.per_case
        if all(m.ok for m in base.per_case.values()):
            base.score = OBJECTIVES[self.args.objective](base.per_case, ctx)
        return ev, base

    def _record(self, ev: Evaluation, stage: str) -> None:
        ev.stage = stage
        with self._lock:
            ev.index = len(self.history)
            self.history.append(ev)
            self._log.write(json.dumps(ev.to_dict(), default=str) + "\n")
            self._log.flush()
            self._csv_write(ev)

    def out_of_time(self) -> bool:
        """True after an interrupt or once --max-hours are used (strategies stop issuing evaluations; the study then validates)."""
        h = getattr(self.args, "max_hours", 0) or 0
        return self.stopped or (h > 0 and (time.time() - self.t0) / 3600.0 >= h)

    def say(self, msg: str) -> None:
        print(f"[{(time.time() - self.t0) / 60:6.1f} min] {msg}", flush=True)

    # --- session --------------------------------------------------------------------------------------------------
    def begin(self) -> None:
        a = self.args
        print(f"algorithm {self.spec.name} | experiment {self.experiment.name} | objective {a.objective} | cases "
              f"{[str(c) for c in self.cases]} | fidelity {a.steps or 'full'} | {len(self.space)} parameters | output {self.out}",
              flush=True)
        self.evaluator, self.baseline = self._prepare(a.steps, self.cases)
        self._record(self.baseline, "baseline")
        self.best, self.reference = self.baseline, self.baseline.score
        self.say(f"starting setting: {self.summary(self.baseline)}")
        for e in self.history:     # evaluations of an earlier session (resume): keep the best one
            if e.accepted and e.stage not in SCREEN_SKIP and e.score < self.best.score:
                self.best = e

    def evaluate(self, values: Values, stage: str = "") -> Evaluation:
        ev = self.evaluator.evaluate(values)
        self._record(ev, stage)
        self._consider(ev)
        return ev

    def evaluate_many(self, many: List[Values], stage: str = "", workers: Optional[int] = None) -> List[Evaluation]:
        workers = max(1, workers or self.args.jobs)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(lambda v: self.evaluate(v, stage), many))

    def _consider(self, ev: Evaluation) -> None:
        with self._lock:
            if not ev.accepted:
                return
            if ev.score < self.best.score:
                self.best = ev
                self.say(f"new best (#{ev.index}, {ev.stage}): {self.summary(ev)}")
            gain = self.args.promote_gain
            if gain and ev.score <= self.reference * (1 - gain) and ev.values != self.start:
                self._promote(ev)

    def _promote(self, ev: Evaluation) -> None:
        a = self.args
        self.say(f"   #{ev.index} is much better than the reference ({ev.score:.3f} vs {self.reference:.3f}): full test ...")
        if self._full is None:
            self._full = self._prepare(a.full_steps, self.full_cases)
            self._record(self._full[1], "full_baseline")
            self.say(f"   full baseline: {self.summary(self._full[1])}")
        full_ev, full_base = self._full
        f = full_ev.evaluate(ev.values, use_cache=False)
        self._record(f, "full")
        self.promoted.append(f)
        self.say(f"   full test:     {self.summary(f)}")
        if f.accepted and f.score < full_base.score:
            self.reference = ev.score
            self.say("   confirmed: new reference")

    def run(self, strategy) -> None:
        if self.args.resume:
            n = self.load_history()
            print(f"resumed: {n} evaluations loaded from {self.out / 'log.jsonl'}", flush=True)
        self.begin()
        try:
            strategy.run()
        except KeyboardInterrupt:
            self.stopped = True
            self.say("interrupted: no new evaluations; validating what was found so far")
        self.finish()
        self._log.close()

    def finish(self, validate: bool = True) -> None:
        a = self.args
        if not validate:       # no new runs: the best screening candidate found so far, judged by its screening score
            first = next((e for e in self.history if e.stage == "baseline"), None)
            cand = [e for e in self.history if e.accepted and e.stage not in SCREEN_SKIP[1:]]
            if not cand or first is None:
                print("nothing to report: no accepted evaluation in the log")
                return
            best = min(cand, key=lambda e: e.score)
            self.best, self.baseline = best, first
            self._write(dict(best.values), best, first)
            return
        ranked: List[Evaluation] = []
        seen = set()
        for ev in sorted((e for e in self.history if e.accepted and e.stage not in SCREEN_SKIP), key=lambda e: e.score):
            k = json.dumps(sorted(ev.values.items()), default=str)
            if k not in seen and ev.values != self.start:
                seen.add(k)
                ranked.append(ev)
        ranked = ranked[:max(0, a.validate_top)]
        winner_vals, winner, base_v = dict(self.start), None, None
        if ranked:
            self.say(f"validation of the best {len(ranked)} at fidelity {a.validate_steps or 'full'} ...")
            ev_v, base_v = self._prepare(a.validate_steps, self.cases)
            self._record(base_v, "validation_baseline")
            winner = base_v
            for c in ranked:
                v = ev_v.evaluate(c.values, use_cache=False)
                self._record(v, "validation")
                self.say(f"   candidate #{c.index}: {self.summary(v)}")
                if v.accepted and v.score < winner.score:
                    winner, winner_vals = v, dict(c.values)
            if winner is base_v:
                self.say("no candidate beats the starting setting on the validation run")
        else:
            winner, winner_vals, base_v = self.best, dict(self.best.values), self.baseline
        self._write(winner_vals, winner, base_v)

    # --- results --------------------------------------------------------------------------------------------------
    @staticmethod
    def _nested(values: Values) -> dict:
        out: dict = {}
        for k, v in values.items():
            d = out
            parts = k.split(".")
            for p in parts[:-1]:
                d = d.setdefault(p, {})
            d[parts[-1]] = v
        return out

    def _write(self, values: Values, winner: Evaluation, base: Evaluation) -> None:
        a, out, e = self.args, self.out, self.experiment
        yaml.safe_dump(self._nested(values), open(out / "best_config.yaml", "w"), sort_keys=False)
        (out / "best_overrides.txt").write_text(e.overrides_text(values) + "\n")
        changed = [(k, self.start.get(k, "<unset>"), values.get(k, "<unset>")) for k in sorted(set(self.start) | set(values))
                   if self.start.get(k) != values.get(k)]
        L = [f"{self.spec.name} tuning ({self.method}) on {e.name}  {datetime.now():%Y-%m-%d %H:%M}",
             f"objective {a.objective}; screening cases {[str(c) for c in self.cases]}, fidelity {a.steps or 'full'}; "
             f"validation fidelity {a.validate_steps or 'full'}",
             f"evaluations {len(self.history)} ({sum(x.accepted for x in self.history)} accepted), experiment runs "
             f"{self.evaluator.n_runs if self.evaluator else '-'}, time {(time.time() - self.t0) / 60:.1f} min", "",
             "changes w.r.t. the starting setting:"]
        L += [f"  {k}: {o} -> {n}" for k, o, n in changed] or ["  (none: no candidate beat the starting setting)"]
        L += ["", "per case (starting setting -> best):"]
        for c in self.cases:
            b, w = base.per_case.get(c), winner.per_case.get(c)
            if b and w and b.ok and w.ok:
                parts = [f"{col.header} {col.fmt.format(b.get(col.metric))} -> {col.fmt.format(w.get(col.metric))}"
                         for col in e.columns]
                L.append(f"  {e.case_label(c):<6} " + "; ".join(parts) + e.reference_note(c, w))
        if self.promoted:
            L += ["", "full-length tests of promoted candidates:"] + [f"  #{p.index}: {self.summary(p)}" for p in self.promoted]
        (out / "report.txt").write_text("\n".join(L) + "\n")
        print("\n" + "\n".join(L) + f"\n\nbest_config.yaml: {out / 'best_config.yaml'}", flush=True)
