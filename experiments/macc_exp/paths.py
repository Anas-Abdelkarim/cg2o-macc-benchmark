"""Locations of the MACC tree, of the C++ binary and of the result folders."""

from __future__ import annotations

import os
from pathlib import Path

# experiments/macc_exp/paths.py  ->  <MACC root>
ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "config.yaml"
PAPER_REFERENCE = ROOT / "config" / "paper_reference.yaml"
DEFAULT_RESULTS = ROOT / "results" / "experiments"


def find_binary() -> Path:
    """`$MACC_RUN`, else the binary of the standard build directory."""
    env = os.environ.get("MACC_RUN")
    candidates = [Path(env)] if env else []
    candidates += [ROOT / "build" / "macc" / "bin" / "macc_run",
                   ROOT / "build" / "bin" / "macc_run"]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError(
        "macc_run is not built yet. Build it first:\n"
        "  ./scripts/build_externals.sh      # g2o, cg2o, IPOPT (once)\n"
        "  ./scripts/build_workspace.sh      # macc_run\n"
        "or set MACC_RUN=/path/to/macc_run.\nLooked in: " + ", ".join(str(c) for c in candidates))
