# the world of dizzi — Autostart-Installer  (EINMAL als Administrator ausfuehren)
# Legt je Netzwerk-App einen Logon-Trigger-Task an (Muster: TradingBotEins-Autostart).
# Jeder Task ruft launch_app.ps1 -> startet den App-Server im Vordergrund (Task "Running").
# Idempotent: -Force ueberschreibt bestehende Tasks; launch_app.ps1 startet nicht doppelt.
#
# AUSFUEHRUNG: Rechtsklick -> "Mit PowerShell ausfuehren" (UAC bestaetigen), ODER in einer
# erhoehten PowerShell:  & "...\the world of dizzi\ops\install_autostart.ps1"
# Das Skript fordert die Erhoehung bei Bedarf selbst an (UAC-Prompt).

# --- Selbst-Erhoehung (UAC) -------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
  Write-Host "Nicht erhoeht -> fordere Administrator-Rechte an (UAC)..."
  Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-NoExit","-File","`"$PSCommandPath`""
  return
}

$ErrorActionPreference = "Stop"
$opsDir   = $PSScriptRoot
$launch   = Join-Path $opsDir "launch_app.ps1"
$wodDir   = Split-Path $opsDir            # ...\dizz-network
$appsDir  = Join-Path $wodDir "apps"      # Monorepo: alle Apps unter apps/<ordner> (Aufraeumung 27.06.2026)
$coreDir  = Join-Path $appsDir "core"

if (-not (Test-Path $launch)) { throw "launch_app.ps1 nicht gefunden: $launch" }

# --- App-Tabelle (Monorepo apps/<ordner>; uvicorn-Spec unveraendert) --------
# Factory = uvicorn --factory (alle Dizz-Apps); Core laeuft ohne Factory (app.main:app).
$apps = @(
  @{ Task="Dizz-News-Autostart";      Spec="newsapp.main:app_factory";       Port=8216; Dir=(Join-Path $appsDir "news");          Factory=$true  },
  @{ Task="Dizz-Money-Autostart";     Spec="moneyapp.main:app_factory";      Port=8210; Dir=(Join-Path $appsDir "money");         Factory=$true  },
  @{ Task="Dizz-Memory-Autostart";    Spec="archivapp.main:app_factory";     Port=8212; Dir=(Join-Path $appsDir "memory");        Factory=$true  },
  @{ Task="Dizz-Admin-Autostart";     Spec="adminapp.main:app_factory";      Port=8222; Dir=(Join-Path $appsDir "admin");         Factory=$true  },
  @{ Task="Dizz-Komm-Autostart";      Spec="kommapp.main:app_factory";       Port=8218; Dir=(Join-Path $appsDir "communication"); Factory=$true  },
  @{ Task="Dizz-Creating-Autostart";  Spec="creatorapp.main:app_factory";    Port=8214; Dir=(Join-Path $appsDir "creating");      Factory=$true  },
  @{ Task="Dizz-Healthy-Autostart";   Spec="healthapp.main:app_factory";     Port=8217; Dir=(Join-Path $appsDir "healthy");       Factory=$true  },
  @{ Task="Dizz-Management-Autostart";Spec="managementapp.main:app_factory"; Port=8213; Dir=(Join-Path $appsDir "management");    Factory=$true  },
  @{ Task="Dizz-Core-Autostart";      Spec="app.main:app";                   Port=8200; Dir=$coreDir;                             Factory=$false }
)
# Hinweis: Trading :8137 hat bereits "TradingBotEins-Autostart". Musik :8220 (eingefroren,
# in Creating eingeschmolzen) hier bewusst NICHT enthalten -- bei Bedarf Zeile ergaenzen.
# Dizz-Admin laeuft aus dem Ordner "admin" (adminapp = vereinte Plans+Admin+Leading-App, docs/28;
# Basis-Repo 20.06. von "leading" -> "admin" umbenannt). $adminDir oben waehlt automatisch.
# Dizz-Plans (:8211) + Dizz-Leading (:8219) sind abgewickelt -> ihre Tasks entfernen (s. u.).

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
               -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger   = New-ScheduledTaskTrigger -AtLogOn

foreach ($a in $apps) {
  $fArg = if ($a.Factory) { " -Factory" } else { "" }
  $arg  = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Spec "{1}" -Port {2} -AppDir "{3}"{4}' -f `
            $launch, $a.Spec, $a.Port, $a.Dir, $fArg
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
  Register-ScheduledTask -TaskName $a.Task -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
  Write-Host ("  [OK] {0,-26} -> :{1}" -f $a.Task, $a.Port)
}

# --- Obsolete Tasks entfernen (abgewickelte Apps, docs/28) -------------------
# Dizz Plans + Dizz Leading sind in Dizz Admin verschmolzen -> ihre Tasks weg.
foreach ($obsolet in "Dizz-Plans-Autostart","Dizz-Leading-Autostart") {
  if (Get-ScheduledTask -TaskName $obsolet -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $obsolet -Confirm:$false
    Write-Host ("  [WEG] {0,-26} (abgewickelt -> Dizz Admin)" -f $obsolet)
  }
}

Write-Host ""
Write-Host "Fertig. Jetzt sofort hochfahren (ohne Reboot):"
Write-Host '  Get-ScheduledTask Dizz-*-Autostart | Start-ScheduledTask'
Write-Host "Beim naechsten Logon starten alle Apps automatisch."
