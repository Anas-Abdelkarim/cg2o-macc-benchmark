// cg2o backend: the MACC factor graph solved by the ISPD-IPM (this paper), the
// barrier IPM (BIPM, ref. [6] of the paper) or the augmented Lagrangian (AL)
// optimizer of cg2o. The algorithm is chosen at RUN time from the config, so one
// binary reproduces every experiment.

#include "macc/backends/factory.hpp"
#include "macc/core/stats.hpp"
#include "macc/core/timer.hpp"
#include "macc/fg/formulation.h"
#include "macc/nlp/macc_nlp.hpp"
#include "macc/solvers/linear_solvers.hpp"

#include <cg2o/core/sparse_optimizer_al.h>
#include <cg2o/core/sparse_optimizer_bipm.h>
#include <cg2o/core/sparse_optimizer_ispd.h>
#include <g2o/core/block_solver.h>
#include <g2o/core/optimization_algorithm_dogleg.h>
#include <g2o/core/optimization_algorithm_gauss_newton.h>
#include <g2o/core/optimization_algorithm_levenberg.h>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <type_traits>

namespace macc::backends {

namespace {

std::string upper(std::string s) {
  std::transform(s.begin(), s.end(), s.begin(),
                 [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
  return s;
}

std::string lowerStr(std::string s) {
  std::transform(s.begin(), s.end(), s.begin(),
                 [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  return s;
}

using KV = std::vector<std::pair<std::string, std::string>>;

// cg2o's ISPD optimizer ends every optimize() call with an unconditional
// `std::cout << std::endl`. That is console I/O that has nothing to do with the
// algorithm (and would distort the timings), so std::cout is parked on a null
// buffer around optimize() unless the user asked for solver output.
class CoutSilencer {
public:
  explicit CoutSilencer(bool active) : active_(active) {
    if (active_) old_ = std::cout.rdbuf(&null_);
  }
  ~CoutSilencer() {
    if (active_) std::cout.rdbuf(old_);
  }
  CoutSilencer(const CoutSilencer &) = delete;
  CoutSilencer &operator=(const CoutSilencer &) = delete;

private:
  struct NullBuf : std::streambuf {
    int overflow(int c) override { return c; }
  };
  bool active_;
  NullBuf null_;
  std::streambuf *old_ = nullptr;
};

template <class T> std::string str(const T &v) {
  std::ostringstream os;
  os.precision(10);
  os << v;
  return os.str();
}

std::unique_ptr<g2o::OptimizationAlgorithm>
makeAlgorithm(const std::string &type, std::unique_ptr<g2o::BlockSolverX> block) {
  const std::string t = upper(type);
  if (t == "GN") return std::make_unique<g2o::OptimizationAlgorithmGaussNewton>(std::move(block));
  if (t == "LV") return std::make_unique<g2o::OptimizationAlgorithmLevenberg>(std::move(block));
  if (t == "DL") return std::make_unique<g2o::OptimizationAlgorithmDogleg>(std::move(block));
  throw std::runtime_error("unconstrained_solver.type must be GN, LV or DL (got '" + type + "')");
}

// Applies the settings that are common to all cg2o optimizers (public API of
// cg2o `dev`). Only values the optimizer can report back are listed in the run
// report, so the stored settings are what was really used.
template <class Opt>
void configureGeneral(Opt &o, const core::Config &cfg, KV &report) {
  o.setVerbose(cfg.get<int>("general_settings.verbose", 0));
  o.setNumInnerIterationsMax(cfg.get<int>("general_settings.num_inner_iterations_max", 10));
  o.setAlphaBacktracking(cfg.get<double>("general_settings.alpha_backtracking", -1.0));
  o.setLagrangeMultiplierInitial(cfg.get<double>("general_settings.lagrange_multiplier_initial_eq", 0.0));
  o.setEqualityRegularization(cfg.get<double>("cg2o.equality_regularization", 0.0));
  // 0 disables the convergence test: every solve runs exactly max_iterations (linear-solver study)
  if (cfg.has("cg2o.epsilon_convergence")) {
    o.setEpsilonConvergence(cfg.get<double>("cg2o.epsilon_convergence"));
    report.emplace_back("epsilon_convergence", str(o.terminationCriteria().epsilon_convergence));
  }
  report.emplace_back("alpha_backtracking", str(o.alpha()));
  report.emplace_back("num_inner_iterations_max", str(o.NumInnerIterationsMax()));
  report.emplace_back("lagrange_multiplier_initial_eq", str(o.getLagrangeMultiplierInitial()));
  report.emplace_back("equality_regularization", str(o.equalityRegularization()));
}

void configureAlgorithm(cg2o::SparseOptimizerAL &o, const core::Config &cfg, KV &report) {
  o.setRhoInitial(cfg.get<double>("general_settings.rho_initial_eq", 0.5));
  o.setRhoMax(cfg.get<double>("general_settings.rho_max_eq", 5e5));
  o.setRhoUpdateFactor(cfg.get<double>("general_settings.rho_update_factor_eq", 20.0));
  report.emplace_back("al.rho_initial", str(o.RhoInitial()));
  report.emplace_back("al.rho_max", str(o.RhoMax()));
  report.emplace_back("al.rho_update_factor", str(o.RhoUpdateFactor()));
}

void configureAlgorithm(cg2o::SparseOptimizerBIPM &o, const core::Config &cfg, KV &report) {
  o.setKappaInitial(cfg.get<double>("bipm_settings.kappa_initial"));
  o.setKappaFinal(cfg.get<double>("bipm_settings.kappa_final"));
  o.setKappaUpdateFactor(cfg.get<double>("bipm_settings.kappa_update_factor"));
  // BIPM-only overrides of general_settings (the other cg2o optimizers keep the general values)
  if (cfg.has("bipm_settings.lagrange_multiplier_initial_eq"))
    o.setLagrangeMultiplierInitial(cfg.get<double>("bipm_settings.lagrange_multiplier_initial_eq"));
  if (cfg.has("bipm_settings.num_inner_iterations_max"))
    o.setNumInnerIterationsMax(cfg.get<int>("bipm_settings.num_inner_iterations_max"));
  if (cfg.has("bipm_settings.alpha_backtracking"))
    o.setAlphaBacktracking(cfg.get<double>("bipm_settings.alpha_backtracking"));
  report.emplace_back("bipm.lagrange_multiplier_initial_eq", str(o.getLagrangeMultiplierInitial()));
  report.emplace_back("bipm.num_inner_iterations_max", str(o.NumInnerIterationsMax()));
  report.emplace_back("bipm.alpha_backtracking", str(o.alpha()));
  report.emplace_back("bipm.kappa_initial (t_init)", str(o.kappaInitial()));
  report.emplace_back("bipm.kappa_final", str(o.kappaFinal()));
  report.emplace_back("bipm.kappa_update_factor (nu)", str(o.kappaUpdateFactor()));
}

void configureAlgorithm(cg2o::SparseOptimizerISPD &o, const core::Config &cfg, KV &report) {
  const std::string p = "ispd_settings.";
  o.setStepSizeStrategy(cfg.get<int>(p + "step_size_strategy"));
  o.setIneqBacktrackingStepMin(cfg.get<double>(p + "ineq_backtracking_step_min"));
  o.setAuxBacktrackingStepMin(cfg.get<double>(p + "aux_backtracking_step_min"));
  o.setInitKappaStrategy(cfg.get<int>(p + "_init_kappa_strategy"));
  o.setKappaInitial(cfg.get<double>(p + "kappa_initial"));
  o.setUpdateKappaStrategy(cfg.get<int>(p + "update_kappa_strategy"));
  o.setKappaUpdateFactor(cfg.get<double>(p + "kappa_update_factor"));
  o.setKappaFinal(cfg.get<double>(p + "kappa_final"));
  o.setTau(cfg.get<double>(p + "tau"));
  o.setLimitKappaFinal(cfg.get<int>(p + "limit_kappa_final") != 0);
  o.setInitSlackStrategy(cfg.get<int>(p + "init_slack_strategy"));
  o.setSlackVariableInitialIneq(cfg.get<double>(p + "slack_variable_initial_ineq"));
  o.setInitLagrangeStrategy(cfg.get<int>(p + "init_lagrange_strategy"));
  o.setLagrangeMultiplierInitialIneq(cfg.get<double>(p + "lagrange_multiplier_initial_ineq"));
  o.setIneqPredictionParam(cfg.get<double>(p + "ineq_prediction_param"));
  o.setIneqPredictionStepStrategy(cfg.get<int>(p + "ineq_prediction_step_strategy"));
  o.setIneqPredictionStrategy(cfg.get<int>(p + "ineq_prediction_strategy"));
  o.setKeepAuxPositiveStrategy(cfg.get<int>(p + "keep_aux_positive_strategy"));
  o.setAuxScalingFactor(cfg.get<double>(p + "aux_scaling_factor"));
  o.setAuxCorrectionValue(cfg.get<double>(p + "aux_correction_value"));

  report.emplace_back("ispd.step_size_strategy", str(o.stepSizeStrategy()));
  report.emplace_back("ispd.ineq_backtracking_step_min", str(o.ineqBacktrackingStepMin()));
  report.emplace_back("ispd.aux_backtracking_step_min", str(o.auxBacktrackingStepMin()));
  report.emplace_back("ispd.init_kappa_strategy", str(o.initKappaStrategy()));
  report.emplace_back("ispd.kappa_initial", str(o.kappaInitial()));
  report.emplace_back("ispd.update_kappa_strategy", str(o.updateKappaStrategy()));
  report.emplace_back("ispd.kappa_update_factor (nu)", str(o.kappaUpdateFactor()));
  report.emplace_back("ispd.kappa_final", str(o.kappaFinal()));
  report.emplace_back("ispd.tau", str(o.tau()));
  report.emplace_back("ispd.limit_kappa_final", str(o.limitKappaFinal()));
  report.emplace_back("ispd.init_slack_strategy", str(o.initSlackStrategy()));
  report.emplace_back("ispd.slack_variable_initial_ineq", str(o.slackVariableInitialIneq()));
  report.emplace_back("ispd.init_lagrange_strategy", str(o.initLagrangeStrategy()));
  report.emplace_back("ispd.lagrange_multiplier_initial_ineq", str(o.lagrangeMultiplierInitialIneq()));
  report.emplace_back("ispd.ineq_prediction_strategy", str(o.ineqPredictionStrategy()));
  report.emplace_back("ispd.ineq_prediction_step_strategy", str(o.ineqPredictionStepStrategy()));
  report.emplace_back("ispd.ineq_prediction_param", str(o.ineqPredictionParam()));
  report.emplace_back("ispd.keep_aux_positive_strategy", str(o.keepAuxPositiveStrategy()));
  report.emplace_back("ispd.aux_scaling_factor", str(o.auxScalingFactor()));
  report.emplace_back("ispd.aux_correction_value", str(o.auxCorrectionValue()));
}

template <class Opt> constexpr const char *algorithmName() {
  if constexpr (std::is_same_v<Opt, cg2o::SparseOptimizerISPD>) return "ISPD-IPM";
  else if constexpr (std::is_same_v<Opt, cg2o::SparseOptimizerBIPM>) return "BIPM";
  else return "AL";
}

template <class Opt> class Cg2oController final : public Controller {
public:
  Cg2oController(const core::Config &cfg, std::shared_ptr<mpc::MPCParameters> param,
                 const Cg2oSettings &s)
      : param_(std::move(param)), s_(s) {
    const auto *info = solvers::findLinearSolver(s.linear_solver);
    linear_solver_text_ = std::to_string(s.linear_solver) + " (" + (info ? info->name : "?") + ")";

    auto linear = solvers::makeLinearSolver(s.linear_solver);
    auto block = std::make_unique<g2o::BlockSolverX>(std::move(linear));
    algorithm_ = makeAlgorithm(s.unconstrained, std::move(block));

    const int N = param_->get_N();
    optimizer_ = std::make_shared<Opt>();
    formulation_ = std::make_unique<fg::MPCFormulation<Opt>>(N, optimizer_, param_);
    optimizer_->setAlgorithm(algorithm_.get());

    settings_.emplace_back("algorithm", algorithmName<Opt>());
    settings_.emplace_back("unconstrained_solver", upper(s.unconstrained));
    settings_.emplace_back("linear_solver", linear_solver_text_);
    settings_.emplace_back("max_iterations", std::to_string(s.max_iterations));
    settings_.emplace_back("initialization",
                           s.warm_start ? "previous solution (warm start), first step constant " + str(s.init_value)
                           : s.feasible_init ? "feasible projection (as in barrier-IPM [6])"
                                             : "constant " + str(s.init_value));
    settings_.emplace_back("termination_criterion", std::to_string(s.termination_criterion));
    configureGeneral(*optimizer_, cfg, settings_);
    configureAlgorithm(*optimizer_, cfg, settings_);

    formulation_->setupMPC();
    optimizer_->setConvergenceCriterion(s.termination_criterion);
    optimizer_->initializeOptimization();

    try {
      nlp_ = std::make_unique<nlp::MaccNLP>(nlp::ProblemData::fromParameters(*param_, false));
    } catch (const std::exception &e) {
      std::cerr << "[cg2o] cost/feasibility scoring disabled: " << e.what() << std::endl;
    }
  }

  std::string name() const override { return lowerStr(s_.algorithm) + (s_.warm_start ? "_warm" : ""); }
  std::string description() const override {
    return std::string("cg2o ") + algorithmName<Opt>() + " (" + upper(s_.unconstrained) +
           ", linear solver " + linear_solver_text_ + ")";
  }
  KV settings() const override { return settings_; }
  std::string paperKey() const override {
    return "cg2o_" + lowerStr(s_.algorithm) + (s_.feasible_init && !s_.warm_start ? "_feasible" : "_fixed");
  }

  SolveResult solve() override {
    if (s_.warm_start && have_previous_) {
      // keep the vertex values left by the previous solve
    } else if (s_.feasible_init && !s_.warm_start) {
      formulation_->setInitialGuess(false);
    } else {
      formulation_->setFixedInitialGuess(s_.init_value);
    }
    have_previous_ = true;

    int iterations = 0;
    double elapsed_ms = 0.0;
    {
      CoutSilencer silence(optimizer_->verbose() == 0);
      core::Stopwatch sw;
      iterations = optimizer_->optimize(s_.max_iterations);
      elapsed_ms = sw.elapsedMs();
    }
    SolveResult r;
    r.time_ms = elapsed_ms;
    r.iterations = iterations;
    r.hit_max_iter = iterations >= s_.max_iterations;
    r.u = formulation_->getForceInput(0);
    r.x = formulation_->getSolutionVector();
    r.success = std::isfinite(r.u);
    r.solver_cost = formulation_->computeCost();
    r.status = r.hit_max_iter ? "max_iterations" : "finished";
    score(r);
    return r;
  }

  // cost computed from the graph (sum of chi^2); should equal the NLP objective.
  double graphCost() { return formulation_->computeCost(); }

private:
  void score(SolveResult &r) {
    if (!nlp_) return;
    try {
      nlp_->setData(nlp::ProblemData::fromParameters(*param_));
    } catch (const std::exception &) {
      return;
    }
    for (double v : r.x)
      if (!std::isfinite(v)) return;
    r.cost = nlp_->objective(r.x.data());
    const auto viol = nlp_->violation(r.x.data());
    r.ineq_violation = viol.ineq_inf;
    r.eq_residual = param_->useEqualityConstraints()
                        ? viol.eq_inf
                        : std::numeric_limits<double>::quiet_NaN();
  }

  std::shared_ptr<mpc::MPCParameters> param_;
  Cg2oSettings s_;
  std::string linear_solver_text_;
  bool have_previous_ = false;
  KV settings_;
  // Destruction order matters (reverse of declaration): graph, then optimizer,
  // then the algorithm that the optimizer points to.
  std::unique_ptr<g2o::OptimizationAlgorithm> algorithm_;
  std::shared_ptr<Opt> optimizer_;
  std::unique_ptr<fg::MPCFormulation<Opt>> formulation_;
  std::unique_ptr<nlp::MaccNLP> nlp_;
};

} // namespace

Cg2oSettings readCg2oSettings(const core::Config &cfg) {
  Cg2oSettings s;
  s.algorithm = lowerStr(cfg.get<std::string>("inequality_algorithm", "ispd"));
  s.unconstrained = cfg.get<std::string>("unconstrained_solver.type", "GN");
  // linear_solver.type accepts the numeric id or a key such as "umfpack"
  const std::string ls = cfg.get<std::string>("linear_solver.type", "14");
  const int id = solvers::resolveLinearSolverId(ls);
  if (id < 0)
    throw std::runtime_error("Unknown linear_solver.type '" + ls + "'. Use --list-solvers.");
  s.linear_solver = id;
  s.max_iterations = cfg.get<int>("mpc.number_of_iterations", 120);
  const std::string init = lowerStr(cfg.get<std::string>("mpc.init_mode", "fixed"));
  if (init != "fixed" && init != "feasible")
    throw std::runtime_error("mpc.init_mode must be 'fixed' or 'feasible'");
  s.feasible_init = (init == "feasible");
  s.init_value = cfg.get<double>("mpc.init_value", 10.0);
  s.termination_criterion = cfg.get<int>("cg2o.termination_criterion", 1);
  return s;
}

std::unique_ptr<Controller> makeCg2oController(const core::Config &cfg,
                                               std::shared_ptr<mpc::MPCParameters> param,
                                               const Cg2oSettings &s) {
  if (s.algorithm == "ispd")
    return std::make_unique<Cg2oController<cg2o::SparseOptimizerISPD>>(cfg, std::move(param), s);
  if (s.algorithm == "bipm")
    return std::make_unique<Cg2oController<cg2o::SparseOptimizerBIPM>>(cfg, std::move(param), s);
  if (s.algorithm == "al")
    return std::make_unique<Cg2oController<cg2o::SparseOptimizerAL>>(cfg, std::move(param), s);
  throw std::runtime_error("inequality_algorithm must be ispd, bipm or al (got '" + s.algorithm + "')");
}

} // namespace macc::backends
