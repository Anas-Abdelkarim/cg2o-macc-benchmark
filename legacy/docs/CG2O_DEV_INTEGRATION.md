# cg2o dev integration (2026-10-22)

Reference: https://github.com/snt-arg/cg2o/tree/dev/app/adaptive_cruise_control/cpp_code

This release fixes legacy `solvers/eigen/...` headers in
`include/macc/application/helper_optimizer_setup.hpp`. The current cg2o
installs `cg2o/solvers/{eigen,umfpack,pardiso}/...` and exports optional CMake
targets. Headers and class names now follow the cg2o `dev` example, but
MACC's existing linear_solver.type IDs (0..15) remain unchanged.

Important: `config/config.yaml` selects solver ID 14 (cg2o UMFPACK).
If you built cg2o without `cg2o::solver_eigen_umfpack`, choose solver 3
(g2o Eigen) temporarily or rebuild cg2o with UMFPACK enabled. A missing
optional solver is never silently substituted, because that would corrupt
benchmark comparisons. `config/config_best_linear.yaml` uses ID 6
(cg2o EigenLU), which requires `cg2o::solvers_eigen`.

The main MPC executable uses target `mpc_cg2o_lib`, **not** the legacy
nonexistent `mpc_space_lib`. Default optimizer is ISPD; AL and BIPM can be
selected using `-DMPC_CG2O_OPTIMIZER=AL` or `BIPM`.

## Quick test with existing installed dependencies (do not rebuild externals)

```bash
./scripts/build_workspace.sh --clean
./build/macc/bin/mpc_space_exc
```

To configure an alternate optimizer:

```bash
./scripts/build_workspace.sh --clean -- -DMPC_CG2O_OPTIMIZER=BIPM -DMPC_FEASIBLE_INITIALIZATION=ON
```

Existing cg2o checkout still has priority at `../../unconstrained` (or
`CG2O_LOCAL_DIR`) before falling back to `externals/cg2o` and clone (the default new clone checks out `dev`, preserving existing checkouts).

## What is and isn't tested

Shell scripts can be syntax-checked and tested offline with mocked external
commands. CMake may be smoke-tested against synthetic package targets. A real
compile of cg2o/g2o and MACC requires an environment with Eigen, g2o and cg2o
installed, so it cannot be certified by such tests alone.

The older `src/mpc_time` build is now opt-in (`-DMACC_BUILD_MPC_TIME=ON`),
because the default cg2o space-domain executable does not depend on it and
this experimental legacy branch needs separate API verification.
