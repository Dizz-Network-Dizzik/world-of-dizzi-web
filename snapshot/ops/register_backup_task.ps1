# Registriert den netzweiten Nightly-Daten-Backup-Task (DizzNetwork-AppBackup) und entfernt
# TBs alten Einzel-Task (TradingBot-Kern-Backup) -> in den Unified-Service eingegliedert.
# Braucht Admin (register_backup_task.cmd eleviert). ASCII-only (PS 5.1).
$ErrorActionPreference = "Stop"
$py     = "C:\Dizzik\data\tools\venv\Scripts\python.exe"
$script = "C:\Dizzik\code\dizz-network\ops\backup_apps.py"
$wd     = "C:\Dizzik\code\dizz-network"

$action    = New-ScheduledTaskAction -Execute $py -Argument "`"$script`"" -WorkingDirectory $wd
$trigger   = New-ScheduledTaskTrigger -Daily -At 3:00am
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "DizzNetwork-AppBackup" -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "[ok] DizzNetwork-AppBackup registriert (taeglich 03:00)"

try {
    Unregister-ScheduledTask -TaskName "TradingBot-Kern-Backup" -Confirm:$false -ErrorAction Stop
    Write-Host "[ok] TradingBot-Kern-Backup entfernt (in Unified-Service eingegliedert)"
} catch { Write-Host "  (TradingBot-Kern-Backup nicht gefunden / schon weg)" }

$t = Get-ScheduledTask -TaskName "DizzNetwork-AppBackup"
$a = $t.Actions[0]
Write-Host ""
Write-Host "Verifikation:"
Write-Host "  State : $($t.State)"
Write-Host "  Action: $($a.Execute) $($a.Arguments)"
Write-Host "  Trigger: taeglich 03:00"
