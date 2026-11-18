#ifndef MACC_CORE_RUN_INFO_HPP
#define MACC_CORE_RUN_INFO_HPP

// Everything needed to describe *where and how* a run was produced:
// timestamp, machine, compiler, build type, git revision, command line, and the
// run-directory / console-log helpers.

#include <filesystem>
#include <iosfwd>
#include <streambuf>
#include <string>
#include <vector>

namespace macc::core {

struct SystemInfo {
  std::string hostname, user, os, kernel;
  std::string cpu_model;
  unsigned logical_cores = 0;
  double mem_total_gb = 0.0;
  std::string compiler, build_type, cxx_standard;
  std::string git_commit, git_state;
  std::string source_dir, working_dir;
  std::string g2o_prefix, cg2o_prefix, ipopt_version;
  std::string command_line;
};

SystemInfo collectSystemInfo(int argc, char **argv);

// "20260122_153012" (file names) and "2026-01-22 15:30:12 +0100" (reports).
std::string timestampCompact();
std::string timestampHuman();

// Create "<base>/<timestamp>_<label>" (made unique if it already exists).
std::filesystem::path createRunDirectory(const std::filesystem::path &base,
                                         const std::string &label);

// Replace characters that are awkward in file names.
std::string sanitizeLabel(const std::string &label);

// Duplicates everything written to std::cout into a log file.
class ConsoleTee {
public:
  explicit ConsoleTee(const std::filesystem::path &log_file);
  ~ConsoleTee();
  ConsoleTee(const ConsoleTee &) = delete;
  ConsoleTee &operator=(const ConsoleTee &) = delete;

private:
  struct Impl;
  Impl *impl_;
};

// Writes "key : value" lines with aligned columns into the experiment report.
class ReportWriter {
public:
  explicit ReportWriter(std::ostream &os) : os_(os) {}
  void title(const std::string &text);
  void section(const std::string &text);
  void kv(const std::string &key, const std::string &value);
  void kv(const std::string &key, double value, int precision = 6);
  void kv(const std::string &key, long long value);
  void line(const std::string &text = "");

private:
  std::ostream &os_;
};

} // namespace macc::core

#endif // MACC_CORE_RUN_INFO_HPP
