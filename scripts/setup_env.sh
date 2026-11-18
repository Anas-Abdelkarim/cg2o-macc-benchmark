#!/usr/bin/env bash
# Source this file to put the local externals on the search paths; safe to re-source.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Must be sourced: source scripts/setup_env.sh' >&2
  exit 2
fi
if [[ $# -gt 0 ]]; then
  case "$1" in --help|-h) echo 'Usage: source scripts/setup_env.sh'; return 0 ;; *) echo "Unknown setup argument: $1" >&2; return 2 ;; esac
fi
export MACC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export EXTERNALS="${EXTERNALS:-$MACC_ROOT/externals}"
export EXTERNAL_BUILD_ROOT="${EXTERNAL_BUILD_ROOT:-$MACC_ROOT/build/externals}"
export EXTERNAL_INSTALL_ROOT="${EXTERNAL_INSTALL_ROOT:-$MACC_ROOT/install/externals}"
export MACC_BUILD_DIR="${MACC_BUILD_DIR:-$MACC_ROOT/build/macc}"
MACC_G2O_PREFIX="${MACC_G2O_PREFIX:-$EXTERNAL_INSTALL_ROOT/g2o}"
MACC_CG2O_PREFIX="${MACC_CG2O_PREFIX:-$EXTERNAL_INSTALL_ROOT/cg2o}"
# optional externals (installed by scripts/build_externals.sh --ipopt)
MACC_IPOPT_PREFIX="${MACC_IPOPT_PREFIX:-$EXTERNAL_INSTALL_ROOT/ipopt}"
export MACC_G2O_PREFIX MACC_CG2O_PREFIX MACC_IPOPT_PREFIX
for _macc_dir in "$MACC_G2O_PREFIX" "$MACC_CG2O_PREFIX" "$MACC_IPOPT_PREFIX"; do
  case "$(realpath -m "$_macc_dir")" in /usr|/usr/*) echo "Refusing system solver prefix: $_macc_dir" >&2; unset _macc_dir; return 1 ;; esac
done
_macc_prepend_path() {
  local name="$1" path="$2" previous
  [[ -d "$path" ]] || return 0
  previous="${!name:-}"
  case ":$previous:" in *":$path:"*) return 0 ;; esac
  printf -v "$name" '%s' "$path${previous:+:$previous}"
  export "$name"
}
for _macc_dep in "$MACC_G2O_PREFIX" "$MACC_CG2O_PREFIX" "$MACC_IPOPT_PREFIX"; do
  _macc_prepend_path CMAKE_PREFIX_PATH "$_macc_dep"
  for _macc_lib in lib lib64; do
    _macc_prepend_path LD_LIBRARY_PATH "$_macc_dep/$_macc_lib"
    _macc_prepend_path PKG_CONFIG_PATH "$_macc_dep/$_macc_lib/pkgconfig"
  done
done
_macc_g2o_config="$(find "$MACC_G2O_PREFIX" -type f -name g2oConfig.cmake -print -quit 2>/dev/null || true)"
_macc_cg2o_config="$(find "$MACC_CG2O_PREFIX" -type f -name cg2oConfig.cmake -print -quit 2>/dev/null || true)"
if [[ -n "$_macc_g2o_config" ]]; then export g2o_DIR="$(dirname "$_macc_g2o_config")"; else unset g2o_DIR; fi
if [[ -n "$_macc_cg2o_config" ]]; then export cg2o_DIR="$(dirname "$_macc_cg2o_config")"; else unset cg2o_DIR; fi
echo "MACC environment activated: $MACC_ROOT"
echo "  g2o : $MACC_G2O_PREFIX $([[ -n "$_macc_g2o_config" ]] && echo '[installed]' || echo '[not installed]')"
echo "  cg2o: $MACC_CG2O_PREFIX $([[ -n "$_macc_cg2o_config" ]] && echo '[installed]' || echo '[not installed]')"
if [[ -f "$MACC_IPOPT_PREFIX/lib/pkgconfig/ipopt.pc" ]]; then echo "  ipopt: $MACC_IPOPT_PREFIX [installed, local copy takes precedence over the system package]"
elif pkg-config --exists ipopt 2>/dev/null; then echo "  ipopt: system package $(pkg-config --modversion ipopt)"
else echo "  ipopt: not found (./scripts/build_externals.sh --ipopt)"; fi
unset _macc_dir _macc_dep _macc_lib _macc_g2o_config _macc_cg2o_config
unset -f _macc_prepend_path
