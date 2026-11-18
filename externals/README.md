# externals/

Source trees of the third-party components. Everything in this folder except this file is ignored by git: the
build scripts clone or unpack the sources here and install the libraries into `install/externals/`.

| folder | created by | content |
|---|---|---|
| `g2o/` | `./scripts/build_externals.sh` | g2o, cloned at revision `eec325a1` |
| `cg2o/` | `./scripts/build_externals.sh` | cg2o, cloned from `snt-arg/cg2o`, branch `dev`, commit `b14da0c` (the version of the paper) |
| `ipopt/` | `./scripts/build_externals.sh` | IPOPT 3.14 (coinbrew), with MUMPS |
| `hsl/` | `USE_HSL=ON ./scripts/build_externals.sh` | the unpacked Coin-HSL source (only if you provide it, see below) |

To use your own cg2o checkout instead of the clone, set `CG2O_DIR=/path/to/cg2o`.

## HSL (optional, licensed)

IPOPT uses **MUMPS** by default, and everything in this repository runs with MUMPS. The paper's Table V and Fig. 3
were measured with IPOPT using the HSL solver **MA57**. HSL is licensed software, so it cannot be distributed here.
If you have a licence:

1. Download Coin-HSL from https://licences.stfc.ac.uk/product/coin-hsl (free for academic use), for example
   `coinhsl-2024.05.15.tar.gz`. Version 2023.11 or newer is needed (meson build).
2. Put the archive, or the unpacked folder, into this folder:
   ```
   externals/coinhsl-2024.05.15.tar.gz
   ```
3. Build it. Either set the switch for the whole externals build:
   ```bash
   USE_HSL=ON ./scripts/build_externals.sh            # g2o, cg2o, IPOPT and HSL
   ```
   or, if IPOPT is already built, only HSL:
   ```bash
   ./scripts/build_externals.sh --hsl
   ```
   You can also change the default `USE_HSL="${USE_HSL:-OFF}"` at the top of `scripts/build_externals.sh`.
   The library is installed as `install/externals/hsl/lib/<arch>/libcoinhsl.so`; IPOPT is not rebuilt.
4. Tell IPOPT to use it, in `config/config.yaml`:
   ```yaml
   ipopt_settings:
     use_hsl: true        # false: MUMPS (default)
     hsl_solver: ma57     # ma27, ma57, ma77, ma86, ma97
   ```
   or for a single run: `--set ipopt_settings.use_hsl=true`.

Without the library, `use_hsl: true` stops with a message that says what is missing.
