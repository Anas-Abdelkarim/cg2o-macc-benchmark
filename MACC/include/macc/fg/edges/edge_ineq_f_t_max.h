#ifndef EDGE_INEQ_f_t_max_H
#define EDGE_INEQ_f_t_max_H

#include "cg2o/core/base_fixed_sized_edge_ineq.h"
#include "macc/mpc/parameters.h"
#include "macc/fg/vertices.h"

namespace macc::fg {

class EdgeIneq_f_t_max
    : public cg2o::BaseFixedSizedEdgeIneq<2, double, Vertex_f_t, Vertex_v_h> {
public:
  EIGEN_MAKE_ALIGNED_OPERATOR_NEW

  EdgeIneq_f_t_max(int k, std::shared_ptr<mpc::MPCParameters> param);
  void computeIneq() override;
#if MPC_USE_NUMERICAL_JACOBIANS == 0
  void linearizeOplus() override; // optional
#endif

  bool write(std::ostream &os) const override;
  bool read(std::istream &is) override;

private:
  int _k;
  std::shared_ptr<mpc::MPCParameters> _param;
  std::vector<double> _scaling_factor;
};

} // namespace macc::fg

#endif // EDGE_INEQ_f_t_max2_H
