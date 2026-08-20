#!/usr/bin/env bash
# Start Paper-Trading Bot + Dashboard (PAPER ONLY).
# Doppelklick / Terminal: startet Bot-Loop und öffnet das Dashboard im Browser.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export TRADING_MODE=paper

LOG_DIR="${ROOT}/logs"
PID_DIR="${ROOT}/.run"
mkdir -p "$LOG_DIR" "$PID_DIR"

BOT_PID_FILE="${PID_DIR}/bot.pid"
DASH_PID_FILE="${PID_DIR}/dashboard.pid"
BOT_LOG="${LOG_DIR}/bot.log"
DASH_LOG="${LOG_DIR}/dashboard.log"

pick_python() {
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    echo "${ROOT}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    command -v python
  fi
}

PYTHON="$(pick_python)"

is_running() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_bot() {
  if is_running "$BOT_PID_FILE"; then
    echo "Bot läuft bereits (PID $(cat "$BOT_PID_FILE"))."
    return
  fi
  echo "Starte Paper-Trading-Bot…"
  nohup "$PYTHON" "${ROOT}/run_bot.py" >>"$BOT_LOG" 2>&1 &
  echo $! >"$BOT_PID_FILE"
  echo "Bot PID $(cat "$BOT_PID_FILE") → $BOT_LOG"
}

start_dashboard() {
  if is_running "$DASH_PID_FILE"; then
    echo "Dashboard läuft bereits (PID $(cat "$DASH_PID_FILE"))."
    return
  fi
  echo "Starte Dashboard…"
  nohup "$PYTHON" "${ROOT}/run_dashboard.py" >>"$DASH_LOG" 2>&1 &
  echo $! >"$DASH_PID_FILE"
  echo "Dashboard PID $(cat "$DASH_PID_FILE") → $DASH_LOG"
}

wait_for_dashboard() {
  local url="http://127.0.0.1:8501"
  local i
  for i in $(seq 1 40); do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS "$url" >/dev/null 2>&1; then
        return 0
      fi
    else
      sleep 2
      return 0
    fi
    sleep 0.5
  done
  return 1
}

open_browser() {
  local url="http://127.0.0.1:8501"
  if command -v open >/dev/null 2>&1; then
    open "$url"   # macOS
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v wslview >/dev/null 2>&1; then
    wslview "$url" || true
  else
    echo "Browser manuell öffnen: $url"
  fi
}

echo "=== Crypto Paper-Trading Starter ==="
echo "Modus: PAPER ONLY (keine echten Orders)"
echo "Python: $PYTHON"
start_bot
start_dashboard
echo "Warte auf Dashboard…"
if wait_for_dashboard; then
  echo "Dashboard bereit."
else
  echo "Dashboard startet noch — Browser öffnet trotzdem."
fi
open_browser
echo
echo "Fertig."
echo "  Bot-Log:        $BOT_LOG"
echo "  Dashboard-Log:  $DASH_LOG"
echo "  Stoppen:        ${ROOT}/stop_paper_trading.sh"
echo
# Keep Terminal briefly visible on double-click (.command)
if [[ "${KEEP_OPEN:-0}" == "1" ]]; then
  read -r -p "Taste drücken zum Schließen…" _
fi
