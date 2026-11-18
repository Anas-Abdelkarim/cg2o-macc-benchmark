#ifndef EDGE_COST_BRAKE_H
#define EDGE_COST_BRAKE_H

#include "g2o/core/base_fixed_sized_edge.h"
#include "macc/mpc/parameters.h"
#include "macc/fg/vertices.h"

namespace macc::fg {

class EdgeCost_brake : public g2o::BaseFixedSizedEdge<1, double, Vertex_f_b> {
public:
  EIGEN_MAKE_ALIGNED_OPERATOR_NEW

  EdgeCost_brake(int k, std::shared_ptr<mpc::MPCParameters> param);

  void computeError() override;
  void linearizeOplus() override; // optional

  bool write(std::ostream &os) const override;
  bool read(std::istream &is) override;

private:
  int _k;
  std::shared_ptr<mpc::MPCParameters> _param;
};

} // namespace macc::fg

#endif // EDGE_COST_BRAKE_CHANGE_H
