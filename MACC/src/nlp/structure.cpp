#include "macc/nlp/macc_nlp.hpp"

#include "hessian_impl.hpp"
#include "jacobian_impl.hpp"
#include "structure_recorder.hpp"

#include <algorithm>
#include <cstddef>
#include <vector>

namespace macc::nlp {

using namespace detail;

void MaccNLP::buildStructure() {
  std::vector<double> x(static_cast<std::size_t>(numVariables()), 1.0);
  std::vector<double> lam(static_cast<std::size_t>(numConstraints()), 1.0);
  // The recorded pattern must not depend on the data: use the space-domain
  // flavour (a superset of the time-domain one) with strictly positive speeds
  // so that 1/(v0+v1) is finite while recording.
  ProblemData probe = d_;
  probe.v_h_0 = 1.0;
  probe.space_domain = true;
  probe.delta_s = 1.0;
  probe.m_eq = probe.m_eq != 0.0 ? probe.m_eq : 1.0;
  probe.v_p.assign(static_cast<std::size_t>(probe.N) + 1, 1.0);
  probe.alpha.assign(static_cast<std::size_t>(probe.N) + 1, 0.0);
  jac_i_.clear(); jac_j_.clear(); jac_slot_.clear();
  hes_i_.clear(); hes_j_.clear(); hes_slot_.clear();
  {
    Recorder rec;
    rec.ri = &jac_i_; rec.rj = &jac_j_; rec.slot = &jac_slot_;
    jacobianImpl(probe, L_, x.data(), rec);
  }
  {
    Recorder rec;
    rec.ri = &hes_i_; rec.rj = &hes_j_; rec.slot = &hes_slot_;
    hessianImpl(probe, L_, x.data(), 1.0, lam.data(), rec);
  }
  // The call sequence of the time-domain flavour is identical in length for the
  // Jacobian and emits only explicit (zero) entries in the Hessian where the
  // space domain has non-zeros, so slot maps are valid for both domains.
}

void MaccNLP::jacobianStructure(int *irow, int *jcol) const {
  std::copy(jac_i_.begin(), jac_i_.end(), irow);
  std::copy(jac_j_.begin(), jac_j_.end(), jcol);
}

void MaccNLP::jacobianValues(const double *x, double *values) const {
  std::fill(values, values + jacobianNnz(), 0.0);
  std::size_t c = 0;
  jacobianImpl(d_, L_, x,
               [&](int, int, double v) { values[jac_slot_[c++]] += v; });
}

void MaccNLP::hessianStructure(int *irow, int *jcol) const {
  std::copy(hes_i_.begin(), hes_i_.end(), irow);
  std::copy(hes_j_.begin(), hes_j_.end(), jcol);
}

void MaccNLP::hessianValues(const double *x, double sigma, const double *lambda,
                            double *values) const {
  std::fill(values, values + hessianNnz(), 0.0);
  std::size_t c = 0;
  hessianImpl(d_, L_, x, sigma, lambda,
              [&](int, int, double v) { values[hes_slot_[c++]] += v; });
}

} // namespace macc::nlp
