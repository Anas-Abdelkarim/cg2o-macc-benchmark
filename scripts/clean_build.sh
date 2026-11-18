#!/usr/bin/env bash
# Removes the MACC build; keeps the builds and installs of the external components.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TARGET="$(realpath -m "${MACC_BUILD_DIR:-$ROOT/build/macc}")"
case "$TARGET" in
  /|"$ROOT"|"$ROOT/build"|"$ROOT/build/externals"|"$ROOT/build/externals/"*|"$ROOT/externals"|"$ROOT/install"|"$ROOT/install/externals")
    echo "ERROR: Refusing to clean protected folder: $TARGET" >&2; exit 1 ;;
esac
[[ "$TARGET" == "$ROOT/build/"* || "${MACC_ALLOW_EXTERNAL_BUILD_DIR:-0}" == 1 ]] || {
  echo "ERROR: MACC_BUILD_DIR must be under $ROOT/build (or set MACC_ALLOW_EXTERNAL_BUILD_DIR=1): $TARGET" >&2; exit 1;
}
echo "Removing MACC application build only: $TARGET"
rm -rf -- "$TARGET"
echo 'Preserved g2o/cg2o source, build and install directories.'
