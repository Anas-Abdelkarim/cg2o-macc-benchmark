// Used when MACC is built without IPOPT (MACC_WITH_IPOPT=OFF or not found).
#include "macc/backends/factory.hpp"

#include <stdexcept>

namespace macc::backends {

bool ipoptAvailable() { return false; }
std::string ipoptVersion() { return "not built"; }

IpoptSettings readIpoptSettings(const core::Config &cfg) {
  IpoptSettings s;
  s.max_iterations = cfg.get<int>("mpc.number_of_iterations", 120);
  s.init_value = cfg.get<double>("mpc.init_value", 10.0);
  s.options = cfg.items("ipopt_settings.options");
  return s;
}

std::unique_ptr<Controller> makeIpoptController(std::shared_ptr<mpc::MPCParameters>,
                                                const IpoptSettings &) {
  throw std::runtime_error(
      "This MACC build has no IPOPT support. Install IPOPT "
      "(scripts/build_externals.sh --ipopt-only  or  sudo apt install coinor-libipopt-dev) "
      "and reconfigure with -DMACC_WITH_IPOPT=ON.");
}

} // namespace macc::backends
