# Tests

| test | what it checks | needs |
|---|---|---|
| `unit/test_nlp_derivatives.cpp` | exact Jacobian and Hessian of the MACC NLP against finite differences, for space- and time-domain dynamics and for cubic and linear speed bounds, horizons N = 1, 3, 8 (7 variables and 16 constraint rows per stage) | nothing but Eigen |
| `integration/test_solver_consistency.cpp` | runs ISPD-IPM and native IPOPT (cold and warm start) in a short closed loop and checks that (1) the factor-graph cost equals the NLP objective, (2) IPOPT's objective equals the NLP objective, (3) both solvers reach the same optimum, (4) the equality residual and inequality violation of the returned solutions are small | IPOPT |
| `../scripts/test_build_workflows.sh` | the build scripts (mocked `git` / `cmake`, nothing is downloaded or compiled) | bash |

```bash
ctest --test-dir build/macc --output-on-failure       # the C++ tests
./scripts/test_build_workflows.sh                      # the script tests
./build/macc/tests/test_solver_consistency 30 100      # horizon N=30, 100 closed-loop steps
```

The consistency test is the reason the IPOPT numbers can be compared with the cg2o
numbers: both solvers are scored by the same `MaccNLP`, so a difference in iterations
or time is a difference in the *solver*, not in the *problem*.
