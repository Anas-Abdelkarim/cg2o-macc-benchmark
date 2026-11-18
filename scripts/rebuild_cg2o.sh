#!/usr/bin/env bash
# Developer loop: rebuild cg2o incrementally, then MACC.
# Changed local cg2o C++ -> incremental cg2o compile/install -> MACC app rebuild.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
CLEAN=0; MODE=both
for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    --library-only) MODE=library ;;
    --application-only) MODE=application ;;
    -h|--help)
      cat <<'HELP'
Usage: ./scripts/rebuild_cg2o.sh [--clean] [--library-only | --application-only]

Default: incremental cg2o library build/install then MACC application rebuild.
--clean: cg2o and MACC app outputs only (NEVER g2o or external sources).
--library-only: only compile/reinstall cg2o.
--application-only: only build MACC app, assumes local g2o/cg2o installed.
HELP
      exit 0 ;;
    *) echo "ERROR: Unknown option $arg" >&2; exit 2 ;;
  esac
done
if [[ "$MODE" != application ]]; then
  options=(); [[ "$CLEAN" == 0 ]] || options+=(--clean)
  bash "$ROOT/scripts/build_externals/cg2o.sh" "${options[@]}"
fi
if [[ "$MODE" != library ]]; then
  options=(); [[ "$CLEAN" == 0 ]] || options+=(--clean)
  bash "$ROOT/scripts/build_workspace.sh" "${options[@]}"
fi
echo 'Done. Source paths in new terminals: source scripts/setup_env.sh'
