"""The MACC closed loop: `macc_run --solvers <driver>,<target> --driver <driver> ...` for one horizon, metrics from steps.csv.

This module is the ONLY code that knows the macc_run command line and the steps.csv columns. Algorithm specs address it with

    experiment="macc_closed_loop"
    setup=dict(target="ipopt",        # solver whose parameters are tuned (steps.csv columns <target>_iterations, <target>_cost ...)
               driver="ispd",         # solver that moves the plant; its cost is the reference of the cost gap
               init="fixed",          # macc_run --init (fixed = all variables 10, feasible = strictly feasible start)
               cases=(3, 15, 30),     # prediction horizons
               paper_key="ipopt_fixed",       # entry of config/paper_reference.yaml (objective "paper")
               fixed={"key": value})  # --set overrides that are never tuned

Metrics returned per run: iter_mean / iter_min / iter_max, hit (fraction of steps at the iteration limit), limit_steps (their
number), fail, bad (fraction with a large residual), gap_mean / gap_median (relative cost gap to the driver), residual
(max equality residual / inequality violation), time_ms (not reliable while other jobs run), n (steps).
"""
from __future__ import annotations

import csv
import math
import os
import re
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Any, Dict

import yaml

from ..constraints import Constraint
from ..experiment import Column, Experiment, register_experiment
from ..metrics import Metrics
from ..objectives import Context, objective, ratio_objective
from ..params import ParamSpace, Values, config_get, fmt_value

ROOT = Path(__file__).resolve().parents[3]
BAD_RESIDUAL = 1e-3     # a step is "bad" when its equality residual / inequality violation exceeds this

# Every macc_run of a tuning run is single-threaded: a shell that exports OMP_NUM_THREADS=8 would make each parallel process
# spin 8 threads (4x the CPU time for the same wall time) and the candidates would starve each other.
SINGLE_THREAD_ENV = {k: "1" for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "BLIS_NUM_THREADS")}
SINGLE_THREAD_ENV["MKL_THREADING_LAYER"] = "SEQUENTIAL"


def quality(cost_gap: float = 1e-4, stat: str = "mean", residual=1e-4, fail=0.02, hit=None) -> tuple:
    """The usual rejection rules of a MACC solver: the solution must stay as good as the driver's.
    cost_gap  max relative cost gap to the driver (stat: "mean" or "median" over the steps; the median tolerates a few
              unconverged steps), residual  max equality residual / inequality violation, fail  max fraction of failed
    steps, hit  max fraction of steps at the iteration limit. None = not checked."""
    cs = [Constraint(f"gap_{stat}", "<=", cost_gap, "cost gap")]
    if residual is not None:
        cs.append(Constraint("residual", "<=", residual, "residual"))
    if fail is not None:
        cs.append(Constraint("fail", "<=", fail, "failed steps"))
    if hit is not None:
        cs.append(Constraint("hit", "<=", hit, "steps at the limit"))
    return tuple(cs)


# --- objectives of this experiment ----------------------------------------------------------------------------------------
ratio_objective("iterations", "iter_mean", {"hit": 2.0, "bad": 1.0},
                "iterations relative to the starting setting + 2*(steps at the limit) + 1*(steps with a large residual)")
ratio_objective("time", "time_ms", {"hit": 2.0}, "solver time relative to the starting setting (idle machine only)")


@objective("paper")
def paper(metrics: Dict[Any, Metrics], ctx: Context) -> float:
    """distance to the paper's iteration statistics (needs setup['paper_key'])"""
    parts = []
    for case, m in metrics.items():
        p = ctx.extras.get("paper", {}).get(case)
        if p:
            parts.append(abs(m["iter_mean"] - p["iter_avg"]) / p["iter_avg"]
                         + 0.5 * abs(m["iter_min"] - p["iter_min"]) / p["iter_min"])
    return statistics.mean(parts) if parts else math.inf


def load_paper(key, path: Path) -> Dict[int, dict]:
    """{horizon: {iter_avg, iter_min, iter_max}} for `key` from config/paper_reference.yaml (empty if absent)."""
    if not key or not path.exists():
        return {}

    def find(d):
        if isinstance(d, dict):
            if key in d:
                return d[key]
            for x in d.values():
                r = find(x)
                if r:
                    return r
        return None

    return {int(k): v for k, v in (find(yaml.safe_load(open(path))) or {}).items() if isinstance(v, dict)}


@register_experiment
class MaccClosedLoop(Experiment):
    name = "macc_closed_loop"
    description = "MACC eco-driving closed loop (macc_run), one run per prediction horizon"
    primary, primary_label = "iter_mean", "iterations"
    case_option_aliases = ("--horizons",)          # cases are prediction horizons
    columns = (Column("iter_mean", "iter_mean"), Column("iter_min", "iter_min", "{:.0f}"), Column("iter_max", "iter_max", "{:.0f}"),
               Column("limit_steps", "steps_at_limit", "{:.0f}"), Column("n", "steps", "{:.0f}"),
               Column("gap_median", "cost_gap", "{:.2e}"))

    @classmethod
    def add_arguments(cls, g) -> None:
        g.add_argument("--config", type=Path, default=ROOT / "config" / "config.yaml",
                       help="macc_run: YAML configuration (the starting setting is read from it)")
        g.add_argument("--timeout", type=float, default=1800.0, help="macc_run: seconds per run")
        g.add_argument("--keep", action="store_true", help="macc_run: keep the run folders of the candidates")

    def __init__(self, args, spec, work_dir):
        super().__init__(args, spec, work_dir)
        self._binary = None
        self.config = Path(getattr(args, "config", ROOT / "config" / "config.yaml"))
        self.timeout, self.keep = getattr(args, "timeout", 1800.0), getattr(args, "keep", False)
        s = spec.setup
        self.target, self.driver, self.init = s["target"], s.get("driver", "ispd"), s.get("init", "fixed")

    @property
    def binary(self):
        if self._binary is None:
            from macc_exp.paths import find_binary      # experiments/ is on sys.path (tune.py); fails clearly if not built
            self._binary = find_binary()
        return self._binary

    # --- hooks ------------------------------------------------------------------------------------------------------------
    def current_values(self, space: ParamSpace) -> Values:
        cfg = yaml.safe_load(open(self.config))
        return {p.key: config_get(cfg, p.key) for p in space if config_get(cfg, p.key) is not None}

    def context_extras(self) -> Dict[str, Any]:
        return {"paper": load_paper(self.spec.setup.get("paper_key"), ROOT / "config" / "paper_reference.yaml")}

    def reference_note(self, case, metrics) -> str:
        p = self.context_extras()["paper"].get(case)
        return f"   [paper: {p['iter_avg']} / {p['iter_min']} / {p['iter_max']}]" if p else ""

    def case_label(self, case) -> str:
        return f"N{case}"

    def overrides_text(self, values: Values) -> str:
        return " ".join(f"--set {k}={fmt_value(v)}" for k, v in {**self.spec.setup.get("fixed", {}), **values}.items())

    @classmethod
    def apply(cls, nested_result: dict, args) -> int:
        def merge(dst, src):
            for k, v in src.items():
                if isinstance(v, dict) and isinstance(dst.get(k), dict):
                    merge(dst[k], v)
                else:
                    dst[k] = v
        cfg = yaml.safe_load(open(args.config))
        merge(cfg, nested_result)
        if args.to.resolve() == Path(args.config).resolve():
            print("refusing to overwrite the input config; choose another --to")
            return 2
        yaml.safe_dump(cfg, open(args.to, "w"), sort_keys=False)
        print(f"wrote {args.to} (comments of the input are lost)")
        return 0

    # --- run --------------------------------------------------------------------------------------------------------------
    @property
    def solvers(self) -> str:
        return self.target if self.driver == self.target else f"{self.driver},{self.target}"

    def command(self, values: Values, horizon: int, steps: int, tag: str) -> list:
        cmd = [str(self.binary), "--config", str(self.config), "--solvers", self.solvers, "--driver", self.driver,
               "--horizon", str(horizon), "--init", self.init, "--label", tag,
               "--set", f"experiment.output_dir={self.work_dir}", "--set", "experiment.progress_every=100000000"]
        if steps:
            cmd += ["--loop-size", str(steps)]
        for k, v in {**self.spec.setup.get("fixed", {}), **values}.items():
            cmd += ["--set", f"{k}={fmt_value(v)}"]
        return cmd

    def run(self, values: Values, case: Any, fidelity: int, tag: str) -> Metrics:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        try:
            r = subprocess.run(self.command(values, case, fidelity, tag), capture_output=True, text=True,
                               timeout=self.timeout, env={**os.environ, **SINGLE_THREAD_ENV})
        except subprocess.TimeoutExpired:
            return Metrics.failed("timeout")
        out = r.stdout + r.stderr
        m = re.search(r"MACC run directory:\s*(\S+)", out)
        if r.returncode != 0 or not m:
            bad = re.search(r"(Setup error|not a valid|Invalid|error).*", out, re.I)
            return Metrics.failed("run failed: " + (bad.group(0) if bad else out[-150:]).replace("\n", " ")[:160])
        run_dir = Path(m.group(1))
        try:
            with open(run_dir / "steps.csv") as f:
                rows = list(csv.DictReader(f))
        finally:
            if not self.keep:
                shutil.rmtree(run_dir, ignore_errors=True)
        return self.metrics(rows)

    def metrics(self, rows: list) -> Metrics:
        t = self.target
        ref = self.driver if self.driver != self.target else None
        try:
            col = lambda name: [float(x[name]) for x in rows]  # noqa: E731
            it, cost = col(f"{t}_iterations"), col(f"{t}_cost")
            eq, ineq = col(f"{t}_eq_residual"), col(f"{t}_ineq_violation")
            hit, succ, ms = col(f"{t}_hit_max_iter"), col(f"{t}_success"), col(f"{t}_time_ms")
            refc = col(f"{ref}_cost") if ref else None
        except (KeyError, ValueError) as e:
            return Metrics.failed(f"missing column {e}")
        if not rows or not all(math.isfinite(v) for vs in (it, cost, eq, ineq) for v in vs):
            return Metrics.failed("non-finite numbers")
        gaps = [abs(c - r) / max(abs(r), 1e-12) for c, r in zip(cost, refc)] if refc else [0.0] * len(cost)
        return Metrics(True, "", {
            "n": float(len(rows)), "iter_mean": statistics.mean(it), "iter_min": min(it), "iter_max": max(it),
            "hit": statistics.mean(hit), "limit_steps": float(sum(hit)), "fail": 1.0 - statistics.mean(succ),
            "bad": statistics.mean(1.0 if (e > BAD_RESIDUAL or i > BAD_RESIDUAL) else 0.0 for e, i in zip(eq, ineq)),
            "gap_mean": statistics.mean(gaps), "gap_median": statistics.median(gaps),
            "residual": max(max(eq), max(ineq)), "max_eq": max(eq), "max_ineq": max(ineq), "time_ms": statistics.mean(ms)})
