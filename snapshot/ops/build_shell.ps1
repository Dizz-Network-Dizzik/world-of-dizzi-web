# Baut das Frontend (portable Node, kein Admin noetig).
$env:PATH = "C:\Dizzik\data\tools\node;$env:PATH"
Set-Location (Join-Path $PSScriptRoot "..\shell")
npm run build
