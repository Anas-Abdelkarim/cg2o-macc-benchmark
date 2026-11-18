#include "macc/nlp/macc_nlp.hpp"

#include <cstddef>
#include <stdexcept>
#include <string>

namespace macc::nlp {

ProblemData ProblemData::fromParameters(const mpc::MPCParameters &p,
                                        bool require_predictions) {
  if (p.isLinearDynamics())
    throw std::invalid_argument(
        "MaccNLP: acc_settings.linearDynamics=1 (sqrt-form dynamics) is not "
        "implemented in the NLP evaluator / IPOPT backend; set it to 0.");
  ProblemData d;
  d.N = p.get_N();
  d.space_domain = p.useSpaceDomain();
  d.linear_v_bounds = p.isLinearInequalities();
  d.c_a = p.get_c_a();
  d.c_r = p.get_c_r();
  d.g = p.get_g();
  d.m_eq = p.get_m_eq();
  d.m_total = p.get_m_total();
  d.delta_s = p.get_delta_s();
  d.delta_t = p.get_delta_t();
  d.Omega1 = p.get_Omega1();
  d.Omega6 = p.get_Omega6();
  d.BrakePenalty = p.get_BrakePenalty();
  d.BrakeChangePenalty = p.get_BrakeChangePenalty();
  d.TractionChangePenalty = p.get_TractionChangePenalty();
  const auto &eff = p.get_eff_map();
  d.eff_p01 = eff[1];
  d.eff_p02 = eff[2];
  d.eff_p10 = eff[3];
  d.eff_p11 = eff[4];
  d.eff_p20 = eff[5];
  d.a2 = p.get_a2();
  d.b2 = p.get_b2();
  d.b3 = p.get_b3();
  d.b4 = p.get_b4();
  d.b_max = p.get_b_max();
  d.Regen_max = p.get_Regen_max();
  d.Brems_a1 = p.get_Brems_a1();
  d.Brems_b1 = p.get_Brems_b1();
  d.h_min = p.get_h_min();
  d.h_soft = p.get_h_soft();
  d.d_min = p.get_d_min();
  d.delta_f_t_max = p.get_delta_f_t_max();
  d.delta_f_b_max = p.get_delta_f_b_max();
  d.v_h_0 = p.get_v_h_0();
  d.d_h_0 = p.get_d_h_0();
  d.f_t_prev = p.get_f_t_prev();
  d.f_b_prev = p.get_f_b_prev();
  const std::size_t need = static_cast<std::size_t>(d.N) + 1;
  auto take = [&](const std::vector<double> &src, const char *name) {
    if (src.size() < need) {
      if (!require_predictions) return std::vector<double>(need, 0.0);
      throw std::invalid_argument(std::string("MaccNLP: prediction '") + name +
                                  "' has fewer than N+1 entries");
    }
    return std::vector<double>(src.begin(),
                               src.begin() + static_cast<std::ptrdiff_t>(need));
  };
  d.v_p = take(p.get_vp_prediction(), "v_p");
  d.alpha = take(p.get_alpha_prediction(), "alpha");
  d.v_min = take(p.get_v_min_prediction(), "v_min");
  d.v_max = take(p.get_v_max_prediction(), "v_max");
  return d;
}

} // namespace macc::nlp
