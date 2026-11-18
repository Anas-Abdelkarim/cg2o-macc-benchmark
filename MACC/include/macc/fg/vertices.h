#ifndef MACC_FG_VERTICES_H_
#define MACC_FG_VERTICES_H_

#include <Eigen/Core>
#include <g2o/core/base_vertex.h>

namespace macc::fg {

// Traits for defining the Estimate type
template <int D> struct EstimateTraits {
  using Type = Eigen::Matrix<double, D, 1>;
};

// Specialization for D = 1
template <> struct EstimateTraits<1> {
  using Type = double;
};

// Generic MPC vertex of dimension D.
template <int D>
class VertexMPC : public g2o::BaseVertex<D, typename EstimateTraits<D>::Type> {
public:
  EIGEN_MAKE_ALIGNED_OPERATOR_NEW

  using Base = g2o::BaseVertex<D, typename EstimateTraits<D>::Type>;
  using EstimateType = typename EstimateTraits<D>::Type;

  void setToOriginImpl() override;
  void oplusImpl(const double *update) override;
  bool write(std::ostream &os) const override;
  bool read(std::istream &is) override;
};

} // namespace macc::fg

#include "macc/fg/vertices.hpp"

namespace macc::fg {

// Scalar vertex types. All decision variables of the MACC problem are scalars;
// the distinct types make the edge definitions self-documenting.
class Vertex_scalar : public VertexMPC<1> {};  // generic 1-D vertex
class Vertex_v_h : public VertexMPC<1> {};     // host velocity
class Vertex_d_h : public VertexMPC<1> {};     // inter-vehicle distance
class Vertex_f_t : public VertexMPC<1> {};     // traction force
class Vertex_f_b : public VertexMPC<1> {};     // braking force
class Vertex_slack_1 : public VertexMPC<1> {}; // slack: soft distance tracking
class Vertex_slack_2 : public VertexMPC<1> {}; // slack: traction-force rate
class Vertex_slack_3 : public VertexMPC<1> {}; // slack: braking-force rate

} // namespace macc::fg

#endif // MACC_FG_VERTICES_H_
