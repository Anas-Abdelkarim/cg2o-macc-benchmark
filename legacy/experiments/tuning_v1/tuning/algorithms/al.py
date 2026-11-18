"""Augmented-Lagrangian solver of cg2o (`al`). ISPD drives the plant and is the cost reference."""
from ..params import Float, Log, ParamSpace
from ..registry import register
from ..spec import AlgorithmSpec
from ..experiments.macc_closed_loop import quality
from ._cg2o_common import CG2O_COMMON

register(AlgorithmSpec(
    name="al",
    description="augmented Lagrangian (rho schedule, initial equality multipliers)",
    params=ParamSpace([
        Log("general_settings.rho_initial_eq", 0.01, 100.0, default=0.5, doc="initial penalty"),
        Log("general_settings.rho_max_eq", 1e2, 1e8, default=5e5, doc="maximum penalty"),
        Log("general_settings.rho_update_factor_eq", 1.5, 100.0, default=20.0, doc="penalty growth factor"),
        Float("general_settings.lagrange_multiplier_initial_eq", -10.0, 10.0, default=0.0),
        *CG2O_COMMON,
    ]),
    experiment="macc_closed_loop",
    setup=dict(target="al", driver="ispd", init="fixed", cases=(3, 15, 30)),
    # starting thresholds: AL need not reach the ISPD optimum exactly; tighten with --constraint gap_median<=... once the baseline is known
    constraints=quality(cost_gap=1e-2, stat="median", residual=None, fail=None),
    default_objective="iterations",
    notes="Thresholds are a starting point: check the baseline's cost gap in the report and set --constraint gap_median<=...."))
