"""Tuning library for the MACC solvers.

Layers (details and "how to add ..." recipes in docs/TUNING.md):

    params.py        Param / ParamSpace      what can be tuned and in which range
    spec.py          AlgorithmSpec, Quality  one algorithm = parameters + how it is run + when a result is acceptable
    registry.py      register / get          algorithms register themselves (algorithms/<name>.py)
    runner.py        MaccRunner              one `macc_run` call -> RunStats (iterations, cost gap, residuals ...)
    evaluator.py     Evaluator               a parameter set -> Evaluation (all horizons in parallel, rejection rules)
    objectives.py    objective registry      Evaluation -> score (lower is better): iterations, paper, ...
    strategies/      search strategies       bayesian (Optuna TPE), coordinate descent, random
    study.py         Study                   baseline, bookkeeping, promotion to full runs, validation, reports
    plots.py         result plots
    cli.py           command line            `python3 experiments/tune.py ...`
"""
