// macc_run - run one closed-loop MACC experiment and store everything about it
// in a time-stamped folder:  <out>/<YYYYmmdd_HHMMSS>_<label>/
//
//   experiment_info.txt   full report: reproduction command, machine, build,
//                         solver settings, model parameters, results, paper comparison
//   config_resolved.yaml  complete configuration actually used
//   steps.csv             per-MPC-step signals and solver statistics
//   summary.json          machine-readable statistics
//   console.log           everything printed to the console

#include "macc/backends/factory.hpp"
#include "macc/core/config.hpp"
#include "macc/core/run_info.hpp"
#include "macc/experiment/experiment.hpp"
#include "macc/solvers/linear_solvers.hpp"

#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <unistd.h>
#include <fstream>
#include <iostream>

#ifndef MACC_SOURCE_DIR
#define MACC_SOURCE_DIR ""
#endif

namespace fs = std::filesystem;

namespace {

void usage() {
  std::cout <<
R"(Usage: macc_run [options]

Experiment
  --config FILE          YAML configuration (default: <MACC>/config/config.yaml)
  --solvers LIST         comma separated: ispd, bipm, al, ipopt     (default: ispd)
                         several solvers solve the SAME problem at each step
  --driver NAME          solver whose input drives the plant (default: first)
  --horizon N            prediction horizon
  --init fixed|feasible  initial guess (feasible projection is required by BIPM)
  --max-iter N           maximum solver iterations (paper: 120)
  --loop-size N          number of MPC steps (default: whole driving cycle, 3863)
  --run-times N          solve every step N times and average (outliers removed)
  --linear-solver X      id or key of the cg2o linear solver (see --list-solvers)
  --no-equality          drop the dynamics constraints (SPD linear-solver study)
Output
  --out DIR              results root (default: <MACC>/results/runs)
  --label TEXT           appended to the time-stamped folder name
  --verbose / --quiet    print every step / only the final summary
Other
  --set key=value        override any config entry, e.g. --set ispd_settings.tau=1.6
  --paper-reference FILE reference numbers of the paper (default: config/paper_reference.yaml)
  --list-solvers         print the available linear solvers and exit
  --help
)";
}

// One thread for OpenMP and MKL unless the caller chose otherwise. With PARDISO, MKL (and its OpenMP runtimes) is
// loaded, and the default thread pools spin and compete with the solve: every solver became about 30x slower
// (UMFPACK at N = 30: 181 ms instead of 6 ms per step). The runtimes read these variables when the program is loaded,
// before main(), so the process restarts itself once with them set. MACC_THREADS_FIXED marks the second start.
void singleThreadedRuntimes(char **argv) {
  if (std::getenv("MACC_THREADS_FIXED")) return;
  bool changed = false;
  for (const char *var : {"OMP_NUM_THREADS", "MKL_NUM_THREADS"})
    if (!std::getenv(var)) {
      setenv(var, "1", 0);
      changed = true;
    }
  setenv("MACC_THREADS_FIXED", "1", 1);
  if (changed) execv("/proc/self/exe", argv);   // returns only on failure: then continue as is
}

} // namespace

int main(int argc, char **argv) {
  using namespace macc;
  singleThreadedRuntimes(argv);
  std::string config_path = std::string(MACC_SOURCE_DIR) + "/config/config.yaml";
  std::string reference_path = std::string(MACC_SOURCE_DIR) + "/config/paper_reference.yaml";
  std::vector<std::string> overrides;
  bool quiet = false;

  auto need = [&](int &i, const char *opt) -> std::string {
    if (i + 1 >= argc) {
      std::cerr << "Missing value for " << opt << std::endl;
      std::exit(2);
    }
    return argv[++i];
  };

  for (int i = 1; i < argc; ++i) {
    const std::string a = argv[i];
    if (a == "--help" || a == "-h") { usage(); return 0; }
    else if (a == "--list-solvers") { std::cout << solvers::describeCatalog(); return 0; }
    else if (a == "--config") config_path = need(i, "--config");
    else if (a == "--paper-reference") reference_path = need(i, "--paper-reference");
    else if (a == "--solvers") overrides.push_back("experiment.solvers=" + need(i, "--solvers"));
    else if (a == "--algorithm") overrides.push_back("experiment.solvers=" + need(i, "--algorithm"));
    else if (a == "--driver") overrides.push_back("experiment.driver=" + need(i, "--driver"));
    else if (a == "--horizon") overrides.push_back("mpc.horizon=" + need(i, "--horizon"));
    else if (a == "--init") overrides.push_back("mpc.init_mode=" + need(i, "--init"));
    else if (a == "--max-iter") overrides.push_back("mpc.number_of_iterations=" + need(i, "--max-iter"));
    else if (a == "--loop-size") overrides.push_back("mpc.loop_size=" + need(i, "--loop-size"));
    else if (a == "--run-times") overrides.push_back("mpc.run_times=" + need(i, "--run-times"));
    else if (a == "--linear-solver") overrides.push_back("linear_solver.type=" + need(i, "--linear-solver"));
    else if (a == "--no-equality") overrides.push_back("acc_settings.use_equality_constraints=0");
    else if (a == "--label") overrides.push_back("experiment.label=\"" + need(i, "--label") + "\"");
    else if (a == "--out") overrides.push_back("experiment.output_dir=\"" + need(i, "--out") + "\"");
    else if (a == "--verbose") overrides.push_back("experiment.verbose=1");
    else if (a == "--quiet") quiet = true;
    else if (a == "--set") overrides.push_back(need(i, "--set"));
    else {
      std::cerr << "Unknown option '" << a << "'\n\n";
      usage();
      return 2;
    }
  }

  core::Config cfg;
  try {
    cfg = core::Config::fromFile(config_path);
    for (const auto &o : overrides) cfg.applyOverride(o);
  } catch (const std::exception &e) {
    std::cerr << "Configuration error: " << e.what() << std::endl;
    return 2;
  }

  // ---- run directory -----------------------------------------------------------
  const core::SystemInfo sys = core::collectSystemInfo(argc, argv);
  fs::path out_root = cfg.get<std::string>("experiment.output_dir", "results/runs");
  if (out_root.is_relative()) {
    const std::string base = MACC_SOURCE_DIR;
    out_root = (base.empty() ? fs::current_path() : fs::path(base)) / out_root;
  }
  std::string label = cfg.get<std::string>("experiment.label", "");
  if (label.empty()) {
    auto names = cfg.getList("experiment.solvers");
    if (names.empty()) names.push_back(cfg.get<std::string>("inequality_algorithm", "ispd"));
    for (const auto &n : names) label += (label.empty() ? "" : "-") + n;
    label += "_N" + std::to_string(cfg.get<int>("mpc.horizon", 0));
  }
  const fs::path dir = core::createRunDirectory(out_root, label);
  const std::string started = core::timestampHuman();

  std::unique_ptr<core::ConsoleTee> tee;
  if (!quiet) tee = std::make_unique<core::ConsoleTee>(dir / "console.log");
  std::cout << "MACC run directory: " << dir.string() << std::endl;

  experiment::Setup setup;
  try {
    setup = experiment::buildSetup(cfg);
  } catch (const std::exception &e) {
    std::ofstream os(dir / "experiment_info.txt");
    os << "MACC experiment " << dir.filename().string() << "\nstatus : FAILED DURING SETUP\n"
       << "started : " << started << "\ncommand : " << sys.command_line << "\nerror   : " << e.what()
       << "\n\n--- configuration ---\n" << cfg.dump() << "\n";
    std::cerr << "Setup error: " << e.what() << "\n(details saved in " << (dir / "experiment_info.txt").string() << ")" << std::endl;
    return 1;
  }
  setup.verbose = cfg.get<int>("experiment.verbose", 0) != 0;

  std::ostream &log = quiet ? std::cerr : std::cout;
  experiment::Result result = experiment::run(setup, log);

  experiment::writeRunFiles(dir, setup, result, sys, started, core::timestampHuman(), reference_path);

  std::cout << "\n=== Summary (" << result.steps_done << " steps, N = " << setup.param->get_N() << ") ===\n";
  for (const auto &s : result.summaries) {
    std::cout << "  " << s.name << ": iterations avg " << s.iterations.mean << " (min "
              << s.iterations.min << ", max " << s.iterations.max << "), time avg "
              << s.time_ms.mean << " ms (min " << s.time_ms.min << ", max " << s.time_ms.max
              << "), time/iter " << s.time_per_iter_total_ms << " ms, steps at max-iter "
              << s.steps_hit_max_iter << "\n";
  }
  std::cout << "Report: " << (dir / "experiment_info.txt").string() << std::endl;
  return result.completed ? 0 : 1;
}
