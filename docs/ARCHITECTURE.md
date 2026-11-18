# Architecture

## Layers

```
apps/macc_run ─ experiment ─┬─ backends/cg2o  ─ fg ─ (g2o, cg2o)
                            ├─ backends/ipopt ─ nlp ─ (IPOPT)      ← the only place that includes IPOPT
                            ├─ solvers   (catalogue of linear solvers)
                            └─ mpc ─ core
```

The CMake libraries (`MACC/src/CMakeLists.txt`) are `core`, `nlp`, `model` (= `fg` + the plant of `mpc`), `solvers`, `cg2o`, `ipopt`
and `experiment`; the executable is `macc_run`. Headers live in `MACC/include/macc/<module>/` and are always included with the module prefix
(`#include "macc/nlp/macc_nlp.hpp"`). There is **no** global include directory per module — this is what removes
the "ambiguous `MPCParameters`" error of the old tree, where two different headers of the same name were visible.

| module | content | depends on |
|---|---|---|
| `core` | `Config` (YAML + `--set`), `Table` (column store → CSV), `stats`, `timer`, `run_info` (machine / build information) | yaml-cpp |
| `mpc` | `MPCParameters` (all model and tuning constants; header only), driving cycle `data_v_h_106_p1`, `ClosedLoopPlant` (plant with model mismatch x1·c_r, x2·c_a, predictor, domain switch; compiled into `model`) | — |
| `nlp` | `MaccNLP`: the problem as plain functions with exact first and second derivatives | `mpc` headers |
| `fg` + `mpc/closed_loop.cpp` (library `model`) | the same problem as a g2o/cg2o factor graph: vertices, cost and constraint edges, `MPCFormulation`; and the closed-loop plant | g2o, cg2o |
| `solvers` | the 19 linear solvers (ids 0..18), availability, `--list-solvers` | g2o, cg2o |
| `backends` | `Controller` interface; `cg2o/` (ISPD-IPM, BIPM, AL) and `ipopt/` (native TNLP) implementations; `factory.hpp` | nlp, fg, solvers |
| `experiment` | `Setup` (config → controllers), `run()` closed loop, report and CSV writing | everything above |

## The MACC problem

`MaccNLP` (`MACC/include/macc/nlp/macc_nlp.hpp`, implementation in `MACC/src/nlp/`: `problem_data.cpp`, `evaluation.cpp`, `structure.cpp`, `macc_nlp.cpp`, and private headers for the Jacobian / Hessian generators) is the problem of paper Eq. 37 / 44:

* variables, 7 per stage: `v_h[1..N]`, `d_h[1..N]`, `slack_1[1..N]`, `f_t[0..N-1]`, `f_b[0..N-1]`, `slack_2[0..N-1]`, `slack_3[0..N-1]`
  (`v_h[0]`, `d_h[0]` are the measured state and constants);
* constraint rows, 16 per stage: two dynamics equalities and fourteen inequalities (speed bounds as cubic or linear
  functions, gap bounds, traction and brake limits, rate limits with slacks) — the enumeration `macc::nlp::Row` documents each row;
* the dynamics are the space-domain model while the minimum of the predicted preceding-vehicle speed is above 3 m/s and the
  time-domain model otherwise (selected per step by the plant; `MaccNLP` follows `ProblemData::space_domain`).

It is used three times, which is what makes the comparison fair:

1. by the IPOPT backend as the TNLP (objective, gradient, constraints, Jacobian, Hessian of the Lagrangian);
2. to **score the solution of every solver** (`cost`, `eq_residual`, `ineq_violation` columns of `steps.csv`);
3. by `test_nlp_derivatives` (finite differences) and `test_solver_consistency` (the factor graph and the NLP are the same problem).

## Controller interface

```cpp
class Controller {
 public:
  virtual std::string name() const = 0;        // "ispd", "bipm", "ipopt", "ipopt_warm", ... (column prefix in steps.csv)
  virtual std::string description() const = 0;
  virtual std::string paperKey() const;        // which reference row of paper_reference.yaml to compare with
  virtual SolveResult solve() = 0;             // solve the problem of the CURRENT state of MPCParameters
  virtual std::vector<std::pair<std::string,std::string>> settings() const = 0;
};
```

`SolveResult` carries `u`, iterations, wall time of the solve call only (setup and scoring excluded), cost as reported by the
solver (`solver_cost`) and as recomputed (`cost`), constraint violation, status and the solution vector.

### Adding a solver

1. Implement `Controller` in `MACC/src/backends/<name>/` (take the data from `param_`, return a `SolveResult`; call
   `nlp::MaccNLP::objective/violation` on your `x` to fill `cost`, `eq_residual`, `ineq_violation`).
2. Add the library in `MACC/src/CMakeLists.txt` and a `make<Name>Controller()` to `backends/factory.hpp`.
3. Recognise its name in `MACC/src/experiment/setup.cpp` (suffix `_warm` / `-warm` is parsed there for warm starts).
4. `macc_run --solvers ispd,<name>` now runs it against ISPD on the same problem and writes the same files.

## cg2o backend notes

* Built on the public cg2o dev API only (`setEqualityRegularization`, `setRhoInitial/Max/UpdateFactor` for AL, ...).
* g2o destruction order matters with `G2O_NO_IMPLICIT_OWNERSHIP_OF_OBJECTS`: the controller owns graph, optimizer and
  algorithm explicitly and releases them in that order.
* cg2o's ISPD prints an unconditional `std::endl`; the controller silences it so that console output stays readable.
* Without equality regularization, the equality rows make the KKT matrix indefinite — see the linear-solver study.
* `<name>_warm`: the graph is not re-initialised, so the previous solution is the starting point.

## IPOPT backend notes

* Options are passed as option-file text (`Initialize(std::istream&)`), so the same code works with IPOPT 3.11 and 3.14.
* Start: every variable 10 (`ipopt`) or the previous solution (`ipopt_warm`; the suffix `_warm` in the solver name selects it).
* `ipopt_settings.single_variable_rows_as_bounds` maps the four rows that only contain `f_t` or `f_b` to variable
  bounds (`1` = yes, the default), otherwise all 16 rows stay general constraints like in the cg2o graph.
* The returned solution is re-evaluated with `MaccNLP`; the objective IPOPT reports is stored as `solver_cost`.

## Configuration

`config/config.yaml` holds every setting; the sections are `experiment`, `mpc`, `linear_solver`, `cg2o`, `general_settings`,
`bipm_settings`, `ispd_settings` (values of paper Table IV), `ipopt_settings` and `acc_settings` (vehicle model).
`--set a.b=value` overrides any of them and is recorded; each run writes the fully resolved `config_resolved.yaml`.
`config/paper_reference.yaml` holds the numbers of paper Tables V and VI used in the reports.
