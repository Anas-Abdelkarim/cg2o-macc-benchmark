"""Evaluate the linear solvers of g2o / cg2o on the full MACC problem (dynamics as equality constraints +
inequalities) inside the ISPD-IPM, and rank them.

Two measures (--measure):
  fixed      every MPC step runs exactly max_iter iterations (convergence test off, default 10), so every solver does
             the same work and the time per MPC step compares the linear solvers only;
  converged  every MPC step runs until cg2o's convergence test holds (limit max_iter, default 120); compared are the
             time per iteration and the iterations needed to terminate.

Every (horizon, mode, solver) is a separate `macc_run` process, so a solver that crashes, diverges or is too
slow cannot spoil the others. Modes: 'kkt' = exact KKT matrix (sigma = 0), 'kkt-reg' = KKT matrix with the
equality regularization sigma (cg2o.equality_regularization). The runs are chosen with --solvers x --modes, or
one by one with --linear-solver, e.g. `--linear-solver 0 0reg 14 14reg` ('<id or key>reg' = mode kkt-reg).
At every horizon UMFPACK on the exact KKT matrix runs first and is the reference: a solver is 'valid' only if it
reproduces that cost. A solver with a different result is still timed and drawn (hatched bar); a solver that
crashes or times out is not run at the larger horizons. linear_solvers.csv is rewritten after every run, so an
interrupted experiment can still be plotted (`run_experiment.py replot <folder>`)."""

from __future__ import annotations

import csv
import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import style
from .experiment import Experiment
from .presets import Opts, PROGRESS
from .runner import list_linear_solvers, run_macc

plt = style.plt

MODE_INFO = {
    "kkt": ("full MACC problem (equalities + inequalities), exact KKT matrix (sigma = 0)",
            "Indefinite KKT matrix: Cholesky-type solvers are expected to fail, LU / QDLDL may work."),
    "kkt-reg": ("full MACC problem + equality regularization sigma (cg2o.equality_regularization)",
                "Quasi-definite KKT matrix: LDL^T without pivoting becomes possible."),
}
MEASURE_INFO = {
    "fixed": "every MPC step runs exactly max_iter ISPD iterations (convergence test off): time per MPC step",
    "converged": "every MPC step runs until convergence (limit max_iter): time per iteration and iterations",
}
DEFAULT_MAX_ITER = {"fixed": 10, "converged": 120}

#: solvers run when --solvers is not given: every solver that is fast enough for the full problem
#: (pcg, SVD, QR, BiCGSTAB, LSCG, dense LDLT and g2o Eigen failed or were far slower in the complete sweep)
DEFAULT_SOLVERS = [0, 1, 2, 6, 12, 13, 14, 16, 17, 18, 19, 20, 21]   # 13 pardiso: only if cg2o is built with MKL
REFERENCE = "umfpack"    # on the exact KKT matrix: the paper's default solver

#: a solver is only valid when its summed cost differs less than this (relative) from the reference
COST_TOL = 1e-3
ITER_TOL = 0.10          # measure fixed: and its mean iteration count less than this (relative)

FIELDS = ["N", "steps", "measure", "mode", "id", "key", "name", "status", "verdict", "valid", "iter_avg", "iter_max",
          "time_avg_ms", "time_median_ms", "time_min_ms", "time_max_ms", "ms_per_iter", "cost_sum", "cost_dev",
          "steps_failed", "steps_at_max_iter", "max_eq_residual", "run_dir", "note"]
STAT_FIELD = {"mean": "time_avg_ms", "median": "time_median_ms"}


def label(key: str, mode: str) -> str:
    """Name of a bar in the figures and in --include: '<key>' = sigma 0, '<key> (reg)' = sigma > 0."""
    return key + (" (reg)" if mode == "kkt-reg" else "")


def rank_field(measure: str, stat: str) -> str:
    """Record field the solvers are ranked by."""
    return "ms_per_iter" if measure == "converged" else STAT_FIELD[stat]


def _num(v, fmt: str = ".4g") -> str:
    return "-" if v is None or v != v else format(v, fmt)


def timed(r: dict, field: str) -> bool:
    """The run finished and has a value to draw (also when its result differs from the reference)."""
    v = r.get(field)
    return r["status"] == "COMPLETED" and v is not None and v == v and not _no_iterations(r)


def _no_iterations(r: dict) -> bool:
    """The linear solver failed in every step (no ISPD iteration accepted): its time is that of a failed
    factorization, not of a solve, so it is not drawn."""
    return r["status"] == "COMPLETED" and r.get("iter_avg") is not None and r["iter_avg"] < 0.5


# ------------------------------------------------------------------------------------------------ running
def _args(o: Opts, mode: str, n: int, solver_id: int) -> Tuple[List[str], List[str]]:
    args = ["--solvers", "ispd", "--horizon", str(n), "--init", "fixed", "--linear-solver", str(solver_id),
            "--run-times", str(o.run_times), "--max-iter", str(o.max_iter)]
    steps = o.steps_by_n.get(n, o.steps)
    if steps:
        args += ["--loop-size", str(steps)]
    if o.config:
        args += ["--config", o.config]
    ov = [PROGRESS]
    if o.measure == "fixed":
        # epsilon_convergence = 0 switches the convergence test off: every MPC step runs exactly max_iter
        # iterations, so all solvers do the same work and the time per step compares the linear solvers only
        ov.append("cg2o.epsilon_convergence=0")
    ov += [*o.overrides, f"cg2o.equality_regularization={o.regularization if mode == 'kkt-reg' else 0}"]
    return args, ov


def _matches(s: dict, names) -> bool:
    names = {str(x).lower() for x in names}
    return str(s["id"]) in names or s["key"].lower() in names


def parse_job(token: str, catalog: List[dict]) -> Tuple[str, dict]:
    """'14' / 'umfpack' -> (kkt, entry); '14reg', '14 reg', '14(reg)', 'umfpack_reg' -> (kkt-reg, entry)."""
    t = token.strip().lower().replace(" ", "")
    mode = "kkt"
    for suffix in ("(reg)", "reg"):
        base = t[:-len(suffix)].rstrip("-_:") if t.endswith(suffix) else ""
        if base and any(_matches(s, [base]) for s in catalog):
            t, mode = base, "kkt-reg"
            break
    entry = next((s for s in catalog if _matches(s, [t])), None)
    if entry is None:
        raise ValueError(f"--linear-solver {token!r}: no such solver (see `run_experiment.py list-solvers`)")
    if not entry["available"]:
        raise ValueError(f"--linear-solver {token!r}: {entry['key']} is not available in this build ({entry['note']})")
    return mode, entry


def _plan(o: Opts, catalog: List[dict]) -> Tuple[Tuple[str, dict], List[Tuple[str, dict]]]:
    """(reference job, other jobs) of one horizon; a job is (mode, catalog entry)."""
    avail = [s for s in catalog if s["available"]]
    ref_entry = next((s for s in avail if s["key"] == REFERENCE), None)
    if ref_entry is None:
        raise RuntimeError(f"the reference solver '{REFERENCE}' is not available in this build")
    jobs: List[Tuple[str, dict]] = []
    if o.ls_jobs:                                    # --linear-solver 0 0reg 1 1reg: exactly these runs
        for tok in o.ls_jobs:
            job = parse_job(tok, catalog)
            if job not in jobs:
                jobs.append(job)
        ref_job = ("kkt", ref_entry)
        return ref_job, [j for j in jobs if j != ref_job]
    if o.solvers is None:
        chosen = [s for s in avail if s["id"] in DEFAULT_SOLVERS]
    elif "all" in {str(x).lower() for x in o.solvers}:
        chosen = avail
    else:
        chosen = [s for s in avail if _matches(s, o.solvers)]
    ref_mode = "kkt" if "kkt" in o.modes else o.modes[0]
    for mode in o.modes:
        for s in chosen:
            if mode == "kkt-reg" and _matches(s, o.no_reg_solvers):
                continue
            if (mode, s["key"]) != (ref_mode, REFERENCE):
                jobs.append((mode, s))
    return (ref_mode, ref_entry), jobs


def _judge(rec: dict, ref: Optional[dict], measure: str) -> None:
    """valid / verdict / cost_dev of a finished run, against the reference run of the same horizon."""
    rec["valid"], rec["cost_dev"] = False, None
    if rec["status"] != "COMPLETED":
        rec["verdict"] = rec["status"].lower()
        return
    if rec["steps_failed"]:
        rec["verdict"] = f"{rec['steps_failed']} failed steps"
        return
    if _no_iterations(rec):
        rec["verdict"] = "fails (0 iterations: factorization fails)"
        return
    if ref is None or ref is rec:
        rec["valid"] = True
        rec["verdict"] = "reference" if ref is rec else "ok (no reference)"
        return
    cdev = abs(rec["cost_sum"] - ref["cost_sum"]) / max(abs(ref["cost_sum"]), 1e-12)
    idev = abs(rec["iter_avg"] - ref["iter_avg"]) / max(ref["iter_avg"], 1e-12)
    rec["cost_dev"] = cdev
    if cdev > COST_TOL:
        rec["verdict"] = f"different result (cost {cdev:.1e} off)"
    elif measure == "fixed" and idev > ITER_TOL:     # converged: other iteration counts are what is measured
        rec["verdict"] = f"stopped early ({rec['iter_avg']:.1f} vs {ref['iter_avg']:.1f} it.)"
    else:
        rec["valid"] = True
        rec["verdict"] = "ok"


def _write_csv(exp: Experiment, records: List[dict]) -> Path:
    p = exp.dir / "linear_solvers.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in FIELDS})
    return p


def run_linear_solvers(exp: Experiment, o: Opts) -> None:
    catalog = list_linear_solvers()
    for s in catalog:
        if not s["available"]:
            exp.notes.append(f"Linear solver {s['id']} ({s['key']}) is not available in this build: {s['note']}")
    ref_job, jobs = _plan(o, catalog)
    horizons = sorted(o.horizons)
    total = len(horizons) * (1 + len(jobs))
    print(f"{total} runs, measure '{o.measure}' ({MEASURE_INFO[o.measure]}, max_iter {o.max_iter}): horizons {horizons}, "
          f"steps {[o.steps_by_n.get(n, o.steps) or 'all' for n in horizons]}, {o.run_times} solves per step, "
          f"reference {label(ref_job[1]['key'], ref_job[0])}", flush=True)
    print("runs: " + ", ".join(label(s["key"], m) for m, s in [ref_job, *jobs]), flush=True)
    timeout = o.timeout if o.timeout is not None else (300.0 if o.measure == "fixed" else 900.0)
    records: List[dict] = []
    i = 0
    for n in horizons:                       # small horizons first: quick results, and failures are known early
        ref = None
        for mode, s in [ref_job, *jobs]:     # the reference first
            i += 1
            key = s["key"]
            rec = {"N": n, "steps": o.steps_by_n.get(n, o.steps), "measure": o.measure, "mode": mode, "id": s["id"],
                   "key": key, "name": s["name"], "status": "", "note": s["note"], "run_dir": ""}
            # crashed / timed out / no iteration before: not again at a larger horizon (a different result is still timed)
            earlier = [r for r in records if (r["key"], r["mode"]) == (key, mode)
                       and (r["status"] not in ("COMPLETED", "SKIPPED") or _no_iterations(r))]
            slow = "slow" in s["note"].lower() or "O(n^3)" in s["note"]
            skip = ""
            if slow and n > 10 and not o.include_slow and not o.ls_jobs:
                skip = "slow solver skipped for N>10 (use --include-slow)"
            elif earlier:
                skip = f"not run: {earlier[0]['verdict']} at N={earlier[0]['N']}"
            if skip:
                rec.update(status="SKIPPED", valid=False, verdict="skipped", note=skip)
                records.append(rec)
                continue
            print(f"\n[{i}/{total}] N={n} {label(key, mode)} (id {s['id']})", flush=True)
            args, ov = _args(o, mode, n, s["id"])        # the id: keys need not be unique
            res = run_macc(args, exp.runs_dir, f"ls_N{n}_{mode}_{key}", overrides=ov, timeout=timeout, echo=False)
            exp.runs.append(res)
            rec["status"] = res.status
            rec["run_dir"] = str(res.dir.relative_to(exp.dir)) if res.dir else ""
            if res.ok:
                d = res.solver_summary("ispd")
                rec.update(iter_avg=d["iterations"]["mean"], iter_max=d["iterations"]["max"],
                           time_avg_ms=d["time_ms"]["mean"], time_min_ms=d["time_ms"]["min"],
                           time_max_ms=d["time_ms"]["max"], ms_per_iter=d["time_per_iter_total_ms"],
                           cost_sum=d["cost_sum"], steps_failed=d["steps_failed"],
                           steps_at_max_iter=d["steps_hit_max_iter"], max_eq_residual=d["max_eq_residual"])
                try:
                    rec["time_median_ms"] = float(np.median(res.steps()["ispd_time_ms"]))
                except Exception:
                    rec["time_median_ms"] = None
            else:
                rec["note"] = (res.error or res.status)[:120]
            if (mode, s) == ref_job and res.ok:
                ref = rec
            _judge(rec, ref, o.measure)
            print(f"    {rec['verdict']}" + (f"   {_num(rec.get('time_avg_ms'))} ms/step (median "
                                            f"{_num(rec.get('time_median_ms'))}), {_num(rec.get('iter_avg'), '.1f')} it., "
                                            f"{_num(rec.get('ms_per_iter'))} ms/iter"
                                            if rec["status"] == "COMPLETED" else ""), flush=True)
            records.append(rec)
            _write_csv(exp, records)
            exp.write_info()
    analyze_linear_solvers(exp, o, records)


# ------------------------------------------------------------------------------------------------ report
def analyze_linear_solvers(exp: Experiment, o: Opts, records: List[dict]) -> None:
    exp.add_output(_write_csv(exp, records))
    tf, st = rank_field(o.measure, o.stat), STAT_FIELD[o.stat]
    by = "time per iteration" if o.measure == "converged" else f"{o.stat} time per MPC step"
    text, best_lines = [], []
    for n in sorted({r["N"] for r in records}):
        grp = [r for r in records if r["N"] == n]
        ranked = sorted([r for r in grp if timed(r, tf)], key=lambda r: r[tf])   # valid or not: every timed run
        good = [r for r in ranked if r["valid"]]
        base = (good or ranked or [None])[0]
        others = [r for r in grp if r not in ranked]
        text.append(f"\n  N = {n}, {grp[0]['steps'] or 'all'} steps   (ranked by {by}, this machine; "
                    f"'x best' = relative to the fastest valid solver)")
        text.append(f"  {'rank':>4} {'id':>3} {'solver':<28} {'ms/step':>9} {'ms/iter':>9} {'iter':>6} "
                    f"{'x best':>7}  verdict")
        for k, r in enumerate(ranked, 1):
            text.append(f"  {k:>4} {r['id']:>3} {label(r['key'], r['mode']):<28} {_num(r.get(st)):>9} "
                        f"{_num(r.get('ms_per_iter'), '.3g'):>9} {_num(r.get('iter_avg'), '.1f'):>6} "
                        f"{r[tf] / base[tf]:>7.2f}  {r['verdict']}")
        for r in others:
            text.append(f"  {'-':>4} {r['id']:>3} {label(r['key'], r['mode']):<28} {'':>9} {'':>9} {'':>6} {'':>7}  "
                        f"{r['verdict']}" + (f" ({r['note']})" if r["status"] != "COMPLETED" and r["note"] else ""))
        if good:
            unit = "ms/iter" if o.measure == "converged" else "ms/step"
            extra = lambda r: f", {r['iter_avg']:.1f} it." if o.measure == "converged" else ""
            best_lines.append(f"N={n:<3d} best: {label(good[0]['key'], good[0]['mode']):<24} {good[0][tf]:.4g} {unit}"
                              + extra(good[0]) + (f"   (runner-up {label(good[1]['key'], good[1]['mode'])} "
                                                  f"{good[1][tf]:.4g} {unit}{extra(good[1])})" if len(good) > 1 else ""))
    modes = "\n".join(f"  {m}: {MODE_INFO[m][0]}\n      {MODE_INFO[m][1]}" for m in MODE_INFO
                      if any(r["mode"] == m for r in records))
    exp.add_section("Ranking of the linear solvers",
                    f"  measure '{o.measure}': {MEASURE_INFO[o.measure]} (max_iter {o.max_iter})\n" + modes + "\n"
                    + "\n".join(text))
    if best_lines:
        rule = (f"every step ran exactly {o.max_iter} ISPD iterations" if o.measure == "fixed" else
                f"every step ran to convergence (limit {o.max_iter} iterations)")
        exp.add_section("Best linear solver", "\n".join(best_lines + [
            "",
            f"'best' counts only solvers whose run finished without failed steps AND reproduced the summed cost of the",
            f"reference ({REFERENCE} on the exact KKT matrix, the paper default) within {COST_TOL:g}"
            + (f" and its iteration count within {ITER_TOL:.0%}" if o.measure == "fixed" else "") + ".",
            f"Solvers with a different result are listed and drawn (hatched) with their time all the same.",
            f"'(reg)' = equality regularization sigma = {o.regularization:g}; {rule}."]))
    if o.plots:
        try:
            exp.add_output(*draw_figures(exp.dir, records, o))
        except Exception as e:
            exp.notes.append(f"Linear-solver figures failed: {e!r}")


# ------------------------------------------------------------------------------------------------ figures
#: (record field, axis label, unit of the bar text) of the figures of each measure
def _specs(o: Opts) -> List[Tuple[str, str, str]]:
    if o.measure == "converged":
        return [("ms_per_iter", "Solver time per iteration [ms]", "ms"),
                ("iter_avg", "Iterations to terminate, mean per MPC step", "it.")]
    return [(STAT_FIELD[o.stat], f"Solver time per MPC step, {o.stat} [ms]", "ms")]


def _select_rows(records: List[dict], o: Opts, tf: str) -> Tuple[List[dict], List[Tuple[str, str]], List[int]]:
    """Records to draw, the bars (key, mode) from top to bottom, and the horizons."""
    if o.horizons:
        records = [r for r in records if r["N"] in o.horizons]
    # a bar needs the chosen statistic (an interrupted run or an older experiment may lack it)
    records = [dict(r, valid=bool(r["valid"]) and r.get(tf) is not None, timed=timed(r, tf)) for r in records]
    skip = {str(x).lower() for x in o.no_reg_solvers}     # older experiments ran them with sigma too
    if not o.ls_jobs:
        records = [r for r in records
                   if not (r["mode"] == "kkt-reg" and (str(r["id"]) in skip or r["key"].lower() in skip))]
    if o.hide_failed:       # only valid results: no failed, skipped or different-result entries at any horizon
        records = [r for r in records if r["valid"] and r["timed"]]
    if not records:
        raise ValueError("no results to draw")
    ns = sorted({r["N"] for r in records})
    big = {(r["key"], r["mode"]): r[tf] for r in records if r["N"] == ns[-1] and r["timed"]}
    small = {(r["key"], r["mode"]): r[tf] for r in records if r["N"] == ns[0] and r["timed"]}
    rows = sorted({(r["key"], r["mode"]) for r in records},       # fastest at the largest N on top, failures last
                  key=lambda km: (km not in big, big.get(km, 0.0), small.get(km, float("inf")), label(*km)))
    if o.include:                                                 # chosen bars, in the order given
        norm = lambda t: t.replace(" ", "").lower()
        chosen: List[Tuple[str, str]] = []
        for pat in o.include:
            chosen += [km for km in rows if fnmatch.fnmatchcase(norm(label(*km)), norm(pat)) and km not in chosen]
        if not chosen:
            raise ValueError(f"--include {list(o.include)} matches none of: {', '.join(label(*km) for km in rows)}")
        rows = chosen
    return records, rows, ns


def _reason(r: dict) -> str:
    return r["note"] if r["status"] == "SKIPPED" else r["verdict"]


def _differs(r: dict) -> str:
    """Short note on a timed bar whose result is not valid."""
    if r["valid"]:
        return ""
    return f"  [cost {r['cost_dev']:.0e} off]" if r.get("cost_dev") else f"  [{r['verdict']}]"


#: text colours of the numbers on the bars, one per quantity
NUM_COLORS = {"ratio": "#c2185b", "time": "#00796b", "iter": "#5e35b1"}
NUM_LABELS = {"ratio": "x fastest", "time": "(avg. time, avg. time/iter) [ms]",
              "time_fixed": "(avg. time) [ms]", "iter": "[mean iter, max iter]"}


def _ctext(ax, x, y, parts, fontsize, transform=None):
    """One line of text made of (text, colour) parts, drawn one after the other."""
    prev = ax.text(x, y, parts[0][0], color=parts[0][1], va="center", fontsize=fontsize,
                   transform=transform or ax.transData)
    for txt, c in parts[1:]:
        prev = ax.annotate(txt, xy=(1, 0.5), xycoords=prev, va="center", ha="left", color=c, fontsize=fontsize)
    return prev


def _sci(v) -> str:
    """Short scientific notation: 1.3e-1, 1.2e0."""
    if v is None:
        return "-"
    m, e = f"{v:.1e}".split("e")
    return f"{m}e{int(e)}"


def _parts(r: dict, o: Opts, field: str, best: float, clipped: bool = False) -> list:
    """Coloured numbers of one bar: (average time, average time per iteration xratio) and [iterations mean, max]
    (converged); (average time xratio) (fixed). The ratio is that of the bar's quantity to the fastest bar."""
    t = r[field]
    ratio = f"x{t / best:.2f}"
    pre = ">> " if clipped else ""
    it = f"[{_num(r.get('iter_avg'), '.1f')}, {_num(r.get('iter_max'), '.0f')}]"
    if field == "iter_avg":
        return [(pre + it, NUM_COLORS["iter"])]
    tm = r.get(STAT_FIELD[o.stat])
    if o.measure == "converged":
        tpi = r.get("ms_per_iter")
        return [(pre + ratio, NUM_COLORS["ratio"]), (f" ({_sci(tm)}, {_sci(tpi)})", NUM_COLORS["time"]),
                ("  -  ", style.MUTED), (it, NUM_COLORS["iter"])]
    return [(pre + ratio, NUM_COLORS["ratio"]), (f" ({_sci(tm)})", NUM_COLORS["time"])]


def _bar(ax, y, width, r, height, left=0.0):
    c = style.CATEGORICAL[1] if r["mode"] == "kkt-reg" else style.CATEGORICAL[0]
    if r["valid"]:
        ax.barh(y, width, left=left, height=height, zorder=3, color=c)
    else:                                   # timed, but the result differs from the reference
        ax.barh(y, width, left=left, height=height, zorder=3, facecolor="none", edgecolor=c, hatch="////",
                linewidth=0.6)


def _legend_handles(modes: Sequence[str], o: Opts, any_differs: bool):
    names = {"kkt": "exact KKT, sigma = 0", "kkt-reg": f"(reg): sigma = {o.regularization:g}"}
    hs = [plt.Rectangle((0, 0), 1, 1, color=style.CATEGORICAL[1 if m == "kkt-reg" else 0]) for m in modes]
    ls = [names[m] for m in modes]
    if any_differs:
        hs.append(plt.Rectangle((0, 0), 1, 1, facecolor="none", edgecolor=style.MUTED, hatch="////"))
        ls.append("result differs from the reference")
    for q in (("ratio", "time", "iter") if o.measure == "converged" else ("ratio", "time_fixed")):
        hs.append(plt.Line2D([], [], color=NUM_COLORS["time" if q == "time_fixed" else q], lw=0, marker="s",
                             markersize=5))
        ls.append(NUM_LABELS[q])
    return hs, ls


def _save(fig, stem: Path) -> List[Path]:
    stem.parent.mkdir(exist_ok=True)
    out = []
    for fmt in ("pdf", "png"):
        fig.savefig(stem.with_suffix("." + fmt), bbox_inches="tight")
        out.append(stem.with_suffix("." + fmt))
    plt.close(fig)
    return out


def draw_figures(folder: Path, records: List[dict], o: Opts) -> List[Path]:
    """figures/linear_solvers.(pdf|png): one panel per horizon (and per quantity), linear axis from zero (bars longer
    than CLIP x the fastest are cut, the label keeps the value); figures/linear_solvers_grouped.(pdf|png): one panel,
    a bar per horizon and solver, log axis. Measure fixed: time per MPC step; converged: time per iteration (and
    iterations to terminate)."""
    style.apply(o.palette, o.latex)
    specs = _specs(o)
    tf = specs[0][0]
    records, rows, ns = _select_rows(records, o, tf)
    look = {(r["key"], r["mode"], r["N"]): r for r in records}
    ylabels = [label(*km) for km in rows]
    ys = list(range(len(rows)))[::-1]
    modes = sorted({km[1] for km in rows}, key=lambda m: m != "kkt")
    any_differs = any(r["timed"] and not r["valid"] for r in records)
    out = []

    # one panel per horizon (columns) and quantity (rows); colour = mode, hatched = different result
    CLIP = 6.0
    fig, axes = plt.subplots(len(specs), len(ns), figsize=(3.4 * len(ns) + 1.4, len(specs) * (0.8 + 0.22 * len(rows))),
                             constrained_layout=True, squeeze=False, sharey=True)
    for (field, xlabel, unit), axrow in zip(specs, axes):
        for ax, n in zip(axrow, ns):
            rs = [look[(*km, n)] for km in rows if (*km, n) in look]
            vals = [r[field] for r in rs if r["timed"] and r.get(field) is not None]
            good = [r[field] for r in rs if r["valid"] and r.get(field) is not None]
            best = min(good or vals or [1.0])
            xmax = min(best * CLIP, max(vals, default=best))
            for y, km in zip(ys, rows):
                r = look.get((*km, n))
                if r is None:
                    continue
                if r["timed"] and r.get(field) is not None:
                    t = r[field]
                    _bar(ax, y, min(t, xmax), r, 0.62)
                    _ctext(ax, min(t, xmax) + xmax * 0.015, y,
                           _parts(r, o, field, best, t > xmax) + [(_differs(r), style.MUTED)], 6.5)
                else:
                    ax.text(0.01, y, _reason(r), va="center", fontsize=6, color=style.MUTED, style="italic",
                            transform=ax.get_yaxis_transform())
            ax.set_xlim(0, xmax * (2.6 if o.measure == "converged" and field != "iter_avg" else 1.6))
            ax.set_title(f"N = {n}", loc="left", fontsize=8)
            ax.set_xlabel(xlabel)
            ax.grid(True, axis="x", linewidth=0.6, alpha=0.4, zorder=0)
            ax.tick_params(axis="y", length=0)
        axrow[0].set_yticks(ys)
        axrow[0].set_yticklabels(ylabels, fontsize=6.5)
        axrow[0].set_ylim(-0.7, len(rows) - 0.3)
    fig.legend(*_legend_handles(modes, o, any_differs), loc="outside upper center", ncol=3, frameon=False, fontsize=7)
    out += _save(fig, folder / "figures" / "linear_solvers")

    # one panel, a block per horizon (fastest first, factor to the fastest valid solver of that horizon); log axis
    xlabel = specs[0][1]
    blocks = []
    for n in ns:
        rs = [look[(*km, n)] for km in rows if (*km, n) in look]
        blocks.append((n, sorted([r for r in rs if r["timed"]], key=lambda r: r[tf]), [r for r in rs if not r["timed"]]))
    ts = [r[tf] for _, ok, _ in blocks for r in ok]
    if not ts:
        raise ValueError("no timed run to draw")
    lo = min(ts) / 1.5
    n_lines = sum(1 + len(ok) + len(bad) for _, ok, bad in blocks)
    fig, ax = plt.subplots(figsize=(6.4, 0.7 + 0.17 * n_lines), constrained_layout=True)
    y, ticks, tick_labels, heads = n_lines, [], [], []
    for n, ok, bad in blocks:
        y -= 1
        ticks.append(y), tick_labels.append(f"N = {n}"), heads.append(len(ticks) - 1)
        if y < n_lines - 1:
            ax.axhline(y + 0.5, color=style.MUTED, linewidth=0.5, alpha=0.6)
        good = [r for r in ok if r["valid"]]
        best = (good or ok)[0][tf]
        for r in ok:
            y -= 1
            t = r[tf]
            _bar(ax, y, t - lo, r, 0.7, left=lo)
            _ctext(ax, t * 1.05, y, _parts(r, o, tf, best) + [(_differs(r), style.MUTED)], 6)
            ticks.append(y), tick_labels.append(label(r["key"], r["mode"]))
        for r in bad:
            y -= 1
            ax.text(lo * 1.05, y, "skipped" if r["status"] == "SKIPPED" else r["verdict"], va="center",
                    fontsize=5.8, color=style.MUTED, style="italic")
            ticks.append(y), tick_labels.append(label(r["key"], r["mode"]))
    ax.set_xscale("log")
    ax.set_xlim(lo, max(ts) * (30 if o.measure == "converged" else 8))
    ax.set_yticks(ticks)
    ax.set_yticklabels(tick_labels, fontsize=6.5)
    for i in heads:
        ax.get_yticklabels()[i].set_fontweight("bold")
        ax.get_yticklabels()[i].set_fontsize(7.5)
    ax.set_ylim(-0.6, n_lines - 0.4)
    ax.set_xlabel(xlabel + ", log axis")
    ax.grid(True, axis="x", linewidth=0.6, alpha=0.4, zorder=0)
    ax.tick_params(axis="y", length=0)
    ax.legend(*_legend_handles(modes, o, any_differs), frameon=False, fontsize=7, loc="upper right")
    out += _save(fig, folder / "figures" / "linear_solvers_grouped")
    return out


# ------------------------------------------------------------------------------------------------ replot
def load_records(folder: Path) -> List[dict]:
    """Records of an experiment (finished or interrupted), from its linear_solvers.csv."""
    num = ["iter_avg", "iter_max", "time_avg_ms", "time_median_ms", "time_min_ms", "time_max_ms", "ms_per_iter",
           "cost_sum", "cost_dev", "max_eq_residual"]
    recs = []
    with open(folder / "linear_solvers.csv", newline="") as f:
        for r in csv.DictReader(f):
            r["N"] = int(r["N"])
            r["steps"] = int(r["steps"]) if r.get("steps") else None
            r["measure"] = r.get("measure") or "fixed"       # older experiments: always a fixed iteration count
            r["valid"] = r["valid"] in ("True", "true", "1")
            for k in num:
                r[k] = float(r[k]) if r.get(k) else None
            recs.append(r)
    return recs


def replot_linear_solvers(folder: Path, o: Opts) -> List[Path]:
    """Redraw the figures from the stored results; no solver is run."""
    records = load_records(folder)
    o.measure = records[0]["measure"] if records else o.measure
    if o.measure == "fixed" and o.stat == "median" and not any(r.get("time_median_ms") is not None for r in records):
        raise ValueError("this experiment has no median times (older version): use --stat mean")
    return draw_figures(folder, records, o)
