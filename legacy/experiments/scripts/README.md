# legacy/experiments/scripts

Scripts of the first paper version. They read the binary result files of the first program
(`data_saver/data_loader.py`) and draw the comparison figures of that version.

* `results_harvesting*.py`, `results_comparison*.py`, `results_comparison.m` — load and compare runs.
* `accepted/` — the scripts behind the figures of that version: cg2o vs BIPM, cg2o vs IPOPT, the established solvers
  through AMPL (KNITRO, LOQO, CONOPT, MINOS, SNOPT), the failed closed loops, the linear solvers and the vehicle data.

Replaced by `experiments/macc_exp/` and `paper/analysis/`.
