#!/usr/bin/env bash
# Preflight check of the build environment (compilers, CMake, libraries).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
failed=0
printf 'MACC root  : %s\n' "$ROOT"
printf 'Compiler   : %s\n' "$(command -v c++ || echo '<missing>')"
for cmd in git cmake c++ pkg-config; do
  if command -v "$cmd" >/dev/null 2>&1; then echo "OK: $cmd"; else echo "FAIL: missing $cmd"; failed=1; fi
done
for pkg in eigen3 fmt yaml-cpp; do
  if pkg-config --modversion "$pkg" >/dev/null 2>&1; then
    echo "OK: $pkg $(pkg-config --modversion "$pkg")"
  else
    echo "WARN: $pkg not found by pkg-config; check CMake/headers"
  fi
done
for f in "$ROOT"/scripts/*.sh "$ROOT"/scripts/build_externals/*.sh; do
  bash -n "$f" || { echo "FAIL: syntax error in $f"; failed=1; }
done
python3 -c 'import numpy, matplotlib, yaml' 2>/dev/null \
  && echo 'OK: python numpy/matplotlib/PyYAML (experiment layer)' \
  || echo 'WARN: python numpy/matplotlib/PyYAML missing -> pip install -r experiments/requirements.txt'
"$ROOT/scripts/build_status.sh"
[[ "$failed" == 0 ]] && echo 'Build environment: core tools OK' || echo 'Build environment: problems detected'
exit "$failed"
