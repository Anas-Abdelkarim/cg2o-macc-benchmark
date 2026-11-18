# legacy/tests

* `test_cmake_integration.py` — configure-only CMake test with dummy g2o/cg2o packages; replaced by
  `scripts/test_build_workflows.sh`.
* `test_ipopt_tuning.py` — unit test of the quality gates of the first IPOPT tuning script (`tune_ipopt`, now in
  `../experiments/tuning_v0`); the current tuning library has its own tests in `experiments/solver_tuning/tests/`.
