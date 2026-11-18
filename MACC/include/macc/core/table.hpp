#ifndef MACC_CORE_TABLE_HPP
#define MACC_CORE_TABLE_HPP

// Column-oriented numeric table that is written as CSV at the end of a run.

#include <cstddef>
#include <string>
#include <vector>

namespace macc::core {

class Table {
public:
  // Returns the column index (re-uses an existing column of the same name).
  std::size_t column(const std::string &name);
  void append(std::size_t col, double value) { cols_[col].push_back(value); }
  void append(const std::string &name, double value) { append(column(name), value); }

  std::size_t numColumns() const { return names_.size(); }
  std::size_t numRows() const { return cols_.empty() ? 0 : cols_[0].size(); }
  const std::vector<std::string> &names() const { return names_; }
  const std::vector<double> &values(const std::string &name) const;
  bool has(const std::string &name) const;

  // Throws std::runtime_error if the file cannot be written.
  void writeCsv(const std::string &path) const;

private:
  std::vector<std::string> names_;
  std::vector<std::vector<double>> cols_;
};

} // namespace macc::core

#endif // MACC_CORE_TABLE_HPP
