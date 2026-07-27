r"""Prueft die .env-Konfiguration — OHNE Geheimnisse im Klartext auszugeben.

Zeigt je Wert nur: gesetzt? Laenge, maskierte Vorschau (erste 3 / letzte 2 Zeichen)
und ein Plausibilitaets-/Verbindungs-Check. Aufruf:
    .\.venv\Scripts\python.exe scripts\check_setup.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import get_settings  # noqa: E402


def mask(value: str) -> str:
    if not value:
        return "(leer)"
    if len(value) <= 6:
        return f"len={len(value)} '{value[0]}***'"
    return f"len={len(value)} '{value[:3]}…{value[-2:]}'"


def line(label: str, ok: bool, detail: str) -> None:
    print(f"[{'OK ' if ok else 'XX'}] {label:24} {detail}")


s = get_settings()
print("=== .env-Pruefung (maskiert) ===\n")

# Betriebsmodus
line("TBT_DRY_RUN", True, f"{s.dry_run}  ({'Paper' if s.dry_run else 'ECHTGELD'})")

# Bitget
line("BITGET_API_KEY", bool(s.bitget_api_key), mask(s.bitget_api_key))
line("BITGET_API_SECRET", bool(s.bitget_api_secret), mask(s.bitget_api_secret))
line("BITGET_API_PASSWORD", bool(s.bitget_api_password), mask(s.bitget_api_password))

# Anthropic
key = s.anthropic_api_key
prefix_ok = key.startswith("sk-ant-") if key else False
line("ANTHROPIC_API_KEY", bool(key), mask(key) + ("  Format ok" if prefix_ok else "  (erwartet: sk-ant-…)" if key else ""))
line("TBT_AI_MODEL", True, s.ai_model)

# Verbindungstest Bitget (nur lesen)
print("\n=== Bitget-Verbindungstest (read-only) ===")
if not s.bitget_configured:
    print("Uebersprungen: API-Key und/oder Secret fehlen.")
else:
    try:
        import ccxt

        client = ccxt.bitget({
            "apiKey": s.bitget_api_key,
            "secret": s.bitget_api_secret,
            "password": s.bitget_api_password,
            "enableRateLimit": True,
        })
        bal = client.fetch_balance()
        assets = [a for a, v in bal.get("total", {}).items() if v and float(v) > 0]
        print(f"[OK ] Verbindung erfolgreich. Assets mit Guthaben: {assets or 'keine'}")
    except Exception as exc:  # pragma: no cover
        name = type(exc).__name__
        print(f"[XX] Fehler: {name}: {str(exc)[:160]}")
        if "Auth" in name or "sign" in str(exc).lower() or "40" in str(exc):
            print("     -> Sehr wahrscheinlich falscher Secret/Passphrase. "
                  "Pruefe, ob im SECRET wirklich der 'Secret Key' steht (nicht der Name/Key).")

print("\nFertig. (Keine Geheimnisse wurden vollstaendig angezeigt.)")
