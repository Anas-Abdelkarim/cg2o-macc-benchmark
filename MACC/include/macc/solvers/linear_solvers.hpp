#ifndef MACC_SOLVERS_LINEAR_SOLVERS_HPP
#define MACC_SOLVERS_LINEAR_SOLVERS_HPP

// Registry of the sparse/dense linear solvers that can be plugged into the
// g2o block solver used by cg2o. IDs 0-15 are the original MACC IDs (unchanged,
// so existing configs keep working); 16+ are the cg2o "dev" additions.

#include <g2o/core/block_solver.h>
#include <g2o/core/linear_solver.h>

#include <memory>
#include <string>
#include <vector>

namespace macc::solvers {

using BlockMatrix = g2o::BlockSolverX::PoseMatrixType;
using LinearSolverBase = g2o::LinearSolver<BlockMatrix>;

struct LinearSolverInfo {
  int id = -1;
  std::string key;         // short name usable on the command line ("umfpack")
  std::string name;        // human readable
  std::string family;      // library providing it
  bool needs_spd = false;  // Cholesky/LDL^T/CG type: needs a positive definite
                           // (or quasi-definite) system, i.e. no equality constraints
  bool available = false;  // compiled into this build
  std::string note;
};

// All known solvers (available or not).
const std::vector<LinearSolverInfo> &linearSolverCatalog();

// Accepts "14", "umfpack", "14:umfpack" (case insensitive). Returns -1 if unknown.
int resolveLinearSolverId(const std::string &id_or_key);

const LinearSolverInfo *findLinearSolver(int id);

// Throws std::runtime_error with a helpful message if `id` is unknown or was not
// compiled in.
std::unique_ptr<LinearSolverBase> makeLinearSolver(int id);

// Human readable table for --list-solvers.
std::string describeCatalog();

} // namespace macc::solvers

#endif // MACC_SOLVERS_LINEAR_SOLVERS_HPP
