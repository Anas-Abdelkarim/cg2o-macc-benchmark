#!/usr/bin/env bash
# Build only MACC CMake app; never rebuild externals implicitly.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
CLEAN=0; CONFIGURE_ONLY=0
CMAKE_EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean) CLEAN=1; shift ;;
    --configure-only) CONFIGURE_ONLY=1; shift ;;
    -h|--help)
      cat <<'HELP'
Usage: ./scripts/build_workspace.sh [--clean] [--configure-only] [-- -DNAME=VALUE ...]

--clean           remove only the MACC application's CMake build (keep all externals)
--configure-only  check CMake configuration without compiling
Extra options following -- are forwarded to cmake -S ... -B ...
Environment: BUILD_TYPE, JOBS, MACC_BUILD_DIR, CXX (e.g. CXX=g++-11)
CMake options (pass after --): -DMACC_WITH_IPOPT=OFF  -DMACC_BUILD_TESTS=OFF
                               -DMACC_NUMERICAL_JACOBIANS=ON
IPOPT is picked up from install/externals/ipopt (./scripts/build_externals.sh
--ipopt-only) first, then from the system package (libipopt-dev).
HELP
      exit 0 ;;
    --) shift; CMAKE_EXTRA=("$@"); break ;;
    *) echo "ERROR: Unknown option: $1" >&2; exit 2 ;;
  esac
done
if [[ "$CLEAN" == 1 ]]; then "$ROOT/scripts/clean_build.sh"; fi
set --                       # options were parsed above; setup_env.sh takes no arguments
# shellcheck disable=SC1091
source "$ROOT/scripts/setup_env.sh"
[[ -n "${g2o_DIR:-}" ]] || { echo 'ERROR: local g2o is not installed. Run ./scripts/build_externals.sh --solver-only' >&2; exit 1; }
[[ -n "${cg2o_DIR:-}" ]] || { echo 'ERROR: local cg2o is not installed. Run ./scripts/build_externals.sh --solver-only' >&2; exit 1; }
# Fail before launching a lengthy C++ compilation if the installed cg2o
# package was built without its public headers. Its modern include layout is
# <prefix>/include/cg2o/core, not the legacy consolver/ directory.
if [[ ! -f "$MACC_CG2O_PREFIX/include/cg2o/core/base_fixed_sized_edge_eq.h" ]]; then
  echo "ERROR: cg2o headers missing from $MACC_CG2O_PREFIX/include/cg2o/core" >&2
  echo 'Expected base_fixed_sized_edge_eq.h. Reinstall cg2o with:' >&2
  echo '  ./scripts/build_externals.sh --cg2o-only --clean' >&2
  echo "Check the cg2o source (CG2O_DIR or externals/cg2o) if it still uses the old consolver layout." >&2
  exit 1
fi
CMAKE_GEN=()
if [[ -n "${CMAKE_GENERATOR:-}" ]]; then CMAKE_GEN=(-G "$CMAKE_GENERATOR")
elif command -v ninja >/dev/null 2>&1; then CMAKE_GEN=(-G Ninja); fi
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: JOBS must be positive integer' >&2; exit 2; }
# Eigen's allocator depends on -march; MACC must use the same setting as the installed g2o.
G2O_MARCH="$(sed -n 's/^march_native=//p' "$MACC_G2O_PREFIX/.macc_install_complete" 2>/dev/null | head -n1)"
[[ "$G2O_MARCH" == ON || "$G2O_MARCH" == OFF ]] || { echo "WARNING: cannot read march_native of g2o; assuming OFF" >&2; G2O_MARCH=OFF; }
echo "Configuring MACC application: $MACC_BUILD_DIR   (-march=native: $G2O_MARCH, same as g2o)"
cmake -S "$ROOT" -B "$MACC_BUILD_DIR" "${CMAKE_GEN[@]}" \
  -DCMAKE_BUILD_TYPE="${BUILD_TYPE:-Release}" \
  -Dg2o_DIR="$g2o_DIR" -Dcg2o_DIR="$cg2o_DIR" \
  -DMACC_CG2O_PREFIX="$MACC_CG2O_PREFIX" \
  -DMACC_MARCH_NATIVE="$G2O_MARCH" \
  "${CMAKE_EXTRA[@]}"
if [[ "$CONFIGURE_ONLY" == 1 ]]; then
  echo 'CMake configuration completed; compilation skipped.'
  exit 0
fi
cmake --build "$MACC_BUILD_DIR" --parallel "$JOBS"
echo "MACC built. Binary: $MACC_BUILD_DIR/bin/macc_run   (tests: ctest --test-dir $MACC_BUILD_DIR)"
