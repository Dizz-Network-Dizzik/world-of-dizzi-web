"""Sprachregister — Kunden-Sprache vorn, Interna hinten (docs/70 §3.6+§3.8, F-6/F-8).

FP-6-Befund (docs/60 F-6): Insider-/Doku-Sprache im Kunden-UI („HITL" als
Button-Text, „v1 DORMANT", „(Gesetz 5)", „REV-3, POST /api/…",
„Apache-Verkaufs-Anker", „waterproof-kommerziell"). Dieses Modul ist das
KANONISCHE Kunden-Lexikon + der Wächter dagegen:

- ``kunden_label(begriff)``  → die verbindliche Kunden-Übersetzung
- ``pruefe_text(text)``      → Lint: welche Insider-Begriffe stehen im Text?
  (läuft in Tests + in der Rollout-Checkliste je App, docs/70 §8)
- ``datum_de(wert)``         → EINE deutsche Datums-Formatierung (F-8) —
  serverseitiges Pendant zu ``DzUx.format.datum`` (ux-kit.js), regelgleich.
- Anrede-/Anmelde-Pill-Norm als Konstanten (F-8).

Regel (docs/70 §2.3): sichtbares Label = Kunden-Sprache; der Fachbegriff darf
ZUSÄTZLICH in den ``title``-Tooltip oder in die Doku — nie umgekehrt.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

# ── F-8 · Anrede- & Wortlaut-Normen ─────────────────────────────────────────
#: Netz-Anrede (Gate G-UX-ANREDE, Empfehlung „du" — Healthy-Ton = Referenz).
ANREDE = "du"
#: Anmelde-Pille, EIN Wortlaut netzweit (nie „Dizzi-ID" nackt, nie „Anmelden" ohne Kontext).
ANMELDE_PILL_ABGEMELDET = "Anmelden (Dizzi-ID)"
ANMELDE_PILL_ANGEMELDET = "{anzeigename} · {stufe}"   # Stufen-Wörter aus auth.LEVELS

# ── F-6 · Kunden-Lexikon (Insider-Begriff → sichtbares Kunden-Label) ────────
KUNDEN_LEXIKON: dict[str, str] = {
    # Freigabe-/Agenten-Vokabular
    "HITL": "mit Freigabe",
    "Senden (HITL)": "Senden (mit Freigabe)",
    "DORMANT": "vorbereitet — bewusst noch aus",
    "v1 DORMANT": "vorbereitet — bewusst noch aus",
    "idempotent": "mehrfach klicken ist unschädlich",
    # Lizenz-Interna (Creating, docs/60 CR-3)
    "waterproof-kommerziell": "kommerziell nutzbar",
    "Apache-Verkaufs-Anker": "kommerziell nutzbar (Apache-Lizenz)",
    # Trading-T5-Panel (docs/70 §5.4, verbindliche UX-T-Labels)
    "Politik→Hand-Brücke": "Master-Steuerung: Empfehlung → Ausführung",
    "L1": "Logik-Wahl",
    "L2": "Einsatz-Dämpfung",
    "L3": "Einstiegs-Bremse",
    "stake_scale": "Einsatz-Faktor",
    "proposal": "Vorschlags-Modus",
    "apply": "Ausführungs-Modus",
}

#: Muster, die in sichtbaren Kunden-Texten NIE auftauchen dürfen (case-sensitiv —
#: es sind spezifische Akronyme/Referenzen; „Apply" als normales Wort bleibt frei).
INTERNA_MUSTER: tuple[str, ...] = (
    "HITL", "DORMANT", "§R-G", "(Gesetz", "(V1", "REV-",
    "POST /api", "GET /api", "waterproof", "Verkaufs-Anker", "stake_scale",
    "idempotent",
)


def kunden_label(begriff: str) -> str:
    """Kanonische Kunden-Übersetzung; unbekannte Begriffe unverändert (Identität)."""
    return KUNDEN_LEXIKON.get(begriff, begriff)


def pruefe_text(text: str) -> list[str]:
    """Lint: welche Insider-Begriffe stehen im (sichtbaren) Text? [] = sauber."""
    text = text or ""
    return [m for m in INTERNA_MUSTER if m in text]


# ── F-8 · Datums-Norm (regelgleich mit DzUx.format.datum in ux-kit.js) ──────
_WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _parse_datum(wert: Any) -> datetime | None:
    """Nimmt datetime, ISO-8601 und RFC-822 (die zwei realen Feed-Formate)."""
    if isinstance(wert, datetime):
        return wert
    if not isinstance(wert, str) or not wert.strip():
        return None
    s = wert.strip()
    try:                                          # ISO-8601 („2026-07-03T14:35:00+02:00")
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:                                          # RFC-822 („Fri, 03 Jul 2026 14:33:44 +0200")
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None


def datum_de(wert: Any, *, mit_zeit: bool = True,
             jetzt: datetime | None = None) -> str:
    """EINE deutsche, relative Datums-Anzeige (docs/70 §3.8):

    „heute 14:33" · „gestern 09:12" · letzte 6 Tage „Mo 01.07." ·
    selbes Jahr „01.07." · sonst „01.07.2025". Unparsebares kommt als
    Rohstring zurück (ehrlich — nie „Invalid Date"). ``jetzt`` ist für
    Tests injizierbar; naive Zeiten gelten als lokal.
    """
    dt = _parse_datum(wert)
    if dt is None:
        return str(wert)
    jetzt = jetzt or datetime.now().astimezone()
    if jetzt.tzinfo is None:
        jetzt = jetzt.astimezone()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=jetzt.tzinfo)      # naive = lokale Zeit
    lokal = dt.astimezone(jetzt.tzinfo)
    zeit = f" {lokal:%H:%M}" if mit_zeit else ""
    heute, tag = jetzt.date(), lokal.date()
    if tag == heute:
        return f"heute{zeit}"
    if tag == heute - timedelta(days=1):
        return f"gestern{zeit}"
    alter = (heute - tag).days
    if 1 < alter <= 6:
        return f"{_WOCHENTAGE[lokal.weekday()]} {lokal:%d.%m.}"
    if tag.year == heute.year:
        return f"{lokal:%d.%m.}"
    return f"{lokal:%d.%m.%Y}"
