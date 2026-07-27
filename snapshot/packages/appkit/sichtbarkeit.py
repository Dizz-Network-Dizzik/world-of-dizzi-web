"""Auth-Sichtbarkeits-Politik + Gesperrt-Zustand (docs/70 §3.2, Baustein B-LOCK/F-2).

FP-6-Befund (docs/60 F-2): zwei gegensätzliche Vertrauensmodelle — Money
maskiert unangemeldet ALLES als stille Leere („0,00 € · alles im grünen
Bereich"), Communication/Healthy zeigen alles. **G-UX-AUTH ✅ (David,
03.07.2026)** hat die Politik je Edition (docs/56) entschieden; dieses Modul
kodiert sie als EINE Entscheidungsfunktion + liefert die „gesperrt"-Bausteine,
damit nie wieder stille Leere entsteht:

- ``zugriff(edition, level, klasse=…)`` → ``frei | anmelden | reauth | wand``
- ``gesperrt_summary(...)`` → Dashboard-Kachel mit ``status="gesperrt"``
  (🔒 statt Pseudo-Nullen; Werte reisen NUR maskiert als „•••")
- ``gesperrt_payload(...)`` → strukturierte Endpoint-Antwort statt stillem ``[]``

Kernsatz (Invariante docs/70 §9.4): **gesperrt ≠ leer ≠ fehler.** Eine App
behauptet NIE „alles in Ordnung", wenn sie die Datenbasis nicht sehen darf.
"""

from __future__ import annotations

from typing import Any, Literal

from .auth import LEVELS
from .db import now_iso
from .summary import Kpi, Summary

Edition = Literal["lokal-pur", "hybrid", "vollserver"]      # docs/56-Editionen
Klasse = Literal["lesen", "schreiben", "server", "hochsicher"]
Zugriff = Literal["frei", "anmelden", "reauth", "wand"]

_KLASSEN = ("lesen", "schreiben", "server", "hochsicher")
_SENSITIVITAETEN = ("normal", "hoch", "hoechst")

#: Maskierungswert für KPI-Zahlen im gesperrten Zustand (nie echte Werte raten).
MASKE = "•••"

#: Standard-Anmelde-Ziel (Core-Login; ``zurueck``-Param gehört zum Link-Vertrag,
#: docs/70 §3.2 — die Netz-Leiste/CTAs hängen ihn clientseitig an).
LOGIN_URL = "/id/login"


def zugriff(edition: str, level: str = "lokal", *,
            klasse: str = "lesen", sensitivity: str = "normal") -> Zugriff:
    """Die entschiedene Editions-Matrix (G-UX-AUTH) als Funktion — fail-closed.

    | Edition    | Regel                                                        |
    |------------|--------------------------------------------------------------|
    | vollserver | ohne Anmeldung ``wand`` (Login-Wand für die ganze App)        |
    | hybrid     | lokal ``frei``; ``klasse="server"`` (Boost/Sync/Remote) erst  |
    |            | ab Stufe „verifiziert" (sonst ``anmelden``)                   |
    | lokal-pur  | nutzbar ohne Login — das Gerät IST die Grenze (auch für       |
    |            | hoch/höchst-ANSICHT, David 03.07.)                            |

    ``klasse="hochsicher"`` (Echtgeld · Export · Löschen · Tresor-Werte ·
    Live-Schaltung) verlangt in JEDER Edition ``reauth`` — frischer Step-up
    auch innerhalb aktiver Session (docs/19 §2 ``reauth_sensibel``; die
    Frische-Prüfung selbst macht ``auth.require_fresh_stepup``).

    Fail-closed: unbekannte Edition ⇒ ``wand``; unbekannte Klasse ODER
    unbekannte Sensitivität ⇒ wird wie ``hochsicher`` behandelt.
    """
    stufe = LEVELS.get(level, 0)                 # unbekannte Stufe = niedrigste
    if klasse not in _KLASSEN or sensitivity not in _SENSITIVITAETEN:
        klasse = "hochsicher"                    # Unbekanntes = strengste Klasse
    if klasse == "hochsicher":
        return "reauth"                          # editions-unabhängige Pflicht
    if edition == "vollserver":
        return "frei" if stufe >= LEVELS["verifiziert"] else "wand"
    if edition == "hybrid":
        if klasse == "server":
            return "frei" if stufe >= LEVELS["verifiziert"] else "anmelden"
        return "frei"
    if edition == "lokal-pur":
        return "frei"
    return "wand"                                # unbekannte Edition: fail-closed


def gesperrt_summary(manifest: Any, grund: str,
                     kpi_labels: tuple[str, ...] | list[str] = ()) -> Summary:
    """Dashboard-Kachel im Gesperrt-Zustand (Vertrags-Erweiterung summary.py).

    ``status="gesperrt"`` + Pflicht-``note`` (der Kunde erfährt WARUM und WAS
    hilft, z. B. „Mit Dizzi-ID anmelden, um deine Finanzen zu sehen"). KPI-
    Werte werden ausschließlich als ``MASKE`` („•••") geliefert — der Core-
    Panel-Renderer zeigt 🔒 statt „0,00" (deckt CO-1/MO-1).
    """
    grund = (grund or "").strip()
    if not grund:
        raise ValueError("gesperrt braucht einen Grund — nie kommentarlos "
                         "sperren (docs/70 §3.2, Invariante 4)")
    kpis = [Kpi(id=f"gesperrt_{i}", label=label, value=MASKE)
            for i, label in enumerate(kpi_labels)]
    return Summary(ok=True, app=manifest.id, name=manifest.name, ts=now_iso(),
                   status="gesperrt", kpis=kpis, note=grund)


def gesperrt_payload(grund: str, login_url: str = LOGIN_URL) -> dict[str, Any]:
    """Endpoint-Antwort statt stillem ``[]``: sagt „gesperrt" + den Weg.

    Konvention fürs Frontend (ux-kit ``DzUx.gesperrt``): HTTP 200, Körper
    ``{"gesperrt": true, "grund": …, "login_url": …}`` — bewusst 200, damit
    Bestands-Fetch-Ketten nicht in Fehlerpfade laufen; der ZUSTAND steht im
    Körper (dasselbe Prinzip wie der Summary-Vertrag).
    """
    grund = (grund or "").strip()
    if not grund:
        raise ValueError("gesperrt braucht einen Grund — nie kommentarlos "
                         "sperren (docs/70 §3.2, Invariante 4)")
    return {"gesperrt": True, "grund": grund, "login_url": login_url}
