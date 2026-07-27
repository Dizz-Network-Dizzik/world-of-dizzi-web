# Legt eine Desktop-Verknuepfung "Trading Bot Trial" an, die den Launcher startet.
$root    = Split-Path -Parent $PSScriptRoot
$launch  = Join-Path $root "scripts\launch.ps1"
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "Trading Bot Trial.lnk"

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnkPath)
$sc.TargetPath       = "powershell.exe"
$sc.Arguments        = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launch`""
$sc.WorkingDirectory = $root
$sc.IconLocation     = "$env:SystemRoot\System32\imageres.dll,109"
$sc.Description       = "Trading Bot Trial - Dashboard starten"
$sc.Save()

Write-Output "Verknuepfung erstellt: $lnkPath"
