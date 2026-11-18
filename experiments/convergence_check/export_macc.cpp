// Local-convergence analysis of cg2o (ISPD-IPM) on the MACC closed loop: export of the final iterates.
//
// ANALYSIS ONLY. The solver is built and configured exactly like macc::backends::Cg2oController
// (MACC/src/backends/cg2o/cg2o_controller.cpp) and the closed loop is the one of macc_run with ISPD as
// driver. After every solve, at the final iterate, the tool reads from cg2o's graph
//   X (primal vertices), gamma (equality multiplier vertices), lambda and s (inequality edges), kappa,
// and from every edge its error and analytic Jacobian (cg2o's own linearizeOplus), and writes
//   H_GN = sum J_e^T Omega J_e, H_g = sum J_g^T diag(lambda/s) J_g, H_p = H_GN + H_g, J_h, J_g,
//   gradL = sum J_e^T Omega e + J_h^T gamma + J_g^T lambda (cg2o normalization: no factor 2),
//   HessL by central differences of gradL with gamma, lambda fixed (relative steps 1e-6, 1e-5, 1e-7),
//   split by factor type so that the omitted term E = HessL - H_GN can be attributed to factor types.
// The assembled Hessian of cg2o's block solver is compared with H_p on every `--assembled-every` problem.
// Nothing is written back into the solver; after the analysis every edge is linearized again at the
// final iterate with the optimizer's own workspace, as optimize() leaves it.
//
//   export_macc --config <accepted run>/runs/<..._N3>/config_resolved.yaml --out <dir> [--steps K]
//               [--reference <accepted run>/runs/<..._N3>/steps.csv] [--assembled-every 100]

#include "macc/core/config.hpp"
#include "macc/experiment/experiment.hpp"
#include "macc/fg/formulation.h"
#include "macc/mpc/closed_loop.hpp"
#include "macc/solvers/linear_solvers.hpp"

#include <cg2o/core/sparse_optimizer_ispd.h>
#include <cg2o/core/vertex_lagrange_multiplier.h>
#include <g2o/core/block_solver.h>
#include <g2o/core/jacobian_workspace.h>
#include <g2o/core/optimization_algorithm_gauss_newton.h>

#include <Eigen/Dense>
#include <cxxabi.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <streambuf>
#include <string>
#include <unordered_map>
#include <vector>

namespace fs = std::filesystem;
using Opt = cg2o::SparseOptimizerISPD;
using Mat = Eigen::MatrixXd;
using Vec = Eigen::VectorXd;

namespace {

// ---------------------------------------------------------------- solver setup (copy of cg2o_controller.cpp)
void configure(Opt &o, const macc::core::Config &cfg) {
  o.setVerbose(cfg.get<int>("general_settings.verbose", 0));
  o.setNumInnerIterationsMax(cfg.get<int>("general_settings.num_inner_iterations_max", 10));
  o.setAlphaBacktracking(cfg.get<double>("general_settings.alpha_backtracking", -1.0));
  o.setLagrangeMultiplierInitial(cfg.get<double>("general_settings.lagrange_multiplier_initial_eq", 0.0));
  o.setEqualityRegularization(cfg.get<double>("cg2o.equality_regularization", 0.0));
  if (cfg.has("cg2o.epsilon_convergence")) o.setEpsilonConvergence(cfg.get<double>("cg2o.epsilon_convergence"));
  const std::string p = "ispd_settings.";
  o.setStepSizeStrategy(cfg.get<int>(p + "step_size_strategy"));
  o.setIneqBacktrackingStepMin(cfg.get<double>(p + "ineq_backtracking_step_min"));
  o.setAuxBacktrackingStepMin(cfg.get<double>(p + "aux_backtracking_step_min"));
  o.setInitKappaStrategy(cfg.get<int>(p + "_init_kappa_strategy"));
  o.setKappaInitial(cfg.get<double>(p + "kappa_initial"));
  o.setUpdateKappaStrategy(cfg.get<int>(p + "update_kappa_strategy"));
  o.setKappaUpdateFactor(cfg.get<double>(p + "kappa_update_factor"));
  o.setKappaFinal(cfg.get<double>(p + "kappa_final"));
  o.setTau(cfg.get<double>(p + "tau"));
  o.setLimitKappaFinal(cfg.get<int>(p + "limit_kappa_final") != 0);
  o.setInitSlackStrategy(cfg.get<int>(p + "init_slack_strategy"));
  o.setSlackVariableInitialIneq(cfg.get<double>(p + "slack_variable_initial_ineq"));
  o.setInitLagrangeStrategy(cfg.get<int>(p + "init_lagrange_strategy"));
  o.setLagrangeMultiplierInitialIneq(cfg.get<double>(p + "lagrange_multiplier_initial_ineq"));
  o.setIneqPredictionParam(cfg.get<double>(p + "ineq_prediction_param"));
  o.setIneqPredictionStepStrategy(cfg.get<int>(p + "ineq_prediction_step_strategy"));
  o.setIneqPredictionStrategy(cfg.get<int>(p + "ineq_prediction_strategy"));
  o.setKeepAuxPositiveStrategy(cfg.get<int>(p + "keep_aux_positive_strategy"));
  o.setAuxScalingFactor(cfg.get<double>(p + "aux_scaling_factor"));
  o.setAuxCorrectionValue(cfg.get<double>(p + "aux_correction_value"));
}

class CoutSilencer { // same as the controller: ISPD prints an unconditional std::endl
public:
  CoutSilencer() { old_ = std::cout.rdbuf(&null_); }
  ~CoutSilencer() { std::cout.rdbuf(old_); }
private:
  struct NullBuf : std::streambuf { int overflow(int c) override { return c; } } null_;
  std::streambuf *old_ = nullptr;
};

std::string demangle(const char *n) {
  int st = 0;
  char *d = abi::__cxa_demangle(n, nullptr, nullptr, &st);
  std::string s = (st == 0 && d) ? d : n;
  std::free(d);
  auto c = s.rfind("::");
  return c == std::string::npos ? s : s.substr(c + 2);
}

// ---------------------------------------------------------------- binary record writer
// record := int32 count, then per array: int32 name_len, name, char dtype ('d'|'i'), int32 ndim,
//           int64 shape[ndim], data (little endian, C order)
class Record {
public:
  void d(const std::string &name, const std::vector<double> &v) { add(name, 'd', {(int64_t)v.size()}, v.data(), v.size() * 8); }
  void d(const std::string &name, const Vec &v) { add(name, 'd', {(int64_t)v.size()}, v.data(), v.size() * 8); }
  void i(const std::string &name, const std::vector<int32_t> &v) { add(name, 'i', {(int64_t)v.size()}, v.data(), v.size() * 4); }
  // dense symmetric/general matrix stored as triplets of its nonzeros
  void sparse(const std::string &name, const Mat &M, double drop = 0.0) {
    std::vector<int32_t> r, c;
    std::vector<double> v;
    for (int j = 0; j < M.cols(); ++j)
      for (int k = 0; k < M.rows(); ++k)
        if (std::abs(M(k, j)) > drop) { r.push_back(k); c.push_back(j); v.push_back(M(k, j)); }
    i(name + "/i", r);
    i(name + "/j", c);
    d(name + "/v", v);
    i(name + "/shape", {(int32_t)M.rows(), (int32_t)M.cols()});
  }
  void write(std::ostream &os) const {
    const int32_t n = static_cast<int32_t>(items_.size());
    os.write(reinterpret_cast<const char *>(&n), 4);
    os.write(buf_.data(), static_cast<std::streamsize>(buf_.size()));
  }
private:
  void add(const std::string &name, char t, std::vector<int64_t> shape, const void *data, std::size_t bytes) {
    auto put = [&](const void *p, std::size_t b) { buf_.append(static_cast<const char *>(p), b); };
    const int32_t len = static_cast<int32_t>(name.size()), nd = static_cast<int32_t>(shape.size());
    put(&len, 4); put(name.data(), name.size()); put(&t, 1); put(&nd, 4);
    put(shape.data(), shape.size() * 8); put(data, bytes);
    items_.push_back(name);
  }
  std::string buf_;
  std::vector<std::string> items_;
};

// ---------------------------------------------------------------- graph view at the final iterate
enum Kind { Cost = 0, Eq = 1, Ineq = 2 };

struct EdgeView {
  g2o::OptimizableGraph::Edge *e = nullptr;
  Kind kind = Cost;
  int type = 0;          // index into type names
  int row = 0;           // first row in h (Eq) or g (Ineq)
  int D = 0;             // constraint rows (Eq, Ineq) or error dimension (Cost)
  double *lambda = nullptr, *slack = nullptr; // Ineq
  std::vector<double> gamma;                  // Eq (copied, fixed during the analysis)
};

struct GraphView {
  std::vector<g2o::OptimizableGraph::Vertex *> primal; // free primal vertices (dimension 1 each in MACC)
  std::unordered_map<const g2o::HyperGraph::Vertex *, int> col; // primal vertex -> column
  std::vector<EdgeView> edges;
  std::unordered_map<const g2o::HyperGraph::Edge *, int> edge_index;
  std::vector<std::vector<int>> adjacent; // column -> edges touching it
  std::vector<std::string> type_names;
  std::vector<int> type_kind;
  int n = 0, m_eq = 0, m_in = 0;
};

GraphView buildView(Opt &opt) {
  GraphView G;
  std::unordered_map<std::string, int> type_id;
  // primal columns in Hessian order; multiplier vertices are excluded
  std::vector<g2o::OptimizableGraph::Vertex *> verts(opt.indexMapping().begin(), opt.indexMapping().end());
  std::sort(verts.begin(), verts.end(), [](auto *a, auto *b) { return a->hessianIndex() < b->hessianIndex(); });
  for (auto *v : verts) {
    if (v->fixed() || dynamic_cast<cg2o::VertexLagrangeMultiplier<1> *>(v)) continue;
    if (v->dimension() != 1) throw std::runtime_error("export_macc expects scalar primal vertices");
    G.col[v] = G.n++;
    G.primal.push_back(v);
  }
  std::unordered_map<const g2o::HyperGraph::Edge *, cg2o::IneqBlock> ineq;
  opt.forEachActiveIneqBlock([&](cg2o::IneqBlock &b) { ineq[b.edge] = b; });
  for (auto *he : opt.activeEdges()) {
    auto *e = static_cast<g2o::OptimizableGraph::Edge *>(he);
    EdgeView ev;
    ev.e = e;
    const std::string tn = demangle(typeid(*e).name());
    auto it = ineq.find(e);
    cg2o::VertexLagrangeMultiplier<1> *mult = nullptr;
    for (auto *v : e->vertices())
      if (auto *m = dynamic_cast<cg2o::VertexLagrangeMultiplier<1> *>(v)) mult = m;
    if (it != ineq.end()) {
      ev.kind = Ineq; ev.D = it->second.dimension; ev.lambda = it->second.multiplier; ev.slack = it->second.slack;
      ev.row = G.m_in; G.m_in += ev.D;
    } else if (mult) {
      ev.kind = Eq; ev.D = e->dimension() / 2; ev.row = G.m_eq; G.m_eq += ev.D;
      ev.gamma.assign(mult->estimate().data(), mult->estimate().data() + ev.D);
    } else {
      ev.kind = Cost; ev.D = e->dimension();
    }
    if (!type_id.count(tn)) {
      type_id[tn] = static_cast<int>(G.type_names.size());
      G.type_names.push_back(tn);
      G.type_kind.push_back(ev.kind);
    }
    ev.type = type_id[tn];
    G.edge_index[e] = static_cast<int>(G.edges.size());
    G.edges.push_back(ev);
  }
  G.adjacent.assign(G.n, {});
  for (std::size_t k = 0; k < G.edges.size(); ++k)
    for (auto *v : G.edges[k].e->vertices()) {
      auto c = G.col.find(v);
      if (c != G.col.end()) G.adjacent[c->second].push_back(static_cast<int>(k));
    }
  return G;
}

// Error and Jacobian of one edge at the current estimates. J has one column per primal column touched.
struct Lin {
  Vec err;
  std::vector<std::pair<int, Vec>> J; // (primal column, column of the Jacobian, length = edge dimension)
};

Lin linearize(const GraphView &G, const EdgeView &ev, g2o::JacobianWorkspace &ws) {
  ev.e->computeError();
  ev.e->linearizeOplus(ws);
  Lin L;
  const int dim = ev.e->dimension();
  L.err = Eigen::Map<const Vec>(ev.e->errorData(), dim);
  for (std::size_t i = 0; i < ev.e->vertices().size(); ++i) {
    auto c = G.col.find(ev.e->vertex(static_cast<int>(i)));
    if (c == G.col.end()) continue;
    L.J.emplace_back(c->second, Eigen::Map<const Vec>(ws.workspaceForVertex(static_cast<int>(i)), dim));
  }
  return L;
}

// contribution of one edge to gradL (cg2o normalization), as (column, value)
std::vector<std::pair<int, double>> gradContribution(const EdgeView &ev, const Lin &L) {
  std::vector<std::pair<int, double>> out;
  for (const auto &[c, Jc] : L.J) {
    double v = 0.0;
    if (ev.kind == Cost) {
      Eigen::Map<const Mat> Om(ev.e->informationData(), ev.D, ev.D);
      v = Jc.dot(Om * L.err);
    } else if (ev.kind == Eq) {
      for (int r = 0; r < ev.D; ++r) v += Jc(r) * ev.gamma[r];
    } else {
      for (int r = 0; r < ev.D; ++r) v += Jc(r) * ev.lambda[r];
    }
    out.emplace_back(c, v);
  }
  return out;
}

struct Analysis {
  Mat H_GN, H_g, J_h, J_g;
  Vec x, gamma, lambda, s, gradL, h, g;
  std::vector<Mat> hess_by_type;    // FD Hessian of gradL per factor type, step 1e-6
  std::vector<Mat> hgn_by_type;     // J^T Omega J per cost type
  Mat hessL[3];                     // total FD Hessian for relative steps 1e-6, 1e-5, 1e-7
  std::vector<int32_t> ineq_row_type, eq_row_type, col_vertex_type;
  std::vector<std::string> vertex_type_names;
  double grad_scale = 0.0;          // max over columns of the largest single term of gradL
};

Analysis analyze(Opt &opt, GraphView &G) {
  Analysis A;
  const int n = G.n, T = static_cast<int>(G.type_names.size());
  g2o::JacobianWorkspace ws;
  for (auto &ev : G.edges) ws.updateSize(ev.e);
  ws.allocate();

  A.H_GN = Mat::Zero(n, n); A.H_g = Mat::Zero(n, n);
  A.J_h = Mat::Zero(G.m_eq, n); A.J_g = Mat::Zero(G.m_in, n);
  A.gradL = Vec::Zero(n); A.h = Vec::Zero(G.m_eq); A.g = Vec::Zero(G.m_in);
  A.gamma = Vec::Zero(G.m_eq); A.lambda = Vec::Zero(G.m_in); A.s = Vec::Zero(G.m_in);
  A.hess_by_type.assign(T, Mat::Zero(n, n));
  A.hgn_by_type.assign(T, Mat::Zero(n, n));
  A.ineq_row_type.assign(G.m_in, 0); A.eq_row_type.assign(G.m_eq, 0);
  Vec maxterm = Vec::Zero(n);

  A.x.resize(n);
  std::unordered_map<std::string, int> vt;
  for (int c = 0; c < n; ++c) {
    auto *mv = dynamic_cast<macc::fg::VertexMPC<1> *>(G.primal[c]);
    if (!mv) throw std::runtime_error("unexpected primal vertex type");
    A.x(c) = mv->estimate();
    const std::string tn = demangle(typeid(*G.primal[c]).name());
    if (!vt.count(tn)) { vt[tn] = static_cast<int>(A.vertex_type_names.size()); A.vertex_type_names.push_back(tn); }
    A.col_vertex_type.push_back(vt[tn]);
  }

  for (auto &ev : G.edges) {
    const Lin L = linearize(G, ev, ws);
    for (const auto &[c, v] : gradContribution(ev, L)) { A.gradL(c) += v; maxterm(c) = std::max(maxterm(c), std::abs(v)); }
    if (ev.kind == Cost) {
      Eigen::Map<const Mat> Om(ev.e->informationData(), ev.D, ev.D);
      for (const auto &[a, Ja] : L.J)
        for (const auto &[b, Jb] : L.J) {
          const double v = Ja.dot(Om * Jb);
          A.H_GN(a, b) += v;
          A.hgn_by_type[ev.type](a, b) += v;
        }
    } else if (ev.kind == Eq) {
      for (int r = 0; r < ev.D; ++r) {
        A.h(ev.row + r) = L.err(r);
        A.gamma(ev.row + r) = ev.gamma[r];
        A.eq_row_type[ev.row + r] = ev.type;
        for (const auto &[c, Jc] : L.J) A.J_h(ev.row + r, c) += Jc(r);
      }
    } else {
      for (int r = 0; r < ev.D; ++r) {
        const int row = ev.row + r;
        A.g(row) = L.err(r);
        A.lambda(row) = ev.lambda[r];
        A.s(row) = ev.slack[r];
        A.ineq_row_type[row] = ev.type;
        for (const auto &[c, Jc] : L.J) A.J_g(row, c) += Jc(r);
      }
    }
  }
  A.H_g = A.J_g.transpose() * (A.lambda.array() / A.s.array()).matrix().asDiagonal() * A.J_g;
  A.grad_scale = maxterm.maxCoeff();

  // central differences of gradL along each primal coordinate; only the edges touching it change
  const double rel[3] = {1e-6, 1e-5, 1e-7};
  for (int si = 0; si < 3; ++si) A.hessL[si] = Mat::Zero(n, n);
  for (int c = 0; c < n; ++c) {
    auto *v = G.primal[c];
    for (int si = 0; si < 3; ++si) {
      const double hstep = rel[si] * std::max(1.0, std::abs(A.x(c)));
      std::vector<std::vector<std::pair<int, double>>> plus, minus;
      for (int sign : {+1, -1}) {
        v->push();
        const double d = sign * hstep;
        v->oplus(&d);
        auto &dst = sign > 0 ? plus : minus;
        for (int k : G.adjacent[c]) dst.push_back(gradContribution(G.edges[k], linearize(G, G.edges[k], ws)));
        v->pop();
      }
      for (std::size_t a = 0; a < G.adjacent[c].size(); ++a) {
        const int type = G.edges[G.adjacent[c][a]].type;
        for (std::size_t q = 0; q < plus[a].size(); ++q) {
          const double val = (plus[a][q].second - minus[a][q].second) / (2.0 * hstep);
          A.hessL[si](plus[a][q].first, c) += val;
          if (si == 0) A.hess_by_type[type](plus[a][q].first, c) += val;
        }
      }
    }
  }
  // restore every edge exactly as optimize() leaves it (errors and Jacobians at the final iterate,
  // Jacobians in the optimizer's own workspace)
  opt.computeActiveErrors();
  for (auto &ev : G.edges) ev.e->linearizeOplus(opt.jacobianWorkspace());
  return A;
}

// Hessian assembled by cg2o's block solver at the final iterate (octave file of g2o), primal block only.
double assembledDifference(Opt &opt, g2o::OptimizationAlgorithmGaussNewton &alg, const GraphView &G,
                           const Mat &H_p, const fs::path &tmp) {
  opt.computeActiveErrors();
  alg.solver().buildSystem();
  alg.solver().saveHessian(tmp.string());
  std::ifstream in(tmp);
  std::string line;
  std::unordered_map<int, int> hcol; // Hessian index -> primal column
  for (int c = 0; c < G.n; ++c) hcol[G.primal[c]->hessianIndex()] = c;
  Mat H = Mat::Zero(G.n, G.n);
  while (std::getline(in, line)) {
    if (line.empty() || line[0] == '#') continue;
    std::istringstream ls(line);
    int r, c; double v;
    if (!(ls >> r >> c >> v)) continue;
    auto a = hcol.find(r - 1), b = hcol.find(c - 1);
    if (a != hcol.end() && b != hcol.end()) H(a->second, b->second) = v;
  }
  return (H - H_p).cwiseAbs().maxCoeff() / std::max(1e-300, H_p.cwiseAbs().maxCoeff());
}

std::vector<std::map<std::string, std::string>> readCsv(const fs::path &p) {
  std::vector<std::map<std::string, std::string>> rows;
  std::ifstream in(p);
  std::string line, cell;
  std::vector<std::string> head;
  if (!std::getline(in, line)) return rows;
  for (std::istringstream hs(line); std::getline(hs, cell, ',');) head.push_back(cell);
  while (std::getline(in, line)) {
    std::map<std::string, std::string> r;
    std::istringstream ls(line);
    for (std::size_t i = 0; i < head.size() && std::getline(ls, cell, ','); ++i) r[head[i]] = cell;
    rows.push_back(std::move(r));
  }
  return rows;
}

} // namespace

int main(int argc, char **argv) {
  std::string config_path, out_dir, reference;
  int steps_limit = 0, assembled_every = 100;
  std::vector<std::string> overrides;
  for (int i = 1; i < argc; ++i) {
    const std::string a = argv[i];
    auto next = [&]() { if (i + 1 >= argc) { std::cerr << "missing value for " << a << "\n"; std::exit(2); } return std::string(argv[++i]); };
    if (a == "--config") config_path = next();
    else if (a == "--out") out_dir = next();
    else if (a == "--steps") steps_limit = std::stoi(next());
    else if (a == "--reference") reference = next();
    else if (a == "--assembled-every") assembled_every = std::stoi(next());
    else if (a == "--set") overrides.push_back(next());
    else { std::cerr << "unknown option " << a << "\n"; return 2; }
  }
  if (config_path.empty() || out_dir.empty()) {
    std::cerr << "usage: export_macc --config <config_resolved.yaml> --out <dir> [--steps K] [--reference steps.csv]"
                 " [--assembled-every K] [--set key=value]\n";
    return 2;
  }
  auto cfg = macc::core::Config::fromFile(config_path);
  for (auto &o : overrides) cfg.applyOverride(o);
  if (cfg.get<std::string>("mpc.init_mode", "fixed") != "fixed")
    throw std::runtime_error("the paper's ISPD runs use mpc.init_mode = fixed");

  // plant and parameters exactly as macc_run (experiment::buildSetup), but without building any controller
  macc::experiment::Setup setup;
  {
    auto c2 = cfg;
    c2.set("experiment.solvers", "[ispd]"); // buildSetup needs a solver list; its controller is discarded
    c2.set("experiment.driver", "ispd");
    setup = macc::experiment::buildSetup(c2);
    setup.controllers.clear();
  }
  auto param = setup.param;
  const int N = param->get_N();
  const int steps = steps_limit > 0 ? std::min(steps_limit, setup.steps) : setup.steps;
  const int max_iter = cfg.get<int>("mpc.number_of_iterations", 120);
  const double init_value = cfg.get<double>("mpc.init_value", 10.0);
  const int linear_id = macc::solvers::resolveLinearSolverId(cfg.get<std::string>("linear_solver.type", "14"));

  // ISPD controller, as Cg2oController<SparseOptimizerISPD>
  auto block = std::make_unique<g2o::BlockSolverX>(macc::solvers::makeLinearSolver(linear_id));
  auto alg = std::make_unique<g2o::OptimizationAlgorithmGaussNewton>(std::move(block));
  auto optimizer = std::make_shared<Opt>();
  auto formulation = std::make_unique<macc::fg::MPCFormulation<Opt>>(N, optimizer, param);
  optimizer->setAlgorithm(alg.get());
  configure(*optimizer, cfg);
  formulation->setupMPC();
  optimizer->setConvergenceCriterion(cfg.get<int>("cg2o.termination_criterion", 1));
  optimizer->initializeOptimization();

  std::vector<std::map<std::string, std::string>> ref;
  if (!reference.empty()) ref = readCsv(reference);

  fs::create_directories(out_dir);
  std::ofstream bin(fs::path(out_dir) / "matrices.bin", std::ios::binary);
  std::ofstream csv(fs::path(out_dir) / "problems.csv");
  csv << "k,N,iterations,converged,hit_limit,kappa,n,m_eq,m_in,u,ref_iterations,ref_u,stationarity_inf,"
         "gradL_scale,eq_inf,ineq_resid_inf,compl_resid_inf,fd_rel_5_vs_6,fd_rel_7_vs_6,fd_rel_E_5_vs_7,"
         "assembled_rel_diff\n";
  csv << std::setprecision(17);
  macc::mpc::ClosedLoopPlant plant(param);
  double u_prev = 0.0;
  int mismatches = 0;
  std::vector<std::string> type_names;
  for (int k = 0; k < steps; ++k) {
    plant.beginStep(k, u_prev);
    formulation->setFixedInitialGuess(init_value);
    int it;
    { CoutSilencer quiet; it = optimizer->optimize(max_iter); }
    const double u = formulation->getForceInput(0);
    const bool hit = it >= max_iter;
    const bool conv = optimizer->lastConverged();
    const double kappa = optimizer->lastKappa();

    GraphView G = buildView(*optimizer);
    Analysis A = analyze(*optimizer, G);
    if (type_names.empty()) type_names = G.type_names;
    else if (type_names != G.type_names) throw std::runtime_error("factor types changed between steps");

    const Mat H_p = A.H_GN + A.H_g;
    double assembled = std::numeric_limits<double>::quiet_NaN();
    if (assembled_every > 0 && k % assembled_every == 0)
      assembled = assembledDifference(*optimizer, *alg, G, H_p, fs::path(out_dir) / "assembled_tmp.txt");
    // FD consistency: total Hessian and E for the different steps
    auto sym = [](const Mat &M) { return Mat(0.5 * (M + M.transpose())); };
    const Mat H6 = sym(A.hessL[0]), H5 = sym(A.hessL[1]), H7 = sym(A.hessL[2]);
    const double nH = std::max(1e-300, H6.norm());
    const Mat E5 = H5 - A.H_GN, E7 = H7 - A.H_GN, E6 = H6 - A.H_GN;
    const double rel56 = (H5 - H6).norm() / nH, rel76 = (H7 - H6).norm() / nH;
    const double relE57 = (E5 - E7).norm() / std::max(1e-300, E6.norm());
    const Vec compl_r = (A.s.array() * A.lambda.array()).matrix() - Vec::Constant(A.s.size(), 1.0 / kappa);

    std::string ref_it = "", ref_u = "";
    if (k < static_cast<int>(ref.size())) {
      ref_it = ref[k]["ispd_iterations"]; ref_u = ref[k]["ispd_u"];
      if (!ref_it.empty() && std::stoi(ref_it) != it) ++mismatches;
    }
    csv << k << ',' << N << ',' << it << ',' << conv << ',' << hit << ',' << kappa << ',' << G.n << ',' << G.m_eq
        << ',' << G.m_in << ',' << u << ',' << ref_it << ',' << ref_u << ',' << A.gradL.cwiseAbs().maxCoeff() << ','
        << A.grad_scale << ',' << (G.m_eq ? A.h.cwiseAbs().maxCoeff() : 0.0) << ','
        << (A.g + A.s).cwiseAbs().maxCoeff() << ',' << compl_r.cwiseAbs().maxCoeff() << ',' << rel56 << ','
        << rel76 << ',' << relE57 << ',' << assembled << '\n';

    Record R;
    R.i("k", {k});
    R.d("kappa", std::vector<double>{kappa});
    R.d("x", A.x); R.d("gamma", A.gamma); R.d("lambda", A.lambda); R.d("s", A.s);
    R.d("gradL", A.gradL); R.d("h", A.h); R.d("g", A.g);
    R.sparse("H_GN", A.H_GN); R.sparse("H_g", A.H_g); R.sparse("H_p", H_p);
    R.sparse("J_h", A.J_h); R.sparse("J_g", A.J_g); R.sparse("HessL", A.hessL[0]);
    R.i("ineq_row_type", A.ineq_row_type); R.i("eq_row_type", A.eq_row_type);
    R.i("col_vertex_type", A.col_vertex_type);
    for (int t = 0; t < static_cast<int>(type_names.size()); ++t) {
      R.sparse("HessL_type/" + std::to_string(t), A.hess_by_type[t]);
      if (G.type_kind[t] == Cost) R.sparse("H_GN_type/" + std::to_string(t), A.hgn_by_type[t]);
    }
    if (k == 0) { // names of the factor and vertex types, once
      std::ofstream tf(fs::path(out_dir) / "types.txt");
      for (int t = 0; t < static_cast<int>(type_names.size()); ++t)
        tf << "factor " << t << ' ' << (G.type_kind[t] == Cost ? "cost" : G.type_kind[t] == Eq ? "eq" : "ineq") << ' ' << type_names[t] << '\n';
      for (std::size_t t = 0; t < A.vertex_type_names.size(); ++t) tf << "vertex " << t << ' ' << A.vertex_type_names[t] << '\n';
    }
    R.write(bin);

    u_prev = u;
    if ((k + 1) % 250 == 0 || k + 1 == steps)
      std::cerr << "  N=" << N << " step " << k + 1 << "/" << steps << "  it=" << it << "  mismatches vs reference: " << mismatches << std::endl;
  }
  fs::remove(fs::path(out_dir) / "assembled_tmp.txt");
  std::cerr << "done: " << steps << " problems, iteration mismatches vs reference: " << mismatches << std::endl;
  return 0;
}
