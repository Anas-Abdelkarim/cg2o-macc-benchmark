#ifndef MACC_SRC_NLP_JACOBIAN_IMPL_HPP
#define MACC_SRC_NLP_JACOBIAN_IMPL_HPP

// Constraint Jacobian generator.
// Private to src/nlp; not part of the public headers.

#include "macc/nlp/macc_nlp.hpp"

#include "nlp_helpers.hpp"

#include <cmath>

namespace macc::nlp::detail {

// ---------------------------------------------------------------------------
// Jacobian: emit(row, col, value). The sequence of emit() calls depends only
// on (N, flags), never on x, so one pass can record the structure and another
// can fill the values in the same order.
// ---------------------------------------------------------------------------
template <class Emit>
void jacobianImpl(const ProblemData &d, const Layout &L, const double *x,
                  Emit &&emit) {
  for (int k = 0; k < d.N; ++k) {
    const double v0 = vAt(d, L, x, k);
    const double v1 = x[L.v(k + 1)];
    const bool has_prev_state = (k >= 1);

    // ---- DynV --------------------------------------------------------------
    {
      const int r = rowIndex(k, Row::DynV);
      if (d.space_domain) {
        const SpaceCoeff c = spaceCoeff(d, k);
        emit(r, L.v(k + 1), 2.0 * v1);
        if (has_prev_state) emit(r, L.v(k), -2.0 * c.A * v0);
        emit(r, L.ft(k), -c.B);
        emit(r, L.fb(k), c.B);
      } else {
        const double s = d.delta_t / d.m_eq;
        emit(r, L.v(k + 1), 1.0);
        if (has_prev_state) emit(r, L.v(k), -(1.0 - s * 2.0 * d.c_a * v0));
        emit(r, L.ft(k), -s);
        emit(r, L.fb(k), s);
      }
    }
    // ---- DynD --------------------------------------------------------------
    {
      const int r = rowIndex(k, Row::DynD);
      emit(r, L.d(k + 1), 1.0);
      if (has_prev_state) emit(r, L.d(k), -1.0);
      if (d.space_domain) {
        const double S = d.v_p[static_cast<std::size_t>(k)] +
                         d.v_p[static_cast<std::size_t>(k + 1)];
        const double den = v0 + v1;
        const double dv = d.delta_s * S / (den * den);
        if (has_prev_state) emit(r, L.v(k), dv);
        emit(r, L.v(k + 1), dv);
      } else {
        if (has_prev_state) emit(r, L.v(k), d.delta_t / 2.0);
        emit(r, L.v(k + 1), d.delta_t / 2.0);
      }
    }
    // ---- speed bounds ------------------------------------------------------
    emit(rowIndex(k, Row::VMax), L.v(k + 1),
         d.linear_v_bounds ? 1.0 : 3.0 * v1 * v1);
    emit(rowIndex(k, Row::VMin), L.v(k + 1),
         d.linear_v_bounds ? -1.0 : -3.0 * v1 * v1);
    // ---- distance bounds ---------------------------------------------------
    {
      const int r = rowIndex(k, Row::DMax);
      emit(r, L.d(k + 1), 1.0);
      emit(r, L.v(k + 1), -d.h_soft);
      emit(r, L.s1(k + 1), -1.0);
    }
    {
      const int r = rowIndex(k, Row::DMin);
      emit(r, L.v(k + 1), d.h_min);
      emit(r, L.d(k + 1), -1.0);
    }
    // ---- traction force ----------------------------------------------------
    emit(rowIndex(k, Row::FtMax1), L.ft(k), 1.0);
    {
      const int r = rowIndex(k, Row::FtMax2);
      emit(r, L.ft(k), 1.0);
      if (has_prev_state) emit(r, L.v(k), -d.a2);
    }
    emit(rowIndex(k, Row::FtMin), L.ft(k), -1.0);
    // ---- braking force -----------------------------------------------------
    emit(rowIndex(k, Row::FbMax1), L.fb(k), 1.0);
    {
      const int r = rowIndex(k, Row::FbMax2);
      emit(r, L.fb(k), 1.0);
      if (has_prev_state) emit(r, L.v(k), -d.Brems_a1);
    }
    emit(rowIndex(k, Row::FbMin), L.fb(k), -1.0);
    // ---- rate limits -------------------------------------------------------
    {
      int r = rowIndex(k, Row::FtUp);
      emit(r, L.ft(k), 1.0);
      if (k >= 1) emit(r, L.ft(k - 1), -1.0);
      emit(r, L.s2(k), -1.0);
      r = rowIndex(k, Row::FtDown);
      emit(r, L.ft(k), -1.0);
      if (k >= 1) emit(r, L.ft(k - 1), 1.0);
      emit(r, L.s2(k), -1.0);
      r = rowIndex(k, Row::FbUp);
      emit(r, L.fb(k), 1.0);
      if (k >= 1) emit(r, L.fb(k - 1), -1.0);
      emit(r, L.s3(k), -1.0);
      r = rowIndex(k, Row::FbDown);
      emit(r, L.fb(k), -1.0);
      if (k >= 1) emit(r, L.fb(k - 1), 1.0);
      emit(r, L.s3(k), -1.0);
    }
  }
}

} // namespace macc::nlp::detail

#endif // MACC_SRC_NLP_JACOBIAN_IMPL_HPP
