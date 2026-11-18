"""Compare the linear solvers of the native IPOPT backend on the MACC closed loop.

ISPD-IPM drives the plant in every run, so all IPOPT linear solvers solve exactly the same sequence of
NLPs (cold start, initial guess 10, the tuned options of config/config.yaml); only
`ipopt_settings.options.linear_solver` changes. Each (solver, horizon) is a separate `macc_run` process.
A solver that is not compiled into this IPOPT build fails a short probe run and is reported as
"not available" (see ./scripts/build_externals/ipopt.sh for how to add MKL PARDISO, SPRAL and HSL)."""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

from . import style
from .experiment import Experiment
from .presets import Opts, PROGRESS
from .runner import run_macc

plt = style.plt

#: every linear solver IPOPT 3.14 knows (wsmp and the custom interface are left out)
ALL_SOLVERS = ["mumps", "pardisomkl", "spral", "spral_mc64", "spral_none", "ma27", "ma57", "ma77", "ma86", "ma97",
               "pardiso"]
#: entries that are an IPOPT linear solver with extra options: name -> (linear_solver, options).
#: IPOPT's default spral_scaling=matching makes it call SPRAL's analyse (ordering + hardware probing) at EVERY
#: factorisation; mc64 / none analyse once, which is what the other solvers do.
VARIANTS = {"spral_mc64": ("spral", {"spral_scaling": "mc64"}),
            "spral_none": ("spral", {"spral_scaling": "none"})}
REFERENCE = "mumps"
COST_TOL = 1e-3          # relative deviation of the summed IPOPT cost from the MUMPS run
ITER_TOL = 0.10          # relative deviation of the mean iteration count

#: OMP_*: SPRAL's SSIDS needs OpenMP cancellation and bound threads. MKL_*: MKL (PARDISO, BLAS/LAPACK of IPOPT) on one core
SPRAL_ENV = {"OMP_CANCELLATION": "TRUE", "OMP_PROC_BIND": "TRUE", "MKL_THREADING_LAYER": "SEQUENTIAL",
             "MKL_NUM_THREADS": "1"}

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _hwloc_xml(exp: Experiment) -> None:
    """SPRAL probes the hardware topology (hwloc) at every analyse call: about 0.3 s per IPOPT iteration on WSL.
    A saved topology file removes that; it is made once per experiment (lstopo, else the helper in tools/)."""
    xml = exp.dir / "topology.xml"
    try:
        if shutil.which("lstopo-no-graphics"):
            subprocess.run(["lstopo-no-graphics", "--of", "xml", str(xml)], check=True, capture_output=True)
        else:
            exe = exp.dir / "hwloc_export_xml"
            subprocess.run(["gcc", str(TOOLS / "hwloc_export_xml.c"), "-o", str(exe), "-lhwloc"],
                           check=True, capture_output=True)
            subprocess.run([str(exe), str(xml)], check=True, capture_output=True)
            exe.unlink()
        os.environ.update(HWLOC_XMLFILE=str(xml), HWLOC_THISSYSTEM="1")
        exp.notes.append(f"HWLOC_XMLFILE={xml.name} HWLOC_THISSYSTEM=1: saved hardware topology, so that SPRAL does not "
                         "probe /sys at every factorisation.")
    except (OSError, subprocess.CalledProcessError) as e:
        exp.notes.append(f"Could not save the hardware topology ({e!r}); SPRAL may be very slow on WSL.")


DESC = """Linear solvers of the native IPOPT backend on the MACC closed loop.
ISPD-IPM drives the plant, so every IPOPT linear solver solves the same NLPs (IPOPT cold start, initial
guess 10, options of config/config.yaml); only ipopt_settings.options.linear_solver differs. A solver is
ranked by its mean time per MPC step, but only if it reproduces the MUMPS result (cost and iterations)."""


def _args(o: Opts, n: int, steps: int) -> List[str]:
    a = ["--solvers", "ispd,ipopt", "--driver", "ispd", "--horizon", str(n), "--init", "fixed",
         "--run-times", str(o.run_times), "--max-iter", str(o.max_iter)]
    if steps:
        a += ["--loop-size", str(steps)]
    if o.config:
        a += ["--config", o.config]
    return a


#: HSL library from `scripts/build_externals.sh --hsl`; IPOPT loads it at run time for ma27 ... ma97.
HSL_LIB = Path(__file__).resolve().parents[2] / "install/externals/hsl/lib/x86_64-linux-gnu/libcoinhsl.so"


def _overrides(solver: str) -> List[str]:
    base, opts = VARIANTS.get(solver, (solver, {}))
    hsl = [f"ipopt_settings.options.hsllib={HSL_LIB}"] if base.startswith("ma") and HSL_LIB.is_file() else []
    return [f"ipopt_settings.options.linear_solver={base}", *hsl,
            *[f"ipopt_settings.options.{k}={v}" for k, v in opts.items()]]


def _probe(exp: Experiment, o: Opts, solver: str) -> str:
    """'' if IPOPT accepts the linear solver, otherwise the reason."""
    res = run_macc(_args(o, 3, 3), exp.runs_dir / "probes", f"probe_{solver}",
                   overrides=[*_overrides(solver), *o.overrides], timeout=60, echo=False)
    if not res.ok:
        return f"run failed ({res.status}); this IPOPT build probably does not contain it"
    d = res.solver_summary("ipopt")
    if d["steps_failed"]:
        return "IPOPT rejected the solver (not compiled into this build?)"
    return ""


def run_ipopt_linear_solvers(exp: Experiment, o: Opts) -> None:
    os.environ.update(SPRAL_ENV)
    _hwloc_xml(exp)
    exp.notes.append("Environment for every run: " + " ".join(f"{k}={v}" for k, v in SPRAL_ENV.items())
                     + " (OMP_*: required by SPRAL; MKL_*: one core for PARDISO and BLAS).")
    wanted = [s.lower() for s in (o.solvers or ALL_SOLVERS)]
    if "all" in wanted:
        wanted = ALL_SOLVERS
    available = []
    for s in wanted:
        why = _probe(exp, o, s)
        if why:
            print(f"  {s:<11} not available: {why}", flush=True)
            exp.notes.append(f"IPOPT linear solver '{s}' not available: {why}")
        else:
            print(f"  {s:<11} available", flush=True)
            available.append(s)
    if REFERENCE in available:            # reference first, so a failure there is seen early
        available.remove(REFERENCE)
        available.insert(0, REFERENCE)

    records: List[dict] = []
    total = len(o.horizons) * len(available)
    i = 0
    for n in sorted(o.horizons):
        for s in available:
            i += 1
            print(f"\n[{i}/{total}] N={n} IPOPT linear solver {s}", flush=True)
            ov = [PROGRESS, *_overrides(s), *o.overrides]
            res = run_macc(_args(o, n, o.steps), exp.runs_dir, f"ipopt_{s}_N{n}", overrides=ov,
                           timeout=o.timeout, echo=False)
            exp.runs.append(res)
            rec = {"N": n, "solver": s, "status": res.status, "iter_avg": None, "iter_max": None,
                   "time_avg_ms": None, "time_min_ms": None, "time_max_ms": None, "ms_per_iter": None,
                   "cost_sum": None, "steps_failed": None, "steps_at_max_iter": None, "max_eq_residual": None,
                   "ispd_time_avg_ms": None, "run_dir": str(res.dir.relative_to(exp.dir)) if res.dir else "",
                   "note": ""}
            if res.ok:
                d = res.solver_summary("ipopt")
                rec.update(iter_avg=d["iterations"]["mean"], iter_max=d["iterations"]["max"],
                           time_avg_ms=d["time_ms"]["mean"], time_min_ms=d["time_ms"]["min"],
                           time_max_ms=d["time_ms"]["max"], ms_per_iter=d["time_per_iter_total_ms"],
                           cost_sum=d["cost_sum"], steps_failed=d["steps_failed"],
                           steps_at_max_iter=d["steps_hit_max_iter"], max_eq_residual=d["max_eq_residual"],
                           ispd_time_avg_ms=res.solver_summary("ispd")["time_ms"]["mean"])
                print(f"    {rec['iter_avg']:.1f} it.  {rec['time_avg_ms']:.4g} ms/step  "
                      f"{rec['ms_per_iter']:.3g} ms/it.  max-iter steps {rec['steps_at_max_iter']}", flush=True)
            else:
                rec["note"] = (res.error or res.status)[:120]
                print(f"    {res.status}: {rec['note']}", flush=True)
            records.append(rec)
            exp.write_info()
    analyze(exp, o, records)


def _validate(records: List[dict]) -> None:
    for n in {r["N"] for r in records}:
        grp = [r for r in records if r["N"] == n]
        ref = next((r for r in grp if r["solver"] == REFERENCE and r["status"] == "COMPLETED"), None)
        for r in grp:
            r["valid"], r["verdict"] = False, r["status"].lower()
            if r["status"] != "COMPLETED":
                continue
            if r["steps_failed"]:
                r["verdict"] = f"{r['steps_failed']} failed steps"
                continue
            if ref is None:
                r["valid"], r["verdict"] = True, "ok (no MUMPS reference)"
                continue
            cdev = abs(r["cost_sum"] - ref["cost_sum"]) / max(abs(ref["cost_sum"]), 1e-12)
            idev = abs(r["iter_avg"] - ref["iter_avg"]) / max(ref["iter_avg"], 1e-12)
            r["cost_dev"] = cdev
            if cdev > COST_TOL:
                r["verdict"] = f"different result (cost {cdev:.1e} off)"
            elif idev > ITER_TOL:
                r["verdict"] = f"different convergence ({r['iter_avg']:.1f} vs {ref['iter_avg']:.1f} it.)"
            else:
                r["valid"], r["verdict"] = True, "ok"


def analyze(exp: Experiment, o: Opts, records: List[dict]) -> None:
    _validate(records)
    fields = ["N", "solver", "status", "verdict", "valid", "iter_avg", "iter_max", "time_avg_ms", "time_min_ms",
              "time_max_ms", "ms_per_iter", "steps_at_max_iter", "steps_failed", "cost_sum", "cost_dev",
              "max_eq_residual", "ispd_time_avg_ms", "run_dir", "note"]
    p = exp.dir / "ipopt_linear_solvers.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    exp.add_output(p)

    text = []
    for n in sorted({r["N"] for r in records}):
        grp = [r for r in records if r["N"] == n]
        ranked = sorted([r for r in grp if r["valid"]], key=lambda r: r["time_avg_ms"])
        text.append(f"N = {n}   (IPOPT time = mean per MPC step on this machine; ISPD-IPM for scale)")
        text.append(f"  {'rank':>4} {'solver':<11} {'time [ms]':>10} {'ms/iter':>9} {'iter':>6} {'max-it':>7} "
                    f"{'x best':>7}  verdict")
        for k, r in enumerate(ranked, 1):
            text.append(f"  {k:>4} {r['solver']:<11} {r['time_avg_ms']:>10.4g} {r['ms_per_iter']:>9.3g} "
                        f"{r['iter_avg']:>6.1f} {r['steps_at_max_iter']:>7} "
                        f"{r['time_avg_ms'] / ranked[0]['time_avg_ms']:>7.2f}  {r['verdict']}")
        for r in grp:
            if not r["valid"]:
                t = "" if r["time_avg_ms"] is None else f"{r['time_avg_ms']:.4g}"
                text.append(f"  {'-':>4} {r['solver']:<11} {t:>10} {'':>9} {'':>6} {'':>7} {'':>7}  {r['verdict']}"
                            + (f" ({r['note']})" if r["note"] else ""))
        isp = next((r["ispd_time_avg_ms"] for r in grp if r["ispd_time_avg_ms"]), None)
        if isp:
            text.append(f"  ISPD-IPM (cg2o) on the same steps: {isp:.4g} ms/step")
        text.append("")
    exp.add_section("Ranking of the IPOPT linear solvers", "\n".join(text))
    if o.plots and records:
        try:
            exp.add_output(*_chart(exp, records, o))
        except Exception as e:  # a figure problem must not lose the table
            exp.notes.append(f"Chart failed: {e!r}")


def _chart(exp: Experiment, records: List[dict], o: Opts) -> List[Path]:
    style.apply(o.palette, o.latex)
    ns = sorted({r["N"] for r in records})
    metrics = [("time_avg_ms", "IPOPT time per MPC step [ms]"), ("ms_per_iter", "IPOPT time per iteration [ms]")]
    solvers = [s for s in ALL_SOLVERS if any(r["solver"] == s for r in records)]
    fig, axes = plt.subplots(len(metrics), len(ns), figsize=(3.4 * len(ns) + 0.8, 1.0 + 0.5 * len(solvers) * len(metrics)),
                             constrained_layout=True, squeeze=False)
    for j, n in enumerate(ns):
        by: Dict[str, dict] = {r["solver"]: r for r in records if r["N"] == n}
        for i, (key, label) in enumerate(metrics):
            ax = axes[i, j]
            ys = list(range(len(solvers)))[::-1]
            vals = [by.get(s, {}).get(key) if by.get(s, {}).get("valid") else None for s in solvers]
            ok = [v for v in vals if v]
            best = min(ok) if ok else 1.0
            for y, s, v in zip(ys, solvers, vals):
                if v:
                    ax.barh(y, v, height=0.62, color=style.CATEGORICAL[0] if v == best else style.MUTED, zorder=3)
                    ax.text(v * 1.02, y, f"{v:.3g}" + ("" if v == best else f" ({v / best:.1f}×)"),
                            va="center", fontsize=6.5)
                else:
                    r = by.get(s)
                    ax.text(0.01, y, r["verdict"] if r else "not available", va="center", fontsize=6.3,
                            color=style.MUTED, style="italic", transform=ax.get_yaxis_transform())
            ax.set_yticks(ys)
            ax.set_yticklabels(solvers, fontsize=6.5)
            ax.set_xlim(0, (max(ok) if ok else 1.0) * 1.35)
            ax.set_xlabel(label)
            if i == 0:
                ax.set_title(f"N = {n}", loc="left", fontsize=8)
            ax.grid(True, axis="x", linewidth=0.6, alpha=0.4, zorder=0)
            ax.tick_params(axis="y", length=0)
    stem = exp.dir / "figures" / "ipopt_linear_solvers"
    stem.parent.mkdir(exist_ok=True)
    out = []
    for fmt in ("pdf", "png"):
        pth = stem.with_suffix("." + fmt)
        fig.savefig(pth, bbox_inches="tight")
        out.append(pth)
    plt.close(fig)
    return out
