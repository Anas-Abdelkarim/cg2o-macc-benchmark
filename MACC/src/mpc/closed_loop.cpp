#include "macc/mpc/closed_loop.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <numeric>

namespace macc::mpc {

namespace {
const std::vector<double> kAccelWeights = {0, 0, 0, 0, 0, 0, 0, 0, 0.25, 0.75};
}

ClosedLoopPlant::ClosedLoopPlant(std::shared_ptr<MPCParameters> param)
    : param_(std::move(param)), a_p_memory_(10, 0.0) {
  // Flat road, constant speed limits. The cg2o formulation also sets these, but the plant must work for
  // backends that have no factor graph (native IPOPT).
  const std::size_t need = static_cast<std::size_t>(param_->get_N()) + 1;
  if (param_->get_alpha_prediction().size() < need)
    param_->set_alpha_prediction(need, param_->get_alpha());
  if (param_->get_v_min_prediction().size() < need)
    param_->set_v_min_prediction(need, param_->get_v_min());
  if (param_->get_v_max_prediction().size() < need)
    param_->set_v_max_prediction(need, param_->get_v_max());
}

double ClosedLoopPlant::predictedPrecedingAcceleration() const {
  return std::inner_product(kAccelWeights.begin(), kAccelWeights.end(),
                            a_p_memory_.begin(), 0.0);
}

double ClosedLoopPlant::simulateVelocity(double u_car) {
  if (u_car < -7000) u_car = -7000; // physical limit of the car
  const double v_h_0 = param_->get_v_h_0();
  param_->set_v_h_prev(v_h_0);

  const double alpha = param_->get_alpha_prediction(0); // road slope (flat)
  const double Ts = param_->get_Ts();
  const double g = param_->get_g();
  const double m_total = param_->get_m_v() + param_->get_m_p();
  const double m_eq = m_total + param_->get_e_i() * param_->get_m_v();
  // plant/model mismatch of the experiment: rolling resistance and drag differ
  const double c_r = param_->get_x1() * param_->get_c_r();
  const double c_a = param_->get_x2() * param_->get_c_a();

  const double f_roll = (v_h_0 > 0.05) ? (c_r * m_total * g * std::cos(alpha)) : 0.0;
  double v_h_1 = (Ts / m_eq) * (u_car - m_total * g * std::sin(alpha) - f_roll -
                                c_a * v_h_0 * v_h_0) + v_h_0;
  v_h_1 = std::max(v_h_1, 0.0);
  param_->set_v_h_0(v_h_1);
  return v_h_1;
}

void ClosedLoopPlant::sense(double v_p) {
  const double Ts = param_->get_Ts();
  const double v_h = param_->get_v_h_0();
  const double v_h_prev = param_->get_v_h_prev();
  double d_h = param_->get_d_h_0();
  const double v_p_prev = param_->get_v_p_prev();

  d_h = d_h + Ts * (v_p_prev + v_p) / 2 - Ts * (v_h_prev + v_h) / 2;
  const double a_p = (v_p - v_p_prev) / Ts;
  a_p_memory_.push_back(a_p);
  a_p_memory_.pop_front();

  param_->set_d_h_0(d_h);
  param_->set_v_p_prev(v_p);
}

std::vector<double> ClosedLoopPlant::predict(double v_p) const {
  double predicted_accel = predictedPrecedingAcceleration();
  const double a_p = a_p_memory_.back();
  const std::size_t n = static_cast<std::size_t>(param_->get_N()) + 1;
  std::vector<double> F(n);
  std::iota(F.begin(), F.end(), 0.0);
  std::vector<double> pred(n, 0.0);
  if (predicted_accel >= 0) {
    predicted_accel = std::min(a_p, 0.5 * predicted_accel);
    for (std::size_t i = 0; i < n; ++i) {
      pred[i] = predicted_accel * F[i] + v_p;
      if (pred[i] < 0) pred[i] = 0;
      if (i >= 3) pred[i] = pred[2]; // hold the value after the 3rd entry
    }
  } else {
    predicted_accel = std::max({a_p, predicted_accel, -0.2});
    for (std::size_t i = 0; i < n; ++i) {
      pred[i] = predicted_accel * F[i] + v_p;
      if (pred[i] < 0) pred[i] = 0;
    }
  }
  return pred;
}

void ClosedLoopPlant::beginStep(int k, double u_input) {
  if (std::isnan(u_input)) {
    u_input = -222;
    std::cerr << "[Warning] u_input is NaN, using -222 N" << std::endl;
  }
  if (u_input >= 0) {
    param_->set_f_t_prev(u_input);
    param_->set_f_b_prev(0.0);
  } else {
    param_->set_f_t_prev(0.0);
    param_->set_f_b_prev(-u_input);
  }

  const double v_p = param_->get_driving_cycle(k);
  if (k > 0) {
    simulateVelocity(u_input);
    sense(v_p);
  }
  const std::vector<double> prediction = predict(v_p);
  param_->set_vp_prediction(prediction);

  // Space domain at high preceding-vehicle speed, time domain below the
  // threshold (paper Eq. 42).
  const double v_p_min = *std::min_element(prediction.begin(), prediction.end());
  param_->set_use_space_domain(param_->isSpaceDomain() &&
                               v_p_min > param_->get_domain_switch_threshold());

  if (param_->isSpaceDomain()) {
    double delta_s = 1.0 * param_->get_v_h_0() * param_->get_delta_t();
    param_->set_delta_s(std::max(delta_s, 1.0));
  }

  if (k == 0) { // initial condition of the experiment
    param_->set_v_h_0(0.0);
    param_->set_d_h_0(5.5);
    param_->set_f_t_prev(0.0);
    param_->set_f_b_prev(0.0);
    param_->set_v_h_prev(0.0);
    param_->set_v_p_prev(v_p);
  }
}

} // namespace macc::mpc
