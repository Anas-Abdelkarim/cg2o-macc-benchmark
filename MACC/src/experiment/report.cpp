#include "macc/backends/factory.hpp"
#include "macc/experiment/experiment.hpp"
#include "macc/solvers/linear_solvers.hpp"

#include <yaml-cpp/yaml.h>

#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace fs = std::filesystem;

namespace macc::experiment {

namespace {

using KV = std::vector<std::pair<std::string, std::string>>;

std::string num(double v, int prec = 6) {
  if (std::isnan(v)) return "nan";
  if (std::isinf(v)) return v > 0 ? "inf" : "-inf";
  std::ostringstream os;
  os << std::setprecision(prec) << v;
  return os.str();
}

std::string jnum(double v) {
  if (!std::isfinite(v)) return "null";
  std::ostringstream os;
  os << std::setprecision(10) << v;
  return os.str();
}

std::string jstr(const std::string &s) {
  std::string o = "\"";
  for (char c : s) {
    switch (c) {
    case '"': o += "\\\""; break;
    case '\\': o += "\\\\"; break;
    case '\n': o += "\\n"; break;
    case '\t': o += "\\t"; break;
    default: o += c;
    }
  }
  return o + "\"";
}

std::string jsummary(const core::Summary &s) {
  std::ostringstream os;
  os << "{\"mean\":" << jnum(s.mean) << ",\"min\":" << jnum(s.min) << ",\"max\":" << jnum(s.max)
     << ",\"std\":" << jnum(s.stddev) << ",\"median\":" << jnum(s.median)
     << ",\"p95\":" << jnum(s.p95) << ",\"n\":" << s.n << "}";
  return os.str();
}

KV modelParameters(const mpc::MPCParameters &p) {
  KV v;
  auto add = [&](const char *k, double x) { v.emplace_back(k, num(x, 12)); };
  v.emplace_back("horizon N", std::to_string(p.get_N()));
  add("Ts (sample time) [s]", p.get_Ts());
  add("delta_t (time-domain step) [s]", p.get_delta_t());
  add("delta_s (initial space step) [m]", p.get_delta_s());
  add("domain_switch_threshold [m/s]", p.get_domain_switch_threshold());
  v.emplace_back("space domain allowed", p.isSpaceDomain() ? "yes" : "no");
  v.emplace_back("linear dynamics", p.isLinearDynamics() ? "yes" : "no");
  v.emplace_back("linear inequalities (v_h bounds)", p.isLinearInequalities() ? "yes" : "no");
  v.emplace_back("equality constraints present", p.useEqualityConstraints() ? "yes" : "no");
  add("m_v [kg]", p.get_m_v());
  add("m_p [kg]", p.get_m_p());
  add("m_total [kg]", p.get_m_total());
  add("m_eq [kg]", p.get_m_eq());
  add("e_i", p.get_e_i());
  add("c_a", p.get_c_a());
  add("c_r", p.get_c_r());
  add("g [m/s^2]", p.get_g());
  add("x1 (plant c_r mismatch)", p.get_x1());
  add("x2 (plant c_a mismatch)", p.get_x2());
  add("p1", p.get_p1());
  add("p2", p.get_p2());
  add("Omega1 (energy weight)", p.get_Omega1());
  add("Omega6 (distance slack weight)", p.get_Omega6());
  add("BrakePenalty", p.get_BrakePenalty());
  add("BrakeChangePenalty", p.get_BrakeChangePenalty());
  add("TractionChangePenalty", p.get_TractionChangePenalty());
  add("h_min [s]", p.get_h_min());
  add("h_soft [s]", p.get_h_soft());
  add("d_min [m]", p.get_d_min());
  add("v_min [m/s]", p.get_v_min());
  add("v_max [m/s]", p.get_v_max());
  add("a2", p.get_a2());
  add("b2", p.get_b2());
  add("b3", p.get_b3());
  add("b4", p.get_b4());
  add("b_max", p.get_b_max());
  add("Regen_max", p.get_Regen_max());
  add("Brems_a1", p.get_Brems_a1());
  add("Brems_b1", p.get_Brems_b1());
  add("delta_f_t_max", p.get_delta_f_t_max());
  add("delta_f_b_max", p.get_delta_f_b_max());
  add("interior_shift", p.get_interior_shift());
  std::ostringstream eff;
  eff << std::setprecision(10);
  for (double e : p.get_eff_map()) eff << e << " ";
  v.emplace_back("eff_map p00 p01 p02 p10 p11 p20", eff.str());
  v.emplace_back("driving cycle samples", std::to_string(p.get_driving_cycle().size()));
  return v;
}

struct RefValues {
  bool found = false;
  double iter_avg = NAN, iter_min = NAN, iter_max = NAN;
  double time_avg = NAN, time_min = NAN, time_max = NAN;
  std::string source;
};

RefValues loadReference(const std::string &file, const std::string &key, int horizon) {
  RefValues r;
  if (file.empty() || key.empty() || !fs::exists(file)) return r;
  try {
    YAML::Node root = YAML::LoadFile(file);
    YAML::Node refs = root["references"];
    if (!refs || !refs[key]) return r;
    YAML::Node e = refs[key];
    YAML::Node h = e[std::to_string(horizon)];
    if (!h) return r;
    auto get = [&](const char *k) { return h[k] ? h[k].as<double>() : NAN; };
    r.found = true;
    r.iter_avg = get("iter_avg");
    r.iter_min = get("iter_min");
    r.iter_max = get("iter_max");
    r.time_avg = get("time_avg_ms");
    r.time_min = get("time_min_ms");
    r.time_max = get("time_max_ms");
    r.source = e["source"] ? e["source"].as<std::string>() : "";
  } catch (const std::exception &) {
  }
  return r;
}

void paperRow(core::ReportWriter &w, const std::string &metric, double mine, double ref) {
  std::ostringstream os;
  os << "  " << std::left << std::setw(26) << metric << std::right << std::setw(14) << num(mine, 5)
     << std::setw(14) << (std::isnan(ref) ? "-" : num(ref, 5));
  if (!std::isnan(ref) && ref != 0.0 && std::isfinite(mine)) os << std::setw(12) << num(mine / ref, 3);
  w.line(os.str());
}

} // namespace

void writeRunFiles(const fs::path &dir, const Setup &setup, const Result &r,
                   const core::SystemInfo &sys, const std::string &started,
                   const std::string &finished, const std::string &paper_reference_file) {
  const auto &cfg = setup.cfg;
  const auto &p = *setup.param;
  const int N = p.get_N();
  const std::string run_id = dir.filename().string();
  const std::string status = r.completed ? "COMPLETED" : "INCOMPLETE: " + r.error;

  // ---- raw data --------------------------------------------------------------
  r.table.writeCsv((dir / "steps.csv").string());
  {
    std::ofstream os(dir / "config_resolved.yaml");
    os << "# Resolved configuration of run " << run_id << "\n"
       << "# Re-run with:  macc_run --config " << (dir / "config_resolved.yaml").string() << "\n"
       << cfg.dump() << "\n";
  }
  for (const auto &s : r.summaries) {
    if (s.name != "ipopt") continue;
    std::ofstream os(dir / "ipopt.opt");
    os << "# IPOPT options used in this run (IPOPT option-file syntax)\n";
    for (const auto &kv : s.settings)
      if (kv.first.rfind("ipopt.", 0) == 0 && kv.first != "ipopt_version")
        os << kv.first.substr(6) << " " << kv.second << "\n";
  }

  // ---- summary.json ----------------------------------------------------------
  {
    std::ofstream js(dir / "summary.json");
    std::string init_mode = cfg.get<std::string>("mpc.init_mode", "fixed");
    js << "{\n";
    js << "  \"run_id\": " << jstr(run_id) << ",\n";
    js << "  \"label\": " << jstr(cfg.get<std::string>("experiment.label", "")) << ",\n";
    js << "  \"started\": " << jstr(started) << ",\n  \"finished\": " << jstr(finished) << ",\n";
    js << "  \"status\": " << jstr(status) << ",\n";
    js << "  \"completed\": " << (r.completed ? "true" : "false") << ",\n";
    js << "  \"horizon\": " << N << ",\n";
    js << "  \"steps\": " << r.steps_done << ",\n";
    js << "  \"steps_space_domain\": " << r.steps_space_domain << ",\n";
    js << "  \"run_times\": " << setup.run_times << ",\n";
    js << "  \"driver\": " << jstr(setup.controllers[setup.driver]->name()) << ",\n";
    js << "  \"init_mode\": " << jstr(init_mode) << ",\n";
    js << "  \"max_iterations\": " << cfg.get<int>("mpc.number_of_iterations", 120) << ",\n";
    js << "  \"linear_solver\": " << jstr(cfg.get<std::string>("linear_solver.type", "14")) << ",\n";
    js << "  \"equality_constraints\": " << (p.useEqualityConstraints() ? "true" : "false") << ",\n";
    js << "  \"wall_seconds\": " << jnum(r.wall_seconds) << ",\n";
    js << "  \"solvers\": {\n";
    for (std::size_t i = 0; i < r.summaries.size(); ++i) {
      const auto &s = r.summaries[i];
      js << "    " << jstr(s.name) << ": {\n";
      js << "      \"description\": " << jstr(s.description) << ",\n";
      js << "      \"paper_key\": " << jstr(s.paper_key) << ",\n";
      js << "      \"iterations\": " << jsummary(s.iterations) << ",\n";
      js << "      \"time_ms\": " << jsummary(s.time_ms) << ",\n";
      js << "      \"time_per_iter_ms\": " << jsummary(s.time_per_iter_ms) << ",\n";
      js << "      \"time_per_iter_total_ms\": " << jnum(s.time_per_iter_total_ms) << ",\n";
      js << "      \"cost\": " << jsummary(s.cost) << ",\n";
      js << "      \"cost_sum\": " << jnum(s.cost_sum) << ",\n";
      js << "      \"total_solver_time_s\": " << jnum(s.total_time_s) << ",\n";
      js << "      \"steps_hit_max_iter\": " << s.steps_hit_max_iter << ",\n";
      js << "      \"steps_failed\": " << s.steps_failed << ",\n";
      js << "      \"max_eq_residual\": " << jnum(s.max_eq_residual) << ",\n";
      js << "      \"max_ineq_violation\": " << jnum(s.max_ineq_violation) << "\n";
      js << "    }" << (i + 1 < r.summaries.size() ? "," : "") << "\n";
    }
    js << "  }\n}\n";
  }

  // ---- experiment_info.txt ---------------------------------------------------
  std::ofstream os(dir / "experiment_info.txt");
  core::ReportWriter w(os);
  w.title("MACC experiment  " + run_id);
  w.kv("status", status);
  w.kv("label", cfg.get<std::string>("experiment.label", "(none)"));
  w.kv("started", started);
  w.kv("finished", finished);
  w.kv("wall-clock duration [s]", r.wall_seconds, 5);
  w.kv("run directory", dir.string());

  w.section("1. How to reproduce");
  w.kv("command line", sys.command_line);
  w.kv("working directory", sys.working_dir);
  w.kv("exact configuration", (dir / "config_resolved.yaml").string());
  w.line("Re-run:  macc_run --config " + (dir / "config_resolved.yaml").string() +
         "   (add --out/--label as needed)");

  w.section("2. System and build");
  w.kv("host", sys.hostname);
  w.kv("user", sys.user);
  w.kv("operating system", sys.os);
  w.kv("kernel", sys.kernel);
  w.kv("CPU", sys.cpu_model);
  w.kv("logical cores", static_cast<long long>(sys.logical_cores));
  w.kv("memory [GB]", sys.mem_total_gb, 3);
  w.kv("compiler", sys.compiler);
  w.kv("build type", sys.build_type);
  w.kv("C++ standard (__cplusplus)", sys.cxx_standard);
  w.kv("MACC source", sys.source_dir);
  w.kv("git commit", sys.git_commit + (sys.git_state.empty() ? "" : " (" + sys.git_state + ")"));
  w.kv("g2o install", sys.g2o_prefix);
  w.kv("cg2o install", sys.cg2o_prefix);
  w.kv("IPOPT", sys.ipopt_version);
  w.line("Timing note: this machine is not the one used for the paper (Table III: Intel Core i9 12th Gen).");

  w.section("3. Experiment setup");
  w.kv("solvers in this run", [&] {
    std::string t;
    for (auto &c : setup.controllers) t += (t.empty() ? "" : ", ") + c->name();
    return t;
  }());
  w.kv("solver driving the plant", setup.controllers[setup.driver]->name());
  w.kv("prediction horizon N", static_cast<long long>(N));
  w.kv("MPC steps simulated", static_cast<long long>(r.steps_done));
  w.kv("MPC steps requested", static_cast<long long>(setup.steps));
  w.kv("steps in space domain", static_cast<long long>(r.steps_space_domain));
  w.kv("steps in time domain", static_cast<long long>(r.steps_done - r.steps_space_domain));
  w.kv("timing repetitions per step", static_cast<long long>(setup.run_times));
  w.kv("initial guess", cfg.get<std::string>("mpc.init_mode", "fixed") == "feasible"
                            ? "feasible projection (needed by BIPM)"
                            : "constant " + num(cfg.get<double>("mpc.init_value", 10.0)));
  w.kv("max solver iterations", static_cast<long long>(cfg.get<int>("mpc.number_of_iterations", 120)));
  w.kv("equality constraints", p.useEqualityConstraints() ? "yes" : "NO (linear-solver study, SPD system)");
  w.kv("driving cycle", "RDE cycle, 'data_v_h_106_p1', " + std::to_string(p.get_driving_cycle().size()) + " samples, Ts = " + num(p.get_Ts()) + " s");
  w.line("Both solvers (if several are listed) solve exactly the same MPC problem at every");
  w.line("step; the input of the 'driver' solver is applied to the plant.");

  for (const auto &s : r.summaries) {
    w.section("4. Solver settings: " + s.name + "  [" + s.description + "]");
    for (const auto &kv : s.settings) w.kv(kv.first, kv.second);
  }

  w.section("5. Vehicle / MPC model parameters");
  for (const auto &kv : modelParameters(p)) w.kv(kv.first, kv.second);

  w.section("6. Results (" + std::to_string(r.steps_done) + " MPC steps)");
  for (const auto &s : r.summaries) {
    w.line("[" + s.name + "]  " + s.description);
    w.kv("  iterations  avg (min, max)", num(s.iterations.mean, 5) + "  (" + num(s.iterations.min, 5) + ", " + num(s.iterations.max, 5) + ")");
    w.kv("  iterations  median / p95 / std", num(s.iterations.median, 5) + " / " + num(s.iterations.p95, 5) + " / " + num(s.iterations.stddev, 5));
    w.kv("  time [ms]   avg (min, max)", num(s.time_ms.mean, 5) + "  (" + num(s.time_ms.min, 5) + ", " + num(s.time_ms.max, 5) + ")");
    w.kv("  time [ms]   median / p95 / std", num(s.time_ms.median, 5) + " / " + num(s.time_ms.p95, 5) + " / " + num(s.time_ms.stddev, 5));
    w.kv("  time / iteration [ms]  mean of steps", num(s.time_per_iter_ms.mean, 5) + "  (min " + num(s.time_per_iter_ms.min, 5) + ", max " + num(s.time_per_iter_ms.max, 5) + ")");
    w.kv("  time / iteration [ms]  sum(t)/sum(it)", num(s.time_per_iter_total_ms, 5));
    w.kv("  total solver time [s]", num(s.total_time_s, 5));
    w.kv("  cost f(x*)  mean / total", num(s.cost.mean, 8) + " / " + num(s.cost_sum, 10));
    w.kv("  steps at iteration limit", static_cast<long long>(s.steps_hit_max_iter));
    w.kv("  steps failed (no valid input)", static_cast<long long>(s.steps_failed));
    w.kv("  max |equality residual|", num(s.max_eq_residual, 4));
    w.kv("  max inequality violation", num(s.max_ineq_violation, 4));
    w.line();
  }
  w.line("Cost and constraint residuals of every solver are evaluated with the SAME function");
  w.line("(macc::nlp::MaccNLP) on each solver's final iterate, so they are directly comparable.");

  // ---- comparison with the paper ---------------------------------------------
  bool any_ref = false;
  for (const auto &s : r.summaries) {
    const RefValues ref = loadReference(paper_reference_file, s.paper_key, N);
    if (!ref.found) continue;
    if (!any_ref) {
      w.section("7. Comparison with the paper (cg2o, IEEE T-RO)");
      any_ref = true;
    }
    w.line("[" + s.name + "]   reference: " + ref.source);
    w.line("  " + std::string("metric") + std::string(20, ' ') + std::string("this run") + std::string(7, ' ') + "paper" + std::string(8, ' ') + "ratio");
    paperRow(w, "iterations avg", s.iterations.mean, ref.iter_avg);
    paperRow(w, "iterations min", s.iterations.min, ref.iter_min);
    paperRow(w, "iterations max", s.iterations.max, ref.iter_max);
    paperRow(w, "time avg [ms]", s.time_ms.mean, ref.time_avg);
    paperRow(w, "time min [ms]", s.time_ms.min, ref.time_min);
    paperRow(w, "time max [ms]", s.time_ms.max, ref.time_max);
    w.line();
  }
  if (any_ref) {
    w.line("Iteration counts are comparable across machines; absolute times are not.");
    w.line("IPOPT iterations match the paper only with the same linear solver (Table V: HSL MA57,");
    w.line("ipopt_settings.use_hsl: true); with MUMPS they differ slightly.");
  }

  w.section("8. Resolved configuration (YAML)");
  w.kv("config file", cfg.sourcePath());
  if (cfg.overrides().empty()) {
    w.kv("command-line overrides", "(none)");
  } else {
    for (const auto &o : cfg.overrides()) w.kv("override", o);
  }
  w.line();
  w.line(cfg.dump());

  w.section("9. Files in this run directory");
  w.line("experiment_info.txt  this report");
  w.line("config_resolved.yaml  complete configuration (re-usable with --config)");
  w.line("steps.csv  per-MPC-step data: plant state, and for each solver u, iterations, time,");
  w.line("            time per iteration, cost, constraint residuals");
  w.line("summary.json  machine-readable statistics (used by the plot scripts)");
  w.line("console.log  console output of the run");
  if (fs::exists(dir / "ipopt.opt")) w.line("ipopt.opt  IPOPT option file that was used");
}

} // namespace macc::experiment
