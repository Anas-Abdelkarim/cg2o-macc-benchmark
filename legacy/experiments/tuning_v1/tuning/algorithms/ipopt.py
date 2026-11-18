"""Native IPOPT backend (C++ TNLP). Two algorithms are registered with the same parameters:
    ipopt        cold start (initial guess 10 at every step, the paper's protocol)
    ipopt_warm   every solve starts from the previous solution (reproduces Table VI)
ISPD drives the plant, so IPOPT solves the same NLPs as in the experiments and is scored against the ISPD cost.

To add an IPOPT option: one line in OPTIONS below (name, kind, low, high, default[, explicit grid]).
"""
from dataclasses import replace

from ..params import Cat, Float, Int, Log, OneMinusLog, ParamSpace
from ..registry import register
from ..spec import AlgorithmSpec
from ..experiments.macc_closed_loop import quality

PREFIX = "ipopt_settings.options."

# name, kind, low/high or choices, IPOPT 3.14 default [, grid used by coordinate descent] [, optional]
OPTIONS = [
    # --- termination (the stopping test is tol AND constr_viol_tol AND dual_inf_tol AND compl_inf_tol)
    Log(PREFIX + "tol", 1e-6, 1e-2, default=1e-8, grid=(1e-2, 1e-3, 1e-4, 1e-5, 1e-6)),
    Log(PREFIX + "constr_viol_tol", 1e-5, 1e-2, default=1e-4, grid=(1e-5, 1e-4, 1e-3)),
    Log(PREFIX + "compl_inf_tol", 1e-5, 1e-1, default=1e-4, grid=(1e-4, 1e-3, 1e-2)),
    Log(PREFIX + "dual_inf_tol", 1.0, 1e4, default=1.0, grid=(1.0, 1e2, 1e4)),
    Log(PREFIX + "acceptable_tol", 1e-8, 1e-1, default=1e-6, grid=(1e-6, 1e-4, 1e-3, 1e-2)),
    Int(PREFIX + "acceptable_iter", 0, 15, default=15, grid=(15, 5, 2, 1)),
    # --- barrier parameter
    Cat(PREFIX + "mu_strategy", ["monotone", "adaptive"], default="monotone"),
    Cat(PREFIX + "adaptive_mu_globalization", ["obj-constr-filter", "kkt-error", "never-monotone-mode"],
        default="obj-constr-filter"),
    Cat(PREFIX + "mu_oracle", ["quality-function", "probing", "loqo"], default="quality-function"),
    Log(PREFIX + "mu_init", 1e-4, 1e3, default=0.1, grid=(1e-3, 1e-2, 0.1, 1.0, 10.0, 100.0, 1000.0)),
    # mu_min: when unset IPOPT computes 0.5 * min(tol, compl_inf_tol) / (barrier_tol_factor + 1), so "unset" is a value
    Log(PREFIX + "mu_min", 1e-11, 1e-4, default=1e-11, grid=(1e-11, 1e-9, 1e-7), optional=True),
    Log(PREFIX + "barrier_tol_factor", 1.0, 100.0, default=10.0, grid=(1, 3, 10, 30, 100)),
    Float(PREFIX + "mu_linear_decrease_factor", 0.02, 0.8, default=0.2, grid=(0.05, 0.1, 0.2, 0.5)),
    Float(PREFIX + "mu_superlinear_decrease_power", 1.1, 1.95, default=1.5, grid=(1.2, 1.5, 1.8)),
    OneMinusLog(PREFIX + "tau_min", 1e-4, 1e-1, default=0.99, grid=(0.9, 0.99, 0.999)),
    Log(PREFIX + "kappa_sigma", 1e2, 1e12, default=1e10, grid=(1e10, 1e4, 1e2)),
    # --- initialisation
    Log(PREFIX + "bound_push", 1e-6, 1.0, default=0.01, grid=(1e-6, 1e-4, 1e-2, 1e-1, 1.0)),
    Log(PREFIX + "bound_frac", 1e-6, 0.5, default=0.01, grid=(1e-6, 1e-4, 1e-2, 1e-1, 0.5)),
    Log(PREFIX + "slack_bound_push", 1e-6, 1.0, default=0.01, grid=(1e-4, 1e-2, 1e-1, 1.0)),
    Log(PREFIX + "slack_bound_frac", 1e-6, 0.5, default=0.01, grid=(1e-4, 1e-2, 1e-1, 0.5)),
    Cat(PREFIX + "bound_mult_init_method", ["constant", "mu-based"], default="constant"),
    Log(PREFIX + "bound_mult_init_val", 1e-3, 1e3, default=1.0, grid=(1e-2, 1.0, 1e2)),
    # constr_mult_init_max: setting it explicitly to its default 1000 changes the result, so "unset" is a value
    Cat(PREFIX + "constr_mult_init_max", [0.0, 1.0, 10.0, 100.0, 1000.0, 10000.0], default=1000.0, optional=True),
    Cat(PREFIX + "least_square_init_duals", ["no", "yes"], default="no"),
    # --- scaling
    Cat(PREFIX + "nlp_scaling_method", ["none", "gradient-based", "equilibration-based"], default="gradient-based"),
    Log(PREFIX + "nlp_scaling_max_gradient", 1.0, 1e4, default=100.0, grid=(10.0, 100.0, 1000.0)),
    # --- line search / step computation
    Cat(PREFIX + "line_search_method", ["filter", "penalty"], default="filter"),
    Cat(PREFIX + "alpha_for_y", ["primal", "bound-mult", "min", "max", "full", "safer-min-dual-infeas"], default="primal"),
    Float(PREFIX + "alpha_red_factor", 0.1, 0.9, default=0.5, grid=(0.3, 0.5, 0.8)),
    Int(PREFIX + "max_soc", 0, 6, default=4, grid=(0, 2, 4)),
    Cat(PREFIX + "corrector_type", ["none", "affine", "primal-dual"], default="none"),
    Int(PREFIX + "watchdog_shortened_iter_trigger", 0, 20, default=10, grid=(0, 10)),
    Cat(PREFIX + "accept_every_trial_step", ["no", "yes"], default="no"),
    Cat(PREFIX + "mehrotra_algorithm", ["no", "yes"], default="no"),
    Cat(PREFIX + "fast_step_computation", ["no", "yes"], default="no"),
    Int(PREFIX + "min_refinement_steps", 0, 2, default=1, grid=(0, 1)),
    Int(PREFIX + "max_refinement_steps", 1, 10, default=10, grid=(3, 10)),
    Float(PREFIX + "required_infeasibility_reduction", 0.01, 0.99, default=0.9, grid=(0.1, 0.5, 0.9)),
    Log(PREFIX + "theta_max_fact", 10.0, 1e8, default=1e4, grid=(1e2, 1e4, 1e6)),
    Log(PREFIX + "obj_max_inc", 1.5, 100.0, default=5.0, grid=(5.0, 50.0)),
    Cat(PREFIX + "recalc_y", ["no", "yes"], default="no"),
    Cat(PREFIX + "constraint_violation_norm_type", ["1-norm", "2-norm", "max-norm"], default="1-norm"),
    Log(PREFIX + "first_hessian_perturbation", 1e-8, 1.0, default=1e-4, grid=(1e-6, 1e-4, 1e-2)),
    Log(PREFIX + "jacobian_regularization_value", 1e-12, 1e-4, default=1e-8, grid=(1e-10, 1e-8, 1e-6)),
]
# Not tuned on purpose: print_level, sb (output), linear_solver (use the ipopt-linear-solvers preset), max_iter (= --max-iter),
# hessian_approximation (exact derivatives are part of the formulation), linear_system_scaling (default mc19 needs HSL).

_cold = register(AlgorithmSpec(
    name="ipopt",
    description="native IPOPT, cold start (initial guess 10 at every step)",
    params=ParamSpace(OPTIONS),
    experiment="macc_closed_loop",
    setup=dict(target="ipopt", driver="ispd", init="fixed", cases=(3, 15, 30), paper_key="ipopt_fixed"),
    constraints=quality(cost_gap=1e-4, stat="mean", residual=1e-4, fail=0.02),
    default_objective="iterations",
    notes="Solutions must stay as good as ISPD's (cost gap, residuals), so a faster setting cannot come from a loose solve."))
register(replace(_cold, name="ipopt_warm", setup={**_cold.setup, "target": "ipopt_warm"},
                 description="native IPOPT, every solve starts from the previous solution (primal only)"))
