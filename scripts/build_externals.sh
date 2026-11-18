#!/usr/bin/env bash
# Dispatcher for the external components of MACC.
#   default  : g2o, cg2o, IPOPT (MUMPS)            + HSL when USE_HSL=ON
#
# USE_HSL: OFF (default) = IPOPT uses MUMPS only. ON = also build the licensed Coin-HSL library (MA27, MA57, ...)
# from the archive you put into externals/ (see externals/README.md). Set it here or in the environment:
#   USE_HSL=ON ./scripts/build_externals.sh
USE_HSL="${USE_HSL:-OFF}"
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SELECT='g2o,cg2o,ipopt'; CLEAN=0; EXTRA=(); EXPLICIT=0
for arg in "$@"; do
  case "$arg" in
    --solver-only) SELECT='g2o,cg2o' ;;
    --full) SELECT='g2o,cg2o,ipopt' ;;
    --cg2o-only) SELECT='cg2o' ;;
    --ipopt|--ipopt-only) SELECT='ipopt' ;;
    --hsl) SELECT='hsl'; EXPLICIT=1 ;;
    --all) SELECT='g2o,cg2o,ipopt' ;;
    --only=*) SELECT="${arg#--only=}"; EXPLICIT=1 ;;
    --clean) CLEAN=1 ;;
    --source|--system) EXTRA+=("$arg") ;;   # forwarded to ipopt.sh
    -h|--help)
      cat <<'HELP'
Usage: ./scripts/build_externals.sh [selection] [--clean] [ipopt options]

Selection (default: g2o, cg2o, then IPOPT with MUMPS; HSL too when USE_HSL=ON):
  --solver-only            g2o + cg2o (no IPOPT)
  --full                   g2o + cg2o + IPOPT (same as the default)
  --cg2o-only              cg2o only
  --ipopt                  IPOPT only (from source, MUMPS)
  --hsl                    HSL (ma27...ma97) only, as a run-time library for the existing IPOPT
                           (licensed source: externals/coinhsl-*.tar.gz or HSL_SOURCE=<archive|dir>)
  --all                    everything above
  --only=a,b,...           explicit list out of g2o, cg2o, ipopt, hsl
IPOPT options:  --source (default) | --system (Ubuntu package, MUMPS only)
--clean rebuilds the selected components and deletes only their build/install folders.
Environment: USE_HSL=ON|OFF (default OFF), CG2O_DIR=<cg2o checkout> (otherwise cloned).
Per-component options: ./scripts/build_externals/<component>.sh --help
HELP
      exit 0 ;;
    *) echo "ERROR: Unknown option: $arg" >&2; exit 2 ;;
  esac
done
[[ -n "$SELECT" ]] || { echo 'ERROR: Empty --only selector' >&2; exit 2; }
case "$USE_HSL" in
  ON|on|1|true|TRUE) [[ "$EXPLICIT" == 1 || ",$SELECT," != *,ipopt,* ]] || SELECT="$SELECT,hsl" ;;
  OFF|off|0|false|FALSE) ;;
  *) echo "ERROR: USE_HSL must be ON or OFF (is '$USE_HSL')" >&2; exit 2 ;;
esac
IFS=',' read -r -a NAMES <<< "${SELECT// /,}"
for name in "${NAMES[@]}"; do
  case "$name" in g2o|cg2o|ipopt|hsl) ;; *) echo "ERROR: Invalid external component: $name" >&2; exit 2 ;; esac
done
if [[ "$CLEAN" == 1 ]] && [[ "${NAMES[*]}" == *g2o* && "${NAMES[*]}" != *cg2o* ]]; then
  echo 'WARNING: You are cleaning g2o without rebuilding cg2o; rebuild cg2o before running MACC.' >&2
fi
for name in "${NAMES[@]}"; do
  args=(); [[ "$CLEAN" == 0 ]] || args+=(--clean)
  [[ "$name" != ipopt ]] || args+=("${EXTRA[@]}")
  bash "$ROOT/scripts/build_externals/$name.sh" "${args[@]}" \
    || { printf '\nERROR: building %s failed (see the messages above); stopped.\n' "$name" >&2; exit 1; }
done
printf '\nExternal components processed: %s\n' "$SELECT"
echo 'Activate paths in this shell with: source scripts/setup_env.sh'
