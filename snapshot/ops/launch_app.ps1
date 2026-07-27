# the world of dizzi — Netzwerk-App-Launcher (Autostart-Tasks rufen dieses Skript)
# Startet EINEN App-Server DETACHED (Muster TradingBotEins-Autostart): ein konsolen-
# UNABHAENGIGER Hintergrundprozess, der das Schliessen der Task-/Session-Konsole ueberlebt.
# Das Skript wartet nur bis der Port bindet und endet dann. Idempotent: Port belegt -> sofort raus.
#
# WARUM dizz-server.exe statt venv\Scripts\python.exe:
#   Die venv-python.exe ist ein Redirector-STUB; per Start-Process/Task gestartet stirbt
#   das Kind. dizz-server.exe = echte Kopie des Basis-Interpreters (Python312) IM
#   venv\Scripts-Ordner -> findet pyvenv.cfg eine Ebene hoeher -> venv inkl. uvicorn aktiv,
#   ist aber ein echter Interpreter und laeuft als stabiler, detached startbarer Prozess.
#
# Aufruf (Beispiel):
#   launch_app.ps1 -Spec "newsapp.main:app_factory" -Port 8216 `
#                  -AppDir "...\news" -Factory
param(
  [Parameter(Mandatory=$true)][string]$Spec,
  [Parameter(Mandatory=$true)][int]$Port,
  [Parameter(Mandatory=$true)][string]$AppDir,
  [switch]$Factory
)
$ErrorActionPreference = "SilentlyContinue"

$server = "C:\Dizzik\data\tools\venv\Scripts\dizz-server.exe"
$base   = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
# dizz-server.exe selbstheilend anlegen, falls fehlt (z. B. nach venv-Neubau).
if ((-not (Test-Path $server)) -and (Test-Path $base)) { Copy-Item $base $server -Force }
if (-not (Test-Path $server)) { $server = "C:\Dizzik\data\tools\venv\Scripts\python.exe" }

# Idempotenz: laeuft schon etwas auf dem Port? Dann nichts tun.
try { Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch {}

$env:PYTHONUTF8 = "1"
# Monorepo: geteiltes appkit/ui-kit aus packages/ auf den Import-Pfad (kein Vendoring mehr).
# Auto-erkannt relativ zum Launcher; fehlt packages/ (Alt-Layout) -> unveraendert (rueckwaerts-kompatibel).
$pkg = Resolve-Path (Join-Path $PSScriptRoot "..\packages") -ErrorAction SilentlyContinue
if ($pkg) { $env:PYTHONPATH = $pkg.Path }
$fl = if ($Factory) { " --factory" } else { "" }
# AppDir explizit gequotet (enthaelt Leerzeichen); WorkingDirectory zusaetzlich als Absicherung.
$argline = "-m uvicorn $Spec$fl --host 127.0.0.1 --port $Port --app-dir `"$AppDir`" --log-level warning"

# DETACHED starten (Muster TradingBotEins-Autostart): eigener, konsolen-UNABHAENGIGER Prozess,
# der das Schliessen der Task-/Session-Konsole ueberlebt (Vordergrund-Start stirbt sonst mit
# 0xC000013A / STATUS_CONTROL_C_EXIT). Das Skript wartet nur bis der Port bindet und endet dann.
Start-Process -FilePath $server -ArgumentList $argline -WorkingDirectory $AppDir -WindowStyle Hidden
for ($i = 0; $i -lt 40; $i++) {
  try { Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2 | Out-Null; break }
  catch { Start-Sleep -Milliseconds 500 }
}
