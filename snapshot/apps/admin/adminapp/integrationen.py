"""Vorbereitete Integrations-Slots (Gesetz 5) — ELSTER + Cross-Finanzen.

**NICHT aktiv** und bewusst so: keine echte ELSTER-Übermittlung, **kein** Push an
Dizz Money. Diese Funktionen erzeugen READ-ONLY **Entwürfe** und dokumentieren
den Vertrag, über den die Aktivierung später läuft (World-Chat-Schritt):

- **Cross-Zugriff Finanzen ↔ Bürokratie**: aus einer Rechnung wird ein
  Buchungs-ENTWURF abgeleitet (Betrag/Datum heuristisch aus Titel+Volltext).
  Die tatsächliche Übergabe an Dizz Money läuft NUR über den App-Vertrag mit
  Human-in-the-Loop (Beleg bleibt bei der Quelle, ZIEL bestätigt) — derzeit Slot.
- **ELSTER-Brücke**: Beleg-/Frist-Referenz-Export (DATEV/ELSTER-nah). Realistisch
  ist Assistenz (Belege/Fristen verwalten), kein automatisches Filing — s.
  docs/RECHERCHE.md §2/§3.
"""

from __future__ import annotations

import re
from typing import Any

# Default-Konten je Dokumenttyp (SKR-03-nah, nur Vorschlag/Entwurf).
_KONTO = {"Rechnung": "Aufwand (zu prüfen)", "Vertrag": "Daueraufwand (zu prüfen)",
          "Steuer": "Steuern (zu prüfen)", "Sonstiges": "noch zuzuordnen"}

# Geldbeträge: „1.234,56", „1234.56", optional € / EUR.
_BETRAG = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.\s]\d{3})*|\d+)(?:[.,](\d{2}))\s*(?:€|EUR|euro)?",
                     re.IGNORECASE)
_DATUM = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"
                    r"|\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")


def _finde_betrag(text: str) -> float | None:
    bester = None
    for m in _BETRAG.finditer(text or ""):
        ganz = m.group(1).replace(".", "").replace(" ", "")
        try:
            wert = float(f"{ganz}.{m.group(2)}")
        except ValueError:
            continue
        if bester is None or wert > bester:   # heuristisch: größter Betrag = Endsumme
            bester = wert
    return bester


def _finde_datum(text: str) -> str | None:
    m = _DATUM.search(text or "")
    if not m:
        return None
    if m.group(1):                              # ISO YYYY-MM-DD
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return f"{m.group(6)}-{int(m.group(5)):02d}-{int(m.group(4)):02d}"   # TT.MM.JJJJ


def buchungsvorschlag(dok: dict[str, Any]) -> dict[str, Any]:
    """READ-ONLY Buchungs-Entwurf aus einem Dokument (Heuristik). Erzeugt KEINE
    Buchung und ruft Dizz Money NICHT — die Übergabe ist der Cross-App-HITL-Slot."""
    text = f"{dok.get('titel', '')}\n{dok.get('volltext', '')}"
    return {
        "status": "entwurf",
        "ziel_app": "finanzen",
        "konto_vorschlag": _KONTO.get(dok.get("typ", "Sonstiges"), "noch zuzuordnen"),
        "betrag": _finde_betrag(text),
        "waehrung": "EUR",
        "datum": _finde_datum(text) or (dok.get("erstellt_am", "") or "")[:10],
        "beleg_referenz": {"app": "admin", "dokument_id": dok.get("id"),
                           "titel": dok.get("titel")},
        "hinweis": ("Vorbereiteter Cross-Zugriff (Slot, NICHT aktiv): Übergabe an "
                    "Dizz Money erst nach Freigabe (HITL) über den App-Vertrag; der "
                    "Beleg bleibt sicher in Dizz Admin, Dizz Money referenziert ihn."),
    }


def elster_referenz(dok: dict[str, Any]) -> dict[str, Any]:
    """Dokumentierter ELSTER-/Beleg-Export-Slot (NICHT aktiv)."""
    return {
        "status": "vorbereitet",
        "format": "DATEV-/ELSTER-Beleg-Referenz",
        "dokument_id": dok.get("id"),
        "typ": dok.get("typ"),
        "hinweis": ("ELSTER-Brücke ist ein dokumentierter Slot: realistisch ist "
                    "Beleg-/Frist-Assistenz (kein automatisches Filing). Aktivierung "
                    "+ Anbindung = separater Schritt (MeinELSTER+ ab 07/2026)."),
    }


def money_lese_bruecke(dok: dict[str, Any]) -> dict[str, Any]:
    """Cross-Money **READ-ONLY**-SLOT (HITL-Vorbereitung, v3) — skizziert die
    LESE-Brücke Admin → Dizz Money: „Ist dieser Beleg dort schon verbucht?".

    Erzeugt KEINE Buchung, bewegt KEIN Geld, ruft Money NICHT. Es beschreibt nur
    die geplante read-only-Abfrage (Richtung Rück-Lese, analog ``memory_suche``).
    Die echte Verdrahtung (Money-``/api/belege/suche``-Gegenstück + Cross-App-
    Vertrag) ist ein World-Chat-Schritt. NIE Echtgeld/Schreib-Aktionen auslösen."""
    return {
        "status": "slot",                      # bewusst inaktiv
        "richtung": "lese",                    # Admin liest, schreibt NIE
        "ziel_app": "finanzen",
        "frage": "beleg_verbucht?",
        "anfrage_entwurf": {                    # so SÄHE die spätere Lese-Abfrage aus
            "endpoint": "GET /api/querverbindung/finanzen/belege/suche (geplant)",
            "params": {"ref": "admin:dokument:" + str(dok.get("id")),
                       "betrag": _finde_betrag(f"{dok.get('titel', '')}\n{dok.get('volltext', '')}")},
        },
        "beleg_referenz": {"app": "admin", "dokument_id": dok.get("id"),
                           "titel": dok.get("titel")},
        "hinweis": ("READ-ONLY-Slot, NICHT aktiv: löst niemals eine Buchung oder "
                    "Echtgeld-Aktion aus. Sobald Dizz Money die Lese-Gegenseite + "
                    "Cross-App-Vertrag hat (World-Chat), liefert dies den Verbuchungs-"
                    "Status eines Belegs — rein informativ, weiterhin ohne Schreibrecht."),
    }


# Heuristisches Auto-Tagging (0-€, keine KI nötig): Dokumenttyp + Jahre + Schlagworte.
_TAG_WORTE = {
    "finanzamt": "finanzamt", "versicherung": "versicherung", "kfz": "kfz",
    "miete": "miete", "mietvertrag": "miete", "kaution": "miete",
    "gehalt": "einkommen", "lohn": "einkommen", "rente": "einkommen",
    "strom": "energie", "gas": "energie", "wasser": "energie",
    "kündigung": "kündigung", "kuendigung": "kündigung",
    "mahnung": "mahnung", "rechnung": "rechnung", "vertrag": "vertrag",
    "telekom": "telekom", "internet": "internet", "kredit": "kredit", "darlehen": "kredit",
}
_JAHR = re.compile(r"\b(20\d{2})\b")


def tag_vorschlaege(dok: dict[str, Any], max_tags: int = 6) -> list[str]:
    """Schlägt Tags vor (Heuristik) — Typ + Jahre + Schlagworte aus Titel/Volltext.
    Bereits vorhandene Tags werden ausgelassen. Reiner Vorschlag (Nutzer kuratiert)."""
    text = f"{dok.get('titel', '')}\n{dok.get('volltext', '')}".lower()
    schon = {str(t).lower() for t in (dok.get("tags") or [])}
    out: list[str] = []

    def _add(t: str) -> None:
        if t and t.lower() not in schon and t not in out:
            out.append(t)

    typ = dok.get("typ", "")
    if typ and typ != "Sonstiges":
        _add(typ.lower())
    for wort, tag in _TAG_WORTE.items():
        if wort in text:
            _add(tag)
    for jahr in dict.fromkeys(_JAHR.findall(text)):    # eindeutige Jahre, Reihenfolge
        _add(jahr)
    return out[:max_tags]
