#!/usr/bin/env bash
# Incremental cg2o build. An existing checkout is used as it is; otherwise cg2o is cloned at the paper's commit.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
CLEAN=0
for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    -h|--help)
      cat <<'HELP'
Usage: ./scripts/build_externals/cg2o.sh [--clean]

Source priority:
  1. CG2O_DIR (explicit checkout path)
  2. <MACC>/externals/cg2o
  3. Clone CG2O_URL into <MACC>/externals/cg2o and check out CG2O_REF
     (default: commit b14da0c of branch dev, the version used for the paper)

Existing checkout content is NEVER overwritten, moved or checked out.
--clean removes ONLY cg2o build + install artifacts, not its source or g2o.
HELP
      exit 0 ;;
    *) die "Unknown cg2o option: $arg" ;;
  esac
done
resolve_cg2o_source
# Resolve/clone before depending on g2o, so a standalone run reports the
# selected repository clearly even if g2o is not installed yet.
clone_missing_source "$CG2O_URL" "$CG2O_DIR" "$CG2O_REF"
require_local_g2o
[[ "$MARCH_NATIVE" == ON || "$MARCH_NATIVE" == OFF ]] || die 'MARCH_NATIVE must be ON or OFF'
ARCH_FLAGS=''; [[ "$MARCH_NATIVE" != ON ]] || ARCH_FLAGS='-march=native'
if grep -Eq '^[[:space:]]*project[[:space:]]*\([[:space:]]*example([[:space:]]|\))' "$CG2O_DIR/CMakeLists.txt"; then
  LAYOUT=example
elif grep -Eqi '^[[:space:]]*project[[:space:]]*\([[:space:]]*cg2o([[:space:]]|\))' "$CG2O_DIR/CMakeLists.txt"; then
  LAYOUT=standalone
else
  LAYOUT=custom
  echo "NOTE: Custom cg2o project at $CG2O_DIR; installation must export cg2oConfig.cmake."
fi
CMAKE_ARGS=("${GEN_ARGS[@]}"
  -DCMAKE_BUILD_TYPE="$BUILD_TYPE"
  -DCMAKE_INSTALL_PREFIX="$CG2O_INSTALL_DIR"
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON
  "-DCMAKE_CXX_FLAGS=$ARCH_FLAGS"
  -DCMAKE_PREFIX_PATH="$G2O_INSTALL_DIR"
  -Dg2o_DIR="$G2O_CMAKE_DIR"
  -DG2O_INCLUDE_DIRS="$G2O_INSTALL_DIR/include"
  -DG2O_LIBRARY_DIRS="$G2O_INSTALL_DIR/lib"
  -DUSE_G2O_SOLVERS=ON
)
if [[ "$LAYOUT" == standalone ]]; then
  CMAKE_ARGS+=(-DCG2O_BUILD_EXAMPLES=OFF -DCG2O_BUILD_PARDISO="${ENABLE_PARDISO:-OFF}" -DCG2O_BUILD_EIGEN_SOLVERS=ON)
else
  CMAKE_ARGS+=(-DG2O_BUILD_EXAMPLES=OFF -DG2O_BUILD_PARDISO="${ENABLE_PARDISO:-ON}" -DG2O_BUILD_UMFPACK=ON)
fi
# cg2o must always be recompiled incrementally; only its CMake reconfigure may
# be skipped. This is how edits to a local research checkout get picked up.
HASH="$(config_hash "source=$CG2O_DIR" "layout=$LAYOUT" "g2o=$(sha256sum "$G2O_BUILD_DIR/CMakeCache.txt" | cut -c1-16)" "${CMAKE_ARGS[@]}")"
banner "Build external: cg2o ($LAYOUT, incremental)"
echo "cg2o source : $CG2O_DIR"
echo "g2o config  : $G2O_CMAKE_DIR/g2oConfig.cmake"
echo "cg2o install: $CG2O_INSTALL_DIR"
if [[ "$CLEAN" == 1 ]]; then
  echo 'Cleaning only cg2o build/install (g2o and sources untouched).'
  rm -rf -- "$CG2O_BUILD_DIR" "$CG2O_INSTALL_DIR"
fi
previous="$(cat "$CG2O_BUILD_DIR/.macc_config" 2>/dev/null || true)"
prepare_build_dir "$CG2O_BUILD_DIR" "$HASH"
if [[ "$previous" == "$HASH" && -f "$CG2O_BUILD_DIR/CMakeCache.txt" ]]; then
  echo 'Reusing cg2o configuration; building changed files incrementally.'
else
  cmake -S "$CG2O_DIR" -B "$CG2O_BUILD_DIR" "${CMAKE_ARGS[@]}"
fi
# Don't allow a system g2o to sneak into a cg2o config.
selected="$(sed -n 's/^g2o_DIR:[^=]*=//p' "$CG2O_BUILD_DIR/CMakeCache.txt" | head -n1)"
[[ "$selected" == "$G2O_CMAKE_DIR" ]] || die "cg2o selected unexpected g2o_DIR: '${selected:-<unset>}' (expected $G2O_CMAKE_DIR)"
cmake --build "$CG2O_BUILD_DIR" --parallel "$JOBS"
mark_complete "$CG2O_BUILD_DIR/.macc_build_complete" "$CG2O_DIR" "$HASH"
# cmake --install each time, even when configuration is unchanged.
cmake --install "$CG2O_BUILD_DIR"
[[ -n "$(find_cmake_config "$CG2O_INSTALL_DIR" cg2oConfig.cmake)" ]] || die "cg2o built but installed no cg2oConfig.cmake under $CG2O_INSTALL_DIR. This local source needs install/export rules (not just library compilation)."
[[ -f "$CG2O_INSTALL_DIR/include/cg2o/core/base_fixed_sized_edge_eq.h" ]] || die "cg2o installed a config, but not modern headers at $CG2O_INSTALL_DIR/include/cg2o/core/. Ensure the local source is the current cg2o checkout (not legacy consolver)."
mark_complete "$CG2O_INSTALL_DIR/.macc_install_complete" "$CG2O_DIR" "$HASH"
echo "cg2o ready: $CG2O_INSTALL_DIR"
