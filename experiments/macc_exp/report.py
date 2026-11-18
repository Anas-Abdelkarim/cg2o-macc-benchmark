"""Result tables (CSV + fixed-width text) built from the runs' summary.json."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import paper
from .runner import RunResult

FIELDS = ["N", "solver", "description", "steps", "iter_avg", "iter_min", "iter_max",
          "time_avg_ms", "time_min_ms", "time_max_ms", "ms_per_iter", "cost_sum",
          "steps_at_max_iter", "steps_failed", "max_eq_residual", "max_ineq_violation",
          "paper_iter_avg", "paper_iter_min", "paper_iter_max",
          "paper_time_avg_ms", "paper_time_min_ms", "paper_time_max_ms", "paper_source"]


def comparison_rows(runs: Dict[int, RunResult], solvers: Sequence[str],
                    ref: Optional[dict] = None) -> List[dict]:
    ref = paper.load() if ref is None else ref
    rows = []
    for n in sorted(runs):
        run = runs[n]
        if not run.ok:
            continue
        for s in solvers:
            if s not in run.summary["solvers"]:
                continue
            d = run.solver_summary(s)
            p = paper.lookup(ref, d.get("paper_key"), n) or {}
            src = (ref.get(d.get("paper_key"), {}) or {}).get("source", "")
            rows.append({
                "N": n, "solver": s, "description": d["description"], "steps": d["iterations"]["n"],
                "iter_avg": d["iterations"]["mean"], "iter_min": d["iterations"]["min"],
                "iter_max": d["iterations"]["max"], "time_avg_ms": d["time_ms"]["mean"],
                "time_min_ms": d["time_ms"]["min"], "time_max_ms": d["time_ms"]["max"],
                "ms_per_iter": d.get("time_per_iter_total_ms"), "cost_sum": d["cost_sum"],
                "steps_at_max_iter": d["steps_hit_max_iter"], "steps_failed": d["steps_failed"],
                "max_eq_residual": d["max_eq_residual"], "max_ineq_violation": d["max_ineq_violation"],
                "paper_iter_avg": p.get("iter_avg"), "paper_iter_min": p.get("iter_min"),
                "paper_iter_max": p.get("iter_max"), "paper_time_avg_ms": p.get("time_avg_ms"),
                "paper_time_min_ms": p.get("time_min_ms"), "paper_time_max_ms": p.get("time_max_ms"),
                "paper_source": src})
    return rows


def write_csv(rows: List[dict], path: Path, fields: Sequence[str] = FIELDS) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def _f(v, fmt="{:.1f}") -> str:
    return "-" if v is None or v == "" else fmt.format(v)


def comparison_text(rows: List[dict], with_time_paper: bool = False) -> str:
    """Fixed-width table: this run next to the paper's numbers."""
    head = (f"{'N':>3}  {'solver':<6} {'iter avg':>8} {'min':>4} {'max':>5} | "
            f"{'t avg [ms]':>10} {'min':>7} {'max':>8} {'ms/iter':>8} | "
            f"{'paper it.avg':>12} {'min':>4} {'max':>5}")
    if with_time_paper:
        head += f" | {'paper t avg':>11} {'min':>6} {'max':>7}"
    lines = [head, "-" * len(head)]
    for r in rows:
        line = (f"{r['N']:>3}  {r['solver']:<6} {_f(r['iter_avg']):>8} {_f(r['iter_min'], '{:.0f}'):>4} "
                f"{_f(r['iter_max'], '{:.0f}'):>5} | {_f(r['time_avg_ms'], '{:.3g}'):>10} "
                f"{_f(r['time_min_ms'], '{:.3g}'):>7} {_f(r['time_max_ms'], '{:.3g}'):>8} "
                f"{_f(r['ms_per_iter'], '{:.3g}'):>8} | {_f(r['paper_iter_avg']):>12} "
                f"{_f(r['paper_iter_min'], '{:.0f}'):>4} {_f(r['paper_iter_max'], '{:.0f}'):>5}")
        if with_time_paper:
            line += (f" | {_f(r['paper_time_avg_ms']):>11} {_f(r['paper_time_min_ms']):>6} "
                     f"{_f(r['paper_time_max_ms']):>7}")
        lines.append(line)
    return "\n".join(lines)
