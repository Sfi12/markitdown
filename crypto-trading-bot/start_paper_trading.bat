@echo off
REM Windows: startet Paper-Trading-Bot + Dashboard und oeffnet den Browser
setlocal
cd /d "%~dp0"

set "PYTHONPATH=%CD%\src"
set "TRADING_MODE=paper"

if not exist "logs" mkdir logs
if not exist ".run" mkdir .run

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

echo === Crypto Paper-Trading Starter ===
echo Modus: PAPER ONLY

start "PaperBot" /MIN cmd /c "%PYTHON% run_bot.py > logs\bot.log 2>&1"
start "PaperDashboard" /MIN cmd /c "%PYTHON% run_dashboard.py > logs\dashboard.log 2>&1"

timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8501"

echo Bot und Dashboard gestartet.
echo Logs: logs\bot.log und logs\dashboard.log
echo Zum Stoppen: stop_paper_trading.bat
pause
