"""Command line of the tuning library (entry point: experiments/tune.py). Generic: algorithms, experiments and strategies are
looked up in the registries; experiment-specific options are added by the experiment classes themselves."""
from __future__ import annotations

import argparse
import csv
import json
import shlex
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import yaml

from . import registry
from .constraints import merge, parse as parse_constraint
from .objectives import OBJECTIVES
from .strategies import STRATEGIES
from .study import Study

ROOT = Path(__file__).resolve().parents[2]


def _experiment_options(parser_or_group) -> None:
    for name in registry.experiment_names():
        registry.experiment_class(name).add_arguments(parser_or_group)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tune.py", description="Tuning library (see docs/TUNING.md).", conflict_handler="resolve")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list algorithms, experiments, strategies and objectives")
    sh = sub.add_parser("show", help="parameters of one algorithm", conflict_handler="resolve")
    sh.add_argument("algorithm")
    _experiment_options(sh)
    pl = sub.add_parser("plot", help="plots of a tuning folder")
    pl.add_argument("folder", type=Path)
    st = sub.add_parser("status", help="summary of a running or stopped study (reads trials.csv)")
    st.add_argument("folder", type=Path)
    st.add_argument("--last", type=int, default=10, help="number of latest evaluations to show")
    fi = sub.add_parser("finish", help="result of a stopped / killed run, from the evaluations found so far")
    fi.add_argument("folder", type=Path)
    fi.add_argument("--no-validate", action="store_true", help="no new runs: best screening candidate from the log")
    fi.add_argument("--validate-top", type=int, default=None)
    fi.add_argument("--validate-steps", type=int, default=None)
    ap = sub.add_parser("apply", help="merge a result (best_config.yaml) into a copy of the system's configuration",
                        conflict_handler="resolve")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--to", type=Path, required=True, help="output file (never the input)")
    _experiment_options(ap)

    r = sub.add_parser("run", help="tune one algorithm", conflict_handler="resolve",
                       description="python3 experiments/tune.py run <algorithm> --method bo|cd|random [options]")
    r.add_argument("algorithm", choices=registry.names())
    r.add_argument("--method", choices=sorted(STRATEGIES), default="bo", help="search strategy (default bo)")
    g = r.add_argument_group("evaluation")
    aliases = sorted({a for n in registry.experiment_names() for a in registry.experiment_class(n).case_option_aliases})
    g.add_argument("--cases", *aliases, dest="cases", nargs="+", default=None,
                   help="cases (scenarios) every candidate is run on, in parallel (default: the algorithm's)")
    g.add_argument("--objective", choices=sorted(OBJECTIVES), default=None, help="default: the algorithm's own")
    g.add_argument("--steps", type=int, default=200, help="simulation length (fidelity) of a screening run (0 = full)")
    g.add_argument("--groups", nargs="+", default=None, help="parameter groups to tune (default: the algorithm's)")
    g.add_argument("--params", nargs="+", default=None, help="only these parameters (short or full names)")
    g.add_argument("--jobs", type=int, default=2, help="candidates evaluated at the same time (each runs all cases in parallel)")
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--max-hours", type=float, default=0.0, help="stop the search after this many hours, then validate (0 = no limit)")
    g.add_argument("--constraint", nargs="+", default=[], metavar="METRIC<=LIMIT",
                   help="replace / add a rejection rule, e.g. gap_median<=1e-3 (default: the algorithm's)")
    g = r.add_argument_group("promotion to full-length runs and validation")
    g.add_argument("--promote-gain", type=float, default=None, help="re-run a candidate at full length when its score is this "
                   "fraction lower than the reference (0 = never; default: the algorithm's)")
    g.add_argument("--full-steps", type=int, default=0, help="fidelity of those runs (0 = full)")
    g.add_argument("--full-cases", *[a.replace("--", "--full-", 1) for a in aliases], dest="full_cases", nargs="+", default=None)
    g.add_argument("--validate-top", type=int, default=3, help="re-run the best candidates at the end (0 = skip)")
    g.add_argument("--validate-steps", type=int, default=1500, help="fidelity of the validation runs (0 = full)")
    g.add_argument("--resume", type=Path, default=None, help="continue a stopped bo study in this folder")
    g = r.add_argument_group("strategy options")
    g.add_argument("--trials", type=int, default=100, help="bo / random: number of evaluations")
    for cls in STRATEGIES.values():
        cls.add_arguments(g)
    g = r.add_argument_group("experiment options")
    _experiment_options(g)
    return p


def _make_experiment(a, spec, work_dir: Path):
    return registry.experiment_class(spec.experiment)(a, spec, work_dir)


def _build_study(a, out: Path) -> Study:
    spec = registry.get(a.algorithm)
    a.objective = a.objective or spec.default_objective
    if a.promote_gain is None:
        a.promote_gain = spec.promote_gain
    space = spec.params.select(groups=a.groups or spec.default_groups, names=a.params)
    if not len(space):
        raise SystemExit("no parameters selected")
    exp = _make_experiment(a, spec, out / "runs")
    constraints = merge(spec.constraints, [parse_constraint(t) for t in a.constraint])
    command = " ".join(["python3"] + [shlex.quote(x) for x in sys.argv])
    return Study(spec, space, exp, constraints, exp.start_values(space), out, a, a.method, command)


def cmd_list() -> int:
    print("algorithms (what is tuned):")
    for n in registry.names():
        s = registry.get(n)
        print(f"  {n:<11} {len(s.params):>3} parameters   on {s.experiment:<17} {s.description}")
    print("\nexperiments (what is simulated):")
    for n in registry.experiment_names():
        print(f"  {n:<17} {registry.experiment_class(n).description}")
    print("\nstrategies (how parameters are chosen):")
    for n, c in sorted(STRATEGIES.items()):
        print(f"  {n:<8} {c.help}")
    print("\nobjectives (how a result is scored):")
    for n, f in sorted(OBJECTIVES.items()):
        print(f"  {n:<11} {(f.__doc__ or '').strip().splitlines()[0] if f.__doc__ else ''}")
    return 0


def cmd_show(a) -> int:
    spec = registry.get(a.algorithm)
    exp = _make_experiment(a, spec, Path("/nonexistent"))
    cur = exp.current_values(spec.params)
    print(f"{spec.name}: {spec.description}\n  experiment {spec.experiment}, setup {spec.setup}\n  default groups "
          f"{list(spec.default_groups)}, objective {spec.default_objective}, promote_gain {spec.promote_gain}\n  constraints:")
    for c in spec.constraints:
        print(f"    {c.metric} {c.op} {c.limit:g}   ({c.label or c.metric})")
    print(f"\n{'parameter':<52}{'group':<8}{'range':<34}{'current':<14}default")
    for p in spec.params:
        v = cur.get(p.key)
        print(f"{p.key:<52}{p.group:<8}{p.describe_range():<34}{str(v) if v is not None else '-':<14}{p.default}"
              f"{'  (may be unset)' if p.optional else ''}")
    if spec.notes:
        print("\n" + spec.notes)
    return 0


def cmd_run(a) -> int:
    if a.resume:
        out = a.resume
    else:
        out = ROOT / "results" / "tuning" / f"{datetime.now():%Y%m%d_%H%M%S}_{a.algorithm}_{a.method}"
        (out / "runs").mkdir(parents=True)
    study = _build_study(a, out)
    e = study.experiment
    prim = next((c.header for c in e.columns if c.metric == e.primary), e.primary)
    meta = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items() if k != "cmd"}
    meta.update(experiment=e.name, primary=e.primary, primary_label=e.primary_label, primary_header=prim,
                param_columns=list(study._csv_names().values()))
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    study.run(STRATEGIES[a.method](study, a))
    return 0


def _load_meta(folder: Path):
    path = folder / "meta.json"
    if not path.exists():
        print(f"{path} not found: only folders of runs started with `tune.py run` can be used", file=sys.stderr)
        return None
    m = json.loads(path.read_text())
    for k, v in list(m.items()):
        if isinstance(v, str) and k in ("config", "resume", "out", "to", "folder"):
            m[k] = Path(v)
    return m


def cmd_finish(a) -> int:
    m = _load_meta(a.folder)
    if m is None:
        return 2
    ns = argparse.Namespace(**m)
    ns.resume = a.folder
    if a.validate_top is not None:
        ns.validate_top = a.validate_top
    if a.validate_steps is not None:
        ns.validate_steps = a.validate_steps
    study = _build_study(ns, a.folder)
    print(f"{study.load_history()} evaluations in the log of {a.folder}")
    if a.no_validate:
        study.finish(validate=False)
    else:
        study.begin()          # re-runs the starting setting (needed to normalise the scores), then validates
        study.finish()
    return 0


def cmd_apply(a) -> int:
    m = _load_meta(a.folder)
    if m is None:
        return 2
    cls = registry.experiment_class(m["experiment"])
    return cls.apply(yaml.safe_load(open(a.folder / "best_config.yaml")), a)


def cmd_status(a) -> int:
    path = a.folder / "trials.csv"
    if not path.exists():
        print(f"{path} not found", file=sys.stderr)
        return 2
    meta = json.loads((a.folder / "meta.json").read_text()) if (a.folder / "meta.json").exists() else {}
    with open(path, newline="") as f:
        lines = list(f)
    heads = [ln.rstrip("\n") for ln in lines if ln.startswith("#")]
    reader = csv.DictReader([ln for ln in lines if not ln.startswith("#") and ln.strip()])
    rows, cols = list(reader), reader.fieldnames or []
    suffix = "_" + meta.get("primary_header", "iter_mean")
    prim = [c for c in cols if c.endswith(suffix)]
    ok = [r for r in rows if r["status"] == "ok"]
    print(heads[0] if heads else "")
    print(f"{len(rows)} evaluations, {len(ok)} accepted, {len(rows) - len(ok)} rejected")
    work = [r for r in ok if r["stage"] not in ("full", "full_baseline", "validation", "validation_baseline")]
    base = next((r for r in rows if r["stage"] == "baseline"), None)
    show = lambda r: "  ".join(f"{c[:-len(suffix)]} {r[c]}" for c in prim if r[c])  # noqa: E731
    if work:
        best = min(work, key=lambda r: float(r["score"]))
        if base:
            print(f"starting setting: score {base['score']}  {meta.get('primary_label', 'primary')} {show(base)}")
        print(f"best so far:      score {best['score']}  {meta.get('primary_label', 'primary')} {show(best)}   "
              f"(evaluation {best['index']}, {best['stage']})")
        for c in meta.get("param_columns", []):
            if c in best and best[c] != "" and (not base or best[c] != base[c]):
                print(f"    {c} = {best[c]}" + (f"   (start {base[c] or 'unset'})" if base else ""))
    print(f"\nlast {min(a.last, len(rows))} evaluations:")
    print(f"  {'#':>4} {'time':<9}{'stage':<20}{'score':<9}" + "".join(f"{c[:-len(suffix)] + ' ' + meta.get('primary_label', '')[:4]:<11}" for c in prim))
    for r in rows[-a.last:]:
        print(f"  {r['index']:>4} {r['time']:<9}{r['stage']:<20}{(r['score'] or 'REJECTED'):<9}"
              + "".join(f"{r[c]:<11}" for c in prim) + (f"   {r['rejected_because'][:60]}" if r["status"] != "ok" else ""))
    return 0


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.cmd == "list":
        return cmd_list()
    if a.cmd == "show":
        return cmd_show(a)
    if a.cmd == "plot":
        from .plots import make_plots
        for f in make_plots(a.folder):
            print(f)
        return 0
    if a.cmd == "apply":
        return cmd_apply(a)
    if a.cmd == "finish":
        return cmd_finish(a)
    if a.cmd == "status":
        return cmd_status(a)
    return cmd_run(a)
