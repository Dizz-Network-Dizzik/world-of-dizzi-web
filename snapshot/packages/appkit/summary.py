"""Stats-Vertrag — das generische Kachel-Format für Dizzis Dashboard.

Kernidee der K3-Generalisierung: statt dass Dizzi für jede App eigenen
Mapping-Code pflegt (wie historisch für den Trading Bot), liefert JEDE App
ihre Kennzahlen display-fertig in EINEM Format. Das Dashboard rendert die
KPI-Liste generisch; App-spezifische Tiefe bleibt über eigene Endpoints und
MCP-Tools verfügbar.

Robustheits-Regel: /api/summary antwortet IMMER mit HTTP 200 und trägt den
Zustand im ``status``-Feld ('ok' | 'leer' | 'fehler' | 'gesperrt') — eine
kaputte App darf das Dashboard nie mit 500ern fluten.

'gesperrt' (docs/70 §3.2, F-2): die App DARF ihre Datenbasis mangels
Anmeldung nicht zeigen — das ist weder 'leer' noch 'fehler'. Kacheln rendern
dann 🔒 + ``note`` statt Pseudo-Nullen; KPI-Werte reisen nur maskiert („•••").
Bauhilfe: ``sichtbarkeit.gesperrt_summary(...)``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from . import CONTRACT_VERSION


class Kpi(BaseModel):
    """Eine display-fertige Kennzahl der Dashboard-Kachel."""

    id: str                                     # stabiler Schlüssel, z. B. 'saldo'
    label: str                                  # Anzeigetext, z. B. 'Saldo'
    value: Any                                  # Zahl oder kurzer String
    unit: str | None = None                     # z. B. '€', '%', 'Stk'
    trend: Literal["up", "down", "flat"] | None = None


class Summary(BaseModel):
    """Antwort-Schema von ``GET /api/summary``."""

    ok: bool = True
    app: str
    name: str
    contract: str = CONTRACT_VERSION
    ts: str
    status: Literal["ok", "leer", "fehler", "gesperrt"] = "ok"
    kpis: list[Kpi] = []
    note: str | None = None                     # kurzer Zustands-/Fehlerhinweis


def normalize(app_id: str, name: str, ts: str, result: Any) -> Summary:
    """Normalisiert das Ergebnis der App-``summary_fn`` auf das Vertrags-Schema.

    Erlaubte Rückgaben der App: fertige ``Summary``, eine ``list[Kpi]`` (auch als
    dicts) oder ein dict mit Summary-Feldern. Leere KPI-Liste ⇒ status 'leer'.
    """
    if isinstance(result, Summary):
        return result
    if isinstance(result, list):
        kpis = [k if isinstance(k, Kpi) else Kpi(**k) for k in result]
        status: Literal["ok", "leer"] = "ok" if kpis else "leer"
        return Summary(app=app_id, name=name, ts=ts, status=status, kpis=kpis)
    if isinstance(result, dict):
        merged: dict[str, Any] = {"app": app_id, "name": name, "ts": ts, **result}
        return Summary(**merged)
    raise TypeError(f"summary_fn lieferte unbrauchbaren Typ: {type(result)!r}")
