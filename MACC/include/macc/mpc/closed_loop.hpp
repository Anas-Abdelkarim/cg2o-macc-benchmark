#ifndef MACC_MPC_CLOSED_LOOP_HPP
#define MACC_MPC_CLOSED_LOOP_HPP

// Simulation environment of the closed-loop MACC experiment (paper Sec. V-B,
// "Simulation Scenario"): vehicle model with plant/model mismatch, virtual
// distance sensor and the preceding-vehicle predictor. It owns no solver; it
// only keeps the shared MPCParameters (current state, predictions, domain) up
// to date between two MPC steps.

#include "macc/mpc/parameters.h"

#include <deque>
#include <memory>
#include <vector>

namespace macc::mpc {

class ClosedLoopPlant {
public:
  explicit ClosedLoopPlant(std::shared_ptr<MPCParameters> param);

  // Advance the world to MPC step k, given the input u applied at step k-1
  // (u = f_t - f_b). Afterwards the parameter object describes the optimal
  // control problem of step k (state, previous forces, v_p prediction,
  // space/time domain, delta_s).
  void beginStep(int k, double u_previous);

  // Weighted one-step-ahead acceleration estimate of the preceding vehicle.
  double predictedPrecedingAcceleration() const;
  // Most recent measured acceleration of the preceding vehicle.
  double measuredPrecedingAcceleration() const { return a_p_memory_.back(); }

  bool spaceDomainActive() const { return param_->useSpaceDomain(); }

private:
  double simulateVelocity(double u_car);
  void sense(double v_p);
  std::vector<double> predict(double v_p) const;

  std::shared_ptr<MPCParameters> param_;
  std::deque<double> a_p_memory_;
};

} // namespace macc::mpc

#endif // MACC_MPC_CLOSED_LOOP_HPP
