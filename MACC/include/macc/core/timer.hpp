#ifndef MACC_CORE_TIMER_HPP
#define MACC_CORE_TIMER_HPP

#include <chrono>

namespace macc::core {

// Wall-clock stopwatch (monotonic).
class Stopwatch {
public:
  Stopwatch() { restart(); }
  void restart() { t0_ = Clock::now(); }
  double elapsedMs() const {
    return std::chrono::duration<double, std::milli>(Clock::now() - t0_).count();
  }

private:
  using Clock = std::chrono::steady_clock;
  Clock::time_point t0_;
};

} // namespace macc::core

#endif // MACC_CORE_TIMER_HPP
