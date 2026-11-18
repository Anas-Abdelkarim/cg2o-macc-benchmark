# legacy/helpers

Header-only helpers of the first program (`../application/main_closed_loop.cpp`).

* `helper_config.hpp` — finds and reads `config.yaml`.
* `helper_optimizer_setup.hpp` — creates the g2o/cg2o optimizer and linear solver from a numeric solver id.
* `mpc_runner.hpp` — the closed-loop MPC loop.

Replaced by `MACC/src/core/config.*`, `MACC/src/backends/cg2o/` and `MACC/src/experiment/`.
