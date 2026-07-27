# Startet den Core-Service (Stufe 1, lokal).
# Frontend: shell/dist wird automatisch mit ausgeliefert -> http://127.0.0.1:8200
$venvPython = "C:\Dizzik\data\tools\venv\Scripts\python.exe"
$coreDir = Join-Path $PSScriptRoot "..\apps\core"
# WICHTIG: geteiltes appkit/ui-kit liegt in packages/ (Single-Source, kein Vendoring) -> PYTHONPATH
# muss auf packages zeigen, sonst schlaegt `import appkit` beim Start fehl und der Core kommt nicht hoch.
$env:PYTHONPATH = (Resolve-Path (Join-Path $PSScriptRoot "..\packages")).Path
& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8200 --app-dir $coreDir
