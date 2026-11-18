"""Options of the cg2o optimizers that ISPD, BIPM and AL all use. Group "shared": for BIPM / AL they also change the ISPD
driver of the closed loop, so they are off by default there (enable with --groups main shared)."""
from ..params import Cat, Int, Log

CG2O_COMMON = [
    Int("general_settings.num_inner_iterations_max", 1, 20, default=10, group="shared",
        doc="inner (Gauss-Newton) iterations per outer iteration"),
    Log("cg2o.epsilon_convergence", 1e-5, 1e-1, default=1e-2, group="shared", doc="convergence tolerance of the solve"),
    Cat("cg2o.termination_criterion", [0, 1, 2], default=1, group="shared",
        doc="0 UpdateNorm, 1 NewtonDecrement, 2 GradientNorm"),
    Cat("cg2o.equality_regularization", [0.0, 1e-8, 1e-6], default=0.0, group="shared", doc="sigma of the KKT system"),
]
