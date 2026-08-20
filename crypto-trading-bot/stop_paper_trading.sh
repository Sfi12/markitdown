#!/usr/bin/env bash
# Stoppt Paper-Trading-Bot und Dashboard.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="${ROOT}/.run"

stop_one() {
  local name="$1"
  local pid_file="$2"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "Stoppe $name (PID $pid)…"
      kill "$pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$pid_file"
  else
    echo "$name: keine PID-Datei."
  fi
}

stop_one "Bot" "${PID_DIR}/bot.pid"
stop_one "Dashboard" "${PID_DIR}/dashboard.pid"
echo "Fertig."
