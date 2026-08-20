@echo off
REM Stoppt Bot/Dashboard-Fenster die von start_paper_trading.bat gestartet wurden
taskkill /FI "WINDOWTITLE eq PaperBot*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq PaperDashboard*" /T /F >nul 2>&1
echo Gestoppt (soweit gefunden).
pause
