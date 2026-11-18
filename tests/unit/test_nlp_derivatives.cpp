// Finite-difference check of the analytic derivatives of the MACC NLP.
// Needs no g2o / IPOPT: it validates macc::nlp::MaccNLP on its own.
#include "macc/mpc/parameters.h"
#include "macc/nlp/macc_nlp.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <memory>
#include <random>
#include <vector>

using namespace macc;

namespace {

struct Stats { double worst_rel = 0.0; int checked = 0; };

double relErr(double a, double n) {
  return std::fabs(a - n) / std::max(1.0, std::max(std::fabs(a), std::fabs(n)));
}

bool checkProblem(const char *label, bool space, bool linear_v, int N, unsigned seed) {
  auto p = std::make_shared<mpc::MPCParameters>();
  p->set_N(N);
  p->set_use_space_domain(space);
  p->set_linearInequalities(linear_v);
  p->set_v_h_0(12.5);
  p->set_d_h_0(14.0);
  p->set_f_t_prev(1800.0);
  p->set_f_b_prev(120.0);
  p->set_delta_s(space ? 1.3 : 1.0);
  p->set_vp_prediction(std::vector<double>(N + 1, 0.0));
  std::vector<double> vp(N + 1);
  for (int k = 0; k <= N; ++k) vp[k] = 13.0 + 0.2 * k;
  p->set_vp_prediction(vp);
  p->set_alpha_prediction(N + 1, 1.5); // degrees, non-zero to test the slope terms
  p->set_v_min_prediction(N + 1, -1.0);
  p->set_v_max_prediction(N + 1, 35.0);

  nlp::MaccNLP nlp(nlp::ProblemData::fromParameters(*p));
  const int n = nlp.numVariables(), m = nlp.numConstraints();

  std::mt19937 gen(seed);
  std::uniform_real_distribution<double> U(0.5, 1.5);
  std::vector<double> x(n);
  const nlp::Layout &L = nlp.layout();
  for (int k = 1; k <= N; ++k) {
    x[L.v(k)] = 12.0 * U(gen);
    x[L.d(k)] = 15.0 * U(gen);
    x[L.s1(k)] = 2.0 * U(gen);
  }
  for (int k = 0; k < N; ++k) {
    x[L.ft(k)] = 1500.0 * U(gen);
    x[L.fb(k)] = 300.0 * U(gen);
    x[L.s2(k)] = 40.0 * U(gen);
    x[L.s3(k)] = 20.0 * U(gen);
  }
  std::vector<double> lam(m);
  for (auto &l : lam) l = U(gen) - 1.0;
  const double sigma = 0.7;

  bool ok = true;
  auto report = [&](const char *what, double worst, double tol) {
    std::printf("  %-34s worst rel. error %.3e %s\n", what, worst, worst < tol ? "ok" : "FAIL");
    if (worst >= tol) ok = false;
  };
  std::printf("[%s] N=%d n=%d m=%d nnzJ=%d nnzH=%d\n", label, N, n, m, nlp.jacobianNnz(), nlp.hessianNnz());

  // ---- gradient ----------------------------------------------------------------
  std::vector<double> g(n), xp = x;
  nlp.gradient(x.data(), g.data());
  double worst = 0;
  for (int i = 0; i < n; ++i) {
    // The objective is a polynomial of degree 4, so the 5-point stencil is exact
    // up to round-off and a large step keeps the round-off small.
    const double h = 1e-2 * std::max(1.0, std::fabs(x[i]));
    auto f = [&](double dx) { xp[i] = x[i] + dx; return nlp.objective(xp.data()); };
    const double fd = (-f(2 * h) + 8 * f(h) - 8 * f(-h) + f(-2 * h)) / (12 * h);
    xp[i] = x[i];
    worst = std::max(worst, relErr(g[i], fd));
  }
  report("objective gradient", worst, 1e-6);

  // ---- Jacobian ----------------------------------------------------------------
  std::vector<int> ji(nlp.jacobianNnz()), jj(nlp.jacobianNnz());
  std::vector<double> jv(nlp.jacobianNnz());
  nlp.jacobianStructure(ji.data(), jj.data());
  nlp.jacobianValues(x.data(), jv.data());
  std::map<std::pair<int, int>, double> J;
  for (std::size_t t = 0; t < jv.size(); ++t) J[{ji[t], jj[t]}] += jv[t];
  worst = 0;
  double structural_miss = 0;
  std::vector<double> cp(m), cm(m);
  for (int j = 0; j < n; ++j) {
    const double h = 1e-6 * std::max(1.0, std::fabs(x[j]));
    xp[j] = x[j] + h; nlp.constraints(xp.data(), cp.data());
    xp[j] = x[j] - h; nlp.constraints(xp.data(), cm.data());
    xp[j] = x[j];
    for (int i = 0; i < m; ++i) {
      const double fd = (cp[i] - cm[i]) / (2 * h);
      auto it = J.find({i, j});
      const double an = (it == J.end()) ? 0.0 : it->second;
      if (it == J.end() && std::fabs(fd) > 1e-6) structural_miss = std::max(structural_miss, std::fabs(fd));
      worst = std::max(worst, relErr(an, fd));
    }
  }
  report("constraint Jacobian", worst, 1e-5);
  report("Jacobian structure (missing nnz)", structural_miss, 1e-6);

  // ---- Hessian of the Lagrangian ----------------------------------------------
  std::vector<int> hi(nlp.hessianNnz()), hj(nlp.hessianNnz());
  std::vector<double> hv(nlp.hessianNnz());
  nlp.hessianStructure(hi.data(), hj.data());
  nlp.hessianValues(x.data(), sigma, lam.data(), hv.data());
  std::map<std::pair<int, int>, double> H;
  for (std::size_t t = 0; t < hv.size(); ++t) {
    if (hi[t] < hj[t]) { std::printf("  Hessian entry above diagonal!\n"); ok = false; }
    H[{hi[t], hj[t]}] += hv[t];
  }
  // FD of the Lagrangian gradient
  auto lagGrad = [&](const std::vector<double> &xx, std::vector<double> &out) {
    std::vector<double> gf(n), jvv(nlp.jacobianNnz());
    nlp.gradient(xx.data(), gf.data());
    nlp.jacobianValues(xx.data(), jvv.data());
    out.assign(n, 0.0);
    for (int i = 0; i < n; ++i) out[i] = sigma * gf[i];
    for (std::size_t t = 0; t < jvv.size(); ++t) out[jj[t]] += lam[ji[t]] * jvv[t];
  };
  worst = 0; structural_miss = 0;
  std::vector<double> gp, gm;
  for (int j = 0; j < n; ++j) {
    const double h = 1e-6 * std::max(1.0, std::fabs(x[j]));
    xp[j] = x[j] + h; lagGrad(xp, gp);
    xp[j] = x[j] - h; lagGrad(xp, gm);
    xp[j] = x[j];
    for (int i = j; i < n; ++i) { // lower triangle only
      const double fd = (gp[i] - gm[i]) / (2 * h);
      auto it = H.find({i, j});
      const double an = (it == H.end()) ? 0.0 : it->second;
      if (it == H.end() && std::fabs(fd) > 1e-5) structural_miss = std::max(structural_miss, std::fabs(fd));
      worst = std::max(worst, relErr(an, fd));
    }
  }
  report("Lagrangian Hessian", worst, 1e-4);
  report("Hessian structure (missing nnz)", structural_miss, 1e-5);
  return ok;
}

} // namespace

int main() {
  bool ok = true;
  for (int N : {1, 3, 8}) {
    ok &= checkProblem("space domain, cubic v bounds", true, false, N, 1);
    ok &= checkProblem("time domain,  cubic v bounds", false, false, N, 2);
    ok &= checkProblem("space domain, linear v bounds", true, true, N, 3);
  }
  std::printf(ok ? "ALL NLP DERIVATIVE CHECKS PASSED\n" : "NLP DERIVATIVE CHECKS FAILED\n");
  return ok ? 0 : 1;
}
