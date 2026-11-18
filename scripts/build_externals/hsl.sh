#!/usr/bin/env bash
# HSL linear solvers for IPOPT (MA27, MA57, MA77, MA86, MA97)  ->  install/externals/hsl/lib/.../libcoinhsl.so
#
#   ./scripts/build_externals/hsl.sh [--clean]          (source found in externals/, see externals/README.md)
#   HSL_SOURCE=<coinhsl-*.tar.gz or unpacked dir> ./scripts/build_externals/hsl.sh
#
# The Coin-HSL source is licensed (free for academic use: https://licences.stfc.ac.uk/product/coin-hsl) and is
# therefore not part of this repository. It is built with meson as a separate library; IPOPT is NOT rebuilt:
# IPOPT 3.14 loads the library at run time when ipopt_settings.use_hsl is true (config/config.yaml), so the
# MUMPS results of the IPOPT build stay unchanged. BLAS/LAPACK: Intel MKL when present, otherwise the system's.
# --clean  removes install/externals/hsl and the build folder first.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

# Source: HSL_SOURCE, else the newest coinhsl-* archive or folder in externals/ (or an earlier unpacked copy)
if [[ -z "${HSL_SOURCE:-}" ]]; then
  HSL_SOURCE="$(ls -d "$EXTERNALS"/coinhsl-*.tar.gz "$EXTERNALS"/coinhsl-*/ "$EXTERNALS"/hsl/coinhsl-*/ 2>/dev/null \
                | sed 's:/$::' | tail -n1)"
fi
HSL_INSTALL_DIR="$INSTALL_ROOT/hsl"
HSL_SRC_ROOT="$EXTERNALS/hsl"
CLEAN=0
for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown hsl option: $arg" ;;
  esac
done
[[ -n "$HSL_SOURCE" && -e "$HSL_SOURCE" ]] || die "No Coin-HSL source found: put coinhsl-<version>.tar.gz into externals/ or set HSL_SOURCE (see externals/README.md)"
if [[ "$CLEAN" == 1 ]]; then
  if [[ "$(realpath -m "$HSL_SOURCE")" == "$(realpath -m "$HSL_SRC_ROOT")"/* ]]; then
    echo "Removing $HSL_INSTALL_DIR (the source in $HSL_SRC_ROOT is kept)"; rm -rf -- "$HSL_INSTALL_DIR"
  else
    echo "Removing $HSL_INSTALL_DIR and $HSL_SRC_ROOT"; rm -rf -- "$HSL_INSTALL_DIR" "$HSL_SRC_ROOT"
  fi
fi

banner "HSL (Coin-HSL) from $HSL_SOURCE"
command -v gfortran >/dev/null || die "gfortran is required"
if ! command -v meson >/dev/null; then
  venv="$EXTERNALS/ipopt/meson-venv"
  [[ -x "$venv/bin/meson" ]] || { python3 -m venv "$venv" && "$venv/bin/pip" install -q meson; } || die "cannot install meson"
  export PATH="$venv/bin:$PATH"
fi

mkdir -p "$HSL_SRC_ROOT"
if [[ -d "$HSL_SOURCE" ]]; then
  src="$HSL_SRC_ROOT/$(basename "$HSL_SOURCE")"
  [[ -d "$src" ]] || cp -r "$HSL_SOURCE" "$src" || die "copy failed"
else
  name="$(basename "$HSL_SOURCE" .tar.gz)"; src="$HSL_SRC_ROOT/$name"
  [[ -d "$src" ]] || tar -xf "$HSL_SOURCE" -C "$HSL_SRC_ROOT" || die "HSL source extraction failed"
  [[ -d "$src" ]] || src="$(find "$HSL_SRC_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n1)"
fi
[[ -f "$src/meson.build" ]] || die "$src has no meson.build (Coin-HSL 2023.11 or newer is needed)"

MKL_ROOT="${MKLROOT:-/opt/intel/oneapi/mkl/latest}"
MKL_LIB="$MKL_ROOT/lib/intel64"; [[ -d "$MKL_LIB" ]] || MKL_LIB="$MKL_ROOT/lib"
BLAS_ARGS=()
if [[ "${WITH_MKL:-ON}" == ON && -f "$MKL_LIB/libmkl_rt.so" ]]; then
  BLAS_ARGS=(-Dlibblas=mkl_rt -Dliblapack=mkl_rt -Dlibblas_path="$MKL_LIB" -Dliblapack_path="$MKL_LIB")
  echo "BLAS/LAPACK: Intel MKL (libmkl_rt) at $MKL_LIB"
else
  echo "BLAS/LAPACK: system"
fi
MARCH_ARGS=(); [[ "$MARCH_NATIVE" != ON ]] || MARCH_ARGS=(-Dfortran_args=-march=native -Dc_args=-march=native)

rm -rf "$src/builddir"
( cd "$src" && meson setup builddir --buildtype=release --prefix="$HSL_INSTALL_DIR" "${BLAS_ARGS[@]}" "${MARCH_ARGS[@]}" \
  && meson compile -C builddir -j "$JOBS" && meson install -C builddir ) || die "HSL build failed"

lib="$(find "$HSL_INSTALL_DIR" -name 'libcoinhsl.so' | head -n1)"
[[ -n "$lib" ]] || die "libcoinhsl.so missing after the build"
echo; echo "Installed $lib"
echo "Use it with:  macc_run --set ipopt_settings.use_hsl=true   (or set use_hsl: true in config/config.yaml)"
