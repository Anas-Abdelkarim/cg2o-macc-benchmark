"""Thin, dependency-light wrapper around the `macc_run` executable."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from .paths import find_binary


@dataclass
class RunResult:
    label: str
    command: List[str]
    dir: Optional[Path]
    returncode: int
    status: str                       # COMPLETED | FAILED | TIMEOUT | NO_OUTPUT
    wall_seconds: float
    summary: Optional[dict] = None
    error: str = ""
    _steps: Optional[Dict[str, np.ndarray]] = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.status == "COMPLETED" and self.summary is not None

    def steps(self) -> Dict[str, np.ndarray]:
        """Per-step table of the run (columns of steps.csv) as arrays."""
        if self._steps is None:
            if self.dir is None or not (self.dir / "steps.csv").is_file():
                raise FileNotFoundError(f"no steps.csv for run '{self.label}'")
            raw = np.genfromtxt(self.dir / "steps.csv", delimiter=",", names=True)
            raw = np.atleast_1d(raw)
            self._steps = {n: np.asarray(raw[n], dtype=float) for n in raw.dtype.names}
        return self._steps

    def solver_summary(self, solver: str) -> dict:
        return self.summary["solvers"][solver]

    @property
    def horizon(self) -> Optional[int]:
        return None if self.summary is None else int(self.summary["horizon"])


def _read_summary(run_dir: Optional[Path]) -> Optional[dict]:
    if run_dir is None:
        return None
    p = run_dir / "summary.json"
    if not p.is_file():
        return None
    try:
        with p.open() as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


_DIR_RE = re.compile(r"^MACC run directory:\s*(.+?)\s*$")


def run_macc(args: Sequence[str], out_root: Path, label: str, *,
             overrides: Sequence[str] = (), timeout: Optional[float] = None,
             echo: bool = True, prefix: str = "") -> RunResult:
    """Run `macc_run <args> --out <out_root> --label <label>` and collect the result.

    The process starts inside `out_root` so that stray files written by third-
    party libraries (e.g. g2o's `debug.txt` after a Cholesky failure) stay
    inside the experiment folder.
    """
    binary = find_binary()
    out_root = Path(out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    cmd = [str(binary), *map(str, args), "--out", str(out_root), "--label", label]
    for o in overrides:
        cmd += ["--set", o]

    t0 = time.time()
    # macc_run is single-threaded by default. g2o is built with OpenMP and links MKL: with OMP_NUM_THREADS=8 (a common ~/.bashrc
    # setting) every solve is about 2x slower and burns many times the CPU time for these tiny problems. Override with
    # MACC_THREADS=<n> if you really want threads.
    threads = os.environ.get("MACC_THREADS", "1")
    env = {**os.environ, **{k: threads for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                                 "BLIS_NUM_THREADS")}}
    proc = subprocess.Popen(cmd, cwd=out_root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, start_new_session=True, env=env)
    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    # 0 (or a value too large for threading.Timer, about 3 years and up) means no limit
    timer = threading.Timer(timeout, _kill) if timeout and 0 < timeout < 1e8 else None
    if timer:
        timer.start()

    run_dir: Optional[Path] = None
    lines: List[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            lines.append(line)
            m = _DIR_RE.match(line)
            if m:
                run_dir = Path(m.group(1))
            if echo and line.strip():
                # keep the console readable: skip library chatter
                if line.startswith(("  step", "===", "  ispd", "  bipm", "  al:", "  ipopt",
                                    "ERROR", "Setup error", "Closed loop", "Report:")):
                    print(f"{prefix}{line}", flush=True)
        proc.wait()
    finally:
        if timer:
            timer.cancel()

    wall = time.time() - t0
    summary = _read_summary(run_dir)
    if timed_out.is_set():
        status = "TIMEOUT"
    elif summary is not None:
        status = str(summary.get("status", "COMPLETED"))
        if status != "COMPLETED" and proc.returncode == 0:
            status = "COMPLETED"
    elif run_dir is None:
        status = "NO_OUTPUT"
    else:
        status = "FAILED"
    if proc.returncode not in (0, None) and status == "COMPLETED":
        status = "FAILED"

    err = ""
    if status != "COMPLETED":
        errs = [l for l in lines if "error" in l.lower() or "ERROR" in l]
        err = errs[-1] if errs else (lines[-1] if lines else "")
    if run_dir is not None and run_dir.is_dir():
        try:
            (run_dir / "runner_output.log").write_text("\n".join(lines) + "\n")
        except OSError:
            pass
    return RunResult(label=label, command=cmd, dir=run_dir, returncode=proc.returncode,
                     status=status, wall_seconds=wall, summary=summary, error=err)


def list_linear_solvers() -> List[dict]:
    """Parse `macc_run --list-solvers` into dictionaries."""
    out = subprocess.run([str(find_binary()), "--list-solvers"], capture_output=True, text=True,
                         check=True).stdout
    solvers = []
    for line in out.splitlines()[1:]:
        m = re.match(r"^(\d+)\s+(\S+)\s+(.+?)\s{2,}(g2o|cg2o)\s+(yes|no)\s+(yes|NO)\s*(.*)$", line)
        if not m:
            continue
        solvers.append({"id": int(m.group(1)), "key": m.group(2), "name": m.group(3).strip(),
                        "lib": m.group(4), "spd_only": m.group(5) == "yes",
                        "available": m.group(6) == "yes", "note": m.group(7).strip()})
    return solvers
