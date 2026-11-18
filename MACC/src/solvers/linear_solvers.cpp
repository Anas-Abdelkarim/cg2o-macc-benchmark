#include "macc/solvers/linear_solvers.hpp"

#include <g2o/solvers/dense/linear_solver_dense.h>
#include <g2o/solvers/eigen/linear_solver_eigen.h>
#include <g2o/solvers/pcg/linear_solver_pcg.h>

#ifdef MACC_HAVE_G2O_CHOLMOD
#include <g2o/solvers/cholmod/linear_solver_cholmod.h>
#endif
#ifdef MACC_HAVE_G2O_CSPARSE
#include <g2o/solvers/csparse/linear_solver_csparse.h>
#endif
#ifdef MACC_HAVE_CG2O_EIGEN
#include <cg2o/solvers/eigen/linear_solver_eigen_bicgstab.h>
#include <cg2o/solvers/eigen/linear_solver_eigen_dense_full_lu.h>
#include <cg2o/solvers/eigen/linear_solver_eigen_dense_partial_lu.h>
#include <cg2o/solvers/eigen/linear_solver_eigen_dense_qr.h>
#include <cg2o/solvers/eigen/linear_solver_eigen_ldlt.h>
#include <cg2o/solvers/eigen/linear_solver_eigen_lscg.h>
#include <cg2o/solvers/eigen/linear_solver_eigen_lu.h>
#include <cg2o/solvers/eigen/linear_solver_eigen_qr.h>
#include <cg2o/solvers/eigen/linear_solver_eigen_svd.h>
#endif
#ifdef MACC_HAVE_CG2O_UMFPACK
#include <cg2o/solvers/umfpack/linear_solver_eigen_umfpack_lu.h>
#include <cg2o/solvers/umfpack/linear_solver_umfpack_fast.h>
#endif
#ifdef MACC_HAVE_CG2O_PARDISO
#include <cg2o/solvers/pardiso/linear_solver_eigen_pardiso_lu.h>
#endif
#ifdef MACC_HAVE_CG2O_CHOLMOD_FAST
#include <cg2o/solvers/cholmod/linear_solver_cholmod_fast.h>
#endif
#ifdef MACC_HAVE_CG2O_QDLDLT
#include <cg2o/solvers/eigen/linear_solver_eigen_qdldlt.h>
#endif

#include <algorithm>
#include <cctype>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace macc::solvers {

namespace {

std::string lower(std::string s) {
  std::transform(s.begin(), s.end(), s.begin(),
                 [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  return s;
}

std::vector<LinearSolverInfo> buildCatalog() {
  auto avail = [](bool compiled) { return compiled; };
  bool g2o_cholmod = false, g2o_csparse = false, cg2o_eigen = false,
       cg2o_umfpack = false, cg2o_pardiso = false, cg2o_cholmod_fast = false,
       cg2o_qdldlt = false;
#ifdef MACC_HAVE_G2O_CHOLMOD
  g2o_cholmod = true;
#endif
#ifdef MACC_HAVE_G2O_CSPARSE
  g2o_csparse = true;
#endif
#ifdef MACC_HAVE_CG2O_EIGEN
  cg2o_eigen = true;
#endif
#ifdef MACC_HAVE_CG2O_UMFPACK
  cg2o_umfpack = true;
#endif
#ifdef MACC_HAVE_CG2O_PARDISO
  cg2o_pardiso = true;
#endif
#ifdef MACC_HAVE_CG2O_CHOLMOD_FAST
  cg2o_cholmod_fast = true;
#endif
#ifdef MACC_HAVE_CG2O_QDLDLT
  cg2o_qdldlt = true;
#endif
  // clang-format off
  std::vector<LinearSolverInfo> c = {
    { 0, "cholmod",        "CHOLMOD",                    "g2o",  true,  avail(g2o_cholmod),       ""},
    { 1, "eigen_ldlt",     "Eigen SimplicialLDLT",       "cg2o", true,  avail(cg2o_eigen),        ""},
    { 2, "csparse",        "CSparse",                    "g2o",  true,  avail(g2o_csparse),       ""},
    { 3, "eigen",          "g2o Eigen sparse (LDLT)",    "g2o",  true,  true,                     ""},
    { 4, "dense",          "g2o dense (LDLT)",           "g2o",  true,  true,                     "O(n^3), only for small N"},
    { 5, "pcg",            "g2o PCG",                    "g2o",  true,  true,                     "iterative"},
    { 6, "eigen_lu",       "Eigen SparseLU",             "cg2o", false, avail(cg2o_eigen),        ""},
    { 7, "eigen_qr",       "Eigen SparseQR",             "cg2o", false, avail(cg2o_eigen),        "slow"},
    { 8, "eigen_svd",      "Eigen dense SVD",            "cg2o", false, avail(cg2o_eigen),        "very slow"},
    { 9, "eigen_bicgstab", "Eigen BiCGSTAB",             "cg2o", false, avail(cg2o_eigen),        "iterative"},
    {10, "eigen_dense_qr", "Eigen dense QR",             "cg2o", false, avail(cg2o_eigen),        "slow"},
    {11, "eigen_dense_full_lu",    "Eigen dense full-pivot LU",    "cg2o", false, avail(cg2o_eigen), "slow"},
    {12, "eigen_dense_partial_lu", "Eigen dense partial-pivot LU", "cg2o", false, avail(cg2o_eigen), "slow"},
    {13, "pardiso",        "PARDISO LU",                 "cg2o", false, avail(cg2o_pardiso),      "needs Intel MKL"},
    {14, "umfpack",        "UMFPACK LU",                 "cg2o", false, avail(cg2o_umfpack),      "reference of the linear-solver study"},
    {15, "eigen_lscg",     "Eigen LeastSquaresCG",       "cg2o", false, avail(cg2o_eigen),        "iterative"},
    {16, "cholmod_fast",   "CHOLMOD (cg2o fast variant)","cg2o", true,  avail(cg2o_cholmod_fast), "cg2o dev"},
    {17, "umfpack_fast",   "UMFPACK LU (cg2o fast variant)", "cg2o", false, avail(cg2o_umfpack),  "cg2o dev"},
    {18, "qdldlt",         "Eigen quasi-definite LDLT",  "cg2o", true,  avail(cg2o_qdldlt),       "own delta 1e-9 on zero diagonals, refinement (max 5) + LU fallback"},
    {19, "qdldlt_s8",      "Eigen QD-LDLT, delta 1e-8",  "cg2o", true, avail(cg2o_qdldlt), "own delta 1e-8, refinement (max 5) + LU fallback"},
    {20, "qdldlt_s7_ref",  "Eigen QD-LDLT, delta 1e-7, ref.", "cg2o", true, avail(cg2o_qdldlt), "own delta 1e-7, always refine (max 3) + LU fallback"},
    {21, "qdldlt_s11",     "Eigen QD-LDLT, delta 1e-11", "cg2o", true, avail(cg2o_qdldlt), "own delta 1e-11 (bias 100x smaller), refinement (max 5) + LU fallback"},
  };
  // clang-format on
  for (auto &s : c) {
    if (!s.available) {
      if (s.id == 0 || s.id == 2) s.note = "g2o built without CHOLMOD/CSparse";
      else if (s.id == 13) s.note = "cg2o built without PARDISO (needs Intel MKL)";
      else s.note = "not compiled into this build";
    }
  }
  return c;
}

} // namespace

const std::vector<LinearSolverInfo> &linearSolverCatalog() {
  static const std::vector<LinearSolverInfo> catalog = buildCatalog();
  return catalog;
}

const LinearSolverInfo *findLinearSolver(int id) {
  for (const auto &s : linearSolverCatalog())
    if (s.id == id) return &s;
  return nullptr;
}

int resolveLinearSolverId(const std::string &text) {
  std::string t = lower(text);
  const auto colon = t.find(':');
  if (colon != std::string::npos) t = t.substr(0, colon);
  if (!t.empty() && std::all_of(t.begin(), t.end(), [](unsigned char c) { return std::isdigit(c); }))
    return findLinearSolver(std::stoi(t)) ? std::stoi(t) : -1;
  for (const auto &s : linearSolverCatalog())
    if (lower(s.key) == t) return s.id;
  return -1;
}

std::unique_ptr<LinearSolverBase> makeLinearSolver(int id) {
  using M = BlockMatrix;
  const LinearSolverInfo *info = findLinearSolver(id);
  if (!info)
    throw std::runtime_error("Unknown linear solver id " + std::to_string(id) +
                             "; run 'macc_run --list-solvers'");
  if (!info->available)
    throw std::runtime_error("Linear solver " + std::to_string(id) + " (" + info->name +
                             ") is not available in this build: " + info->note);
  switch (id) {
#ifdef MACC_HAVE_G2O_CHOLMOD
  case 0: return std::make_unique<g2o::LinearSolverCholmod<M>>();
#endif
#ifdef MACC_HAVE_G2O_CSPARSE
  case 2: return std::make_unique<g2o::LinearSolverCSparse<M>>();
#endif
  case 3: return std::make_unique<g2o::LinearSolverEigen<M>>();
  case 4: return std::make_unique<g2o::LinearSolverDense<M>>();
  case 5: return std::make_unique<g2o::LinearSolverPCG<M>>();
#ifdef MACC_HAVE_CG2O_EIGEN
  case 1: return std::make_unique<cg2o::LinearSolverEigenLDLT<M>>();
  case 6: return std::make_unique<cg2o::LinearSolverEigenLU<M>>();
  case 7: return std::make_unique<cg2o::LinearSolverEigenQR<M>>();
  case 8: return std::make_unique<cg2o::LinearSolverEigenSVD<M>>();
  case 9: return std::make_unique<cg2o::LinearSolverEigenBiCGSTAB<M>>();
  case 10: return std::make_unique<cg2o::LinearSolverEigenDenseQR<M>>();
  case 11: return std::make_unique<cg2o::LinearSolverEigenDenseFullLU<M>>();
  case 12: return std::make_unique<cg2o::LinearSolverEigenDensePartialLU<M>>();
  case 15: return std::make_unique<cg2o::LinearSolverEigenLSCG<M>>();
#endif
#ifdef MACC_HAVE_CG2O_PARDISO
  case 13: return std::make_unique<cg2o::LinearSolverEigenPardisoLU<M>>();
#endif
#ifdef MACC_HAVE_CG2O_UMFPACK
  case 14: return std::make_unique<cg2o::LinearSolverEigenUmfPackLU<M>>();
  case 17: return std::make_unique<cg2o::LinearSolverUmfpackFast<M>>();
#endif
#ifdef MACC_HAVE_CG2O_CHOLMOD_FAST
  case 16: return std::make_unique<cg2o::LinearSolverCholmodFast<M>>();
#endif
#ifdef MACC_HAVE_CG2O_QDLDLT
  case 18: return std::make_unique<cg2o::LinearSolverEigenQDLDLT<M>>();
  case 19: return std::make_unique<cg2o::LinearSolverEigenQDLDLT<M>>(1e-8, false);
  case 20: return std::make_unique<cg2o::LinearSolverEigenQDLDLT<M>>(1e-7, true, 3);
  // delta 1e-11: the -delta bias lies in nearly singular directions of the KKT matrix that the residual does not see,
  // so refinement cannot remove it; it is proportional to delta (N = 50: 1e-3 -> 1e-5 off UMFPACK's step)
  case 21: return std::make_unique<cg2o::LinearSolverEigenQDLDLT<M>>(1e-11, false, 5);
#endif
  default: break;
  }
  throw std::runtime_error("Linear solver " + std::to_string(id) + " is not compiled in");
}

std::string describeCatalog() {
  std::ostringstream os;
  os << std::left << std::setw(4) << "ID" << std::setw(24) << "key" << std::setw(34) << "name"
     << std::setw(6) << "lib" << std::setw(10) << "SPD-only" << std::setw(11) << "available"
     << "note\n";
  for (const auto &s : linearSolverCatalog())
    os << std::left << std::setw(4) << s.id << std::setw(24) << s.key << std::setw(34) << s.name
       << std::setw(6) << s.family << std::setw(10) << (s.needs_spd ? "yes" : "no")
       << std::setw(11) << (s.available ? "yes" : "NO") << s.note << "\n";
  return os.str();
}

} // namespace macc::solvers
