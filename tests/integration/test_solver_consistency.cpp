// End-to-end consistency of the solvers on the real closed loop.
//
//  1. cg2o: the cost of the factor graph (sum of chi^2) equals the objective of the
//     solver-independent NLP evaluated at the same point  -> the graph IS the NLP.
//  2. IPOPT: the objective IPOPT reports equals the same NLP objective.
//  3. cg2o (ISPD-IPM) and native IPOPT reach the same optimum at every step.
//  4. The solutions are feasible.
//
// Usage: test_solver_consistency [horizon] [steps]      (defaults 3 and 60)
#include "macc/backends/factory.hpp"
#include "macc/experiment/experiment.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <sstream>

#ifndef MACC_SOURCE_DIR
#error "MACC_SOURCE_DIR must be defined"
#endif

using namespace macc;

namespace {
int failures = 0;

void check(bool ok, const std::string &what) {
  if (!ok) {
    ++failures;
    std::printf("  FAIL: %s\n", what.c_str());
  }
}
} // namespace

int main(int argc, char **argv) {
  const int N = argc > 1 ? std::atoi(argv[1]) : 3;
  const int steps = argc > 2 ? std::atoi(argv[2]) : 60;

  core::Config cfg = core::Config::fromFile(std::string(MACC_SOURCE_DIR) + "/config/config.yaml");
  cfg.applyOverride("mpc.horizon=" + std::to_string(N));
  cfg.applyOverride("mpc.loop_size=" + std::to_string(steps));
  cfg.applyOverride("experiment.solvers=[ispd, ipopt, ipopt_warm]");
  cfg.applyOverride("experiment.progress_every=100000");

  experiment::Setup setup;
  try {
    setup = experiment::buildSetup(cfg);
  } catch (const std::exception &e) {
    std::printf("setup failed: %s\n", e.what());
    return 1;
  }
  std::ostringstream log;
  const experiment::Result res = experiment::run(setup, log);
  check(res.completed, "closed loop completed: " + res.error);
  const core::Table &t = res.table;
  const std::size_t rows = t.numRows();
  check(rows == static_cast<std::size_t>(steps), "all steps simulated");

  double worst_graph = 0, worst_ipopt = 0, worst_pair = 0, worst_eq = 0, worst_ineq = 0;
  int compared = 0;
  for (std::size_t i = 0; i < rows; ++i) {
    const double c_ispd = t.values("ispd_cost")[i], g_ispd = t.values("ispd_solver_cost")[i];
    const double c_ip = t.values("ipopt_cost")[i], s_ip = t.values("ipopt_solver_cost")[i];
    const double c_wm = t.values("ipopt_warm_cost")[i];
    const auto rel = [](double a, double b) { return std::fabs(a - b) / std::max(1.0, std::fabs(b)); };
    worst_graph = std::max(worst_graph, rel(g_ispd, c_ispd));
    worst_ipopt = std::max(worst_ipopt, rel(s_ip, c_ip));
    for (const char *s : {"ispd", "ipopt", "ipopt_warm"}) {
      worst_eq = std::max(worst_eq, t.values(std::string(s) + "_eq_residual")[i]);
      worst_ineq = std::max(worst_ineq, t.values(std::string(s) + "_ineq_violation")[i]);
    }
    // compare optima only where IPOPT really converged
    if (t.values("ipopt_hit_max_iter")[i] < 0.5 && t.values("ipopt_warm_hit_max_iter")[i] < 0.5) {
      worst_pair = std::max({worst_pair, rel(c_ispd, c_ip), rel(c_wm, c_ip)});
      ++compared;
    }
  }
  std::printf("N=%d, %d steps\n", N, steps);
  std::printf("  graph cost vs NLP objective (cg2o)  : worst relative difference %.2e\n", worst_graph);
  std::printf("  IPOPT objective vs NLP objective    : worst relative difference %.2e\n", worst_ipopt);
  std::printf("  cg2o vs IPOPT optimum (%d steps)    : worst relative difference %.2e\n", compared, worst_pair);
  std::printf("  worst equality residual / inequality violation : %.2e / %.2e\n", worst_eq, worst_ineq);

  check(worst_graph < 1e-9, "factor-graph cost equals NLP objective");
  check(worst_ipopt < 1e-9, "IPOPT objective equals NLP objective");
  check(compared > rows / 2, "IPOPT converged on most steps");
  check(worst_pair < 1e-4, "cg2o and IPOPT reach the same optimum");
  check(worst_eq < 1e-4, "equality constraints satisfied");
  check(worst_ineq < 1e-5, "inequality constraints satisfied");

  std::printf(failures ? "FAILED (%d)\n" : "PASSED\n", failures);
  return failures ? 1 : 0;
}
