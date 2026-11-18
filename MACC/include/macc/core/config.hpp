#ifndef MACC_CORE_CONFIG_HPP
#define MACC_CORE_CONFIG_HPP

// Thin wrapper around a YAML tree with dotted-path access and command-line
// overrides ("--set ispd_settings.tau=1.6"). The resolved tree can be dumped,
// so every run folder contains the exact configuration that was used.

#include <yaml-cpp/yaml.h>

#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace macc::core {

class Config {
public:
  Config() = default;

  static Config fromFile(const std::string &path) {
    Config c;
    try {
      c.root_ = YAML::LoadFile(path);
    } catch (const std::exception &e) {
      throw std::runtime_error("Cannot read config file '" + path + "': " + e.what());
    }
    c.source_ = path;
    return c;
  }

  // Override / create the value at a dotted path. `yaml_value` is parsed as YAML,
  // so "15" is an integer, "1e-3" a number, "true" a bool and "[1,2]" a list.
  void set(const std::string &dotted, const std::string &yaml_value) {
    YAML::Node cur = root_;
    const auto parts = split(dotted);
    if (parts.empty()) throw std::invalid_argument("empty config key");
    // NOTE: yaml-cpp's Node::operator= writes THROUGH the node (it would overwrite
    // the parent), so descending must use reset().
    for (std::size_t i = 0; i + 1 < parts.size(); ++i) cur.reset(cur[parts[i]]);
    cur[parts.back()] = YAML::Load(yaml_value);
    overrides_.push_back(dotted + "=" + yaml_value);
  }

  // "key=value" convenience used by the command-line parser.
  void applyOverride(const std::string &assignment) {
    const auto eq = assignment.find('=');
    if (eq == std::string::npos || eq == 0)
      throw std::invalid_argument("--set expects key=value, got '" + assignment + "'");
    set(assignment.substr(0, eq), assignment.substr(eq + 1));
  }

  bool has(const std::string &dotted) const { return find(dotted).IsDefined(); }

  template <class T> T get(const std::string &dotted) const {
    YAML::Node n = find(dotted);
    if (!n.IsDefined() || n.IsNull())
      throw std::runtime_error("Missing required config key '" + dotted + "'");
    try {
      return n.as<T>();
    } catch (const std::exception &e) {
      throw std::runtime_error("Config key '" + dotted + "' has the wrong type: " + e.what());
    }
  }

  template <class T> T get(const std::string &dotted, const T &fallback) const {
    YAML::Node n = find(dotted);
    if (!n.IsDefined() || n.IsNull()) return fallback;
    try {
      return n.as<T>();
    } catch (const std::exception &e) {
      throw std::runtime_error("Config key '" + dotted + "' has the wrong type: " + e.what());
    }
  }

  // A list given either as a YAML sequence or as "a,b,c". Empty if missing.
  std::vector<std::string> getList(const std::string &dotted) const {
    std::vector<std::string> out;
    YAML::Node n = find(dotted);
    if (!n.IsDefined() || n.IsNull()) return out;
    if (n.IsSequence()) {
      for (const auto &e : n) out.push_back(e.as<std::string>());
      return out;
    }
    std::string all = n.as<std::string>(), cur;
    for (char ch : all) {
      if (ch == ',') {
        if (!cur.empty()) out.push_back(cur);
        cur.clear();
      } else if (ch != ' ') {
        cur += ch;
      }
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
  }

  // Map entries below a key (empty if the key is missing or not a map).
  std::vector<std::pair<std::string, std::string>> items(const std::string &dotted) const {
    std::vector<std::pair<std::string, std::string>> out;
    YAML::Node n = find(dotted);
    if (n.IsDefined() && n.IsMap())
      for (auto it = n.begin(); it != n.end(); ++it)
        out.emplace_back(it->first.as<std::string>(), it->second.as<std::string>());
    return out;
  }

  std::string dump() const {
    std::ostringstream os;
    os << root_;
    return os.str();
  }

  const std::string &sourcePath() const { return source_; }
  const std::vector<std::string> &overrides() const { return overrides_; }
  const YAML::Node &root() const { return root_; }

private:
  static std::vector<std::string> split(const std::string &s) {
    std::vector<std::string> parts;
    std::string cur;
    for (char ch : s) {
      if (ch == '.') {
        parts.push_back(cur);
        cur.clear();
      } else {
        cur += ch;
      }
    }
    parts.push_back(cur);
    return parts;
  }

  YAML::Node find(const std::string &dotted) const {
    YAML::Node cur = root_;
    for (const auto &p : split(dotted)) {
      const YAML::Node &c = cur;
      if (!c.IsMap() || !c[p]) return YAML::Node(YAML::NodeType::Undefined);
      YAML::Node next = c[p];
      cur.reset(next);
    }
    return cur;
  }

  YAML::Node root_{YAML::NodeType::Map};
  std::string source_;
  std::vector<std::string> overrides_;
};

} // namespace macc::core

#endif // MACC_CORE_CONFIG_HPP
