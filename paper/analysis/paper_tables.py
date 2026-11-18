#!/usr/bin/env python3
"""Numbers of the MACC tables of the paper (Sec. VI), computed from experiment folders.

  Table IV   cg2o vs barrier IPM, feasible start          (fig2 experiment)
  Table V    cg2o vs IPOPT, cold and warm                  (fig3 experiment)
  Table VII  large-scale problems, time per MPC problem    (linear-solvers experiment(s) with N = 3e4 / 3e5)

Iteration counts, limits and residuals are reproducible; times depend on the machine.

Each table is printed and also saved INTO the experiment folder it was computed from:
  <fig2 folder>/paper_table_iv.txt (+ .json), <fig3 folder>/paper_table_v.txt (+ .json),
  <large folder>/paper_table_vii.txt (+ .json).
run_experiment.py fig2 / fig3 does this automatically at the end of every run.

Without --fig2 / --fig3 the newest COMPLETE folders in results/experiments/ are used (all of N = 3, 15, 30 over the
whole driving cycle; --quick runs are skipped). With one of them, only that table is made.

usage: paper_tables.py [--fig2 DIR] [--fig3 DIR] [--large DIR [DIR ...]] [--json FILE]
"""
import argparse
import contextlib
import csv
import io
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FULL_CYCLE, experiment_dir, is_complete, runs_by_horizon  # noqa: E402

HORIZONS = (3, 15, 30)


def stats(d, s, ref=None):
    it, t = d[f'{s}_iterations'], d[f'{s}_time_ms']
    r = dict(n=len(d), it_mean=it.mean(), it_min=it.min(), it_max=it.max(),
             t_mean=t.mean(), t_p95=t.quantile(.95), t_max=t.max(), ms_per_iter=t.sum() / it.sum(),
             limit=int(d[f'{s}_hit_max_iter'].sum()), failed=int((d[f'{s}_success'] == 0).sum()),
             eq_max=d[f'{s}_eq_residual'].max(), ineq_max=d[f'{s}_ineq_violation'].max())
    if ref:   # objective relative to the reference solver (cg2o)
        rc = (d[f'{s}_cost'] - d[f'{ref}_cost']) / d[f'{ref}_cost'].abs()
        r.update(dcost_median=rc.abs().median(), frac_higher_1e6=(rc > 1e-6).mean(), frac_lower_1e6=(rc < -1e-6).mean())
    return {k: float(v) for k, v in r.items()}


def table_iv(exp):
    print(f'\nTable IV  (from {exp})')
    print(f'{"N":>3} {"solver":<12} {"iter avg (min, max)":>20} {"time avg / max [ms]":>21} {"ms/iter":>8} '
          f'{"limit":>5} {"max |h|":>9} {"max viol.":>9}')
    out = {}
    for n, f in runs_by_horizon(exp).items():
        d = pd.read_csv(f)
        for s, name in (('bipm', 'Barrier IPM'), ('ispd', 'cg2o')):
            r = stats(d, s, 'ispd' if s != 'ispd' else None)
            out[f'N{n}_{s}'] = r
            print(f'{n:>3} {name:<12} {r["it_mean"]:>8.1f} ({r["it_min"]:.0f}, {r["it_max"]:.0f})'
                  f'{r["t_mean"]:>11.3g} / {r["t_max"]:<8.3g} {r["ms_per_iter"]:>8.2g} {r["limit"]:>5.0f} '
                  f'{r["eq_max"]:>9.1e} {r["ineq_max"]:>9.1e}')
        print(f'    cg2o faster on average by {out[f"N{n}_bipm"]["t_mean"] / out[f"N{n}_ispd"]["t_mean"]:.1f}x; '
              f'median relative objective difference {out[f"N{n}_bipm"]["dcost_median"]:.1e}')
    return out


def table_v(exp):
    print(f'\nTable V  (from {exp})')
    print(f'{"N":>3} {"solver":<12} {"it avg":>6} {"max":>4} {"t avg":>7} {"P95":>7} {"max":>7} {"lim":>4} '
          f'{"max |h|":>9} {"max viol.":>9}')
    out = {}
    for n, f in runs_by_horizon(exp).items():
        d = pd.read_csv(f)
        for s, name in (('ipopt', 'IPOPT, cold'), ('ipopt_warm', 'IPOPT, warm'), ('ispd', 'cg2o, cold')):
            r = stats(d, s, 'ispd' if s != 'ispd' else None)
            out[f'N{n}_{s}'] = r
            print(f'{n:>3} {name:<12} {r["it_mean"]:>6.1f} {r["it_max"]:>4.0f} {r["t_mean"]:>7.3g} {r["t_p95"]:>7.3g} '
                  f'{r["t_max"]:>7.3g} {r["limit"]:>4.0f} {r["eq_max"]:>9.1e} {r["ineq_max"]:>9.1e}')
        c = out[f'N{n}_ispd']['t_mean']
        print(f'    cg2o faster on average: {out[f"N{n}_ipopt"]["t_mean"] / c:.1f}x than IPOPT cold, '
              f'{out[f"N{n}_ipopt_warm"]["t_mean"] / c:.1f}x than IPOPT warm; '
              f'fewer iterations than IPOPT cold: {100 * (1 - out[f"N{n}_ispd"]["it_mean"] / out[f"N{n}_ipopt"]["it_mean"]):.0f}%')
    return out


def table_vii(folders):
    rows = []
    for f in folders:
        rows += [r for r in csv.DictReader(open(Path(f) / 'linear_solvers.csv')) if int(r['N']) >= 10000]
    if not rows:
        print('\nTable VII: no linear-solver rows with N >= 10000 in', ', '.join(map(str, folders)))
        return {}
    print(f'\nTable VII  (from {", ".join(Path(f).name for f in folders)})')
    ns = sorted({int(r['N']) for r in rows})
    keys = []
    for r in rows:
        if (r['mode'], r['key']) not in keys:
            keys.append((r['mode'], r['key']))
    val = {(r['mode'], r['key'], int(r['N'])): float(r['time_avg_ms']) / 1000 for r in rows}
    print(f'{"formulation":<12} {"linear solver":<14} ' + ' '.join(f'{"N = %d [s]" % n:>14}' for n in ns))
    out = {}
    for mode, key in keys:
        cells = [val.get((mode, key, n)) for n in ns]
        out[f'{mode}_{key}'] = dict(zip(map(str, ns), cells))
        print(f'{("K0" if mode == "kkt" else "K_sigma"):<12} {key:<14} ' +
              ' '.join(f'{c:>14.3g}' if c is not None else f'{"-":>14}' for c in cells))
    return out


class _Tee(io.StringIO):
    """Writes to the terminal and keeps a copy."""
    def __init__(self, out):
        super().__init__()
        self._out = out

    def write(self, text):
        self._out.write(text)
        return super().write(text)


def save_table(fn, exp, name):
    """Run fn(exp), print its table and save it as <exp>/paper_<name>.txt and .json. Returns the numbers."""
    exp = Path(exp)
    buf = _Tee(sys.stdout)
    with contextlib.redirect_stdout(buf):
        if fn is not table_vii and not is_complete(exp):
            print(f'NOTE: not a complete run (paper: N = 3, 15, 30 over all {FULL_CYCLE} MPC steps); '
                  f'the numbers are for this run only.')
        out = fn([exp]) if fn is table_vii else fn(exp)
    (exp / f'paper_{name}.txt').write_text(buf.getvalue().lstrip('\n'))
    (exp / f'paper_{name}.json').write_text(json.dumps(out, indent=1))
    print(f'saved {exp / f"paper_{name}.txt"}')
    return out


def write_for_experiment(exp, preset):
    """Hook for run_experiment.py: save the paper table of a finished fig2 / fig3 experiment into its folder."""
    name, fn = {'fig2': ('table_iv', table_iv), 'fig3': ('table_v', table_v)}[preset]
    return save_table(fn, exp, name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fig2', help='fig2 experiment folder (default: newest complete one)')
    ap.add_argument('--fig3', help='fig3 experiment folder (default: newest complete one)')
    ap.add_argument('--large', nargs='*', default=[], help='linear-solvers folder(s) with the large horizons')
    ap.add_argument('--json', help='also write all numbers together to this JSON file')
    a = ap.parse_args()
    both = not (a.fig2 or a.fig3)
    result = {}
    if a.fig2 or both:
        result['table_iv'] = save_table(table_iv, experiment_dir(a.fig2, 'fig2'), 'table_iv')
    if a.fig3 or both:
        result['table_v'] = save_table(table_v, experiment_dir(a.fig3, 'fig3'), 'table_v')
    if a.large:
        result['table_vii'] = {}
        for f in a.large:
            result['table_vii'].update(save_table(table_vii, f, 'table_vii'))
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=1))
        print(f'\nwritten {a.json}')


if __name__ == '__main__':
    main()
