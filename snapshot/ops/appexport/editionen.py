"""Editionen × Pakete — Freigabe-Regelwerk (docs/66 §6, fail-closed I-7).

Datengetrieben und pur: WAS auslieferbar ist, steht hier als Tabelle; das
Bündel-Werkzeug fragt nur ``ist_auslieferbar()``. Unbekannte App oder unbekannte
Edition ⇒ ``False`` — nie eine Exception, nie ein stilles Ja (fail-closed).
"""

from __future__ import annotations

EDITIONEN: tuple[str, ...] = ("lokal", "hybrid", "server")   # docs/56 §1 (E-LOKAL/E-HYBRID/E-SERVER)
PAKET_TYPEN: tuple[str, ...] = ("einzel", "bundle", "gesamt")  # docs/56 §2.2
SENSITIVITAETEN: tuple[str, ...] = ("normal", "hoch", "hoechst")

# „Core immer dabei" (docs/56 §2.1): diese Apps nimmt der Builder in JEDES Bündel auf.
KERN_APPS: tuple[str, ...] = ("core",)

# Freigabe-Matrix v1 (docs/66 §6.1). Leere Menge = heute NICHT auslieferbar (Gate offen
# oder grundsätzlich gesperrt) — die Begründung steht im Vertrag, nicht hier dupliziert.
APP_FREIGABEN: dict[str, frozenset[str]] = {
    "core": frozenset(),            # nie einzeln verkäuflich; via KERN_APPS immer Bestandteil
    "news": frozenset({"lokal"}),
    "memory": frozenset({"lokal"}),
    "communication": frozenset({"lokal"}),
    "money": frozenset({"lokal"}),  # Kern ohne Bank/ELSTER-Wire; deren Gates hängen an den Komponenten (lizenz.py)
    "creating": frozenset(),        # G-FLUX-LIZENZ / G-MODELL-LIZENZ offen (docs/66 §12.3)
    "management": frozenset({"lokal"}),   # hoch ⇒ lokal_only
    "admin": frozenset({"lokal"}),        # hoch ⇒ lokal_only
    "healthy": frozenset(),         # hoechst: erst nach SQLITE-SEE-Entscheid (docs/66 §12.4)
    "trading": frozenset(),         # NIE exportieren (Echtgeld-System, docs/66 §6.1)
}


def erlaubte_editionen(app_id: str) -> frozenset[str]:
    """Freigegebene Editionen einer App; unbekannte App ⇒ leere Menge (fail-closed)."""
    return APP_FREIGABEN.get(app_id, frozenset())


def ist_auslieferbar(app_id: str, edition: str) -> bool:
    """Fail-closed: nur ausdrücklich freigegebene (App, Edition)-Paare sind wahr."""
    return edition in EDITIONEN and edition in erlaubte_editionen(app_id)
