@echo off
REM Registriert den netzweiten Nightly-Backup-Task (DizzNetwork-AppBackup) + entfernt den alten
REM TB-Einzel-Task. Selbst-elevierend (1x UAC).
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register_backup_task.ps1"
echo.
pause
