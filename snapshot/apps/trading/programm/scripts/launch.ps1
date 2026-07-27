# Dizz Trading — Launcher
# Startet das Orchestrator-Backend (falls nicht aktiv) und oeffnet das Dashboard.
$ErrorActionPreference = "SilentlyContinue"

$root   = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$url    = "http://127.0.0.1:8137"

# Monorepo (dizz-network): appkit/ui-kit liegen geteilt in packages/ (Single-Source, kein Vendoring
# mehr). PYTHONPATH muss packages/ enthalten, damit `import appkit` greift (analog ops/launch_app.ps1).
# $root = ...\dizz-network\apps\trading\programm  ->  drei Ebenen hoch = ...\dizz-network
$packages = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $root))) "packages"

# Taskmanager-Sichtbarkeit: benannte Kopie der venv-Python, damit das Backend als
# "DizzTrading-Server.exe" erscheint statt als anonyme python.exe (gleicher Scripts-Ordner =
# voll funktionsfaehiges venv). Idempotent; bei Fehler Fallback auf python.exe.
$serverExe = Join-Path $root ".venv\Scripts\DizzTrading-Server.exe"
try { if ((Test-Path $python) -and -not (Test-Path $serverExe)) { Copy-Item $python $serverExe -Force } } catch {}
if (-not (Test-Path $serverExe)) { $serverExe = $python }

function Test-Up { try { Invoke-RestMethod "$url/health" -TimeoutSec 2 | Out-Null; return $true } catch { return $false } }

if (-not (Test-Up)) {
    $env:PYTHONUTF8 = "1"
    if (Test-Path $packages) { $env:PYTHONPATH = $packages }
    # Boot-Output in ein Log (data\ ist gitignored) - sonst bleibt ein Startup-/Resume-Fehler
    # beim versteckten Autostart unsichtbar. Wird bei jedem Start ueberschrieben.
    $bootErr = Join-Path $root "data\_server_boot.err.log"
    $bootOut = Join-Path $root "data\_server_boot.out.log"
    Start-Process -FilePath $serverExe `
        -ArgumentList "-m","uvicorn","backend.app.main:app","--host","127.0.0.1","--port","8137" `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardError $bootErr -RedirectStandardOutput $bootOut
    for ($i=0; $i -lt 40; $i++) { if (Test-Up) { break }; Start-Sleep -Milliseconds 500 }
}

# Status-Monitor „Dizz Network" ★ VERLEGT 02.07.2026 -> ops\monitor\ (netzweiter Launcher, kein
# Trading-Teil). Startet jetzt UNABHAENGIG ueber die Autostart-Verknuepfung im Windows-Startup-Ordner
# (ops\monitor\launch_monitor.ps1 -> DizzNetwork-Monitor.exe). Hier bewusst NICHT mehr gebaut/gestartet.

Start-Process $url
