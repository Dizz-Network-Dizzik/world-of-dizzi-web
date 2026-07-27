@echo off
REM ==========================================================================
REM  Dizz Autostart-Tasks neu registrieren  (Reboot-Persistenz)
REM  Doppelklick -> es kommt EIN UAC-Fenster -> mit "Ja" bestaetigen.
REM  Registriert alle Dizz-*-Autostart-Tasks idempotent neu; der Task
REM  Dizz-Admin-Autostart zeigt danach auf den Ordner "admin" (nach dem Rename).
REM  Der eigentliche Cutover (Stop/Rename/Neustart) ist bereits erledigt -
REM  dies ist NUR die erhoehte Task-Registrierung.
REM ==========================================================================
title Dizz Autostart neu registrieren
echo.
echo Gleich oeffnet sich EIN UAC-Fenster - bitte mit "Ja" bestaetigen.
echo (Danach zeigt ein erhoehtes Fenster die [OK]-Zeilen der 9 Tasks.)
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_autostart.ps1"
echo.
echo Fertig. Dieses Fenster kann geschlossen werden.
pause
