#include "macc/core/stats.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>

namespace macc::core {

namespace {
double quantileSorted(const std::vector<double> &s, double q) {
  if (s.empty()) return std::numeric_limits<double>::quiet_NaN();
  const double pos = q * static_cast<double>(s.size() - 1);
  const std::size_t lo = static_cast<std::size_t>(std::floor(pos));
  const std::size_t hi = static_cast<std::size_t>(std::ceil(pos));
  return s[lo] + (s[hi] - s[lo]) * (pos - static_cast<double>(lo));
}

double medianRange(const std::vector<double> &s, std::size_t start, std::size_t end) {
  const std::size_t len = end - start;
  if (len == 0) return std::numeric_limits<double>::quiet_NaN();
  const std::size_t mid = start + len / 2;
  return (len % 2 == 0) ? 0.5 * (s[mid - 1] + s[mid]) : s[mid];
}
} // namespace

Summary summarize(const std::vector<double> &values) {
  std::vector<double> v;
  v.reserve(values.size());
  for (double x : values)
    if (!std::isnan(x)) v.push_back(x);
  Summary s;
  s.n = v.size();
  if (v.empty()) {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    s.mean = s.min = s.max = s.stddev = s.median = s.p95 = nan;
    return s;
  }
  std::sort(v.begin(), v.end());
  s.min = v.front();
  s.max = v.back();
  s.mean = std::accumulate(v.begin(), v.end(), 0.0) / static_cast<double>(v.size());
  double acc = 0.0;
  for (double x : v) acc += (x - s.mean) * (x - s.mean);
  s.stddev = v.size() > 1 ? std::sqrt(acc / static_cast<double>(v.size() - 1)) : 0.0;
  s.median = quantileSorted(v, 0.5);
  s.p95 = quantileSorted(v, 0.95);
  return s;
}

double meanWithoutOutliers(const std::vector<double> &data) {
  if (data.empty()) return std::numeric_limits<double>::quiet_NaN();
  std::vector<double> sorted = data;
  std::sort(sorted.begin(), sorted.end());
  const std::size_t n = sorted.size();
  const std::size_t half = n / 2;
  if (half == 0) return data[0];
  double q1, q3;
  if (n % 2 == 0) {
    q1 = medianRange(sorted, 0, half);
    q3 = medianRange(sorted, half, n);
  } else {
    q1 = medianRange(sorted, 0, half);
    q3 = medianRange(sorted, half + 1, n);
  }
  const double iqr = q3 - q1;
  const double lo = q1 - 1.5 * iqr, hi = q3 + 1.5 * iqr;
  double sum = 0.0;
  std::size_t count = 0;
  for (double x : data)
    if (x >= lo && x <= hi) {
      sum += x;
      ++count;
    }
  return count ? sum / static_cast<double>(count) : std::numeric_limits<double>::quiet_NaN();
}

} // namespace macc::core
