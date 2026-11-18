# Local convergence condition of cg2o (analysis only)

Paper Sec. VI-E. Evaluates, at every final iterate of the paper's MACC closed loop (N = 3, 15, 30), whether cg2o's
Gauss–Newton Newton-type iteration satisfies the local convergence condition

    rho(I - Jhat^-1 J) < 1   <=>   all nu in (0, 2),   nu = eig(N_h^T (H_p + E) N_h, N_h^T H_p N_h),

with `E = HessL - H_GN` (omitted second-order terms), `HessL` by central differences of the Lagrangian
gradient `gradL = sum J_e^T Omega e + J_h^T gamma + J_g^T lambda` (cg2o normalization, multipliers fixed).
Nothing here changes a solver, a setting or a result; `macc_run` is not touched.

| File | Role |
|---|---|
| `export_macc.cpp` | Runs the paper's closed loop with an ISPD controller configured exactly like `Cg2oController` (QDLDLT, `sigma_eq = 0`, settings from the run's `config_resolved.yaml`). After each solve it reads X, gamma, lambda, s, kappa and every edge's error and analytic Jacobian, builds `H_GN`, `H_g`, `H_p`, `J_h`, `J_g`, `gradL`, and `HessL` (FD steps 1e-6, 1e-5, 1e-7; split by factor type), and checks `H_p` against cg2o's assembled Hessian. Vertex estimates are restored with push/pop and the edges are re-linearized at the final iterate, so the next solve is unaffected (`--reference steps.csv` counts iteration mismatches against the paper run). |
| `analyze.py` | Reduced form with scipy (`null_space`, `eigh(Hr_ex, Hr)`), attribution of E to factor types at the extreme eigenvector, validations, CSV / summary / report. The same file evaluates the quadrotor benchmark of the paper (separate repository). |

## Run

```bash
cmake --build build/macc --target export_macc          # option MACC_BUILD_CONVERGENCE_CHECK (ON)
A=results/experiments/<fig3 folder>/runs; O=results/convergence_check/macc     # any fig3 experiment
for d in $A/*_N3 $A/*_N15 $A/*_N30; do N=${d##*_N}
  build/macc/bin/export_macc --config $d/config_resolved.yaml --reference $d/steps.csv --out $O/N$N --assembled-every 50
done
PY=python3                                             # needs numpy + scipy (pip install scipy)
$PY experiments/convergence_check/analyze.py --run macc:3:cold:$O/N3 --run macc:15:cold:$O/N15 \
    --run macc:30:cold:$O/N30 --full-check-benchmarks macc:3 --out $O/analysis
$PY experiments/convergence_check/analyze.py --from-csv $O/analysis --out $O/analysis   # report only
```

Export: about 1 min for all 11 589 problems (≈ 510 MB of binary records, git-ignored under `results/`).

## Outputs (`--out`)

* `convergence_condition.csv` — one row per problem: benchmark, N, start, problem id, iterations, converged,
  hit_limit, rho, nu_min, nu_max, stationarity (absolute and relative), Newton decrement of the next step,
  wrong-convention ratio, kappa, dominant factor type of E and the contributions `w^T E_t w`, FD checks.
* `summary.csv` — per benchmark/horizon/start: max, median, P95 of rho and the number with rho >= 1
  (converged solves only; solves at the iteration limit are counted separately).
* `full_kkt_check.csv` — dense `rho(I - Jhat^-1 J)` in (X, gamma, lambda, s) vs the reduced form.
* `report.md` — validation results and the problems where the condition fails.

## Numerically null directions

`nu` is invariant under congruence, so `Hr` and `Hr_ex` are Jacobi-scaled before the eigenproblem. Directions whose
scaled eigenvalue is below 1e-10 of the largest are numerically null (MACC: the traction force with its rate-limit
slack when that limit is inactive); `nu` and `rho` are computed
on the complement. The deflation is *clean* when E on those directions and their coupling to the rest are below
1e-8 (scaled), i.e. the exact Jacobian is equally singular there and nothing is approximated; clean cases stay in
the statistics (columns `hr_deflated`, `hr_E_null`, `hr_E_cross`), others would be listed as "condition undefined".
