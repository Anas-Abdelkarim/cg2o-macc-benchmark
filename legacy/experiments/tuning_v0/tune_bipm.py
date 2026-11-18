#!/usr/bin/env python3
"""Tuning of the barrier IPM (BIPM, ref. [6] of the paper) on the Fig. 2 closed loop.

Screening: every candidate runs `macc_run --solvers ispd,bipm --init feasible --horizon 30` for --steps MPC steps
(ISPD drives the plant, so BIPM solves the same NLPs as in the fig2 preset). Candidates of one option are evaluated in
parallel. When a candidate is MUCH better than the current reference (--promote-gain, default 10 % lower score), it is
promoted: the FULL driving cycle is run (all --full-horizons) and logged; if the full run confirms the gain it becomes the
new reference.

Objective (--objective):
    paper   make BIPM behave like the paper (Table V, N = 30: mean 37.9 iterations, min 25, max 120):
            score = |mean - 37.9| / 37.9 + 0.5 * |min - 25| / 25          (config/paper_reference.yaml)
    fast    the best BIPM, i.e. fewest iterations:
            score = mean_iterations / baseline + 3 * (steps at the limit) + 2 * (steps with equality residual > 1e-3)
In both modes a candidate is rejected if the cost leaves the ISPD cost by more than --max-cost-gap (mean relative).

Options searched (coordinate descent, then random perturbations): bipm_settings.kappa_initial / kappa_final /
kappa_update_factor. --include-shared adds options that ISPD uses too (inner iterations, epsilon_convergence,
termination criterion, regularization): the ISPD driver trajectory then changes with the candidate as well.

    python3 experiments/tune_bipm.py --steps 300                       # paper objective, about 20-40 min
    python3 experiments/tune_bipm.py --objective fast --steps 500 --full-horizons 3 15 30
Results: results/tuning/<timestamp>_bipm/  (log.jsonl, report.txt, best_config.yaml). config/ is not modified.
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

SPACE = {
    "bipm_settings.kappa_initial": [1e-3, 1e-2, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0],
    "bipm_settings.kappa_final": [300.0, 500.0, 1000.0, 1500.0, 3000.0, 5000.0, 1e4],
    "bipm_settings.kappa_update_factor": [2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0],
}
SHARED = {  # also used by ISPD (the driver)
    "general_settings.num_inner_iterations_max": [1, 2, 3, 5, 10, 20],
    "cg2o.epsilon_convergence": [1e-4, 1e-3, 1e-2, 1e-1],
    "cg2o.termination_criterion": [0, 1, 2],
    "cg2o.equality_regularization": [0.0, 1e-8, 1e-6],
}


def fmt(v) -> str:
    return repr(v) if isinstance(v, float) else str(v)


class Tuner:
    def __init__(self, a, binary: Path, workdir: Path, paper: dict):
        self.a, self.binary, self.workdir, self.paper = a, binary, workdir, paper
        self.n_eval = 0
        self._lock = threading.Lock()
        self.base_iter: float | None = None

    def run(self, opts: dict, horizon: int, steps: int, tag: str) -> dict:
        cmd = [str(self.binary), "--config", str(self.a.config), "--solvers", "ispd,bipm", "--driver", "ispd",
               "--horizon", str(horizon), "--init", "feasible", "--label", tag,
               "--set", f"experiment.output_dir={self.workdir}", "--set", "experiment.progress_every=100000"]
        if steps:
            cmd += ["--loop-size", str(steps)]
        for k, v in opts.items():
            cmd += ["--set", f"{k}={fmt(v)}"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.a.timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "why": "timeout"}
        out = r.stdout + r.stderr
        m = re.search(r"MACC run directory:\s*(\S+)", out)
        if r.returncode != 0 or not m:
            return {"ok": False, "why": "run failed: " + out[-150:].replace("\n", " ")}
        run_dir = Path(m.group(1))
        try:
            with open(run_dir / "steps.csv") as f:
                rows = list(csv.DictReader(f))
        finally:
            if not self.a.keep:
                shutil.rmtree(run_dir, ignore_errors=True)
        col = lambda k: [float(x[k]) for x in rows]  # noqa: E731
        it, cost, ref = col("bipm_iterations"), col("bipm_cost"), col("ispd_cost")
        eq, hit = col("bipm_eq_residual"), col("bipm_hit_max_iter")
        if not rows or not all(math.isfinite(v) for v in it + cost + eq):
            return {"ok": False, "why": "non-finite numbers"}
        gap = statistics.median(abs(c - r_) / max(abs(r_), 1e-12) for c, r_ in zip(cost, ref))   # median: unconverged steps are normal for BIPM
        return {"ok": True, "iter": statistics.mean(it), "iter_min": min(it), "iter_max": max(it),
                "hit": statistics.mean(hit), "bad_eq": statistics.mean(1.0 if v > 1e-3 else 0.0 for v in eq),
                "gap": gap, "ispd_iter": statistics.mean(col("ispd_iterations"))}

    def score(self, r: dict, horizon: int, baseline: bool = False) -> float:
        if not r["ok"] or (r["gap"] > self.a.max_cost_gap and not baseline):
            return math.inf
        if self.a.objective == "paper":
            p = self.paper.get(horizon)
            if not p:
                return math.inf
            return abs(r["iter"] - p["iter_avg"]) / p["iter_avg"] + 0.5 * abs(r["iter_min"] - p["iter_min"]) / p["iter_min"]
        base = self.base_iter or r["iter"]
        return r["iter"] / base + 3 * r["hit"] + 2 * r["bad_eq"]

    def screen(self, opts: dict) -> dict:
        with self._lock:
            self.n_eval += 1
            tag = f"bt{self.n_eval}"
        r = self.run(opts, self.a.horizon, self.a.steps, tag)
        return {"options": dict(opts), "stats": r, "score": self.score(r, self.a.horizon), "steps": self.a.steps}

    def full(self, opts: dict, tag: str, baseline: bool = False) -> dict:
        per = {}
        with ThreadPoolExecutor(max_workers=len(self.a.full_horizons)) as ex:
            futs = {n: ex.submit(self.run, opts, n, self.a.full_steps, f"{tag}_N{n}") for n in self.a.full_horizons}
            for n, f in futs.items():
                per[n] = f.result()
        sc = [self.score(r, n, baseline) for n, r in per.items()]
        return {"options": dict(opts), "per_horizon": per, "score": statistics.mean(sc) if sc else math.inf}


def load_paper() -> dict:
    """Paper Table V numbers of the barrier IPM: {horizon: {iter_avg, iter_min, iter_max}} from config/paper_reference.yaml."""
    ref_yaml = yaml.safe_load(open(ROOT / "config" / "paper_reference.yaml"))

    def find(d):
        if isinstance(d, dict):
            if "cg2o_bipm_feasible" in d:
                return d["cg2o_bipm_feasible"]
            for x in d.values():
                r = find(x)
                if r:
                    return r
        return None

    return {int(k): d for k, d in (find(ref_yaml) or {}).items() if isinstance(d, dict)}


def line(res: dict) -> str:
    s = res["stats"]
    if not s["ok"]:
        return f"score inf  ({s['why'][:60]})"
    return (f"score {res['score']:.3f}  it {s['iter']:.1f} (min {s['iter_min']:.0f}, max {s['iter_max']:.0f})  "
            f"limit {100 * s['hit']:.1f}%  eq>1e-3 {100 * s['bad_eq']:.1f}%  gap {s['gap']:.1e}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=ROOT / "config" / "config.yaml")
    p.add_argument("--objective", choices=["paper", "fast"], default="paper")
    p.add_argument("--horizon", type=int, default=30, help="horizon of the screening runs")
    p.add_argument("--steps", type=int, default=300, help="MPC steps of a screening run")
    p.add_argument("--full-horizons", type=int, nargs="+", default=[30], help="horizons of the full-cycle test")
    p.add_argument("--full-steps", type=int, default=0, help="steps of the full test (0 = whole driving cycle)")
    p.add_argument("--promote-gain", type=float, default=0.10,
                   help="run the full test when the screening score is this fraction lower than the reference")
    p.add_argument("--passes", type=int, default=2)
    p.add_argument("--random", type=int, default=20)
    p.add_argument("--include-shared", action="store_true", help="also tune options shared with ISPD")
    p.add_argument("--jobs", type=int, default=4, help="parallel screening runs")
    p.add_argument("--max-cost-gap", type=float, default=1e-3,
                   help="reject if the MEDIAN relative cost gap to ISPD exceeds this")
    p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--keep", action="store_true")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()

    binary = find_binary()
    out = ROOT / "results" / "tuning" / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_bipm")
    (out / "runs").mkdir(parents=True)
    paper = load_paper()
    space = dict(SPACE, **(SHARED if a.include_shared else {}))
    cfg = yaml.safe_load(open(a.config))

    def current(k):
        d = cfg
        for part in k.split("."):
            d = d.get(part, None) if isinstance(d, dict) else None
        return d

    best = {k: current(k) for k in space if current(k) is not None}
    tuner = Tuner(a, binary, out / "runs", paper)
    log = open(out / "log.jsonl", "w")
    t0 = time.time()
    rng = random.Random(a.seed)

    def record(stage, name, res):
        log.write(json.dumps({"stage": stage, "change": name, **res}, default=str) + "\n")
        log.flush()

    print(f"output: {out}\nobjective {a.objective}, screening N={a.horizon}, {a.steps} steps; paper targets {paper.get(a.horizon)}")
    base = tuner.screen(best)
    tuner.base_iter = base["stats"].get("iter")
    base["score"] = tuner.score(base["stats"], a.horizon, baseline=True)
    record("baseline", "-", base)
    print("baseline ", line(base), flush=True)
    reference = base["score"]
    best_res = base
    promoted: list[dict] = []
    base_full = None

    def maybe_promote(res, label):
        nonlocal reference, base_full, best
        if not math.isfinite(res["score"]) or res["score"] > reference * (1 - a.promote_gain):
            return False
        print(f"   -> much better than the reference ({res['score']:.3f} vs {reference:.3f}): full test ...", flush=True)
        if base_full is None:
            base_full = tuner.full(base["options"], "full_base", baseline=True)
            record("full_baseline", "-", base_full)
            print("   full baseline score", f"{base_full['score']:.3f}", flush=True)
        f = tuner.full(res["options"], f"full{len(promoted) + 1}")
        record("full", label, f)
        promoted.append(f)
        per = "  ".join(f"N={n}: it {r['iter']:.1f} limit {100 * r['hit']:.1f}%" if r["ok"] else f"N={n}: failed"
                        for n, r in f["per_horizon"].items())
        print(f"   full test score {f['score']:.3f} (baseline {base_full['score']:.3f})  {per}", flush=True)
        if f["score"] < base_full["score"]:
            reference = res["score"]
            return True
        return False

    names = list(space)
    for sweep in range(1, a.passes + 1):
        improved = False
        for name in names:
            cands = []
            for v in space[name]:
                if best.get(name) == v:
                    continue
                c = dict(best)
                c[name] = v
                cands.append((v, c))
            with ThreadPoolExecutor(max_workers=a.jobs) as ex:
                results = list(ex.map(lambda t: (t[0], tuner.screen(t[1])), cands))
            for v, r in results:
                record(f"pass{sweep}", f"{name}={v}", r)
            if not results:
                continue
            v, r = min(results, key=lambda t: t[1]["score"])
            if r["score"] < best_res["score"] - 1e-3:
                best, best_res, improved = r["options"], r, True
                print(f"[pass {sweep}] {name} = {v}  ->  {line(r)}   ({(time.time() - t0) / 60:.1f} min)", flush=True)
                maybe_promote(r, f"{name}={v}")
            else:
                print(f"[pass {sweep}] {name}: no gain", flush=True)
        if not improved:
            break
    for i in range(a.random):
        cand = dict(best)
        for name in rng.sample(names, k=min(len(names), rng.choice([2, 3]))):
            cand[name] = rng.choice(space[name])
        if cand == best:
            continue
        r = tuner.screen(cand)
        record("random", "perturbation", r)
        if r["score"] < best_res["score"] - 1e-3:
            best, best_res = r["options"], r
            print(f"[random {i + 1}] {line(r)}", flush=True)
            maybe_promote(r, "random")

    # final: if the best screening candidate was never fully tested, test it now
    if not promoted or promoted[-1]["options"] != best:
        if best != base["options"]:
            if base_full is None:
                base_full = tuner.full(base["options"], "full_base", baseline=True)
                record("full_baseline", "-", base_full)
            f = tuner.full(best, "full_best")
            record("full", "best", f)
            promoted.append(f)
    winner = min(promoted + ([base_full] if base_full else []), key=lambda r: r["score"]) if (promoted or base_full) else None
    lines = [f"BIPM tuning ({a.objective}) {datetime.now():%Y-%m-%d %H:%M}",
             f"screening: N={a.horizon}, {a.steps} steps; full test: horizons {a.full_horizons}, whole cycle",
             f"evaluations {tuner.n_eval}, time {(time.time() - t0) / 60:.1f} min", ""]
    if winner:
        lines.append("best configuration (full cycle):")
        lines += [f"  {k}: {v}" for k, v in winner["options"].items()]
        lines.append("")
        lines.append("            starting setting                          best")
        for n in a.full_horizons:
            for tag, res in (("start", base_full), ("best ", winner)):
                r = res["per_horizon"][n] if res else None
                if r and r["ok"]:
                    pp = paper.get(n, {})
                    lines.append(f"  N={n:<3} {tag}: iterations {r['iter']:.1f} (min {r['iter_min']:.0f}, max {r['iter_max']:.0f}), "
                                 f"steps at the limit {100 * r['hit']:.1f}%, eq residual > 1e-3 in {100 * r['bad_eq']:.1f}%, "
                                 f"cost gap to ISPD {r['gap']:.1e}   [paper: {pp.get('iter_avg', '-')} / {pp.get('iter_min', '-')} / {pp.get('iter_max', '-')}]")
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
