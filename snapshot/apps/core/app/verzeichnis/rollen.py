"""Verzeichnis-KEIM (§B4 / V-BIZZI-2, D2, docs/84) — Core-Naht der Subjekt-Quelle.

Die *einzige* vertrauenswürdige Quelle für Rollen + Bereiche je Identität, die
``charta.antrag_bauen`` (CH-5) speist — kein Client liefert je eigene Subjekt-
Attribute. Die wiederverwendbare KEIM-Logik ist Single-Source in
``appkit.charta_verzeichnis`` (byte-stabil, Muster wie ``chronik``/``charta``);
hier liegt NUR die dünne App-Naht an Cores modul-basierte DB.

★ **Umfang = Lese-Substrat** (World-Admin-Entscheid 13.07.): Tabelle
(``_ensure_verzeichnis_schema`` in ``db.py``) + Subjekt-Quelle (``rollen_von`` /
``belegschaft``) + Lese-Routen (``main.py``). Die **schreibenden**
``zuweisen``/``entziehen`` (Rollen-Zuweisung/-Entzug) emittieren ``verzeichnis.rolle``-
Chronik-Ereignisse (hash_only, gepfeffert) und werden bewusst NICHT hier
gespiegelt: Core hat heute kein Chronik-Substrat und keinen Versiegler (nur Moneys
On-demand-Chronist über ``Quelle('money')``). Sie reiten mit dem netzweiten
Chronik-Schritt mit (B2). Bis dahin ist die Tabelle die Quelle; steht (noch) keine
Rolle, behandelt die Charta den Antrag fail-closed (deny-default, CH-1) — ehrlich,
kein stilles Durchrutschen.

★ **Kein Provisorium** (§B4): B5 baut GENAU diesen Keim per Dual-Read (SSO/SCIM)
zum Vollmodul aus — dieselbe Tabelle, dieselbe Lese-API.
"""

from __future__ import annotations

from appkit import charta_verzeichnis as V

from ..db import get_conn


def rollen_von(user_id: str, *, zum: str | None = None) -> dict:
    """Rollen + Bereiche einer Identität — nur GÜLTIGE Zeilen (``gueltig_ab``/``bis``
    + Soft-Delete). ``zum`` (ISO) erlaubt Replay auf einen historischen Zeitpunkt.
    Rückgabe ``{rollen: [...], bereiche: [...]}`` als sortierte Listen (JSON-fähig +
    deterministisch; ``charta.antrag_bauen`` nimmt beliebige Iterables)."""
    roh = V.rollen_von(get_conn(), user_id, zum=zum)
    return {"rollen": sorted(roh["rollen"]), "bereiche": sorted(roh["bereiche"])}


def belegschaft(*, edition: str = "bizzi", zum: str | None = None) -> list[dict]:
    """Aggregierte Belegschaft für den Erreichbarkeits-Enumerator (CH-14): Rollen +
    Bereiche je Identität, Assurance/Frische = best case. Beantwortet „wer ist
    STRUKTURELL fähig, sofern stark authentifiziert" — Basis der „tote Artikel"-/
    SoD-Berichte (``appkit.charta_erreichbar``)."""
    return V.belegschaft(get_conn(), edition=edition, zum=zum)
