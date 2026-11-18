#!/usr/bin/env python3
"""Tuning of the MACC solvers (IPOPT, BIPM, ISPD, AL, ...). Library in experiments/tuning/, documentation in docs/TUNING.md.

    python3 experiments/tune.py list
    python3 experiments/tune.py show ipopt
    python3 experiments/tune.py run ipopt --method bo --trials 300 --steps 200
    python3 experiments/tune.py run bipm --method bo --trials 80 --steps 300
    python3 experiments/tune.py plot results/tuning/<folder>
    python3 experiments/tune.py apply results/tuning/<folder> --to /tmp/config_tuned.yaml
"""
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuning.cli import main  # noqa: E402

def _stop(signum, frame):
    raise KeyboardInterrupt        # the study catches it: stop issuing evaluations, validate, write the report


if __name__ == "__main__":
    # also for background jobs (nohup / &), which would otherwise ignore SIGINT: `kill <pid>` ends a run cleanly
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    sys.exit(main())
