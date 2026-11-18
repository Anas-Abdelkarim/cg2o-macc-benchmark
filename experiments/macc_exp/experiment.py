"""A time-stamped experiment folder: several `macc_run` runs + figures + one
text file (experiment_info.txt) that documents everything needed to reproduce it."""

from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import __version__
from .paths import CONFIG, DEFAULT_RESULTS, ROOT, find_binary
from .runner import RunResult, run_macc

WIDE = "=" * 78
THIN = "-" * 78


class _Tee:
    """Duplicate stdout into a file (the experiment's console.log)."""

    def __init__(self, path: Path):
        self._f = open(path, "w", buffering=1)
        self._stdout = sys.stdout
        sys.stdout = self

    def write(self, s: str) -> int:
        self._stdout.write(s)
        return self._f.write(s)

    def flush(self) -> None:
        self._stdout.flush()
        self._f.flush()

    def close(self) -> None:
        sys.stdout = self._stdout
        self._f.close()


def _cpu_model() -> str:
    try:
        for line in open("/proc/cpuinfo"):
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _mem_gb() -> str:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                return f"{int(line.split()[1]) / 1048576:.1f}"
    except OSError:
        pass
    return "unknown"


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        if out.returncode == 0:
            return out.stdout.strip() + (" (+ uncommitted changes)" if dirty else "")
    except Exception:
        pass
    return "not a git checkout"


class Experiment:
    def __init__(self, preset: str, description: str, options: dict, *,
                 out_root: Optional[Path] = None, label: str = "", argv: Optional[Sequence[str]] = None,
                 existing_dir: Optional[Path] = None):
        self.preset = preset
        self.description = description
        self.options = dict(options)
        self.argv = list(argv if argv is not None else sys.argv)
        self.label = label
        self.runs: List[RunResult] = []
        self.sections: List[tuple] = []
        self.outputs: List[Path] = []
        self.notes: List[str] = []
        self.started = _dt.datetime.now().astimezone()
        self.status = "RUNNING"
        self._tee: Optional[_Tee] = None
        self._t0 = time.time()
        if existing_dir is not None:
            self.dir = Path(existing_dir).resolve()
        else:
            root = Path(out_root) if out_root else DEFAULT_RESULTS
            stamp = self.started.strftime("%Y%m%d_%H%M%S")
            name = f"{stamp}_{preset}" + (f"_{re.sub(r'[^A-Za-z0-9._-]+', '-', label)}" if label else "")
            self.dir = (root / name).resolve()
            n = 2
            while self.dir.exists():
                self.dir = (root / f"{name}_{n}").resolve()
                n += 1
            self.dir.mkdir(parents=True)
        self.runs_dir = self.dir / "runs"
        self.runs_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------ lifecycle
    def __enter__(self) -> "Experiment":
        self._tee = _Tee(self.dir / "console.log")
        print(f"MACC experiment '{self.preset}' -> {self.dir}")
        self.write_info()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.status = "FAILED" if exc_type else (
            "COMPLETED" if all(r.ok for r in self.runs) else "COMPLETED WITH FAILED RUNS")
        if exc_type:
            self.notes.append(f"Experiment aborted: {exc_type.__name__}: {exc}")
        self.write_info()
        if self._tee:
            print(f"\nReport : {self.dir / 'experiment_info.txt'}")
            print(f"Directory : {self.dir}")
            self._tee.close()

    # ------------------------------------------------------------------ content
    def run(self, label: str, args: Sequence[str], overrides: Sequence[str] = (),
            timeout: Optional[float] = None) -> RunResult:
        print(f"\n--- run '{label}': macc_run {shlex.join(map(str, args))}", flush=True)
        res = run_macc(args, self.runs_dir, label, overrides=overrides, timeout=timeout,
                       prefix="    ")
        self.runs.append(res)
        if not res.ok:
            print(f"    !! run '{label}' {res.status}: {res.error}", flush=True)
        self.write_info()
        return res

    def add_section(self, title: str, body: str) -> None:
        self.sections.append((title, body))

    def add_output(self, *paths: Path) -> None:
        for p in paths:
            if p not in self.outputs:
                self.outputs.append(Path(p))

    # ------------------------------------------------------------------ persistence
    def _build_block(self) -> str:
        """The 'System and build' block of the first successful run (compiler, libs)."""
        for r in self.runs:
            if r.dir and (r.dir / "experiment_info.txt").is_file():
                text = (r.dir / "experiment_info.txt").read_text().splitlines()
                try:
                    i = next(k for k, l in enumerate(text) if l.startswith("2. System and build"))
                except StopIteration:
                    continue
                out = []
                for l in text[i + 2:]:
                    if l.startswith("-----"):
                        break
                    out.append(l)
                return "\n".join(l for l in out if l.strip())
        return "(no run finished yet)"

    def write_info(self) -> None:
        now = _dt.datetime.now().astimezone()
        L: List[str] = []
        add = L.append
        add(WIDE)
        add(f"MACC experiment  {self.dir.name}")
        add(WIDE)
        add(f"preset                             : {self.preset}")
        add(f"status                             : {self.status}")
        add(f"label                              : {self.label or '-'}")
        add(f"started                            : {self.started.strftime('%Y-%m-%d %H:%M:%S %z')}")
        add(f"last update                        : {now.strftime('%Y-%m-%d %H:%M:%S %z')}")
        add(f"duration [s]                       : {time.time() - self._t0:.1f}")
        add(f"experiment folder                  : {self.dir}")
        add("")
        add(self.description.strip())
        add("")
        add(THIN)
        add("1. How to reproduce")
        add(THIN)
        add("command line                       : " + shlex.join(self.argv))
        add(f"working directory                  : {os.getcwd()}")
        add(f"options (resolved)                 : " + json.dumps(self.options, sort_keys=True, default=str))
        add("Every run below stores its own experiment_info.txt, config_resolved.yaml and steps.csv;")
        add("re-run a single run with:  macc_run --config <run folder>/config_resolved.yaml")
        add("")
        add(THIN)
        add("2. System and build")
        add(THIN)
        add(f"host                               : {platform.node()}")
        add(f"operating system                   : {platform.platform()}")
        add(f"CPU                                : {_cpu_model()}")
        add(f"logical cores                      : {os.cpu_count()}")
        add(f"memory [GB]                        : {_mem_gb()}")
        add(f"python                             : {platform.python_version()}")
        try:
            add(f"macc_run                           : {find_binary()}")
        except FileNotFoundError:
            add("macc_run                           : NOT FOUND")
        add(f"MACC git commit                    : {_git_commit()}")
        add(f"experiment layer version           : {__version__}")
        add("--- compiler / libraries reported by macc_run ---")
        add(self._build_block())
        add("")
        add(THIN)
        add("3. Runs")
        add(THIN)
        add(f"{'label':<28} {'status':<10} {'wall [s]':>9}  folder")
        for r in self.runs:
            rel = os.path.relpath(r.dir, self.dir) if r.dir else "-"
            add(f"{r.label:<28} {r.status:<10} {r.wall_seconds:>9.1f}  {rel}")
            if not r.ok and r.error:
                add(f"    error: {r.error}")
        n = 4
        for title, body in self.sections:
            add("")
            add(THIN)
            add(f"{n}. {title}")
            add(THIN)
            add(body.rstrip())
            n += 1
        if self.notes:
            add("")
            add(THIN)
            add(f"{n}. Notes")
            add(THIN)
            for t in self.notes:
                add(t)
            n += 1
        if self.outputs:
            add("")
            add(THIN)
            add(f"{n}. Files written by this experiment")
            add(THIN)
            for p in self.outputs:
                add(os.path.relpath(p, self.dir))
            n += 1
        add("")
        add(THIN)
        add(f"{n}. Base configuration (config/config.yaml, before the overrides listed above)")
        add(THIN)
        try:
            add(CONFIG.read_text().rstrip())
        except OSError:
            add("(not readable)")
        (self.dir / "experiment_info.txt").write_text("\n".join(L) + "\n")
        meta = {"preset": self.preset, "description": self.description, "options": self.options,
                "label": self.label, "argv": self.argv, "status": self.status,
                "started": self.started.isoformat(),
                "runs": [{"label": r.label, "dir": os.path.relpath(r.dir, self.dir) if r.dir else None,
                          "status": r.status, "wall_seconds": r.wall_seconds} for r in self.runs]}
        (self.dir / "experiment.json").write_text(json.dumps(meta, indent=1, default=str))

    @classmethod
    def load(cls, directory: Path) -> "Experiment":
        """Reopen a finished experiment folder (for `replot`)."""
        d = Path(directory).resolve()
        meta = json.loads((d / "experiment.json").read_text())
        exp = cls(meta["preset"], meta["description"], meta["options"], label=meta.get("label", ""),
                  argv=meta.get("argv"), existing_dir=d)
        try:
            exp.started = _dt.datetime.fromisoformat(meta["started"])
        except (KeyError, ValueError):
            pass
        for r in meta["runs"]:
            rd = (d / r["dir"]) if r["dir"] else None
            summary = None
            if rd and (rd / "summary.json").is_file():
                summary = json.loads((rd / "summary.json").read_text())
            exp.runs.append(RunResult(label=r["label"], command=[], dir=rd, returncode=0,
                                      status=r["status"], wall_seconds=r["wall_seconds"], summary=summary))
        return exp

    def run_by_label(self, label: str) -> RunResult:
        for r in self.runs:
            if r.label == label:
                return r
        raise KeyError(label)
