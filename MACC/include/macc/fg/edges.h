#ifndef MACC_FG_EDGES_H_
#define MACC_FG_EDGES_H_

// Convenience header: every factor (edge) of the MACC factor graph.

// Cost factors
#include "macc/fg/edges/edge_cost_brake.h"
#include "macc/fg/edges/edge_cost_brake_change.h"
#include "macc/fg/edges/edge_cost_energy.h"
#include "macc/fg/edges/edge_cost_inner_distance.h"
#include "macc/fg/edges/edge_cost_traction_change.h"

// Equality factors (dynamics)
#include "macc/fg/edges/edge_dynamics_d_h.h"
#include "macc/fg/edges/edge_dynamics_v_h.h"

// Inequality factors
#include "macc/fg/edges/edge_ineq_d_h_max.h"
#include "macc/fg/edges/edge_ineq_d_h_min.h"
#include "macc/fg/edges/edge_ineq_f_b_change_limit.h"
#include "macc/fg/edges/edge_ineq_f_b_max.h"
#include "macc/fg/edges/edge_ineq_f_b_min.h"
#include "macc/fg/edges/edge_ineq_f_t_change_limit.h"
#include "macc/fg/edges/edge_ineq_f_t_max.h"
#include "macc/fg/edges/edge_ineq_f_t_min.h"
#include "macc/fg/edges/edge_ineq_v_h_max.h"
#include "macc/fg/edges/edge_ineq_v_h_min.h"

#endif // MACC_FG_EDGES_H_
