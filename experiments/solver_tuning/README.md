# Solver Tuning 2

> **In the MACC repository** (version 2.1.0 integration): run it with `scripts/tune.sh` (isolated `.venv-tuning/`, created by
> `scripts/setup_tuning_env.sh`); the ready-made studies are in [`studies/`](studies/); the repository guide is `docs/TUNING.md`.
> Additions over 2.0.0: live `trials.csv` (written after every evaluation, command in line 1), a detailed `status`, `--finish`,
> SIGINT/SIGTERM handling, parallel finalist validation, a frozen copy of the base configuration inside each study, three plots.

A general Python package for tuning expensive simulations, optimizers and external
programs. MACC is one optional adapter; the search engine has no dependency on MACC,
IPOPT, cg2o, NumPy, or plotting libraries.

This is a redesign of the supplied `tuning.zip`, not a drop-in replacement for its
internal modules. The package import remains `tuning`; use a clean virtual environment
or remove the old `experiments/tuning` from the import path. See [migration](docs/MIGRATION.md).

## Start in five minutes

From the extracted project directory, with Python 3.10 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[bo,plots,dev]'
PYTHONPATH=examples python -m tuning run examples/toy.yaml --out results/toy --trials 30
python -m tuning status results/toy
python -m tuning plot results/toy
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell and set
`$env:PYTHONPATH = "examples"`. These are the only shell-specific parts of the toy
example. Tests were run on Linux; Windows process-tree cleanup is limited to the
immediate child process.

The toy runs an actual analytic experiment with constraints and an additional
validation case. It does not require any solver executable.

For Bayesian optimization, change `method: random` to `method: tpe` **before
starting a new study**. The TPE extra targets Optuna 4.x explicitly; version 5+
requires a separate integration update rather than silently relying on deprecated
APIs. Search never promises a global optimum.

## What changed

- Standalone installable package with a Python API and CLI.
- General Python-function and external-command adapters.
- MACC adapter for IPOPT cold/warm, ISPD, BIPM and AL.
- Random search, coordinate search, conditional multivariate TPE, and numeric
  differential evolution (DE).
- Mixed integer/categorical/logarithmic domains, optional settings, conditions and
  cross-parameter relations.
- Identical quality gates for baselines and candidates, checked per run and repeat.
- Validation always covers the union of screening and extra validation cases.
- An invalid baseline can normalize measurements, but cannot be selected.
- No validated feasible configuration means **no exported best configuration**.
- Exact inputs, commands, resolved settings and raw measurements retained.
- Transactional SQLite history, process locking and compatible resume.
- One concurrency budget: `jobs` is the maximum number of simultaneous experiment
  calls. Cases and repeats inside one evaluation are sequential.
- Isolated MACC timing mode rejects concurrent runs and cached measurements.
- TPE failures are infeasible observations with infinite objective, not a magic
  finite penalty such as 10.
- Reports and plots distinguish screening progress from the final validation winner.

## Use it with MACC

Edit the paths in `examples/macc_warm.yaml` first. They are resolved relative to the
YAML file, not the current working directory.

```bash
python -m tuning run examples/macc_warm.yaml --out results/ipopt-warm --trials 100
python -m tuning status results/ipopt-warm
```

Other starting specifications are `macc_cold.yaml`, `macc_ispd.yaml`,
`macc_bipm.yaml`, and `macc_al.yaml`. Accuracy thresholds are explicit examples,
not universal engineering defaults. Strict settings may find no eligible winner;
inspect the actual residuals and solve statuses before changing thresholds.

MACC runs explicitly set:

- driver and target solver, horizon and initialization;
- `mpc.run_times=1`, including warm-start comparisons;
- the common and IPOPT iteration budgets;
- `mpc.loop_size`, including `0` for the full driving cycle.

The original input YAML is never overwritten. The adapter starts from a deep copy,
removes all managed settings for a candidate, and applies only its active values.
An absent optional setting is therefore **truly absent**, not inherited from the
base YAML. The baseline uses the original settings, except values that violate the search domain: those are
replaced before the first run (declared default, else clipped to the bounds) with a WARNING, and listed in
`report.txt` and `inputs/baseline_repairs.json` (`Space.repair`).
`executed_config.yaml` records every trial's effective configuration.

Reference measurements must also be finite, successful and feasible. This avoids
rejecting a good candidate because an untrustworthy reference had a lower cost.
The one-sided `cost_excess_mean` metric penalizes only higher candidate objective;
`cost_agreement_mean` separately records absolute agreement. Near-zero reference
cost makes relative metrics unstable; adapt the metric if that applies.

For timing, set `experiment.timing: true`, `settings.jobs: 1`,
`settings.cache: false`, and use `objective.metric: time_ms`. Repeat full
trajectories on an otherwise idle machine. Internal BLAS/OpenMP thread counts
are held at one in MACC runs. This is an execution protocol, not a guarantee
against OS scheduling noise.

### Regenerate ISPD-versus-IPOPT figures

After a successful validated MACC selection:

```bash
python -m tuning macc-figures results/ipopt-warm --macc-root /absolute/path/to/MACC
```

The bridge uses your existing `macc_exp.figures` and plotting dependencies and
writes PDF/PNG comparisons under the study's `figures/`. It reads repeat 0 of the
selected validation evaluation and performs no solver runs. It does not invent
figures if there is no validated winner. All repetitions remain available for
statistical analysis. General studies can use `plot` for search progress or
provide their own domain-specific plots.

## Resume and budgets

```bash
PYTHONPATH=examples python -m tuning run examples/toy.yaml --out results/toy --trials 100 --resume
```

`--trials` is the **total search-attempt budget**, including previous attempts.
Baseline and finalist validation evaluations are additional. Cached proposals and
parameter combinations rejected before simulation still consume an attempt.
Interrupted in-flight requests are marked `abandoned` on resume and also consume
budget; they are not represented as completed measurements.

Resume checks a manifest containing package source hashes, Python/dependency
versions, experiment fingerprint, baseline, search domains, method, constraints,
objective, cases, repeats and seed. If any changes, create a new study folder.
The original baseline denominator is retained, not remeasured after every resume.
Only the search budget, wall-time scheduling budget and decision to validate may
change without changing the manifest.

`--max-seconds` limits scheduling of new search batches; existing calls finish,
and baseline/validation work is additional. For a quick screening-only run, use
`--screen-only`; it writes a report but never exports a validated best config.

Ctrl-C stops new search work, waits for already launched calls, and retains
completed records. Resume to continue. SIGKILL or a power failure may leave
abandoned requests, but completed SQLite transactions survive. No unsafe pickled
sampler state is loaded. Use a local filesystem for the SQLite database and lock.

## Outputs

| File | Purpose |
| --- | --- |
| `manifest.json` | Immutable study identity and resume guard |
| `trials.sqlite3` | Live authoritative request/result journal |
| `trials.csv` | **Live** table, one row appended after every evaluation (command in line 1); rewritten completely at exit |
| `log.jsonl` | Full-detail export refreshed when the controller exits |
| `inputs/` | Frozen copy of the MACC base configuration and of the study file |
| `artifacts/trial-.../` | Per-run input, output, metrics, commands and logs |
| `report.json`, `report.txt` | Final status and selected validation measurement |
| `best_config.json` | Validated parameter map, only when a winner exists |
| `selected_config.yaml` | MACC configuration with optional removals materialized |
| `search_progress.png` | Optional screening plot |

`status` reads the live SQLite database, so it works while tuning. Search tables
retain failed trials and reasons. A selected baseline means no eligible finalist
beat it; the report identifies its actual validation trial. Only configurations
that passed screening enter finalist validation; a candidate that fails a short
run is not claimed to be bad on every possible scenario.

## Extend it beyond MACC

Choose one route:

1. **Python function:** implement `evaluate(parameters, context) -> dict[str,float]`.
   `context` supplies case, fidelity, seed, baseline flag and a unique artifact
   directory. See `examples/toy_problem.py` and `examples/python_api.py`.
2. **External program:** read `{request}` JSON and write `{result}` JSON containing
   `{"metrics": {...}}`. No shell interpolation is used. See
   `examples/external_program.py` and `examples/command.yaml`.
3. **Custom Experiment:** subclass `Experiment`, implement `run()` and
   `fingerprint()`, then pass it to `Study` from Python. Override `baseline()` and
   `export()` when the experiment needs special configuration handling.

The objective can minimize or maximize a numeric metric, raw or relative to the
baseline. Optional penalty metrics have nonnegative weights. Constraints are
separate hard bounds, applied to each replicate before aggregation. More advanced
metric definitions belong in the adapter; for example, return a worst-case KKT
residual rather than averaging it away. Cases have equal weight; repetitions are
averaged within each case. Multiobjective/Pareto optimization is not implemented.

For custom strategies, pass a factory to `Study` through the Python API as
described in [extension guide](docs/EXTENDING.md).

## Validate the implementation

```bash
python -m pytest -q
python -m build
```

See [validation record](docs/VALIDATION.md) for what was actually tested in this
release. The MACC adapter was tested against a contract-compatible fake executable;
no IPOPT/cg2o performance improvement is claimed without real solver experiments.

## Scientific limitations

A longer prefix of the same driving cycle is broader verification, not an
independent driving scenario. Reserve separate scenarios/cases for final testing.
Repeated runs measure variability; they do not establish independent scenario
generalization. Keep accuracy requirements fixed when claiming solver efficiency.
Primal feasibility and objective agreement do not establish KKT stationarity or
global optimality; supply those metrics if the solver exposes them.

The included BIPM/AL specifications do not tune toward published iteration counts
or exempt their failures. Paper reproduction and performance tuning should be
separate, explicitly labeled studies. Shared options that alter a fixed MACC
driver are rejected, except AL-specific rho options verified in the supplied C++
backend. ISPD may tune shared cg2o settings when its driver is IPOPT.
