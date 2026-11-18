#!/usr/bin/env python3
"""Bayesian optimisation (Optuna TPE) of the barrier IPM (BIPM, ref. [6] of the paper) on the Fig. 2 closed loop.

Same evaluation, objective and promotion rule as tune_bipm.py:
  * screening: `macc_run --solvers ispd,bipm --init feasible` at --horizon (default 30) for --steps MPC steps, ISPD drives
    the plant;
  * objective `paper`: match the paper's BIPM (Table V: N = 30 mean 37.9 iterations, min 25);
    objective `fast`: fewest iterations (with penalties for steps at the 120 limit and large equality residuals);
  * when a trial is MUCH better than the reference (--promote-gain, default 10 %), the FULL driving cycle is run on
    --full-horizons; if it confirms the gain, it becomes the new reference.
Instead of changing one option at a time, the sampler proposes all options together and learns from the scores
(bipm_settings.kappa_initial / kappa_final / kappa_update_factor on log scales; with --include-shared also the cg2o options
that ISPD shares, which changes the ISPD driver trajectory as well).

    python3 experiments/tune_bipm_bo.py --trials 80 --steps 300                       # paper objective
    python3 experiments/tune_bipm_bo.py --objective fast --trials 120 --full-horizons 3 15 30
    python3 experiments/tune_bipm_bo.py --resume results/tuning/<folder>              # continue a stopped study
Results: results/tuning/<timestamp>_bipm_bo/ (study.db, trials.csv, log.jsonl, report.txt, best_config.yaml).
config/ is not modified.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune_bipm as base  # noqa: E402  (Tuner, load_paper, line: identical evaluation)
from macc_exp.paths import ROOT, find_binary  # noqa: E402

import optuna  # noqa: E402
import yaml  # noqa: E402

# name -> ("log", lo, hi) | ("float", lo, hi) | ("int", lo, hi) | ("cat", [values])
RANGES = {
    "bipm_settings.kappa_initial": ("log", 1e-3, 100.0),
    "bipm_settings.kappa_final": ("log", 100.0, 2e4),
    "bipm_settings.kappa_update_factor": ("log", 1.5, 50.0),
}
SHARED = {  # also used by ISPD (the driver)
    "general_settings.num_inner_iterations_max": ("int", 1, 20),
    "cg2o.epsilon_convergence": ("log", 1e-5, 1e-1),
    "cg2o.termination_criterion": ("cat", [0, 1, 2]),
    "cg2o.equality_regularization": ("cat", [0.0, 1e-8, 1e-6]),
}
DEFAULTS = {  # used for the first trial when the config does not set the option
    "general_settings.num_inner_iterations_max": 10, "cg2o.epsilon_convergence": 1e-2,
    "cg2o.termination_criterion": 1, "cg2o.equality_regularization": 0.0,
}
REJECTED_VALUE = 10.0


def r3(v: float) -> float:
    return float(f"{v:.3g}")


def suggest(trial: optuna.Trial, name: str, spec):
    kind = spec[0]
    if kind == "cat":
        return trial.suggest_categorical(name, spec[1])
    if kind == "int":
        return trial.suggest_int(name, spec[1], spec[2])
    if kind == "float":
        return r3(trial.suggest_float(name, spec[1], spec[2]))
    return r3(trial.suggest_float(name, spec[1], spec[2], log=True))


def snap(v, spec):
    kind = spec[0]
    if kind == "cat":
        return v if v in spec[1] else None
    if kind == "int":
        return int(min(max(int(v), spec[1]), spec[2]))
    return min(max(float(v), spec[1]), spec[2])


def cfg_get(cfg: dict, dotted: str):
    d = cfg
    for part in dotted.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=ROOT / "config" / "config.yaml")
    p.add_argument("--objective", choices=["paper", "fast"], default="paper")
    p.add_argument("--horizon", type=int, default=30, help="horizon of the screening runs")
    p.add_argument("--steps", type=int, default=300, help="MPC steps of a screening run")
    p.add_argument("--full-horizons", type=int, nargs="+", default=[30])
    p.add_argument("--full-steps", type=int, default=0, help="steps of the full test (0 = whole driving cycle)")
    p.add_argument("--promote-gain", type=float, default=0.10)
    p.add_argument("--trials", type=int, default=80)
    p.add_argument("--startup", type=int, default=15, help="random trials before the model is used")
    p.add_argument("--include-shared", action="store_true")
    p.add_argument("--n-jobs", type=int, default=3, help="trials evaluated at the same time")
    p.add_argument("--max-cost-gap", type=float, default=1e-3, help="reject if the MEDIAN relative cost gap to ISPD exceeds this")
    p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--keep", action="store_true")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--resume", type=Path, default=None)
    a = p.parse_args()
    a.jobs = a.n_jobs

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    binary = find_binary()
    if a.resume:
        out = a.resume
    else:
        out = ROOT / "results" / "tuning" / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_bipm_bo")
        (out / "runs").mkdir(parents=True)
    paper = base.load_paper()
    cfg = yaml.safe_load(open(a.config))
    ranges = dict(RANGES, **(SHARED if a.include_shared else {}))
    start = {}
    for k in ranges:
        v = cfg_get(cfg, k)
        start[k] = v if v is not None else DEFAULTS.get(k)
    tuner = base.Tuner(a, binary, out / "runs", paper)
    log = open(out / "log.jsonl", "a")
    t0 = time.time()
    lock = threading.Lock()

    print(f"output: {out}\nobjective {a.objective}, screening N={a.horizon}, {a.steps} steps; paper {paper.get(a.horizon)}")
    base_res = tuner.screen(start)
    tuner.base_iter = base_res["stats"].get("iter")
    base_res["score"] = tuner.score(base_res["stats"], a.horizon, baseline=True)
    print("starting setting ", base.line(base_res), flush=True)
    state = {"reference": base_res["score"], "base_full": None, "promoted": []}

    def objective(trial: optuna.Trial) -> float:
        opts = {k: suggest(trial, k, ranges[k]) for k in ranges}
        res = tuner.screen(opts)
        trial.set_user_attr("options", json.dumps(opts))
        s = res["stats"]
        trial.set_user_attr("stats", json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()}, default=str))
        log.write(json.dumps({"stage": "bo", "trial": trial.number, **res}, default=str) + "\n")
        log.flush()
        return REJECTED_VALUE if not math.isfinite(res["score"]) else res["score"]

    def promote(study_, trial):
        if trial.value is None or trial.value >= REJECTED_VALUE:
            return
        with lock:
            if study_.best_trial.number == trial.number:
                print(f"[trial {trial.number:4d}] new best  score {trial.value:.3f}   {trial.params}   "
                      f"({(time.time() - t0) / 60:.1f} min)", flush=True)
            if trial.value > state["reference"] * (1 - a.promote_gain):
                return
            print(f"   -> much better than the reference ({trial.value:.3f} vs {state['reference']:.3f}): full test ...",
                  flush=True)
            if state["base_full"] is None:
                state["base_full"] = tuner.full(start, "full_base", baseline=True)
                log.write(json.dumps({"stage": "full_baseline", **state["base_full"]}, default=str) + "\n")
                print(f"   full baseline score {state['base_full']['score']:.3f}", flush=True)
            opts = json.loads(trial.user_attrs["options"])
            f = tuner.full(opts, f"full_t{trial.number}")
            log.write(json.dumps({"stage": "full", "trial": trial.number, **f}, default=str) + "\n")
            log.flush()
            state["promoted"].append(f)
            per = "  ".join(f"N={n}: it {r['iter']:.1f} limit {100 * r['hit']:.1f}%" if r["ok"] else f"N={n}: failed"
                            for n, r in f["per_horizon"].items())
            print(f"   full test score {f['score']:.3f} (baseline {state['base_full']['score']:.3f})  {per}", flush=True)
            if f["score"] < state["base_full"]["score"]:
                state["reference"] = trial.value

    study = optuna.create_study(
        study_name="bipm", direction="minimize", storage=f"sqlite:///{out / 'study.db'}", load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=a.seed, multivariate=True, n_startup_trials=a.startup,
                                           constant_liar=a.n_jobs > 1))
    if not study.trials:  # first trial = the current config
        enq = {k: snap(v, ranges[k]) for k, v in start.items() if v is not None}
        study.enqueue_trial({k: v for k, v in enq.items() if v is not None})
    done = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
    todo = max(0, a.trials - done)
    print(f"{done} trials done, running {todo} more (n_jobs={a.n_jobs}, startup {a.startup})", flush=True)
    study.optimize(objective, n_trials=todo, n_jobs=a.n_jobs, callbacks=[promote])
    study.trials_dataframe().to_csv(out / "trials.csv", index=False)

    ok = [t for t in study.trials if t.value is not None and t.value < REJECTED_VALUE]
    best_t = min(ok, key=lambda t: t.value) if ok else None
    if best_t is not None:
        best_opts = json.loads(best_t.user_attrs["options"])
        if not state["promoted"] or state["promoted"][-1]["options"] != best_opts:  # best trial not fully tested yet
            if state["base_full"] is None:
                state["base_full"] = tuner.full(start, "full_base", baseline=True)
            f = tuner.full(best_opts, "full_best")
            log.write(json.dumps({"stage": "full", "trial": best_t.number, **f}, default=str) + "\n")
            state["promoted"].append(f)
    cands = state["promoted"] + ([state["base_full"]] if state["base_full"] else [])
    winner = min(cands, key=lambda r: r["score"]) if cands else None
    lines = [f"BIPM Bayesian optimisation ({a.objective}) {datetime.now():%Y-%m-%d %H:%M}",
             f"screening: N={a.horizon}, {a.steps} steps; full test: horizons {a.full_horizons}, "
             f"{a.full_steps or 'whole'} steps",
             f"trials {len(study.trials)} ({len(ok)} accepted), time {(time.time() - t0) / 60:.1f} min", ""]
    if winner:
        lines.append("best configuration (full cycle):")
        lines += [f"  {k}: {v}" for k, v in winner["options"].items()]
        lines.append("")
        for n in a.full_horizons:
            for tag, res in (("start", state["base_full"]), ("best ", winner)):
                r = res["per_horizon"][n] if res else None
                if r and r["ok"]:
                    pp = paper.get(n, {})
                    lines.append(f"  N={n:<3} {tag}: iterations {r['iter']:.1f} (min {r['iter_min']:.0f}, max {r['iter_max']:.0f}), "
                                 f"steps at the limit {100 * r['hit']:.1f}%, eq residual > 1e-3 in {100 * r['bad_eq']:.1f}%, "
                                 f"cost gap to ISPD {r['gap']:.1e}   [paper: {pp.get('iter_avg', '-')} / "
                                 f"{pp.get('iter_min', '-')} / {pp.get('iter_max', '-')}]")
        cfgout = {}
        for k, v in winner["options"].items():
            d = cfgout
            parts = k.split(".")
            for part in parts[:-1]:
                d = d.setdefault(part, {})
            d[parts[-1]] = v
        yaml.safe_dump(cfgout, open(out / "best_config.yaml", "w"), sort_keys=False)
    open(out / "report.txt", "w").write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines) + f"\n\nbest_config.yaml: {out / 'best_config.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
