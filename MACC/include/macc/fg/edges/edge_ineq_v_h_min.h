#ifndef EDGE_INEQ_V_H_MIN_H
#define EDGE_INEQ_V_H_MIN_H

#include "macc/mpc/parameters.h"
#include "macc/fg/vertices.h"
#include "cg2o/core/base_fixed_sized_edge_ineq.h"




namespace macc::fg {


class EdgeIneq_v_h_min : public cg2o::BaseFixedSizedEdgeIneq<1, double, Vertex_v_h> {
public:
    EIGEN_MAKE_ALIGNED_OPERATOR_NEW

    EdgeIneq_v_h_min(int k, std::shared_ptr<mpc::MPCParameters> param);
    void computeIneq() override;
    #if MPC_USE_NUMERICAL_JACOBIANS == 0
    void linearizeOplus() override; //optional
    #endif

    bool write(std::ostream& os) const override;
    bool read(std::istream& is) override;

private:
    int _k;
    std::shared_ptr<mpc::MPCParameters> _param;

};

} // namespace macc::fg

#endif  // EDGE_INEQ_V_H_MIN_H
