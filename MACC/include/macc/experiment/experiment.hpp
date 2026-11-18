#ifndef MACC_EXPERIMENT_EXPERIMENT_HPP
#define MACC_EXPERIMENT_EXPERIMENT_HPP

// One closed-loop MACC experiment: builds the plant and the solver(s) from a
// config, runs the driving cycle, and produces tables + a complete report.

#include "macc/backends/controller.hpp"
#include "macc/core/config.hpp"
#include "macc/core/run_info.hpp"
#include "macc/core/stats.hpp"
#include "macc/core/table.hpp"
#include "macc/mpc/closed_loop.hpp"
#include "macc/mpc/parameters.h"

#include <filesystem>
#include <memory>
#include <string>
#include <vector>

namespace macc::experiment {

struct Setup {
  core::Config cfg;
  std::shared_ptr<mpc::MPCParameters> param;
  std::vector<std::unique_ptr<backends::Controller>> controllers;
  std::size_t driver = 0;      // index of the controller whose input drives the plant
  int steps = 0;               // number of MPC steps to simulate
  int run_times = 1;           // repeated solves per step for timing
  int progress_every = 100;
  bool verbose = false;
};

// Per-controller statistics over the whole run.
struct ControllerSummary {
  std::string name, description, paper_key;
  core::Summary iterations, time_ms, time_per_iter_ms, cost;
  double time_per_iter_total_ms = 0.0; // sum(time) / sum(iterations)
  double total_time_s = 0.0;
  int steps_hit_max_iter = 0;
  int steps_failed = 0;
  double max_eq_residual = 0.0;
  double max_ineq_violation = 0.0;
  double cost_sum = 0.0;
  std::vector<std::pair<std::string, std::string>> settings;
};

struct Result {
  core::Table table;
  std::vector<ControllerSummary> summaries;
  int steps_done = 0;
  int steps_space_domain = 0;
  bool completed = false;
  std::string error;
  double wall_seconds = 0.0;
};

// Reads the config (after overrides), creates parameters and controllers.
Setup buildSetup(const core::Config &cfg);

// Runs the closed loop. Never throws for solver problems: errors end the run
// early and are stored in Result::error so partial results are still saved.
Result run(Setup &setup, std::ostream &log);

// Writes experiment_info.txt, summary.json, steps.csv, config_resolved.yaml (+ ipopt.opt).
void writeRunFiles(const std::filesystem::path &dir, const Setup &setup, const Result &result,
                   const core::SystemInfo &sys, const std::string &started,
                   const std::string &finished, const std::string &paper_reference_file);

} // namespace macc::experiment

#endif // MACC_EXPERIMENT_EXPERIMENT_HPP
