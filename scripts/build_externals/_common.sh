#!/usr/bin/env bash
# Shared build machinery of the component scripts (sourced, not executed directly).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
EXTERNALS="$(realpath -m "${EXTERNALS:-$ROOT/externals}")"
BUILD_ROOT="$(realpath -m "${EXTERNAL_BUILD_ROOT:-$ROOT/build/externals}")"
INSTALL_ROOT="$(realpath -m "${EXTERNAL_INSTALL_ROOT:-$ROOT/install/externals}")"
BUILD_TYPE="${BUILD_TYPE:-Release}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"
MARCH_NATIVE="${MARCH_NATIVE:-ON}"
# Versions used for the paper. g2o: tested revision; cg2o: branch dev, commit of 2026-11-03 (QDLDLT refinement fix).
G2O_REF="${G2O_REF:-eec325a1}"
CG2O_REF="${CG2O_REF:-b14da0c969fa856f1daf8c3518b0e6101df9b4f0}"
G2O_URL="${G2O_URL:-https://github.com/RainerKuemmerle/g2o.git}"
CG2O_URL="${CG2O_URL:-https://github.com/snt-arg/cg2o.git}"

G2O_DIR="$(realpath -m "${G2O_DIR:-$EXTERNALS/g2o}")"
G2O_BUILD_DIR="$BUILD_ROOT/g2o"
G2O_INSTALL_DIR="$INSTALL_ROOT/g2o"
CG2O_BUILD_DIR="$BUILD_ROOT/cg2o"
CG2O_INSTALL_DIR="$INSTALL_ROOT/cg2o"

case "$INSTALL_ROOT" in /usr|/usr/*) echo "ERROR: Refusing system install prefix: $INSTALL_ROOT" >&2; exit 1 ;; esac
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: JOBS must be a positive integer' >&2; exit 2; }

banner() { printf '\n============================================================\n%s\n============================================================\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }
find_cmake_config() { local root="$1" name="$2"; find "$root" -type f -name "$name" -print -quit 2>/dev/null || true; }
config_hash() { printf '%s\n' "${CC:-}" "${CXX:-}" "$@" | sha256sum | cut -c1-16; }
marker_matches() { [[ -f "$1" ]] && grep -Fqx "source=$2" "$1" && grep -Fqx "config=$3" "$1"; }
mark_complete() { mkdir -p "$(dirname "$1")"; printf 'source=%s\nconfig=%s\nbuild_type=%s\nmarch_native=%s\n' "$2" "$3" "$BUILD_TYPE" "$MARCH_NATIVE" > "$1"; }
prepare_build_dir() { # directory, hash; keep incremental work if flags unchanged
  local target="$1" hash="$2" previous
  previous="$(cat "$target/.macc_config" 2>/dev/null || true)"
  if [[ -d "$target" && "$previous" != "$hash" ]]; then
    echo "Changed CMake configuration; cleaning obsolete build tree: $target"
    rm -rf -- "$target"
  fi
  mkdir -p "$target"
  printf '%s\n' "$hash" > "$target/.macc_config"
}
choose_generator() {
  GEN_ARGS=()
  if [[ -n "${CMAKE_GENERATOR:-}" ]]; then GEN_ARGS=(-G "$CMAKE_GENERATOR")
  elif command -v ninja >/dev/null 2>&1; then GEN_ARGS=(-G Ninja)
  fi
}
choose_generator

# For cg2o build, derive CPU mode from the already-built g2o if not specified.
# Never silently mix Eigen ABI settings between the two.
follow_g2o_march() {
  local cache="$G2O_BUILD_DIR/CMakeCache.txt" selected
  if [[ -f "$cache" ]]; then
    selected="$(sed -n 's/^BUILD_WITH_MARCH_NATIVE:BOOL=//p' "$cache" | head -n1)"
    [[ -n "$selected" ]] || die "Cannot read g2o BUILD_WITH_MARCH_NATIVE from $cache"
    if [[ -n "$MARCH_NATIVE" && "$MARCH_NATIVE" != "$selected" ]]; then
      die "MARCH_NATIVE=$MARCH_NATIVE mismatches local g2o ($selected); rebuild g2o first."
    fi
    MARCH_NATIVE="$selected"
  else
    MARCH_NATIVE="${MARCH_NATIVE:-OFF}"
  fi
}

# Existing source checkouts (including custom trees without .git) are NEVER
# reset, fetched or checked out. A newly cloned tree can be pinned to a ref.
clone_missing_source() { # source-url, target-path, optional-ref
  local url="$1" dir="$2" ref="${3:-}"
  if [[ -f "$dir/CMakeLists.txt" ]]; then
    echo "Using existing local repository: $dir"
    return 0
  fi
  if [[ -e "$dir" ]]; then
    die "Source directory exists but lacks CMakeLists.txt: $dir (not overwriting it)."
  fi
  command -v git >/dev/null 2>&1 || die 'git is required to clone external sources.'
  mkdir -p "$(dirname "$dir")"
  echo "No local source at $dir; cloning $url"
  git clone --recursive "$url" "$dir" || die "Cannot clone $url to $dir"
  if [[ -n "$ref" ]]; then git -C "$dir" checkout "$ref" || die "Cannot checkout ref $ref at $dir"; fi
}

# Resolution is fixed and deterministic:
#   1. CG2O_DIR (an existing checkout, used as it is)
#   2. externals/cg2o (an earlier clone)
#   3. clone CG2O_URL into externals/cg2o and check out CG2O_REF
resolve_cg2o_source() {
  if [[ -n "${CG2O_DIR:-}" ]]; then
    CG2O_DIR="$(realpath -m "$CG2O_DIR")"
    echo "Explicit cg2o source selected: $CG2O_DIR"
  else
    CG2O_DIR="$EXTERNALS/cg2o"
    if [[ -f "$CG2O_DIR/CMakeLists.txt" ]]; then
      echo "Using project-local cg2o repository: $CG2O_DIR"
    fi
  fi
}

# CMake should consume this workspace's g2o, never the unrelated system copy.
require_local_g2o() {
  local config
  config="$(find_cmake_config "$G2O_INSTALL_DIR" g2oConfig.cmake)"
  [[ -n "$config" ]] || die "Local g2o not installed in $G2O_INSTALL_DIR. Run ./scripts/build_externals/g2o.sh"
  G2O_CMAKE_DIR="$(dirname "$config")"
  [[ -f "$G2O_BUILD_DIR/CMakeCache.txt" ]] || die "g2o cache missing: $G2O_BUILD_DIR/CMakeCache.txt. Rebuild local g2o first."
  grep -q '^G2O_NO_IMPLICIT_OWNERSHIP_OF_OBJECTS:BOOL=ON' "$G2O_BUILD_DIR/CMakeCache.txt" || die 'g2o must be compiled with G2O_NO_IMPLICIT_OWNERSHIP_OF_OBJECTS=ON.'
  follow_g2o_march
}

g2o_has_solvers() {
  local dep
  for dep in solver_cholmod solver_csparse; do
    find "$G2O_INSTALL_DIR" -type f -name "libg2o_${dep}*" -print -quit 2>/dev/null | grep -q . || return 1
  done
}

# cg2o compatibility patch: makes SparseOptimizer::update() virtual in a g2o checkout that still has the
# non-virtual declaration. Other forms of the declaration are left unchanged.
patch_g2o_for_cg2o() {
  local header="$G2O_DIR/g2o/core/sparse_optimizer.h"
  [[ -f "$header" ]] || { echo "WARNING: g2o patch skipped: missing $header" >&2; return 0; }
  if grep -Fqx '  void update(const double* update);' "$header"; then
    echo 'Applying legacy cg2o compatibility patch to g2o SparseOptimizer::update()'
    sed -i 's/^  void update(const double\* update);/  virtual void update(const double* update);/' "$header"
  fi
}
