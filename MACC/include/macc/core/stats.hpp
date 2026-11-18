#ifndef MACC_CORE_STATS_HPP
#define MACC_CORE_STATS_HPP

#include <cstddef>
#include <vector>

namespace macc::core {

struct Summary {
  std::size_t n = 0;
  double mean = 0, min = 0, max = 0, stddev = 0, median = 0, p95 = 0;
};

// Basic descriptive statistics; NaN entries are ignored.
Summary summarize(const std::vector<double> &values);

// Mean after removing values outside [Q1 - 1.5 IQR, Q3 + 1.5 IQR] (the timing
// procedure used for the paper: repeated solves, outliers removed).
double meanWithoutOutliers(const std::vector<double> &values);

} // namespace macc::core

#endif // MACC_CORE_STATS_HPP
