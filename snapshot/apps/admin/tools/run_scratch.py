"""Scratch-Start für den isolierten Feel-Check (Preview-Config „admin-verify").

Startet Dizz Admin auf :8319 mit einem EIGENEN Daten-Verzeichnis
(``C:\\Dizzik\\data\\scratch-admin-verify``) — damit die Live-Instanz :8222
(Autostart, Produktionsdaten) NIE berührt wird. Der Preview-Proxy „admin-verify"
mappt :8329 → :8319.

    <venv>\\python tools\\run_scratch.py            # default :8319 + Scratch-Daten
    DIZZ_ADMIN_DATA_DIR=… <venv>\\python tools\\run_scratch.py   # eigenes Daten-Dir
"""

from __future__ import annotations

import os

os.environ.setdefault("DIZZ_ADMIN_DATA_DIR", r"C:\Dizzik\data\scratch-admin-verify")

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DIZZ_ADMIN_SCRATCH_PORT", "8319"))
    uvicorn.run("adminapp.main:app_factory", factory=True, host="127.0.0.1", port=port)
