#ifndef MACC_BACKENDS_CONTROLLER_HPP
#define MACC_BACKENDS_CONTROLLER_HPP

// Common interface of every optimal-control backend (cg2o, native IPOPT, ...).
// A controller solves the MACC problem described by the shared MPCParameters at
// its *current* state; the closed-loop runner moves the plant between calls.

#include <limits>
#include <string>
#include <utility>
#include <vector>

namespace macc::backends {

struct SolveResult {
  double u = 0.0;           // commanded force  f_t[0] - f_b[0]  [N]
  int iterations = 0;       // solver iterations
  double time_ms = 0.0;     // wall time of the solve call only
  double cost = std::numeric_limits<double>::quiet_NaN();     // common objective f(x*)
  // objective as reported by the solver's own model (cg2o: sum of chi^2 of the cost
  // edges, IPOPT: objective of its TNLP). Must equal `cost`; the self test checks it.
  double solver_cost = std::numeric_limits<double>::quiet_NaN();
  double eq_residual = std::numeric_limits<double>::quiet_NaN();   // max |c(x*)|
  double ineq_violation = std::numeric_limits<double>::quiet_NaN(); // max(0, g(x*))
  bool hit_max_iter = false;
  bool success = true;      // false: NaN input / solver failure
  std::string status;       // solver specific status text
  std::vector<double> x;    // solution in the macc::nlp::Layout ordering
};

class Controller {
public:
  virtual ~Controller() = default;
  // Short unique name used in file/column names ("cg2o", "ipopt").
  virtual std::string name() const = 0;
  // Longer description for the report ("cg2o ISPD-IPM (GN, linear solver 14 UMFPACK LU)").
  virtual std::string description() const = 0;
  // Key of the matching paper reference ("cg2o_ispd_feasible", "ipopt_fixed", ...)
  // used to print the comparison with Tables V / VI; empty if there is none.
  virtual std::string paperKey() const { return {}; }
  virtual SolveResult solve() = 0;
  // Effective settings of the solver after configuration (for experiment_info.txt).
  virtual std::vector<std::pair<std::string, std::string>> settings() const = 0;
};

} // namespace macc::backends

#endif // MACC_BACKENDS_CONTROLLER_HPP
