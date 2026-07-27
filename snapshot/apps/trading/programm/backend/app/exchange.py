"""Börsen-Anbindung (Bitget via CCXT) — Kontoinformationen.

Im Dry-Run / ohne API-Keys werden keine echten Calls gemacht; stattdessen wird
ein simuliertes Paper-Wallet zurückgegeben. Sind read-only-Keys hinterlegt,
wird der echte Kontostand abgefragt (niemals Handels-/Withdraw-Aktionen hier).
"""

from __future__ import annotations

from typing import Any

from . import cache
from .config import Settings

# Wiederverwendeter ccxt-Client: sonst wird bei JEDEM /api/account-Poll ein neuer Client erzeugt (teuer)
# und Bitget bei Live-Keys (M6) gehämmert. Lazy + ein Mal pro Key-Tripel.
_client = None
_client_key: tuple | None = None


def _get_client(settings: Settings):
    global _client, _client_key
    import ccxt  # lokal importiert, damit das Backend ohne ccxt-Call startet
    key = (settings.bitget_api_key, settings.bitget_api_secret, settings.bitget_api_password)
    if _client is None or _client_key != key:
        _client = ccxt.bitget({
            "apiKey": settings.bitget_api_key,
            "secret": settings.bitget_api_secret,
            "password": settings.bitget_api_password,
            "enableRateLimit": True,
            "timeout": 10000,   # 10 s — ein Netz-Hänger darf den /api/account-Request nicht blockieren
        })
        _client_key = key
    return _client


def _live_overview(settings: Settings) -> dict[str, Any]:
    raw = _get_client(settings).fetch_balance()
    balances = {asset: float(total) for asset, total in raw.get("total", {}).items()
                if total and float(total) > 0}
    return {"mode": "live" if not settings.dry_run else "paper",
            "source": "Bitget (read-only API)", "balances": balances}


def get_account_overview(settings: Settings) -> dict[str, Any]:
    """Liefert eine Kontoübersicht — echt (read-only) oder simuliert (Paper).

    Bei Live-Keys: kurzer TTL-Cache (15 s) + wiederverwendeter Client + Timeout, damit häufiges
    /api/account-Polling Bitget nicht hämmert und ein Netz-Hänger den Request nicht blockiert."""
    if not settings.bitget_configured:
        return {
            "mode": "paper",
            "source": "simuliert (keine API-Keys hinterlegt)",
            "balances": {"USDT": 1000.0},
            "note": "Dry-Run-Wallet. Fuer echte Salden read-only Bitget-Key in .env eintragen.",
        }
    try:
        return cache.ttl_get("account_overview", 15.0, lambda: _live_overview(settings))
    except Exception as exc:  # pragma: no cover - Netzwerk/Key-abhängig
        return {"mode": "error", "source": "Bitget", "balances": {},
                "error": f"{type(exc).__name__}: {exc}"}
