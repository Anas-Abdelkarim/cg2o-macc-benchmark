# Installation

C++20, CMake >= 3.22 (the version of Ubuntu 22.04), Ninja. Built and tested on Ubuntu 22.04 (GCC 11.4 and 12.3) and
Ubuntu 24.04 (GCC 13.3). The short path is [QUICKSTART.md](QUICKSTART.md); this file has the details.

## 1. System packages

```bash
sudo apt update
sudo apt install -y git build-essential gfortran cmake ninja-build pkg-config python3-pip python3-venv \
  libeigen3-dev libfmt-dev libyaml-cpp-dev libsuitesparse-dev libomp-dev \
  liblapack-dev libblas-dev libmetis-dev libhwloc-dev
python3 -m pip install -r experiments/requirements.txt     # numpy, matplotlib, PyYAML, pandas, scipy
./scripts/check_build_env.sh                                 # reports what is missing
```

## 2. Externals

Everything below is installed into `install/externals/<name>` (never into the system) and
found again through `scripts/setup_env.sh`, which `build_workspace.sh` sources for you (`macc_run` itself needs
no environment: the library paths are compiled into it).

| component | needed for | command | notes |
|---|---|---|---|
| g2o | cg2o solvers | `./scripts/build_externals.sh` | cloned to `externals/g2o` at `G2O_REF` (default `eec325a1`), built with `G2O_NO_IMPLICIT_OWNERSHIP_OF_OBJECTS` |
| cg2o | ISPD-IPM, BIPM, AL | same command | source: `CG2O_DIR` → `externals/cg2o` → clone of `snt-arg/cg2o` at `CG2O_REF` (default `b14da0c`, branch `dev`, the paper's version) |
| IPOPT | native IPOPT backend (`ipopt`, `ipopt_warm`, Fig. 3) | same command (or `--ipopt` alone) | 3.14.21 (`stable/3.14` @ `cc33071`) from source, MUMPS; see below |
| HSL (optional) | IPOPT with MA27/MA57/... (paper Table V: MA57) | `USE_HSL=ON ./scripts/build_externals.sh` or `--hsl` | licensed source in `externals/`, see [externals/README.md](externals/README.md) |

`./scripts/build_externals.sh` (the default, same as `--all`) builds g2o, cg2o and IPOPT, and HSL too when
`USE_HSL=ON`; `--solver-only` skips IPOPT. `--clean` rebuilds only the selected components and
removes only their own build and install folders.

### Using a local checkout of cg2o or g2o (development)

By default the pinned versions are cloned into `externals/`. To build against your own checkout instead (e.g. to
test changes in cg2o), point the scripts to it. The checkout is used as it is: its branch and local edits are not
touched, and `CG2O_REF` is ignored.

```bash
CG2O_DIR=/path/to/cg2o ./scripts/build_externals.sh --cg2o-only     # build and install your cg2o
CG2O_DIR=/path/to/cg2o ./scripts/rebuild_cg2o.sh                    # after editing it: cg2o, then MACC
./scripts/rebuild_cg2o.sh                                           # back to the pinned externals/cg2o
G2O_DIR=/path/to/g2o ./scripts/build_externals.sh --solver-only --clean   # own g2o (cg2o is rebuilt against it)
```

Set `CG2O_DIR` on every call: without it the scripts use `externals/cg2o` again (the switch reconfigures and
rebuilds cg2o automatically). After `build_externals.sh`, run `./scripts/build_workspace.sh` so that MACC is
relinked. Other pinned commits are chosen with `CG2O_REF=<commit>` / `G2O_REF=<commit>`; they apply to a fresh
clone only, so delete `externals/cg2o` or `externals/g2o` first. Results are comparable with the paper only
with the pinned versions.

### IPOPT

```bash
./scripts/build_externals.sh --ipopt                 # default: --source, IPOPT 3.14.21 with all linear solvers it can find
./scripts/build_externals.sh --hsl                   # HSL as a run-time library (source in externals/, licensed)
./scripts/build_externals.sh --ipopt --system        # use the Ubuntu package instead (IPOPT 3.11.9, MUMPS only)
```

`--source` builds IPOPT 3.14.21 (branch `IPOPT_REF=stable/3.14`, commit `IPOPT_COMMIT=cc33071`; for a tagged release
use e.g. `IPOPT_REF=3.14.20 IPOPT_COMMIT=`) with coinbrew (needs git, gfortran, BLAS/LAPACK, `libmetis-dev`, `libhwloc-dev`
and access to GitHub) and adds every linear solver that can be built on the machine:

| `linear_solver` | built when | notes |
|---|---|---|
| `mumps` | always (ThirdParty-Mumps) | the default (`ipopt_settings.use_hsl: false`) |
| `pardisomkl` | Intel MKL is found (`MKLROOT`, else `/opt/intel/oneapi/mkl/latest`); `WITH_MKL=OFF` skips it | MKL is linked **sequentially**, so PARDISO runs on one core like the others; MKL is then also IPOPT's BLAS/LAPACK |
| `spral` | always (`WITH_SPRAL=OFF` skips it); cloned from GitHub, built with meson (a venv is created if meson is missing) | needs `OMP_CANCELLATION=TRUE OMP_PROC_BIND=TRUE` at run time (the `ipopt-linear-solvers` preset sets them) |
| `ma27`, `ma57`, `ma77`, `ma86`, `ma97` | loaded at run time from `install/externals/hsl` (`USE_HSL=ON` / `--hsl`); used with `ipopt_settings.use_hsl: true`, solver `hsl_solver` | licensed: free for academic use from https://licences.stfc.ac.uk/product/coin-hsl |

The script prints the solvers that made it into the library. Compare them with
`python3 experiments/run_experiment.py ipopt-linear-solvers` (see docs/EXPERIMENTS.md).

`cmake` looks for IPOPT with pkg-config; a local `install/externals/ipopt` wins over the system package.
Without IPOPT, MACC still builds (`-DMACC_WITH_IPOPT=OFF`, or no package found: CMake prints a warning) and asking for the solver `ipopt` stops with a message explaining how to install it.

## 3. Build

```bash
./scripts/build_workspace.sh                         # Release, Ninja, build/macc
./scripts/build_workspace.sh --clean                 # from scratch (keeps all externals)
./scripts/build_workspace.sh -- -DMACC_WITH_IPOPT=OFF -DMACC_BUILD_TESTS=OFF
CXX=g++-11 ./scripts/build_workspace.sh --clean      # choose the compiler
BUILD_TYPE=Debug JOBS=4 ./scripts/build_workspace.sh
```

CMake options: `MACC_WITH_IPOPT` (ON), `MACC_BUILD_TESTS` (ON), `MACC_BUILD_CONVERGENCE_CHECK` (ON; the exporter of
`experiments/convergence_check`), `MACC_NUMERICAL_JACOBIANS` (OFF; lets g2o differentiate the edges numerically, only
for debugging analytic Jacobians).

Binaries are linked with `RPATH`, so `build/macc/bin/macc_run` runs in any shell without sourcing `setup_env.sh`.

Verify:

```bash
ctest --test-dir build/macc --output-on-failure      # nlp_derivatives, solver_consistency_N3, solver_consistency_N15
./scripts/test_build_workflows.sh                    # build-script tests, no network
```

## 4. After editing cg2o

```bash
./scripts/rebuild_cg2o.sh                            # incremental cg2o build + install, then MACC
./scripts/rebuild_cg2o.sh --library-only | --application-only | --clean
```

## Troubleshooting

* **First error first.** `./scripts/build_status.sh` shows which sources and installs are used.
* **`cg2o headers missing`** — the installed cg2o is an older layout; `./scripts/build_externals.sh --cg2o-only --clean`.
* **An optional linear solver is `NO` in `macc_run --list-solvers`** — the corresponding cg2o target was not built
  (PARDISO needs Intel MKL). A missing solver is never replaced silently; asking for it is an error.
* **`ipopt_settings.use_hsl is true, but libcoinhsl.so was not found`** — build HSL first (`externals/README.md`), or
  set `ipopt_settings.hsl_library` to an existing `libcoinhsl.so`.
* **Cholesky-type solvers fail on the full problem** — the KKT matrix is indefinite. Use `umfpack`/`eigen_lu`,
  or `qdldlt`, or add `--set cg2o.equality_regularization=1e-8` to make LDL^T-type solvers work (docs/EXPERIMENTS.md).
* **WSL**: build inside the Linux file system (`~/`) rather than `/mnt/c/...`; compiling and, above all, the file
  writes of long experiments are much slower on the Windows drives.
