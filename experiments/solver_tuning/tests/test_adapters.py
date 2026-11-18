from __future__ import annotations
import subprocess
import sys
import yaml
import pytest
from tuning import RunContext
from tuning.adapters.command import CommandExperiment
from tuning.adapters.macc import MaccExperiment
from tuning.adapters.process import execute


def make_macc(tmp_path, **kwargs):
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "mpc": {"loop_size": 300, "run_times": 10},
                "ipopt_settings": {"options": {"mu_min": 0.0001, "tol": 1e-8}},
            }
        )
    )
    return MaccExperiment(
        sys.executable, path, ["ipopt_settings.options.mu_min"], **kwargs
    )


def test_optional_parameter_really_removed(tmp_path):
    adapter = make_macc(tmp_path)
    original = adapter.resolved({}, baseline=True)
    candidate = adapter.resolved({})
    assert original["ipopt_settings"]["options"]["mu_min"] == 0.0001
    assert "mu_min" not in candidate["ipopt_settings"]["options"]
    assert candidate["ipopt_settings"]["options"]["tol"] == 1e-8


def test_reject_shared_driver_settings(tmp_path):
    adapter = make_macc(tmp_path)
    with pytest.raises(ValueError, match="driver"):
        MaccExperiment(
            sys.executable,
            adapter.config,
            ["general_settings.num_inner_iterations_max"],
            target="bipm",
        )


def rows(cost=99, ref=100):
    row = {}
    for solver, c in [("ipopt_warm", cost), ("ispd", ref)]:
        row.update(
            {
                f"{solver}_{key}": str(v)
                for key, v in {
                    "iterations": 15,
                    "cost": c,
                    "eq_residual": 0,
                    "ineq_violation": 0,
                    "hit_max_iter": 0,
                    "success": 1,
                    "time_ms": 1,
                }.items()
            }
        )
    return [row]


def test_better_candidate_is_not_rejected_for_cost_gap(tmp_path):
    m = make_macc(tmp_path).metrics(rows())
    assert m.metrics["cost_excess_mean"] == 0
    assert m.metrics["cost_agreement_mean"] == 0.01


@pytest.mark.parametrize(
    "key,value",
    [("cost", "nan"), ("eq_residual", "1"), ("success", "0"), ("hit_max_iter", "1")],
)
def test_bad_reference_rejected(tmp_path, key, value):
    data = rows()
    data[0]["ispd_" + key] = value
    assert make_macc(tmp_path).metrics(data).error


def test_json_program_adapter(tmp_path):
    script = tmp_path / "program.py"
    script.write_text(
        'import json,sys\nr=json.load(open(sys.argv[1]))\njson.dump({"metrics":{"loss":r["parameters"]["x"]**2}},open(sys.argv[2],"w"))\n'
    )
    adapter = CommandExperiment(
        [sys.executable, str(script), "{request}", "{result}"], inputs=[script]
    )
    directory = tmp_path / "trial"
    directory.mkdir()
    ctx = RunContext("test", 0, 1, directory)
    result = adapter.run({"x": 3}, ctx)
    assert result.metrics == {"loss": 9}
    assert (directory / "stdout.log").exists()


def test_external_timeout(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        execute([sys.executable, "-c", "import time; time.sleep(20)"], tmp_path, 0.05)
    assert (tmp_path / "stderr.log").exists()


def test_executed_yaml_has_explicit_protocol(tmp_path, monkeypatch):
    adapter = make_macc(tmp_path)

    def fake(command, directory, timeout, env):
        raise RuntimeError("stop after inspecting resolved YAML")

    monkeypatch.setattr("tuning.adapters.macc.execute", fake)
    ctx = RunContext(30, 0, 1, tmp_path / "trial", False)
    ctx.directory.mkdir()
    with pytest.raises(RuntimeError):
        adapter.run({}, ctx)
    cfg = yaml.safe_load((ctx.directory / "executed_config.yaml").read_text())
    assert cfg["mpc"]["loop_size"] == 0
    assert cfg["mpc"]["run_times"] == 1
    assert cfg["ipopt_settings"]["options"]["max_iter"] == 120
    assert "mu_min" not in cfg["ipopt_settings"]["options"]
