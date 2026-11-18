#!/usr/bin/env python3
"""Automatic tuning of the native IPOPT options for the COLD start (initial guess 10 at every step).

Every candidate is evaluated in the closed loop `--solvers ispd,ipopt` (ISPD drives the plant, so IPOPT solves exactly
the same NLPs as in the experiments) on a few horizons. Score = mean over the horizons of
    iterations(candidate) / iterations(baseline)  +  2 * (fraction of steps that hit the iteration limit)
(lower is better). A candidate is REJECTED (score = inf) if the solution gets worse:
    * mean relative cost gap to ISPD above --max-cost-gap, or
    * max equality residual / inequality violation above --feasibility, or
    * non-finite numbers, or IPOPT failed (success = 0) in more than --max-fail of the steps.

Search = coordinate descent over the SPACE below (--passes sweeps, every value of every option is tried while the others
stay at the best setting found so far), followed by --random perturbations of the best setting. Everything is logged
to results/tuning/<timestamp>/ (log.jsonl, best_options.yaml, report.txt); nothing in config/ is changed.

    python3 experiments/tune_ipopt_cold.py --steps 300                  # about 20-40 min on 8 cores
    python3 experiments/tune_ipopt_cold.py --steps 300 --params mu_strategy,mu_init,bound_push --passes 1
    python3 experiments/tune_ipopt_cold.py --validate-steps 0            # at the end: best setting on the full cycle
Then copy best_options.yaml into ipopt_settings.options of config/config.yaml (or try it with --set ... first).
Iteration counts do not depend on the machine load, so the candidates run in parallel (--jobs); do NOT quote the
milliseconds of these runs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from macc_exp.paths import ROOT, find_binary  # noqa: E402

import yaml  # noqa: E402

# option -> values tried. The IPOPT default is NOT necessarily in the list: the starting value comes from config.yaml.
SPACE = {
    # --- termination (the real stopping test is tol AND constr_viol_tol AND dual_inf_tol AND compl_inf_tol)
    "tol": [1e-2, 1e-3, 1e-4, 1e-5, 1e-6],
    "constr_viol_tol": [1e-5, 1e-4, 1e-3],
    "compl_inf_tol": [1e-4, 1e-3, 1e-2],
    "dual_inf_tol": [1, 1e2, 1e4],
    "acceptable_tol": [1e-6, 1e-4, 1e-3, 1e-2],
    "acceptable_iter": [15, 5, 2, 1],
    # --- barrier parameter
    "mu_strategy": ["monotone", "adaptive"],
    "adaptive_mu_globalization": ["obj-constr-filter", "kkt-error", "never-monotone-mode"],
    "mu_oracle": ["quality-function", "probing", "loqo"],
    "mu_init": [1e-3, 1e-2, 0.1, 1.0, 10.0, 100.0, 1000.0],
    "mu_min": [1e-11, 1e-9, 1e-7],
    "mu_target": [0.0, 1e-4],
    "barrier_tol_factor": [1, 3, 10, 30, 100],
    "mu_linear_decrease_factor": [0.05, 0.1, 0.2, 0.5],
    "mu_superlinear_decrease_power": [1.2, 1.5, 1.8],
    "tau_min": [0.9, 0.99, 0.999],
    "kappa_sigma": [1e10, 1e4, 1e2],
    # --- initialization
    "bound_push": [1e-6, 1e-4, 1e-2, 1e-1, 1.0],
    "bound_frac": [1e-6, 1e-4, 1e-2, 1e-1, 0.5],
    "slack_bound_push": [1e-4, 1e-2, 1e-1, 1.0],
    "bound_mult_init_method": ["constant", "mu-based"],
    "bound_mult_init_val": [1e-2, 1.0, 1e2],
    "constr_mult_init_max": [0.0, 1.0, 1e3],
    "least_square_init_duals": ["no", "yes"],
    # --- scaling
    "nlp_scaling_method": ["none", "gradient-based", "equilibration-based"],
    "nlp_scaling_max_gradient": [10, 100, 1000],
    # --- line search / step computation
    "line_search_method": ["filter", "penalty"],
    "alpha_for_y": ["primal", "bound-mult", "min", "max", "full", "safer-min-dual-infeas"],
    "alpha_red_factor": [0.3, 0.5, 0.8],
    "max_soc": [0, 2, 4],
    "corrector_type": ["none", "affine", "primal-dual"],
    "watchdog_shortened_iter_trigger": [0, 10],
    "accept_every_trial_step": ["no", "yes"],
    "mehrotra_algorithm": ["no", "yes"],
    "fast_step_computation": ["no", "yes"],
    "min_refinement_steps": [0, 1],
    "max_refinement_steps": [3, 10],
    "required_infeasibility_reduction": [0.1, 0.5, 0.9],
    "theta_max_fact": [1e2, 1e4, 1e6],
    "obj_max_inc": [5, 50],
    "recalc_y": ["no", "yes"],
    "constraint_violation_norm_type": ["1-norm", "2-norm", "max-norm"],
    "first_hessian_perturbation": [1e-6, 1e-4, 1e-2],
    "jacobian_regularization_value": [1e-10, 1e-8, 1e-6],
}
def _valid(o: dict) -> bool:
    """Combinations that are meaningless are skipped (a hook; every combination is currently allowed)."""
    return True


def fmt(v) -> str:
    return v if isinstance(v, str) else repr(v) if isinstance(v, float) else str(v)


class Evaluator:
    def __init__(self, a, binary: Path, workdir: Path, base_options: dict):
        self.a, self.binary, self.workdir = a, binary, workdir
        self.base_options = base_options
        self.cache: dict[str, dict] = {}
        self.baseline_iter: dict[int, float] = {}
        self.n_eval = 0
        self._lock = threading.Lock()

    def run_one(self, options: dict, horizon: int, steps: int, tag: str) -> dict:
        cmd = [str(self.binary), "--config", str(self.a.config), "--solvers", "ispd,ipopt", "--driver", "ispd",
               "--horizon", str(horizon), "--init", "fixed", "--label", tag,
               "--set", f"experiment.output_dir={self.workdir}", "--set", "experiment.progress_every=100000"]
        if steps:
            cmd += ["--loop-size", str(steps)]
        for k, v in options.items():
            cmd += ["--set", f"ipopt_settings.options.{k}={fmt(v)}"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.a.timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "why": "timeout"}
        out = r.stdout + r.stderr
        m = re.search(r"MACC run directory:\s*(\S+)", out)
        if r.returncode != 0 or not m:
            why = "setup error: " + (re.search(r"(Setup error|Invalid|not a valid).*", out) or [out[-120:]])[0][:150]
            return {"ok": False, "why": why}
        run_dir = Path(m.group(1))
        try:
            with open(run_dir / "steps.csv") as f:
                rows = list(csv.DictReader(f))
        finally:
            if not self.a.keep:
                shutil.rmtree(run_dir, ignore_errors=True)
        col = lambda k: [float(x[k]) for x in rows]  # noqa: E731
        it, cost, ref = col("ipopt_iterations"), col("ipopt_cost"), col("ispd_cost")
        eq, ineq = col("ipopt_eq_residual"), col("ipopt_ineq_violation")
        hit, succ = col("ipopt_hit_max_iter"), col("ipopt_success")
        finite = all(math.isfinite(v) for vs in (it, cost, eq, ineq) for v in vs)
        if not finite or not rows:
            return {"ok": False, "why": "non-finite numbers"}
        gap = statistics.mean(abs(c - r_) / max(abs(r_), 1e-12) for c, r_ in zip(cost, ref))
        return {"ok": True, "iter": statistics.mean(it), "iter_max": max(it), "hit": statistics.mean(hit),
                "fail": 1 - statistics.mean(succ), "gap": gap, "eq": max(eq), "ineq": max(ineq),
                "time_ms": statistics.mean(col("ipopt_time_ms"))}

    def evaluate(self, options: dict, steps: int | None = None, use_cache: bool = True) -> dict:
        steps = self.a.steps if steps is None else steps
        key = json.dumps([sorted(options.items(), key=lambda kv: kv[0]), steps], default=str)
        if use_cache and key in self.cache:
            return self.cache[key]
        with self._lock:
            self.n_eval += 1
            tag = f"tune{self.n_eval}"
        with ThreadPoolExecutor(max_workers=self.a.jobs) as ex:
            futs = {n: ex.submit(self.run_one, options, n, steps, f"{tag}_N{n}") for n in self.a.horizons}
            per = {n: f.result() for n, f in futs.items()}
        res = {"options": dict(options), "per_horizon": per, "steps": steps}
        bad = [f"N={n}: {r['why']}" for n, r in per.items() if not r["ok"]]
        if not bad:
            for n, r in per.items():
                if r["gap"] > self.a.max_cost_gap:
                    bad.append(f"N={n}: cost gap {r['gap']:.1e}")
                if max(r["eq"], r["ineq"]) > self.a.feasibility:
                    bad.append(f"N={n}: infeasible {max(r['eq'], r['ineq']):.1e}")
                if r["fail"] > self.a.max_fail:
                    bad.append(f"N={n}: {100 * r['fail']:.1f}% steps failed")
        if bad:
            res.update(score=math.inf, rejected="; ".join(bad))
        else:
            base = self.baseline_iter
            res["score"] = statistics.mean(per[n]["iter"] / base.get(n, per[n]["iter"]) + 2 * per[n]["hit"]
                                           for n in per)
            res["rejected"] = ""
        self.cache[key] = res
        return res


def describe(res: dict) -> str:
    per = res["per_horizon"]
    its = " / ".join(f"{per[n]['iter']:.1f}" if per[n].get("ok") else "-" for n in per)
    return f"score {res['score']:.3f}  it {its}" + (f"  REJECTED {res['rejected']}" if res["rejected"] else "")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=ROOT / "config" / "config.yaml")
    p.add_argument("--horizons", type=int, nargs="+", default=[3, 15, 30])
    p.add_argument("--steps", type=int, default=300, help="MPC steps per screening run (0 = full cycle)")
    p.add_argument("--passes", type=int, default=2, help="coordinate-descent sweeps")
    p.add_argument("--random", type=int, default=30, help="random perturbations of the best setting afterwards")
    p.add_argument("--params", default="", help="comma list: restrict the search to these options (default: all in SPACE)")
    p.add_argument("--start", default="config", choices=["config", "ipopt-default"],
                   help="config: start from ipopt_settings.options of the config; ipopt-default: from an empty list")
    p.add_argument("--jobs", type=int, default=3, help="parallel runs (one per horizon)")
    p.add_argument("--max-cost-gap", type=float, default=1e-4, help="reject if mean relative cost gap to ISPD exceeds this")
    p.add_argument("--feasibility", type=float, default=1e-4)
    p.add_argument("--max-fail", type=float, default=0.02, help="reject if more steps than this fraction fail")
    p.add_argument("--min-gain", type=float, default=0.005, help="a change must lower the score by this much")
    p.add_argument("--validate-top", type=int, default=3)
    p.add_argument("--validate-steps", type=int, default=1500, help="steps of the final validation (0 = full cycle)")
    p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--keep", action="store_true", help="keep the run folders of the candidates")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()

    binary = find_binary()
    out = ROOT / "results" / "tuning" / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_ipopt_cold")
    out.mkdir(parents=True)
    work = out / "runs"
    work.mkdir()
    cfg = yaml.safe_load(open(a.config))
    base_opts = {} if a.start == "ipopt-default" else dict(cfg["ipopt_settings"]["options"])
    base_opts.pop("max_iter", None)
    # fixed: printing, banner, linear solver (compare linear solvers with the ipopt-linear-solvers preset)
    fixed = {k: base_opts[k] for k in ("print_level", "sb", "linear_solver") if k in base_opts}
    if a.start == "ipopt-default":
        fixed.update(print_level=0, sb="yes", linear_solver=cfg["ipopt_settings"]["options"].get("linear_solver", "mumps"))
    ev = Evaluator(a, binary, work, base_opts)
    rng = random.Random(a.seed)
    log = open(out / "log.jsonl", "w")
    t0 = time.time()

    def record(stage, name, res):
        log.write(json.dumps({"stage": stage, "change": name, **res}, default=str) + "\n")
        log.flush()

    print(f"output: {out}\nstart: {a.start}, horizons {a.horizons}, {a.steps or 'all'} steps, jobs {a.jobs}")
    best_opts = dict(base_opts)
    # baseline: also defines the normalisation of the iteration counts
    first = ev.evaluate(best_opts)
    for n, r in first["per_horizon"].items():
        if r["ok"]:
            ev.baseline_iter[n] = r["iter"]
    ev.cache.clear()
    best = ev.evaluate(best_opts)
    record("baseline", "-", best)
    print(f"baseline  {describe(best)}")
    if best["score"] == math.inf:
        print("the baseline is rejected; relax --max-cost-gap / --feasibility or check the config", file=sys.stderr)

    names = [n for n in (a.params.split(",") if a.params else list(SPACE)) if n]
    unknown = [n for n in names if n not in SPACE]
    if unknown:
        print("unknown options (not in SPACE):", unknown, file=sys.stderr)
        return 2
    for sweep in range(1, a.passes + 1):
        improved = False
        for name in names:
            tried = []
            for v in SPACE[name]:
                if best_opts.get(name) == v:
                    continue
                cand = dict(best_opts)
                cand[name] = v
                if not _valid(cand):
                    continue
                res = ev.evaluate(cand)
                record(f"pass{sweep}", f"{name}={v}", res)
                tried.append((res["score"], v, res))
            if not tried:
                continue
            score, v, res = min(tried, key=lambda t: t[0])
            if score < best["score"] - a.min_gain:
                best_opts[name], best, improved = v, res, True
                print(f"[pass {sweep}] {name} = {v}  ->  {describe(best)}   ({(time.time() - t0) / 60:.1f} min)", flush=True)
            else:
                print(f"[pass {sweep}] {name}: no gain (best of {len(tried)} tried: {score:.3f} vs {best['score']:.3f})", flush=True)
        if not improved:
            break

    for i in range(a.random):
        cand = dict(best_opts)
        for name in rng.sample(names, k=min(len(names), rng.choice([2, 3, 4]))):
            cand[name] = rng.choice(SPACE[name])
        if cand == best_opts or not _valid(cand):
            continue
        res = ev.evaluate(cand)
        record("random", "perturbation", res)
        if res["score"] < best["score"] - a.min_gain:
            best_opts, best = cand, res
            print(f"[random {i + 1}] new best  {describe(best)}", flush=True)

    # final: the best few distinct candidates on a longer run
    ranked = sorted({json.dumps(r["options"], sort_keys=True, default=str): r for r in ev.cache.values()
                     if r["score"] < math.inf}.values(), key=lambda r: r["score"])[:max(1, a.validate_top)]
    print(f"\nvalidation of the best {len(ranked)} on {a.validate_steps or 'all'} steps ...", flush=True)
    ev.baseline_iter = {}
    base_val = ev.evaluate(dict(base_opts), a.validate_steps, use_cache=False)
    for n, r in base_val["per_horizon"].items():
        if r["ok"]:
            ev.baseline_iter[n] = r["iter"]
    base_val = ev.evaluate(dict(base_opts), a.validate_steps, use_cache=False)
    validated = []
    for r in ranked:
        v = ev.evaluate(r["options"], a.validate_steps, use_cache=False)
        record("validation", "-", v)
        validated.append(v)
        print("  ", describe(v), flush=True)
    winner = min(validated, key=lambda r: r["score"]) if validated else base_val
    if winner["score"] >= base_val["score"]:
        winner = base_val
        print("no candidate beats the starting setting on the validation run")
    final = {**fixed, **{k: v for k, v in winner["options"].items() if k not in fixed}}
    with open(out / "best_options.yaml", "w") as f:
        f.write("# best IPOPT options for the cold start (tune_ipopt_cold.py); paste under ipopt_settings: options:\n"
                "options:\n")
        for k, v in final.items():
            f.write(f"  {k}: {chr(34) + v + chr(34) if v in ('yes', 'no') else fmt(v)}\n")
    lines = [f"IPOPT cold-start tuning  {datetime.now():%Y-%m-%d %H:%M}",
             f"horizons {a.horizons}, screening steps {a.steps or 'all'}, validation steps {a.validate_steps or 'all'}",
             f"evaluations: {ev.n_eval}, time {(time.time() - t0) / 60:.1f} min", "",
             "changes w.r.t. the starting setting:"]
    changed = {k: (base_opts.get(k, "<ipopt default>"), v) for k, v in winner["options"].items()
               if base_opts.get(k) != v}
    lines += [f"  {k}: {o} -> {n}" for k, (o, n) in changed.items()] or ["  (none)"]
    lines += ["", "mean iterations per step (start -> best):"]
    for n in a.horizons:
        b, w = base_val["per_horizon"][n], winner["per_horizon"][n]
        if b.get("ok") and w.get("ok"):
            lines.append(f"  N={n:<3} {b['iter']:.1f} -> {w['iter']:.1f}   steps at the limit {100 * b['hit']:.1f}% -> "
                         f"{100 * w['hit']:.1f}%   mean cost gap to ISPD {b['gap']:.1e} -> {w['gap']:.1e}")
    open(out / "report.txt", "w").write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines) + f"\n\nbest_options.yaml: {out / 'best_options.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
