#!/usr/bin/env python3
"""Bayesian optimisation (Optuna TPE, multivariate, with the current config as first trial) of the IPOPT options.

Same evaluation as tune_ipopt_cold.py (cold start, `--solvers ispd,ipopt`, ISPD drives the plant, the same score and the
same rejection rules: cost gap to ISPD, feasibility, failed steps), but instead of changing one option at a time all
options are sampled together from continuous / integer / categorical ranges, so interactions (e.g. mu_strategy x mu_init x
bound_push) are found. The sampler models which regions of the space gave a low score and proposes the next trial there.

    python3 experiments/tune_ipopt_bo.py --trials 300 --steps 200            # about 1-2 h on 8 cores
    python3 experiments/tune_ipopt_bo.py --trials 40 --steps 100 --horizons 15 30    # quick try
    python3 experiments/tune_ipopt_bo.py --resume results/tuning/<folder>      # continue a stopped study

The study is stored in <folder>/study.db (SQLite), so it can be stopped and resumed. At the end the best --validate-top
trials are re-run on --validate-steps steps (0 = full cycle) against the starting setting.
Results: results/tuning/<timestamp>_ipopt_bo/ (best_options.yaml, report.txt, trials.csv). config/ is not modified.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune_ipopt_cold as base  # noqa: E402  (Evaluator, describe, fmt: identical evaluation)
from macc_exp.paths import ROOT, find_binary  # noqa: E402

import optuna  # noqa: E402
import yaml  # noqa: E402

# name -> ("log", lo, hi) | ("float", lo, hi) | ("int", lo, hi) | ("cat", [values]) | ("one_minus_log", lo, hi)
# (one_minus_log: the option is 1 - x with x log-uniform in [lo, hi], e.g. tau_min close to 1)
RANGES = {
    "tol": ("log", 1e-6, 1e-2),
    "constr_viol_tol": ("log", 1e-5, 1e-2),
    "compl_inf_tol": ("log", 1e-5, 1e-1),
    "dual_inf_tol": ("log", 1.0, 1e4),
    "acceptable_tol": ("log", 1e-8, 1e-1),
    "acceptable_iter": ("int", 0, 15),
    "mu_strategy": ("cat", ["monotone", "adaptive"]),
    "adaptive_mu_globalization": ("cat", ["obj-constr-filter", "kkt-error", "never-monotone-mode"]),
    "mu_oracle": ("cat", ["quality-function", "probing", "loqo"]),
    "mu_init": ("log", 1e-4, 1e3),
    "mu_min": ("log", 1e-11, 1e-4),
    "barrier_tol_factor": ("log", 1.0, 100.0),
    "mu_linear_decrease_factor": ("float", 0.02, 0.8),
    "mu_superlinear_decrease_power": ("float", 1.1, 1.95),
    "tau_min": ("one_minus_log", 1e-4, 1e-1),
    "kappa_sigma": ("log", 1e2, 1e12),
    "bound_push": ("log", 1e-6, 1.0),
    "bound_frac": ("log", 1e-6, 0.5),
    "slack_bound_push": ("log", 1e-6, 1.0),
    "slack_bound_frac": ("log", 1e-6, 0.5),
    "bound_mult_init_method": ("cat", ["constant", "mu-based"]),
    "bound_mult_init_val": ("log", 1e-3, 1e3),
    "constr_mult_init_max": ("cat", [0.0, 1.0, 10.0, 100.0, 1000.0, 10000.0]),
    "least_square_init_duals": ("cat", ["no", "yes"]),
    "nlp_scaling_method": ("cat", ["none", "gradient-based", "equilibration-based"]),
    "nlp_scaling_max_gradient": ("log", 1.0, 1e4),
    "line_search_method": ("cat", ["filter", "penalty"]),
    "alpha_for_y": ("cat", ["primal", "bound-mult", "min", "max", "full", "safer-min-dual-infeas"]),
    "alpha_red_factor": ("float", 0.1, 0.9),
    "max_soc": ("int", 0, 6),
    "corrector_type": ("cat", ["none", "affine", "primal-dual"]),
    "watchdog_shortened_iter_trigger": ("int", 0, 20),
    "accept_every_trial_step": ("cat", ["no", "yes"]),
    "mehrotra_algorithm": ("cat", ["no", "yes"]),
    "fast_step_computation": ("cat", ["no", "yes"]),
    "min_refinement_steps": ("int", 0, 2),
    "max_refinement_steps": ("int", 1, 10),
    "required_infeasibility_reduction": ("float", 0.01, 0.99),
    "theta_max_fact": ("log", 10.0, 1e8),
    "obj_max_inc": ("log", 1.5, 100.0),
    "recalc_y": ("cat", ["no", "yes"]),
    "constraint_violation_norm_type": ("cat", ["1-norm", "2-norm", "max-norm"]),
    "first_hessian_perturbation": ("log", 1e-8, 1.0),
    "jacobian_regularization_value": ("log", 1e-12, 1e-4),
}
# IPOPT 3.14 defaults, used for the first trial (= the starting setting) when the config does not set an option.
# linear_system_scaling stays unset (the default mc19 needs HSL).
DEFAULTS = {
    "tol": 1e-8, "constr_viol_tol": 1e-4, "compl_inf_tol": 1e-4, "dual_inf_tol": 1.0, "acceptable_tol": 1e-6,
    "acceptable_iter": 15, "mu_strategy": "monotone", "adaptive_mu_globalization": "obj-constr-filter",
    "mu_oracle": "quality-function", "mu_init": 0.1, "mu_min": 1e-11, "barrier_tol_factor": 10.0,
    "mu_linear_decrease_factor": 0.2, "mu_superlinear_decrease_power": 1.5, "tau_min": 0.99, "kappa_sigma": 1e10,
    "bound_push": 0.01, "bound_frac": 0.01, "slack_bound_push": 0.01, "slack_bound_frac": 0.01,
    "bound_mult_init_method": "constant", "bound_mult_init_val": 1.0, "constr_mult_init_max": 1000.0,
    "least_square_init_duals": "no", "nlp_scaling_method": "gradient-based", "nlp_scaling_max_gradient": 100.0,
    "line_search_method": "filter", "alpha_for_y": "primal", "alpha_red_factor": 0.5, "max_soc": 4,
    "corrector_type": "none", "watchdog_shortened_iter_trigger": 10, "accept_every_trial_step": "no",
    "mehrotra_algorithm": "no", "fast_step_computation": "no", "min_refinement_steps": 1, "max_refinement_steps": 10,
    "required_infeasibility_reduction": 0.9, "theta_max_fact": 1e4, "obj_max_inc": 5.0, "recalc_y": "no",
    "constraint_violation_norm_type": "1-norm", "first_hessian_perturbation": 1e-4,
    "jacobian_regularization_value": 1e-8,
}
# options whose default is computed from other options when unset (mu_min: 0.5 * min(tol, compl_inf_tol) / (barrier_tol_factor + 1)):
# the sampler may also leave them unset (parameter "<name>__set")
OPTIONAL = {"mu_min", "constr_mult_init_max"}   # constr_mult_init_max: setting it explicitly to its default 1000 changes the result
REJECTED_VALUE = 10.0  # score given to a rejected candidate (a normal good score is about 0.6 - 1.0)


def r3(v: float) -> float:
    return float(f"{v:.3g}")


def suggest(trial: optuna.Trial, name: str, spec) -> object:
    kind = spec[0]
    if kind == "cat":
        return trial.suggest_categorical(name, spec[1])
    if kind == "int":
        return trial.suggest_int(name, spec[1], spec[2])
    if kind == "float":
        return r3(trial.suggest_float(name, spec[1], spec[2]))
    if kind == "log":
        return r3(trial.suggest_float(name, spec[1], spec[2], log=True))
    if kind == "one_minus_log":
        return round(1.0 - r3(trial.suggest_float(name, spec[1], spec[2], log=True)), 6)
    raise ValueError(kind)


def snap(name: str, v, spec):
    """Map a value of the config onto the sampler's space (used to enqueue the starting setting)."""
    kind = spec[0]
    if kind == "cat":
        return v if v in spec[1] else None
    if kind == "int":
        return int(min(max(int(v), spec[1]), spec[2]))
    if kind == "one_minus_log":
        return min(max(1.0 - float(v), spec[1]), spec[2])
    return min(max(float(v), spec[1]), spec[2])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=ROOT / "config" / "config.yaml")
    p.add_argument("--horizons", type=int, nargs="+", default=[3, 15, 30])
    p.add_argument("--steps", type=int, default=200, help="MPC steps per screening run (0 = full cycle)")
    p.add_argument("--trials", type=int, default=300)
    p.add_argument("--startup", type=int, default=40, help="random trials before the model is used")
    p.add_argument("--params", default="", help="comma list: only these options (default: all in RANGES)")
    p.add_argument("--n-jobs", type=int, default=2, help="trials evaluated at the same time (each uses --jobs processes)")
    p.add_argument("--jobs", type=int, default=3, help="parallel runs inside one trial (one per horizon)")
    p.add_argument("--max-cost-gap", type=float, default=1e-4)
    p.add_argument("--feasibility", type=float, default=1e-4)
    p.add_argument("--max-fail", type=float, default=0.02)
    p.add_argument("--validate-top", type=int, default=3)
    p.add_argument("--validate-steps", type=int, default=1500)
    p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--keep", action="store_true")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--resume", type=Path, default=None, help="continue the study of an earlier folder")
    a = p.parse_args()

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    binary = find_binary()
    if a.resume:
        out = a.resume
    else:
        out = ROOT / "results" / "tuning" / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_ipopt_bo")
        (out / "runs").mkdir(parents=True)
    cfg = yaml.safe_load(open(a.config))
    start_opts = dict(cfg["ipopt_settings"]["options"])
    start_opts.pop("max_iter", None)
    fixed = {k: start_opts[k] for k in ("print_level", "sb", "linear_solver") if k in start_opts}
    names = [n for n in (a.params.split(",") if a.params else list(RANGES)) if n]
    bad = [n for n in names if n not in RANGES]
    if bad:
        print("unknown options:", bad, file=sys.stderr)
        return 2

    ev = base.Evaluator(a, binary, out / "runs", start_opts)
    t0 = time.time()
    # normalisation: iterations of the starting setting
    first = ev.evaluate(start_opts)
    for n, r in first["per_horizon"].items():
        if r["ok"]:
            ev.baseline_iter[n] = r["iter"]
    ev.cache.clear()
    base_res = ev.evaluate(start_opts)
    print(f"output: {out}\nstarting setting  {base.describe(base_res)}", flush=True)

    study = optuna.create_study(
        study_name="ipopt_cold", direction="minimize", storage=f"sqlite:///{out / 'study.db'}", load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=a.seed, multivariate=True, group=True, n_startup_trials=a.startup,
                                           constant_liar=a.n_jobs > 1))
    if not study.trials:  # first trial = the current config, so the model knows where we are
        enq = {n: snap(n, start_opts.get(n, DEFAULTS[n]), RANGES[n]) for n in names}
        for n in OPTIONAL:
            if n in names:
                enq[f"{n}__set"] = n in start_opts
        study.enqueue_trial({k: v for k, v in enq.items() if v is not None})

    def objective(trial: optuna.Trial) -> float:
        opts = dict(start_opts)
        for n in names:
            if n in OPTIONAL and not trial.suggest_categorical(f"{n}__set", [False, True]):
                opts.pop(n, None)
                continue
            opts[n] = suggest(trial, n, RANGES[n])
        res = ev.evaluate(opts, use_cache=False)
        trial.set_user_attr("options", json.dumps(opts, default=str))
        trial.set_user_attr("rejected", res["rejected"])
        trial.set_user_attr("iters", [round(r["iter"], 1) if r.get("ok") else None for r in res["per_horizon"].values()])
        return REJECTED_VALUE if not math.isfinite(res["score"]) else res["score"]

    def progress(study_, trial):
        if trial.value is not None and study_.best_trial.number == trial.number:
            print(f"[trial {trial.number:4d}] new best score {trial.value:.3f}  iterations {trial.user_attrs['iters']}"
                  f"   ({(time.time() - t0) / 60:.1f} min)", flush=True)

    done = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
    todo = max(0, a.trials - done)
    print(f"{done} trials done, running {todo} more (n_jobs={a.n_jobs}, startup {a.startup})", flush=True)
    study.optimize(objective, n_trials=todo, n_jobs=a.n_jobs, callbacks=[progress])

    df = study.trials_dataframe()
    df.to_csv(out / "trials.csv", index=False)
    ok = [t for t in study.trials if t.value is not None and t.value < REJECTED_VALUE]
    top = sorted(ok, key=lambda t: t.value)[:max(1, a.validate_top)]
    print(f"\nvalidation of the best {len(top)} on {a.validate_steps or 'all'} steps ...", flush=True)
    ev.baseline_iter = {}
    bv = ev.evaluate(dict(start_opts), a.validate_steps, use_cache=False)
    for n, r in bv["per_horizon"].items():
        if r["ok"]:
            ev.baseline_iter[n] = r["iter"]
    bv = ev.evaluate(dict(start_opts), a.validate_steps, use_cache=False)
    validated = []
    for t in top:
        o = json.loads(t.user_attrs["options"])
        v = ev.evaluate(o, a.validate_steps, use_cache=False)
        validated.append(v)
        print(f"   trial {t.number}: {base.describe(v)}", flush=True)
    winner = min(validated, key=lambda r: r["score"]) if validated else bv
    if winner["score"] >= bv["score"]:
        winner = bv
        print("no trial beats the starting setting on the validation run")
    final = {**fixed, **{k: v for k, v in winner["options"].items() if k not in fixed}}
    with open(out / "best_options.yaml", "w") as f:
        f.write("# best IPOPT options for the cold start (tune_ipopt_bo.py); paste under ipopt_settings: options:\n"
                "options:\n")
        for k, v in final.items():
            f.write(f"  {k}: {chr(34) + v + chr(34) if v in ('yes', 'no') else base.fmt(v)}\n")
    lines = [f"IPOPT cold-start Bayesian optimisation  {datetime.now():%Y-%m-%d %H:%M}",
             f"horizons {a.horizons}, screening steps {a.steps or 'all'}, validation steps {a.validate_steps or 'all'}",
             f"trials {len(study.trials)} ({len(ok)} accepted), time {(time.time() - t0) / 60:.1f} min", "",
             "changes w.r.t. the starting setting:"]
    ch = {k: (start_opts.get(k, "<ipopt default>"), v) for k, v in winner["options"].items() if start_opts.get(k) != v}
    lines += [f"  {k}: {o} -> {n}" for k, (o, n) in ch.items()] or ["  (none)"]
    lines += ["", "mean iterations per step (start -> best):"]
    for n in a.horizons:
        b, w = bv["per_horizon"][n], winner["per_horizon"][n]
        if b.get("ok") and w.get("ok"):
            lines.append(f"  N={n:<3} {b['iter']:.1f} -> {w['iter']:.1f}   steps at the limit {100 * b['hit']:.1f}% -> "
                         f"{100 * w['hit']:.1f}%   mean cost gap to ISPD {b['gap']:.1e} -> {w['gap']:.1e}")
    open(out / "report.txt", "w").write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines) + f"\n\nbest_options.yaml: {out / 'best_options.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
