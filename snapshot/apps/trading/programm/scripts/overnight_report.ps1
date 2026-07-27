param([int]$SleepSeconds = 21600)
Start-Sleep -Seconds $SleepSeconds
$b = 'http://127.0.0.1:8137'
"=== Uebernacht-Report $(Get-Date -Format 'dd.MM.yyyy HH:mm') ==="
try { $bots = Invoke-RestMethod "$b/api/bots" | Where-Object { $_.name -like 'Auto-*' -or $_.name -like 'Fut-*' } }
catch { "Backend nicht erreichbar: $($_.Exception.Message)"; return }
foreach ($bot in $bots) {
    try {
        $t = Invoke-RestMethod "$b/api/bots/$($bot.id)/trades?limit=5"
        $e = Invoke-RestMethod "$b/api/bots/$($bot.id)/equity"
        $now = if ($e.points -and $e.points.Count) { $e.points[$e.points.Count - 1].equity } else { '-' }
        "$($bot.name) [$($bot.strategy)] running=$($bot.running) status=$($bot.status) | Trades geschlossen=$($t.closed) offen=$($t.open) | Equity $($e.starting) -> $now USDT"
    } catch { "$($bot.id): Fehler $($_.Exception.Message)" }
}
