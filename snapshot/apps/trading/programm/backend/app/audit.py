"""Audit-Log — append-only Protokoll sicherheitsrelevanter Vorgänge.

Pflicht-Feature wegen DAC8/Steuer-Dokumentation (siehe docs/LEGAL.md). Jeder
Eintrag ist eine JSON-Zeile (JSONL) in ``data/audit.log`` — maschinen- und
menschenlesbar, leicht als CSV/Steuer-Export weiterzuverarbeiten (ab M3/M6).

Beispiel-Ereignisse: Bot angelegt/gelöscht, Limit verletzt (Kill-Switch),
Transfer bestätigt, Echtgeld scharfgeschaltet, Strategie-Katalog refresht.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR

AUDIT_FILE = DATA_DIR / "audit.log"


def record(event: str, **details: Any) -> dict[str, Any]:
    """Schreibt einen Audit-Eintrag und gibt ihn zurück.

    Args:
        event: Kurzname des Ereignisses, z. B. ``"bot_created"``.
        **details: Beliebige zusätzliche, JSON-serialisierbare Felder.

    Returns:
        Den geschriebenen Eintrag als Dict.
    """
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **details,
    }
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_all() -> list[dict[str, Any]]:
    """Liest alle Audit-Einträge (für Anzeige/Export)."""
    if not AUDIT_FILE.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in AUDIT_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries
