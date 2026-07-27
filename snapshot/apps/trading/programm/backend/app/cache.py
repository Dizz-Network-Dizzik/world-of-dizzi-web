"""cache.py — winziger, thread-sicherer TTL-Memo für teure Read-Aggregationen.

Mehrere UI-Panels stoßen pro Refresh dieselbe schwere Auswertung an (z. B. ``governor.evaluate`` läuft
für Governor-Panel, Monitoring-Panel UND Alert-Leiste). Diese Aggregationen iterieren alle Bots inkl.
SQLite-Zugriff (~400 ms). Ein kurzer TTL-Cache kollabiert die Mehrfach-Aufrufe innerhalb eines
Refresh-Bursts auf **eine** Berechnung — ohne die Aktualität spürbar zu verschlechtern.

WICHTIG: nur für **read-only**-Pfade gedacht. Aktiv eingreifende Pfade (z. B. ``governor.run_once``)
holen sich bewusst eine **frische** Auswertung und invalidieren danach (``invalidate``)."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def ttl_get(key: str, ttl: float, producer: Callable[[], Any]) -> Any:
    """Liefert den gecachten Wert zu ``key``, wenn jünger als ``ttl`` Sekunden — sonst berechnet
    ``producer()`` neu (außerhalb des Locks, damit teure Arbeit nicht serialisiert)."""
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit is not None and (now - hit[0]) < ttl:
            return hit[1]
    value = producer()
    with _lock:
        _store[key] = (time.monotonic(), value)
    return value


def invalidate(key: str | None = None) -> None:
    """Verwirft einen Schlüssel (oder den ganzen Cache bei ``None``) — nach einem mutierenden Eingriff."""
    with _lock:
        if key is None:
            _store.clear()
        else:
            _store.pop(key, None)
