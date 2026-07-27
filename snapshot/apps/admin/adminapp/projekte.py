"""Projekte-Modul von Dizz Admin — Projekte · Aufgaben · Termine (aus Dizz Plans
portiert, docs/28 §13). Eigenes Geschwister-Modul neben ``domain.py`` (Geschäft+
Studium) und ``tresor.py``; namespaced (``ProjekteDomain``/``SCHEMA_PROJEKTE``/
``build_projekte``). Die App-weiten Endpunkte ``/api/stats`` + ``/api/netzwerk``
liefert die Geschäfts-Domäne bzw. der Aggregator (main.py) — hier entfernt.

Hier sitzt die App-eigene Substanz; alles Vertragliche (Health/Summary/Settings/
Account/Datenrechte/Defense/Mini-Dizzi) liefert appkit über ``create_app``.

Datenmodell folgt zwingend den Vertrags-Konventionen (UUID/user_id/Timestamps/
Soft-Delete, appkit/db.py): so greifen DSGVO-Export, Lösch-Kaskade und Retention
ohne Per-App-Code.

── Vorbereitete Anschlüsse (Gesetz 5 · docs/RECHERCHE §3) ─────────────────────
Bewusst als dokumentierte Slots angelegt, auch wenn v1 sie noch nicht voll nutzt:
- ``termine.quelle``/``extern_id``/``etag`` = SYNC-READY-Felder: Herkunft einer
  Quelle, stabiler Fremd-Schlüssel (Dedupe) und Versionsmarke (ETags/Last-
  Modified) für den späteren Zwei-Wege-Sync. v1 füllt sie beim iCal-Import.
- ``projekte.app_id`` = Kopplung eines Projekts an eine Netzwerk-App (Vision:
  „welche App = welches Projekt"); ``NETZWERK_APPS`` ist der Registry-Katalog,
  ``GET /api/netzwerk`` liefert ihn. Live-Status-Abfrage je App = späterer Slot.
- ``aufgaben.abhaengig_von`` (JSON-Liste) + ``meilenstein`` = Keim für Roadmap/
  Abhängigkeitsgraph. Kalender-Quellen kommen über ``sources.CalendarSource``
  herein (iCal echt; Google vorbereitet).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from appkit.actions import ActionRegistry
from appkit.auth import DEFAULT_USER_ID, UserContext, current_user
from appkit.db import Database, new_id, now_iso
from appkit.summary import Kpi

from . import recurrence
from .sources import SOURCE_SLOTS, ICalImport

# --- Domänen-Vokabular (UI + Validierung teilen sich diese Listen) -----------
PROJEKT_STATUS = ("aktiv", "pausiert", "abgeschlossen", "archiviert")
AUFGABE_STATUS = ("offen", "in-bearbeitung", "erledigt")
PRIORITAETEN = ("hoch", "mittel", "niedrig")
FARBEN = ("cyan", "magenta", "gruen", "amber", "violett")

# Registry-Katalog der Netzwerk-Apps (Vision: „welche App = welches Projekt").
# Stabiler, dokumentierter Slot — die Live-Status-Abfrage je App folgt (Core-Hub).
NETZWERK_APPS: tuple[dict[str, str], ...] = (
    {"id": "core", "brand": "the world of dizzi"},
    {"id": "tradingbot", "brand": "Dizz Trading"},
    {"id": "finanzen", "brand": "Dizz Money"},
    {"id": "creator", "brand": "Dizz Creating"},
    {"id": "kommunikation", "brand": "Dizz Communication"},
    {"id": "news", "brand": "Dizz News"},
    {"id": "memory", "brand": "Dizz Memory"},
    {"id": "admin", "brand": "Dizz Admin"},
    {"id": "health", "brand": "Dizz Healthy"},
    {"id": "social-media", "brand": "Dizz Management"},
    # plans + leading sind in Dizz Admin verschmolzen (docs/28) ⇒ keine eigenen App-Kopplungen mehr.
)
_APP_IDS = frozenset(a["id"] for a in NETZWERK_APPS)

# Domänen-Schema — in main.py an die Database (extra_schema) angehängt.
SCHEMA_PROJEKTE = """
CREATE TABLE IF NOT EXISTS projekte (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    name         TEXT NOT NULL,
    beschreibung TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'aktiv',   -- aktiv|pausiert|abgeschlossen|archiviert
    farbe        TEXT NOT NULL DEFAULT 'cyan',
    app_id       TEXT NOT NULL DEFAULT '',        -- Kopplung an Netzwerk-App (Vision)
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_projekte ON projekte (user_id, status, created_at);
CREATE TABLE IF NOT EXISTS aufgaben (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    projekt_id    TEXT NOT NULL DEFAULT '',       -- '' = Eingang (ohne Projekt)
    titel         TEXT NOT NULL,
    notiz         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'offen',  -- offen|in-bearbeitung|erledigt
    prioritaet    TEXT NOT NULL DEFAULT 'mittel', -- hoch|mittel|niedrig
    faellig       TEXT NOT NULL DEFAULT '',       -- ISO-Date oder leer
    meilenstein   INTEGER NOT NULL DEFAULT 0,     -- 0/1 (Roadmap-Keim)
    abhaengig_von TEXT NOT NULL DEFAULT '[]',     -- JSON-Liste Aufgaben-IDs (Abhängigkeiten)
    rrule         TEXT NOT NULL DEFAULT '',       -- RRULE-light (wiederkehrende Aufgabe; Bestands-DBs via Migration)
    quelle_ref    TEXT NOT NULL DEFAULT '',       -- Herkunfts-Referenz (A5 Frist→Aufgabe: admin:<art>:<id>; Idempotenz)
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_aufgaben ON aufgaben (user_id, projekt_id, status, faellig);
CREATE TABLE IF NOT EXISTS termine (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    projekt_id   TEXT NOT NULL DEFAULT '',
    titel        TEXT NOT NULL,
    beginn       TEXT NOT NULL,                   -- ISO-8601 (Date oder DateTime)
    ende         TEXT NOT NULL DEFAULT '',
    ganztags     INTEGER NOT NULL DEFAULT 0,
    ort          TEXT NOT NULL DEFAULT '',
    notiz        TEXT NOT NULL DEFAULT '',
    rrule        TEXT NOT NULL DEFAULT '',        -- roh (RFC 5545); Expansion = Slot
    quelle       TEXT NOT NULL DEFAULT 'lokal',   -- lokal|google|ical|caldav (Sync-Herkunft)
    extern_id    TEXT NOT NULL DEFAULT '',        -- Fremd-UID (Dedupe + Zwei-Wege-Sync)
    etag         TEXT NOT NULL DEFAULT '',        -- Last-Modified/ETag (Konfliktauflösung, Slot)
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_termine ON termine (user_id, beginn);
CREATE INDEX IF NOT EXISTS idx_termine_extern ON termine (user_id, quelle, extern_id);
"""


# --- Request-Modelle: MODUL-Ebene zwingend (PEP-563-Falle, s. refapp/README) -
class ProjektIn(BaseModel):
    name: str
    beschreibung: str = ""
    status: str = "aktiv"
    farbe: str = "cyan"
    app_id: str = ""


class ProjektPatch(BaseModel):
    name: str | None = None
    beschreibung: str | None = None
    status: str | None = None
    farbe: str | None = None
    app_id: str | None = None


class AufgabeIn(BaseModel):
    titel: str
    projekt_id: str = ""
    notiz: str = ""
    status: str = "offen"
    prioritaet: str = "mittel"
    faellig: str = ""
    meilenstein: bool = False
    abhaengig_von: list[str] = []
    rrule: str = ""             # RRULE-light (wiederkehrend); leer = einmalig


class AufgabePatch(BaseModel):
    titel: str | None = None
    projekt_id: str | None = None
    notiz: str | None = None
    status: str | None = None
    prioritaet: str | None = None
    faellig: str | None = None
    meilenstein: bool | None = None
    abhaengig_von: list[str] | None = None
    rrule: str | None = None


class TerminIn(BaseModel):
    titel: str
    beginn: str
    ende: str = ""
    projekt_id: str = ""
    ganztags: bool = False
    ort: str = ""
    notiz: str = ""
    rrule: str = ""             # RRULE-light (wiederkehrend); leer = einmalig


class TerminPatch(BaseModel):
    titel: str | None = None
    beginn: str | None = None
    ende: str | None = None
    projekt_id: str | None = None
    ganztags: bool | None = None
    ort: str | None = None
    notiz: str | None = None
    rrule: str | None = None


class ICalIn(BaseModel):
    ics: str
    projekt_id: str = ""


class ProjektNotizIn(BaseModel):
    """Projekt-Notiz-Strom (V6): eine freie Notiz zu einem Projekt wird ins
    zentrale Archiv (Dizz Memory) publiziert — Memory IST der Speicher dieses
    Stroms (Rück-Lese über /api/wissen/suche). Kein lokaler Notiz-Tisch nötig."""
    text: str


class KalenderEmpfangIn(BaseModel):
    """Querverbindungs-Empfang Kalender (V5 docs/26): eine andere App (z. B.
    Communication aus einer Mail-Einladung) trägt ein Event in den Plans-Kalender
    ein. Zweiter Vertragstyp neben dem Memory-Archiv-Umschlag."""
    titel: str = ""
    beginn: str = ""            # ISO-8601 (Pflicht)
    ende: str = ""
    ganztags: bool = False
    ort: str = ""
    beschreibung: str = ""      # → Termin-Notiz
    app: str = ""               # absendende App-id → ``quelle`` (Idempotenz-Namensraum)
    quelle: str = ""            # Referenz/URL beim Absender → in die Notiz
    ref: str | None = None      # Idempotenz-Schlüssel → ``extern_id``


def heute_iso() -> str:
    return date.today().isoformat()


def _in(wert: str, erlaubt: tuple[str, ...], default: str) -> str:
    return wert if wert in erlaubt else default


class ProjekteDomain:
    """Bündelt Router + Kennzahl-Funktionen der Plans-Domäne. main.py reicht
    ``summary``/``stats`` an den Vertrag bzw. den MCP-Server, ``ki_kontext`` an
    den App-KI-Slot (Mini-Dizzi)."""

    def __init__(self, db: Database, archiv_post=None, memory_get=None,
                 kalender_post=None) -> None:
        self.db = db
        self.archiv_post = archiv_post   # Injektion für den Querverbindungs-POST (Tests/Relay)
        self.memory_get = memory_get     # Injektion für die RÜCK-LESE (memory_suche; Tests/Relay)
        self.kalender_post = kalender_post  # Injektion für den Termin-Sende-POST (V5-Rücksync; Tests/Relay)
        self._migriere()
        self.actions = self._build_actions()   # K4: HITL-Aktionen (propose→approve→execute)
        self.router = self._build_router()

    # --- Create-Helfer: EINE Quelle für POST-Routen UND K4-Aktions-Handler ----
    # Validierung wirft ValueError (Routen → HTTP 400; Aktions-Handler → 'failed').
    def neues_projekt(self, user_id: str, *, name: str, beschreibung: str = "",
                      status: str = "aktiv", farbe: str = "cyan", app_id: str = "") -> str:
        name = (name or "").strip()
        if not name:
            raise ValueError("Name ist Pflicht.")
        if app_id and app_id not in _APP_IDS:
            raise ValueError(f"Unbekannte App-Kopplung: {app_id!r}.")
        ts = now_iso(); pid = new_id(); conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO projekte (id, user_id, name, beschreibung, status, farbe, "
            "app_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, user_id, name, (beschreibung or "").strip(),
             _in(status, PROJEKT_STATUS, "aktiv"), _in(farbe, FARBEN, "cyan"), app_id, ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "projekt_angelegt", {"app_id": app_id})
        return pid

    def neue_aufgabe(self, user_id: str, *, titel: str, projekt_id: str = "", notiz: str = "",
                     status: str = "offen", prioritaet: str = "mittel", faellig: str = "",
                     meilenstein: bool = False, abhaengig_von=None, rrule: str = "",
                     quelle_ref: str = "") -> str:
        titel = (titel or "").strip()
        if not titel:
            raise ValueError("Titel ist Pflicht.")
        if projekt_id and conn_proj_fehlt(self.db, user_id, projekt_id):
            raise ValueError("Projekt unbekannt.")
        rrule = (rrule or "").strip()
        if not recurrence.ist_gueltig(rrule):
            raise ValueError("Ungültige Wiederholungsregel (FREQ=DAILY|WEEKLY|MONTHLY).")
        ts = now_iso(); aid = new_id()
        dep = json.dumps([str(x) for x in (abhaengig_von or [])], ensure_ascii=False)
        conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO aufgaben (id, user_id, projekt_id, titel, notiz, status, "
            "prioritaet, faellig, meilenstein, abhaengig_von, rrule, quelle_ref, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, user_id, projekt_id, titel, (notiz or "").strip(),
             _in(status, AUFGABE_STATUS, "offen"), _in(prioritaet, PRIORITAETEN, "mittel"),
             (faellig or "").strip(), int(bool(meilenstein)), dep, rrule,
             (quelle_ref or "").strip(), ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "aufgabe_angelegt",
                      {"projekt_id": projekt_id, "prioritaet": prioritaet, "wiederkehrend": bool(rrule)})
        return aid

    def neuer_termin(self, user_id: str, *, titel: str, beginn: str, ende: str = "",
                     projekt_id: str = "", ganztags: bool = False, ort: str = "",
                     notiz: str = "", rrule: str = "") -> str:
        titel = (titel or "").strip(); beginn = (beginn or "").strip()
        if not titel:
            raise ValueError("Titel ist Pflicht.")
        if not beginn:
            raise ValueError("Beginn ist Pflicht.")
        if projekt_id and conn_proj_fehlt(self.db, user_id, projekt_id):
            raise ValueError("Projekt unbekannt.")
        rrule = (rrule or "").strip()
        if not recurrence.ist_gueltig(rrule):
            raise ValueError("Ungültige Wiederholungsregel (FREQ=DAILY|WEEKLY|MONTHLY).")
        ts = now_iso(); tid = new_id(); conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO termine (id, user_id, projekt_id, titel, beginn, ende, ganztags, "
            "ort, notiz, rrule, quelle, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,'lokal',?,?)",
            (tid, user_id, projekt_id, titel, beginn, (ende or "").strip(),
             int(bool(ganztags)), (ort or "").strip(), (notiz or "").strip(), rrule, ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "termin_angelegt",
                      {"projekt_id": projekt_id, "wiederkehrend": bool(rrule)})
        return tid

    def _build_actions(self) -> ActionRegistry:
        """K4 (APP_GRUNDLAGEN §A1): die Projekt-KI/MCP darf Anlegen NUR VORSCHLAGEN
        (`propose`), Wirkung erst nach Nutzer-Freigabe (`approve`). Stufe `lokal` =
        die Freigabe genügt im Standalone-Betrieb (Anlegen ist lokal/harmlos);
        die HITL-Schwelle ist der bewusste Approve-Klick. Handler = die Create-Helfer."""
        reg = ActionRegistry()
        uid = DEFAULT_USER_ID
        reg.register("aufgabe_anlegen", lambda p: {"id": self.neue_aufgabe(
            uid, titel=p.get("titel", ""), projekt_id=p.get("projekt_id", ""),
            notiz=p.get("notiz", ""), prioritaet=p.get("prioritaet", "mittel"),
            faellig=p.get("faellig", ""), meilenstein=bool(p.get("meilenstein", False)),
            rrule=p.get("rrule", ""))}, level="lokal",
            beschreibung="Neue Aufgabe anlegen (KI-Vorschlag, erst nach Freigabe).")
        reg.register("termin_anlegen", lambda p: {"id": self.neuer_termin(
            uid, titel=p.get("titel", ""), beginn=p.get("beginn", ""), ende=p.get("ende", ""),
            projekt_id=p.get("projekt_id", ""), ort=p.get("ort", ""), notiz=p.get("notiz", ""),
            rrule=p.get("rrule", ""))}, level="lokal",
            beschreibung="Neuen Termin anlegen (KI-Vorschlag, erst nach Freigabe).")
        reg.register("projekt_anlegen", lambda p: {"id": self.neues_projekt(
            uid, name=p.get("name", ""), beschreibung=p.get("beschreibung", ""),
            app_id=p.get("app_id", ""))}, level="lokal",
            beschreibung="Neues Projekt anlegen (KI-Vorschlag, erst nach Freigabe).")
        return reg

    def memory_suche(self, q: str, semantisch: bool = False,
                     limit: int = 8) -> dict[str, Any]:
        """RÜCK-LESE (V5–V11 „↔", docs/26 §10.1): fragt das zentrale Archiv
        (Dizz Memory) über den Core-Relay nach Projekt-Wissen. Best-effort —
        ``appkit.querverbindung.memory_suche`` wirft nie (Core down ⇒ leere
        Treffer). So kann die Plans-KI ergänzendes Wissen heranziehen."""
        from appkit.querverbindung import memory_suche as _suche
        return _suche((q or "").strip(), semantisch=semantisch,
                      limit=min(max(limit, 1), 25), http_get=self.memory_get)

    def _migriere(self) -> None:
        """Idempotente Mini-Migration für BESTANDS-DBs: ``aufgaben.rrule`` ergänzen
        (frische DBs tragen es schon via SCHEMA). ``CREATE TABLE IF NOT EXISTS``
        fügt neue Spalten nicht nach — daher hier ein gezieltes ALTER, das nur
        läuft, wenn die Spalte fehlt (kein Schaden bei Wiederholung)."""
        conn = self.db.get_conn()
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(aufgaben)")}
        if "rrule" not in cols:
            conn.execute("ALTER TABLE aufgaben ADD COLUMN rrule TEXT NOT NULL DEFAULT ''")
        if "quelle_ref" not in cols:    # A5: Herkunfts-Referenz (Frist→Aufgabe, Idempotenz)
            conn.execute("ALTER TABLE aufgaben ADD COLUMN quelle_ref TEXT NOT NULL DEFAULT ''")
        conn.commit()

    # --- Kennzahlen (Kachel + /api/stats + MCP plans_kachel_stats) ----------
    def stats(self, user_id: str) -> dict[str, int]:
        conn = self.db.get_conn()
        heute = heute_iso()
        n_proj = conn.execute(
            "SELECT COUNT(*) AS n FROM projekte WHERE user_id=? AND deleted_at IS NULL "
            "AND status='aktiv'", (user_id,)).fetchone()["n"]
        n_offen = conn.execute(
            "SELECT COUNT(*) AS n FROM aufgaben WHERE user_id=? AND deleted_at IS NULL "
            "AND status!='erledigt'", (user_id,)).fetchone()["n"]
        n_heute = conn.execute(
            "SELECT COUNT(*) AS n FROM aufgaben WHERE user_id=? AND deleted_at IS NULL "
            "AND status!='erledigt' AND faellig=?", (user_id, heute)).fetchone()["n"]
        n_termine = conn.execute(
            "SELECT COUNT(*) AS n FROM termine WHERE user_id=? AND deleted_at IS NULL "
            "AND substr(beginn,1,10)=?", (user_id, heute)).fetchone()["n"]
        return {"projekte_aktiv": n_proj, "aufgaben_offen": n_offen,
                "aufgaben_heute_faellig": n_heute, "termine_heute": n_termine}

    def summary(self, user_id: str = "dizzi") -> list[Kpi]:
        s = self.stats(user_id)
        return [
            Kpi(id="projekte", label="Projekte aktiv", value=s["projekte_aktiv"]),
            Kpi(id="aufgaben_offen", label="Aufgaben offen", value=s["aufgaben_offen"]),
            Kpi(id="heute_faellig", label="Heute fällig", value=s["aufgaben_heute_faellig"]),
            Kpi(id="termine_heute", label="Termine heute", value=s["termine_heute"]),
        ]

    def ki_kontext(self, user_id: str) -> dict[str, Any]:
        """Kontext für die App-KI: aktive Projekte (mit Fortschritt), die obersten
        offenen Aufgaben und die nächsten Termine — Mini-Dizzi erfindet nichts dazu."""
        conn = self.db.get_conn()
        proj = [self._projekt_public(conn, user_id, r) for r in conn.execute(
            "SELECT * FROM projekte WHERE user_id=? AND deleted_at IS NULL "
            "AND status='aktiv' ORDER BY created_at DESC LIMIT 12", (user_id,)).fetchall()]
        auf = [{"titel": r["titel"], "faellig": r["faellig"], "status": r["status"],
                "prioritaet": r["prioritaet"]}
               for r in conn.execute(
                   "SELECT titel, faellig, status, prioritaet FROM aufgaben "
                   "WHERE user_id=? AND deleted_at IS NULL AND status!='erledigt' "
                   "ORDER BY (faellig='') ASC, faellig ASC, created_at DESC LIMIT 20",
                   (user_id,)).fetchall()]
        term = [{"titel": r["titel"], "beginn": r["beginn"], "ort": r["ort"]}
                for r in conn.execute(
                    "SELECT titel, beginn, ort FROM termine WHERE user_id=? "
                    "AND deleted_at IS NULL AND substr(beginn,1,10)>=? "
                    "ORDER BY beginn ASC LIMIT 12", (user_id, heute_iso())).fetchall()]
        return {"projekte": proj, "aufgaben": auf, "termine": term}

    def erinnerungen(self, user_id: str, vorlauf: int | None = None) -> dict[str, Any]:
        """Frist-/Termin-Wächter (APP_GRUNDLAGEN §A1 — beobachten + melden, nie
        eingreifen): deterministischer Feed dessen, was Aufmerksamkeit braucht —
        überfällige + heute fällige + demnächst fällige Aufgaben (im Vorlauf-Fenster)
        + anstehende Termine. ``vorlauf`` Tage = Setting ``erinnerung_vorlauf_tage``
        (Default 2). Read-only; der Push an Dizzi-Meldungen ist der Aktivierungs-Slot."""
        conn = self.db.get_conn()
        h = heute_iso()
        if vorlauf is None:
            try:
                vorlauf = int(self.db.setting_get(user_id, "erinnerung_vorlauf_tage", 2) or 2)
            except (TypeError, ValueError):
                vorlauf = 2
        vorlauf = max(0, vorlauf)
        bis = (date.today() + timedelta(days=vorlauf)).isoformat()

        def _auf(where: str, params: list) -> list[dict[str, Any]]:
            rows = conn.execute(
                "SELECT id, titel, faellig, prioritaet, projekt_id FROM aufgaben "
                "WHERE user_id=? AND deleted_at IS NULL AND status!='erledigt' AND faellig!='' "
                + where + " ORDER BY faellig ASC, created_at DESC LIMIT 100",
                [user_id] + params).fetchall()
            return [{"id": r["id"], "titel": r["titel"], "faellig": r["faellig"],
                     "prioritaet": r["prioritaet"], "projekt_id": r["projekt_id"]} for r in rows]

        ueberfaellig = _auf("AND faellig<?", [h])
        heute_faellig = _auf("AND faellig=?", [h])
        bald = _auf("AND faellig>? AND faellig<=?", [h, bis]) if vorlauf > 0 else []
        term = [{"id": r["id"], "titel": r["titel"], "beginn": r["beginn"], "ort": r["ort"]}
                for r in conn.execute(
                    "SELECT id, titel, beginn, ort FROM termine WHERE user_id=? AND deleted_at IS NULL "
                    "AND substr(beginn,1,10)>=? AND substr(beginn,1,10)<=? ORDER BY beginn ASC LIMIT 100",
                    (user_id, h, bis)).fetchall()]
        return {"vorlauf_tage": vorlauf, "ueberfaellig": ueberfaellig,
                "heute": heute_faellig, "bald": bald, "termine": term,
                "anzahl": len(ueberfaellig) + len(heute_faellig) + len(bald) + len(term)}

    # --- Serializer ---------------------------------------------------------
    def _projekt_fortschritt(self, conn, user_id: str, pid: str) -> dict[str, int]:
        row = conn.execute(
            "SELECT COUNT(*) AS gesamt, "
            "SUM(CASE WHEN status='erledigt' THEN 1 ELSE 0 END) AS fertig "
            "FROM aufgaben WHERE user_id=? AND projekt_id=? AND deleted_at IS NULL",
            (user_id, pid)).fetchone()
        gesamt = row["gesamt"] or 0
        fertig = row["fertig"] or 0
        prozent = round(100 * fertig / gesamt) if gesamt else 0
        return {"aufgaben_gesamt": gesamt, "aufgaben_fertig": fertig,
                "fortschritt": prozent}

    def _projekt_public(self, conn, user_id: str, r) -> dict[str, Any]:
        d = {"id": r["id"], "name": r["name"], "beschreibung": r["beschreibung"],
             "status": r["status"], "farbe": r["farbe"], "app_id": r["app_id"],
             "bereich_id": (r["bereich_id"] if "bereich_id" in r.keys() else ""),
             "created_at": r["created_at"], "updated_at": r["updated_at"]}
        d.update(self._projekt_fortschritt(conn, user_id, r["id"]))
        return d

    def _archiviere_projekt(self, user_id: str, pid: str,
                            explizit: bool = False) -> dict[str, Any]:
        """Reicht ein Projekt (Metadaten + Fortschritt + Aufgaben-Überblick) als
        Notiz an Dizz Memory weiter (Core-Relay, V6 docs/26). Die Archiv-Regel
        je (plans, projekt) gated; ``explizit`` (Nutzer-Knopf) schlägt jede Regel.
        Best-effort — ``archiviere`` wirft nie. Das Herkunftslabel „Plans" vergibt
        Memory zentral (docs/26 §9.1) ⇒ wir senden keine Tags."""
        from appkit.querverbindung import archiviere
        conn = self.db.get_conn()
        row = conn.execute(
            "SELECT * FROM projekte WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (pid, user_id)).fetchone()
        if row is None:
            return {"ok": False, "fehler": "Projekt unbekannt"}
        fort = self._projekt_fortschritt(conn, user_id, pid)
        aufgaben = conn.execute(
            "SELECT titel, status, prioritaet, faellig, meilenstein FROM aufgaben "
            "WHERE user_id=? AND projekt_id=? AND deleted_at IS NULL "
            "ORDER BY (faellig='') ASC, faellig ASC, created_at DESC",
            (user_id, pid)).fetchall()
        zeilen = [f"**Status:** {row['status']} · **Fortschritt:** {fort['fortschritt']} % "
                  f"({fort['aufgaben_fertig']}/{fort['aufgaben_gesamt']} Aufgaben)"]
        if row["app_id"]:
            zeilen.append(f"**Gekoppelte App:** {row['app_id']}")
        if (row["beschreibung"] or "").strip():
            zeilen += ["", row["beschreibung"].strip()]
        if aufgaben:
            zeilen += ["", "## Aufgaben"]
            for a in aufgaben:
                haken = "x" if a["status"] == "erledigt" else " "
                stern = "🏁 " if a["meilenstein"] else ""
                frist = f" (fällig {a['faellig']})" if a["faellig"] else ""
                zeilen.append(f"- [{haken}] {stern}{a['titel']} · {a['prioritaet']}{frist}")
        inhalt = "\n".join(zeilen).strip() or "(leeres Projekt)"
        return archiviere("admin", "Projekt · " + row["name"], inhalt,
                          strom="projekt", ref="admin:projekt:" + pid,
                          quelle="admin:projekt:" + pid, explizit=explizit,
                          http_post=self.archiv_post)

    def _archiviere_meilenstein(self, user_id: str, aid: str,
                                explizit: bool = True) -> dict[str, Any]:
        """Meilenstein-Strom (V6 docs/26, zusätzlich zum projekt-Strom): reicht
        EINEN (Meilenstein-)Aufgabenpunkt als eigene Notiz an Dizz Memory weiter
        — ``strom="meilenstein"``. Best-effort; Herkunftslabel vergibt Memory."""
        from appkit.querverbindung import archiviere
        conn = self.db.get_conn()
        row = conn.execute(
            "SELECT * FROM aufgaben WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (aid, user_id)).fetchone()
        if row is None:
            return {"ok": False, "fehler": "Aufgabe unbekannt"}
        projekt = conn.execute(
            "SELECT name FROM projekte WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (row["projekt_id"], user_id)).fetchone() if row["projekt_id"] else None
        haken = "x" if row["status"] == "erledigt" else " "
        stern = "🏁 " if row["meilenstein"] else ""
        zeilen = [f"**Status:** {row['status']} · **Priorität:** {row['prioritaet']}"]
        if row["faellig"]:
            zeilen.append(f"**Fällig:** {row['faellig']}")
        if projekt is not None:
            zeilen.append(f"**Projekt:** {projekt['name']}")
        if (row["notiz"] or "").strip():
            zeilen += ["", row["notiz"].strip()]
        zeilen += ["", f"- [{haken}] {stern}{row['titel']}"]
        return archiviere("admin", "Meilenstein · " + row["titel"], "\n".join(zeilen),
                          strom="meilenstein", ref="admin:meilenstein:" + aid,
                          quelle="admin:meilenstein:" + aid, explizit=explizit,
                          http_post=self.archiv_post)

    def _sende_termin_an_komm(self, user_id: str, tid: str) -> dict[str, Any]:
        """V5-RÜCKSYNC (docs/26 §4b): reicht einen Plans-Termin als read-only
        Erinnerung an Dizz Communication weiter — Plans → Core-Relay → Communications
        Kalender-Empfänger (``ziel="kommunikation"``). **Idempotent** per
        ``ref=plans:termin:<id>``. Best-effort — ``sende_termin`` wirft nie. Nur Daten,
        kein Aktions-Auslöser. Gegenrichtung zu V5 (Communication → Plans)."""
        from appkit.querverbindung import sende_termin
        conn = self.db.get_conn()
        row = conn.execute(
            "SELECT * FROM termine WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (tid, user_id)).fetchone()
        if row is None:
            return {"ok": False, "fehler": "Termin unbekannt"}
        return sende_termin(
            "admin", row["titel"], row["beginn"], ende=(row["ende"] or ""),
            ganztags=bool(row["ganztags"]), ort=(row["ort"] or ""),
            beschreibung=(row["notiz"] or ""), quelle="admin:termin:" + tid,
            ref="admin:termin:" + tid, ziel="kommunikation",
            http_post=self.kalender_post)

    def _publiziere_projekt_notiz(self, user_id: str, pid: str,
                                  text: str) -> dict[str, Any]:
        """Projekt-Notiz-Strom (V6): publiziert eine freie Notiz zu einem Projekt
        ins zentrale Archiv (``strom="projekt_notiz"``). Jede Notiz ist distinkt
        (ref mit UUID) — Memory ist der Speicher; Rück-Lese via /api/wissen/suche."""
        from appkit.querverbindung import archiviere
        conn = self.db.get_conn()
        row = conn.execute(
            "SELECT name FROM projekte WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (pid, user_id)).fetchone()
        if row is None:
            return {"ok": False, "fehler": "Projekt unbekannt"}
        notiz_id = new_id()
        return archiviere("admin", "Notiz · " + row["name"], text.strip(),
                          strom="projekt_notiz",
                          ref=f"admin:projekt_notiz:{pid}:{notiz_id}",
                          quelle="admin:projekt:" + pid, explizit=True,
                          http_post=self.archiv_post)

    def _spawn_folgeaufgabe(self, conn, user_id: str, alt, body) -> dict[str, Any] | None:
        """Wiederkehrende Aufgabe: legt die NÄCHSTE Instanz an, wenn dieser PATCH
        die Aufgabe ERSTMALS auf 'erledigt' setzt und sie eine Regel + Frist trägt.
        Deterministisch (recurrence.naechste_faellig); nie ein Endlos-Lauf — die
        erledigte Aufgabe spawnt nicht erneut (Übergangs-Bedingung), die neue
        Instanz ist 'offen'. ``None`` wenn nichts zu tun ist."""
        neuer_status = _in(body.status, AUFGABE_STATUS, "offen") if body.status is not None \
            else alt["status"]
        if alt["status"] == "erledigt" or neuer_status != "erledigt":
            return None
        alt_rrule = alt["rrule"] if "rrule" in alt.keys() else ""
        rrule = (body.rrule if body.rrule is not None else alt_rrule) or ""
        faellig = (body.faellig if body.faellig is not None else alt["faellig"]) or ""
        naechste = recurrence.naechste_faellig(rrule.strip(), faellig.strip())
        if not naechste:
            return None
        # Aktuelle (ggf. im selben PATCH geänderte) Werte aus der Zeile übernehmen.
        akt = conn.execute("SELECT * FROM aufgaben WHERE id=? AND user_id=?",
                           (alt["id"], user_id)).fetchone()
        ts = now_iso()
        nid = new_id()
        conn.execute(
            "INSERT INTO aufgaben (id, user_id, projekt_id, titel, notiz, status, "
            "prioritaet, faellig, meilenstein, abhaengig_von, rrule, created_at, updated_at) "
            "VALUES (?,?,?,?,?,'offen',?,?,?,?,?,?,?)",
            (nid, user_id, akt["projekt_id"], akt["titel"], akt["notiz"],
             akt["prioritaet"], naechste, akt["meilenstein"], akt["abhaengig_von"],
             akt["rrule"], ts, ts))
        conn.commit()
        self.db.audit(user_id, "system", "aufgabe_wiederkehr",
                      {"von": alt["id"], "neu": nid, "faellig": naechste})
        return {"id": nid, "faellig": naechste}

    @staticmethod
    def _aufgabe_public(r) -> dict[str, Any]:
        return {"id": r["id"], "projekt_id": r["projekt_id"], "titel": r["titel"],
                "notiz": r["notiz"], "status": r["status"], "prioritaet": r["prioritaet"],
                "faellig": r["faellig"], "meilenstein": bool(r["meilenstein"]),
                "abhaengig_von": json.loads(r["abhaengig_von"] or "[]"),
                "rrule": (r["rrule"] if "rrule" in r.keys() else ""),
                "quelle_ref": (r["quelle_ref"] if "quelle_ref" in r.keys() else ""),
                "bereich_id": (r["bereich_id"] if "bereich_id" in r.keys() else ""),
                "created_at": r["created_at"]}

    @staticmethod
    def _termin_public(r) -> dict[str, Any]:
        return {"id": r["id"], "projekt_id": r["projekt_id"], "titel": r["titel"],
                "beginn": r["beginn"], "ende": r["ende"], "ganztags": bool(r["ganztags"]),
                "ort": r["ort"], "notiz": r["notiz"], "rrule": r["rrule"],
                "quelle": r["quelle"], "extern_id": r["extern_id"],
                "bereich_id": (r["bereich_id"] if "bereich_id" in r.keys() else ""),
                "created_at": r["created_at"]}

    # --- Router -------------------------------------------------------------
    def _build_router(self) -> APIRouter:
        r = APIRouter()
        db = self.db

        # ===================== RÜCK-LESE / WÄCHTER / QUELLEN ================
        # (/api/stats + /api/netzwerk entfallen im Merge: die App-weiten Endpunkte
        #  liefert die Geschäfts-Domäne bzw. der Aggregator in main.py, docs/28 §13.
        #  ``stats()``/``summary()`` bleiben als Methoden für die spätere Einfaltung
        #  in die gemeinsame /api/stats-Kachel, Phase 3.)
        @r.get("/api/wissen/suche")
        def wissen_suche(q: str = "", semantisch: str = "", limit: int = 8,
                         user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """RÜCK-LESE: fragt Dizz Memory nach Projekt-Wissen (Core-Relay,
            best-effort). ``semantisch=1`` ⇒ Bedeutungssuche (RAG), sonst Wortsuche.
            Leere Frage ⇒ keine Treffer (kein Leerlauf-Call)."""
            if not q.strip():
                return {"ok": True, "treffer": [], "anzahl": 0}
            return self.memory_suche(q, semantisch=(semantisch in ("1", "true")),
                                     limit=limit)

        @r.get("/api/erinnerungen")
        def erinnerungen_ep(vorlauf: int | None = None,
                            user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Frist-/Termin-Wächter-Feed (überfällig/heute/demnächst + Termine)."""
            return self.erinnerungen(user.user_id, vorlauf=vorlauf)

        @r.get("/api/quellen")
        def quellen_ep(request: Request,
                       user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Vorbereitete Datenquellen-Stecker sichtbar machen (Gesetz 5): iCal
            (aktiv) · Google/CalDAV (Kalender) · GitHub/GitLab (Aufgaben) — je mit
            ``verbunden`` (Token im Tresor vorhanden?). Read-only Übersicht."""
            try:
                vorhanden = set(getattr(request.app.state, "vault").names())
            except Exception:
                vorhanden = set()
            return {"quellen": [{**s, "verbunden": bool(s["token_name"]) and s["token_name"] in vorhanden}
                                for s in SOURCE_SLOTS]}

        # ===================== PROJEKTE =====================================
        @r.post("/api/projekte")
        def projekt_anlegen(body: ProjektIn,
                            user: UserContext = Depends(current_user)) -> dict[str, Any]:
            try:
                pid = self.neues_projekt(user.user_id, name=body.name,
                                         beschreibung=body.beschreibung, status=body.status,
                                         farbe=body.farbe, app_id=body.app_id)
            except ValueError as e:
                raise HTTPException(400, str(e))
            return {"ok": True, "id": pid}

        @r.get("/api/projekte")
        def projekt_liste(status: str = "", app_id: str = "", bereich_id: str | None = None,
                          user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            conn = db.get_conn()
            q = "SELECT * FROM projekte WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if status:
                q += " AND status=?"; params.append(status)
            if app_id:
                q += " AND app_id=?"; params.append(app_id)
            if bereich_id is not None:           # None=alle · ''=nur „Allgemein" · id=Bereich
                q += " AND bereich_id=?"; params.append(bereich_id)
            q += " ORDER BY (status='aktiv') DESC, created_at DESC"
            return [self._projekt_public(conn, user.user_id, row)
                    for row in conn.execute(q, params).fetchall()]

        @r.get("/api/projekte/{pid}")
        def projekt_detail(pid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            row = conn.execute(
                "SELECT * FROM projekte WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (pid, user.user_id)).fetchone()
            if row is None:
                return JSONResponse({"error": "Projekt unbekannt"}, status_code=404)
            auf = [self._aufgabe_public(a) for a in conn.execute(
                "SELECT * FROM aufgaben WHERE user_id=? AND projekt_id=? AND deleted_at IS NULL "
                "ORDER BY (faellig='') ASC, faellig ASC, created_at DESC",
                (user.user_id, pid)).fetchall()]
            term = [self._termin_public(t) for t in conn.execute(
                "SELECT * FROM termine WHERE user_id=? AND projekt_id=? AND deleted_at IS NULL "
                "ORDER BY beginn ASC", (user.user_id, pid)).fetchall()]
            return {"projekt": self._projekt_public(conn, user.user_id, row),
                    "aufgaben": auf, "termine": term}

        @r.post("/api/projekte/{pid}/archivieren")
        def projekt_archivieren_ep(pid: str,
                                   user: UserContext = Depends(current_user)):
            """„In Memory archivieren" (Nutzer-Zuruf): schickt das Projekt explizit
            an Dizz Memory — schlägt jede Archiv-Regel (V6, docs/26)."""
            conn = db.get_conn()
            if conn.execute("SELECT 1 FROM projekte WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (pid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Projekt unbekannt"}, status_code=404)
            ergebnis = self._archiviere_projekt(user.user_id, pid, explizit=True)
            db.audit(user.user_id, "user", "projekt_archiviert",
                     {"id": pid, "status": ergebnis.get("status")})
            return ergebnis

        @r.post("/api/projekte/{pid}/notiz")
        def projekt_notiz_ep(pid: str, body: ProjektNotizIn,
                             user: UserContext = Depends(current_user)):
            """Projekt-Notiz-Strom (V6): publiziert eine freie Notiz zum Projekt
            ins zentrale Archiv (Dizz Memory, Strom „projekt_notiz"). Rück-Lese
            später über /api/wissen/suche."""
            if not body.text.strip():
                raise HTTPException(400, "Notiz-Text ist Pflicht.")
            conn = db.get_conn()
            if conn.execute("SELECT 1 FROM projekte WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (pid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Projekt unbekannt"}, status_code=404)
            ergebnis = self._publiziere_projekt_notiz(user.user_id, pid, body.text)
            db.audit(user.user_id, "user", "projekt_notiz_publiziert",
                     {"id": pid, "status": ergebnis.get("status")})
            return ergebnis

        @r.patch("/api/projekte/{pid}")
        def projekt_patch(pid: str, body: ProjektPatch,
                          user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM projekte WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (pid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Projekt unbekannt"}, status_code=404)
            felder, werte = [], []
            if body.name is not None and body.name.strip():
                felder.append("name=?"); werte.append(body.name.strip())
            if body.beschreibung is not None:
                felder.append("beschreibung=?"); werte.append(body.beschreibung.strip())
            if body.status is not None:
                felder.append("status=?"); werte.append(_in(body.status, PROJEKT_STATUS, "aktiv"))
            if body.farbe is not None:
                felder.append("farbe=?"); werte.append(_in(body.farbe, FARBEN, "cyan"))
            if body.app_id is not None:
                if body.app_id and body.app_id not in _APP_IDS:
                    return JSONResponse({"error": f"Unbekannte App-Kopplung: {body.app_id!r}"},
                                        status_code=400)
                felder.append("app_id=?"); werte.append(body.app_id)
            if not felder:
                return {"ok": True, "id": pid}
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [pid, user.user_id]
            conn.execute(f"UPDATE projekte SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "projekt_geaendert", {"id": pid})
            return {"ok": True, "id": pid}

        @r.delete("/api/projekte/{pid}")
        def projekt_delete(pid: str, user: UserContext = Depends(current_user)):
            """Soft-Delete des Projekts MIT Kaskade auf seine Aufgaben/Termine
            (Listen bleiben sauber; Soft-Delete = Sync-/Wiederherstellungs-ready)."""
            conn = db.get_conn()
            if conn.execute("SELECT id FROM projekte WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (pid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Projekt unbekannt"}, status_code=404)
            ts = now_iso()
            conn.execute("UPDATE projekte SET deleted_at=? WHERE id=? AND user_id=?",
                         (ts, pid, user.user_id))
            conn.execute("UPDATE aufgaben SET deleted_at=? WHERE projekt_id=? AND user_id=? "
                         "AND deleted_at IS NULL", (ts, pid, user.user_id))
            conn.execute("UPDATE termine SET deleted_at=? WHERE projekt_id=? AND user_id=? "
                         "AND deleted_at IS NULL", (ts, pid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "projekt_geloescht", {"id": pid})
            return {"ok": True, "id": pid}

        # ===================== AUFGABEN =====================================
        @r.post("/api/aufgaben")
        def aufgabe_anlegen(body: AufgabeIn,
                            user: UserContext = Depends(current_user)) -> dict[str, Any]:
            try:
                aid = self.neue_aufgabe(user.user_id, titel=body.titel, projekt_id=body.projekt_id,
                                        notiz=body.notiz, status=body.status, prioritaet=body.prioritaet,
                                        faellig=body.faellig, meilenstein=body.meilenstein,
                                        abhaengig_von=body.abhaengig_von, rrule=body.rrule)
            except ValueError as e:
                raise HTTPException(400, str(e))
            return {"ok": True, "id": aid}

        @r.get("/api/aufgaben")
        def aufgabe_liste(projekt_id: str = "", status: str = "", faellig_bis: str = "",
                          meilenstein: str = "", bereich_id: str | None = None, limit: int = 100,
                          user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM aufgaben WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if projekt_id:
                q += " AND projekt_id=?"; params.append(projekt_id)
            if status:
                q += " AND status=?"; params.append(status)
            if faellig_bis:
                q += " AND faellig!='' AND faellig<=?"; params.append(faellig_bis)
            if meilenstein in ("0", "1"):
                q += " AND meilenstein=?"; params.append(int(meilenstein))
            if bereich_id is not None:           # None=alle · ''=nur „Allgemein" · id=Bereich
                q += " AND bereich_id=?"; params.append(bereich_id)
            q += " ORDER BY (faellig='') ASC, faellig ASC, created_at DESC LIMIT ?"
            params.append(min(max(limit, 1), 500))
            return [self._aufgabe_public(row) for row in db.get_conn().execute(q, params).fetchall()]

        @r.patch("/api/aufgaben/{aid}")
        def aufgabe_patch(aid: str, body: AufgabePatch,
                          user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            alt = conn.execute("SELECT * FROM aufgaben WHERE id=? AND user_id=? "
                               "AND deleted_at IS NULL", (aid, user.user_id)).fetchone()
            if alt is None:
                return JSONResponse({"error": "Aufgabe unbekannt"}, status_code=404)
            if body.rrule is not None and not recurrence.ist_gueltig(body.rrule.strip()):
                return JSONResponse({"error": "Ungültige Wiederholungsregel"}, status_code=400)
            felder, werte = [], []
            if body.titel is not None and body.titel.strip():
                felder.append("titel=?"); werte.append(body.titel.strip())
            if body.projekt_id is not None:
                if body.projekt_id and conn_proj_fehlt(db, user.user_id, body.projekt_id):
                    return JSONResponse({"error": "Projekt unbekannt"}, status_code=400)
                felder.append("projekt_id=?"); werte.append(body.projekt_id)
            if body.notiz is not None:
                felder.append("notiz=?"); werte.append(body.notiz.strip())
            if body.status is not None:
                felder.append("status=?"); werte.append(_in(body.status, AUFGABE_STATUS, "offen"))
            if body.prioritaet is not None:
                felder.append("prioritaet=?"); werte.append(_in(body.prioritaet, PRIORITAETEN, "mittel"))
            if body.faellig is not None:
                felder.append("faellig=?"); werte.append(body.faellig.strip())
            if body.meilenstein is not None:
                felder.append("meilenstein=?"); werte.append(int(body.meilenstein))
            if body.abhaengig_von is not None:
                felder.append("abhaengig_von=?")
                werte.append(json.dumps([str(x) for x in body.abhaengig_von], ensure_ascii=False))
            if body.rrule is not None:
                felder.append("rrule=?"); werte.append(body.rrule.strip())
            if not felder:
                return {"ok": True, "id": aid}
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [aid, user.user_id]
            conn.execute(f"UPDATE aufgaben SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "aufgabe_geaendert", {"id": aid})
            # Wiederkehrende Aufgabe: beim ÜBERGANG auf 'erledigt' die nächste
            # Instanz erzeugen (deterministisch, recurrence.naechste_faellig).
            # Nur beim echten Übergang (alt != erledigt), nur mit Regel + Frist.
            folge = self._spawn_folgeaufgabe(conn, user.user_id, alt, body)
            antwort = {"ok": True, "id": aid}
            if folge:
                antwort["folgeaufgabe"] = folge
            return antwort

        @r.delete("/api/aufgaben/{aid}")
        def aufgabe_delete(aid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM aufgaben WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (aid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Aufgabe unbekannt"}, status_code=404)
            conn.execute("UPDATE aufgaben SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), aid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "aufgabe_geloescht", {"id": aid})
            return {"ok": True, "id": aid}

        @r.post("/api/aufgaben/{aid}/archivieren")
        def aufgabe_archivieren_ep(aid: str,
                                   user: UserContext = Depends(current_user)):
            """„Als Meilenstein in Memory" (Nutzer-Zuruf): schickt diesen Aufgaben-/
            Meilenstein-Punkt explizit an Dizz Memory (Strom „meilenstein", V6)."""
            conn = db.get_conn()
            if conn.execute("SELECT 1 FROM aufgaben WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (aid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Aufgabe unbekannt"}, status_code=404)
            ergebnis = self._archiviere_meilenstein(user.user_id, aid, explizit=True)
            db.audit(user.user_id, "user", "meilenstein_archiviert",
                     {"id": aid, "status": ergebnis.get("status")})
            return ergebnis

        # ===================== TERMINE ======================================
        @r.post("/api/termine")
        def termin_anlegen(body: TerminIn,
                           user: UserContext = Depends(current_user)) -> dict[str, Any]:
            try:
                tid = self.neuer_termin(user.user_id, titel=body.titel, beginn=body.beginn,
                                        ende=body.ende, projekt_id=body.projekt_id,
                                        ganztags=body.ganztags, ort=body.ort, notiz=body.notiz,
                                        rrule=body.rrule)
            except ValueError as e:
                raise HTTPException(400, str(e))
            return {"ok": True, "id": tid}

        @r.post("/api/querverbindung/kalender")
        def querverbindung_kalender(body: KalenderEmpfangIn,
                                    user: UserContext = Depends(current_user)):
            """Querverbindungs-EMPFANG (Plans-Kalender-Seite, V5 docs/26): eine andere
            App (z. B. Communication aus einer Mail-Einladung) trägt ein Kalender-Event
            in den Plans-Kalender ein. **Idempotent** (``quelle=app`` × ``extern_id=ref``,
            gleicher iCal-Dedupe-Mechanismus), auditiert. Server-zu-Server über den
            Core-Relay (localhost-Guard + Single-User, kein Token)."""
            titel = (body.titel or "").strip() or "Termin"
            beginn = (body.beginn or "").strip()
            if not beginn:
                return JSONResponse({"ok": False, "error": "beginn fehlt"}, status_code=400)
            app = (body.app or "").strip() or "querverbindung"
            ref = (body.ref or "").strip() or f"{app}:{titel}:{beginn}"
            conn = db.get_conn()
            vorhanden = conn.execute(
                "SELECT id FROM termine WHERE user_id=? AND quelle=? AND extern_id=? "
                "AND deleted_at IS NULL", (user.user_id, app, ref)).fetchone()
            if vorhanden:
                return {"ok": True, "status": "vorhanden", "id": vorhanden["id"]}
            notiz = (body.beschreibung or "").strip()
            if (body.quelle or "").strip():
                notiz = (notiz + "\n\n" if notiz else "") + "Quelle: " + body.quelle.strip()
            ts = now_iso(); tid = new_id()
            conn.execute(
                "INSERT INTO termine (id, user_id, titel, beginn, ende, ganztags, ort, notiz, "
                "quelle, extern_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, user.user_id, titel, beginn, (body.ende or "").strip(),
                 int(body.ganztags), (body.ort or "").strip(), notiz, app, ref, ts, ts))
            conn.commit()
            db.audit(user.user_id, "system", "querverbindung_kalender_empfangen",
                     {"app": app, "id": tid, "titel": titel})
            return {"ok": True, "status": "eingetragen", "id": tid}

        @r.post("/api/termine/{tid}/an-komm")
        def termin_an_komm_ep(tid: str,
                              user: UserContext = Depends(current_user)):
            """„→ Kommunikation" (Nutzer-Zuruf): schickt diesen Termin als read-only
            Erinnerung an Dizz Communication (V5-Rücksync, docs/26 §4b). Gegenrichtung
            zum V5-Sender (Communication → Plans). Best-effort, idempotent."""
            conn = db.get_conn()
            if conn.execute("SELECT 1 FROM termine WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (tid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Termin unbekannt"}, status_code=404)
            ergebnis = self._sende_termin_an_komm(user.user_id, tid)
            db.audit(user.user_id, "user", "termin_an_komm",
                     {"id": tid, "status": ergebnis.get("status")})
            return ergebnis

        @r.get("/api/termine")
        def termin_liste(projekt_id: str = "", von: str = "", bis: str = "",
                         bereich_id: str | None = None, limit: int = 200,
                         user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM termine WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if projekt_id:
                q += " AND projekt_id=?"; params.append(projekt_id)
            if von:
                q += " AND (ende>=? OR beginn>=?)"; params += [von, von]
            if bis:
                q += " AND beginn<=?"; params.append(bis)
            if bereich_id is not None:           # None=alle · ''=nur „Allgemein" · id=Bereich
                q += " AND bereich_id=?"; params.append(bereich_id)
            q += " ORDER BY beginn ASC LIMIT ?"
            params.append(min(max(limit, 1), 1000))
            return [self._termin_public(row) for row in db.get_conn().execute(q, params).fetchall()]

        @r.patch("/api/termine/{tid}")
        def termin_patch(tid: str, body: TerminPatch,
                         user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM termine WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (tid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Termin unbekannt"}, status_code=404)
            felder, werte = [], []
            if body.titel is not None and body.titel.strip():
                felder.append("titel=?"); werte.append(body.titel.strip())
            if body.beginn is not None and body.beginn.strip():
                felder.append("beginn=?"); werte.append(body.beginn.strip())
            if body.ende is not None:
                felder.append("ende=?"); werte.append(body.ende.strip())
            if body.projekt_id is not None:
                if body.projekt_id and conn_proj_fehlt(db, user.user_id, body.projekt_id):
                    return JSONResponse({"error": "Projekt unbekannt"}, status_code=400)
                felder.append("projekt_id=?"); werte.append(body.projekt_id)
            if body.ganztags is not None:
                felder.append("ganztags=?"); werte.append(int(body.ganztags))
            if body.ort is not None:
                felder.append("ort=?"); werte.append(body.ort.strip())
            if body.notiz is not None:
                felder.append("notiz=?"); werte.append(body.notiz.strip())
            if body.rrule is not None:
                if not recurrence.ist_gueltig(body.rrule.strip()):
                    return JSONResponse({"error": "Ungültige Wiederholungsregel"}, status_code=400)
                felder.append("rrule=?"); werte.append(body.rrule.strip())
            if not felder:
                return {"ok": True, "id": tid}
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [tid, user.user_id]
            conn.execute(f"UPDATE termine SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "termin_geaendert", {"id": tid})
            return {"ok": True, "id": tid}

        @r.get("/api/termine/{tid}/serie")
        def termin_serie(tid: str, limit: int = 20, bis: str = "",
                         user: UserContext = Depends(current_user)):
            """Expandiert die Wiederholungsregel eines Termins in die nächsten
            Vorkommen (deterministisch, recurrence.expandiere — NICHT materialisiert:
            ein Master-Termin, berechnete Instanzen). Ohne Regel = ein Vorkommen."""
            conn = db.get_conn()
            row = conn.execute(
                "SELECT * FROM termine WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (tid, user.user_id)).fetchone()
            if row is None:
                return JSONResponse({"error": "Termin unbekannt"}, status_code=404)
            starts = recurrence.expandiere(row["rrule"], row["beginn"],
                                           limit=min(max(limit, 1), 366), bis=bis)
            return {"id": tid, "titel": row["titel"], "rrule": row["rrule"],
                    "wiederkehrend": bool((row["rrule"] or "").strip()),
                    "vorkommen": [{"beginn": s, "titel": row["titel"], "ort": row["ort"],
                                   "ganztags": bool(row["ganztags"])} for s in starts]}

        @r.delete("/api/termine/{tid}")
        def termin_delete(tid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM termine WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (tid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Termin unbekannt"}, status_code=404)
            conn.execute("UPDATE termine SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), tid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "termin_geloescht", {"id": tid})
            return {"ok": True, "id": tid}

        @r.post("/api/termine/import_ical")
        def termin_import_ical(body: ICalIn,
                               user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """iCal/.ics-Import über die ``CalendarSource``-Schiene (lokal-first).
            Idempotent: Dedupe per (quelle, extern_id) — erneuter Import desselben
            Kalenders aktualisiert bestehende Termine, statt sie zu duplizieren."""
            if body.projekt_id and conn_proj_fehlt(db, user.user_id, body.projekt_id):
                raise HTTPException(400, "Projekt unbekannt.")
            quelle = ICalImport(body.ics)
            try:
                events = quelle.list_events()
            except Exception as e:
                raise HTTPException(400, f"iCal nicht lesbar: {e}")
            if not events:
                return {"ok": True, "importiert": 0, "aktualisiert": 0, "gefunden": 0,
                        "hinweis": "Keine VEVENT-Einträge gefunden."}
            conn = db.get_conn()
            ts = now_iso()
            neu = akt = 0
            for ev in events:
                vorhanden = conn.execute(
                    "SELECT id FROM termine WHERE user_id=? AND quelle='ical' AND extern_id=? "
                    "AND deleted_at IS NULL", (user.user_id, ev.extern_id)).fetchone()
                if vorhanden:
                    conn.execute(
                        "UPDATE termine SET titel=?, beginn=?, ende=?, ganztags=?, ort=?, "
                        "notiz=?, rrule=?, updated_at=? WHERE id=? AND user_id=?",
                        (ev.titel, ev.beginn, ev.ende, int(ev.ganztags), ev.ort, ev.notiz,
                         ev.rrule, ts, vorhanden["id"], user.user_id))
                    akt += 1
                else:
                    conn.execute(
                        "INSERT INTO termine (id, user_id, projekt_id, titel, beginn, ende, "
                        "ganztags, ort, notiz, rrule, quelle, extern_id, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,'ical',?,?,?)",
                        (new_id(), user.user_id, body.projekt_id, ev.titel, ev.beginn, ev.ende,
                         int(ev.ganztags), ev.ort, ev.notiz, ev.rrule, ev.extern_id, ts, ts))
                    neu += 1
            conn.commit()
            db.audit(user.user_id, "user", "termine_importiert",
                     {"quelle": "ical", "neu": neu, "aktualisiert": akt})
            return {"ok": True, "importiert": neu, "aktualisiert": akt, "gefunden": len(events)}

        return r


def conn_proj_fehlt(db: Database, user_id: str, pid: str) -> bool:
    """True, wenn das referenzierte Projekt nicht (mehr) existiert."""
    return db.get_conn().execute(
        "SELECT id FROM projekte WHERE id=? AND user_id=? AND deleted_at IS NULL",
        (pid, user_id)).fetchone() is None


def build_projekte(db: Database, archiv_post=None, memory_get=None,
                   kalender_post=None) -> ProjekteDomain:
    return ProjekteDomain(db, archiv_post=archiv_post, memory_get=memory_get,
                          kalender_post=kalender_post)
