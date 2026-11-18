#!/usr/bin/env bash
# Deep, parallel tuning of IPOPT (cold start), BIPM and ISPD with the tuning library (experiments/solver_tuning), three studies at
# once, each stopped by itself after HOURS hours of searching and then validated at full length.
#
#   scripts/tune_deep.sh start     launch the three studies in the background (survive closing the terminal)
#   scripts/tune_deep.sh status    best so far and latest evaluations of each study
#   scripts/tune_deep.sh stop      stop searching now (completed evaluations are kept), then run `finish` to validate
#   scripts/tune_deep.sh finish    validate the best candidates found so far and select (no further search)
#
# Environment (defaults): HOURS=5.5  FORCE=0 (1: start even if studies are running)  STUDIES="ipopt_cold bipm ispd"
# CPU use = the sum of `jobs` in the study files (ipopt_cold 9 + bipm 4 + ispd 3 = 16 simulations at a time; the machine has 20 threads).
# Do not rebuild macc_run or edit the studies while they run (the study folders fingerprint the binary). config.yaml may change:
# every study works on its own frozen copy.
# Results: results/tuning/<timestamp>_<study>/  (trials.csv is the live table; report.txt, selected_config.yaml after validation)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
HOURS="${HOURS:-5.5}"
STUDIES="${STUDIES:-ipopt_cold bipm ispd}"
STATE=results/tuning/logs/current
SPECS=experiments/solver_tuning/studies
declare -A TRIALS=([ipopt_cold]=2500 [ipopt_warm]=2500 [bipm]=4000 [bipm_strict]=4000 [ispd]=4000 [al]=2000)
running() { pgrep -f '^[^ ]*python[0-9.]* -m tuning run' >/dev/null; }

case "${1:-}" in
start)
  [[ -x build/macc/bin/macc_run ]] || { echo "build first: ./scripts/build_workspace.sh" >&2; exit 2; }
  [[ -x .venv-tuning/bin/python ]] || { echo "environment missing: run scripts/setup_tuning_env.sh" >&2; exit 2; }
  if running && [[ "${FORCE:-0}" != 1 ]]; then echo "studies are already running (FORCE=1 to start anyway): $0 status" >&2; exit 2; fi
  STAMP=$(date +%Y%m%d_%H%M%S); LOG=results/tuning/logs/$STAMP; mkdir -p "$LOG"; : > "$LOG/studies"; echo "$LOG" > "$STATE"
  SECONDS_BUDGET=$(python3 -c "print(int(float('$HOURS')*3600))")
  for s in $STUDIES; do
    out="results/tuning/${STAMP}_$s"
    nohup scripts/tune.sh run "$SPECS/$s.yaml" --out "$out" --trials "${TRIALS[$s]:-2000}" --max-seconds "$SECONDS_BUDGET" \
      > "$LOG/$s.log" 2>&1 &
    echo "$s $! $out $SPECS/$s.yaml" >> "$LOG/studies"
  done
  disown -a 2>/dev/null || true
  echo "started at $(date +%H:%M): $STUDIES  (search ${HOURS} h, then validation). Logs: $LOG"
  echo "  $0 status | $0 stop | $0 finish"
  ;;
status)
  LOG=$(cat "$STATE" 2>/dev/null) || { echo "no study started yet"; exit 1; }
  while read -r s pid out spec; do
    echo "================ $s   $out   $(kill -0 "$pid" 2>/dev/null && echo "[running, pid $pid]" || echo "[not running]")"
    [[ -f "$out/trials.sqlite3" ]] && scripts/tune.sh status "$out" --last "${LAST:-4}" 2>&1 | grep -v "^# command" | cut -c1-200
  done < "$LOG/studies"
  uptime
  ;;
stop)
  LOG=$(cat "$STATE" 2>/dev/null) || { echo "nothing to stop"; exit 1; }
  while read -r s pid out spec; do kill -TERM "$pid" 2>/dev/null && echo "stopping $s (pid $pid): finishing running simulations, keeping all results"; done < "$LOG/studies"
  echo "then:  $0 finish   (validates the best candidates found so far)"
  ;;
finish)
  LOG=$(cat "$STATE" 2>/dev/null) || { echo "nothing to finish"; exit 1; }
  running && { echo "studies are still running; use '$0 stop' first" >&2; exit 2; }
  while read -r s pid out spec; do
    nohup scripts/tune.sh run "$spec" --out "$out" --finish > "$LOG/$s.finish.log" 2>&1 &
    echo "validating $s -> $out/report.txt"
  done < "$LOG/studies"
  wait
  while read -r s pid out spec; do echo "== $s"; head -8 "$out/report.txt" 2>/dev/null; done < "$LOG/studies"
  ;;
*) sed -n '2,15p' "$0"; exit 1 ;;
esac
