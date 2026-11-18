"""Integration contract test against an actual fake executable, not the solver."""

import json
import os
import pytest
import yaml
from tuning import Space, Log, Objective, Constraint, Settings, Study
from tuning.adapters.macc import MaccExperiment


@pytest.mark.skipif(os.name != "posix", reason="fake executable uses POSIX shebang")
def test_macc_adapter_end_to_end(tmp_path):
    binary = tmp_path / "fake_macc"
    binary.write_text("""#!/usr/bin/env python3
import csv,json,pathlib,sys,yaml
cfg=yaml.safe_load(open(sys.argv[2]))
root=pathlib.Path(cfg['experiment']['output_dir'])/'result'
root.mkdir(parents=True)
n=cfg['mpc']['loop_size'] or 4
summary={'completed':True,'driver':cfg['experiment']['driver'],'horizon':cfg['mpc']['horizon'],'steps':n}
(root/'summary.json').write_text(json.dumps(summary))
row={}
for s in cfg['experiment']['solvers'].split(','):
    for k,v in {'iterations':20,'cost':100,'eq_residual':0,'ineq_violation':0,'success':1,'hit_max_iter':0,'time_ms':2}.items():
        row[s+'_'+k]=v
with open(root/'steps.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerows([row]*n)
print('MACC run directory:',root)
""")
    binary.chmod(0o755)
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "mpc": {"loop_size": 300, "run_times": 10},
                "ipopt_settings": {"options": {"mu_min": 1e-8}},
            }
        )
    )
    space = Space([Log("ipopt_settings.options.mu_min", 1e-9, 1e-5, optional=True)])
    adapter = MaccExperiment(binary, config, space.keys)
    study = Study(
        space,
        adapter,
        Objective("iterations", "relative"),
        [Constraint("hit_fraction", 0), Constraint("eq_max", 1e-4)],
        directory=tmp_path / "study",
        settings=Settings(cases=(3,), screening_fidelity=2, validation_repeats=1),
        method="random",
    )
    assert study.run(2).accepted
    report = json.loads((tmp_path / "study" / "report.json").read_text())
    assert all(r["metrics"]["steps"] == 4 for r in report["winner"]["runs"])
    assert (tmp_path / "study" / "selected_config.yaml").exists()
    assert yaml.safe_load(config.read_text())["mpc"]["loop_size"] == 300
