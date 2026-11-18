#ifndef MACC_SRC_NLP_HELPERS_HPP
#define MACC_SRC_NLP_HELPERS_HPP

// Index helpers and coefficient bundles shared by the NLP evaluators.
// Private to src/nlp; not part of the public headers.

#include "macc/nlp/macc_nlp.hpp"

#include <cmath>
#include <cstddef>

namespace macc::nlp::detail {

constexpr double kDegToRad = 3.14159265358979323846 / 180.0;

inline int rowIndex(int k, Row r) {
  return kRowsPerStage * k + static_cast<int>(r);
}
inline int R(Row r) { return static_cast<int>(r); }

// v_h[k], d_h[k] with the constant initial state at k = 0
inline double vAt(const ProblemData &d, const Layout &L, const double *x, int k) {
  return k == 0 ? d.v_h_0 : x[L.v(k)];
}
inline double dAt(const ProblemData &d, const Layout &L, const double *x, int k) {
  return k == 0 ? d.d_h_0 : x[L.d(k)];
}

// Constants of the space-domain velocity dynamics at stage k.
struct SpaceCoeff {
  double A, B, w1;
};
inline SpaceCoeff spaceCoeff(const ProblemData &d, int k) {
  SpaceCoeff c;
  c.A = 1.0 - 2.0 * d.c_a * d.delta_s / d.m_eq;
  c.B = 2.0 * d.delta_s / d.m_eq;
  const double a = d.alpha[static_cast<std::size_t>(k)] * kDegToRad;
  c.w1 = -c.B * d.m_total * d.g * (std::sin(a) + d.c_r * std::cos(a));
  return c;
}
// rolling + gravity force of the time-domain dynamics (p1 = 0)
inline double timeForces(const ProblemData &d, int k) {
  const double a = d.alpha[static_cast<std::size_t>(k)] * kDegToRad;
  const double f_roll = d.c_r * d.m_total * d.g * std::cos(a);
  const double f_grav = d.m_total * d.g * std::sin(a);
  return f_roll + f_grav;
}

// Constants of the completed-square energy term  e = (v^2, f_t) + 0.5 Q^-1 b.
struct EnergyCoeff {
  double q00, q01, q11, h0, h1;
};
inline EnergyCoeff energyCoeff(const ProblemData &d) {
  EnergyCoeff c;
  c.q00 = d.eff_p20;
  c.q01 = 0.5 * d.eff_p11;
  c.q11 = d.eff_p02;
  const double det = c.q00 * c.q11 - c.q01 * c.q01;
  const double b0 = d.eff_p10, b1 = d.eff_p01;
  c.h0 = 0.5 * (c.q11 * b0 - c.q01 * b1) / det;
  c.h1 = 0.5 * (-c.q01 * b0 + c.q00 * b1) / det;
  return c;
}

} // namespace macc::nlp::detail

#endif // MACC_SRC_NLP_HELPERS_HPP
