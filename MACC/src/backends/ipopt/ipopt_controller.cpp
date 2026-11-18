// Native IPOPT backend: the MACC problem is handed to IPOPT through its C++
// TNLP interface, with exact analytic Jacobian and Hessian. There is no
// modelling-language layer between the problem and the solver,
// so iteration counts reflect IPOPT itself and the timings reflect a real
// embedded call.

#include "macc/backends/factory.hpp"
#include "macc/core/timer.hpp"
#include "macc/nlp/macc_nlp.hpp"

#include <IpIpoptApplication.hpp>
#include <IpReturnCodes.hpp>
#include <IpSolveStatistics.hpp>
#include <IpTNLP.hpp>

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <stdexcept>

#ifndef MACC_IPOPT_VERSION_STR
#define MACC_IPOPT_VERSION_STR "unknown"
#endif

namespace macc::backends {

namespace {

using Ipopt::Index;
using Ipopt::Number;

class MaccTNLP final : public Ipopt::TNLP {
public:
  MaccTNLP(nlp::MaccNLP &problem, bool rows_as_bounds) : nlp_(problem), rows_as_bounds_(rows_as_bounds) {
    buildMapping();
  }

  void setStart(std::vector<double> x0) { x0_ = std::move(x0); }
  void resetResult() {
    have_solution_ = false;
    x_.clear();
    obj_ = std::numeric_limits<double>::quiet_NaN();
    status_ = Ipopt::INTERNAL_ERROR;
  }
  bool haveSolution() const { return have_solution_; }
  const std::vector<double> &solution() const { return x_; }
  double objective() const { return obj_; }
  Ipopt::SolverReturn solverStatus() const { return status_; }

  int numRowsPassedToIpopt() const { return m_eff_; }

  bool get_nlp_info(Index &n, Index &m, Index &nnz_jac_g, Index &nnz_h_lag,
                    IndexStyleEnum &index_style) override {
    n = nlp_.numVariables();
    m = m_eff_;
    nnz_jac_g = static_cast<Index>(jac_keep_.size());
    nnz_h_lag = nlp_.hessianNnz();
    index_style = C_STYLE;
    return true;
  }

  bool get_bounds_info(Index n, Number *x_l, Number *x_u, Index m, Number *g_l,
                       Number *g_u) override {
    // Either every bound is a general constraint row (exactly as in the factor
    // graph) or the f_t / f_b limit rows are variable bounds.
    if (rows_as_bounds_) {
      nlp_.variableBounds(x_l, x_u, 1e19);
    } else {
      for (Index i = 0; i < n; ++i) {
        x_l[i] = -1e19;
        x_u[i] = 1e19;
      }
    }
    std::vector<double> gl(static_cast<std::size_t>(nlp_.numConstraints()));
    std::vector<double> gu(gl.size());
    nlp_.constraintBounds(gl.data(), gu.data(), 1e19);
    for (std::size_t i = 0; i < gl.size(); ++i)
      if (row_new_[i] >= 0) {
        g_l[row_new_[i]] = gl[i];
        g_u[row_new_[i]] = gu[i];
      }
    (void)m;
    return true;
  }

  bool get_starting_point(Index n, bool init_x, Number *x, bool init_z, Number *, Number *,
                          Index, bool init_lambda, Number *) override {
    if (init_z || init_lambda) return false; // cold start, as in the paper
    if (init_x) {
      if (static_cast<Index>(x0_.size()) != n) return false;
      std::copy(x0_.begin(), x0_.end(), x);
    }
    return true;
  }

  bool eval_f(Index, const Number *x, bool, Number &obj_value) override {
    obj_value = nlp_.objective(x);
    return std::isfinite(obj_value);
  }

  bool eval_grad_f(Index n, const Number *x, bool, Number *grad_f) override {
    nlp_.gradient(x, grad_f);
    return allFinite(grad_f, n);
  }

  bool eval_g(Index, const Number *x, bool, Index m, Number *g) override {
    g_full_.resize(static_cast<std::size_t>(nlp_.numConstraints()));
    nlp_.constraints(x, g_full_.data());
    for (std::size_t i = 0; i < g_full_.size(); ++i)
      if (row_new_[i] >= 0) g[row_new_[i]] = g_full_[i];
    return allFinite(g, m);
  }

  bool eval_jac_g(Index, const Number *x, bool, Index, Index nele_jac, Index *iRow,
                  Index *jCol, Number *values) override {
    if (values == nullptr) {
      jac_full_i_.resize(static_cast<std::size_t>(nlp_.jacobianNnz()));
      jac_full_j_.resize(jac_full_i_.size());
      nlp_.jacobianStructure(jac_full_i_.data(), jac_full_j_.data());
      for (std::size_t e = 0; e < jac_keep_.size(); ++e) {
        iRow[e] = row_new_[static_cast<std::size_t>(jac_full_i_[static_cast<std::size_t>(jac_keep_[e])])];
        jCol[e] = jac_full_j_[static_cast<std::size_t>(jac_keep_[e])];
      }
      return true;
    }
    jac_vals_.resize(static_cast<std::size_t>(nlp_.jacobianNnz()));
    nlp_.jacobianValues(x, jac_vals_.data());
    for (std::size_t e = 0; e < jac_keep_.size(); ++e)
      values[e] = jac_vals_[static_cast<std::size_t>(jac_keep_[e])];
    return allFinite(values, nele_jac);
  }

  bool eval_h(Index, const Number *x, bool, Number obj_factor, Index, const Number *lambda,
              bool, Index nele_hess, Index *iRow, Index *jCol, Number *values) override {
    if (values == nullptr) {
      nlp_.hessianStructure(iRow, jCol);
      return true;
    }
    // rows that became bounds are linear: their multipliers do not enter the Hessian
    lambda_full_.assign(static_cast<std::size_t>(nlp_.numConstraints()), 0.0);
    for (std::size_t i = 0; i < lambda_full_.size(); ++i)
      if (row_new_[i] >= 0) lambda_full_[i] = lambda[row_new_[i]];
    nlp_.hessianValues(x, obj_factor, lambda_full_.data(), values);
    return allFinite(values, nele_hess);
  }

  void finalize_solution(Ipopt::SolverReturn status, Index n, const Number *x, const Number *,
                         const Number *, Index, const Number *, const Number *,
                         Number obj_value, const Ipopt::IpoptData *,
                         Ipopt::IpoptCalculatedQuantities *) override {
    status_ = status;
    obj_ = obj_value;
    if (x != nullptr) {
      x_.assign(x, x + n);
      have_solution_ = true;
    }
  }

private:
  void buildMapping() {
    const int m = nlp_.numConstraints();
    row_new_.assign(static_cast<std::size_t>(m), -1);
    m_eff_ = 0;
    for (int i = 0; i < m; ++i)
      if (!(rows_as_bounds_ && nlp_.isSingleVariableRow(i))) row_new_[static_cast<std::size_t>(i)] = m_eff_++;
    std::vector<int> ri(static_cast<std::size_t>(nlp_.jacobianNnz())), rj(ri.size());
    nlp_.jacobianStructure(ri.data(), rj.data());
    jac_keep_.clear();
    for (std::size_t e = 0; e < ri.size(); ++e)
      if (row_new_[static_cast<std::size_t>(ri[e])] >= 0) jac_keep_.push_back(static_cast<int>(e));
  }

  static bool allFinite(const Number *v, Index n) {
    for (Index i = 0; i < n; ++i)
      if (!std::isfinite(v[i])) return false;
    return true;
  }

  nlp::MaccNLP &nlp_;
  bool rows_as_bounds_;
  int m_eff_ = 0;
  std::vector<int> row_new_;   // old row -> row seen by IPOPT (-1: became a bound)
  std::vector<int> jac_keep_;  // Jacobian entries that stay
  std::vector<double> g_full_, jac_vals_, lambda_full_;
  std::vector<int> jac_full_i_, jac_full_j_;
  std::vector<double> x0_;
  std::vector<double> x_;
  double obj_ = 0.0;
  bool have_solution_ = false;
  Ipopt::SolverReturn status_ = Ipopt::INTERNAL_ERROR;
};

std::string returnStatusText(Ipopt::ApplicationReturnStatus s) {
  switch (s) {
  case Ipopt::Solve_Succeeded: return "Solve_Succeeded";
  case Ipopt::Solved_To_Acceptable_Level: return "Solved_To_Acceptable_Level";
  case Ipopt::Infeasible_Problem_Detected: return "Infeasible_Problem_Detected";
  case Ipopt::Search_Direction_Becomes_Too_Small: return "Search_Direction_Becomes_Too_Small";
  case Ipopt::Diverging_Iterates: return "Diverging_Iterates";
  case Ipopt::User_Requested_Stop: return "User_Requested_Stop";
  case Ipopt::Feasible_Point_Found: return "Feasible_Point_Found";
  case Ipopt::Maximum_Iterations_Exceeded: return "Maximum_Iterations_Exceeded";
  case Ipopt::Restoration_Failed: return "Restoration_Failed";
  case Ipopt::Error_In_Step_Computation: return "Error_In_Step_Computation";
  case Ipopt::Maximum_CpuTime_Exceeded: return "Maximum_CpuTime_Exceeded";
  case Ipopt::Not_Enough_Degrees_Of_Freedom: return "Not_Enough_Degrees_Of_Freedom";
  case Ipopt::Invalid_Problem_Definition: return "Invalid_Problem_Definition";
  case Ipopt::Invalid_Option: return "Invalid_Option";
  case Ipopt::Invalid_Number_Detected: return "Invalid_Number_Detected";
  case Ipopt::Unrecoverable_Exception: return "Unrecoverable_Exception";
  case Ipopt::NonIpopt_Exception_Thrown: return "NonIpopt_Exception_Thrown";
  case Ipopt::Insufficient_Memory: return "Insufficient_Memory";
  case Ipopt::Internal_Error: return "Internal_Error";
  default: return "status " + std::to_string(static_cast<int>(s));
  }
}

class IpoptController final : public Controller {
public:
  IpoptController(std::shared_ptr<mpc::MPCParameters> param, const IpoptSettings &s)
      : param_(std::move(param)), s_(s),
        nlp_(nlp::ProblemData::fromParameters(*param_, false)) {
    if (!param_->useEqualityConstraints())
      throw std::invalid_argument(
          "IPOPT backend: removing the equality constraints is only meaningful for the "
          "cg2o linear-solver study (paper Sec. VI-D)");

    // Options are fed to IPOPT as an option-file stream, so IPOPT itself types
    // them (integer / number / string) and the identical text can be stored in
    // the run directory.
    std::ostringstream opt;
    bool max_iter_given = false;
    for (const auto &kv : s_.options) {
      if (kv.first == "max_iter") max_iter_given = true;
      opt << kv.first << " " << kv.second << "\n";
    }
    if (!max_iter_given) opt << "max_iter " << s_.max_iterations << "\n";
    options_text_ = opt.str();

    app_ = new Ipopt::IpoptApplication();
    std::istringstream is(options_text_);
    const Ipopt::ApplicationReturnStatus st = app_->Initialize(is);
    if (st != Ipopt::Solve_Succeeded)
      throw std::runtime_error("IPOPT Initialize failed (" + returnStatusText(st) +
                               "); check ipopt_settings.options:\n" + options_text_);
    tnlp_ = new MaccTNLP(nlp_, s_.single_variable_rows_as_bounds);
    settings_.emplace_back("backend", "native IPOPT C++ TNLP (exact Jacobian + Hessian)");
    settings_.emplace_back("ipopt_version", MACC_IPOPT_VERSION_STR);
    settings_.emplace_back("initialization", s_.init_mode == "previous"
                                                 ? "previous solution (warm start of the primal variables)"
                                                 : "constant " + std::to_string(s_.init_value));
    settings_.emplace_back("f_t/f_b limit rows",
                           s_.single_variable_rows_as_bounds
                               ? "variable bounds: 12 rows/stage + 4 bounds"
                               : "general constraints: 16 rows/stage");
    settings_.emplace_back("max_iter", std::to_string(maxIterEffective()));
    std::istringstream lines(options_text_);
    std::string line;
    while (std::getline(lines, line)) {
      const auto sp = line.find(' ');
      if (sp != std::string::npos)
        settings_.emplace_back("ipopt." + line.substr(0, sp), line.substr(sp + 1));
    }
  }

  std::string name() const override { return s_.init_mode == "previous" ? "ipopt_warm" : "ipopt"; }
  std::string description() const override {
    return std::string("native IPOPT ") + MACC_IPOPT_VERSION_STR;
  }
  std::vector<std::pair<std::string, std::string>> settings() const override { return settings_; }
  // keys of config/paper_reference.yaml (paper Table V): cold = constant start, warm = previous solution
  std::string paperKey() const override { return s_.init_mode == "previous" ? "ipopt_warm" : "ipopt_cold"; }
  const std::string &optionsText() const { return options_text_; }

  SolveResult solve() override {
    nlp_.setData(nlp::ProblemData::fromParameters(*param_));
    MaccTNLP *tnlp = static_cast<MaccTNLP *>(Ipopt::GetRawPtr(tnlp_));
    if (s_.init_mode == "previous" && !last_x_.empty()) tnlp->setStart(last_x_);
    else tnlp->setStart(nlp_.constantGuess(s_.init_value));
    tnlp->resetResult();

    core::Stopwatch sw;
    const Ipopt::ApplicationReturnStatus st = app_->OptimizeTNLP(tnlp_);
    SolveResult r;
    r.time_ms = sw.elapsedMs();
    if (Ipopt::IsValid(app_->Statistics())) r.iterations = app_->Statistics()->IterationCount();
    r.status = returnStatusText(st);
    r.hit_max_iter = (st == Ipopt::Maximum_Iterations_Exceeded);
    if (tnlp->haveSolution()) {
      r.x = tnlp->solution();
      r.solver_cost = tnlp->objective();
      last_x_ = r.x;
      r.u = nlp_.inputForce(r.x.data());
      r.success = std::isfinite(r.u) && (st == Ipopt::Solve_Succeeded ||
                                         st == Ipopt::Solved_To_Acceptable_Level ||
                                         st == Ipopt::Maximum_Iterations_Exceeded);
      r.cost = nlp_.objective(r.x.data());
      const auto v = nlp_.violation(r.x.data());
      r.eq_residual = v.eq_inf;
      r.ineq_violation = v.ineq_inf;
    } else {
      r.success = false;
      r.u = std::numeric_limits<double>::quiet_NaN();
    }
    return r;
  }

private:
  int maxIterEffective() const {
    for (const auto &kv : s_.options)
      if (kv.first == "max_iter") return std::atoi(kv.second.c_str());
    return s_.max_iterations;
  }

  std::shared_ptr<mpc::MPCParameters> param_;
  IpoptSettings s_;
  nlp::MaccNLP nlp_;
  std::string options_text_;
  std::vector<double> last_x_;
  std::vector<std::pair<std::string, std::string>> settings_;
  Ipopt::SmartPtr<Ipopt::IpoptApplication> app_;
  Ipopt::SmartPtr<Ipopt::TNLP> tnlp_;
};

} // namespace

bool ipoptAvailable() { return true; }
std::string ipoptVersion() { return MACC_IPOPT_VERSION_STR; }

namespace {

// Sets an IPOPT option unless ipopt_settings.options already contains it.
void setDefaultOption(std::vector<std::pair<std::string, std::string>> &options,
                      const std::string &key, const std::string &value) {
  for (const auto &kv : options)
    if (kv.first == key) return;
  options.emplace_back(key, value);
}

// libcoinhsl.so installed by scripts/build_externals.sh (USE_HSL=ON).
std::string defaultHslLibrary() {
#ifdef MACC_SOURCE_DIR
  const std::filesystem::path root = std::filesystem::path(MACC_SOURCE_DIR) / "install/externals/hsl";
  for (const char *rel : {"lib/x86_64-linux-gnu/libcoinhsl.so", "lib/aarch64-linux-gnu/libcoinhsl.so",
                          "lib64/libcoinhsl.so", "lib/libcoinhsl.so"})
    if (std::filesystem::exists(root / rel)) return (root / rel).string();
#endif
  return {};
}

} // namespace

IpoptSettings readIpoptSettings(const core::Config &cfg) {
  IpoptSettings s;
  s.max_iterations = cfg.get<int>("mpc.number_of_iterations", 120);
  s.init_value = cfg.get<double>("mpc.init_value", 10.0);
  s.options = cfg.items("ipopt_settings.options");
  s.single_variable_rows_as_bounds =
      cfg.get<int>("ipopt_settings.single_variable_rows_as_bounds", 1) != 0;

  // IPOPT's linear solver: MUMPS unless use_hsl is set. The HSL solvers (MA27, MA57, ...) need the
  // licensed Coin-HSL library, which IPOPT loads at run time.
  if (cfg.get<bool>("ipopt_settings.use_hsl", false)) {
    std::string lib = cfg.get<std::string>("ipopt_settings.hsl_library", "");
    if (lib.empty()) lib = defaultHslLibrary();
    if (lib.empty() || !std::filesystem::exists(lib))
      throw std::runtime_error(
          "ipopt_settings.use_hsl is true, but libcoinhsl.so was not found" +
          (lib.empty() ? std::string() : " at " + lib) +
          ". Put the Coin-HSL source into externals/ and run USE_HSL=ON ./scripts/build_externals.sh --hsl, "
          "or set ipopt_settings.hsl_library.");
    setDefaultOption(s.options, "linear_solver", cfg.get<std::string>("ipopt_settings.hsl_solver", "ma57"));
    setDefaultOption(s.options, "hsllib", lib);
  } else {
    setDefaultOption(s.options, "linear_solver", "mumps");
  }
  return s;
}

std::unique_ptr<Controller> makeIpoptController(std::shared_ptr<mpc::MPCParameters> param,
                                                const IpoptSettings &settings) {
  return std::make_unique<IpoptController>(std::move(param), settings);
}

} // namespace macc::backends
