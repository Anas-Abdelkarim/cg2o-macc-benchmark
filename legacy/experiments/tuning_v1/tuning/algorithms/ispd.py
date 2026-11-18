"""ISPD-IPM, the proposed solver (Table IV). IPOPT (warm start) drives the plant and is the cost reference, so the
trajectory does not depend on the ISPD candidate."""
from dataclasses import replace

from ..params import Cat, Float, Log, ParamSpace
from ..registry import register
from ..spec import AlgorithmSpec
from ..experiments.macc_closed_loop import quality
from ._cg2o_common import CG2O_COMMON

P = "ispd_settings."
register(AlgorithmSpec(
    name="ispd",
    description="ISPD-IPM (kappa schedule, step sizes, slack / multiplier initialisation, prediction)",
    params=ParamSpace([
        Cat(P + "step_size_strategy", [0, 1, 2, 3], default=0, doc="0 min(ineq, aux), 1 average, 2 ineq, 3 aux"),
        Float(P + "ineq_backtracking_step_min", 0.05, 1.0, default=1.0, doc="zeta_ineq^min"),
        Float(P + "aux_backtracking_step_min", 0.05, 1.0, default=0.8, doc="zeta_aux^min"),
        Log(P + "kappa_initial", 1e-4, 10.0, default=1e-3, doc="kappa_0"),
        Cat(P + "update_kappa_strategy", [0, 1, 2, 3], default=0, doc="0 t>=t_memory, 1 t>=kappa_initial, 2 duality gap, 3 fixed nu"),
        Log(P + "kappa_update_factor", 1.5, 100.0, default=15.0, doc="nu"),
        Log(P + "kappa_final", 100.0, 1e5, default=1500.0, doc="final barrier weight"),
        Float(P + "tau", 1.01, 4.0, default=1.4),
        Cat(P + "limit_kappa_final", [0, 1], default=1),
        Log(P + "slack_variable_initial_ineq", 0.1, 1000.0, default=10.0, doc="s_pos"),
        Log(P + "lagrange_multiplier_initial_ineq", 0.1, 1000.0, default=10.0, doc="lambda_pos"),
        Float(P + "ineq_prediction_param", 0.1, 2.0, default=1.0, doc="zeta_pred"),
        Float(P + "aux_scaling_factor", 0.01, 0.9, default=0.2, doc="beta"),
        Log(P + "aux_correction_value", 0.1, 10.0, default=1.0),
        Log(P + "feas_tol", 1e-6, 1e-1, default=1e-3),
        *[replace(p, group="main") for p in CG2O_COMMON],     # ISPD owns these options: tune them by default
    ]),
    experiment="macc_closed_loop",
    setup=dict(target="ispd", driver="ipopt_warm", init="fixed", cases=(3, 15, 30), paper_key="cg2o_ispd_fixed"),
    constraints=quality(cost_gap=1e-4, stat="mean", residual=1e-3, fail=0.02),
    default_objective="iterations",
    notes="Reference solver: ipopt_warm (same NLP at every step). The paper numbers of ISPD with initial guess 10 are in "
          "cg2o_ispd_fixed."))
