# launch_monitor.ps1 — startet die native „Dizz Network"-Statusleiste (unten rechts auf dem Desktop).
# Baut die EXE bei Bedarf aus monitor_app.cs (Windows-eigener C#-Compiler). Doppel-Start verhindert die
# App selbst (benannter Mutex „DizzNetworkMonitor"). Wird von der Autostart-Verknuepfung im Windows-
# Startup-Ordner mit -WindowStyle Hidden aufgerufen — unabhaengig vom Trading-Stack.
$ErrorActionPreference = "SilentlyContinue"
$exe = Join-Path $PSScriptRoot "DizzNetwork-Monitor.exe"
if (-not (Test-Path $exe)) { & (Join-Path $PSScriptRoot "build_monitor.ps1") }
if (Test-Path $exe) { Start-Process -FilePath $exe -WorkingDirectory $PSScriptRoot }
