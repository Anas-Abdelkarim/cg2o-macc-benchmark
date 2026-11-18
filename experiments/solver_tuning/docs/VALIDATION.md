# Validation record

Release: 2.0.0. Implementation and verification performed on Linux with Python
3.12. Dependencies exercised included Optuna 4.9.0 and pytest 9.1.1. Other supported
Python/OS combinations have not been executed in this environment.

## Automated checks

46 tests passed. Coverage includes:

- Numeric/log/integer/categorical and near-one sampling bounds.
- Conditional parameters, real optional removals and invalid-domain detection.
- Cross-parameter relation rejection before launching simulations.
- Baseline preservation outside search bounds; no silent clipping.
- Invalid baselines and invalid candidates cannot be final winners.
- Validation includes all original and extra cases.
- Every repeat must satisfy quality bounds; averaging does not hide failures.
- Nonfinite measurements and invalid references are rejected.
- Cache entries deserialize into independent objects and retain provenance.
- Crash recovery marks incomplete requests abandoned.
- Resume retains the original baseline denominator and total-attempt budget.
- Changed experiment fingerprints are refused on resume.
- Random and TPE serial resume match uninterrupted deterministic proposals,
  including TPE's model-based phase after startup.
- A single global worker budget limits concurrent experiment calls.
- Timing mode enforces isolated measurements.
- Single-controller process locking.
- Random, coordinate, DE and TPE strategies execute end to end.
- Rejected TPE observations are infeasible/infinite rather than a finite magic
  penalty; valid scores above 10 remain correctly ordered.
- Custom strategy feedback errors propagate without exporting a false winner.
- MACC configuration snapshots force the exact simulation length, iteration
  budget and one solve per step.
- MACC target/reference metrics and one-sided cost excess.
- External request/result JSON protocol and subprocess timeout handling.
- A contract-compatible fake MACC executable exercises command execution,
  summary/CSV reading, full-cycle handling, selection and configuration export.
- CLI run/status/resume checks and all MACC example parameter domains.

Ruff's undefined/unused-name checks and formatter checks were run. Both a wheel
and a source distribution were built successfully with setuptools.

## Installed-package smoke test

The wheel was installed into an isolated target directory and exercised through
`python -m tuning`. A conditional TPE study completed its search and validation,
resumed with a larger total budget, displayed live status and generated a search
progress plot. The plot was visually inspected. The toy objective improved; this
checks integration, not superiority of TPE or performance of any real solver.

## What this does not establish

The C++ IPOPT/cg2o libraries are not installed here. No real MACC tuning run was
performed, no numerical improvement is claimed, and MACC paper figures were not
regenerated from real trajectories. The figure bridge relies on the existing
MACC plotting API. Windows process locking is implemented but not tested here;
Windows timeout cleanup guarantees only the immediate process, not descendants.

External data, shared libraries and environment settings are only reproducible
when captured by the adapter's fingerprint or explicit revision/inputs. Arbitrary
Python dependency discovery and distributed/multi-host scheduling are not provided.
A larger search budget is not proof of global optimality, and full-cycle validation
is not a substitute for separate scenarios or independent safety assessment.

## Repository integration record (2.1.0, 2026-10-26)

Done in the MACC repository with the real `macc_run` and the real `config.yaml`:

- 52 tests pass (the original 46 plus 6 for the additions: live table, status, plots, `--finish`, signal handler, frozen base
  configuration); `ruff check --select F` and `ruff format --check` are clean.
- The MACC adapter's assumptions were checked against a real `summary.json` / `steps.csv`; IPOPT cold studies ran end to end
  (random and TPE search, Ctrl-C, resume, validation, figure bridge). Against the untuned default IPOPT configuration a 16-trial TPE
  study under the strict fixed-accuracy gates found a setting that measured, over 600 steps, 57 -> 42 iterations at N=15 (steps at
  the limit 20 -> 0) and 67 -> 49 at N=30 (56 -> 1); only horizons 3 and 15 were part of that study.
- Every file in `studies/` loads, resolves against the repository, and completed a short smoke study.
- The driver gates are satisfiable: with the constant start, ISPD as the reference has 0 steps at the limit and residuals below
  4e-7 over the whole driving cycle for N = 3, 15, 30.
- Found while testing: `config.yaml` is edited while studies run; an edited base configuration makes resume impossible (by design),
  hence the frozen copy in `inputs/`.

Not established: no long (hours) study has been completed yet; the feasible start used by `bipm*.yaml` has an open
reproducibility bug in MACC itself (see 'Reproducibility' in docs/EXPERIMENTS.md), so BIPM results are not trustworthy until it is fixed.
