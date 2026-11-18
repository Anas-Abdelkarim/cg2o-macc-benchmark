#!/usr/bin/env bash
# Read-only status of the local externals (g2o, cg2o, ipopt) and of the MACC build.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
EXTERNALS="$(realpath -m "${EXTERNALS:-$ROOT/externals}")"
BUILDS="$(realpath -m "${EXTERNAL_BUILD_ROOT:-$ROOT/build/externals}")"
INSTALL="$(realpath -m "${EXTERNAL_INSTALL_ROOT:-$ROOT/install/externals}")"
if [[ -n "${CG2O_DIR:-}" ]]; then SRC="$(realpath -m "$CG2O_DIR")"; SRC_KIND='CG2O_DIR'
else SRC="$EXTERNALS/cg2o"; SRC_KIND='project checkout / clone destination'; fi
printf 'MACC root       : %s\n' "$ROOT"
printf 'cg2o selected  : %s (%s) %s\n' "$SRC" "$SRC_KIND" "$([[ -f "$SRC/CMakeLists.txt" ]] && echo '[found]' || echo '[missing: clone on build]')"
for dep in g2o cg2o; do
  config="$(find "$INSTALL/$dep" -name "${dep}Config.cmake" -type f -print -quit 2>/dev/null || true)"
  [[ -n "$config" ]] && state='[installed]' || state='[missing]'
  printf '%-5s install : %s %s\n' "$dep" "$state" "$INSTALL/$dep"
  [[ -f "$BUILDS/$dep/CMakeCache.txt" ]] && printf '       cache   : %s\n' "$BUILDS/$dep/CMakeCache.txt"
done
if [[ -f "$BUILDS/g2o/CMakeCache.txt" ]]; then
  grep -E '^(BUILD_WITH_MARCH_NATIVE|G2O_NO_IMPLICIT_OWNERSHIP_OF_OBJECTS|CMAKE_BUILD_TYPE):' "$BUILDS/g2o/CMakeCache.txt" || true
fi
# Optional components: native IPOPT backend.
if [[ -f "$INSTALL/ipopt/lib/pkgconfig/ipopt.pc" ]]; then
  printf 'ipopt install  : [installed] %s (%s)\n' "$INSTALL/ipopt" "$(grep -m1 '^Version:' "$INSTALL/ipopt/lib/pkgconfig/ipopt.pc" | awk '{print $2}')"
elif pkg-config --exists ipopt 2>/dev/null; then
  printf 'ipopt install  : [system package] %s\n' "$(pkg-config --modversion ipopt)"
else
  printf 'ipopt install  : [missing] ./scripts/build_externals.sh --ipopt\n'
fi
MACC_BUILD_DIR="${MACC_BUILD_DIR:-$ROOT/build/macc}"
[[ -f "$MACC_BUILD_DIR/CMakeCache.txt" ]] && echo "MACC configured: $MACC_BUILD_DIR" || echo 'MACC not configured'
