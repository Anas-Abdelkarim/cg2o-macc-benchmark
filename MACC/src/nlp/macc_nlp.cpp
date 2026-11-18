#include "macc/nlp/macc_nlp.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace macc::nlp {

MaccNLP::MaccNLP(const ProblemData &data) : d_(data), L_(data.N) {
  buildStructure();
}

void MaccNLP::setData(const ProblemData &data) {
  if (data.N != d_.N)
    throw std::invalid_argument("MaccNLP::setData: horizon changed");
  d_ = data;
}

void MaccNLP::constraintBounds(double *gl, double *gu, double inf) const {
  for (int i = 0; i < numConstraints(); ++i) {
    if (isEquality(i)) {
      gl[i] = 0.0;
      gu[i] = 0.0;
    } else {
      gl[i] = -inf;
      gu[i] = 0.0;
    }
  }
}

void MaccNLP::variableBounds(double *xl, double *xu, double inf) const {
  for (int i = 0; i < numVariables(); ++i) {
    xl[i] = -inf;
    xu[i] = inf;
  }
  for (int k = 0; k < L_.N; ++k) {
    xl[L_.ft(k)] = d_.b3;
    xu[L_.ft(k)] = d_.b4;
    xl[L_.fb(k)] = 0.0;
    xu[L_.fb(k)] = d_.b_max + d_.Regen_max;
  }
}

MaccNLP::Violation MaccNLP::violation(const double *x) const {
  std::vector<double> g(static_cast<std::size_t>(numConstraints()));
  constraints(x, g.data());
  Violation v;
  for (int i = 0; i < numConstraints(); ++i) {
    if (isEquality(i))
      v.eq_inf = std::max(v.eq_inf, std::fabs(g[static_cast<std::size_t>(i)]));
    else
      v.ineq_inf = std::max(v.ineq_inf, g[static_cast<std::size_t>(i)]);
  }
  return v;
}

} // namespace macc::nlp
