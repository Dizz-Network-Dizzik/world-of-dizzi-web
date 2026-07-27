"""Transfers zwischen Hauptkonto und Bot-(Sub)Account.

Sicherheitsprinzip (Plan §autonomie): **Transfers laufen NIE automatisch.**
Jeder Transfer erfordert eine ausdrückliche Bestätigung (``confirm=True``) und
wird im Audit-Log protokolliert. Ohne hinterlegte API-Keys läuft alles im
Paper-Modus (simuliert). Mit read-only-Keys bleibt es ebenfalls simuliert —
echte Transfers erfordern einen Key MIT Transfer-Recht (bewusst getrennt).
"""

from __future__ import annotations

from . import audit
from .config import Settings


def transfer(settings: Settings, from_acc: str, to_acc: str, asset: str,
             amount: float, confirm: bool) -> dict:
    """Führt einen Transfer aus — nur nach ausdrücklicher Bestätigung."""
    if amount <= 0:
        return {"ok": False, "error": "Betrag muss > 0 sein."}
    if from_acc == to_acc:
        return {"ok": False, "error": "Quelle und Ziel sind identisch."}

    details = {"from": from_acc, "to": to_acc, "asset": asset, "amount": amount}

    if not confirm:
        # Schritt 1: Bestätigung anfordern (kein Geld bewegt).
        audit.record("transfer_requested", **details)
        return {
            "ok": False,
            "needs_confirmation": True,
            "message": f"Bitte bestätigen: {amount} {asset} von '{from_acc}' nach '{to_acc}'.",
            "details": details,
        }

    # Schritt 2: bestätigt.
    paper = not settings.bitget_configured or settings.dry_run
    if paper:
        audit.record("transfer_executed", mode="paper", **details)
        return {"ok": True, "mode": "paper", "message": "Transfer simuliert (Paper).", "details": details}

    # Echter Transfer würde hier via ccxt erfolgen (Key mit Transfer-Recht nötig).
    audit.record("transfer_blocked", reason="kein Transfer-Key", **details)
    return {
        "ok": False,
        "error": "Echter Transfer erfordert einen Bitget-Key MIT Transfer-Recht "
                 "(aktuell read-only). Bewusst blockiert.",
        "details": details,
    }
