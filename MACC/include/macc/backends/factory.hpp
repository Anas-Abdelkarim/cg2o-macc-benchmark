#ifndef MACC_BACKENDS_FACTORY_HPP
#define MACC_BACKENDS_FACTORY_HPP

#include "macc/backends/controller.hpp"
#include "macc/core/config.hpp"
#include "macc/mpc/parameters.h"

#include <memory>
#include <string>

namespace macc::backends {

// Options that differ between runs of the same executable. They are resolved
// from the YAML config (+ --set overrides) by macc::experiment::buildOptions().
struct Cg2oSettings {
  std::string algorithm = "ispd";   // ispd | bipm | al
  std::string unconstrained = "GN"; // GN | LV | DL
  int linear_solver = 14;
  int max_iterations = 120;
  bool feasible_init = false;       // false: constant guess `init_value` (paper)
  bool warm_start = false;          // start every solve from the previous solution (solver name "<x>_warm")
  double init_value = 10.0;
  int termination_criterion = 1;    // 0 UpdateNorm, 1 NewtonDecrement, 2 GradientNorm
};

struct IpoptSettings {
  int max_iterations = 120;
  double init_value = 10.0;
  // true: the four f_t / f_b limit rows per stage become variable bounds; false: all 16 rows/stage
  // stay general constraints, exactly like the cg2o factor graph.
  bool single_variable_rows_as_bounds = true;
  // "fixed": every variable = init_value at every step (paper protocol);
  // "previous": start from the previous step's solution.
  std::string init_mode = "fixed";
  // name -> value, written to ipopt.opt semantics (typed by IPOPT itself)
  std::vector<std::pair<std::string, std::string>> options;
};

Cg2oSettings readCg2oSettings(const core::Config &cfg);
IpoptSettings readIpoptSettings(const core::Config &cfg);

// Builds the cg2o controller (algorithm chosen at run time). The parameters
// object must already contain the horizon N.
std::unique_ptr<Controller> makeCg2oController(const core::Config &cfg,
                                               std::shared_ptr<mpc::MPCParameters> param,
                                               const Cg2oSettings &settings);

// Native IPOPT (C++ TNLP, exact derivatives). Throws if the build has no IPOPT.
bool ipoptAvailable();
std::string ipoptVersion();
std::unique_ptr<Controller> makeIpoptController(std::shared_ptr<mpc::MPCParameters> param,
                                                const IpoptSettings &settings);

} // namespace macc::backends

#endif // MACC_BACKENDS_FACTORY_HPP
