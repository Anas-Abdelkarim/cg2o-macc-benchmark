#!/usr/bin/env bash
# Deep, parallel tuning of IPOPT (cold start), BIPM and ISPD by Bayesian optimisation. Uses 18 of the 20 logical CPUs of the
# development machine (i9-12900H) and stops each tuner after HOURS hours of searching, then validates (about 10-20 min more).
#
#   scripts/tune_deep_cold.sh start     launch the three tuners in the background (survives closing the terminal)
#   scripts/tune_deep_cold.sh status    best so far and latest evaluations of each tuner
#   scripts/tune_deep_cold.sh stop      stop cleanly: no new evaluations, validate what was found, write the reports
#
# Environment (defaults): HOURS=5.5  VALIDATE_TOP=5  VALIDATE_STEPS=2000  FORCE=0 (1: start even if tuners are running)
# Docs: docs/TUNING.md. Results: results/tuning/<timestamp>_<algorithm>_bo/ (trials.csv is the live table).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
HOURS="${HOURS:-5.5}"
VALIDATE_TOP="${VALIDATE_TOP:-5}"
VALIDATE_STEPS="${VALIDATE_STEPS:-2000}"
STATE=results/tuning/logs/current          # file with the folder of the last launch
TUNE="python3 -u experiments/tune.py run"

latest() { ls -dt results/tuning/*_"$1"_bo 2>/dev/null | head -1; }

case "${1:-}" in
start)
  [[ -x build/macc/bin/macc_run ]] || { echo "build first: ./scripts/build_workspace.sh" >&2; exit 2; }
  if pgrep -f '^python3 .*experiments/tune\.py ru[n]' >/dev/null && [[ "${FORCE:-0}" != 1 ]]; then
    echo "tuners are already running (FORCE=1 to start anyway). See: $0 status" >&2; exit 2
  fi
  LOG=results/tuning/logs/$(date +%Y%m%d_%H%M%S); mkdir -p "$LOG"; echo "$LOG" > "$STATE"
  COMMON="--method bo --max-hours $HOURS --validate-top $VALIDATE_TOP --validate-steps $VALIDATE_STEPS"
  # IPOPT, cold start (initial guess 10), ISPD drives the plant.   3 jobs x 3 horizons = 9 processes
  nohup $TUNE ipopt $COMMON --trials 2500 --startup 150 --steps 300 --horizons 3 15 30 --jobs 3 \
        > "$LOG/ipopt.log" 2>&1 & echo $! >> "$LOG/pids"
  # BIPM (needs a strictly feasible start by construction), ISPD drives; kappa schedule + shared cg2o options.
  # Objective "iterations" = fewest iterations; use "--objective paper" to match the paper's Table V instead.  3 x 2 = 6 processes
  nohup $TUNE bipm $COMMON --trials 4000 --startup 60 --steps 500 --horizons 15 30 --groups main shared --jobs 3 \
        --objective iterations --promote-gain 0.10 --full-horizons 30 \
        > "$LOG/bipm.log" 2>&1 & echo $! >> "$LOG/pids"
  # ISPD, initial guess 10; IPOPT (warm) drives the plant and is the cost reference.   1 x 3 = 3 processes
  nohup $TUNE ispd $COMMON --trials 4000 --startup 80 --steps 300 --horizons 3 15 30 --jobs 1 \
        > "$LOG/ispd.log" 2>&1 & echo $! >> "$LOG/pids"
  disown -a 2>/dev/null || true
  echo "started at $(date +%H:%M), searching for ${HOURS} h, then validation. Logs: $LOG"
  echo "  $0 status     # progress      $0 stop     # finish early with a report"
  ;;
status)
  for a in ipopt bipm ispd; do
    d=$(latest "$a"); echo "================ $a  ${d:-<none>}"
    [[ -n "$d" ]] && python3 experiments/tune.py status "$d" --last "${LAST:-5}" 2>&1 | grep -v -i "warn"
  done
  echo; echo -n "running tuners: "; pgrep -f '^python3 .*experiments/tune\.py ru[n]' | wc -l; uptime
  ;;
stop)
  if [[ -f "$(cat "$STATE" 2>/dev/null)/pids" ]]; then
    while read -r p; do kill -TERM "$p" 2>/dev/null && echo "stopping $p (it validates and writes its report)"; done < "$(cat "$STATE")/pids"
  else pkill -TERM -f '^python3 .*experiments/tune\.py ru[n]' || echo "nothing running"; fi
  ;;
*) sed -n '2,11p' "$0"; exit 1 ;;
esac
