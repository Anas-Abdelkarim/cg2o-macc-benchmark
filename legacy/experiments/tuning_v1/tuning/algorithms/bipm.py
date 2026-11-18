"""Barrier IPM of ref. [6] of the paper (Fig. 2 / Table V). Strictly feasible start; ISPD drives the plant."""
from ..params import Float, Log
from ..registry import register
from ..spec import AlgorithmSpec
from ..experiments.macc_closed_loop import quality
from ..params import ParamSpace
from ._cg2o_common import CG2O_COMMON

register(AlgorithmSpec(
    name="bipm",
    description="barrier IPM (kappa schedule); objective 'paper' tries to match Table V at N = 30",
    params=ParamSpace([
        Log("bipm_settings.kappa_initial", 1e-3, 100.0, default=0.5, grid=(1e-3, 1e-2, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0),
            doc="initial barrier weight t_init (mu = 1/kappa)"),
        Log("bipm_settings.kappa_final", 100.0, 2e4, default=1500.0, grid=(300.0, 500.0, 1000.0, 1500.0, 3000.0, 5000.0, 1e4),
            doc="final barrier weight"),
        Log("bipm_settings.kappa_update_factor", 1.5, 50.0, default=8.0, grid=(2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0),
            doc="kappa is multiplied by this after every outer iteration (nu)"),
        Float("bipm_settings.lagrange_multiplier_initial_eq", -1000.0, 1000.0, default=0.0,
              grid=(-1000.0, -100.0, -10.0, 0.0, 10.0, 100.0, 1000.0),
              doc="initial equality multipliers (BIPM only; general_settings.lagrange_multiplier_initial_eq is shared)"),
        *CG2O_COMMON,
    ]),
    experiment="macc_closed_loop",
    setup=dict(target="bipm", driver="ispd", init="feasible", cases=(30,), paper_key="cg2o_bipm_feasible"),
    # BIPM stops at the iteration limit in some steps by design (also in the paper): judge the cost by the MEDIAN gap
    constraints=quality(cost_gap=1e-3, stat="median", residual=None, fail=None),
    default_objective="paper", promote_gain=0.10,
    notes="Screening at N = 30 only; promotion re-runs the whole cycle. Shared options also change the ISPD driver."))
