#include "macc/backends/factory.hpp"
#include "macc/experiment/experiment.hpp"
#include "macc/mpc/driving_cycles.h"

#include <algorithm>
#include <functional>
#include <map>
#include <stdexcept>

namespace macc::experiment {

namespace {

using Setter = std::function<void(mpc::MPCParameters &, double)>;

// Optional overrides of the vehicle / MPC model: "--set model.Omega1=0.02".
const std::map<std::string, Setter> &modelSetters() {
  static const std::map<std::string, Setter> m = {
      {"c_a", [](auto &p, double v) { p.set_c_a(v); }},
      {"c_r", [](auto &p, double v) { p.set_c_r(v); }},
      {"e_i", [](auto &p, double v) { p.set_e_i(v); }},
      {"m_eq", [](auto &p, double v) { p.set_m_eq(v); }},
      {"m_p", [](auto &p, double v) { p.set_m_p(v); }},
      {"m_total", [](auto &p, double v) { p.set_m_total(v); }},
      {"m_v", [](auto &p, double v) { p.set_m_v(v); }},
      {"p1", [](auto &p, double v) { p.set_p1(v); }},
      {"p2", [](auto &p, double v) { p.set_p2(v); }},
      {"x1", [](auto &p, double v) { p.set_x1(v); }},
      {"x2", [](auto &p, double v) { p.set_x2(v); }},
      {"Omega1", [](auto &p, double v) { p.set_Omega1(v); }},
      {"Omega6", [](auto &p, double v) { p.set_Omega6(v); }},
      {"BrakeChangePenalty", [](auto &p, double v) { p.set_BrakeChangePenalty(v); }},
      {"BrakePenalty", [](auto &p, double v) { p.set_BrakePenalty(v); }},
      {"TractionChangePenalty", [](auto &p, double v) { p.set_TractionChangePenalty(v); }},
      {"Brems_a1", [](auto &p, double v) { p.set_Brems_a1(v); }},
      {"Brems_b1", [](auto &p, double v) { p.set_Brems_b1(v); }},
      {"Regen_max", [](auto &p, double v) { p.set_Regen_max(v); }},
      {"a2", [](auto &p, double v) { p.set_a2(v); }},
      {"b2", [](auto &p, double v) { p.set_b2(v); }},
      {"b3", [](auto &p, double v) { p.set_b3(v); }},
      {"b4", [](auto &p, double v) { p.set_b4(v); }},
      {"b_max", [](auto &p, double v) { p.set_b_max(v); }},
      {"d_min", [](auto &p, double v) { p.set_d_min(v); }},
      {"delta_t", [](auto &p, double v) { p.set_delta_t(v); }},
      {"h_min", [](auto &p, double v) { p.set_h_min(v); }},
      {"h_soft", [](auto &p, double v) { p.set_h_soft(v); }},
      {"delta_f_t_max", [](auto &p, double v) { p.set_delta_f_t_max(v); }},
      {"delta_f_b_max", [](auto &p, double v) { p.set_delta_f_b_max(v); }},
      {"v_min", [](auto &p, double v) { p.set_v_min(v); }},
      {"v_max", [](auto &p, double v) { p.set_v_max(v); }},
      {"alpha", [](auto &p, double v) { p.set_alpha(v); }},
      {"interior_shift", [](auto &p, double v) { p.set_interior_shift(v); }},
      {"domain_switch_threshold", [](auto &p, double v) { p.set_domain_switch_threshold(v); }},
  };
  return m;
}

void applyModelOverrides(const core::Config &cfg, mpc::MPCParameters &p) {
  for (const auto &kv : cfg.items("model")) {
    auto it = modelSetters().find(kv.first);
    if (it == modelSetters().end())
      throw std::runtime_error("Unknown model parameter 'model." + kv.first + "'");
    it->second(p, std::stod(kv.second));
  }
}

std::vector<std::string> solverList(const core::Config &cfg) {
  std::vector<std::string> names = cfg.getList("experiment.solvers");
  if (names.empty()) names.push_back(cfg.get<std::string>("inequality_algorithm", "ispd"));
  for (auto &n : names)
    std::transform(n.begin(), n.end(), n.begin(), [](unsigned char c) { return std::tolower(c); });
  return names;
}

} // namespace

Setup buildSetup(const core::Config &cfg) {
  Setup s;
  s.cfg = cfg;
  s.param = std::make_shared<mpc::MPCParameters>();
  auto &p = *s.param;

  const int N = cfg.get<int>("mpc.horizon");
  if (N < 1) throw std::runtime_error("mpc.horizon must be >= 1");
  p.set_N(N);

  p.set_space_domain(cfg.get<int>("acc_settings.spaceDomain", 1) != 0);
  p.set_linearDynamics(cfg.get<int>("acc_settings.linearDynamics", 0) != 0);
  p.set_linearInequalities(cfg.get<int>("acc_settings.linearInequalities", 0) != 0);
  p.set_scaleInequalities(cfg.get<int>("acc_settings.scaleInequalities", 0) != 0);
  p.set_use_equality_constraints(cfg.get<int>("acc_settings.use_equality_constraints", 1) != 0);
  applyModelOverrides(cfg, p);
  p.set_driving_cycle(mpc::data_v_h_106_p1, cfg.get<double>("model.Ts", 0.1));

  const double loop_size = cfg.get<double>("mpc.loop_size", 0.0);
  const int cycle = static_cast<int>(p.get_driving_cycle().size());
  s.steps = (loop_size <= 0.0 || loop_size > cycle) ? cycle : static_cast<int>(loop_size);
  s.run_times = std::max(1, cfg.get<int>("mpc.run_times", 1));
  s.progress_every = std::max(1, cfg.get<int>("experiment.progress_every", 100));

  const auto names = solverList(cfg);
  for (const auto &full : names) {
    // "<solver>_warm": same solver, but every solve starts from the previous
    // solution instead of the constant initial guess.
    std::string n = full;
    bool warm = false, ampl = false;
    // "<solver>_ampl": like the AMPL model of the cg2o repo, which resets every variable to 10 before a solve except d_h
    if (n.size() > 5 && n.compare(n.size() - 5, 5, "_ampl") == 0) {
      n.erase(n.size() - 5);
      ampl = true;
    }
    for (const char *suffix : {"_warm", "-warm"}) {
      const std::string sx = suffix;
      if (n.size() > sx.size() && n.compare(n.size() - sx.size(), sx.size(), sx) == 0) {
        n.erase(n.size() - sx.size());
        warm = true;
      }
    }
    if (n == "ipopt") {
      backends::IpoptSettings is = backends::readIpoptSettings(cfg);
      if (warm) is.init_mode = "previous";
      if (ampl) is.init_mode = "ampl";
      s.controllers.push_back(backends::makeIpoptController(s.param, is));
    } else if (n == "ispd" || n == "bipm" || n == "al") {
      backends::Cg2oSettings cs = backends::readCg2oSettings(cfg);
      cs.algorithm = n;
      cs.warm_start = warm;
      s.controllers.push_back(backends::makeCg2oController(cfg, s.param, cs));
    } else {
      throw std::runtime_error("Unknown solver '" + full +
                               "' in experiment.solvers (use ispd, bipm, al, ipopt, optionally with suffix _warm)");
    }
  }
  for (std::size_t i = 0; i < s.controllers.size(); ++i)
    for (std::size_t j = i + 1; j < s.controllers.size(); ++j)
      if (s.controllers[i]->name() == s.controllers[j]->name())
        throw std::runtime_error("The same solver '" + s.controllers[i]->name() + "' was listed twice");

  const std::string driver = cfg.get<std::string>("experiment.driver", "");
  s.driver = 0;
  if (!driver.empty()) {
    bool found = false;
    for (std::size_t i = 0; i < s.controllers.size(); ++i)
      if (s.controllers[i]->name() == driver) { s.driver = i; found = true; }
    if (!found) throw std::runtime_error("experiment.driver '" + driver + "' is not in experiment.solvers");
  }
  return s;
}

} // namespace macc::experiment
