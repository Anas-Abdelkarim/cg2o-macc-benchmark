# Quickstart: from a clean Ubuntu to the paper's results

Tested on Ubuntu 22.04 (GCC 11.4) and Ubuntu 24.04 (GCC 13.3), x86-64. About 30–60 minutes for the build (IPOPT is
the longest part). On the paper's machine the experiments took about one hour, most of it Table VII. Everything is installed inside this folder
(`install/externals/`); nothing is installed into the system except the apt packages of step 1.

On WSL, keep the repository in the Linux file system (e.g. `~/MACC`), not under `/mnt/c/...`: builds and result
writing are much slower on the Windows drives.

## 1. System packages

```bash
sudo apt update
sudo apt install -y git build-essential gfortran cmake ninja-build pkg-config python3-pip python3-venv \
  libeigen3-dev libfmt-dev libyaml-cpp-dev libsuitesparse-dev libomp-dev \
  liblapack-dev libblas-dev libmetis-dev libhwloc-dev
python3 -m pip install -r experiments/requirements.txt     # numpy, matplotlib, PyYAML, pandas, scipy
./scripts/check_build_env.sh                                 # reports anything that is still missing
```

## 2. Get the code

```bash
git clone <this repository> MACC
cd MACC
```

## 3. Build the solvers: g2o, cg2o, IPOPT

```bash
./scripts/build_externals.sh
```

This builds, in order, and installs into `install/externals/`:

1. **g2o** — cloned into `externals/g2o` (revision `eec325a1`), built with `G2O_NO_IMPLICIT_OWNERSHIP_OF_OBJECTS=ON`.
2. **cg2o** — cloned from https://github.com/snt-arg/cg2o into `externals/cg2o` at the commit used for the paper
   (`b14da0c`, branch `dev`), built against the local g2o. To use your own checkout: `CG2O_DIR=/path/to/cg2o`.
3. **IPOPT 3.14.21** — built from source with coinbrew, with **MUMPS** as its linear solver. 3.14.21 has no release
   tag yet: the scripts fetch branch `stable/3.14` and check out commit `cc33071`, the version used for the paper.

Single components: `--solver-only` (g2o + cg2o), `--ipopt` (IPOPT only), `--cg2o-only`. `--clean` rebuilds the
selected components.

### Optional: HSL (only if you have a licence)

The paper's IPOPT results (Table V, Fig. 3) use the HSL solver MA57. Everything else works with MUMPS.

1. Get Coin-HSL from https://licences.stfc.ac.uk/product/coin-hsl (free for academic use).
2. Copy the archive into `externals/`, e.g. `externals/coinhsl-2024.05.15.tar.gz`.
3. Build with the switch on (default is `USE_HSL=OFF`):
   ```bash
   USE_HSL=ON ./scripts/build_externals.sh          # or, with IPOPT already built:  ./scripts/build_externals.sh --hsl
   ```
4. Use it: `--set ipopt_settings.use_hsl=true` for one run, or `use_hsl: true` in `config/config.yaml`.

Details: [externals/README.md](externals/README.md).

## 4. Build MACC and run the tests

```bash
./scripts/build_workspace.sh                          # -> build/macc/bin/macc_run
ctest --test-dir build/macc --output-on-failure       # 3 tests, a few seconds
```

The tests check the analytic derivatives of the problem and that cg2o and IPOPT reach the same optimum of the same
problem. A first short run:

```bash
python3 experiments/run_experiment.py fig2 --quick     # 300 MPC steps, about a minute
```

## 5. Reproduce the paper (Sec. VI)

Run all commands from the repository root. Close other programs: timings are measured on one thread. Each
command writes a folder
`results/experiments/<date>_<name>/` with `experiment_info.txt`, which compares the run with the paper's numbers.

```bash
# Table IV and Fig. 2: cg2o vs the barrier IPM, feasible start, N = 3, 15, 30            (~1 min)
python3 experiments/run_experiment.py fig2

# Table V and Figs. 3, 4: cg2o vs IPOPT (cold and warm start), N = 3, 15, 30              (~2 min)
python3 experiments/run_experiment.py fig3 --set ipopt_settings.use_hsl=true   # with HSL MA57, as in the paper
python3 experiments/run_experiment.py fig3                                      # without HSL: IPOPT with MUMPS

# Fig. 7: linear solvers inside cg2o, 500 MPC problems, N = 3 and 30  Failed solvers are out             (~1 min)
python3 experiments/run_experiment.py linear-solvers --measure converged --run-times 1 --hide-failed \
    --solvers 0,1,3,6,13,14,16,18 --horizons 3 30

# Table VII: large-scale problems (N = 30 000 and 300 000), 10 iterations each           (~50 min)
python3 experiments/run_experiment.py linear-solvers --measure fixed --max-iter 10 --steps 2 --timeout 0 --hide-failed \
    --linear-solver 14 16reg 0reg 1reg 6 6reg 13 13reg 18 --horizons 30000 300000
```

PARDISO (solver 13) is only available if cg2o was built with Intel MKL
(`ENABLE_PARDISO=ON ./scripts/build_externals.sh --cg2o-only --clean`, then `./scripts/build_workspace.sh`);
otherwise it is skipped.

Every run writes the paper's table and figures into its own folder (the run prints their paths at the end); the
other figures in `figures/` (`*_overview*`) are per-step overviews that are not in the paper:

| run | table | figures (in `figures/`) |
|---|---|---|
| `fig2` | `paper_table_iv.txt` | `paper_fig2_macc_vs_bipm.pdf` |
| `fig3` | `paper_table_v.txt` | `paper_fig3_macc_vs_ipopt.pdf`, `paper_fig4_macc_trajectory.pdf` |
| `linear-solvers` (N = 3, 30) | | `paper_fig7_linear_solver_comparison.pdf` |

To make them again, from chosen runs, or for Table VII (without arguments the newest complete runs are used;
`--quick` runs are skipped; each script prints the folder it used):

```bash
python3 paper/analysis/paper_tables.py                       # Tables IV and V (newest complete runs)
python3 paper/analysis/paper_tables.py --fig3 results/experiments/<fig3 folder>           # one particular run
python3 paper/analysis/paper_tables.py --large results/experiments/<large-scale folder>   # + Table VII
python3 paper/analysis/paper_figures.py                      # Figs. 2, 3, 4, 7 -> results/paper_figures/
```

Local convergence analysis (Sec. VI-E, ρ at every solution): see
[experiments/convergence_check/README.md](experiments/convergence_check/README.md).

### What you should get

* **Iteration counts:** cg2o 13.0 / 14.9 / 15.7 (Table IV) and 13.2 / 15.1 / 15.9 (Table V) iterations on average
  for N = 3 / 15 / 30; with HSL MA57 also IPOPT's 19.5 / 22.5 / 27.6 (cold) and 12.8 / 17.6 / 19.8 (warm), exactly,
  problem by problem. With MUMPS, IPOPT's counts differ slightly from the paper's. The barrier IPM of Table IV varies
  slightly from run to run (averages within ±0.1; see "Reproducibility" in docs/EXPERIMENTS.md).
* **Times depend on the machine.** The paper used an Intel Core i9-12900H. Compare the ratios between the solvers.
  For timing worth quoting, solve every problem several times (`--run-times 10`) and pin the run to fast cores, e.g.
  `taskset -c 0,2,4 python3 experiments/run_experiment.py fig3 --run-times 10`.

## 6. Tuning the solvers (optional, Sec. V-B and Table III)

The tuned settings of the paper are already in `config/config.yaml`; you need this step only to repeat or extend the
tuning. It uses its own Python environment (optuna), created once:

```bash
./scripts/setup_tuning_env.sh --test          # creates .venv-tuning/ and runs the tuning library's tests
```

One study per solver, in `experiments/solver_tuning/studies/`:

```bash
./scripts/tune.sh run experiments/solver_tuning/studies/bipm.yaml       --out results/tuning/bipm       --trials 3000
./scripts/tune.sh run experiments/solver_tuning/studies/ipopt_cold.yaml --out results/tuning/ipopt_cold --trials 300
./scripts/tune.sh run experiments/solver_tuning/studies/ipopt_warm.yaml --out results/tuning/ipopt_warm --trials 300
./scripts/tune.sh run experiments/solver_tuning/studies/ispd.yaml       --out results/tuning/ispd       --trials 150

./scripts/tune.sh status results/tuning/<stamp>_bipm     # progress and best trials, also while it runs
./scripts/tune.sh plot   results/tuning/<stamp>_bipm     # figures of the search
```

What a study does: it measures the current setting of `config/config.yaml` (the baseline), proposes new settings with
Bayesian optimization (TPE, `seed: 1`), runs each on N = 3, 15, 30 over 300 MPC steps, rejects every setting that
violates a quality limit (residuals, failed solves, steps at the iteration limit, cost against the reference solver),
and validates the best ones on the whole driving cycle. The score is the mean iteration count relative to the
baseline. Results in `results/tuning/<stamp>_<name>/`:

* `report.txt` — what changed against the baseline and by how much;
* `selected_config.yaml` — the winning setting (copy it into `config/config.yaml`, then rerun `fig2` / `fig3`);
* `trials.csv` — every trial with its parameters, score and, if rejected, the reason.

A study starts from the values in `config/config.yaml`, which are already the tuned ones; it therefore checks and
refines them rather than starting from the solvers' defaults. Do not rebuild `macc_run` while a study runs. Details:
[docs/TUNING.md](docs/TUNING.md).

## 7. Everyday commands

```bash
build/macc/bin/macc_run --solvers ispd,ipopt --horizon 15 --loop-size 200      # one closed-loop run
build/macc/bin/macc_run --list-solvers                                          # linear solvers of cg2o
python3 experiments/run_experiment.py fig3 --quick --linear-solver umfpack     # another linear solver
python3 experiments/run_experiment.py fig2 --set mpc.number_of_iterations=200  # change any setting
python3 experiments/run_experiment.py replot results/experiments/<folder>      # redraw without re-running
python3 experiments/run_experiment.py --help                                   # all presets and options
```

After changing cg2o: `./scripts/rebuild_cg2o.sh` (cg2o, then MACC). After changing MACC:
`./scripts/build_workspace.sh && ctest --test-dir build/macc`.

More: [INSTALL.md](INSTALL.md) (build details, troubleshooting), [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)
(all presets and options), [docs/TUNING.md](docs/TUNING.md) (solver tuning).
