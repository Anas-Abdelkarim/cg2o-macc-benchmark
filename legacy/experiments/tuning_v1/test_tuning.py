#!/usr/bin/env python3
"""Unit tests of the tuning library (no macc_run needed):  python3 -m unittest experiments/test_tuning.py -v"""
import math
import random
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuning import registry  # noqa: E402
from tuning.constraints import Constraint, check, merge, parse  # noqa: E402
from tuning.evaluator import Evaluator  # noqa: E402
from tuning.experiment import Column, Experiment  # noqa: E402
from tuning.experiments.macc_closed_loop import MaccClosedLoop, quality  # noqa: E402
from tuning.metrics import Metrics  # noqa: E402
from tuning.objectives import OBJECTIVES, Context, ratio_objective  # noqa: E402
from tuning.params import Cat, Float, Int, Log, OneMinusLog, ParamSpace  # noqa: E402
from tuning.spec import AlgorithmSpec  # noqa: E402
from tuning.strategies import STRATEGIES  # noqa: E402
from tuning.study import Study  # noqa: E402

CONFIG = yaml.safe_load(open(Path(__file__).resolve().parents[1] / "config" / "config.yaml"))


class ParamTests(unittest.TestCase):
    def test_snap_and_candidates(self):
        self.assertEqual(Cat("a", ["no", "yes"]).snap(True), "yes")
        self.assertIsNone(Cat("a", ["no", "yes"]).snap("maybe"))
        self.assertEqual(Int("i", 1, 5).snap(9), 5)
        self.assertAlmostEqual(OneMinusLog("t", 1e-3, 1e-1).snap(0.5), 0.9)
        self.assertEqual(Log("x", 1, 100, grid=(1, 10)).candidates(), [1, 10])
        c = Log("x", 1e-3, 1e3).candidates(7)
        self.assertEqual(len(c), 7)
        self.assertAlmostEqual(c[0], 1e-3)

    def test_sample_in_range(self):
        rng = random.Random(0)
        for p in (Float("f", 0, 1), Log("l", 1e-4, 1e2), Int("i", 0, 5), OneMinusLog("o", 1e-3, 1e-1), Cat("c", [1, 2])):
            for _ in range(50):
                self.assertIsNotNone(p.snap(p.sample(rng)), p.key)

    def test_bad_definitions(self):
        with self.assertRaises(ValueError):
            Log("x", 0, 1)
        with self.assertRaises(ValueError):
            ParamSpace([Float("a.b", 0, 1), Float("a.b", 0, 2)])

    def test_start_values(self):
        space = ParamSpace([Float("g.a", 0, 1, default=0.5), Float("g.b", 0, 1, default=0.5),
                            Float("g.c", 0, 1, default=0.5, optional=True), Cat("g.d", ["no", "yes"], default="no")])
        v = space.start_values({"g": {"a": 0.2, "d": True}})
        self.assertEqual(v, {"g.a": 0.2, "g.b": 0.5, "g.d": "yes"})      # optional key stays unset, defaults fill the rest


class ConstraintTests(unittest.TestCase):
    def test_check_and_merge(self):
        m = Metrics(True, "", {"gap": 0.5, "res": 0.0})
        self.assertEqual(check([Constraint("gap", "<=", 1.0)], {1: m}, str), "")
        self.assertIn("gap", check([Constraint("gap", "<=", 0.1)], {1: m}, str))
        self.assertIn("boom", check([], {1: Metrics.failed("boom")}, str))
        self.assertIn("not available", check([Constraint("nope", "<=", 1)], {1: m}, str))
        self.assertEqual(parse("gap<=1e-3"), Constraint("gap", "<=", 1e-3))
        merged = merge([Constraint("gap", "<=", 1.0), Constraint("res", "<=", 1.0)], [Constraint("gap", "<=", 0.1)])
        self.assertEqual([c.limit for c in merged], [0.1, 1.0])


class RegistryTests(unittest.TestCase):
    def test_registered(self):
        self.assertTrue({"ipopt", "ipopt_warm", "bipm", "ispd", "al", "toy"} <= set(registry.names()))
        self.assertTrue({"macc_closed_loop", "toy"} <= set(registry.experiment_names()))
        self.assertTrue({"bo", "cd", "random"} <= set(STRATEGIES))

    def test_every_algorithm_names_a_registered_experiment_and_objective(self):
        for name in registry.names():
            spec = registry.get(name)
            registry.experiment_class(spec.experiment)
            self.assertIn(spec.default_objective, OBJECTIVES, name)

    def test_macc_parameters_have_a_start_value(self):
        """The starting setting must be definable: the config sets the key or the Param has a default (else it is optional)."""
        for name in registry.names():
            spec = registry.get(name)
            if spec.experiment != "macc_closed_loop":
                continue
            start = spec.params.select(groups=("main", "shared")).start_values(CONFIG)
            for p in spec.params:
                if not p.optional:
                    self.assertIn(p.key, start, f"{name}: {p.key} has neither a config value nor a default")


class FakeExperiment(Experiment):
    """A pure-Python experiment: the point of the design is that this is all a new simulation needs."""
    name = "fake"
    primary, primary_label = "loss", "loss"
    columns = (Column("loss", "loss"),)

    def __init__(self, table):
        self.table = table
        self.args, self.spec = Namespace(cases=None), AlgorithmSpec("t", "t", ParamSpace([]), "fake", {"cases": (1, 2)})

    def run(self, values, case, fidelity, tag):
        return self.table(values, case)


class EvaluatorTests(unittest.TestCase):
    def make(self, table, objective="loss", constraints=()):
        ratio_objective("loss", "loss")
        ctx = Context(baseline={1: Metrics(True, "", {"loss": 20.0}), 2: Metrics(True, "", {"loss": 20.0})})
        return Evaluator(FakeExperiment(table), constraints, (1, 2), 10, objective, ctx)

    def test_score_is_ratio_to_baseline(self):
        ev = self.make(lambda v, c: Metrics(True, "", {"loss": 10.0}))
        self.assertAlmostEqual(ev.evaluate({"x": 1}).score, 0.5)

    def test_constraint_rejects(self):
        ev = self.make(lambda v, c: Metrics(True, "", {"loss": 10.0, "gap": 1.0}), constraints=[Constraint("gap", "<=", 0.1)])
        r = ev.evaluate({})
        self.assertFalse(r.accepted)
        self.assertIn("gap", r.rejected)

    def test_baseline_is_not_rejected_for_quality(self):
        ev = self.make(lambda v, c: Metrics(True, "", {"loss": 10.0, "gap": 1.0}), constraints=[Constraint("gap", "<=", 0.1)])
        self.assertTrue(ev.evaluate({}, baseline=True).accepted)

    def test_crashing_experiment_rejects_instead_of_raising(self):
        def boom(v, c):
            raise RuntimeError("x")
        r = self.make(boom).evaluate({})
        self.assertFalse(r.accepted)
        self.assertIn("RuntimeError", r.rejected)

    def test_cache(self):
        calls = []
        ev = self.make(lambda v, c: calls.append(1) or Metrics(True, "", {"loss": 1.0}))
        ev.evaluate({"a": 1})
        ev.evaluate({"a": 1})
        self.assertEqual(len(calls), 2)       # two cases, evaluated once


class MaccExperimentTests(unittest.TestCase):
    def test_metrics_from_rows(self):
        spec = AlgorithmSpec("t", "t", ParamSpace([]), "macc_closed_loop", {"target": "bipm", "driver": "ispd"})
        e = MaccClosedLoop(Namespace(cases=None), spec, Path(tempfile.mkdtemp()))
        rows = [{"bipm_iterations": "30", "bipm_cost": "101", "bipm_eq_residual": "0", "bipm_ineq_violation": "0",
                 "bipm_hit_max_iter": "0", "bipm_success": "1", "bipm_time_ms": "2", "ispd_cost": "100"},
                {"bipm_iterations": "120", "bipm_cost": "100", "bipm_eq_residual": "5", "bipm_ineq_violation": "0",
                 "bipm_hit_max_iter": "1", "bipm_success": "1", "bipm_time_ms": "4", "ispd_cost": "100"}]
        m = e.metrics(rows)
        self.assertTrue(m.ok)
        self.assertEqual((m["iter_mean"], m["iter_min"], m["iter_max"], m["hit"], m["limit_steps"], m["bad"]),
                         (75.0, 30.0, 120.0, 0.5, 1.0, 0.5))
        self.assertAlmostEqual(m["gap_mean"], 0.005)
        self.assertFalse(e.metrics([{"x": "1"}]).ok)

    def test_quality_builds_constraints(self):
        names = [c.metric for c in quality(1e-3, "median", residual=None, fail=None)]
        self.assertEqual(names, ["gap_median"])


class EndToEndTests(unittest.TestCase):
    """The whole library on the toy experiment: a study with each strategy, no macc_run."""

    def run_study(self, method, **extra):
        spec = registry.get("toy")
        args = Namespace(objective="toy_loss", steps=1, jobs=2, seed=1, trials=25, startup=8, passes=1, random_refine=3,
                         min_gain=0.005, grid_points=5, promote_gain=0.0, full_steps=0, full_cases=None, validate_top=1,
                         validate_steps=1, resume=None, max_hours=0, cases=None, **extra)
        out = Path(tempfile.mkdtemp())
        (out / "runs").mkdir()
        exp = registry.experiment_class("toy")(args, spec, out / "runs")
        study = Study(spec, spec.params, exp, spec.constraints, exp.start_values(spec.params), out, args, method, "test")
        study.run(STRATEGIES[method](study, args))
        return study, out

    def test_every_strategy_improves_on_the_start(self):
        for method in ("random", "cd", "bo"):
            study, out = self.run_study(method)
            self.assertLess(study.best.score, 1.0, method)
            for f in ("trials.csv", "log.jsonl", "report.txt", "best_config.yaml", "best_overrides.txt"):
                self.assertTrue((out / f).exists(), f"{method}: {f}")
            self.assertTrue((out / "trials.csv").read_text().startswith("# command: test"))

    def test_resume_loads_history(self):
        study, out = self.run_study("random")
        n = len(study.history)
        spec = registry.get("toy")
        study2 = Study(spec, spec.params, study.experiment, spec.constraints, study.start, out, study.args, "random", "test")
        self.assertEqual(study2.load_history(), n)


if __name__ == "__main__":
    unittest.main()
