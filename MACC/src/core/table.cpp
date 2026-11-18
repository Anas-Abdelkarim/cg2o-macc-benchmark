#include "macc/core/table.hpp"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <stdexcept>

namespace macc::core {

std::size_t Table::column(const std::string &name) {
  for (std::size_t i = 0; i < names_.size(); ++i)
    if (names_[i] == name) return i;
  names_.push_back(name);
  cols_.emplace_back();
  return names_.size() - 1;
}

bool Table::has(const std::string &name) const {
  for (const auto &n : names_)
    if (n == name) return true;
  return false;
}

const std::vector<double> &Table::values(const std::string &name) const {
  for (std::size_t i = 0; i < names_.size(); ++i)
    if (names_[i] == name) return cols_[i];
  throw std::out_of_range("Table has no column '" + name + "'");
}

void Table::writeCsv(const std::string &path) const {
  std::ofstream os(path);
  if (!os) throw std::runtime_error("Cannot write " + path);
  for (std::size_t c = 0; c < names_.size(); ++c) os << (c ? "," : "") << names_[c];
  os << '\n';
  os << std::setprecision(10);
  for (std::size_t r = 0; r < numRows(); ++r) {
    for (std::size_t c = 0; c < cols_.size(); ++c) {
      os << (c ? "," : "");
      const double v = r < cols_[c].size() ? cols_[c][r] : std::nan("");
      if (std::isnan(v)) os << "nan";
      else if (std::isinf(v)) os << (v > 0 ? "inf" : "-inf");
      else os << v;
    }
    os << '\n';
  }
}

} // namespace macc::core
