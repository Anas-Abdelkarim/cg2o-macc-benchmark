# legacy/application

The first MACC program, before the code was split into modules.

* `main_closed_loop.cpp` — closed-loop simulation of the space-domain MPC with one cg2o optimizer (ISPD, AL or BIPM);
  results were written as binary files (`../data_saver.hpp`).
* `CMakeLists.txt.old` — its build file (executable `mpc_space_exc`).
* `core_README.md`, `g2o_solvers_README.md` — notes on the problem formulation and the g2o linear solvers of that version.

Replaced by `MACC/src/apps/macc_run.cpp` and the libraries in `MACC/src/`.
