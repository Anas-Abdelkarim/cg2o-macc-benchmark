#include "macc/core/run_info.hpp"

#include <unistd.h>
#include <sys/utsname.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <thread>

#ifndef MACC_BUILD_TYPE
#define MACC_BUILD_TYPE "unknown"
#endif
#ifndef MACC_SOURCE_DIR
#define MACC_SOURCE_DIR ""
#endif
#ifndef MACC_G2O_PREFIX_STR
#define MACC_G2O_PREFIX_STR ""
#endif
#ifndef MACC_CG2O_PREFIX_STR
#define MACC_CG2O_PREFIX_STR ""
#endif
#ifndef MACC_IPOPT_VERSION_STR
#define MACC_IPOPT_VERSION_STR "not built"
#endif

namespace fs = std::filesystem;

namespace macc::core {

namespace {

std::string shell(const std::string &cmd) {
  std::array<char, 256> buf{};
  std::string out;
  if (FILE *p = popen(cmd.c_str(), "r")) {
    while (fgets(buf.data(), static_cast<int>(buf.size()), p)) out += buf.data();
    pclose(p);
  }
  while (!out.empty() && (out.back() == '\n' || out.back() == '\r')) out.pop_back();
  return out;
}

std::string readKey(const std::string &file, const std::string &key) {
  std::ifstream is(file);
  std::string line;
  while (std::getline(is, line)) {
    if (line.rfind(key, 0) == 0) {
      auto pos = line.find(':');
      if (pos == std::string::npos) pos = line.find('=');
      if (pos != std::string::npos) {
        std::string v = line.substr(pos + 1);
        v.erase(0, v.find_first_not_of(" \t\""));
        v.erase(v.find_last_not_of(" \t\"") + 1);
        return v;
      }
    }
  }
  return {};
}

std::string timeFormat(const char *fmt) {
  std::time_t t = std::time(nullptr);
  std::tm tm{};
  localtime_r(&t, &tm);
  std::ostringstream os;
  os << std::put_time(&tm, fmt);
  return os.str();
}

} // namespace

std::string timestampCompact() { return timeFormat("%Y%m%d_%H%M%S"); }
std::string timestampHuman() { return timeFormat("%Y-%m-%d %H:%M:%S %z"); }

std::string sanitizeLabel(const std::string &label) {
  std::string s = label;
  for (char &c : s)
    if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '-' || c == '_' || c == '.')) c = '_';
  return s;
}

SystemInfo collectSystemInfo(int argc, char **argv) {
  SystemInfo s;
  char host[256] = {0};
  if (gethostname(host, sizeof(host) - 1) == 0) s.hostname = host;
  if (const char *u = std::getenv("USER")) s.user = u;
  struct utsname un;
  if (uname(&un) == 0) s.kernel = std::string(un.sysname) + " " + un.release;
  s.os = readKey("/etc/os-release", "PRETTY_NAME");
  s.cpu_model = readKey("/proc/cpuinfo", "model name");
  s.logical_cores = std::thread::hardware_concurrency();
  {
    const std::string kb = readKey("/proc/meminfo", "MemTotal");
    if (!kb.empty()) s.mem_total_gb = std::atof(kb.c_str()) / 1024.0 / 1024.0;
  }
#if defined(__clang__)
  s.compiler = std::string("clang ") + __clang_version__;
#elif defined(__GNUC__)
  s.compiler = std::string("GCC ") + __VERSION__;
#else
  s.compiler = "unknown";
#endif
  s.build_type = MACC_BUILD_TYPE;
  s.cxx_standard = std::to_string(__cplusplus);
  s.source_dir = MACC_SOURCE_DIR;
  s.g2o_prefix = MACC_G2O_PREFIX_STR;
  s.cg2o_prefix = MACC_CG2O_PREFIX_STR;
  s.ipopt_version = MACC_IPOPT_VERSION_STR;
  s.working_dir = fs::current_path().string();
  if (!s.source_dir.empty() && fs::exists(fs::path(s.source_dir) / ".git")) {
    s.git_commit = shell("git -C '" + s.source_dir + "' rev-parse --short HEAD 2>/dev/null");
    s.git_state = shell("git -C '" + s.source_dir + "' status --porcelain 2>/dev/null | head -1").empty()
                      ? "clean" : "modified";
  } else {
    s.git_commit = "not a git checkout";
  }
  std::ostringstream cl;
  for (int i = 0; i < argc; ++i) cl << (i ? " " : "") << argv[i];
  s.command_line = cl.str();
  return s;
}

fs::path createRunDirectory(const fs::path &base, const std::string &label) {
  fs::create_directories(base);
  const std::string stem = timestampCompact() + (label.empty() ? "" : "_" + sanitizeLabel(label));
  fs::path dir = base / stem;
  for (int n = 2; fs::exists(dir); ++n) dir = base / (stem + "_" + std::to_string(n));
  fs::create_directories(dir);
  return dir;
}

// --------------------------- ConsoleTee ------------------------------------

struct ConsoleTee::Impl : public std::streambuf {
  std::streambuf *original = nullptr;
  std::ofstream file;
  int overflow(int c) override {
    if (c == EOF) return !EOF;
    file.put(static_cast<char>(c));
    return original->sputc(static_cast<char>(c));
  }
  std::streamsize xsputn(const char *s, std::streamsize n) override {
    file.write(s, n);
    return original->sputn(s, n);
  }
  int sync() override {
    file.flush();
    return original->pubsync();
  }
};

ConsoleTee::ConsoleTee(const fs::path &log_file) : impl_(new Impl) {
  impl_->file.open(log_file);
  impl_->original = std::cout.rdbuf(impl_);
}

ConsoleTee::~ConsoleTee() {
  std::cout.flush();
  std::cout.rdbuf(impl_->original);
  delete impl_;
}

// --------------------------- ReportWriter ----------------------------------

void ReportWriter::title(const std::string &text) {
  os_ << std::string(78, '=') << "\n" << text << "\n" << std::string(78, '=') << "\n";
}
void ReportWriter::section(const std::string &text) {
  os_ << "\n" << std::string(78, '-') << "\n" << text << "\n" << std::string(78, '-') << "\n";
}
void ReportWriter::kv(const std::string &key, const std::string &value) {
  os_ << std::left << std::setw(34) << key << " : " << value << "\n";
}
void ReportWriter::kv(const std::string &key, double value, int precision) {
  std::ostringstream v;
  v << std::setprecision(precision) << value;
  kv(key, v.str());
}
void ReportWriter::kv(const std::string &key, long long value) { kv(key, std::to_string(value)); }
void ReportWriter::line(const std::string &text) { os_ << text << "\n"; }

} // namespace macc::core
