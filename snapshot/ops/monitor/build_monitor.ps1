# build_monitor.ps1 — kompiliert die native „Dizz Network"-Statusleiste (monitor_app.cs) zu einer
# Windows-EXE mit eingebettetem Neon-Icon + FileDescription „Dizz Network" (so erscheint das System
# im Taskmanager unter APPS mit eigenem Namen/Icon). Nutzt den .NET-Framework-C#-Compiler, der auf
# jedem Windows vorhanden ist — keine Installation noetig.
# Ausgabe: ops\monitor\DizzNetwork-Monitor.exe
# (Verlegt 02.07.2026 aus apps\trading\programm\scripts — der Monitor ueberwacht das GANZE Netz.)
$ErrorActionPreference = "Stop"

$src = Join-Path $PSScriptRoot "monitor_app.cs"
$ico = Join-Path $PSScriptRoot "monitor.ico"
$out = Join-Path $PSScriptRoot "DizzNetwork-Monitor.exe"
$csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { $csc = "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe" }

$cscArgs = @('/nologo', '/target:winexe', '/platform:anycpu', '/optimize+')
if (Test-Path $ico) { $cscArgs += "/win32icon:$ico" }
$cscArgs += @('/r:System.dll', '/r:System.Drawing.dll', '/r:System.Windows.Forms.dll', "/out:$out", $src)

& $csc @cscArgs

if (Test-Path $out) {
  $vi = (Get-Item $out).VersionInfo
  Write-Output ("Build OK: " + $out)
  Write-Output ("  FileDescription (Taskmanager-Name): '" + $vi.FileDescription + "'")
} else {
  throw "Build fehlgeschlagen"
}
