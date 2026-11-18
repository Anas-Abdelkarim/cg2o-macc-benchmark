#ifndef MACC_NLP_MACC_NLP_HPP
#define MACC_NLP_MACC_NLP_HPP

// Solver-independent definition of the MACC nonlinear program.
//
//   min  f(x)          (energy + brake + slack penalties, paper Eq. 37a / 44)
//   s.t. c(x)  = 0     (switched space/time dynamics, paper Eq. 37b, 37c)
//        g(x) <= 0     (14 inequality rows per stage, paper Eq. 37d-37n)
//
// This is *exactly* the problem that the cg2o factor graph (macc::fg edges)
// builds, written down with analytic first and second derivatives. It is used
//   * by the native IPOPT backend (no modelling-language interface in between),
//   * to evaluate cost and constraint violation of ANY solver's solution with
//     one common function, so all solvers are compared on the same numbers,
//   * by the finite-difference self test (macc_nlp_check).
//
// Decision vector (only the free variables, n = 7N); v_h[0] and d_h[0] are the
// measured initial state and therefore constants of the problem:
//   [ v_h[1..N] | d_h[1..N] | slack_1[1..N] | f_t[0..N-1] | f_b[0..N-1]
//     | slack_2[0..N-1] | slack_3[0..N-1] ]
// Constraint rows: 16 per stage k = 0..N-1, ordered as in macc::nlp::Row.

#include "macc/mpc/parameters.h"

#include <cstddef>
#include <vector>

namespace macc::nlp {

// Index helper for the decision vector.
struct Layout {
  int N = 0;
  explicit Layout(int horizon = 0) : N(horizon) {}
  int numVariables() const { return 7 * N; }
  int v(int k) const { return k - 1; }          // k = 1..N
  int d(int k) const { return N + k - 1; }      // k = 1..N
  int s1(int k) const { return 2 * N + k - 1; } // k = 1..N
  int ft(int k) const { return 3 * N + k; }     // k = 0..N-1
  int fb(int k) const { return 4 * N + k; }     // k = 0..N-1
  int s2(int k) const { return 5 * N + k; }     // k = 0..N-1
  int s3(int k) const { return 6 * N + k; }     // k = 0..N-1
};

// Rows of the constraint vector, per stage.
enum class Row : int {
  DynV = 0, // equality  v_h dynamics
  DynD,     // equality  d_h dynamics
  VMax,     // v_h[k+1]^3 - v_max^3            <= 0
  VMin,     // v_min^3 - v_h[k+1]^3            <= 0
  DMax,     // d_h[k+1] - (h_soft v_h[k+1] + slack_1[k+1]) <= 0
  DMin,     // (h_min v_h[k+1] + d_min) - d_h[k+1]         <= 0
  FtMax1,   // f_t - b4                         <= 0
  FtMax2,   // f_t - (a2 v_h[k] + b2)           <= 0
  FtMin,    // b3 - f_t                         <= 0
  FbMax1,   // f_b - (b_max + Regen_max)        <= 0
  FbMax2,   // f_b - (Brems_a1 v_h[k] + b_max + Brems_b1) <= 0
  FbMin,    // -f_b                             <= 0
  FtUp,     // f_t - f_t_prev - (dF + slack_2)  <= 0
  FtDown,   // f_t_prev - f_t - (dF + slack_2)  <= 0
  FbUp,     // f_b - f_b_prev - (dF + slack_3)  <= 0
  FbDown,   // f_b_prev - f_b - (dF + slack_3)  <= 0
  Count
};
constexpr int kRowsPerStage = static_cast<int>(Row::Count);

// All numbers the NLP depends on at one MPC step. Cheap to copy and refresh.
struct ProblemData {
  int N = 0;
  bool space_domain = true; // dynamics flavour used at this step
  bool linear_v_bounds = false; // v_h bounds linear instead of cubic

  // vehicle / model constants
  double c_a, c_r, g, m_eq, m_total, delta_s, delta_t;
  double Omega1, Omega6, BrakePenalty, BrakeChangePenalty, TractionChangePenalty;
  double eff_p01, eff_p02, eff_p10, eff_p11, eff_p20;
  double a2, b2, b3, b4, b_max, Regen_max, Brems_a1, Brems_b1;
  double h_min, h_soft, d_min, delta_f_t_max, delta_f_b_max;

  // state & previous inputs
  double v_h_0 = 0, d_h_0 = 0, f_t_prev = 0, f_b_prev = 0;

  // predictions, index 0..N (alpha_k, v_p) and 0..N (v_min/v_max)
  std::vector<double> v_p, alpha, v_min, v_max;

  // Copy everything from the parameter object (throws std::invalid_argument for
  // options the NLP does not implement, e.g. linearDynamics).
  // `require_predictions = false` is for building the problem *structure* before
  // the first MPC step has produced predictions: missing ones are zero-filled.
  static ProblemData fromParameters(const mpc::MPCParameters &p,
                                    bool require_predictions = true);
};

class MaccNLP {
public:
  explicit MaccNLP(const ProblemData &data);

  // Refresh the data of the current MPC step. The sparsity structure does not
  // depend on the data, so this is cheap (no re-analysis).
  void setData(const ProblemData &data);
  const ProblemData &data() const { return d_; }
  const Layout &layout() const { return L_; }

  int numVariables() const { return L_.numVariables(); }
  int numConstraints() const { return kRowsPerStage * L_.N; }
  bool isEquality(int row) const {
    int r = row % kRowsPerStage;
    return r == static_cast<int>(Row::DynV) || r == static_cast<int>(Row::DynD);
  }

  // constraint bounds: equalities [0,0], inequalities (-inf, 0]
  void constraintBounds(double *g_lower, double *g_upper,
                        double infinity = 1e19) const;

  double objective(const double *x) const;
  void gradient(const double *x, double *grad) const;
  void constraints(const double *x, double *g) const;

  int jacobianNnz() const { return static_cast<int>(jac_i_.size()); }
  void jacobianStructure(int *irow, int *jcol) const;
  void jacobianValues(const double *x, double *values) const;

  int hessianNnz() const { return static_cast<int>(hes_i_.size()); }
  void hessianStructure(int *irow, int *jcol) const; // lower triangle
  void hessianValues(const double *x, double sigma, const double *lambda,
                     double *values) const;

  // Feasibility measure of a point: infinity norm of the equality residual and
  // the largest positive inequality value.
  struct Violation {
    double eq_inf = 0.0;
    double ineq_inf = 0.0;
  };
  Violation violation(const double *x) const;

  // Input applied to the plant: u = f_t[0] - f_b[0].
  double inputForce(const double *x) const {
    return x[L_.ft(0)] - x[L_.fb(0)];
  }

  // The four rows per stage that involve ONE variable linearly (limits of f_t
  // and f_b). The native IPOPT backend can turn exactly these into variable bounds
  // (ipopt_settings.single_variable_rows_as_bounds).
  bool isSingleVariableRow(int row) const {
    switch (static_cast<Row>(row % kRowsPerStage)) {
    case Row::FtMax1: case Row::FtMin: case Row::FbMax1: case Row::FbMin: return true;
    default: return false;
    }
  }
  // Variable bounds equivalent to those rows (all other variables are free).
  void variableBounds(double *x_lower, double *x_upper, double infinity = 1e19) const;

  // Fixed initial guess used in the paper for all solvers except the barrier
  // IPM: every free variable set to `value`.
  std::vector<double> constantGuess(double value) const {
    return std::vector<double>(static_cast<std::size_t>(numVariables()), value);
  }

private:
  void buildStructure();

  ProblemData d_;
  Layout L_;
  std::vector<int> jac_i_, jac_j_;       // unique entries
  std::vector<int> jac_slot_;            // call order -> unique entry
  std::vector<int> hes_i_, hes_j_;
  std::vector<int> hes_slot_;
};

} // namespace macc::nlp

#endif // MACC_NLP_MACC_NLP_HPP
