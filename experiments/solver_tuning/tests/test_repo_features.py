"""Features added for use in the MACC repository: live trials.csv, rich status, plots, --finish, config snapshot, SIGTERM."""

import json
import os
from pathlib import Path
import signal
import pytest
import yaml
from tuning import Study, Space, Float, Objective, Settings
from tuning.cli import main, load_study, _stop
from tuning.experiment import Experiment
from tuning.tables import status_text

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class Probe(Experiment):
    """loss = 1 + x^2; remembers how many table rows were visible when each simulation started."""

    def __init__(self, folder):
        self.folder, self.rows_seen = Path(folder), []

    def fingerprint(self):
        return {"probe": 1}

    def run(self, values, context):
        path = self.folder / "trials.csv"
        lines = path.read_text().splitlines() if path.exists() else []
        data = [ln for ln in lines if ln and not ln.startswith("#")]
        self.rows_seen.append(max(0, len(data) - 1))  # minus the header line
        return {"loss": 1 + values["x"] ** 2}


def make_study(tmp_path, trials=4):
    exp = Probe(tmp_path)
    study = Study(
        Space([Float("x", -1, 1, default=0.9)]),
        exp,
        Objective("loss", "relative"),
        directory=tmp_path,
        settings=Settings(
            cases=(0,),
            screening_fidelity=1,
            validation_repeats=1,
            validate_top=2,
            jobs=1,
            seed=3,
        ),
        method="random",
    )
    study.command = "pytest live-table"
    return study, exp


def test_trials_csv_is_written_while_the_study_runs(tmp_path):
    study, exp = make_study(tmp_path)
    assert study.run(4).accepted
    # the k-th simulation saw exactly the k rows of the evaluations completed before it
    assert exp.rows_seen[:5] == [0, 1, 2, 3, 4]
    lines = (tmp_path / "trials.csv").read_text().splitlines()
    assert lines[0].startswith("# command: pytest live-table")
    header = next(ln for ln in lines if not ln.startswith("#"))
    assert header.startswith("trial,time,phase,status,score,fidelity,c0_loss")
    assert header.endswith(",x,reasons")
    rows = [ln for ln in lines if not ln.startswith("#")][1:]
    assert (
        len(rows) >= 7
    )  # baseline, 4 searches, validation baseline and at least one finalist


def test_status_shows_best_changes_and_latest(tmp_path):
    study, _ = make_study(tmp_path)
    study.run(5)
    text = status_text(tmp_path, last=3)
    assert "# command: pytest live-table" in text
    assert "best so far" in text and "x = " in text and "(baseline: 0.9)" in text
    assert text.count("\n  #") == 3
    assert "selection: validated" in text


def test_plots_are_written_after_validation(tmp_path):
    pytest.importorskip("matplotlib")
    study, _ = make_study(tmp_path)
    study.run(10)
    assert main(["plot", str(tmp_path)]) == 0
    assert (tmp_path / "search_progress.png").exists()
    assert (tmp_path / "selected_vs_baseline.png").exists()


def spec_in(tmp_path):
    cfg = yaml.safe_load((EXAMPLES / "toy.yaml").read_text())
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return path


def test_finish_validates_without_more_search_and_resume_matches(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLES))
    out = tmp_path / "out"
    spec = spec_in(tmp_path)
    assert (
        main(["run", str(spec), "--out", str(out), "--trials", "5", "--screen-only", "--no-stamp"])
        == 0
    )
    report = json.loads((out / "report.json").read_text())
    assert report["status"].startswith("screening only")
    assert main(["run", str(spec), "--out", str(out), "--finish"]) == 0
    report = json.loads((out / "report.json").read_text())
    assert report["status"] in ("validated", "no configuration passed validation")
    assert "selection:" in status_text(out)


def test_sigterm_and_sigint_are_turned_into_a_clean_stop():
    with pytest.raises(KeyboardInterrupt):
        _stop(signal.SIGTERM, None)


FAKE = """#!/usr/bin/env python3
import csv,json,pathlib,sys,yaml
cfg=yaml.safe_load(open(sys.argv[2]))
root=pathlib.Path(cfg['experiment']['output_dir'])/'result'
root.mkdir(parents=True)
n=cfg['mpc']['loop_size'] or 4
(root/'summary.json').write_text(json.dumps({'completed':True,'driver':cfg['experiment']['driver'],'horizon':cfg['mpc']['horizon'],'steps':n}))
row={}
for s in cfg['experiment']['solvers'].split(','):
    for k,v in {'iterations':20,'cost':100,'eq_residual':0,'ineq_violation':0,'success':1,'hit_max_iter':0,'time_ms':2}.items():
        row[s+'_'+k]=v
with open(root/'steps.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerows([row]*n)
print('MACC run directory:',root)
"""


@pytest.mark.skipif(os.name != "posix", reason="fake executable uses a POSIX shebang")
def test_macc_base_config_is_frozen_inside_the_study(tmp_path):
    binary = tmp_path / "fake_macc"
    binary.write_text(FAKE)
    binary.chmod(0o755)
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {"mpc": {"loop_size": 300}, "ipopt_settings": {"options": {"mu_min": 1e-8}}}
        )
    )
    spec = tmp_path / "macc.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "method": "random",
                "experiment": {
                    "type": "macc",
                    "binary": "fake_macc",
                    "config": "config.yaml",
                    "target": "ipopt",
                    "driver": "ispd",
                },
                "parameters": [
                    {
                        "key": "ipopt_settings.options.mu_min",
                        "kind": "log",
                        "low": 1e-9,
                        "high": 1e-5,
                        "optional": True,
                    }
                ],
                "objective": {"metric": "iterations", "mode": "relative"},
                "constraints": [{"metric": "hit_fraction", "limit": 0}],
                "settings": {
                    "cases": [3],
                    "screening_fidelity": 2,
                    "validation_repeats": 1,
                    "validate_top": 1,
                },
            }
        )
    )
    out = tmp_path / "out"
    assert main(["run", str(spec), "--out", str(out), "--trials", "2", "--no-stamp"]) == 0
    snapshot = out / "inputs" / "base_config.yaml"
    assert snapshot.exists() and (out / "inputs" / "study.yaml").exists()
    # the living config.yaml is edited while the study exists: resume must neither fail nor change what is tuned
    config.write_text(
        yaml.safe_dump(
            {"mpc": {"loop_size": 999}, "ipopt_settings": {"options": {"mu_min": 1e-3}}}
        )
    )
    assert main(["run", str(spec), "--out", str(out), "--trials", "3", "--resume"]) == 0
    assert yaml.safe_load(snapshot.read_text())["mpc"]["loop_size"] == 300
    assert load_study(spec, out).experiment.config == snapshot.resolve()
