# legacy/ — replaced code, kept for reference

Nothing in this folder is built, imported or needed to reproduce the paper. It documents earlier versions of the
MACC application and its scripts. Each sub-folder has its own README.

| item | what it was | replaced by |
|---|---|---|
| `application/` | the first closed-loop program (`main_closed_loop.cpp`, executable `mpc_space_exc`) and its CMake file | `MACC/src/apps/macc_run.cpp` |
| `helpers/` | header-only helpers of that program: configuration lookup, optimizer setup, MPC loop | `MACC/src/core`, `MACC/src/backends/cg2o`, `MACC/src/experiment` |
| `data_loader.hpp`, `data_saver.hpp` | binary result files (`.bin`) of the first program | `steps.csv` / `summary.json` per run (`MACC/src/experiment/report.cpp`) |
| `config_best_linear.yaml.old` | configuration of an early linear-solver comparison | `config/config.yaml` and the `linear-solvers` preset |
| `docs/` | notes of the move to the cg2o `dev` API and the former project-structure file | `README.md`, `docs/ARCHITECTURE.md` |
| `experiments/` | result-harvesting and plotting scripts of the first paper version, the first tuning scripts, old result tables | `experiments/`, `paper/analysis/` |
| `tests/` | tests of replaced tools | `tests/`, `scripts/test_build_workflows.sh` |
