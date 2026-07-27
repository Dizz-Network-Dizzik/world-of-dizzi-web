# Desktop-Starter: sorgt dafuer, dass der Core laeuft, und oeffnet das Dashboard.
# Wird von der Desktop-Verknuepfung mit -WindowStyle Hidden aufgerufen.
$ErrorActionPreference = "SilentlyContinue"
$url = "http://127.0.0.1:8200"

function Test-Core {
    try {
        $r = Invoke-WebRequest "$url/api/health" -UseBasicParsing -TimeoutSec 1
        return $r.StatusCode -eq 200
    } catch { return $false }
}

if (-not (Test-Core)) {
    $venvPython = "C:\Dizzik\data\tools\venv\Scripts\python.exe"
    $coreDir = Join-Path $PSScriptRoot "..\apps\core"
    Start-Process -FilePath $venvPython -WindowStyle Hidden -ArgumentList @(
        "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8200", "--app-dir", "`"$coreDir`""
    )
    foreach ($i in 1..30) {
        Start-Sleep -Milliseconds 500
        if (Test-Core) { break }
    }
}

Start-Process $url
