#!/usr/bin/env bash
# Offline workflow tests: mocked git/cmake; never clones or compiles real projects.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
mkdir -p "$TMP/mock" "$TMP/checkout/cg2o" "$TMP/work" "$TMP/externals"
export MOCK_LOG="$TMP/log"
export EXTERNALS="$TMP/externals"
export EXTERNAL_BUILD_ROOT="$TMP/build/externals"
export EXTERNAL_INSTALL_ROOT="$TMP/install/externals"
LOCAL_CG2O="$TMP/checkout/cg2o"
export MACC_BUILD_DIR="$TMP/work/macc"
export MACC_ALLOW_EXTERNAL_BUILD_DIR=1
export JOBS=2 CMAKE_GENERATOR=Ninja
: > "$MOCK_LOG"
cat > "$TMP/mock/git" <<'GIT'
#!/usr/bin/env bash
printf 'git %s\n' "$*" >> "$MOCK_LOG"
if [[ "$1" == clone ]]; then
  # git clone --recursive URL DEST
  dir="${@: -1}"
  mkdir -p "$dir/.git"
  case "$dir" in
    */g2o) echo 'project(g2o)' > "$dir/CMakeLists.txt"
           mkdir -p "$dir/g2o/core"
           echo '  virtual void update(const double* update);' > "$dir/g2o/core/sparse_optimizer.h" ;;
    *) echo 'project(cg2o)' > "$dir/CMakeLists.txt" ;;
  esac
fi
GIT
cat > "$TMP/mock/cmake" <<'CMAKE'
#!/usr/bin/env bash
printf 'cmake %s\n' "$*" >> "$MOCK_LOG"
if [[ "$1" == -S ]]; then
  bd=''; g2o=''; march='OFF'
  args=("$@")
  for ((i=0;i<${#args[@]};i++)); do
    case "${args[$i]}" in
      -B) bd="${args[$((i+1))]}" ;;
      -Dg2o_DIR=*) g2o="${args[$i]#*=}" ;;
      -DBUILD_WITH_MARCH_NATIVE=*) march="${args[$i]#*=}" ;;
    esac
  done
  mkdir -p "$bd"
  printf 'g2o_DIR:PATH=%s\nG2O_NO_IMPLICIT_OWNERSHIP_OF_OBJECTS:BOOL=ON\nBUILD_WITH_MARCH_NATIVE:BOOL=%s\n' "$g2o" "$march" > "$bd/CMakeCache.txt"
elif [[ "$1" == --install ]]; then
  case "$2" in
    */g2o) mkdir -p "$EXTERNAL_INSTALL_ROOT/g2o/lib/cmake/g2o"; touch "$EXTERNAL_INSTALL_ROOT/g2o/lib/cmake/g2o/g2oConfig.cmake"; mkdir -p "$EXTERNAL_INSTALL_ROOT/g2o/lib"; touch "$EXTERNAL_INSTALL_ROOT/g2o/lib/libg2o_solver_cholmod.so" "$EXTERNAL_INSTALL_ROOT/g2o/lib/libg2o_solver_csparse.so" ;;
    */cg2o) mkdir -p "$EXTERNAL_INSTALL_ROOT/cg2o/lib/cmake/cg2o" "$EXTERNAL_INSTALL_ROOT/cg2o/include/cg2o/core"; touch "$EXTERNAL_INSTALL_ROOT/cg2o/lib/cmake/cg2o/cg2oConfig.cmake" "$EXTERNAL_INSTALL_ROOT/cg2o/include/cg2o/core/base_fixed_sized_edge_eq.h" ;;
  esac
fi
CMAKE
chmod +x "$TMP/mock/git" "$TMP/mock/cmake"
export PATH="$TMP/mock:$PATH"
fail() { echo "FAIL: $*" >&2; exit 1; }
assert_contains() { grep -Fq -- "$1" "$MOCK_LOG" || fail "Expected log to include: $1"; }

# 1. First run gets g2o via clone, and g2o skip on second run.
"$ROOT/scripts/build_externals/g2o.sh" > /dev/null
[[ -f "$EXTERNAL_INSTALL_ROOT/g2o/lib/cmake/g2o/g2oConfig.cmake" ]] || fail 'missing g2o local install'
"$ROOT/scripts/build_externals/g2o.sh" > /dev/null
[[ "$(grep -c '^git clone .*g2o' "$MOCK_LOG")" == 1 ]] || fail 'g2o must clone once'
[[ "$(grep -c '^cmake --build .*g2o' "$MOCK_LOG")" == 1 ]] || fail 'g2o should skip identical installed build'

# 2. An explicit checkout (CG2O_DIR) is used as it is, and every call triggers cmake --build.
echo 'project(cg2o)' > "$LOCAL_CG2O/CMakeLists.txt"
CG2O_DIR="$LOCAL_CG2O" "$ROOT/scripts/build_externals/cg2o.sh" > /dev/null
CG2O_DIR="$LOCAL_CG2O" "$ROOT/scripts/build_externals/cg2o.sh" > /dev/null
[[ "$(grep -c '^cmake --build .*cg2o' "$MOCK_LOG")" == 2 ]] || fail 'cg2o should incrementally build on every call'
[[ "$(grep -c '^git clone .*cg2o' "$MOCK_LOG" || true)" == 0 ]] || fail 'cg2o cloned despite CG2O_DIR'
assert_contains "-S $LOCAL_CG2O -B $EXTERNAL_BUILD_ROOT/cg2o"
assert_contains "-Dg2o_DIR=$EXTERNAL_INSTALL_ROOT/g2o/lib/cmake/g2o"

# 3. No checkout -> clone into externals/cg2o at the pinned commit, only once.
"$ROOT/scripts/build_externals.sh" --cg2o-only > /dev/null
"$ROOT/scripts/build_externals/cg2o.sh" > /dev/null
[[ "$(grep -c '^git clone .*cg2o' "$MOCK_LOG")" == 1 ]] || fail 'cg2o must auto-clone once'
[[ -f "$EXTERNALS/cg2o/CMakeLists.txt" ]] || fail 'cg2o not cloned into externals/cg2o'
assert_contains "git -C $EXTERNALS/cg2o checkout b14da0c969fa856f1daf8c3518b0e6101df9b4f0"

# 4. CG2O_DIR takes precedence over externals/cg2o.
before="$(grep -c -- "--build $EXTERNAL_BUILD_ROOT/cg2o" "$MOCK_LOG")"
CG2O_DIR="$LOCAL_CG2O" "$ROOT/scripts/build_externals/cg2o.sh" > /dev/null
[[ "$(tail -n 5 "$MOCK_LOG" | grep -c -- "$EXTERNALS/cg2o" || true)" == 0 ]] || fail 'externals/cg2o used although CG2O_DIR is set'
[[ "$(grep -c -- "--build $EXTERNAL_BUILD_ROOT/cg2o" "$MOCK_LOG")" -gt "$before" ]] || fail 'CG2O_DIR build missing'

# 5. Cleaning cg2o NEVER deletes g2o install or source.
CG2O_DIR="$LOCAL_CG2O" "$ROOT/scripts/build_externals/cg2o.sh" --clean > /dev/null
[[ -f "$EXTERNAL_INSTALL_ROOT/g2o/lib/cmake/g2o/g2oConfig.cmake" ]] || fail 'cg2o clean deleted g2o'
[[ -f "$LOCAL_CG2O/CMakeLists.txt" ]] || fail 'cg2o clean deleted cg2o source'

# 6. Idempotent local environment paths and strict local app configure.
# shellcheck disable=SC1091
source "$ROOT/scripts/setup_env.sh" > /dev/null
source "$ROOT/scripts/setup_env.sh" > /dev/null
[[ "$g2o_DIR" == "$EXTERNAL_INSTALL_ROOT/g2o/lib/cmake/g2o" ]] || fail 'wrong g2o_DIR'
[[ "$cg2o_DIR" == "$EXTERNAL_INSTALL_ROOT/cg2o/lib/cmake/cg2o" ]] || fail 'wrong cg2o_DIR'
# Missing cg2o headers must cause immediate actionable diagnostic, not 38 C++ failures.
rm -f "$EXTERNAL_INSTALL_ROOT/cg2o/include/cg2o/core/base_fixed_sized_edge_eq.h"
if "$ROOT/scripts/build_workspace.sh" --configure-only > "$TMP/header_error" 2>&1; then
  fail 'workspace accepted cg2o installation without public headers'
fi
grep -q 'cg2o headers missing' "$TMP/header_error" || fail 'missing clear header diagnostic'
touch "$EXTERNAL_INSTALL_ROOT/cg2o/include/cg2o/core/base_fixed_sized_edge_eq.h"
[[ "$(printf '%s' "$CMAKE_PREFIX_PATH" | grep -oF "$EXTERNAL_INSTALL_ROOT/g2o" | wc -l)" == 1 ]] || fail 'env duplicate prefix'
"$ROOT/scripts/build_workspace.sh" --configure-only > /dev/null
assert_contains "-Dcg2o_DIR=$EXTERNAL_INSTALL_ROOT/cg2o/lib/cmake/cg2o"
"$ROOT/scripts/build_workspace.sh" --clean > /dev/null
[[ -f "$EXTERNAL_INSTALL_ROOT/g2o/lib/cmake/g2o/g2oConfig.cmake" ]] || fail 'workspace clean deleted g2o'
[[ -f "$EXTERNAL_INSTALL_ROOT/cg2o/lib/cmake/cg2o/cg2oConfig.cmake" ]] || fail 'workspace clean deleted cg2o'

# 7. Invalid selector exits with error rather than silently building.
if "$ROOT/scripts/build_externals.sh" --only=bogus > /dev/null 2>&1; then fail 'accepted invalid component'; fi

printf 'PASS: explicit cg2o checkout, pinned clone fallback, override, incremental builds,\n      isolated cleans, local g2o linking, setup idempotence, dispatcher and workspace.\n'
