#ifndef EDGE_DYNAMICS_D_H_H
#define EDGE_DYNAMICS_D_H_H

#include "cg2o/core/base_fixed_sized_edge_eq.h"
#include "macc/mpc/parameters.h"
#include "macc/fg/vertices.h"

namespace macc::fg {

class EdgeDynamics_d_h
    : public cg2o::BaseFixedSizedEdgeEq<1, double, Vertex_d_h, Vertex_d_h,
                                       Vertex_v_h, Vertex_v_h> {
public:
  EIGEN_MAKE_ALIGNED_OPERATOR_NEW

  EdgeDynamics_d_h(int k, std::shared_ptr<mpc::MPCParameters> param);
  void computeEq() override;
#if MPC_USE_NUMERICAL_JACOBIANS == 0
  void linearizeOplus() override; // optional
#endif

  bool write(std::ostream &os) const override;
  bool read(std::istream &is) override;

private:
  int _k;
  std::shared_ptr<mpc::MPCParameters> _param;
};

} // namespace macc::fg

#endif // EDGE_DYNAMICS_D_H_H
