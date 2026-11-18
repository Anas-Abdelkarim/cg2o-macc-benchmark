#ifndef EDGE_INEQ_V_H_MAX_H
#define EDGE_INEQ_V_H_MAX_H

#include "cg2o/core/base_fixed_sized_edge_ineq.h"
#include "macc/mpc/parameters.h"
#include "macc/fg/vertices.h"

namespace macc::fg {

class EdgeIneq_v_h_max
    : public cg2o::BaseFixedSizedEdgeIneq<1, double, Vertex_v_h> {
public:
  EIGEN_MAKE_ALIGNED_OPERATOR_NEW

  EdgeIneq_v_h_max(int k, std::shared_ptr<mpc::MPCParameters> param);
  void computeIneq() override;
  #if MPC_USE_NUMERICAL_JACOBIANS == 0
  void linearizeOplus() override; // optional
  #endif

  bool write(std::ostream &os) const override;
  bool read(std::istream &is) override;

private:
  int _k;
  std::shared_ptr<mpc::MPCParameters> _param;
  double _scaling_factor;
};

} // namespace macc::fg

#endif // EDGE_INEQ_V_H_MAX_H
