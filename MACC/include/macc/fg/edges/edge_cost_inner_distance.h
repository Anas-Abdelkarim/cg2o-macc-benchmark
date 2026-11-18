#ifndef EDGE_COST_INNER_DISTANCE_H
#define EDGE_COST_INNER_DISTANCE_H

#include "g2o/core/base_fixed_sized_edge.h"
#include "macc/mpc/parameters.h"
#include "macc/fg/vertices.h"

namespace macc::fg {

class EdgeCost_inner_distance
    : public g2o::BaseFixedSizedEdge<1, double, Vertex_slack_1> {
public:
  EIGEN_MAKE_ALIGNED_OPERATOR_NEW

  EdgeCost_inner_distance(int k, std::shared_ptr<mpc::MPCParameters> param);
  void computeError() override;
#if MPC_USE_NUMERICAL_JACOBIANS == 0
  void linearizeOplus() override;
#endif

  bool write(std::ostream &os) const override;
  bool read(std::istream &is) override;

private:
  int _k;
  std::shared_ptr<mpc::MPCParameters> _param;
};

} // namespace macc::fg

#endif // EDGE_COST_INNER_DISTANCE_H
