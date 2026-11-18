"""Optional bridge to the existing MACC comparison figures; no new solver runs."""

from __future__ import annotations
import json
from pathlib import Path
import re
import sys


def export_figures(folder, macc_root):
    folder = Path(folder).resolve()
    report = json.loads((folder / "report.json").read_text())
    if report["status"] != "validated" or report["winner"] is None:
        raise ValueError("no validated selected configuration to plot")
    manifest = json.loads((folder / "manifest.json").read_text())
    adapter = manifest["experiment"]
    if adapter["adapter"] != "macc":
        raise ValueError("this bridge requires a MACC study")
    sys.path.insert(0, str(Path(macc_root).resolve() / "experiments"))
    from macc_exp.figures import comparison_figure
    from macc_exp.runner import RunResult

    runs = {}
    for row in report["winner"]["runs"]:
        if row["repeat"] != 0:
            continue
        directory = folder / row["directory"]
        text = (directory / "stdout.log").read_text()
        match = re.search(r"^MACC run directory:\s*(.+?)\s*$", text, re.M)
        if not match:
            raise ValueError("MACC run directory missing in retained stdout.log")
        run_dir = Path(match.group(1))
        if not run_dir.is_absolute():
            run_dir = directory / run_dir
        summary = json.loads((run_dir / "summary.json").read_text())
        runs[int(row["case"])] = RunResult(
            label="selected",
            command=[],
            dir=run_dir,
            returncode=0,
            status="COMPLETED",
            wall_seconds=0.0,
            summary=summary,
        )
    a, b = adapter["driver"], adapter["target"]
    labels = {
        a: a.upper() if a == "ispd" else a.replace("_", " "),
        b: b.replace("_", " "),
    }
    return comparison_figure(
        runs,
        a,
        b,
        labels,
        ["traj", "iter", "time", "tpi", "cost", "better"],
        folder / "figures" / f"{a}_vs_{b}",
    )
