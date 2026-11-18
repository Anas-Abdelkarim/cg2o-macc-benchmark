#!/usr/bin/env python3
"""Figures of the MACC benchmark in the paper (Sec. VI), drawn from experiment folders.

  Fig. 2  macc_vs_bipm.pdf              iterations of cg2o and the barrier IPM          (fig2 experiment)
  Fig. 3  macc_vs_ipopt.pdf             solve time and iterations of cg2o and IPOPT     (fig3 experiment)
  Fig. 4  macc_trajectory.pdf           closed loop with cg2o, N = 30                   (fig3 experiment)
  Fig. 7  linear_solver_comparison.pdf  linear solvers inside cg2o, N = 3 and 30        (linear-solvers experiment)

run_experiment.py draws these figures automatically into <experiment folder>/figures/ at the end of every run,
named paper_fig2_macc_vs_bipm.pdf, paper_fig3_macc_vs_ipopt.pdf, paper_fig4_macc_trajectory.pdf,
paper_fig7_linear_solver_comparison.pdf. This script draws them again, or from chosen folders.
By default the newest complete folder of each kind in results/experiments/ is used (--quick runs are skipped).

usage: paper_figures.py [--fig2 DIR] [--fig3 DIR] [--linear DIR] [--out DIR] [--only fig2,fig3,fig4,fig7]
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO, experiment_dir, runs_by_horizon  # noqa: E402

HORIZONS = (3, 15, 30)
VERBOSE = True          # False inside run_experiment.py, which prints the final file names itself
LIMIT = 120

plt.rcParams.update({'font.family': 'serif', 'font.serif': ['Times New Roman', 'Times', 'DejaVu Serif'],
                     'mathtext.fontset': 'stix', 'font.size': 8, 'axes.labelsize': 8,
                     'xtick.labelsize': 7, 'ytick.labelsize': 7, 'legend.fontsize': 7,
                     'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'ps.fonttype': 42,
                     'lines.linewidth': 1.3, 'xtick.major.width': 0.5, 'ytick.major.width': 0.5})

STYLE = {'ispd': ('#0072B2', '-', 'cg2o (ISPD-IPM)'),
         'bipm': ('#CC79A7', '--', 'Barrier IPM, tuned'),
         'ipopt': ('#D55E00', '--', 'IPOPT, cold start'),
         'ipopt_warm': ('#E69F00', ':', 'IPOPT, warm start')}


def survival(ax, values, key):
    """Fraction of problems with at least the given value (step curve)."""
    v = np.sort(np.asarray(values, dtype=float))
    y = 1.0 - np.arange(len(v)) / len(v)
    color, ls, label = STYLE[key]
    ax.step(v, y, where='post', color=color, ls=ls, label=label)


def percent_log_axis(ax):
    ax.set_yscale('log')
    ax.set_ylim(0.8 / 4000, 1.15)
    ax.yaxis.set_major_locator(FixedLocator([1, 0.1, 0.01, 0.001]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{100 * y:g}%'))
    ax.minorticks_off()
    ax.grid(True, which='major', color='0.88', lw=0.5)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=2)


def save(fig, out, stem):
    fig.savefig(out / f'{stem}.pdf')
    fig.savefig(out / f'{stem}.png', dpi=220)
    plt.close(fig)
    if VERBOSE:
        print(f'  {out / stem}.pdf')


def fig2(exp, out):
    runs = runs_by_horizon(exp)
    fig, axs = plt.subplots(1, 3, figsize=(7.16, 1.85), sharey=True, constrained_layout=True)
    for ax, n in zip(axs, HORIZONS):
        d = pd.read_csv(runs[n])
        survival(ax, d.bipm_iterations, 'bipm')
        survival(ax, d.ispd_iterations, 'ispd')
        percent_log_axis(ax)
        ax.set_xlabel('Iterations per MPC step')
        ax.set_title(f'$N={n}$', fontsize=8)
        ax.axvline(LIMIT, color='0.4', lw=0.6, ls=(0, (1, 2)))
        ax.set_xlim(0, 128)
        ax.text(LIMIT - 2, 0.5, 'limit', rotation=90, fontsize=6, color='0.35', ha='right', va='center')
    axs[0].set_ylabel('MPC problems requiring\n$\\geq$ x iterations [%]')
    handles, labels = axs[0].get_legend_handles_labels()
    fig.legend(handles[::-1], labels[::-1], loc='outside upper center', ncol=2, frameon=False)
    save(fig, out, 'macc_vs_bipm')


def fig3(exp, out):
    runs = runs_by_horizon(exp)
    fig, axs = plt.subplots(2, 3, figsize=(7.16, 3.3), constrained_layout=True, sharey=True)
    for j, n in enumerate(HORIZONS):
        d = pd.read_csv(runs[n])
        ax = axs[0, j]
        for key in ('ipopt', 'ipopt_warm', 'ispd'):
            survival(ax, d[f'{key}_time_ms'], key)
        percent_log_axis(ax)
        ax.set_xscale('log')
        ax.set_xlabel('Solve time per MPC step [ms]')
        ax.set_title(f'$N={n}$', fontsize=8)
        ax = axs[1, j]
        for key in ('ipopt', 'ipopt_warm', 'ispd'):
            survival(ax, d[f'{key}_iterations'], key)
        percent_log_axis(ax)
        ax.set_xlabel('Iterations per MPC step')
        ax.set_xlim(0, 125)
        ax.axvline(LIMIT, color='0.4', lw=0.6, ls=(0, (1, 2)))
    for ax in axs[:, 1:].ravel():
        ax.tick_params(axis='y', labelleft=False)
    fig.supylabel('MPC problems $\\geq$ indicated value [%]', fontsize=8)
    handles, labels = axs[0, 0].get_legend_handles_labels()
    order = [2, 0, 1]
    fig.legend([handles[i] for i in order], [labels[i] for i in order],
               loc='outside upper center', ncol=3, frameon=False)
    save(fig, out, 'macc_vs_ipopt')


def fig4(exp, out):
    d = pd.read_csv(runs_by_horizon(exp)[30])
    t = d.time_s.values
    fig, axs = plt.subplots(3, 1, figsize=(3.45, 2.9), sharex=True, constrained_layout=True)
    axs[0].plot(t, d.v_p, color='0.55', lw=1.0, label='preceding $v_p$')
    axs[0].plot(t, d.v_h, color='#0072B2', lw=0.9, label='host $v_h$')
    axs[0].set_ylabel('Speed [m/s]')
    axs[0].legend(loc='upper left', ncol=2, frameon=False, fontsize=6.5)
    axs[1].plot(t, d.d_h, color='#0072B2', lw=0.9)
    axs[1].set_ylabel('$d_h$ [m]')
    axs[2].plot(t, d.u_applied / 1000, color='#0072B2', lw=0.7)
    axs[2].set_ylabel('$f_t-f_b$ [kN]')
    axs[2].set_xlabel('Time [s]')
    for ax in axs:
        ax.grid(True, color='0.9', lw=0.5)
        ax.set_axisbelow(True)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=2)
    save(fig, out, 'macc_trajectory')


# Fig. 7: the solvers shown, as (key, mode, label); mode kkt = K0 (sigma_eq = 0), kkt-reg = K_sigma
LINEAR_SOLVERS = [('cholmod_fast', 'kkt-reg', 'CHOLMOD fast (reg.)'), ('eigen_ldlt', 'kkt-reg', 'Eigen LDLT (reg.)'),
                  ('cholmod', 'kkt-reg', 'CHOLMOD (reg.)'), ('qdldlt', 'kkt', 'QDLDLT'),
                  ('pardiso', 'kkt', 'PARDISO'), ('eigen_lu', 'kkt', 'Eigen LU'), ('umfpack', 'kkt', 'UMFPACK')]


def fig7(exp, out):
    rows = {(int(r['N']), r['key'], r['mode']): r for r in csv.DictReader(open(Path(exp) / 'linear_solvers.csv'))}
    sel = [s for s in LINEAR_SOLVERS if all((n, s[0], s[1]) in rows for n in (3, 30))]
    missing = [s[2] for s in LINEAR_SOLVERS if s not in sel]
    if missing:
        print(f'  Fig. 7: not in {exp.name}: {", ".join(missing)} (e.g. PARDISO needs cg2o built with MKL)')
    plt.rcParams.update({'font.size': 7.5, 'axes.labelsize': 7.5})
    fig, axs = plt.subplots(1, 2, figsize=(3.45, 2.15), sharey=True, constrained_layout=True,
                            gridspec_kw={'width_ratios': [1.35, 1]})
    y = np.arange(len(sel))
    h = 0.38
    colors = {3: '#0072B2', 30: '#E69F00'}
    for j, n in enumerate((3, 30)):
        ref = float(rows[(n, 'umfpack', 'kkt')]['ms_per_iter'])
        ratio = [float(rows[(n, k, m)]['ms_per_iter']) / ref for k, m, _ in sel]
        iters = [float(rows[(n, k, m)]['iter_avg']) for k, m, _ in sel]
        off = (j - 0.5) * h
        axs[0].barh(y + off, ratio, height=h, color=colors[n], edgecolor='white', linewidth=0.4, label=f'$N={n}$')
        axs[1].barh(y + off, iters, height=h, color=colors[n], edgecolor='white', linewidth=0.4)
        for yy, v in zip(y + off, ratio):
            axs[0].text(v + 0.02, yy, f'{v:.2f}', va='center', fontsize=5.5, color='0.2')
    axs[0].set_yticks(y)
    axs[0].set_yticklabels([label for *_, label in sel])
    axs[0].invert_yaxis()
    axs[0].axvline(1, color='0.4', lw=0.6, ls=(0, (2, 2)))
    axs[0].set_xlim(0, 1.25)
    axs[0].set_xlabel('Time per iteration / UMFPACK')
    axs[1].set_xlabel('Iterations')
    axs[0].set_title('(a)', fontsize=7.5, loc='left')
    axs[1].set_title('(b)', fontsize=7.5, loc='left')
    for a in axs:
        a.grid(axis='x', color='0.9', lw=0.5)
        a.set_axisbelow(True)
        for s in ('top', 'right'):
            a.spines[s].set_visible(False)
        a.tick_params(length=2)
    fig.legend(*axs[0].get_legend_handles_labels(), loc='outside upper right', ncol=2, frameon=False)
    save(fig, out, 'linear_solver_comparison')


def write_for_experiment(exp, preset):
    """Hook for run_experiment.py: draw the paper figures of a finished experiment into <exp>/figures/."""
    global VERBOSE
    VERBOSE = False
    exp = Path(exp)
    out = exp / 'figures'
    out.mkdir(exist_ok=True)
    todo = {'fig2': [(fig2, 'macc_vs_bipm')], 'fig3': [(fig3, 'macc_vs_ipopt'), (fig4, 'macc_trajectory')],
            'linear-solvers': [(fig7, 'linear_solver_comparison')]}.get(preset, [])
    made = []
    for fn, stem in todo:
        try:
            fn(exp, out)
        except (KeyError, ValueError, FileNotFoundError) as e:   # e.g. a run without N = 3, 15, 30
            print(f'  paper {fn.__name__} not drawn for this run ({type(e).__name__}: {e})')
            continue
        # inside a run folder the names say which paper figure it is, e.g. paper_fig3_macc_vs_ipopt.pdf
        for ext in ('pdf', 'png'):
            (out / f'{stem}.{ext}').replace(out / f'paper_{fn.__name__}_{stem}.{ext}')
        made.append(out / f'paper_{fn.__name__}_{stem}.pdf')
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fig2', help='fig2 experiment folder (default: newest complete one)')
    ap.add_argument('--fig3', help='fig3 experiment folder (default: newest complete one)')
    ap.add_argument('--linear', help='linear-solvers experiment folder with N = 3 and 30 (default: newest)')
    ap.add_argument('--out', default=str(REPO / 'results' / 'paper_figures'), help='output folder')
    ap.add_argument('--only', default='fig2,fig3,fig4,fig7', help='comma list of figures')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(','))
    if 'fig2' in only:
        exp = experiment_dir(a.fig2, 'fig2')
        print(f'Fig. 2 from {exp}')
        fig2(exp, out)
    if only & {'fig3', 'fig4'}:
        exp = experiment_dir(a.fig3, 'fig3')
        print(f'Fig. 3 / 4 from {exp}')
        if 'fig3' in only:
            fig3(exp, out)
        if 'fig4' in only:
            fig4(exp, out)
    if 'fig7' in only:
        exp = experiment_dir(a.linear, 'linear-solvers')
        print(f'Fig. 7 from {exp}')
        fig7(exp, out)


if __name__ == '__main__':
    main()
