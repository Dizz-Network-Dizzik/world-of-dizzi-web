"""Kanonisches App-Verzeichnis des Dizz-Netzwerks (docs/70 §3.1, Baustein B-NAV/F-1).

Bisher wusste NUR der Core, welche Apps es gibt (eigene Panel-Seeds) — jede
andere App war eine Navigations-Insel (FP-6-Audit, docs/60 F-1). Dieses Modul
ist die EINE code-kanonische Quelle „welche Apps hat das Netz": statische
Daten, kein Cross-App-Call, funktioniert offline und in jeder Edition.

Verbraucher:
- ``netz_router()`` → ``GET /api/netz/apps`` in jeder App (create_app ``netz=True``):
  Datenquelle der ui-kit-Netz-Leiste (``DzUx.netzleiste``, ux-kit.js).
- Perspektivisch: Core-Panel-Seeds können hierauf umziehen (Single-Source).

Die Werte sind 1:1 gegen die realen App-Manifeste verifiziert (04.07.2026);
``id`` = Manifest-/MCP-Namensraum-ID (NICHT der Ordnername: money→``finanzen``,
communication→``kommunikation``, creating→``creator``, healthy→``health``,
trading→``tradingbot``). Ändert eine App Marke/Port, wird HIER nachgezogen
(Doku-Sync, Gesetz 9).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, computed_field

from .manifest import Sensitivity

#: Die Zentrale — Konvention wie app_gateway.py (localhost-Netz, docs/16).
CORE_URL = "http://127.0.0.1:8200"


class NetzApp(BaseModel):
    """Ein Eintrag des Netz-Verzeichnisses (display-fertig für die Netz-Leiste)."""

    id: str                              # Manifest-ID (z. B. 'finanzen')
    brand: str                           # Marke, betont (K2.3), z. B. 'Dizz Money'
    name: str                            # Funktionsname, dezent (K2.3)
    port: int
    icon: str = "box"                    # Icon-Schlüssel der Dizzi-Shell
    sensitivity: Sensitivity = "normal"  # hoechst ⇒ Netz-Leiste zeigt 🛡

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


#: Das Verzeichnis — Reihenfolge = Anzeige-Reihenfolge der Netz-Leiste
#: (Zentrale zuerst, dann die Apps im Kachel-Rhythmus des Core-Dashboards).
NETZ_APPS: tuple[NetzApp, ...] = (
    NetzApp(id="core", brand="Dizzi-Core", name="Kommandozentrale",
            port=8200, icon="home"),
    NetzApp(id="news", brand="Dizz News", name="News Compact",
            port=8216, icon="globe"),
    NetzApp(id="finanzen", brand="Dizz Money", name="Finanzmanagement",
            port=8210, icon="wallet", sensitivity="hoch"),
    NetzApp(id="kommunikation", brand="Dizz Communication", name="Nachrichtenverkehr",
            port=8218, icon="mail", sensitivity="hoechst"),
    NetzApp(id="creator", brand="Dizz Creating", name="Medien-Suite",
            port=8214, icon="wand", sensitivity="hoch"),
    NetzApp(id="memory", brand="Dizz Memory", name="Wissensspeicher",
            port=8212, icon="archive", sensitivity="hoch"),
    NetzApp(id="management", brand="Dizz Management", name="KI-Agenten",
            port=8213, icon="broadcast", sensitivity="hoch"),
    NetzApp(id="health", brand="Dizz Healthy", name="Gesundheit",
            port=8217, icon="heart", sensitivity="hoechst"),
    NetzApp(id="admin", brand="Dizz Admin", name="Verwaltung",
            port=8222, icon="stamp", sensitivity="hoch"),
    NetzApp(id="tradingbot", brand="Dizz Trading", name="Trading Bot",
            port=8137, icon="chart", sensitivity="hoechst"),
)


def netz_app(app_id: str) -> NetzApp | None:
    """Verzeichnis-Eintrag zu einer App-ID (None statt KeyError — Anzeige-Pfad)."""
    for a in NETZ_APPS:
        if a.id == app_id:
            return a
    return None


def netz_router() -> APIRouter:
    """``GET /api/netz/apps`` — das Verzeichnis für die ui-kit-Netz-Leiste.

    Antwort: ``{"core_url": …, "apps": [NetzApp…]}``. Reine Konstanten ⇒ keine
    Auth-Stufe nötig (es sind dieselben localhost-Links, die der Core zeigt).
    """
    r = APIRouter(tags=["netz"])

    @r.get("/api/netz/apps")
    def get_netz_apps() -> dict:
        return {"core_url": CORE_URL,
                "apps": [a.model_dump() for a in NETZ_APPS]}  # inkl. computed url

    return r
