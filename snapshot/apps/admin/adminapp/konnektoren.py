"""Externe-Tool-Konnektoren von Dizz Admin (Konnektivitäts-Vision docs/35 §3, D2).

Admin soll **externe Tools/Dienste** (fremde Kalender-, Projekt-, Office-Tools) in
die eigene **Bereichs-/Fristen-Sicht** einklinken — Überblick behalten UND ansteuern.
Die **Bereichs-Achse** (docs/28/34) ist der Andockpunkt: ein Konnektor wird optional
an einen Bereich gebunden ("Studium X → Uni-Kalender", "Mandant Y → dessen Trello").

── Status: VORBEREITUNG (Gesetz 5, wie health/sources + management ChannelSource) ──
Dieses Modul liefert **jetzt**: das **Datenmodell** (gebundene Konnektor-Instanzen,
DSGVO-konform) + ein **Typen-Register** (welche externen Tools andockbar sind) +
**dormante Adapter** (Interface + „nicht verbunden, bis Token+Freigabe") + die
**Sichtbarkeit** (`GET /api/konnektoren`) + den **UI-Slot** in der Bereichs-Sicht.
**Echte Plattform-APIs sind NICHT dabei** (Architektur-KI-Park) — sie werden scharf
geschaltet, „wenn nötig" (docs/35 §6).

── Rebase-Ziel (docs/36 W4): appkit/connectors.py ─────────────────────────────
Sobald das **appkit-Connector-Gerüst** vendort ist, wird ``ExternalConnector`` von
dort geerbt und dieses Modul liefert nur noch die admin-spezifischen Adapter +
das Bereichs-Binding. Das Interface ist bewusst minimal gehalten, damit der Rebase
klein bleibt. Outbound („ansteuern") läuft IMMER über das bestehende K4-HITL —
nie autonom (docs/35 §5.2).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from appkit.auth import UserContext, current_user
from appkit.db import Database, new_id, now_iso

from .sources import QuelleNichtVerbunden

# Kategorien externer Tools (UI-Gruppierung + Validierung).
KONNEKTOR_ART = ("kalender", "aufgaben", "projekt", "office", "speicher",
                 "kommunikation", "sonstiges")

# ── Typen-Register: welche externen Tools andockbar sind (alle dormant) ────────
# Reine Daten (kein Plattform-SDK-Import). ``token_name`` = der Tresor-Schlüssel,
# unter dem das Zugriffs-Token/Passwort liegt (OS-Secret-Store, NIE in der DB).
# ``lesen`` = read-only-Einzug vorgesehen; ``steuern`` = Outbound (immer K4-HITL,
# v1 überall False). Mehrere kalender-/aufgaben-Typen haben in ``sources.py`` bereits
# einen Adapter-Rumpf (Import-Pfad) — hier in EINER Tool-Übersicht zusammengeführt.
KONNEKTOR_TYPEN: tuple[dict[str, Any], ...] = (
    {"typ": "google_calendar", "name": "Google Calendar", "art": "kalender",
     "token_name": "google_calendar_refresh_token", "lesen": True, "steuern": False,
     "hinweis": "Termine read-only (OAuth-Refresh-Token im Tresor). "
                "Aktiver Import-Pfad: sources.GoogleCalendarAdapter."},
    {"typ": "caldav", "name": "CalDAV (Nextcloud/Fastmail …)", "art": "kalender",
     "token_name": "caldav_passwort", "lesen": True, "steuern": False,
     "hinweis": "Offener Kalender-Standard — Server-URL + App-Passwort im Tresor."},
    {"typ": "microsoft_outlook", "name": "Microsoft 365 / Outlook", "art": "kalender",
     "token_name": "ms_graph_token", "lesen": True, "steuern": False,
     "hinweis": "Kalender/Mail über Microsoft Graph (read-only) — OAuth-Token im Tresor."},
    {"typ": "notion", "name": "Notion", "art": "projekt",
     "token_name": "notion_token", "lesen": True, "steuern": False,
     "hinweis": "Seiten/Datenbanken (Projekte/Wissen) read-only — Integration-Token im Tresor."},
    {"typ": "trello", "name": "Trello", "art": "projekt",
     "token_name": "trello_token", "lesen": True, "steuern": False,
     "hinweis": "Boards/Karten als Projektquelle read-only — API-Key/Token im Tresor."},
    {"typ": "todoist", "name": "Todoist", "art": "aufgaben",
     "token_name": "todoist_token", "lesen": True, "steuern": False,
     "hinweis": "Aufgaben read-only (Aufgabe-Import-Muster) — API-Token im Tresor."},
    {"typ": "github", "name": "GitHub Issues", "art": "aufgaben",
     "token_name": "github_token", "lesen": True, "steuern": False,
     "hinweis": "Issues → Aufgaben read-only — Repo + PAT im Tresor (sources.GitHubAdapter)."},
    {"typ": "gitlab", "name": "GitLab Issues", "art": "aufgaben",
     "token_name": "gitlab_token", "lesen": True, "steuern": False,
     "hinweis": "Issues → Aufgaben read-only — Repo + PAT im Tresor (sources.GitLabAdapter)."},
    {"typ": "google_drive", "name": "Google Drive / Docs", "art": "office",
     "token_name": "google_workspace_token", "lesen": True, "steuern": False,
     "hinweis": "Dokumente/Dateien read-only — OAuth-Token im Tresor (Tresor-Import-Slot)."},
    {"typ": "microsoft_onedrive", "name": "OneDrive / SharePoint", "art": "speicher",
     "token_name": "ms_graph_token", "lesen": True, "steuern": False,
     "hinweis": "Dateien read-only über Microsoft Graph — OAuth-Token im Tresor."},
)
_TYP_INDEX = {t["typ"]: t for t in KONNEKTOR_TYPEN}

# Datenmodell: gebundene Konnektor-INSTANZEN (der Nutzer dockt einen Typ — optional
# an einen Bereich — an). Vertrags-Konventionen (user_id/Timestamps/Soft-Delete) ⇒
# DSGVO-Export + Lösch-Kaskade greifen ohne Per-App-Code.
SCHEMA_KONNEKTOREN = """
CREATE TABLE IF NOT EXISTS konnektoren (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    typ         TEXT NOT NULL,                  -- Konnektor-Typ (KONNEKTOR_TYPEN)
    name        TEXT NOT NULL DEFAULT '',       -- Anzeigename (Nutzer-vergeben)
    bereich_id  TEXT NOT NULL DEFAULT '',       -- '' = global, sonst an einen Bereich gebunden
    extern_ref  TEXT NOT NULL DEFAULT '',       -- externe Kennung (Kalender-ID/Board-Key/Repo …)
    aktiv       INTEGER NOT NULL DEFAULT 0,     -- dormant: 0, bis Token + Freigabe
    config      TEXT NOT NULL DEFAULT '{}',     -- JSON (zusätzliche, nicht-geheime Parameter)
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_konnektoren ON konnektoren (user_id, bereich_id, typ);
"""


# ── Interface (Rebase-Ziel = appkit/connectors.ExternalConnector, W4) ─────────
class ExternalConnector(ABC):
    """Vertrag, gegen den die App arbeitet — read-only Einzug + Status. Outbound
    („ansteuern") läuft NIE hier, sondern über das bestehende K4-HITL (docs/35 §5.2)."""

    typ: str = "extern"
    art: str = "sonstiges"

    @abstractmethod
    def verfuegbar(self) -> bool:
        """True, sobald das Zugriffs-Token im Tresor liegt (sonst dormant)."""

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Für UI/MCP: verbunden? welcher Tresor-Schlüssel wird erwartet?"""

    def lesen(self, **kw) -> list[dict[str, Any]]:  # noqa: D401 — Slot
        """Read-only-Einzug (dormant bis appkit-Gerüst + Token + Freigabe)."""
        raise QuelleNichtVerbunden(
            f"{self.typ}: Live-Lesen ist noch nicht freigeschaltet "
            "(Datenmodell + Adapter-Rumpf stehen; Aktivierung = appkit-Connector-Gerüst "
            "[docs/36 W4] + Token im Tresor + Freigabe).")

    def ansteuern(self, *a, **k) -> Any:
        """Outbound bleibt strikt HITL — nie über den Konnektor selbst."""
        raise QuelleNichtVerbunden(
            f"{self.typ}: Ansteuern/Schreiben läuft ausschließlich über die K4-HITL-"
            "Freigabe (docs/35 §5.2), nie autonom über den Konnektor.")


class DormantExternalConnector(ExternalConnector):
    """Generischer dormanter Adapter über einem Typ-Register-Eintrag. Bis das
    appkit-Connector-Gerüst (W4) + ein Tresor-Token da sind, meldet er ehrlich
    „nicht verbunden", statt zu raten. Spezialisierte Adapter (z. B. Notion mit
    eigener Paginierung) subklassen ihn bei der Aktivierung."""

    def __init__(self, meta: dict[str, Any], vault_get=None) -> None:
        self.meta = meta
        self.typ = meta["typ"]
        self.art = meta["art"]
        self.token_name = meta.get("token_name", "")
        self._vault_get = vault_get or (lambda _name: None)

    def verfuegbar(self) -> bool:
        if not self.token_name:
            return False
        try:
            return bool(self._vault_get(self.token_name))
        except Exception:  # noqa: BLE001 — Tresor-Fehler ⇒ „nicht verbunden"
            return False

    def status(self) -> dict[str, Any]:
        return {"typ": self.typ, "name": self.meta["name"], "art": self.art,
                "token_name": self.token_name, "verbunden": self.verfuegbar(),
                "lesen": self.meta.get("lesen", False), "steuern": self.meta.get("steuern", False),
                "hinweis": self.meta.get("hinweis", "")}


def connector_for(typ: str, vault_get=None) -> ExternalConnector | None:
    """Factory: liefert den (dormanten) Adapter zu einem Typ — oder None."""
    meta = _TYP_INDEX.get(typ)
    return DormantExternalConnector(meta, vault_get=vault_get) if meta else None


# ── Request-Modelle ──────────────────────────────────────────────────────────
class KonnektorIn(BaseModel):
    typ: str
    name: str = ""
    bereich_id: str = ""
    extern_ref: str = ""
    config: dict[str, Any] = {}


class KonnektorPatch(BaseModel):
    name: str | None = None
    bereich_id: str | None = None
    extern_ref: str | None = None
    aktiv: bool | None = None
    config: dict[str, Any] | None = None


class Konnektoren:
    """CRUD + Sichtbarkeit der externen-Tool-Konnektoren. ``vault`` (appkit-Vault,
    von main.py gesetzt) liefert den Token-Status; ohne Vault gelten alle als
    nicht verbunden (ehrlich)."""

    def __init__(self, db: Database, vault=None) -> None:
        self.db = db
        self.vault = vault   # appkit-Vault (OS-Secret-Store) — Token-Vorhandensein

    # --- Token-Status -------------------------------------------------------
    def _vorhandene_token(self) -> set[str]:
        try:
            return set(self.vault.names()) if self.vault is not None else set()
        except Exception:  # noqa: BLE001
            return set()

    def _verbunden(self, token_name: str, vorhanden: set[str]) -> bool:
        return bool(token_name) and token_name in vorhanden

    def typen(self) -> list[dict[str, Any]]:
        """Das Typen-Register + je Typ ``verbunden`` (Token im Tresor vorhanden?)."""
        vorhanden = self._vorhandene_token()
        return [{**t, "verbunden": self._verbunden(t["token_name"], vorhanden)}
                for t in KONNEKTOR_TYPEN]

    # --- CRUD der gebundenen Instanzen --------------------------------------
    def _public(self, row, vorhanden: set[str]) -> dict[str, Any]:
        meta = _TYP_INDEX.get(row["typ"], {})
        try:
            config = json.loads(row["config"] or "{}")
        except (ValueError, TypeError):
            config = {}
        return {"id": row["id"], "typ": row["typ"],
                "name": row["name"] or meta.get("name", row["typ"]),
                "art": meta.get("art", "sonstiges"), "bereich_id": row["bereich_id"],
                "extern_ref": row["extern_ref"], "aktiv": bool(row["aktiv"]),
                "config": config, "token_name": meta.get("token_name", ""),
                "verbunden": self._verbunden(meta.get("token_name", ""), vorhanden),
                "lesen": meta.get("lesen", False), "steuern": meta.get("steuern", False),
                "hinweis": meta.get("hinweis", ""), "created_at": row["created_at"]}

    def liste(self, user_id: str, *, bereich_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM konnektoren WHERE user_id=? AND deleted_at IS NULL"
        p: list[Any] = [user_id]
        if bereich_id is not None:          # None=alle · ''=nur global · id=Bereich
            q += " AND bereich_id=?"; p.append(bereich_id)
        rows = self.db.get_conn().execute(q + " ORDER BY created_at DESC", p).fetchall()
        vorhanden = self._vorhandene_token()
        return [self._public(r, vorhanden) for r in rows]

    def anlegen(self, user_id: str, body: KonnektorIn) -> dict[str, Any]:
        if body.typ not in _TYP_INDEX:
            raise ValueError(f"Unbekannter Konnektor-Typ: {body.typ!r}.")
        kid = new_id(); ts = now_iso()
        self.db.get_conn().execute(
            "INSERT INTO konnektoren (id,user_id,typ,name,bereich_id,extern_ref,aktiv,config,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,0,?,?,?)",
            (kid, user_id, body.typ, (body.name or "").strip(), (body.bereich_id or "").strip(),
             (body.extern_ref or "").strip(),
             json.dumps(body.config or {}, ensure_ascii=False), ts, ts))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "konnektor_angelegt", {"id": kid, "typ": body.typ})
        return {"ok": True, "id": kid}

    def aendern(self, user_id: str, kid: str, body: KonnektorPatch) -> bool:
        conn = self.db.get_conn()
        if conn.execute("SELECT 1 FROM konnektoren WHERE id=? AND user_id=? AND deleted_at IS NULL",
                        (kid, user_id)).fetchone() is None:
            return False
        felder, werte = [], []
        if body.name is not None:
            felder.append("name=?"); werte.append(body.name.strip())
        if body.bereich_id is not None:
            felder.append("bereich_id=?"); werte.append(body.bereich_id.strip())
        if body.extern_ref is not None:
            felder.append("extern_ref=?"); werte.append(body.extern_ref.strip())
        if body.aktiv is not None:
            felder.append("aktiv=?"); werte.append(int(bool(body.aktiv)))
        if body.config is not None:
            felder.append("config=?"); werte.append(json.dumps(body.config, ensure_ascii=False))
        if felder:
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [kid, user_id]
            conn.execute(f"UPDATE konnektoren SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            self.db.audit(user_id, "user", "konnektor_geaendert", {"id": kid})
        return True

    def loeschen(self, user_id: str, kid: str) -> bool:
        conn = self.db.get_conn()
        cur = conn.execute("UPDATE konnektoren SET deleted_at=?, updated_at=? "
                           "WHERE id=? AND user_id=? AND deleted_at IS NULL",
                           (now_iso(), now_iso(), kid, user_id))
        conn.commit()
        if cur.rowcount:
            self.db.audit(user_id, "user", "konnektor_geloescht", {"id": kid})
        return cur.rowcount > 0

    def zaehler(self, user_id: str) -> dict[str, int]:
        rows = self.liste(user_id)
        return {"gesamt": len(rows), "verbunden": sum(1 for r in rows if r["verbunden"]),
                "aktiv": sum(1 for r in rows if r["aktiv"])}

    # --- Router -------------------------------------------------------------
    def build_router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/api/konnektoren/typen")
        def konnektor_typen(user: UserContext = Depends(current_user)):
            """Andockbare externe Tools (Typen-Register) + je Typ Token-Status."""
            return {"typen": self.typen(), "arten": list(KONNEKTOR_ART)}

        @r.get("/api/konnektoren")
        def konnektoren_liste(bereich_id: str | None = None,
                              user: UserContext = Depends(current_user)):
            """Externe-Tool-Konnektoren im Überblick (read-only Sichtbarkeit, docs/35 §3).
            Ohne ``bereich_id`` = alle; ``''`` = nur globale; ``id`` = die eines Bereichs."""
            return {"konnektoren": self.liste(user.user_id, bereich_id=bereich_id),
                    "typen": self.typen(), "zaehler": self.zaehler(user.user_id)}

        @r.post("/api/konnektoren")
        def konnektor_anlegen(body: KonnektorIn, user: UserContext = Depends(current_user)):
            """Einen externen Konnektor (dormant) anlegen — optional an einen Bereich
            gebunden. Bleibt inaktiv, bis Token im Tresor + Freigabe (Gesetz 5)."""
            try:
                return self.anlegen(user.user_id, body)
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)

        @r.patch("/api/konnektoren/{kid}")
        def konnektor_aendern(kid: str, body: KonnektorPatch,
                              user: UserContext = Depends(current_user)):
            if not self.aendern(user.user_id, kid, body):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return {"ok": True, "id": kid}

        @r.delete("/api/konnektoren/{kid}")
        def konnektor_loeschen(kid: str, user: UserContext = Depends(current_user)):
            if not self.loeschen(user.user_id, kid):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return {"ok": True, "id": kid}

        return r


def build_konnektoren(db: Database, vault=None) -> Konnektoren:
    return Konnektoren(db, vault=vault)
