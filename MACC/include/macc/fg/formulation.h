#ifndef MACC_FG_FORMULATION_H_
#define MACC_FG_FORMULATION_H_

#include "macc/fg/edges.h"
#include "macc/fg/vertices.h"
#include "macc/mpc/parameters.h"
#include "macc/nlp/macc_nlp.hpp"

#include <g2o/core/optimizable_graph.h>
#include <g2o/core/sparse_optimizer.h>

#include <memory>
#include <vector>

namespace macc::fg {

// Builds the MACC factor graph (vertices + factors) inside a cg2o optimizer
// (ISPD, BIPM or AL). The plant simulation (vehicle model, sensor, predictor)
// lives in macc::mpc::ClosedLoopPlant, not here.
template <typename Optimizer> class MPCFormulation {
public:
  MPCFormulation(int N, std::shared_ptr<Optimizer> optimizer,
                 std::shared_ptr<mpc::MPCParameters> param);

  // Vertices
  void addVertex(int offset, int k);
  void addVertices(int k);
  void setVertexScalarEstimate(int id, double value);
  double getVertexScalarEstimate(int id);
  std::vector<double> getResults();
  // Decision vector in the layout of macc::nlp::MaccNLP (n = 7N).
  std::vector<double> getSolutionVector();
  double getForceInput(int k);
  double getVelocityDesired();
  double getAccelerationDesired(double v_h, double road_grad = 0.0);

  // Factors
  void addEdgeCost_brake_change(int k);
  void addEdgeCost_brake(int k);
  void addEdgeCost_energy(int k);
  void addEdgeCost_inner_distance(int k);
  void addEdgeCost_traction_change(int k);
  void addEdgeDynamics_v_h(int k);
  void addEdgeDynamics_d_h(int k);
  void addEdgeIneq_v_h_max(int k);
  void addEdgeIneq_v_h_min(int k);
  void addEdgeIneq_d_h_max(int k);
  void addEdgeIneq_d_h_min(int k);
  void addEdgeIneq_f_t_max(int k);
  void addEdgeIneq_f_t_min(int k);
  void addEdgeIneq_f_b_max(int k);
  void addEdgeIneq_f_b_min(int k);
  void addEdgeIneq_f_t_change_limit(int k);
  void addEdgeIneq_f_b_change_limit(int k);
  void addEdges(int k);

  void setN(int N);
  int getN() const;
  void setVLagrangianInitial(double vInitial);
  double getVLagrangianInitial();

  // Build the whole graph for the horizon N.
  void setupMPC();

  // Sum of the cost-factor chi^2 values at the current estimate.
  double computeCost();

  // Initial guesses
  bool setInitialGuess(bool reset_lagrange_multipliers = true); // feasible projection
  bool setFixedInitialGuess(double value);                      // constant value
  void computeOffsets();

protected:
  int _N;
  std::shared_ptr<Optimizer> _optimizer;
  std::shared_ptr<mpc::MPCParameters> _param;
  std::vector<double> _results;
  double _init_lagrange_multiplier = 0.0;
  double _replace_nan = 10.0; // value used instead of NaN estimates

  // Vertex-id offsets: id = offset + k
  int _offset_d_h = 0;
  int _offset_slack_1 = 0;
  int _offset_f_t = 0;
  int _offset_slack_2 = 0;
  int _offset_v_h = 0;
  int _offset_f_b = 0;
  int _offset_slack_3 = 0;
  int _offset_eqDynamics_v_h = 0; // Lagrange multipliers of the equality factors
  int _offset_eqDynamics_d_h = 0;

  std::vector<std::shared_ptr<g2o::OptimizableGraph::Vertex>> _vertices;
  std::vector<std::shared_ptr<g2o::OptimizableGraph::Edge>> _edges;
  std::vector<std::shared_ptr<g2o::OptimizableGraph::Edge>> _edges_cost;
};

} // namespace macc::fg

#include "macc/fg/formulation.hpp"

#endif // MACC_FG_FORMULATION_H_
