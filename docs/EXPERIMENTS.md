# Running the experiments

```bash
python3 experiments/run_experiment.py <preset> [options]   # from the repository root; uses build/macc/bin/macc_run (or $MACC_RUN)
```

Presets: `fig2`, `fig3`, `linear-solvers`, `ipopt-linear-solvers`, `single`, `replot <folder>`, `list-solvers`.

## What each preset does

| preset | solvers | start | horizons | what it reproduces |
|---|---|---|---|---|
| `fig2` | `ispd`, `bipm` | feasibility projection (BIPM needs a strictly feasible start; ISPD gets the same one) | N = 3, 15, 30 | Fig. 2 and Table V: iterations and time per MPC step, ISPD-IPM vs barrier IPM |
| `fig3` | `ispd`, `ipopt`, `ipopt_warm` | every variable = 10 (`ispd`, `ipopt`); previous solution (`ipopt_warm`) | N = 3, 15, 30 | Fig. 3 and Table V: ISPD-IPM vs native IPOPT on the exact MACC problem |
| `linear-solvers` | `ispd` with every available linear solver | every variable = 10 | N = 3, 30 | ranking of the linear solvers (paper Sec. VI-D) |
| `ipopt-linear-solvers` | `ispd` (driver) + `ipopt` with each IPOPT linear solver (`mumps`, `pardisomkl`, `spral`, `ma27` ... `ma97`) | every variable = 10 | N = 3, 15, 30 | which linear solver IPOPT should use; solvers missing from the build are reported as not available |

All presets simulate the whole driving cycle (3863 MPC steps, Ts = 0.1 s; 3007 steps in the space
domain, 856 in the time domain) except `linear-solvers` (500 steps). `--quick` limits any preset to 300 steps.

In every closed-loop run **all solvers solve the same NLP at every step**; the input of the first solver
(the *driver*) moves the plant. Each solution is scored by one common function (`MaccNLP`), so the cost
columns of different solvers are directly comparable.

## Options

```
--horizons N [N ...]    prediction horizons                      (default 3 15 30; linear-solvers 3 30)
--steps K [K ...]       MPC steps to simulate                    (default whole cycle; linear-solvers 500;
                        linear-solvers also one value per horizon: --horizons 3 15 30 --steps 2000 1000 500)
--quick                 300 steps                                (smoke test)
--run-times R           solve each step R times, average without outliers   (default 1; linear-solvers 3)
--max-iter M            iteration limit: fig2/fig3/single run each step to convergence, at most M (default 120);
                        linear-solvers --measure fixed: EXACTLY M iterations per step (default 10);
                        linear-solvers --measure converged: limit (default 120)
--linear-solver X       id or key of the cg2o linear solver      (default: config, 14 = umfpack)
                        linear-solvers: the runs to make, '<id|key>reg' = with sigma, e.g.
                        --linear-solver 0 0reg 14 14reg qdldlt  (replaces --solvers / --modes)
--measure fixed|converged  linear-solvers ONLY (other presets reject it): fixed = every step runs exactly
                        --max-iter iterations, ranked by time per step; converged = run to convergence,
                        ranked by time per iteration, iterations to terminate shown too    (default fixed)
--set KEY=VALUE         override any entry of config/config.yaml (repeatable), e.g. --set ispd_settings.tau=1.6
--config FILE           use another base configuration
--protocol both|cold|warm      fig3: IPOPT start        (default both)
--modes kkt,kkt-reg            linear-solvers: which formulations to sweep
--solvers a,b,c|all     linear-solvers: these solvers (ids or keys); default: the KKT-capable shortlist
--include-slow          linear-solvers: also run the dense O(n^3) solvers for N > 10
--regularization SIGMA  linear-solvers, mode kkt-reg           (default 1e-8)
--no-reg-solvers a,b    linear-solvers: not run in kkt-reg     (default 18,19,20,21: qdldlt has its own regularization)
--include A,B,...       linear-solvers figures: these bars, in this order, named as in the figure
                        ('cholmod_fast(reg)', 'qdldlt', 'umfpack', '*' wildcards); also with replot
--hide-failed           linear-solvers figures: draw only valid results (failed, skipped or different-result
                        entries are left out at every horizon). Every bar carries coloured numbers: converged:
                        time/iteration (x fastest), mean time per step, iterations mean and max; fixed: time (x fastest);
                        fig2/fig3 (also replot): failed steps are not drawn or averaged, horizons where a
                        solver has no result are left out
--no-numbers            fig2/fig3: no numbers in the panels (default: iterations mean/max, mean time,
                        mean time per iteration x ratio to ISPD, each in the colour of its solver)
--stat mean|median      linear-solvers figures and ranking: time per MPC step (default mean)
--timeout SECONDS       linear-solvers: limit per run          (default 300 fixed / 900 converged; 0 = no limit)
--out DIR --label TEXT  result root (default results/experiments) / text appended to the folder name
--no-plots  --palette  --latex
```

### Fixed iteration count or run to convergence

Only the `linear-solvers` study runs a fixed number of iterations. Every other preset runs each MPC step to convergence.

| experiment | iterations per MPC step | compared | `--max-iter` means |
|---|---|---|---|
| `fig2`, `fig3`, `single` | until convergence | iterations and time to converge (paper Fig. 2/3, Tables V/VI) | limit (default 120) |
| `linear-solvers` (default `--measure fixed`) | exactly `--max-iter`, convergence test off (`cg2o.epsilon_convergence=0`) | time per MPC step; all solvers do the same work | the count (default 10) |
| `linear-solvers --measure converged` | until convergence | time per iteration and iterations to terminate | limit (default 120) |
| `ipopt-linear-solvers` | until convergence (IPOPT, cold start) | time per MPC step; iterations must match MUMPS | limit (default 120) |

When to use which: the fixed count isolates the linear solver (same number of factorisations for everyone, so a solver
cannot win by needing fewer iterations, and a slow-converging one cannot hit the 120 limit). The paper's linear-solver
comparison (Sec. VI-D) also uses 10 fixed iterations, there with the equality constraints removed. Use `--measure converged` when you also want to know whether
a solver changes how many iterations ISPD needs, e.g. because a regularized or inexact solve slows convergence. fig2/fig3
always converge because they compare solvers by the iterations they need. Steps that hit the 120 limit stay in the averages.

The word "fixed" also appears in `--init fixed` / `mpc.init_mode: fixed`, which fig3 uses. That is the **initial guess**
(every variable = `mpc.init_value` = 10), not an iteration count.

Examples:

```bash
python3 experiments/run_experiment.py fig2 --horizons 3 15 --steps 1000
python3 experiments/run_experiment.py fig3 --protocol warm --run-times 10        # timing you want to quote
python3 experiments/run_experiment.py linear-solvers --quick --horizons 3 --run-times 1      # try it in a minute
python3 experiments/run_experiment.py linear-solvers --horizons 3 15 30 --steps 2000 1000 500 --run-times 10   # overnight
python3 experiments/run_experiment.py linear-solvers --measure converged --horizons 3 15 30 --run-times 10 \
    --linear-solver 0 0reg 14 14reg 18                    # time/iteration + iterations, chosen runs
python3 experiments/run_experiment.py replot results/experiments/<folder> --include "cholmod_fast(reg),qdldlt,umfpack" --show
python3 experiments/run_experiment.py single -- --solvers ispd,bipm,ipopt --horizon 10 --loop-size 200
python3 experiments/run_experiment.py replot results/experiments/<folder>
```

## Linear-solver study

Both modes solve the full MACC problem (dynamics as equality constraints + all inequalities). With the default
`--measure fixed` the convergence test is switched off (`cg2o.epsilon_convergence=0`), so every MPC step runs exactly
`--max-iter` ISPD iterations (default 10) and every solver does the same work; with `--measure converged` every step runs
to convergence (limit 120) and the solvers are ranked by time per iteration (see "Fixed iteration count or run to
convergence" above). Two modes, because the linear system that cg2o solves differs:

* `kkt` — the full MACC problem. The KKT matrix is **indefinite**: the Cholesky-type solvers fail
  (reported as such, they do not stop the sweep); LU solvers and `qdldlt` work.
* `kkt-reg` — the full problem with `cg2o.equality_regularization = sigma` (default 1e-8), which makes the system
  quasi-definite, so LDL^T-type solvers (`cholmod_fast`, `qdldlt`, `eigen_ldlt`) can be used.

By default these solvers run in both modes: `cholmod` (0), `eigen_ldlt` (1), `csparse` (2), `eigen_lu` (6),
`eigen_dense_partial_lu` (12), `pardiso` (13), `umfpack` (14), `cholmod_fast` (16), `umfpack_fast` (17), and only in `kkt` (they have
their own internal regularization delta, `--no-reg-solvers`): `qdldlt` (18, delta 1e-9), `qdldlt_s7` (19, delta 1e-7),
`qdldlt_s7_ref` (20, delta 1e-7, always refine); all three refine and fall back to LU when inaccurate (README, "Two
different regularizations"). `pardiso` (13) runs when cg2o is built with MKL. `--solvers all` runs every available solver.

Order and reference: the horizons run from small to large; at every horizon `umfpack` on the exact KKT matrix runs
first and is the reference for BOTH modes, i.e. a regularized solver must reproduce the cost of the exact problem.
A solver that fails or gives a different result at a horizon is not run at the larger ones (reported as skipped).
A solver whose result differs from the reference (UMFPACK, exact KKT) is still timed and drawn as a hatched bar;
a run with 0 iterations (the factorization fails in every step, e.g. CHOLMOD / CSparse / Eigen LDLT on the exact
KKT matrix) has no meaningful time and is listed as failed. `linear_solvers.csv` is rewritten after every run, so an interrupted experiment can still be plotted with `replot`.

Each (solver, mode, horizon) is a separate process, so a solver that crashes, diverges or times out cannot spoil the
others. A solver is only *ranked* if its cost and its iteration count agree with the reference solver (`COST_TOL` 1e-3,
`ITER_TOL` 10%), so a solver that is fast because it returns a wrong answer does not win. The status line `COMPLETED WITH FAILED RUNS` is normal for this preset: solvers that are unsuited to a formulation (Cholesky on the
indefinite KKT system, PCG on a badly conditioned one) fail or time out by design. Output:
`figures/linear_solvers.png` (one panel per horizon, colour = mode, linear axis from zero; bars longer than 6x the
fastest are cut and marked `>>`), `figures/linear_solvers_grouped.png` (one panel, a bar per horizon, log axis),
`linear_solvers.csv` (mean and median time per step) and the ranking in `experiment_info.txt`. In the figures
`<key> (reg)` means sigma = `--regularization`, a plain `<key>` the exact KKT matrix.

## What is in a result folder

```
results/experiments/20261022_114335_fig2_myLabel/
  experiment_info.txt        read this first (sections below)
  experiment.json            the same information, machine readable
  console.log                everything that was printed while running
  figures/                   paper_fig2_macc_vs_bipm (the paper's Fig. 2); fig2_overview, fig2_overview_tpi,
                             fig2_overview_full (per-step overviews, not in the paper)   (.png and .pdf)
  table_iv_bipm.csv          numbers behind the figure (fig3: table_v_ipopt.csv; linear-solvers: linear_solvers.csv)
  paper_table_iv.txt (+.json) fig2: this run as the paper's Table IV (fig3: paper_table_v.txt); paper/analysis/paper_tables.py
  runs/<stamp>_N15/
     config_resolved.yaml    the exact configuration of this run (macc_run --config <this file> repeats it)
     steps.csv               one row per MPC step: k, time, v_h, d_h, v_p, a_p, space_domain, delta_s, u_applied and per
                             solver  <name>_{u, iterations, time_ms, time_min_ms, time_max_ms, ms_per_iter, cost,
                             solver_cost, eq_residual, ineq_violation, hit_max_iter, success}
     summary.json            means, medians, extremes and totals per solver
     experiment_info.txt, console.log, runner_output.log
```

`experiment_info.txt` sections: 1 how to reproduce (command line, options) · 2 system and build (host, CPU, OS, compiler,
library versions: g2o, cg2o, IPOPT, git commit) · 3 runs · 4 results next to the numbers of the paper · 5 where the iterations
go (space vs time domain) · 6 solution quality (cost agreement, constraint violation, steps at the iteration limit) · 7 notes ·
8 files written · 9 base configuration.

`solver_cost` is what the solver itself reports (factor-graph cost for cg2o, IPOPT's objective); `cost` is the same
quantity recomputed by `MaccNLP` at the returned point. They agree to better than 1e-9 relative (`ctest` checks it; typically 1e-14); the column exists to catch
a solver that returns one point and reports another.

## Fig. 3 / Table V: how IPOPT is run

* **Start.** `ipopt` starts every MPC problem from the same infeasible point as cg2o (every variable = 10);
  `ipopt_warm` starts from its own previous solution. cg2o always starts cold.
* **Options.** `ipopt_settings.options` in `config/config.yaml` (tuned, exact Hessian, adaptive mu with the
  quality function, filter line search, no scaling, iteration limit 120). Every run lists the options it used.
* **Linear solver.** MUMPS by default (`ipopt_settings.use_hsl: false`). The paper's Table V and Fig. 3 use HSL MA57:
  build HSL as described in `externals/README.md` and run `fig3 --set ipopt_settings.use_hsl=true`. The linear
  solver changes IPOPT's time per iteration and, slightly, its iteration counts (pivoting differs); cg2o is not
  affected.
* **Bounds.** The four single-variable force/brake limit rows per stage are passed to IPOPT as variable bounds
  (`ipopt_settings.single_variable_rows_as_bounds`, default 1); this does not change the iteration counts.

## Reproducibility

* **Constant start (`fig3`): reproducible bit for bit** on the same build. A full
  `fig3` rerun with MA57 gave the same iteration count as the paper's run in all 3 × 3863 problems, for cg2o and both
  IPOPT runs; 300-step checks with MUMPS did the same.
* **Feasible start (`fig2`): not fully deterministic.** `setInitialGuess(false)` clamps the *current* vertex estimates,
  and the scalar vertices get no initial value when they are created (`MPCFormulation::addVertex` in
  `MACC/include/macc/fg/formulation.hpp`). The first feasible-start solve therefore depends on memory contents (heap
  layout, environment size, binary). Measured over three full `fig2` runs: cg2o differs in at most 4 of 3863 problems
  (averages 13.0 / 14.9 / 15.7 unchanged, maximum at N = 30: 49 or 50); the barrier IPM differs in 40–590 problems,
  averages 18.8 / 26.3–26.4 / 34.1–34.2, problems at the limit 0 / 19–24 / 171–180.
  Calling `vertex->setToOrigin()` in `addVertex` makes the runs deterministic (padded and unpadded environment give
  identical runs); the barrier IPM then gives 18.8 / 26.2 / 34.2 with 0 / 16 / 186 problems at the limit, and cg2o
  is unchanged.
* `-march=native` must be the same for g2o, cg2o and MACC (Eigen's memory layout depends on it);
  `build_workspace.sh` takes the setting of the installed g2o.
* With cg2o built with PARDISO (`ENABLE_PARDISO=ON`), Intel MKL and its OpenMP runtime are linked in; their default
  thread pools made every solver about 30x slower. `macc_run` therefore sets `OMP_NUM_THREADS=1` and
  `MKL_NUM_THREADS=1` (unless already set) and restarts itself once.

## Timing: what is comparable

* **Threads and cores.** The experiment runner starts `macc_run` single-threaded (`OMP_NUM_THREADS=1`, also MKL / OpenBLAS; set
  `MACC_THREADS=<n>` to change it). With `OMP_NUM_THREADS=8` exported in `~/.bashrc` the same run was 2x slower (g2o is built with
  OpenMP) and used 25x the CPU time. On this hybrid CPU (6 performance + 8 efficiency cores) the core the run lands on also matters:
  the same solve took 0.9 ms on a performance core and 2.1-2.3 ms on an efficiency core. For numbers to quote: nothing else running,
  and pin to performance cores, e.g. `taskset -c 0,2,4,6,8,10 python3 experiments/run_experiment.py fig2 --run-times 10`.
* Iteration counts are deterministic and independent of the machine.
* Milliseconds depend on the machine, load, CPU frequency and (in WSL) the file system. Compare solvers *inside
  one experiment folder*, and use `--run-times 10` or more for numbers you want to quote.
* Absolute IPOPT times here are not comparable with the paper's IPOPT times (different setup); time per iteration is.
* The `ms/iteration` panel (`fig2_overview_tpi`, `fig3_overview_full`) is an extra that is not in the paper.

## Tuning solver parameters
The tuning library (IPOPT, BIPM, ISPD, AL options; Bayesian optimisation, differential evolution, coordinate and random search) is documented in
[TUNING.md](TUNING.md); entry point `scripts/tune.sh` (isolated environment: `scripts/setup_tuning_env.sh`).
