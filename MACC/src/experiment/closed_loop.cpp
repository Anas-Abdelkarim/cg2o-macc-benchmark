#include "macc/core/stats.hpp"
#include "macc/core/timer.hpp"
#include "macc/experiment/experiment.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>

namespace macc::experiment {

namespace {
constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
}

Result run(Setup &s, std::ostream &log) {
  Result res;
  core::Stopwatch wall;
  mpc::ClosedLoopPlant plant(s.param);
  const std::size_t C = s.controllers.size();
  core::Table &t = res.table;

  // ---- column layout ----------------------------------------------------------
  const std::size_t c_k = t.column("k");
  const std::size_t c_time = t.column("time_s");
  const std::size_t c_vh = t.column("v_h");
  const std::size_t c_dh = t.column("d_h");
  const std::size_t c_vp = t.column("v_p");
  const std::size_t c_ap = t.column("a_p");
  const std::size_t c_space = t.column("space_domain");
  const std::size_t c_ds = t.column("delta_s");
  const std::size_t c_u = t.column("u_applied");
  struct Cols { std::size_t u, it, tm, tmin, tmax, tpi, cost, scost, eq, ineq, hit, ok; };
  std::vector<Cols> cols(C);
  for (std::size_t c = 0; c < C; ++c) {
    const std::string n = s.controllers[c]->name() + "_";
    cols[c] = {t.column(n + "u"),        t.column(n + "iterations"),
               t.column(n + "time_ms"),  t.column(n + "time_min_ms"),
               t.column(n + "time_max_ms"), t.column(n + "ms_per_iter"),
               t.column(n + "cost"),     t.column(n + "solver_cost"), t.column(n + "eq_residual"),
               t.column(n + "ineq_violation"), t.column(n + "hit_max_iter"),
               t.column(n + "success")};
  }

  std::vector<ControllerSummary> sum(C);
  std::vector<std::vector<double>> it_v(C), tm_v(C), tpi_v(C), cost_v(C);
  std::vector<double> time_total(C, 0.0), iter_total(C, 0.0);
  for (std::size_t c = 0; c < C; ++c) {
    sum[c].name = s.controllers[c]->name();
    sum[c].description = s.controllers[c]->description();
    sum[c].paper_key = s.controllers[c]->paperKey();
    sum[c].settings = s.controllers[c]->settings();
  }

  log << "Closed loop: " << s.steps << " MPC steps, horizon N=" << s.param->get_N()
      << ", solvers:";
  for (auto &c : s.controllers) log << " " << c->name();
  log << ", " << s.run_times << " timing repetition(s) per step, driver = "
      << s.controllers[s.driver]->name() << std::endl;

  double u_prev = 0.0;
  try {
    for (int k = 0; k < s.steps; ++k) {
      plant.beginStep(k, u_prev);

      t.append(c_k, k);
      t.append(c_time, k * s.param->get_Ts());
      t.append(c_vh, s.param->get_v_h_0());
      t.append(c_dh, s.param->get_d_h_0());
      t.append(c_vp, s.param->get_vp_prediction(0));
      t.append(c_ap, plant.measuredPrecedingAcceleration());
      t.append(c_space, s.param->useSpaceDomain() ? 1.0 : 0.0);
      t.append(c_ds, s.param->get_delta_s());
      if (s.param->useSpaceDomain()) ++res.steps_space_domain;

      double u_driver = 0.0;
      for (std::size_t c = 0; c < C; ++c) {
        std::vector<double> reps;
        reps.reserve(static_cast<std::size_t>(s.run_times));
        backends::SolveResult r;
        for (int rep = 0; rep < s.run_times; ++rep) {
          r = s.controllers[c]->solve();
          reps.push_back(r.time_ms);
        }
        const double tmean = core::meanWithoutOutliers(reps);
        const double tmin = *std::min_element(reps.begin(), reps.end());
        const double tmax = *std::max_element(reps.begin(), reps.end());
        const double tpi = r.iterations > 0 ? tmean / r.iterations : kNaN;

        t.append(cols[c].u, r.u);
        t.append(cols[c].it, r.iterations);
        t.append(cols[c].tm, tmean);
        t.append(cols[c].tmin, tmin);
        t.append(cols[c].tmax, tmax);
        t.append(cols[c].tpi, tpi);
        t.append(cols[c].cost, r.cost);
        t.append(cols[c].scost, r.solver_cost);
        t.append(cols[c].eq, r.eq_residual);
        t.append(cols[c].ineq, r.ineq_violation);
        t.append(cols[c].hit, r.hit_max_iter ? 1.0 : 0.0);
        t.append(cols[c].ok, r.success ? 1.0 : 0.0);

        it_v[c].push_back(r.iterations);
        tm_v[c].push_back(tmean);
        tpi_v[c].push_back(tpi);
        cost_v[c].push_back(r.cost);
        time_total[c] += tmean;
        iter_total[c] += r.iterations;
        if (r.hit_max_iter) ++sum[c].steps_hit_max_iter;
        if (!r.success) ++sum[c].steps_failed;
        if (std::isfinite(r.eq_residual)) sum[c].max_eq_residual = std::max(sum[c].max_eq_residual, r.eq_residual);
        if (std::isfinite(r.ineq_violation)) sum[c].max_ineq_violation = std::max(sum[c].max_ineq_violation, r.ineq_violation);
        if (c == s.driver) u_driver = r.u;

        if (s.verbose)
          log << "  k=" << k << " " << s.controllers[c]->name() << ": u=" << r.u
              << " it=" << r.iterations << " t=" << tmean << " ms cost=" << r.cost
              << " [" << r.status << "]" << std::endl;
      }
      t.append(c_u, u_driver);
      u_prev = u_driver;
      ++res.steps_done;

      if ((k + 1) % s.progress_every == 0 || k + 1 == s.steps) {
        log << "  step " << std::setw(5) << (k + 1) << "/" << s.steps
            << "  v_h=" << std::fixed << std::setprecision(2) << s.param->get_v_h_0()
            << " m/s  d_h=" << s.param->get_d_h_0() << " m ";
        for (std::size_t c = 0; c < C; ++c)
          log << " | " << s.controllers[c]->name() << ": it=" << static_cast<int>(it_v[c].back())
              << " t=" << std::setprecision(2) << tm_v[c].back() << " ms";
        log << std::defaultfloat << std::endl;
      }
    }
    res.completed = true;
  } catch (const std::exception &e) {
    res.error = e.what();
    log << "ERROR in closed loop at step " << res.steps_done << ": " << e.what() << std::endl;
  }

  for (std::size_t c = 0; c < C; ++c) {
    sum[c].iterations = core::summarize(it_v[c]);
    sum[c].time_ms = core::summarize(tm_v[c]);
    sum[c].time_per_iter_ms = core::summarize(tpi_v[c]);
    sum[c].cost = core::summarize(cost_v[c]);
    sum[c].cost_sum = 0.0;
    for (double v : cost_v[c])
      if (std::isfinite(v)) sum[c].cost_sum += v;
    sum[c].time_per_iter_total_ms = iter_total[c] > 0 ? time_total[c] / iter_total[c] : kNaN;
    sum[c].total_time_s = time_total[c] / 1000.0;
  }
  res.summaries = std::move(sum);
  res.wall_seconds = wall.elapsedMs() / 1000.0;
  return res;
}

} // namespace macc::experiment
