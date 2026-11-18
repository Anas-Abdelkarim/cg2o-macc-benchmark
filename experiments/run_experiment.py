#!/usr/bin/env python3
"""Run the experiments of the paper with one command (from the repository root):

  python3 experiments/run_experiment.py fig2                   cg2o vs barrier IPM, N = 3, 15, 30 (Table IV, Fig. 2)
  python3 experiments/run_experiment.py fig3                   cg2o vs native IPOPT, N = 3, 15, 30 (Table V, Figs. 3, 4)
  python3 experiments/run_experiment.py linear-solvers         linear solvers inside cg2o, ranked (Fig. 7, Table VII)
  python3 experiments/run_experiment.py ipopt-linear-solvers   IPOPT with each of its linear solvers (MUMPS, HSL, ...)
  python3 experiments/run_experiment.py single -- --solvers ispd,ipopt --horizon 15 --loop-size 500
  python3 experiments/run_experiment.py replot <experiment folder>   redraw figures/tables from stored runs
  python3 experiments/run_experiment.py list-solvers
  python3 experiments/run_experiment.py fig2 --quick           300 MPC steps instead of the whole cycle (smoke test)

Every call creates  results/experiments/<YYYYmmdd_HHMMSS>_<preset>/  containing
experiment_info.txt (all settings, machine, results, paper comparison), the runs
(config_resolved.yaml, steps.csv, summary.json each), figures and tables.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _check_packages() -> None:
    missing = []
    for module, package in (("numpy", "numpy"), ("matplotlib", "matplotlib"), ("yaml", "PyYAML")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        req = Path(__file__).resolve().parent / "requirements.txt"
        sys.exit(f"Python packages missing: {', '.join(missing)}. Install them once with:\n"
                 f"  python3 -m pip install -r {req}")


_check_packages()

from macc_exp import ipopt_linear_solvers, linear_solvers, presets  # noqa: E402
from macc_exp.experiment import Experiment  # noqa: E402
from macc_exp.paths import DEFAULT_RESULTS, find_binary  # noqa: E402
from macc_exp.runner import list_linear_solvers  # noqa: E402

QUICK_STEPS = 300
PAPER_ANALYSIS = Path(__file__).resolve().parents[1] / "paper" / "analysis"


def save_paper_outputs(exp_dir: Path, preset: str) -> None:
    """Write the paper's table and figures of this experiment into its folder:
    fig2 -> paper_table_iv.txt, figures/paper_fig2_macc_vs_bipm.pdf; fig3 -> paper_table_v.txt,
    figures/paper_fig3_macc_vs_ipopt.pdf and paper_fig4_macc_trajectory.pdf; linear-solvers ->
    figures/paper_fig7_linear_solver_comparison.pdf (needs N = 3 and 30)."""
    if preset not in ("fig2", "fig3", "linear-solvers"):
        return
    try:
        sys.path.insert(0, str(PAPER_ANALYSIS))
        import paper_figures  # noqa: E402
        import paper_tables  # noqa: E402
        print()
        if preset in ("fig2", "fig3"):
            paper_tables.write_for_experiment(exp_dir, preset)
        made = paper_figures.write_for_experiment(exp_dir, preset)
        if made:
            print("\n=== The paper's figures and table of this run ===")
            for f in made:
                print(f"  {f}")
            for t in sorted(Path(exp_dir).glob("paper_table_*.txt")):
                print(f"  {t}")
    except ImportError as e:
        print(f"NOTE: paper table/figures not written ({e}); install the packages of experiments/requirements.txt",
              file=sys.stderr)
    except Exception as e:  # the experiment itself is complete; only this summary failed
        print(f"WARNING: could not write the paper table/figures: {e}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("preset", choices=["fig2", "fig3", "figures", "linear-solvers", "ipopt-linear-solvers", "single", "replot",
                                      "list-solvers"])
    p.add_argument("target", nargs="?", help="replot: experiment folder")
    g = p.add_argument_group("what to run")
    g.add_argument("--horizons", type=int, nargs="+", metavar="N",
                   help="prediction horizons (default 3 15 30; linear-solvers: 3 30)")
    g.add_argument("--steps", type=int, nargs="+", default=None, metavar="K",
                   help="MPC steps to simulate (default: whole driving cycle = 3863; linear-solvers: 500). "
                        "linear-solvers: one value per horizon is allowed, e.g. --horizons 3 15 30 --steps 2000 1000 500")
    g.add_argument("--quick", action="store_true", help=f"only {QUICK_STEPS} MPC steps (smoke test)")
    g.add_argument("--run-times", type=int, default=None, metavar="R",
                   help="solve each step R times and average without outliers (paper: >10; default 1, "
                        "linear-solvers 3)")
    g.add_argument("--max-iter", type=int, default=None,
                   help="fig2/fig3/single: every step runs to convergence, this is only the limit (default 120, "
                        "as in the paper); linear-solvers --measure fixed: EXACTLY this many iterations per step "
                        "(default 10); --measure converged: the limit (default 120)")
    g.add_argument("--linear-solver", nargs="+", default=None, metavar="SOLVER",
                   help="id or key of the cg2o linear solver (default: config). linear-solvers: the runs to make, "
                        "'<id or key>reg' = with regularization sigma, e.g. --linear-solver 0 0reg 14 14reg qdldlt "
                        "(replaces --solvers / --modes)")
    g.add_argument("--config", default=None, help="base YAML configuration (default: config/config.yaml)")
    g.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE",
                   help="override any configuration entry (repeatable)")
    g.add_argument("--protocol", choices=["both", "cold", "warm"], default="both",
                   help="fig3: IPOPT starts from 10 (cold), from the previous solution (warm) or both")
    g = p.add_argument_group("linear-solvers")
    g.add_argument("--measure", choices=["fixed", "converged"], default=None,
                   help="linear-solvers only (default fixed). "
                        "fixed: every MPC step runs exactly --max-iter iterations, compared is the time per step; "
                        "converged: every step runs to convergence, compared are the time per iteration and the "
                        "iterations to terminate")
    g.add_argument("--modes", default="kkt,kkt-reg",
                   help="comma list of: kkt (full problem), kkt-reg (KKT + regularization)")
    g.add_argument("--solvers", default=None,
                   help="comma list of solver ids/keys, or 'all' (default: the solvers that handle the KKT system); "
                        "ipopt-linear-solvers: IPOPT names, e.g. mumps,pardisomkl,spral,spral_mc64,spral_none,ma57 (default: all)")
    g.add_argument("--include-slow", action="store_true", help="also run the slow dense solvers for N > 10")
    g.add_argument("--regularization", type=float, default=1e-8, help="sigma of mode kkt-reg")
    g.add_argument("--include", default="",
                   help="linear-solvers combined figure (also with replot): comma list of the bars to draw, in this order, "
                        "named as in the figure: 'cholmod(reg)', 'qdldlt', 'umfpack', ... ('*' wildcards allowed); default all")
    g.add_argument("--stat", choices=["mean", "median"], default="mean",
                   help="linear-solvers figures: mean (paper) or median time per MPC step (robust to a few slow steps)")
    g.add_argument("--hide-failed", action="store_true",
                   help="linear-solvers combined figure: leave out solvers that failed / gave a different result; "
                        "fig2/fig3 (also with replot): do not draw steps a solver failed and leave out horizons "
                        "where a solver has no result")
    g.add_argument("--no-numbers", action="store_true",
                   help="fig2/fig3: do not write the means (iterations mean/max, time, time per iteration x ratio) "
                        "into the panels")
    g.add_argument("--no-reg-solvers", default="18,19,20,21",
                   help="linear-solvers: solver ids/keys that are NOT run in mode kkt-reg (default: the qdldlt family, which has "
                        "its own internal regularization); '' = run every solver in every mode")
    g.add_argument("--timeout", type=float, default=None, help="seconds per run (linear-solvers default 300 fixed / 900 converged; 0 = no limit)")
    g = p.add_argument_group("output")
    g.add_argument("--out", type=Path, default=DEFAULT_RESULTS, help="parent folder of the experiment folder")
    g.add_argument("--label", default="", help="appended to the experiment folder name")
    g.add_argument("--no-plots", action="store_true")
    g.add_argument("--show", action="store_true",
                   help="open the PNG figures of the experiment when it is finished (also with replot)")
    g.add_argument("--palette", choices=["paper", "clean"], default="paper",
                   help="paper: colours of the T-RO figures; clean: colour-blind-safe pair")
    g.add_argument("--latex", action="store_true", help="render text with LaTeX (needs latex + dvipng)")
    return p


def show_figures(folder: Path) -> None:
    """Open the PNG figures of an experiment folder with the desktop viewer (WSL: Windows default app)."""
    import os
    import shutil
    import subprocess
    pngs = sorted((folder / "figures").glob("*.png")) or sorted(folder.glob("*.png"))
    if not pngs:
        print(f"--show: no PNG figures in {folder}")
        return
    for f in pngs:
        if shutil.which("wslview"):
            cmd = ["wslview", str(f)]
        elif shutil.which("explorer.exe") and shutil.which("wslpath"):   # WSL without wslu
            win = subprocess.run(["wslpath", "-w", str(f)], capture_output=True, text=True).stdout.strip()
            cmd = ["explorer.exe", win]
        elif sys.platform == "darwin":
            cmd = ["open", str(f)]
        elif shutil.which("xdg-open"):
            cmd = ["xdg-open", str(f)]
        else:
            print(f"--show: no viewer found; figures are in {f.parent}")
            return
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ)


def make_opts(a: argparse.Namespace, macc_args=()) -> presets.Opts:
    ls = a.preset == "linear-solvers"
    if a.measure is not None and a.preset not in ("linear-solvers", "replot"):
        raise SystemExit(f"--measure only applies to linear-solvers; {a.preset} always runs every step to "
                         "convergence (--max-iter is the limit)")
    a.measure = a.measure or "fixed"
    horizons = tuple(a.horizons) if a.horizons else ((3, 30) if ls else (3, 15, 30))
    steps_list = [QUICK_STEPS] if a.quick else (a.steps or [])
    if len(steps_list) > 1:
        if a.preset != "linear-solvers":
            raise SystemExit("--steps: one value per horizon is only supported by linear-solvers")
        if len(steps_list) != len(horizons):
            raise SystemExit(f"--steps: give one value, or one per horizon ({len(horizons)}: {list(horizons)})")
        steps, steps_by_n = 0, dict(zip(horizons, steps_list))
    else:
        steps = steps_list[0] if steps_list else (500 if ls else 0)
        steps_by_n = {n: steps for n in horizons} if a.preset == "linear-solvers" else {}
    if a.linear_solver and len(a.linear_solver) > 1 and not ls:
        raise SystemExit("--linear-solver: several solvers are only supported by linear-solvers")
    linear_solver = None if ls or not a.linear_solver else a.linear_solver[0]
    max_iter = a.max_iter if a.max_iter is not None else (
        linear_solvers.DEFAULT_MAX_ITER[a.measure] if ls else 120)
    return presets.Opts(
        horizons=horizons, steps=steps, steps_by_n=steps_by_n,
        run_times=a.run_times if a.run_times is not None else (3 if ls else 1),
        max_iter=max_iter, linear_solver=linear_solver, overrides=list(a.overrides), config=a.config,
        palette=a.palette, latex=a.latex, plots=not a.no_plots, timeout=a.timeout,
        modes=tuple(m.strip() for m in a.modes.split(",") if m.strip()),
        include_slow=a.include_slow, solvers=a.solvers.split(",") if a.solvers else None,
        regularization=a.regularization, protocol=a.protocol,
        include=tuple(x.strip() for x in a.include.split(",") if x.strip()), hide_failed=a.hide_failed, numbers=not a.no_numbers, stat=a.stat,
        no_reg_solvers=tuple(x.strip() for x in a.no_reg_solvers.split(",") if x.strip()), macc_args=tuple(macc_args),
        measure=a.measure, ls_jobs=tuple(a.linear_solver or ()) if ls else ())


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    macc_args = []
    if "--" in argv:
        i = argv.index("--")
        argv, macc_args = argv[:i], argv[i + 1:]
    a = build_parser().parse_args(argv)

    if a.preset == "list-solvers":
        print(f"{'id':>3}  {'key':<24}{'name':<34}{'lib':<6}{'available':<10}note")
        for s in list_linear_solvers():
            print(f"{s['id']:>3}  {s['key']:<24}{s['name']:<34}{s['lib']:<6}{'yes' if s['available'] else 'NO':<10}{s['note']}")
        return 0
    try:
        find_binary()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2

    if a.preset == "replot":
        if not a.target:
            print("replot needs the experiment folder", file=sys.stderr)
            return 2
        exp = Experiment.load(Path(a.target))
        o = make_opts(a)
        o.horizons = tuple(sorted({r.horizon for r in exp.runs if r.ok and r.horizon}))
        if exp.preset == "linear-solvers":      # no new runs: redraw from linear_solvers.csv with the chosen bars
            o.horizons = tuple(a.horizons) if a.horizons else ()
            o.ls_jobs = tuple(exp.options.get("ls_jobs", ()))
            try:
                for pth in linear_solvers.replot_linear_solvers(exp.dir, o):
                    print(f"figure: {pth}")
            except (ValueError, FileNotFoundError) as e:
                print(f"replot: {e}", file=sys.stderr)
                return 2
            if a.show:
                show_figures(exp.dir)
            return 0
        with exp:
            if exp.preset == "fig2":
                presets.analyze_fig2(exp, o)
            elif exp.preset == "fig3":
                presets.analyze_fig3(exp, o)
            else:
                print(f"replot is implemented for fig2 / fig3 (this is '{exp.preset}')")
        save_paper_outputs(exp.dir, exp.preset)
        if a.show:
            show_figures(exp.dir)
        return 0

    presets_to_run = ["fig2", "fig3"] if a.preset == "figures" else [a.preset]
    rc = 0
    for name in presets_to_run:
        o = make_opts(a, macc_args)
        desc, fn = {
            "fig2": (presets.FIG2_DESC, presets.run_fig2),
            "fig3": (presets.FIG3_DESC, presets.run_fig3),
            "linear-solvers": (
                "Evaluation of the promising linear solvers of g2o / cg2o inside the ISPD-IPM on the full\n"
                "MACC problem (equality + inequality constraints) with a fixed number of iterations per MPC\n"
                "step (--measure fixed) or until convergence (--measure converged). Every solver runs in its own\n"
                "process on the same closed loop; solvers are ranked by the solver time per MPC step (fixed) or\n"
                "per iteration (converged); a solver that does not reproduce the reference result is shown too.",
                linear_solvers.run_linear_solvers),
            "ipopt-linear-solvers": (ipopt_linear_solvers.DESC, ipopt_linear_solvers.run_ipopt_linear_solvers),
            "single": (presets.SINGLE_DESC, presets.run_single),
        }[name]
        exp = Experiment(name, desc, o.as_dict(), out_root=a.out, label=a.label,
                         argv=[sys.argv[0], *sys.argv[1:]])
        with exp:
            fn(exp, o)
        rc = rc or (0 if exp.status == "COMPLETED" else 1)
        if exp.status == "COMPLETED":
            save_paper_outputs(exp.dir, name)
        if a.show:
            show_figures(exp.dir)
    return rc


if __name__ == "__main__":
    sys.exit(main())
