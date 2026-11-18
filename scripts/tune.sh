#!/usr/bin/env bash
# Run the tuning library from its isolated environment:   scripts/tune.sh run|status|plot|macc-figures ...
# (see experiments/solver_tuning/README.md and docs/TUNING.md)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PY="$ROOT/.venv-tuning/bin/python"
[[ -x "$PY" ]] || { echo "environment missing: run scripts/setup_tuning_env.sh first" >&2; exit 2; }
exec env -u PYTHONPATH "$PY" -m tuning "$@"
