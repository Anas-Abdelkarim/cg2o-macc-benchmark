#!/usr/bin/env bash
# Incremental project-local g2o install.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
CLEAN=0; REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1; REBUILD=1 ;;
    --rebuild) REBUILD=1 ;;
    -h|--help) echo 'Usage: ./scripts/build_externals/g2o.sh [--rebuild] [--clean]'; exit 0 ;;
    *) die "Unknown g2o option: $arg" ;;
  esac
done
MARCH_NATIVE="${MARCH_NATIVE:-ON}"
[[ "$MARCH_NATIVE" == ON || "$MARCH_NATIVE" == OFF ]] || die 'MARCH_NATIVE must be ON or OFF'
ARCH_FLAGS=''; [[ "$MARCH_NATIVE" != ON ]] || ARCH_FLAGS='-march=native'
CMAKE_ARGS=("${GEN_ARGS[@]}"
  -DCMAKE_BUILD_TYPE="$BUILD_TYPE"
  -DCMAKE_INSTALL_PREFIX="$G2O_INSTALL_DIR"
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON
  "-DCMAKE_CXX_FLAGS=$ARCH_FLAGS"
  -DBUILD_WITH_MARCH_NATIVE="$MARCH_NATIVE"
  -DG2O_NO_IMPLICIT_OWNERSHIP_OF_OBJECTS=ON
  -DG2O_USE_OPENMP="${G2O_OPENMP:-ON}"
  -DG2O_BUILD_APPS=OFF -DG2O_BUILD_EXAMPLES=OFF -DG2O_USE_OPENGL=OFF
  -DG2O_USE_CHOLMOD=ON -DG2O_USE_CSPARSE=ON
  -DG2O_FAST_MATH=OFF -DBUILD_UNITTESTS=OFF
)
HASH="$(config_hash "source=$G2O_DIR" "ref=$G2O_REF" "${CMAKE_ARGS[@]}")"
banner 'Build external: g2o (local)'
if [[ "$CLEAN" == 0 && "$REBUILD" == 0 ]] \
  && [[ -n "$(find_cmake_config "$G2O_INSTALL_DIR" g2oConfig.cmake)" ]] \
  && g2o_has_solvers \
  && marker_matches "$G2O_INSTALL_DIR/.macc_install_complete" "$G2O_DIR" "$HASH"; then
  echo "g2o already installed with these settings: $G2O_INSTALL_DIR"
  exit 0
fi
clone_missing_source "$G2O_URL" "$G2O_DIR" "$G2O_REF"
patch_g2o_for_cg2o
if [[ "$CLEAN" == 1 ]]; then
  echo 'Cleaning only g2o build and install trees.'
  rm -rf -- "$G2O_BUILD_DIR" "$G2O_INSTALL_DIR"
fi
prepare_build_dir "$G2O_BUILD_DIR" "$HASH"
cmake -S "$G2O_DIR" -B "$G2O_BUILD_DIR" "${CMAKE_ARGS[@]}"
cmake --build "$G2O_BUILD_DIR" --parallel "$JOBS"
mark_complete "$G2O_BUILD_DIR/.macc_build_complete" "$G2O_DIR" "$HASH"
# Replacing the install prefix prevents old libraries from persisting.
rm -rf -- "$G2O_INSTALL_DIR"
cmake --install "$G2O_BUILD_DIR"
[[ -n "$(find_cmake_config "$G2O_INSTALL_DIR" g2oConfig.cmake)" ]] || die "g2o built, but installed no g2oConfig.cmake under $G2O_INSTALL_DIR"
g2o_has_solvers || die "g2o installed without CHOLMOD/CSparse solver libraries. Install libsuitesparse-dev and use the tested g2o revision (default G2O_REF=eec325a1)."
mark_complete "$G2O_INSTALL_DIR/.macc_install_complete" "$G2O_DIR" "$HASH"
echo "g2o ready: $G2O_INSTALL_DIR"
