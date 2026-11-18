"""Shared helpers of the paper scripts: locating experiment folders and their runs."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO / 'results' / 'experiments'
FULL_CYCLE = 3863                 # MPC steps of the whole driving cycle
PAPER_HORIZONS = (3, 15, 30)


def _rows(csv_file):
    with open(csv_file, 'rb') as f:
        return sum(1 for _ in f) - 1


def is_complete(exp_dir):
    """True if the folder has the paper's horizons, each over the whole driving cycle (not a --quick run)."""
    try:
        runs = runs_by_horizon(exp_dir)
    except SystemExit:
        return False
    return all(n in runs and _rows(runs[n]) >= FULL_CYCLE for n in PAPER_HORIZONS)


def latest_experiment(kind):
    """Newest results/experiments/<stamp>_<kind>* folder. For fig2 / fig3 only complete runs count."""
    found = sorted((p for p in EXPERIMENTS.glob(f'*_{kind}*') if p.is_dir()), reverse=True)
    if kind in ('fig2', 'fig3'):
        complete = [p for p in found if is_complete(p)]
        skipped = len(found) - len(complete)
        found = complete
    else:
        skipped = 0
    if not found:
        raise SystemExit(f'No complete {kind} experiment in {EXPERIMENTS}; run python3 experiments/run_experiment.py '
                         f'{kind} or pass the folder explicitly.')
    note = f'  (skipped {skipped} incomplete runs, e.g. --quick)' if skipped else ''
    print(f'{kind}: using {found[0]}{note}')
    return found[0]


def experiment_dir(arg, kind):
    """The folder given on the command line, or the newest complete one of this kind."""
    if arg:
        p = Path(arg).expanduser().resolve()
        if not p.is_dir():
            raise SystemExit(f'{p} is not a folder')
        return p
    return latest_experiment(kind)


def runs_by_horizon(exp_dir):
    """{N: path of steps.csv} of an experiment folder (runs/<stamp>_N<N>/steps.csv)."""
    runs = {}
    for f in sorted(Path(exp_dir).glob('runs/*_N*/steps.csv')):
        n = f.parent.name.rsplit('_N', 1)[-1]
        if n.isdigit():
            runs[int(n)] = f
    if not runs:
        raise SystemExit(f'No runs/*_N<N>/steps.csv in {exp_dir}')
    return dict(sorted(runs.items()))
