#ifndef MACC_SRC_NLP_HESSIAN_IMPL_HPP
#define MACC_SRC_NLP_HESSIAN_IMPL_HPP

// Lagrangian Hessian generator.
// Private to src/nlp; not part of the public headers.

#include "macc/nlp/macc_nlp.hpp"

#include "nlp_helpers.hpp"

#include <cmath>
#include <utility>

namespace macc::nlp::detail {

// ---------------------------------------------------------------------------
// Hessian of  sigma*f + sum_r lambda_r c_r  (lower triangle, emit(i, j, v))
// ---------------------------------------------------------------------------
template <class Emit>
void hessianImpl(const ProblemData &d, const Layout &L, const double *x,
                 double sigma, const double *lambda, Emit &&emit) {
  auto put = [&](int i, int j, double v) {
    if (i < j) std::swap(i, j);
    emit(i, j, v);
  };
  const EnergyCoeff ec = energyCoeff(d);

  for (int k = 0; k < d.N; ++k) {
    const double v0 = vAt(d, L, x, k);
    const double v1 = x[L.v(k + 1)];
    const bool has_prev_state = (k >= 1);

    // ---- objective ---------------------------------------------------------
    {
      const double ft = x[L.ft(k)];
      const double e0 = v0 * v0 + ec.h0;
      const double e1 = ft + ec.h1;
      const double u0 = ec.q00 * e0 + ec.q01 * e1;
      if (has_prev_state) {
        put(L.v(k), L.v(k),
            sigma * (4.0 * d.Omega1 * u0 + 8.0 * d.Omega1 * ec.q00 * v0 * v0));
        put(L.ft(k), L.v(k), sigma * 4.0 * d.Omega1 * v0 * ec.q01);
      }
      put(L.ft(k), L.ft(k), sigma * 2.0 * d.Omega1 * ec.q11);
      put(L.fb(k), L.fb(k), sigma * 2.0 * d.BrakePenalty);
      put(L.s3(k), L.s3(k), sigma * 2.0 * d.BrakeChangePenalty);
      put(L.s2(k), L.s2(k), sigma * 2.0 * d.TractionChangePenalty);
      put(L.s1(k + 1), L.s1(k + 1), sigma * 2.0 * d.Omega6);
    }
    // ---- v_h dynamics ------------------------------------------------------
    {
      const double lam = lambda[rowIndex(k, Row::DynV)];
      if (d.space_domain) {
        const SpaceCoeff c = spaceCoeff(d, k);
        put(L.v(k + 1), L.v(k + 1), 2.0 * lam);
        if (has_prev_state) put(L.v(k), L.v(k), -2.0 * c.A * lam);
      } else {
        const double s = d.delta_t / d.m_eq;
        put(L.v(k + 1), L.v(k + 1), 0.0);
        if (has_prev_state) put(L.v(k), L.v(k), 2.0 * d.c_a * s * lam);
      }
    }
    // ---- d_h dynamics ------------------------------------------------------
    {
      const double lam = lambda[rowIndex(k, Row::DynD)];
      if (d.space_domain) {
        const double S = d.v_p[static_cast<std::size_t>(k)] +
                         d.v_p[static_cast<std::size_t>(k + 1)];
        const double den = v0 + v1;
        const double h = -2.0 * d.delta_s * S / (den * den * den) * lam;
        put(L.v(k + 1), L.v(k + 1), h);
        if (has_prev_state) {
          put(L.v(k), L.v(k), h);
          put(L.v(k + 1), L.v(k), h);
        }
      } else {
        put(L.v(k + 1), L.v(k + 1), 0.0);
        if (has_prev_state) {
          put(L.v(k), L.v(k), 0.0);
          put(L.v(k + 1), L.v(k), 0.0);
        }
      }
    }
    // ---- cubic speed bounds ------------------------------------------------
    {
      const double lmax = lambda[rowIndex(k, Row::VMax)];
      const double lmin = lambda[rowIndex(k, Row::VMin)];
      put(L.v(k + 1), L.v(k + 1),
          d.linear_v_bounds ? 0.0 : 6.0 * v1 * (lmax - lmin));
    }
  }
}

} // namespace macc::nlp::detail

#endif // MACC_SRC_NLP_HESSIAN_IMPL_HPP
