"""Börsen-/Session-Eröffnungen — kanonische Zeit-Struktur des Marktes (UTC).

Sonder-Thema „Markt-Eröffnungen": Krypto handelt 24/7, zeigt aber über Jahre
stabile **Sessions** (Asien/Tokio, London/EU, USA/NY) mit Volatilitäts-/
Liquiditäts-Spitzen an den **Opens**. Dieses Modul ist die EINE Quelle für die
Session-Zeiten — genutzt von der Lern-Schicht (`meta.py`), dem Tracker und den
Tests. Die Engine-Strategie (eigene venv) dupliziert die Zeiten bewusst inline
(siehe ``engine/.../session_open_breakout.py``) und referenziert dieses Modul.

Alles in **UTC**. Siehe ``docs/BOERSENEROEFFNUNGEN.md`` für die Recherche-Basis.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Grobe, NICHT überlappende Session-Bänder über 24 h (für die Lern-Zuordnung:
# jeder Trade fällt in genau ein Band). Reihenfolge = Tagesverlauf.
# (start_h inklusive, end_h exklusiv; UTC.)
SESSION_BANDS: list[tuple[str, int, int]] = [
    ("asia", 0, 7),            # Asien-Phase (Tokio-Open 00:00)
    ("london", 7, 13),         # London/EU-Phase (Open ~07:00–08:00)
    ("eu_us_overlap", 13, 16),  # EU↔US-Overlap — Vola-/Liquiditäts-Peak
    ("us", 16, 21),            # US-Hauptphase
    ("late_us", 21, 24),       # späte US-Phase (empirisch starke BTC-Stunden)
]

# Schmale OPEN-Fenster (UTC) — die eigentlichen „Eröffnungen" für ORB/Opening-Systeme.
SESSION_OPENS: list[dict] = [
    {"key": "asia", "label": "Asia-Open", "start_h": 0, "end_h": 2},
    {"key": "london", "label": "London-Open", "start_h": 7, "end_h": 9},
    {"key": "us", "label": "US-Open", "start_h": 13, "end_h": 15},
]

# Anzeige-Labels (Deutsch) je Session-Schlüssel.
SESSION_LABELS: dict[str, str] = {
    "asia": "Asien (Tokio)",
    "london": "London / EU",
    "eu_us_overlap": "EU/US-Overlap",
    "us": "USA / NY",
    "late_us": "Späte US-Phase",
}

# Gültige `opening_session`-Werte für Katalog-Systeme (Recherche-Tool).
OPENING_SESSIONS: set[str] = {"asia", "london", "us", "eu_us_overlap", "none"}


def to_utc(dt: datetime | None) -> datetime | None:
    """Macht ``dt`` aware-UTC. Naive Stempel werden als UTC interpretiert
    (Freqtrade-Trade-DBs speichern UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def session_for(dt: datetime | None) -> str | None:
    """Grobes Session-Band für einen beliebigen Zeitpunkt (eines der
    ``SESSION_BANDS``-Labels). ``None`` bei fehlendem Zeitpunkt.

    Für die Lern-Zuordnung: ordnet jeden Trade GENAU einem Band zu.
    """
    dt = to_utc(dt)
    if dt is None:
        return None
    h = dt.hour
    for key, start, end in SESSION_BANDS:
        if start <= h < end:
            return key
    return None  # pragma: no cover — Bänder decken 0–24 vollständig ab


def opening_window(dt: datetime | None) -> dict | None:
    """Liefert das ``SESSION_OPENS``-Fenster, falls ``dt`` in einem schmalen
    OPEN-Fenster liegt (Asia/London/US-Open), sonst ``None``.

    Grundlage für Opening-Range-Breakout & Co.: „Sind wir gerade in einer
    Börseneröffnung — und in welcher?"
    """
    dt = to_utc(dt)
    if dt is None:
        return None
    h = dt.hour
    for w in SESSION_OPENS:
        if w["start_h"] <= h < w["end_h"]:
            return w
    return None


def session_label(key: str | None) -> str:
    """Menschliches Label zu einem Session-Schlüssel (Fallback: der Schlüssel)."""
    if not key:
        return "—"
    return SESSION_LABELS.get(key, key)
