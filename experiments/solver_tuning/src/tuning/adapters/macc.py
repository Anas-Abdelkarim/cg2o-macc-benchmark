"""MACC is an adapter, not part of the optimizer. Preserves exact executed YAML."""

from __future__ import annotations
import copy
import csv
import json
import math
from pathlib import Path
import re
import statistics
import yaml
from ..experiment import Experiment
from ..model import RunResult
from ..util import get_dotted, set_dotted, del_dotted, file_hash, atomic_json
from .process import execute

SINGLE_THREAD = {
    key: "1"
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "BLIS_NUM_THREADS",
    )
}


class MaccExperiment(Experiment):
    def __init__(
        self,
        binary,
        config,
        managed_keys,
        *,
        target="ipopt_warm",
        driver="ispd",
        init="fixed",
        max_iterations=120,
        timeout=1800,
        reference_residual=1e-4,
        require_reference_convergence=True,
        timing=False,
    ):
        self.binary = Path(binary).resolve()
        self.config = Path(config).resolve()
        if not self.binary.is_file():
            raise ValueError(f"MACC executable missing: {self.binary}")
        self.original = yaml.safe_load(self.config.read_text())
        if not isinstance(self.original, dict):
            raise ValueError("MACC config must be a YAML mapping")
        self.managed_keys = tuple(managed_keys)
        known = {"ipopt", "ipopt_warm", "ispd", "bipm", "al"}
        if target not in known or driver not in known:
            raise ValueError("unknown MACC target/driver solver")
        if target == driver:
            raise ValueError(
                "target and driver must differ for a fixed reference trajectory"
            )
        self.target, self.driver, self.init = target, driver, init
        self.max_iterations, self.timeout = max_iterations, timeout
        if not math.isfinite(reference_residual) or reference_residual < 0:
            raise ValueError("reference_residual must be finite and nonnegative")
        self.reference_residual = reference_residual
        self.require_reference_convergence = require_reference_convergence
        self.isolated_timing = timing
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        for key in self.managed_keys:
            allowed = (
                ("ipopt_settings.options.",)
                if target.startswith("ipopt")
                else (target + "_settings.",)
            )
            # ISPD may own cg2o options while IPOPT is the fixed driver.
            if target == "ispd" and driver.startswith("ipopt"):
                allowed += ("cg2o.", "general_settings.")
            al_only = target == "al" and key in (
                "general_settings.rho_initial_eq",
                "general_settings.rho_max_eq",
                "general_settings.rho_update_factor_eq",
            )
            if not al_only and not key.startswith(allowed):
                raise ValueError(
                    f"{key}: tuning this may change the driver/problem; use a target-specific key"
                )
            if key.endswith(".max_iter"):
                raise ValueError(
                    "iteration budget is fixed by the adapter, not a tunable parameter"
                )

    def fingerprint(self):
        return {
            "adapter": "macc",
            "binary": str(self.binary),
            "binary_sha256": file_hash(self.binary),
            "config": str(self.config),
            "config_sha256": file_hash(self.config),
            "managed_keys": self.managed_keys,
            "target": self.target,
            "driver": self.driver,
            "init": self.init,
            "max_iterations": self.max_iterations,
            "timeout": self.timeout,
            "reference_residual": self.reference_residual,
            "require_reference_convergence": self.require_reference_convergence,
            "timing": self.isolated_timing,
        }

    def baseline(self, space):
        return {
            p.key: get_dotted(self.original, p.key)
            for p in space
            if get_dotted(self.original, p.key) is not None
        }

    def resolved(self, values, baseline=False):
        cfg = copy.deepcopy(self.original)
        if not baseline:
            for key in self.managed_keys:
                del_dotted(cfg, key)
        # baseline: the original configuration with its (possibly repaired, see Space.repair) values; unchanged
        # values are a no-op, absent ones stay absent
        for key, value in values.items():
            set_dotted(cfg, key, value)
        return cfg

    def run(self, values, context):
        cfg = self.resolved(values, context.baseline)
        # Force a fair repetition protocol and explicit fidelity even when 0=full.
        for key, value in {
            "experiment.solvers": self.driver + "," + self.target,
            "experiment.driver": self.driver,
            "mpc.horizon": int(context.case),
            "mpc.init_mode": self.init,
            "mpc.run_times": 1,
            "mpc.number_of_iterations": self.max_iterations,
            "mpc.loop_size": context.fidelity,
            "experiment.output_dir": str(context.directory / "runs"),
            "experiment.label": "evaluation",
            "experiment.progress_every": 100000000,
        }.items():
            set_dotted(cfg, key, value)
        # IPOPT max_iter in YAML overrides the common budget; freeze it explicitly.
        set_dotted(cfg, "ipopt_settings.options.max_iter", self.max_iterations)
        path = context.directory / "executed_config.yaml"
        path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        cmd = [str(self.binary), "--config", str(path)]
        atomic_json(context.directory / "command.json", cmd)
        execute(cmd, context.directory, self.timeout, SINGLE_THREAD)
        output = (context.directory / "stdout.log").read_text()
        match = re.search(r"^MACC run directory:\s*(.+?)\s*$", output, re.M)
        if not match:
            return RunResult(error="MACC did not report its run directory")
        run_dir = Path(match.group(1))
        # Some builds print paths relative to the subprocess cwd.
        if not run_dir.is_absolute():
            run_dir = context.directory / run_dir
        if not run_dir.resolve().is_relative_to(context.directory.resolve()):
            return RunResult(error="MACC returned a run directory outside this trial")
        summary = json.loads((run_dir / "summary.json").read_text())
        if (
            summary.get("completed") is not True
            or summary.get("driver") != self.driver
            or int(summary.get("horizon", -1)) != int(context.case)
        ):
            return RunResult(error="incomplete run or driver/horizon mismatch")
        with open(run_dir / "steps.csv") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return RunResult(error="empty steps.csv")
        if len(rows) != int(summary.get("steps", -1)):
            return RunResult(error="steps.csv length differs from summary")
        if context.fidelity and len(rows) != context.fidelity:
            return RunResult(error="requested number of steps not completed")
        return self.metrics(rows)

    def metrics(self, rows):
        try:

            def col(solver, name):
                return [float(r[f"{solver}_{name}"]) for r in rows]

            cols = {
                s: {
                    k: col(s, k)
                    for k in (
                        "iterations",
                        "cost",
                        "eq_residual",
                        "ineq_violation",
                        "hit_max_iter",
                        "success",
                        "time_ms",
                    )
                }
                for s in (self.target, self.driver)
            }
            if any(
                not math.isfinite(v)
                for d in cols.values()
                for vs in d.values()
                for v in vs
            ):
                return RunResult(error="nonfinite target/reference measurements")
            if any(
                v not in (0, 1)
                for d in cols.values()
                for k in ("success", "hit_max_iter")
                for v in d[k]
            ):
                return RunResult(error="invalid success/iteration-limit flag")
            if any(
                v < 0
                for d in cols.values()
                for k in ("eq_residual", "ineq_violation", "time_ms", "iterations")
                for v in d[k]
            ):
                return RunResult(error="negative residual, time or iteration count")
            reference = cols[self.driver]
            if any(v != 1 for v in reference["success"]):
                return RunResult(error="reference solver failed")
            if self.require_reference_convergence and any(reference["hit_max_iter"]):
                return RunResult(error="reference hit iteration limit")
            if (
                max(reference["eq_residual"] + reference["ineq_violation"])
                > self.reference_residual
            ):
                return RunResult(
                    error="reference solver is infeasible under configured threshold"
                )
            target = cols[self.target]
            gaps = [
                max(0.0, c - r) / max(abs(r), 1e-12)
                for c, r in zip(target["cost"], reference["cost"])
            ]
            # One-sided excess allows a candidate to find a better feasible solution.
            agreement = [
                abs(c - r) / max(abs(r), 1e-12)
                for c, r in zip(target["cost"], reference["cost"])
            ]
            return RunResult(
                {
                    "iterations": statistics.mean(target["iterations"]),
                    "time_ms": statistics.mean(target["time_ms"]),
                    "cost_mean": statistics.mean(target["cost"]),
                    "cost_excess_mean": statistics.mean(gaps),
                    "cost_agreement_mean": statistics.mean(agreement),
                    "cost_excess_max": max(gaps),
                    "eq_max": max(target["eq_residual"]),
                    "ineq_max": max(target["ineq_violation"]),
                    "hit_fraction": statistics.mean(target["hit_max_iter"]),
                    "fail_fraction": 1 - statistics.mean(target["success"]),
                    "steps": float(len(rows)),
                }
            )
        except (KeyError, ValueError, TypeError) as e:
            return RunResult(error=f"invalid MACC measurements: {e}")

    def export(self, values, directory):
        from ..util import atomic_json

        atomic_json(directory / "selected_parameters.json", values)
        # Export baseline unchanged if selected, otherwise materialize all removals.
        original_values = {
            k: get_dotted(self.original, k)
            for k in self.managed_keys
            if get_dotted(self.original, k) is not None
        }
        cfg = self.resolved(values, baseline=values == original_values)
        set_dotted(cfg, "mpc.run_times", 1)
        set_dotted(cfg, "mpc.number_of_iterations", self.max_iterations)
        set_dotted(cfg, "ipopt_settings.options.max_iter", self.max_iterations)
        (directory / "selected_config.yaml").write_text(
            yaml.safe_dump(cfg, sort_keys=False)
        )
