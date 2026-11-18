# MACC benchmark of cg2o

This repository contains the code and the reproduction scripts of the **multi-objective adaptive cruise control
(MACC)** benchmark of the paper

> *cg2o: Constrained Factor Graph Optimization via an Infeasible-Start Primal–Dual Interior-Point Method*
> (Sec. VI of the paper)

The solver itself, **cg2o**, is a separate library (https://github.com/snt-arg/cg2o), an extension of g2o. This
repository builds it, formulates the MACC problem as a constrained factor graph, runs it in a closed loop over a
full driving cycle, and compares it with other solvers on exactly the same optimization problems.

To install and reproduce the paper, follow **[QUICKSTART.md](QUICKSTART.md)**.

---

## 1. The benchmark

An electric host vehicle follows a preceding vehicle whose speed is the RDE-compliant driving cycle (3863 MPC
problems at a sampling time of 100 ms). At every step a nonlinear MPC problem with horizon N ∈ {3, 15, 30} is solved:

* **variables per stage (7):** host speed v_h, inter-vehicle distance d_h, traction force f_t, braking force f_b,
  and three slack variables;
* **constraints per stage (16):** 2 equality rows (dynamics) and 14 inequality rows: safety distance, speed limits
  (deliberately cubic, so the benchmark has nonlinear inequalities), force and power limits, rate limits;
* **switched dynamics:** the dynamics are written in the space domain and switch to the time domain by themselves
  when the predicted preceding-vehicle speed drops below 3 m/s (stop-and-go phases).

The same problem is available twice, and both are checked against each other by the tests:

| form | where | used by |
|---|---|---|
| factor graph: vertices, cost / equality / inequality edges | `MACC/include/macc/fg`, `MACC/src/fg` | cg2o solvers |
| plain NLP: f, g, ∇f, Jacobian, Hessian of the Lagrangian (`MaccNLP`) | `MACC/include/macc/nlp`, `MACC/src/nlp` | IPOPT, and the common evaluator |

**Common evaluator.** Every returned solution, from every solver, is scored by the same function (`MaccNLP`): the
objective, the largest equality residual and the largest inequality violation in `steps.csv` are therefore directly
comparable between solvers.

**Closed loop.** In the paired comparisons the input computed by cg2o drives the vehicle model; the other solvers
solve the same problem at every step without applying their input. All solvers therefore see identical problems.

## 2. Solvers

| name | solver | start |
|---|---|---|
| `ispd` | **cg2o, ISPD-IPM** (infeasible-start primal–dual interior-point method, the paper's method) | every variable 10 (infeasible), or the feasible projection in `fig2` |
| `bipm` | barrier IPM for factor graphs (ref. [6] of the paper), through cg2o | feasible projection (it cannot start infeasible) |
| `al` | augmented Lagrangian, through cg2o | every variable 10 |
| `ipopt` | IPOPT 3.14, native C++ interface, exact Jacobian and Hessian | every variable 10 ("cold") |
| `ipopt_warm` | the same IPOPT | its previous solution ("warm") |

cg2o solves the reduced KKT system with one of 22 linear solvers (`macc_run --list-solvers`); the paper uses
QDLDLT on the unregularized system (σ_eq = 0). IPOPT uses **MUMPS** by default; the paper's Table V uses the licensed
HSL solver **MA57**, which you can enable if you have a licence (see [externals/README.md](externals/README.md)).

All settings are in [`config/config.yaml`](config/config.yaml); the values there are the ones of the paper
(Table III). Any entry can be changed for one run with `--set key=value`.

## 3. What can be reproduced

| paper | content | command (after the installation) | evaluated with |
|---|---|---|---|
| Table IV, Fig. 2 | cg2o vs barrier IPM, feasible start, N = 3, 15, 30 | `python3 experiments/run_experiment.py fig2` | `paper/analysis/paper_tables.py`, `paper_figures.py` |
| Table V, Fig. 3 | cg2o vs IPOPT (cold and warm), N = 3, 15, 30 | `python3 experiments/run_experiment.py fig3 --set ipopt_settings.use_hsl=true` (MA57; without it: MUMPS) | same |
| Fig. 4 | closed loop with cg2o, N = 30 | from the `fig3` run | `paper_figures.py` |
| Sec. VI-E | local convergence condition ρ at every solution | `experiments/convergence_check/` (on a `fig3` run) | `analyze.py` |
| Fig. 7 | linear solvers inside cg2o, 500 problems, N = 3 and 30 | `python3 experiments/run_experiment.py linear-solvers --measure converged --run-times 1 --solvers 0,1,3,6,13,14,16,18 --horizons 3 30 --hide-failed` | `paper_figures.py` |
| Table VII | large-scale problems, N = 3·10⁴ and 3·10⁵, 10 iterations | `python3 experiments/run_experiment.py linear-solvers --linear-solver 14 16reg 0reg 1reg 6 6reg 13 13reg 18 --horizons 30000 300000 --steps 2 --measure fixed --max-iter 10 --timeout 0 --hide-failed` | `paper_tables.py --large` |

Not part of this repository: the AMPL comparison with KNITRO, LOQO, CONOPT, MINOS and SNOPT (Table VI, Figs. 5–6),
which needs AMPL and commercial licences; the vehicle experiments (Figs. 8–9), which run on the vehicle's ROS 2
stack; and the quadrotor benchmark (Sec. VII), which has its own repository.

### Expected results

**Table V is reproduced exactly:** a full rerun gives the same iteration count in every one of the 3 × 3863 MPC
problems, for cg2o and for both IPOPT runs (MA57; with MUMPS the IPOPT counts differ slightly from the paper's).
**Table IV:** cg2o is reproduced (averages and maxima; at most 4 of 3863 problems differ by an iteration). The
barrier IPM varies slightly from run to run (averages within ±0.1, problems at the limit 19–24 for N = 15 and
171–180 for N = 30), because its feasible start reads vertex values that are not initialised; see "Reproducibility"
in [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

| | N = 3 | N = 15 | N = 30 |
|---|---|---|---|
| **Table IV** cg2o, feasible start: iterations avg (min, max) | 13.0 (10, 17) | 14.9 (13, 30) | 15.7 (14, 50) |
| Barrier IPM | 18.8 (13, 26) | 26.3 (19, 120) | 34.1 (20, 120) |
| **Table V** cg2o, cold: iterations avg / max | 13.2 / 18 | 15.1 / 31 | 15.9 / 34 |
| IPOPT MA57, cold | 19.5 / 90 | 22.5 / 116 | 27.6 / 120 |
| IPOPT MA57, warm | 12.8 / 48 | 17.6 / 70 | 19.8 / 120 |

**Times depend on the machine.** The paper's times were measured on an Intel Core i9-12900H, one thread, one
repetition per problem. On another machine compare the ratios between the solvers (e.g. cg2o is 4.6–11.2× faster than
cold-started IPOPT with MA57), not the milliseconds. See "Timing" in [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

Every experiment writes `experiment_info.txt`, which compares the run with these numbers (section 7) using
[`config/paper_reference.yaml`](config/paper_reference.yaml).

## 4. Output of an experiment

Every call of `python3 experiments/run_experiment.py` creates `results/experiments/<YYYYmmdd_HHMMSS>_<name>/`:

| file | content |
|---|---|
| `experiment_info.txt` | date, machine, compiler, library versions, the full resolved configuration, every command line, per-run statistics, comparison with the paper |
| `figures/*_overview*.pdf, .png` | per-step overview figures (not in the paper) |
| `table_iv_bipm.csv`, `table_v_ipopt.csv`, `linear_solvers.csv` | the numbers behind the figures |
| `paper_table_iv.txt`, `paper_table_v.txt` (+ `.json`) | fig2 / fig3: this run's numbers in the layout of the paper's Table IV / V |
| `figures/paper_fig2_macc_vs_bipm.pdf`, `paper_fig3_macc_vs_ipopt.pdf`, `paper_fig4_macc_trajectory.pdf`, `paper_fig7_linear_solver_comparison.pdf` | this run drawn exactly as the paper's Fig. 2 / 3 / 4 / 7 |
| `runs/<stamp>_N<n>/` | one folder per horizon: `config_resolved.yaml`, `steps.csv` (every MPC step: states, input, and per solver iterations, time, cost, equality residual, inequality violation), `summary.json`, `console.log` |

The paper's figures and tables are drawn from these folders by [`paper/analysis/`](paper/README.md).

## 5. Repository layout

```
MACC/include/macc/<module>/   public headers, always included as "macc/<module>/<file>"
MACC/src/<module>/            implementation, one CMake library per module
  core/        configuration, tables, statistics, run information
  mpc/         parameters, driving cycle, plant and predictor of the closed loop
  nlp/         MaccNLP: the problem as plain functions (exact derivatives)
  fg/          the same problem as a factor graph (vertices, edges, formulation)
  solvers/     catalogue of the linear solvers of cg2o / g2o
  backends/    cg2o/ (ISPD-IPM, BIPM, AL) and ipopt/ (native IPOPT), behind one Controller interface
  experiment/  closed-loop driver, report writer, setup from the configuration
  apps/        macc_run, the command-line program
config/        config.yaml (all settings, paper values), paper_reference.yaml (paper numbers)
experiments/   Python layer: presets fig2 / fig3 / linear-solvers, figures, reports;
               convergence_check/ (Sec. VI-E); solver_tuning/ (the tuning procedure of Sec. V-B)
paper/         analysis/ (scripts for the paper's MACC figures and tables)
scripts/       build and run scripts
tests/         unit/ (derivatives) and integration/ (cg2o vs IPOPT on the same problem)
externals/     third-party sources (cloned by the scripts; HSL goes here, see externals/README.md)
legacy/        earlier versions of the code, kept for reference, not built
```

## 6. Documentation

* [QUICKSTART.md](QUICKSTART.md) — install everything and reproduce the paper, step by step.
* [INSTALL.md](INSTALL.md) — prerequisites, externals (g2o, cg2o, IPOPT, HSL), build options, troubleshooting.
* [externals/README.md](externals/README.md) — where the third-party sources go, and how to enable HSL.
* [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) — presets, options, output files, timing, reproducibility.
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — modules, the MACC problem, how a new solver is added.
* [docs/BUILD_WORKFLOWS.md](docs/BUILD_WORKFLOWS.md) — the build scripts in detail.
* [docs/TUNING.md](docs/TUNING.md) — the solver tuning library (`experiments/solver_tuning`).
* [paper/README.md](paper/README.md) — the paper's figures and tables from your own runs.
* [experiments/convergence_check/README.md](experiments/convergence_check/README.md) — the local convergence analysis.

## 7. Notes on the linear solvers of cg2o

With equality constraints, the KKT matrix is indefinite. Two different regularizations exist:

* **σ_eq** = `cg2o.equality_regularization` (default 0). cg2o puts −σ_eq on the diagonal of the equality rows. This
  changes the Newton step slightly. Cholesky / LDLᵀ solvers without pivoting (`cholmod`, `eigen_ldlt`, `cholmod_fast`)
  need σ_eq > 0 (the paper uses 10⁻⁸ for them, marked "reg."); with σ_eq = 0 they fail.
* **δ**, the internal regularization of `qdldlt` (10⁻⁹). With σ_eq = 0 it puts −δ on the zero diagonal entries,
  factorizes without pivoting, then refines against the *unregularized* matrix and falls back to a pivoted LU if the
  residual stays above 10⁻⁸·|b|. The result is the exact KKT step, as with UMFPACK. This is the paper's default.

PARDISO needs cg2o built with Intel MKL (`ENABLE_PARDISO=ON ./scripts/build_externals.sh --cg2o-only --clean`).
