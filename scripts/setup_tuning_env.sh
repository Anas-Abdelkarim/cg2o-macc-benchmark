#!/usr/bin/env bash
# Create the isolated Python environment of the tuning library (experiments/solver_tuning) in .venv-tuning/.
# Isolated on purpose: the library needs optuna 4.x (the system may have 5.x) and the ROS python path must not leak in.
#   scripts/setup_tuning_env.sh            create / update the environment
#   scripts/setup_tuning_env.sh --test     ... and run the unit tests
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
VENV="$ROOT/.venv-tuning"
command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 2; }
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
env -u PYTHONPATH "$VENV/bin/python" -m pip install -q --upgrade pip
env -u PYTHONPATH "$VENV/bin/python" -m pip install -q -e "$ROOT/experiments/solver_tuning[bo,plots,dev]"
echo "tuning environment ready: $VENV"
env -u PYTHONPATH "$VENV/bin/python" -m pip list 2>/dev/null | grep -i -E "^(solver-tuning|optuna|PyYAML|numpy|matplotlib|pytest) "
if [[ "${1:-}" == "--test" ]]; then
  cd "$ROOT/experiments/solver_tuning"
  # PYTEST_DISABLE_PLUGIN_AUTOLOAD: a sourced ROS installation registers pytest plugins that need packages this venv lacks
  env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$VENV/bin/python" -m pytest -q -p no:cacheprovider
fi
echo "run studies with:  scripts/tune.sh run experiments/solver_tuning/studies/<study>.yaml --out results/tuning/<name>"
