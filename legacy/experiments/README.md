# legacy/experiments

| folder | what it was |
|---|---|
| `scripts/` | harvesting and plotting scripts of the first paper version (read the `.bin` files of the first program, including the AMPL comparison of that time) |
| `results_old/` | result tables (`.xlsx`) and figures of the first paper version |
| `tuning_v0/` | the first tuning scripts, one per solver (grid / Bayesian search for BIPM and IPOPT) |
| `tuning_v1/` | the second tuning library; replaced by `experiments/solver_tuning` |

The experiments of the current paper are run with `experiments/run_experiment.py` and evaluated with `paper/analysis/`.
