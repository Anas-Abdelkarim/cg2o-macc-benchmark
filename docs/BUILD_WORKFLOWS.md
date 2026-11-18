# MACC build workflows

The build consists of a component dispatcher
(`build_externals.sh`), component scripts (`build_externals/{g2o,cg2o,ipopt,hsl}.sh`),
a sourced environment (`setup_env.sh`), a project build (`build_workspace.sh`),
status/preflight commands, a short incremental cg2o development loop
(`rebuild_cg2o.sh`). The experiments are run with Python (`experiments/run_experiment.py`).

## Default source priority

```text
CG2O_DIR explicitly set?       YES -> use exactly that source (clone there if absent)
             |
             NO
             v
externals/cg2o valid?          YES -> use project-local checkout (as it is)
             |
             NO
             v
clone snt-arg/cg2o.git -> externals/cg2o, check out CG2O_REF
(default b14da0c of branch dev: the version used for the paper)
```

Only a source containing `CMakeLists.txt` is accepted. An existing checkout is never reset, fetched or
checked out; only a fresh clone is pinned. g2o is cloned to `externals/g2o` at `G2O_REF` (default `eec325a1`).

HSL: `USE_HSL=ON ./scripts/build_externals.sh` (or `--hsl` alone) builds the licensed Coin-HSL library from
`externals/coinhsl-*` (see `externals/README.md`). The default is `USE_HSL=OFF`: IPOPT uses MUMPS.

## Typical commands

| Goal | Command |
| --- | --- |
| Build all externals (g2o, cg2o, IPOPT) | `./scripts/build_externals.sh` |
| ... and HSL (licensed source in `externals/`) | `USE_HSL=ON ./scripts/build_externals.sh` |
| Only g2o + cg2o | `./scripts/build_externals.sh --solver-only` |
| Only IPOPT | `./scripts/build_externals.sh --ipopt [--source \| --system]` (`--source` is the default) |
| Run a paper experiment | `python3 experiments/run_experiment.py fig2 \| fig3 \| linear-solvers` |
| Build only cg2o | `./scripts/build_externals.sh --cg2o-only` |
| Build only g2o | `./scripts/build_externals.sh --only=g2o` |
| Rebuild g2o after edits | `./scripts/build_externals/g2o.sh --rebuild` |
| Clean/rebuild cg2o only | `./scripts/build_externals/cg2o.sh --clean` |
| Incremental cg2o + MACC rebuild | `./scripts/rebuild_cg2o.sh` |
| Clean cg2o + MACC outputs, keep g2o | `./scripts/rebuild_cg2o.sh --clean` |
| Rebuild cg2o only | `./scripts/rebuild_cg2o.sh --library-only` |
| Rebuild MACC only | `./scripts/rebuild_cg2o.sh --application-only` |
| Clean the MACC application only | `./scripts/build_workspace.sh --clean` |
| Remove MACC build without building | `./scripts/clean_build.sh` |
| Activate local dependencies | `source scripts/setup_env.sh` |
| Inspect installed packages and cg2o path | `./scripts/build_status.sh` |
| Check core toolchain | `./scripts/check_build_env.sh` |
| Test scripts offline without downloads | `./scripts/test_build_workflows.sh` |

`--full` and the default invocation of `build_externals.sh` both mean g2o + cg2o + IPOPT.

## Build/clean boundaries

* `g2o.sh --clean` deletes only `build/externals/g2o` and
  `install/externals/g2o`. **Rebuild cg2o after changing g2o**.
* `cg2o.sh --clean` deletes only `build/externals/cg2o` and
  `install/externals/cg2o`.
* `build_workspace.sh --clean` deletes only `build/macc`.
* None of these options removes source checkouts under `externals/` or an explicit `CG2O_DIR`.
* `scripts/setup_env.sh` can be sourced repeatedly without duplicated paths.
* g2o and cg2o install into project-local prefixes. `cg2o.sh` passes the
  installed **local** `g2o_DIR` explicitly, checks the CMake cache, and refuses
  a system g2o fallback.
* `MARCH_NATIVE=ON` can make solver binaries CPU-specific. cg2o checks that
  its flag matches the local g2o build.

## Offline testing

`scripts/test_build_workflows.sh` supplies mocked `git` and `cmake`; it checks
predefined cg2o precedence, cloning exactly once when missing, existing-checkout
reuse, explicit overrides, incremental calls, isolated clean, environment
idempotence, and CMake arguments. These checks do not establish C++ ABI/API
compatibility or a successful native application compilation.

## Real-build troubleshooting

Start with `./scripts/build_status.sh` and read the **first** CMake/compiler error. Common issues are a missing
`libsuitesparse-dev`, incompatible g2o and cg2o revisions, a custom cg2o project without proper CMake install/export
rules, and a stale `build/macc` configured against an older install (`./scripts/build_workspace.sh --clean`).
Do not fix these by pointing at `/usr/local` copies of unrelated solver builds.

## cg2o header layout

MACC uses the installed layout of current cg2o (`<cg2o/core/...>`, namespace `cg2o::`, exported targets `cg2o::cg2o` and
`cg2o::core`) and the public API of the `dev` branch. `build_workspace.sh` checks that
`install/externals/cg2o/include/cg2o/core/base_fixed_sized_edge_eq.h` exists before it starts compiling; if not:

```bash
./scripts/build_externals.sh --cg2o-only --clean
./scripts/build_workspace.sh --clean
```

`--clean` on the cg2o script removes only cg2o build/install artifacts and preserves the local source and the g2o
installation. Modern cg2o requires C++20.

## What is tested

* `scripts/test_build_workflows.sh` — control flow of the scripts with mocked `git`/`cmake`.
* `ctest --test-dir build/macc` — derivatives of the NLP, and ISPD-IPM vs native IPOPT on the same problem (see `tests/README.md`).
* A clean configure, build and test with GCC 13.3 and GCC 11.4.

Not tested: `build_externals.sh --ipopt --source` (no access to GitHub while this was prepared).
