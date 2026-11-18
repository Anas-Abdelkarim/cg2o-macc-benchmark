#include "macc/nlp/macc_nlp.hpp"

#include "nlp_helpers.hpp"

#include <algorithm>
#include <cstddef>

namespace macc::nlp {

using namespace detail;

double MaccNLP::objective(const double *x) const {
  const ProblemData &d = d_;
  const EnergyCoeff ec = energyCoeff(d);
  double f = 0.0;
  for (int k = 0; k < d.N; ++k) {
    const double v = vAt(d, L_, x, k);
    const double ft = x[L_.ft(k)];
    const double fb = x[L_.fb(k)];
    const double e0 = v * v + ec.h0;
    const double e1 = ft + ec.h1;
    f += d.Omega1 * (ec.q00 * e0 * e0 + 2.0 * ec.q01 * e0 * e1 + ec.q11 * e1 * e1);
    f += d.BrakePenalty * fb * fb;
    const double s3 = x[L_.s3(k)];
    const double s2 = x[L_.s2(k)];
    const double s1 = x[L_.s1(k + 1)];
    f += d.BrakeChangePenalty * s3 * s3;
    f += d.TractionChangePenalty * s2 * s2;
    f += d.Omega6 * s1 * s1;
  }
  return f;
}

void MaccNLP::gradient(const double *x, double *grad) const {
  const ProblemData &d = d_;
  std::fill(grad, grad + numVariables(), 0.0);
  const EnergyCoeff ec = energyCoeff(d);
  for (int k = 0; k < d.N; ++k) {
    const double v = vAt(d, L_, x, k);
    const double ft = x[L_.ft(k)];
    const double e0 = v * v + ec.h0;
    const double e1 = ft + ec.h1;
    const double u0 = ec.q00 * e0 + ec.q01 * e1;
    const double u1 = ec.q01 * e0 + ec.q11 * e1;
    if (k >= 1) grad[L_.v(k)] += 4.0 * d.Omega1 * u0 * v;
    grad[L_.ft(k)] += 2.0 * d.Omega1 * u1;
    grad[L_.fb(k)] += 2.0 * d.BrakePenalty * x[L_.fb(k)];
    grad[L_.s3(k)] += 2.0 * d.BrakeChangePenalty * x[L_.s3(k)];
    grad[L_.s2(k)] += 2.0 * d.TractionChangePenalty * x[L_.s2(k)];
    grad[L_.s1(k + 1)] += 2.0 * d.Omega6 * x[L_.s1(k + 1)];
  }
}

void MaccNLP::constraints(const double *x, double *g) const {
  const ProblemData &d = d_;
  for (int k = 0; k < d.N; ++k) {
    const double v0 = vAt(d, L_, x, k);
    const double v1 = x[L_.v(k + 1)];
    const double d0 = dAt(d, L_, x, k);
    const double d1 = x[L_.d(k + 1)];
    const double ft = x[L_.ft(k)];
    const double fb = x[L_.fb(k)];
    const double s1 = x[L_.s1(k + 1)];
    const double s2 = x[L_.s2(k)];
    const double s3 = x[L_.s3(k)];
    const double ft_prev = (k == 0) ? d.f_t_prev : x[L_.ft(k - 1)];
    const double fb_prev = (k == 0) ? d.f_b_prev : x[L_.fb(k - 1)];
    const double S = d.v_p[static_cast<std::size_t>(k)] +
                     d.v_p[static_cast<std::size_t>(k + 1)];

    double *gr = g + kRowsPerStage * k;
    if (d.space_domain) {
      const SpaceCoeff c = spaceCoeff(d, k);
      gr[R(Row::DynV)] = v1 * v1 - (v0 * v0 * c.A + c.B * (ft - fb) + c.w1);
      const double dt = 2.0 * d.delta_s / (v0 + v1);
      gr[R(Row::DynD)] = d1 - (d0 + dt / 2.0 * S - d.delta_s);
    } else {
      const double s = d.delta_t / d.m_eq;
      gr[R(Row::DynV)] =
          v1 - (v0 + s * ((ft - fb) - (timeForces(d, k) + d.c_a * v0 * v0)));
      gr[R(Row::DynD)] = d1 - (d0 + d.delta_t / 2.0 * (S - (v0 + v1)));
    }
    const double vmax = d.v_max[static_cast<std::size_t>(k + 1)];
    const double vmin = d.v_min[static_cast<std::size_t>(k + 1)];
    if (d.linear_v_bounds) {
      gr[R(Row::VMax)] = v1 - vmax;
      gr[R(Row::VMin)] = vmin - v1;
    } else {
      gr[R(Row::VMax)] = v1 * v1 * v1 - vmax * vmax * vmax;
      gr[R(Row::VMin)] = vmin * vmin * vmin - v1 * v1 * v1;
    }
    gr[R(Row::DMax)] = d1 - (d.h_soft * v1 + s1);
    gr[R(Row::DMin)] = (d.h_min * v1 + d.d_min) - d1;
    gr[R(Row::FtMax1)] = ft - d.b4;
    gr[R(Row::FtMax2)] = ft - (d.a2 * v0 + d.b2);
    gr[R(Row::FtMin)] = d.b3 - ft;
    gr[R(Row::FbMax1)] = fb - (d.b_max + d.Regen_max);
    gr[R(Row::FbMax2)] = fb - (d.Brems_a1 * v0 + d.b_max + d.Brems_b1);
    gr[R(Row::FbMin)] = 0.0 - fb;
    gr[R(Row::FtUp)] = ft - ft_prev - (d.delta_f_t_max + s2);
    gr[R(Row::FtDown)] = -(ft - ft_prev) - (d.delta_f_t_max + s2);
    gr[R(Row::FbUp)] = fb - fb_prev - (d.delta_f_b_max + s3);
    gr[R(Row::FbDown)] = -(fb - fb_prev) - (d.delta_f_b_max + s3);
  }
}

} // namespace macc::nlp
