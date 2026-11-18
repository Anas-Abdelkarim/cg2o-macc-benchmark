# cmake/

Reusable CMake modules of MACC.

| file | purpose |
|---|---|
| `MaccOptions.cmake` | C++ standard, default build type, user options, warning flags |
| `MaccDependencies.cmake` | Eigen, yaml-cpp, g2o, cg2o, optional IPOPT, detection of the available linear solvers |
| `FindIPOPT.cmake` | IPOPT through pkg-config (system package or `install/externals/ipopt`) |
| `MaccSummary.cmake` | prints the configuration summary |
