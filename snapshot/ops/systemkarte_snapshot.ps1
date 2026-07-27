# systemkarte_snapshot.ps1 - sichert die Gesamtsystem-Karte (+ ihre Quell-Artefakte) als
# zeitgestempelten Schnappschuss unter C:\Dizzik\data\_backups\systemkarte\<ts>\.
#
# Gedacht als EIN Schritt des "Systemkarte-Pflege"-Rituals (siehe DIZZ_NETWORK_CHAT_MANAGEMENT.md,
# Abschnitt Systemkarte): nach einem grossen Bearbeitungs-Satz im Netz die Karte aktualisieren,
# dann snapshotten, dann committen. Der git-Verlauf bleibt die durable Sicherung; dieser
# Schnappschuss ist die schnelle, server-unabhaengige Sicherheitskopie zum direkten Oeffnen.
#
# ASCII-rein halten (Windows-PowerShell 5.1 mis-parst sonst Umlaute/Gedankenstriche ohne BOM).
# Aufruf:  powershell -ExecutionPolicy Bypass -File ops\systemkarte_snapshot.ps1
$ErrorActionPreference = "Stop"

# Repo-Wurzel = ein Verzeichnis ueber ops\ (Skript-robust, egal von wo aufgerufen).
$repo = Split-Path -Parent $PSScriptRoot
$net  = Join-Path $repo "_netzwerk"

# Was gesichert wird: die Karte selbst + ihre Quell-/Begleit-Artefakte.
$quellen = @(
    (Join-Path $net "SYSTEM_KARTE.html"),
    (Join-Path $net "tradingbot_architektur.svg"),
    (Join-Path $net "LOTSE.md"),
    (Join-Path $net "SYSTEMDATENBLATT.md")
)

$ziel   = "C:\Dizzik\data\_backups\systemkarte"
$ts     = Get-Date -Format "yyyyMMdd-HHmmss"
$ablage = Join-Path $ziel $ts
New-Item -ItemType Directory -Path $ablage -Force | Out-Null

$kopiert = 0
foreach ($q in $quellen) {
    if (Test-Path $q) {
        Copy-Item $q -Destination $ablage -Force
        $kopiert++
    } else {
        Write-Warning "fehlt (uebersprungen): $q"
    }
}

if ($kopiert -eq 0) {
    Remove-Item $ablage -Recurse -Force
    throw "Nichts gesichert - keine Quell-Datei gefunden unter $net"
}

# Aufraeumen: nur die letzten 20 Schnappschuesse behalten (unbegrenztes Wachstum vermeiden).
Get-ChildItem $ziel -Directory |
    Sort-Object Name -Descending |
    Select-Object -Skip 20 |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

$behalten = (Get-ChildItem $ziel -Directory).Count
Write-Output ("Systemkarte gesichert: " + $ablage + "  (" + $kopiert + " Dateien)")
Write-Output ("Behaltene Schnappschuesse: " + $behalten + " (max 20)")
Write-Output "Hinweis: Der git-Verlauf ist die eigentliche durable Sicherung - Karte nach Updates committen."
