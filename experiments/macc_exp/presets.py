"""The experiments of the paper: Fig. 2 (cg2o vs BIPM) and Fig. 3 (cg2o vs IPOPT)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import figures, paper, report
from .experiment import Experiment
from .runner import RunResult

PROGRESS = "experiment.progress_every=500"


@dataclass
class Opts:
    horizons: Sequence[int] = (3, 15, 30)
    steps: int = 0                    # 0 = whole driving cycle (3863 steps)
    steps_by_n: Dict[int, int] = field(default_factory=dict)   # linear-solvers: MPC steps per horizon (else steps)
    run_times: int = 1                # solves per step used for the timing (paper: >10)
    max_iter: int = 120
    linear_solver: Optional[str] = None
    overrides: List[str] = field(default_factory=list)
    config: Optional[str] = None
    palette: str = "paper"
    latex: bool = False
    plots: bool = True
    timeout: Optional[float] = None
    # linear-solver sweep
    modes: Sequence[str] = ("kkt", "kkt-reg")
    include_slow: bool = False
    solvers: Optional[Sequence[str]] = None
    regularization: float = 1e-8
    include: Sequence[str] = ()          # combined figure only: bars to draw, e.g. "cholmod(reg)", "qdldlt"; empty = all
    stat: str = "mean"                   # linear-solver figures: "mean" or "median" time per MPC step
    hide_failed: bool = False            # linear-solvers: leave out solvers without a valid result; fig2/fig3: failed steps / horizons
    numbers: bool = True                 # fig2/fig3: write the means into the panels
    no_reg_solvers: Sequence[str] = ("18", "19", "20", "21")   # run only without regularization (they have their own internal one)
    measure: str = "fixed"               # fixed: max_iter iterations per step (time per step); converged: run to convergence
    ls_jobs: Sequence[str] = ()          # --linear-solver 0 0reg 1 1reg: exactly these runs (overrides solvers / modes)
    # fig3
    protocol: str = "both"            # both | cold | warm  (IPOPT start protocol)
    # single
    macc_args: Sequence[str] = ()

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["horizons"] = list(self.horizons)
        d["modes"] = list(self.modes)
        d["include"] = list(self.include)
        d["steps_by_n"] = {str(k): v for k, v in self.steps_by_n.items()}
        d["no_reg_solvers"] = list(self.no_reg_solvers)
        d["ls_jobs"] = list(self.ls_jobs)
        d["macc_args"] = list(self.macc_args)
        return d


def base_args(o: Opts, horizon: int, solvers: Sequence[str], init: str) -> List[str]:
    a = ["--solvers", ",".join(solvers), "--horizon", str(horizon), "--init", init,
         "--run-times", str(o.run_times), "--max-iter", str(o.max_iter), "--driver", solvers[0]]
    if o.steps:
        a += ["--loop-size", str(o.steps)]
    if o.linear_solver is not None:
        a += ["--linear-solver", str(o.linear_solver)]
    if o.config:
        a += ["--config", o.config]
    return a


# ----------------------------------------------------------------------------- analysis
def _domain_split(run: RunResult, solver: str) -> Optional[str]:
    st = run.steps()
    if "space_domain" not in st:
        return None
    sp = st["space_domain"] > 0.5
    it = st[f"{solver}_iterations"]
    tm = st[f"{solver}_time_ms"]
    out = []
    for name, m in (("space-domain", sp), ("time-domain", ~sp)):
        if m.any():
            out.append(f"{name}: {m.sum():>4d} steps, {it[m].mean():5.1f} it., {tm[m].mean():7.3g} ms")
    return "; ".join(out)


def _cost_agreement(run: RunResult, a: str, b: str) -> str:
    st = run.steps()
    ca, cb = st[f"{a}_cost"], st[f"{b}_cost"]
    ok = np.isfinite(ca) & np.isfinite(cb)
    if not ok.any():
        return "n/a"
    rel = np.abs(ca[ok] - cb[ok]) / np.maximum(np.abs(cb[ok]), 1e-12)
    lower = (ca[ok] < cb[ok] - figures.COST_TOL * np.abs(cb[ok])).mean()
    higher = (ca[ok] > cb[ok] + figures.COST_TOL * np.abs(cb[ok])).mean()
    return (f"median |dcost|/cost = {np.median(rel):.1e}, 95th pct = {np.percentile(rel, 95):.1e}, "
            f"max = {rel.max():.1e};  {a} lower in {100 * lower:.1f}% of the steps, "
            f"{b} lower in {100 * higher:.1f}%")


def analyze_comparison(exp: Experiment, o: Opts, *, pairs: Sequence[dict], table: str,
                       with_time_paper: bool, notes: Sequence[str]) -> None:
    """pairs: dicts with a, b (solver names), labels, fig (file prefix), fig_rows."""
    runs = {r.horizon: r for r in exp.runs if r.ok}
    if not runs:
        exp.notes.append("No run finished: nothing to analyse.")
        return
    present = set()
    for r in runs.values():
        present |= set(r.summary["solvers"])
    solvers: List[str] = []
    for p in pairs:
        for s in (p["a"], p["b"]):
            if s in present and s not in solvers:
                solvers.append(s)
    rows = report.comparison_rows(runs, solvers)
    csv_path = exp.dir / f"{table}.csv"
    report.write_csv(rows, csv_path)
    exp.add_output(csv_path)

    exp.add_section("Results of this run next to the numbers of the paper",
                    "iterations / computation time per MPC step over the closed-loop simulation\n"
                    "(time = average over run_times repetitions per step, outliers removed;\n"
                    "min/max are over the MPC steps).\n\n" +
                    report.comparison_text(rows, with_time_paper))
    split = []
    for n in sorted(runs):
        for s in solvers:
            if s in runs[n].summary["solvers"]:
                txt = _domain_split(runs[n], s)
                if txt:
                    split.append(f"N={n:<3d} {s:<10s} {txt}")
    if split:
        exp.add_section("Where the iterations go (space domain = host faster than 3 m/s, paper Eq. 42)",
                        "\n".join(split))
    quality = []
    for p in pairs:
        if p["a"] in present and p["b"] in present:
            quality.append(f"{p['a']} vs {p['b']}")
            quality += [f"  N={n:<3d} {_cost_agreement(runs[n], p['a'], p['b'])}" for n in sorted(runs)]
    exp.add_section("Solution quality (cost of every step re-evaluated with one common function)",
                    "\n".join(quality) +
                    "\n\nconstraint violation (max over the run):\n" +
                    "\n".join(f"N={r['N']:<3d} {r['solver']:<10s} equality residual {r['max_eq_residual']:.2e}, "
                              f"inequality violation {r['max_ineq_violation']:.2e}, "
                              f"{r['steps_at_max_iter']} step(s) at the iteration limit, "
                              f"{r['steps_failed']} failed" for r in rows))
    exp.notes.extend(notes)

    if not o.plots:
        return
    stem = exp.dir / "figures"
    for p in pairs:
        if p["a"] not in present or p["b"] not in present:
            continue
        for name, rws in p["fig_rows"].items():
            try:
                written = figures.comparison_figure(runs, p["a"], p["b"], p["labels"], rws,
                                                    stem / f"{p['fig']}_{name}",
                                                    palette=o.palette, latex=o.latex, note=p.get("note", ""),
                                                    hide_failed=o.hide_failed, numbers=o.numbers)
                exp.add_output(*written)
            except Exception as e:  # keep the experiment usable if plotting fails
                exp.notes.append(f"Figure {p['fig']}_{name} could not be created: {e!r}")


# ----------------------------------------------------------------------------- fig 2
FIG2_DESC = """Paper Fig. 2 / Table IV: ISPD-IPM of cg2o against the barrier-based factor-graph
solver (BIPM, ref. [6]). Both solve the SAME MPC problem at every step of the MACC
closed loop and both start from the strictly feasible projection of the initial
guess (BIPM cannot start elsewhere). The input of cg2o drives the plant. In addition
to iterations and time per step, the time per iteration is stored for every step."""

FIG2_NOTES = [
    "Steps that reach the iteration limit (120) are part of the averages, as in the paper (its BIPM maxima\n"
    "are 120 too). The point returned there is not converged: see the constraint violation in section 6.",
    "Absolute times belong to this machine (the paper used an Intel Core i9, 12th gen), so compare\n"
    "iteration counts and the ratio between the solvers, not the milliseconds.",
    "Time per iteration = solver time of the step / iterations of the step (column *_ms_per_iter of\n"
    "runs/*/steps.csv); the table above uses total time / total iterations.",
]


def run_fig2(exp: Experiment, o: Opts) -> None:
    for n in o.horizons:
        exp.run(f"N{n}", base_args(o, n, ["ispd", "bipm"], "feasible"), [PROGRESS, *o.overrides],
                timeout=o.timeout)
    analyze_fig2(exp, o)


def analyze_fig2(exp: Experiment, o: Opts) -> None:
    pair = dict(a="ispd", b="bipm", labels={"ispd": "cg2o (ISPD-IPM)", "bipm": "Barrier-IPM"}, fig="fig2",
                fig_rows={"overview": ["iter", "time"],                   # per-step overview (the paper's Fig. 2 is
                          "overview_tpi": ["iter", "time", "tpi"],         # paper_fig2_macc_vs_bipm.pdf)
                          "overview_full": ["traj", "iter", "time", "tpi", "cost", "better"]})
    analyze_comparison(exp, o, pairs=[pair], table="table_iv_bipm", with_time_paper=False,
                       notes=FIG2_NOTES)


# ----------------------------------------------------------------------------- fig 3
FIG3_DESC = """Paper Fig. 3 / Table V: ISPD-IPM of cg2o against IPOPT on the exact MACC problem
(horizons N = 3, 15, 30; at most 120 iterations). All solvers solve the SAME NLP at every
closed-loop step (same cost, same dynamics, same 16 constraint rows per stage); the input
of cg2o drives the plant. IPOPT is the native C++ library called through its TNLP interface
with exact analytic Jacobian and Hessian - no modelling-language layer in between.

Two IPOPT start protocols are evaluated side by side:
  ipopt       every variable = 10 at every step, as cg2o ("IPOPT, cold" in the paper)
  ipopt_warm  start from the solution of the previous step ("IPOPT, warm")"""

FIG3_NOTES = [
    "IPOPT is the native library; its version and linear solver are listed in section 2 and in the\n"
    "ipopt.* settings of each run. The paper's Table V uses HSL MA57 (ipopt_settings.use_hsl: true);\n"
    "with MUMPS (the default) the IPOPT iteration counts differ slightly from the paper's.",
    "Steps that reach the iteration limit (120) are part of the averages, as in the paper. The point\n"
    "returned there is not converged: see the constraint violation in section 6.",
    "Absolute times belong to this machine (the paper used an Intel Core i9-12900H); compare iterations\n"
    "and the ratios between the solvers.",
    "IPOPT options used are listed in each run's experiment_info.txt (and runs/*/ipopt.opt).",
]


def fig3_solvers(o: Opts) -> List[str]:
    return {"both": ["ispd", "ipopt", "ipopt_warm"], "cold": ["ispd", "ipopt"],
            "warm": ["ispd", "ipopt_warm"]}[o.protocol]


def run_fig3(exp: Experiment, o: Opts) -> None:
    for n in o.horizons:
        exp.run(f"N{n}", base_args(o, n, fig3_solvers(o), "fixed"), [PROGRESS, *o.overrides],
                timeout=o.timeout)
    analyze_fig3(exp, o)


def analyze_fig3(exp: Experiment, o: Opts) -> None:
    # per-step overviews; the paper's Figs. 3 and 4 are paper_fig3_macc_vs_ipopt.pdf / paper_fig4_macc_trajectory.pdf
    rows = {"overview": ["traj", "iter", "time", "cost", "better"],
            "overview_full": ["traj", "iter", "time", "tpi", "cost", "better"]}
    pairs = [
        dict(a="ispd", b="ipopt", labels={"ispd": "cg2o (ISPD-IPM)", "ipopt": "IPOPT"},
             note="Both solvers: cold start at every MPC step, all variables = 10 (infeasible initial guess)",
             fig="fig3", fig_rows=rows),
        dict(a="ispd", b="ipopt_warm", labels={"ispd": "cg2o (ISPD-IPM)", "ipopt_warm": "IPOPT, warm start"},
             note="cg2o: cold start, all variables = 10 (infeasible);  IPOPT: warm start from the previous solution",
             fig="fig3_ipopt_warm", fig_rows=rows),
    ]
    analyze_comparison(exp, o, pairs=pairs, table="table_v_ipopt", with_time_paper=True, notes=FIG3_NOTES)


# ----------------------------------------------------------------------------- single
SINGLE_DESC = """One free-form closed-loop run of macc_run, stored like every other experiment.
All arguments after '--' are handed to macc_run unchanged."""


def run_single(exp: Experiment, o: Opts) -> None:
    exp.run("run", list(o.macc_args), list(o.overrides), timeout=o.timeout)
    ok = [r for r in exp.runs if r.ok]
    if ok:
        r = ok[0]
        rows = []
        for name, d in r.summary["solvers"].items():
            rows.append(f"{name:<6} iterations {d['iterations']['mean']:.1f} "
                        f"({d['iterations']['min']:.0f}..{d['iterations']['max']:.0f}), "
                        f"time {d['time_ms']['mean']:.3g} ms ({d['time_ms']['min']:.3g}..{d['time_ms']['max']:.3g}), "
                        f"{d['time_per_iter_total_ms']:.3g} ms/iteration")
        exp.add_section("Result", "\n".join(rows))
