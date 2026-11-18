# tuning v1 (replaced by experiments/solver_tuning)

The first tuning library (registry of algorithms + Experiment plug-ins, Bayesian / coordinate search, live trials.csv), written
2026-10-25/26. It is superseded by `experiments/solver_tuning` (v2): stricter quality gates for the baseline, validation over
every case, a transactional SQLite journal, a resume manifest, conditional parameters and no hidden accuracy trade-offs.
Kept for reference only; it is not on the import path (it used the package name `tuning`, which v2 also uses).
The earlier per-algorithm scripts are in
`../tuning_v0/`.
