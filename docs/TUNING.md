# Tuning the solvers

The library is `experiments/solver_tuning/` (package `solver-tuning` 2.x, import name `tuning`). It tunes the parameters of IPOPT,
ISPD, BIPM, AL (and anything else you can run) by repeated simulation, with Bayesian optimisation (TPE), differential evolution,
coordinate or random search. Its own documentation: [README](../experiments/solver_tuning/README.md),
[ARCHITECTURE](../experiments/solver_tuning/docs/ARCHITECTURE.md), [EXTENDING](../experiments/solver_tuning/docs/EXTENDING.md),
[MIGRATION](../experiments/solver_tuning/docs/MIGRATION.md), [VALIDATION](../experiments/solver_tuning/docs/VALIDATION.md).
This page is the short guide for working in this repository.

## Setup (once)
```bash
scripts/setup_tuning_env.sh --test     # creates .venv-tuning/ (optuna 4.x, matplotlib, pytest) and runs the 52 tests
```
The environment is isolated on purpose: the library needs optuna 4.x, and a sourced ROS installation must not leak into it.
`scripts/tune.sh` always runs inside it.

## Run a study
```bash
scripts/tune.sh run experiments/solver_tuning/studies/ipopt_cold.yaml --out results/tuning/ipopt_cold --trials 300
scripts/tune.sh status results/tuning/<stamp>_ipopt_cold    # works while it runs
scripts/tune.sh plot   results/tuning/<stamp>_ipopt_cold    # progress, parameter effects, selected-vs-baseline
```
A new run prefixes the folder name with a time stamp (`results/tuning/ipopt_cold` -> `results/tuning/20261027_153000_ipopt_cold`,
printed at the start); a name that already starts with a stamp is kept, `--no-stamp` uses `--out` as given. `--resume` and
`--finish` take the stamped folder unchanged.
Studies in `experiments/solver_tuning/studies/` (paths inside are relative to the file):

| file | tunes | driver (reference) | start | notes |
|---|---|---|---|---|
| `ipopt_cold.yaml` | 37 IPOPT options | ISPD | all variables 10 | conditional parameters (e.g. `mu_init` only for monotone) |
| `ipopt_warm.yaml` | same | ISPD | previous solution | |
| `ispd.yaml` | 16 ISPD / cg2o options | IPOPT warm | all variables 10 | |
| `al.yaml` | 3 penalty options | ISPD | all variables 10 | the unchanged AL fails the 1e-4 residual gate: expect "no winner" unless a candidate passes |
| `bipm.yaml` | kappa schedule + initial equality multiplier | ISPD | feasible | relaxed: steps at the limit are penalised, not rejected |
| `bipm_strict.yaml` | same | ISPD | feasible | no step may reach the limit |

**What a study does.** (1) It measures the starting setting (the values in `config/config.yaml`) with the same quality gates as every
candidate. (2) The search proposes settings; each is run on every case (horizon) at a short length (`screening_fidelity`).
(3) A setting is **rejected** if any run violates a gate: residuals, failed solves, steps at the iteration limit, cost excess
against the driver. (4) The best finalists are re-run at the full driving cycle on all cases and compared with the baseline;
only a validated, gate-passing setting is exported (`selected_config.yaml`, `best_config.json`). If nothing beats the baseline,
the report says so.

**Gates (per run, any case, any repeat)** — set in each study file, with the reason written next to them:

| study | residuals `eq_max`, `ineq_max` | failed solves | steps at the limit | cost excess vs the driver |
|---|---|---|---|---|
| `ipopt_cold`, `ipopt_warm` | <= 5e-4 | none | <= 0.2 % of steps (7 per full cycle) | mean <= 1e-4 |
| `ispd`, `al` | <= 1e-4 | none | <= 0.2 % | mean <= 1e-4 |
| `bipm` (relaxed) | not gated | <= 2 % | penalised in the objective (weight 2) | mean <= 2 % |
| `bipm_strict` | <= 1e-4 | none | none | mean <= 1e-4 |

The driver (reference) itself must be clean: finite, successful, no step at the limit, residuals <= 1e-4. **Baseline outside the search domain.** If a value in `config.yaml` violates its study domain (outside `low`/`high`,
not one of the choices, or a broken relation), the study prints a WARNING and **updates the baseline before the first
run**: the value becomes the parameter's `default` from the study file (if valid), otherwise it is clipped to the nearest
bound. Operands of a broken relation are reset to their defaults; if that does not fix it, the study stops with an error.
The changes are listed in `report.txt` and `inputs/baseline_repairs.json`. Numbers written as `1e-3` / `5e5` (read as
text by Python's YAML) count as numbers, not as violations. `config.yaml` itself is not changed.
If an unchanged baseline fails a gate
it can still normalise the scores but can never be selected; read the reasons with `status` before loosening a gate.

**Fixed accuracy.** The studies do not tune tolerances (`tol`, `compl_inf_tol`, ...): they stay as in `config.yaml`, so a gain
cannot come from solving less accurately. (Part of the gain reported by the first library came from loosening them.)

**Frozen configuration.** `config.yaml` is copied to `<study>/inputs/base_config.yaml` when the study starts; later edits of
`config.yaml` neither change nor block the study. The binary is fingerprinted too: do not rebuild `macc_run` during a study.

## Reading a run while it runs
* `<study>/trials.csv` gets one row per finished evaluation (flushed at once). Line 1 holds the command, line 2 explains the
  columns (`pandas.read_csv(path, comment="#")`). Columns: `trial, time, phase, status (ok/REJECTED), score, fidelity`, per case the
  objective metric and every constrained metric (`c30_iterations`, `c30_hit_fraction`, ...), one column per parameter
  (empty = absent), `reasons`.
* `scripts/tune.sh status <study> [--last 20]`: command, counts, baseline, best so far with the parameters that differ from the
  baseline, latest evaluations, selection.

## Stop, finish, resume
* **Ctrl-C or `kill <pid>`** (SIGINT and SIGTERM, also for `nohup` jobs): stops scheduling, keeps every completed evaluation, writes
  `interrupted.json`.
* **`run ... --finish`**: no further search; validates the best finalists found so far and selects (also after a hard kill).
* **`run ... --resume --trials N`**: continue; `--trials` is the TOTAL number of search attempts. Resume is refused if the code, binary,
  settings or space changed (a deliberate guard).
* `--max-seconds S` limits the search time; validation is additional. `--screen-only` skips validation (no winner is exported).

## Deep run: IPOPT (cold), BIPM and ISPD in parallel
```bash
scripts/tune_deep.sh start         # three studies at once, 5.5 h of search by default (HOURS=8 to change), then full-cycle validation
scripts/tune_deep.sh status
scripts/tune_deep.sh stop          # then:
scripts/tune_deep.sh finish        # validate what was found and write the reports
```
16 simulations run at a time (`jobs` in the study files: 9 + 4 + 3); the machine has 20 threads. Each simulation is single-threaded.
Results: `results/tuning/<timestamp>_<study>/`.

## Cautions
* **BIPM and the feasible start.** The feasible start (fig2, BIPM) still has an open reproducibility bug (see
  "Reproducibility" in docs/EXPERIMENTS.md): the same run can diverge depending on e.g. the output-path length. Studies that use `init: feasible`
  (`bipm*.yaml`) are not trustworthy until that is fixed. IPOPT, ISPD and AL studies use the constant start and were verified
  deterministic.
* **Timing.** Candidates run in parallel: do not quote milliseconds from a study. Iteration counts are exact. For timing use
  `experiment.timing: true`, `jobs: 1` (see the library README) on an idle machine.
* **Power limit.** Check `cat /sys/class/powercap/intel-rapl-mmio:0/constraint_0_power_limit_uw` (45 W); at 13 W parallel jobs get
  no more throughput than a single one.
* **Validation is expensive:** a full cycle of IPOPT cold on three horizons takes about 5 minutes per finalist; finalists run in parallel.
* A study result is valid for the problem it was tuned on (cases, driving cycle, start type); add `validation_cases` for scenarios
  that must not be tuned on.

## Tests
```bash
scripts/setup_tuning_env.sh --test          # or:  cd experiments/solver_tuning && ../../.venv-tuning/bin/python -m pytest -q
```
(`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `env -u PYTHONPATH` are used by the scripts: a sourced ROS installation registers pytest plugins
that need packages the isolated environment does not have.)

## History
The first library (registry of algorithms, Experiment plug-ins, live `trials.csv`) is in `legacy/experiments/tuning_v1/`; it was replaced by
`experiments/solver_tuning` because the new library gates the baseline like every candidate, validates on all cases, journals every run
transactionally and refuses unsafe resumes. Features of the first library that were carried over: the live `trials.csv`, the
detailed `status`, `--finish`, signal handling, the three plots, the deep-run script, parallel validation, and the BIPM
initial-multiplier parameter.
