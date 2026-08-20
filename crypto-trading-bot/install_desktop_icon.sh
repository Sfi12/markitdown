#!/usr/bin/env bash
# Legt auf dem Desktop eine startbare Verknüpfung mit Icon an (macOS / Linux).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ICON="${ROOT}/assets/paper-trading-icon.png"

if [[ "$(uname -s)" == "Darwin" ]]; then
  DEST="${HOME}/Desktop/Paper Trading starten.command"
  cp "${ROOT}/Paper Trading starten.command" "$DEST"
  chmod +x "$DEST"
  # Icon am .command setzen (optional, benötigt sips/DeRez nicht zwingend)
  if command -v osascript >/dev/null 2>&1 && [[ -f "$ICON" ]]; then
    # Setzt File-Icon grob über Finder (best effort)
    osascript <<EOF >/dev/null 2>&1 || true
use framework "AppKit"
set imagePath to POSIX file "${ICON}"
set iconImage to current application's NSImage's alloc()'s initWithContentsOfFile:"${ICON}"
if iconImage is not missing value then
  current application's NSWorkspace's sharedWorkspace()'s setIcon:iconImage forFile:"${DEST}" options:0
end if
EOF
  fi
  echo "Desktop-Icon erstellt: $DEST"
  echo "Einmalig: Rechtsklick → Öffnen (Gatekeeper), danach Doppelklick."
  exit 0
fi

# Linux .desktop auf Desktop
DEST="${HOME}/Desktop/Paper Trading starten.desktop"
# Absolute Pfade für Exec/Icon
cat >"$DEST" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Paper Trading starten
Comment=Startet den Paper-Trading-Bot und öffnet das Dashboard (PAPER ONLY)
Exec=${ROOT}/start_paper_trading.sh
Path=${ROOT}
Icon=${ICON}
Terminal=true
Categories=Finance;Utility;
StartupNotify=true
EOF
chmod +x "$DEST"
# Manche DEs verlangen "Allow Launching"
if command -v gio >/dev/null 2>&1; then
  gio set "$DEST" metadata::trusted true 2>/dev/null || true
fi
echo "Desktop-Icon erstellt: $DEST"
echo "Falls nötig: Rechtsklick → Allow Launching / als Programm ausführen."
