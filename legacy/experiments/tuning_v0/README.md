# legacy/experiments/tuning_v0

The first tuning scripts, one per solver: `tune_bipm.py` (grid search), `tune_bipm_bo.py`, `tune_ipopt_bo.py`
(Bayesian search), `tune_ipopt_cold.py` (IPOPT from the constant start) and `plot_tuning.py`. They called `macc_run`
directly. Replaced by `../tuning_v1` and then by `experiments/solver_tuning`.
