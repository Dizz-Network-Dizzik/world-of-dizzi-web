"""Geschäfts-/Studien-Domäne von Dizz Admin — Kunden · Produkte · Rechnungen
(GoBD-Archiv, append-only) · Fristen · Support + Geschäfts-KPIs + EÜR-Sicht +
Frist-Wächter (Geschäftsführung aus dem Basis-Repo `leading`; Studium = P-Stud-1).

Hier sitzt die App-eigene Substanz; alles Vertragliche (Summary/Settings/Account/
Datenrechte/Defense/Mini-Dizzi) liefert appkit über ``create_app``. Datenmodell
folgt den Vertrags-Konventionen (UUID/user_id/Timestamps/Soft-Delete) ⇒ DSGVO-
Export/Lösch-Kaskade/Retention greifen ohne Per-App-Code.

GoBD-Prinzip (Append-only): eine GESTELLTE Rechnung (Status ≠ ``entwurf``) ist
unveränderlich — Beträge/Positionen sind dann gesperrt, nur Status-Übergänge
(offen→bezahlt/storniert) sind erlaubt. Die laufende Nummer wird beim Stellen
lückenlos je Jahr vergeben. Geld in **Cent** (Minor-Units, integer — keine Floats).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from appkit.auth import UserContext, current_user
from appkit.csv_safe import csv_safe  # CSV-Formel-Injection-Schutz (EÜR-Export → Finanzamt)
from appkit.db import Database, new_id, now_iso
from appkit.summary import Kpi

from . import recurrence  # RRULE-light (A6: wiederkehrende Rechnungen)

# --- Domänen-Vokabular (UI + Validierung teilen sich diese Listen) -----------
PRODUKT_ART = ("app", "service", "lizenz", "sonstiges")
ABO_INTERVALL = ("einmalig", "monatlich", "jaehrlich")
RECHNUNG_STATUS = ("entwurf", "offen", "bezahlt", "storniert")
FRIST_KATEGORIE = ("steuer", "rechnung", "vertrag", "behoerde", "sonstiges")
# Mahnwesen (A8): eskalierende Stufen. ``frist_tage`` = Zahlungsziel der Mahnung
# ab Erstellung; ``gebuehr_cent`` = pauschale Mahngebühr (DE-übliche Größen).
MAHN_STUFEN = {
    1: {"label": "Zahlungserinnerung", "frist_tage": 14, "gebuehr_cent": 0},
    2: {"label": "1. Mahnung",         "frist_tage": 10, "gebuehr_cent": 500},
    3: {"label": "2. Mahnung",         "frist_tage": 7,  "gebuehr_cent": 1000},
}
MAHN_MAX_STUFE = 3
MAHN_STATUS = ("offen", "erledigt")
SUPPORT_STATUS = ("offen", "in_arbeit", "geschlossen")
SUPPORT_PRIO = ("niedrig", "normal", "hoch", "dringend")
# Studienverwaltung (P-Stud-1, docs/04)
BILDUNGSWEG_ART = ("universitaet", "fachhochschule", "ausbildung", "dual", "promotion", "sonstiges")
ABSCHLUSS_ART = ("bachelor", "master", "staatsexamen", "diplom", "ausbildungsberuf", "sonstiges")
BILDUNGSWEG_STATUS = ("laufend", "abgeschlossen", "abgebrochen", "pausiert")
MODUL_TYP = ("pflicht", "wahlpflicht", "wahl")
MODUL_BEREICH = ("hauptfach", "nebenfach", "schluesselqual", "thesis", "sonstiges")
MODUL_STATUS = ("offen", "geplant", "angemeldet", "bestanden", "nicht_bestanden", "endgueltig", "anerkannt")
STUDIENFRIST_ART = ("anmeldung", "abgabe", "rueckmeldung", "orientierung", "pruefung", "sonstiges")

# Domänen-Schema — direkt an create_app/Database übergeben (extra_schema).
SCHEMA = """
CREATE TABLE IF NOT EXISTS kunden (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    firma       TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    adresse     TEXT NOT NULL DEFAULT '',
    notiz       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_kunden ON kunden (user_id, name);

CREATE TABLE IF NOT EXISTS produkte (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    name          TEXT NOT NULL,                  -- z. B. eine Dizz-App
    art           TEXT NOT NULL DEFAULT 'app',    -- app|service|lizenz|sonstiges
    preis_cent    INTEGER NOT NULL DEFAULT 0,
    abo_intervall TEXT NOT NULL DEFAULT 'einmalig',-- einmalig|monatlich|jaehrlich
    aktiv         INTEGER NOT NULL DEFAULT 1,
    notiz         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_produkte ON produkte (user_id, aktiv);

CREATE TABLE IF NOT EXISTS rechnungen (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    nummer       TEXT NOT NULL DEFAULT '',        -- leer im Entwurf; lückenlos je Jahr beim Stellen
    kunde_id     TEXT NOT NULL DEFAULT '',
    titel        TEXT NOT NULL DEFAULT '',
    datum        TEXT NOT NULL DEFAULT '',        -- Rechnungsdatum (beim Stellen gesetzt)
    faellig_am   TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'entwurf', -- entwurf|offen|bezahlt|storniert
    netto_cent   INTEGER NOT NULL DEFAULT 0,      -- Snapshot beim Stellen (GoBD-immutabel)
    ust_cent     INTEGER NOT NULL DEFAULT 0,
    brutto_cent  INTEGER NOT NULL DEFAULT 0,
    bezahlt_am   TEXT NOT NULL DEFAULT '',
    notiz        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_rechnungen ON rechnungen (user_id, status, datum);

CREATE TABLE IF NOT EXISTS rechnung_positionen (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    rechnung_id     TEXT NOT NULL,
    beschreibung    TEXT NOT NULL DEFAULT '',
    menge           REAL NOT NULL DEFAULT 1,
    einzelpreis_cent INTEGER NOT NULL DEFAULT 0,
    ust_satz        INTEGER NOT NULL DEFAULT 19,  -- Prozent (19|7|0)
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_positionen ON rechnung_positionen (user_id, rechnung_id);

CREATE TABLE IF NOT EXISTS fristen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    titel       TEXT NOT NULL,
    kategorie   TEXT NOT NULL DEFAULT 'sonstiges',
    faellig_am  TEXT NOT NULL DEFAULT '',
    erledigt    INTEGER NOT NULL DEFAULT 0,
    notiz       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_fristen ON fristen (user_id, erledigt, faellig_am);

CREATE TABLE IF NOT EXISTS support (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    kunde_id    TEXT NOT NULL DEFAULT '',
    betreff     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'offen',
    prioritaet  TEXT NOT NULL DEFAULT 'normal',
    notiz       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_support ON support (user_id, status);

-- Mahnwesen (A8, docs/30): eigene Entität NEBEN der Rechnung. GoBD-Kern bleibt
-- unangetastet — eine Mahnung verweist nur read-only auf ``rechnung_id`` und
-- ändert die Rechnung NICHT (keine Status-/Betrags-Mutation). Eskalierende Stufen
-- (Zahlungserinnerung → 1./2. Mahnung) mit eigener Zahlungsfrist + Mahngebühr.
CREATE TABLE IF NOT EXISTS mahnungen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    rechnung_id TEXT NOT NULL,                   -- read-only Bezug auf die Rechnung
    stufe       INTEGER NOT NULL DEFAULT 1,      -- 1=Zahlungserinnerung, 2=1. Mahnung, 3=2. Mahnung
    titel       TEXT NOT NULL DEFAULT '',
    frist_am    TEXT NOT NULL DEFAULT '',        -- neue Zahlungsfrist (ISO-Date)
    gebuehr_cent INTEGER NOT NULL DEFAULT 0,     -- pauschale Mahngebühr (Cent)
    status      TEXT NOT NULL DEFAULT 'offen',   -- offen|erledigt
    notiz       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_mahnungen ON mahnungen (user_id, rechnung_id, status);

-- Wiederkehrende Rechnungen / Abo-Stellung (A6, docs/30): eine Vorlage (Kunde +
-- Positionen + RRULE-light) erzeugt getaktet ENTWURFS-Rechnungen (Plan→Ist). GoBD
-- bleibt unberührt — die laufende Nummer wird erst beim Stellen vergeben. Erzeugung
-- ist HITL + idempotent über ``naechster_lauf`` (kein Scheduler; Lauf wird ausgelöst).
CREATE TABLE IF NOT EXISTS rechnung_abo (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    kunde_id       TEXT NOT NULL DEFAULT '',
    titel          TEXT NOT NULL DEFAULT '',
    rrule          TEXT NOT NULL DEFAULT 'FREQ=MONTHLY',  -- RRULE-light (jährlich = MONTHLY;INTERVAL=12)
    positionen     TEXT NOT NULL DEFAULT '[]',            -- JSON-Vorlage [{beschreibung,menge,einzelpreis_cent,ust_satz}]
    faellig_tage   INTEGER NOT NULL DEFAULT 14,           -- Zahlungsziel der erzeugten Rechnung (Tage)
    naechster_lauf TEXT NOT NULL DEFAULT '',              -- ISO-Date: wann die nächste Rechnung gezogen wird
    letzter_lauf   TEXT NOT NULL DEFAULT '',
    aktiv          INTEGER NOT NULL DEFAULT 1,
    bereich_id     TEXT NOT NULL DEFAULT '',              -- erzeugte Rechnungen erben diesen Bereich
    notiz          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    deleted_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_rechnung_abo ON rechnung_abo (user_id, aktiv, naechster_lauf);

-- KPI-Verlauf (UI/UX-Phase P1c): EIN Snapshot je Tag — Grundlage für Trend-Pfeile
-- + MRR-Zerlegung (neu/Expansion/Contraction/Churn). Additiv, deterministisch,
-- ohne Scheduler (lazy beim Lesen geschrieben). Vertrags-konventionen (user_id/
-- Timestamps/Soft-Delete) ⇒ DSGVO-Export + Lösch-Kaskade greifen ohne Per-App-Code.
CREATE TABLE IF NOT EXISTS kpi_snapshot (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    datum          TEXT NOT NULL,                  -- YYYY-MM-DD (ein Punkt je Tag)
    umsatz_cent    INTEGER NOT NULL DEFAULT 0,
    mrr_cent       INTEGER NOT NULL DEFAULT 0,
    offen_cent     INTEGER NOT NULL DEFAULT 0,
    offen_n        INTEGER NOT NULL DEFAULT 0,
    ueberfaellig_n INTEGER NOT NULL DEFAULT 0,
    kunden_n       INTEGER NOT NULL DEFAULT 0,
    mrr_posten     TEXT NOT NULL DEFAULT '{}',     -- JSON {produkt_id: mrr_cent} für die Zerlegung
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    deleted_at     TEXT,
    UNIQUE (user_id, datum)
);
CREATE INDEX IF NOT EXISTS idx_kpi_snapshot ON kpi_snapshot (user_id, datum);

-- === Studienverwaltung (P-Stud-1, docs/04) =================================
CREATE TABLE IF NOT EXISTS bildungsweg (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    art              TEXT NOT NULL DEFAULT 'universitaet', -- universitaet|fachhochschule|ausbildung|dual|promotion|sonstiges
    institution      TEXT NOT NULL DEFAULT '',             -- z. B. Universität Bayreuth
    abschluss        TEXT NOT NULL DEFAULT '',             -- bachelor|master|staatsexamen|diplom|ausbildungsberuf|sonstiges
    studiengang      TEXT NOT NULL DEFAULT '',             -- Studiengang bzw. Ausbildungsberuf
    hauptfach        TEXT NOT NULL DEFAULT '',
    nebenfach        TEXT NOT NULL DEFAULT '',
    matrikelnr       TEXT NOT NULL DEFAULT '',             -- SENSIBEL
    po_version       TEXT NOT NULL DEFAULT '',             -- PO-Jahrgang/Version (frei)
    start_semester   TEXT NOT NULL DEFAULT '',             -- z. B. WS2024 / SS2025
    regelstudienzeit INTEGER NOT NULL DEFAULT 0,           -- Semester (0=unbekannt)
    ects_gesamt      INTEGER NOT NULL DEFAULT 0,           -- Soll-ECTS gesamt (0=unbekannt)
    max_versuche     INTEGER NOT NULL DEFAULT 3,           -- Default-Versuche je Modulprüfung
    kammer           TEXT NOT NULL DEFAULT '',             -- Ausbildung: IHK/HWK
    betrieb          TEXT NOT NULL DEFAULT '',             -- Ausbildung: Ausbildungsbetrieb
    berufsschule     TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'laufend',      -- laufend|abgeschlossen|abgebrochen|pausiert
    notiz            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    deleted_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_bildungsweg ON bildungsweg (user_id, status);

CREATE TABLE IF NOT EXISTS studienmodul (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    bildungsweg_id TEXT NOT NULL,
    code           TEXT NOT NULL DEFAULT '',
    name           TEXT NOT NULL,
    typ            TEXT NOT NULL DEFAULT 'pflicht',        -- pflicht|wahlpflicht|wahl
    bereich        TEXT NOT NULL DEFAULT 'hauptfach',      -- hauptfach|nebenfach|schluesselqual|thesis|sonstiges
    ects           INTEGER NOT NULL DEFAULT 0,
    empf_semester  INTEGER NOT NULL DEFAULT 0,             -- empfohlenes Fachsemester (0=offen)
    pruefungsform  TEXT NOT NULL DEFAULT '',               -- klausur|muendlich|hausarbeit|portfolio|...
    max_versuche   INTEGER NOT NULL DEFAULT 0,             -- 0 => Default des Bildungswegs
    status         TEXT NOT NULL DEFAULT 'offen',          -- offen|geplant|angemeldet|bestanden|nicht_bestanden|endgueltig|anerkannt
    versuch_nr     INTEGER NOT NULL DEFAULT 0,             -- genutzte Versuche (0=noch keiner)
    note           REAL,                                   -- z. B. 1.7 (NULL=keine)
    ects_erreicht  INTEGER NOT NULL DEFAULT 0,
    abgelegt_am    TEXT NOT NULL DEFAULT '',
    notiz          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    deleted_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_studienmodul ON studienmodul (user_id, bildungsweg_id, status);

CREATE TABLE IF NOT EXISTS studienfrist (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    bildungsweg_id TEXT NOT NULL,
    modul_id       TEXT NOT NULL DEFAULT '',               -- optionaler Modulbezug
    titel          TEXT NOT NULL,
    art            TEXT NOT NULL DEFAULT 'sonstiges',       -- anmeldung|abgabe|rueckmeldung|orientierung|pruefung|sonstiges
    faellig_am     TEXT NOT NULL DEFAULT '',
    erledigt       INTEGER NOT NULL DEFAULT 0,
    notiz          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    deleted_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_studienfrist ON studienfrist (user_id, erledigt, faellig_am);
"""


# --- Request-Modelle: MODUL-Ebene zwingend (PEP-563-Falle, refapp/README) -----
class KundeIn(BaseModel):
    name: str
    firma: str = ""
    email: str = ""
    adresse: str = ""
    notiz: str = ""


class KundePatch(BaseModel):
    name: str | None = None
    firma: str | None = None
    email: str | None = None
    adresse: str | None = None
    notiz: str | None = None


class ProduktIn(BaseModel):
    name: str
    art: str = "app"
    preis_cent: int = 0
    abo_intervall: str = "einmalig"
    notiz: str = ""


class ProduktPatch(BaseModel):
    name: str | None = None
    art: str | None = None
    preis_cent: int | None = None
    abo_intervall: str | None = None
    aktiv: bool | None = None
    notiz: str | None = None


class PositionIn(BaseModel):
    beschreibung: str = ""
    menge: float = 1
    einzelpreis_cent: int = 0
    ust_satz: int = 19


class RechnungIn(BaseModel):
    kunde_id: str = ""
    titel: str = ""
    faellig_am: str = ""
    notiz: str = ""
    positionen: list[PositionIn] = []


class FristIn(BaseModel):
    titel: str
    kategorie: str = "sonstiges"
    faellig_am: str = ""
    notiz: str = ""


class FristPatch(BaseModel):
    titel: str | None = None
    kategorie: str | None = None
    faellig_am: str | None = None
    erledigt: bool | None = None
    notiz: str | None = None


class MahnungIn(BaseModel):
    """A8: eine Mahnung zu einer offenen (gestellten, überfälligen) Rechnung.
    ``stufe``/``frist_am``/``gebuehr_cent`` leer ⇒ deterministisch abgeleitet
    (nächste Stufe, Standard-Zahlungsziel + Standard-Gebühr der Stufe)."""
    rechnung_id: str
    stufe: int | None = None
    frist_am: str = ""
    gebuehr_cent: int | None = None
    titel: str = ""
    notiz: str = ""


class MahnungPatch(BaseModel):
    status: str | None = None
    frist_am: str | None = None
    gebuehr_cent: int | None = None
    titel: str | None = None
    notiz: str | None = None


class RechnungAboIn(BaseModel):
    """A6: Vorlage für wiederkehrende Rechnungen. ``rrule`` = RRULE-light
    (``FREQ=MONTHLY`` etc.; jährlich = ``FREQ=MONTHLY;INTERVAL=12``).
    ``naechster_lauf`` leer ⇒ heute (sofort fällig)."""
    kunde_id: str = ""
    titel: str = ""
    rrule: str = "FREQ=MONTHLY"
    positionen: list[PositionIn] = []
    faellig_tage: int = 14
    naechster_lauf: str = ""
    notiz: str = ""
    bereich_id: str = ""
    aktiv: bool = True


class RechnungAboPatch(BaseModel):
    kunde_id: str | None = None
    titel: str | None = None
    rrule: str | None = None
    positionen: list[PositionIn] | None = None
    faellig_tage: int | None = None
    naechster_lauf: str | None = None
    notiz: str | None = None
    bereich_id: str | None = None
    aktiv: bool | None = None


class SupportIn(BaseModel):
    betreff: str
    kunde_id: str = ""
    prioritaet: str = "normal"
    notiz: str = ""


class SupportPatch(BaseModel):
    betreff: str | None = None
    kunde_id: str | None = None
    status: str | None = None
    prioritaet: str | None = None
    notiz: str | None = None


# --- Studienverwaltung (P-Stud-1) -------------------------------------------
class BildungswegIn(BaseModel):
    art: str = "universitaet"
    institution: str = ""
    abschluss: str = ""
    studiengang: str = ""
    hauptfach: str = ""
    nebenfach: str = ""
    matrikelnr: str = ""
    po_version: str = ""
    start_semester: str = ""
    regelstudienzeit: int = 0
    ects_gesamt: int = 0
    max_versuche: int = 3
    kammer: str = ""
    betrieb: str = ""
    berufsschule: str = ""
    notiz: str = ""


class BildungswegPatch(BaseModel):
    art: str | None = None
    institution: str | None = None
    abschluss: str | None = None
    studiengang: str | None = None
    hauptfach: str | None = None
    nebenfach: str | None = None
    matrikelnr: str | None = None
    po_version: str | None = None
    start_semester: str | None = None
    regelstudienzeit: int | None = None
    ects_gesamt: int | None = None
    max_versuche: int | None = None
    kammer: str | None = None
    betrieb: str | None = None
    berufsschule: str | None = None
    status: str | None = None
    notiz: str | None = None


class StudienmodulIn(BaseModel):
    name: str
    code: str = ""
    typ: str = "pflicht"
    bereich: str = "hauptfach"
    ects: int = 0
    empf_semester: int = 0
    pruefungsform: str = ""
    max_versuche: int = 0
    notiz: str = ""


class StudienmodulPatch(BaseModel):
    name: str | None = None
    code: str | None = None
    typ: str | None = None
    bereich: str | None = None
    ects: int | None = None
    empf_semester: int | None = None
    pruefungsform: str | None = None
    max_versuche: int | None = None
    status: str | None = None
    notiz: str | None = None


class ModulErgebnisIn(BaseModel):
    bestanden: bool
    note: float | None = None
    ects_erreicht: int | None = None


class StudienfristIn(BaseModel):
    titel: str
    art: str = "sonstiges"
    faellig_am: str = ""
    modul_id: str = ""
    notiz: str = ""


class StudienfristPatch(BaseModel):
    titel: str | None = None
    art: str | None = None
    faellig_am: str | None = None
    modul_id: str | None = None
    erledigt: bool | None = None
    notiz: str | None = None


def heute_iso() -> str:
    return date.today().isoformat()


def _in(wert: str, erlaubt: tuple[str, ...], default: str) -> str:
    return wert if wert in erlaubt else default


class Domain:
    """Bündelt Router + Kennzahl-Funktionen der Leading-Domäne. main.py reicht
    ``summary``/``stats`` an Vertrag bzw. MCP, ``ki_kontext`` an die KI."""

    def __init__(self, db: Database, http_post: Any | None = None,
                 ausgaben_reader: Any | None = None) -> None:
        self.db = db
        self.http_post = http_post
        # V16: liefert die geschäftlichen Ausgaben eines Jahres (Dizz Money über den
        # Core-Relay) für die EÜR-Ausgabenseite. None ⇒ EÜR zeigt nur die Einnahmen.
        self.ausgaben_reader = ausgaben_reader
        self.router = self._build_router()

    # --- gemeinsame Helfer --------------------------------------------------
    def _row(self, tabelle: str, user_id: str, rid: str):
        return self.db.get_conn().execute(
            f"SELECT * FROM {tabelle} WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (rid, user_id)).fetchone()

    def _soft_delete(self, tabelle: str, user_id: str, rid: str) -> bool:
        conn = self.db.get_conn()
        cur = conn.execute(
            f"UPDATE {tabelle} SET deleted_at=?, updated_at=? "
            f"WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (now_iso(), now_iso(), rid, user_id))
        conn.commit()
        return cur.rowcount > 0

    def _positionen(self, user_id: str, rechnung_id: str) -> list[dict[str, Any]]:
        rows = self.db.get_conn().execute(
            "SELECT * FROM rechnung_positionen WHERE rechnung_id=? AND user_id=? "
            "AND deleted_at IS NULL ORDER BY created_at", (rechnung_id, user_id)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _summe(positionen: list[dict[str, Any]]) -> tuple[int, int, int]:
        """(netto_cent, ust_cent, brutto_cent) aus Positionen — kaufmännisch gerundet."""
        netto = ust = 0
        for p in positionen:
            zeile = round(float(p["menge"]) * int(p["einzelpreis_cent"]))
            netto += zeile
            ust += round(zeile * int(p["ust_satz"]) / 100)
        return netto, ust, netto + ust

    def _rechnung_dict(self, user_id: str, row) -> dict[str, Any]:
        d = dict(row)
        pos = self._positionen(user_id, row["id"])
        d["positionen"] = pos
        if row["status"] == "entwurf":                 # Entwurf: live rechnen
            d["netto_cent"], d["ust_cent"], d["brutto_cent"] = self._summe(pos)
        return d

    # --- Router -------------------------------------------------------------
    def _build_router(self) -> APIRouter:
        r = APIRouter()
        db = self.db

        # ===== Kunden ======================================================
        @r.get("/api/kunden")
        def kunden_liste(bereich_id: str | None = None, user: UserContext = Depends(current_user)):
            q = "SELECT * FROM kunden WHERE user_id=? AND deleted_at IS NULL"
            p: list[Any] = [user.user_id]
            if bereich_id is not None:           # None=alle · ''=nur „Allgemein" · id=Bereich
                q += " AND bereich_id=?"; p.append(bereich_id)
            rows = db.get_conn().execute(q + " ORDER BY name", p).fetchall()
            return [dict(x) for x in rows]

        @r.post("/api/kunden")
        def kunde_anlegen(body: KundeIn, user: UserContext = Depends(current_user)):
            if not body.name.strip():
                return JSONResponse({"error": "Name fehlt"}, status_code=400)
            kid = new_id(); ts = now_iso()
            db.get_conn().execute(
                "INSERT INTO kunden (id,user_id,name,firma,email,adresse,notiz,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (kid, user.user_id, body.name.strip(), body.firma, body.email,
                 body.adresse, body.notiz, ts, ts))
            db.get_conn().commit()
            db.audit(user.user_id, "user", "kunde_angelegt", {"id": kid})
            return {"ok": True, "id": kid}

        @r.put("/api/kunden/{kid}")
        def kunde_aendern(kid: str, body: KundePatch, user: UserContext = Depends(current_user)):
            if self._row("kunden", user.user_id, kid) is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            self._patch("kunden", user.user_id, kid, body.model_dump(exclude_none=True))
            return {"ok": True, "id": kid}

        @r.delete("/api/kunden/{kid}")
        def kunde_loeschen(kid: str, user: UserContext = Depends(current_user)):
            if not self._soft_delete("kunden", user.user_id, kid):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            db.audit(user.user_id, "user", "kunde_geloescht", {"id": kid})
            return {"ok": True, "id": kid}

        # ===== Produkte ====================================================
        @r.get("/api/produkte")
        def produkte_liste(aktiv: int = -1, bereich_id: str | None = None,
                           user: UserContext = Depends(current_user)):
            q = "SELECT * FROM produkte WHERE user_id=? AND deleted_at IS NULL"
            p: list[Any] = [user.user_id]
            if aktiv in (0, 1):
                q += " AND aktiv=?"; p.append(aktiv)
            if bereich_id is not None:           # None=alle · ''=nur „Allgemein" · id=Bereich
                q += " AND bereich_id=?"; p.append(bereich_id)
            rows = db.get_conn().execute(q + " ORDER BY name", p).fetchall()
            return [dict(x) for x in rows]

        @r.post("/api/produkte")
        def produkt_anlegen(body: ProduktIn, user: UserContext = Depends(current_user)):
            if not body.name.strip():
                return JSONResponse({"error": "Name fehlt"}, status_code=400)
            pid = new_id(); ts = now_iso()
            db.get_conn().execute(
                "INSERT INTO produkte (id,user_id,name,art,preis_cent,abo_intervall,notiz,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, user.user_id, body.name.strip(), _in(body.art, PRODUKT_ART, "app"),
                 max(0, int(body.preis_cent)), _in(body.abo_intervall, ABO_INTERVALL, "einmalig"),
                 body.notiz, ts, ts))
            db.get_conn().commit()
            return {"ok": True, "id": pid}

        @r.put("/api/produkte/{pid}")
        def produkt_aendern(pid: str, body: ProduktPatch, user: UserContext = Depends(current_user)):
            if self._row("produkte", user.user_id, pid) is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            werte = body.model_dump(exclude_none=True)
            if "art" in werte:
                werte["art"] = _in(werte["art"], PRODUKT_ART, "app")
            if "abo_intervall" in werte:
                werte["abo_intervall"] = _in(werte["abo_intervall"], ABO_INTERVALL, "einmalig")
            if "aktiv" in werte:
                werte["aktiv"] = int(bool(werte["aktiv"]))
            self._patch("produkte", user.user_id, pid, werte)
            return {"ok": True, "id": pid}

        @r.delete("/api/produkte/{pid}")
        def produkt_loeschen(pid: str, user: UserContext = Depends(current_user)):
            if not self._soft_delete("produkte", user.user_id, pid):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return {"ok": True, "id": pid}

        # ===== Rechnungen (GoBD append-only) ===============================
        @r.get("/api/rechnungen")
        def rechnungen_liste(status: str = "", bereich_id: str | None = None,
                             user: UserContext = Depends(current_user)):
            q = "SELECT * FROM rechnungen WHERE user_id=? AND deleted_at IS NULL"
            p: list[Any] = [user.user_id]
            if status in RECHNUNG_STATUS:
                q += " AND status=?"; p.append(status)
            if bereich_id is not None:           # None=alle · ''=nur „Allgemein" · id=Bereich
                q += " AND bereich_id=?"; p.append(bereich_id)
            rows = db.get_conn().execute(q + " ORDER BY created_at DESC", p).fetchall()
            return [self._rechnung_dict(user.user_id, x) for x in rows]

        @r.get("/api/rechnungen/{rid}")
        def rechnung_holen(rid: str, user: UserContext = Depends(current_user)):
            row = self._row("rechnungen", user.user_id, rid)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return self._rechnung_dict(user.user_id, row)

        @r.post("/api/rechnungen")
        def rechnung_anlegen(body: RechnungIn, user: UserContext = Depends(current_user)):
            rid = new_id(); ts = now_iso()
            db.get_conn().execute(
                "INSERT INTO rechnungen (id,user_id,kunde_id,titel,faellig_am,notiz,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?, 'entwurf', ?,?)",
                (rid, user.user_id, body.kunde_id, body.titel, body.faellig_am, body.notiz, ts, ts))
            self._positionen_schreiben(user.user_id, rid, body.positionen)
            db.get_conn().commit()
            db.audit(user.user_id, "user", "rechnung_entwurf", {"id": rid})
            return {"ok": True, "id": rid, "status": "entwurf"}

        @r.put("/api/rechnungen/{rid}")
        def rechnung_aendern(rid: str, body: RechnungIn, user: UserContext = Depends(current_user)):
            row = self._row("rechnungen", user.user_id, rid)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            if row["status"] != "entwurf":          # GoBD: gestellte Rechnung ist unveränderlich
                return JSONResponse({"error": "Gestellte Rechnung ist unveränderlich (GoBD)."},
                                    status_code=409)
            self._patch("rechnungen", user.user_id, rid,
                        {"kunde_id": body.kunde_id, "titel": body.titel,
                         "faellig_am": body.faellig_am, "notiz": body.notiz})
            # Positionen ersetzen (nur im Entwurf erlaubt)
            db.get_conn().execute(
                "UPDATE rechnung_positionen SET deleted_at=? WHERE rechnung_id=? AND user_id=? AND deleted_at IS NULL",
                (now_iso(), rid, user.user_id))
            self._positionen_schreiben(user.user_id, rid, body.positionen)
            db.get_conn().commit()
            return {"ok": True, "id": rid}

        @r.post("/api/rechnungen/{rid}/stellen")
        def rechnung_stellen(rid: str, user: UserContext = Depends(current_user)):
            """Entwurf → offen: vergibt die lückenlose Nummer + friert die Beträge ein (GoBD)."""
            row = self._row("rechnungen", user.user_id, rid)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            if row["status"] != "entwurf":
                return JSONResponse({"error": "Nur ein Entwurf kann gestellt werden."}, status_code=409)
            pos = self._positionen(user.user_id, rid)
            if not pos:
                return JSONResponse({"error": "Rechnung ohne Positionen."}, status_code=400)
            netto, ust, brutto = self._summe(pos)
            nummer = self._naechste_nummer(user.user_id)
            ts = now_iso(); heute = heute_iso()
            db.get_conn().execute(
                "UPDATE rechnungen SET status='offen', nummer=?, datum=?, "
                "netto_cent=?, ust_cent=?, brutto_cent=?, updated_at=? WHERE id=? AND user_id=?",
                (nummer, heute, netto, ust, brutto, ts, rid, user.user_id))
            db.get_conn().commit()
            db.audit(user.user_id, "user", "rechnung_gestellt", {"id": rid, "nummer": nummer})
            return {"ok": True, "id": rid, "nummer": nummer, "status": "offen", "brutto_cent": brutto}

        @r.post("/api/rechnungen/{rid}/bezahlt")
        def rechnung_bezahlt(rid: str, user: UserContext = Depends(current_user)):
            row = self._row("rechnungen", user.user_id, rid)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            if row["status"] != "offen":
                return JSONResponse({"error": "Nur eine offene Rechnung kann bezahlt werden."}, status_code=409)
            db.get_conn().execute(
                "UPDATE rechnungen SET status='bezahlt', bezahlt_am=?, updated_at=? WHERE id=? AND user_id=?",
                (heute_iso(), now_iso(), rid, user.user_id))
            db.get_conn().commit()
            db.audit(user.user_id, "user", "rechnung_bezahlt", {"id": rid})
            self.schliesse_mahnungen(user.user_id, rid)   # A8: offene Mahnungen erledigen
            return {"ok": True, "id": rid, "status": "bezahlt"}

        @r.post("/api/rechnungen/{rid}/stornieren")
        def rechnung_stornieren(rid: str, user: UserContext = Depends(current_user)):
            row = self._row("rechnungen", user.user_id, rid)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            if row["status"] not in ("offen", "bezahlt"):
                return JSONResponse({"error": "Nur eine gestellte Rechnung kann storniert werden."}, status_code=409)
            db.get_conn().execute(
                "UPDATE rechnungen SET status='storniert', updated_at=? WHERE id=? AND user_id=?",
                (now_iso(), rid, user.user_id))
            db.get_conn().commit()
            db.audit(user.user_id, "user", "rechnung_storniert", {"id": rid})
            self.schliesse_mahnungen(user.user_id, rid)   # A8: offene Mahnungen erledigen
            return {"ok": True, "id": rid, "status": "storniert"}

        @r.delete("/api/rechnungen/{rid}")
        def rechnung_loeschen(rid: str, user: UserContext = Depends(current_user)):
            row = self._row("rechnungen", user.user_id, rid)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            if row["status"] != "entwurf":          # GoBD: gestellte Rechnungen NIE löschen, nur stornieren
                return JSONResponse({"error": "Nur ein Entwurf kann gelöscht werden (sonst stornieren)."},
                                    status_code=409)
            db.get_conn().execute(
                "UPDATE rechnung_positionen SET deleted_at=? WHERE rechnung_id=? AND user_id=?",
                (now_iso(), rid, user.user_id))
            self._soft_delete("rechnungen", user.user_id, rid)
            return {"ok": True, "id": rid}

        # ===== Mahnwesen (A8) — eigene Entität neben der GoBD-Rechnung =====
        @r.get("/api/mahnungen/vorschlaege")
        def mahn_vorschlaege_ep(user: UserContext = Depends(current_user)):
            """Welche überfällige offene Rechnung braucht (die nächste) Mahnstufe?
            Read-only, deterministisch — legt nichts an (HITL: Nutzer mahnt aktiv)."""
            return {"vorschlaege": self.mahn_vorschlaege(user.user_id),
                    "stufen": MAHN_STUFEN, "max_stufe": MAHN_MAX_STUFE}

        @r.get("/api/mahnungen")
        def mahnungen_liste_ep(rechnung_id: str = "", status: str = "",
                               user: UserContext = Depends(current_user)):
            return self.mahnungen_liste(user.user_id, rechnung_id=rechnung_id, status=status)

        @r.post("/api/mahnungen")
        def mahnung_anlegen(body: MahnungIn, user: UserContext = Depends(current_user)):
            if not (body.rechnung_id or "").strip():
                return JSONResponse({"error": "rechnung_id fehlt"}, status_code=400)
            try:
                return self.neue_mahnung(
                    user.user_id, rechnung_id=body.rechnung_id.strip(), stufe=body.stufe,
                    frist_am=body.frist_am, gebuehr_cent=body.gebuehr_cent,
                    titel=body.titel, notiz=body.notiz)
            except ValueError as e:
                code = 404 if "unbekannt" in str(e) else 409
                return JSONResponse({"error": str(e)}, status_code=code)

        @r.patch("/api/mahnungen/{mid}")
        def mahnung_aendern(mid: str, body: MahnungPatch,
                            user: UserContext = Depends(current_user)):
            if self._row("mahnungen", user.user_id, mid) is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            werte = body.model_dump(exclude_none=True)
            if "status" in werte:
                werte["status"] = _in(werte["status"], MAHN_STATUS, "offen")
            if "gebuehr_cent" in werte:
                werte["gebuehr_cent"] = max(0, int(werte["gebuehr_cent"]))
            self._patch("mahnungen", user.user_id, mid, werte)
            return {"ok": True, "id": mid}

        @r.delete("/api/mahnungen/{mid}")
        def mahnung_loeschen(mid: str, user: UserContext = Depends(current_user)):
            if not self._soft_delete("mahnungen", user.user_id, mid):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return {"ok": True, "id": mid}

        # ===== Wiederkehrende Rechnungen / Abos (A6) =======================
        @r.get("/api/rechnung-abos/vorschlaege")
        def abo_vorschlaege_ep(user: UserContext = Depends(current_user)):
            """Erkennung: aktive Abo-Produkte als fertige Abo-Vorlagen (Anlage per Klick)."""
            return {"vorschlaege": self.abo_vorschlaege(user.user_id)}

        @r.get("/api/rechnung-abos/faellig")
        def abo_faellig_ep(user: UserContext = Depends(current_user)):
            """Welche Abos sind zum Ziehen fällig (read-only Vorschau)?"""
            return {"faellig": self.abo_faellig(user.user_id)}

        @r.post("/api/rechnung-abos/lauf")
        def abo_lauf_ep(user: UserContext = Depends(current_user)):
            """Sammel-Lauf: aus allen fälligen Abos Entwurfs-Rechnungen ziehen (HITL)."""
            return self.abo_lauf(user.user_id)

        @r.get("/api/rechnung-abos")
        def abo_liste_ep(aktiv: int = -1, bereich_id: str | None = None,
                         user: UserContext = Depends(current_user)):
            return self.abo_liste(user.user_id, aktiv=aktiv, bereich_id=bereich_id)

        @r.post("/api/rechnung-abos")
        def abo_anlegen(body: RechnungAboIn, user: UserContext = Depends(current_user)):
            try:
                return self.neue_abo(user.user_id, body)
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)

        @r.get("/api/rechnung-abos/{aid}")
        def abo_holen(aid: str, user: UserContext = Depends(current_user)):
            row = self._row("rechnung_abo", user.user_id, aid)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return self._abo_public(row)

        @r.patch("/api/rechnung-abos/{aid}")
        def abo_aendern(aid: str, body: RechnungAboPatch,
                        user: UserContext = Depends(current_user)):
            if self._row("rechnung_abo", user.user_id, aid) is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            werte = body.model_dump(exclude_none=True)
            if "rrule" in werte and not recurrence.ist_gueltig(werte["rrule"].strip()):
                return JSONResponse({"error": "Ungültige Wiederholungsregel"}, status_code=400)
            if "positionen" in werte:
                werte["positionen"] = json.dumps(
                    [{"beschreibung": p.get("beschreibung", ""), "menge": float(p.get("menge", 1)),
                      "einzelpreis_cent": max(0, int(p.get("einzelpreis_cent", 0))),
                      "ust_satz": int(p.get("ust_satz", 19))} for p in werte["positionen"]],
                    ensure_ascii=False)
            if "faellig_tage" in werte:
                werte["faellig_tage"] = max(0, int(werte["faellig_tage"]))
            if "aktiv" in werte:
                werte["aktiv"] = int(bool(werte["aktiv"]))
            self._patch("rechnung_abo", user.user_id, aid, werte)
            return {"ok": True, "id": aid}

        @r.delete("/api/rechnung-abos/{aid}")
        def abo_loeschen(aid: str, user: UserContext = Depends(current_user)):
            if not self._soft_delete("rechnung_abo", user.user_id, aid):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return {"ok": True, "id": aid}

        @r.post("/api/rechnung-abos/{aid}/ausfuehren")
        def abo_ausfuehren_ep(aid: str, force: int = 0,
                              user: UserContext = Depends(current_user)):
            """Zieht aus diesem Abo eine Entwurfs-Rechnung + rückt den Lauf vor.
            ``force=1`` ignoriert die Fälligkeit (sofort ziehen)."""
            try:
                return self.abo_ausfuehren(user.user_id, aid, force=force in (1, "1"))
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=404)

        # ===== EÜR-Sicht (Einnahmen-Überschuss, licht) =====================
        @r.get("/api/euer")
        def euer(jahr: int = 0, user: UserContext = Depends(current_user)):
            return self.euer(user.user_id, jahr or date.today().year)

        @r.get("/api/euer/export", response_class=PlainTextResponse)
        def euer_export(jahr: int = 0, user: UserContext = Depends(current_user)):
            e = self.euer(user.user_id, jahr or date.today().year)
            buf = io.StringIO()
            w = csv.writer(buf, delimiter=";")
            w.writerow(["EINNAHMEN (bezahlte Rechnungen)"])
            w.writerow(["nummer", "datum", "kunde_id", "netto_eur", "ust_eur", "brutto_eur", "status"])
            for z in e["belege"]:
                # Felder sind kontrolliert (generierte Nr./UUID/Enum) ⇒ defensiv csv_safe
                # gegen Formel-Injection, falls künftig ein Freitext (z. B. Kundenname) dazukommt.
                w.writerow([csv_safe(z["nummer"]), z["datum"], csv_safe(z["kunde_id"]),
                            f'{z["netto_cent"]/100:.2f}', f'{z["ust_cent"]/100:.2f}',
                            f'{z["brutto_cent"]/100:.2f}', csv_safe(z["status"])])
            # V16: Ausgabenseite (geschäftlich/steuer-relevant aus Dizz Money).
            w.writerow([])
            w.writerow(["AUSGABEN (geschaeftlich, aus Dizz Money)"
                        + ("" if e.get("ausgaben_ok") else " - gerade nicht abrufbar")])
            w.writerow(["kategorie", "steuer_art", "ausgaben_eur"])
            for k in e.get("ausgaben_je_kategorie", []):
                # kategorie/steuer_art = Freitext aus Money ⇒ csv_safe (Export geht ans Finanzamt).
                w.writerow([csv_safe(k.get("kategorie", "")), csv_safe(k.get("steuer_art", "")),
                            f'{int(k.get("ausgaben_cent", 0))/100:.2f}'])
            # V16/(b): informative Money-Einnahmen (steuer-relevant) — bewusst NICHT in der
            # Summe (Doppelzählung mit den eigenen Rechnungen vermeiden), nur zum Abgleich.
            if e.get("money_einnahmen_je_kategorie"):
                w.writerow([])
                w.writerow(["MONEY-EINNAHMEN (steuer-relevant, informativ - NICHT in der Summe)"])
                w.writerow(["kategorie", "steuer_art", "einnahmen_eur"])
                for k in e.get("money_einnahmen_je_kategorie", []):
                    w.writerow([csv_safe(k.get("kategorie", "")), csv_safe(k.get("steuer_art", "")),
                                f'{int(k.get("einnahmen_cent", 0))/100:.2f}'])
            w.writerow([])
            w.writerow(["SUMME", "Einnahmen_netto_eur (eigene Rechnungen)", f'{e["einnahmen_netto_cent"]/100:.2f}'])
            w.writerow(["SUMME", "Ausgaben_eur", f'{e.get("ausgaben_cent", 0)/100:.2f}'])
            w.writerow(["SUMME", "Ueberschuss_eur", f'{e.get("ueberschuss_cent", e["einnahmen_netto_cent"])/100:.2f}'])
            return PlainTextResponse(buf.getvalue(), media_type="text/csv")

        # ===== Fristen + Wächter ===========================================
        @r.get("/api/fristen")
        def fristen_liste(offen: int = -1, bereich_id: str | None = None,
                          user: UserContext = Depends(current_user)):
            q = "SELECT * FROM fristen WHERE user_id=? AND deleted_at IS NULL"
            p: list[Any] = [user.user_id]
            if offen == 1:
                q += " AND erledigt=0"
            if bereich_id is not None:           # None=alle · ''=nur „Allgemein" · id=Bereich
                q += " AND bereich_id=?"; p.append(bereich_id)
            rows = db.get_conn().execute(q + " ORDER BY faellig_am", p).fetchall()
            return [dict(x) for x in rows]

        @r.post("/api/fristen")
        def frist_anlegen(body: FristIn, user: UserContext = Depends(current_user)):
            if not body.titel.strip():
                return JSONResponse({"error": "Titel fehlt"}, status_code=400)
            fid = new_id(); ts = now_iso()
            db.get_conn().execute(
                "INSERT INTO fristen (id,user_id,titel,kategorie,faellig_am,notiz,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (fid, user.user_id, body.titel.strip(), _in(body.kategorie, FRIST_KATEGORIE, "sonstiges"),
                 body.faellig_am, body.notiz, ts, ts))
            db.get_conn().commit()
            return {"ok": True, "id": fid}

        @r.put("/api/fristen/{fid}")
        def frist_aendern(fid: str, body: FristPatch, user: UserContext = Depends(current_user)):
            if self._row("fristen", user.user_id, fid) is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            werte = body.model_dump(exclude_none=True)
            if "kategorie" in werte:
                werte["kategorie"] = _in(werte["kategorie"], FRIST_KATEGORIE, "sonstiges")
            if "erledigt" in werte:
                werte["erledigt"] = int(bool(werte["erledigt"]))
            self._patch("fristen", user.user_id, fid, werte)
            return {"ok": True, "id": fid}

        @r.delete("/api/fristen/{fid}")
        def frist_loeschen(fid: str, user: UserContext = Depends(current_user)):
            if not self._soft_delete("fristen", user.user_id, fid):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return {"ok": True, "id": fid}

        @r.get("/api/waechter")
        def waechter(user: UserContext = Depends(current_user)):
            """Frist-Wächter (deterministisch): überfällige offene Rechnungen +
            fällige/überfällige Fristen — Grundlage für KI-Hinweise + Glocke (HITL)."""
            return self.frist_waechter(user.user_id)

        # ===== Support =====================================================
        @r.get("/api/support")
        def support_liste(status: str = "", bereich_id: str | None = None,
                          user: UserContext = Depends(current_user)):
            q = "SELECT * FROM support WHERE user_id=? AND deleted_at IS NULL"
            p: list[Any] = [user.user_id]
            if status in SUPPORT_STATUS:
                q += " AND status=?"; p.append(status)
            if bereich_id is not None:           # None=alle · ''=nur „Allgemein" · id=Bereich
                q += " AND bereich_id=?"; p.append(bereich_id)
            rows = db.get_conn().execute(q + " ORDER BY created_at DESC", p).fetchall()
            return [dict(x) for x in rows]

        @r.post("/api/support")
        def support_anlegen(body: SupportIn, user: UserContext = Depends(current_user)):
            if not body.betreff.strip():
                return JSONResponse({"error": "Betreff fehlt"}, status_code=400)
            sid = new_id(); ts = now_iso()
            db.get_conn().execute(
                "INSERT INTO support (id,user_id,kunde_id,betreff,prioritaet,notiz,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (sid, user.user_id, body.kunde_id, body.betreff.strip(),
                 _in(body.prioritaet, SUPPORT_PRIO, "normal"), body.notiz, ts, ts))
            db.get_conn().commit()
            return {"ok": True, "id": sid}

        @r.put("/api/support/{sid}")
        def support_aendern(sid: str, body: SupportPatch, user: UserContext = Depends(current_user)):
            if self._row("support", user.user_id, sid) is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            werte = body.model_dump(exclude_none=True)
            if "status" in werte:
                werte["status"] = _in(werte["status"], SUPPORT_STATUS, "offen")
            if "prioritaet" in werte:
                werte["prioritaet"] = _in(werte["prioritaet"], SUPPORT_PRIO, "normal")
            self._patch("support", user.user_id, sid, werte)
            return {"ok": True, "id": sid}

        @r.delete("/api/support/{sid}")
        def support_loeschen(sid: str, user: UserContext = Depends(current_user)):
            if not self._soft_delete("support", user.user_id, sid):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return {"ok": True, "id": sid}

        # ===== KPIs ========================================================
        @r.get("/api/stats")
        def stats_endpoint(user: UserContext = Depends(current_user)):
            return self.stats(user.user_id)

        @r.get("/api/kpi/verlauf")
        def kpi_verlauf_endpoint(tage: int = 30, user: UserContext = Depends(current_user)):
            """KPI-Kopfleiste (P1c): Ist-Werte + Trend + Sparklines + MRR-Zerlegung."""
            return self.kpi_verlauf(user.user_id, max(1, min(int(tage), 365)))

        # ===== Studienverwaltung (P-Stud-1) ================================
        # WICHTIG: Literal-Routen (uebersicht/warnungen) VOR `/api/studien/{bw}`,
        # sonst fängt {bw} sie ab (Starlette matcht in Deklarations-Reihenfolge).
        @r.get("/api/studien/uebersicht")
        def studien_uebersicht_ep(user: UserContext = Depends(current_user)):
            return self.studien_uebersicht(user.user_id)

        @r.get("/api/studien/warnungen")
        def studien_warnungen_ep(user: UserContext = Depends(current_user)):
            return {"warnungen": self.studien_warnungen(user.user_id)}

        @r.get("/api/studienfristen")
        def studienfristen_alle_ep(user: UserContext = Depends(current_user)):
            """Alle offenen Studien-Fristen über alle Bildungswege (MCP/Übersicht)."""
            return self.studienfristen_offen(user.user_id)

        @r.get("/api/studien")
        def studien_liste(status: str = "", bereich_id: str | None = None,
                          user: UserContext = Depends(current_user)):
            q = "SELECT * FROM bildungsweg WHERE user_id=? AND deleted_at IS NULL"
            p: list[Any] = [user.user_id]
            if status in BILDUNGSWEG_STATUS:
                q += " AND status=?"; p.append(status)
            if bereich_id is not None:           # None=alle · ''=nur „Allgemein" · id=Bereich
                q += " AND bereich_id=?"; p.append(bereich_id)
            rows = db.get_conn().execute(q + " ORDER BY created_at DESC", p).fetchall()
            return [self._bildungsweg_kurz(user.user_id, x) for x in rows]

        @r.post("/api/studien")
        def studien_anlegen(body: BildungswegIn, user: UserContext = Depends(current_user)):
            if not (body.institution.strip() or body.studiengang.strip()):
                return JSONResponse({"error": "Institution oder Studiengang angeben"}, status_code=400)
            bid = new_id(); ts = now_iso()
            db.get_conn().execute(
                "INSERT INTO bildungsweg (id,user_id,art,institution,abschluss,studiengang,hauptfach,"
                "nebenfach,matrikelnr,po_version,start_semester,regelstudienzeit,ects_gesamt,max_versuche,"
                "kammer,betrieb,berufsschule,notiz,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (bid, user.user_id, _in(body.art, BILDUNGSWEG_ART, "universitaet"), body.institution.strip(),
                 _in(body.abschluss, ABSCHLUSS_ART, ""), body.studiengang.strip(), body.hauptfach, body.nebenfach,
                 body.matrikelnr, body.po_version, body.start_semester, max(0, int(body.regelstudienzeit)),
                 max(0, int(body.ects_gesamt)), max(1, int(body.max_versuche)), body.kammer, body.betrieb,
                 body.berufsschule, body.notiz, ts, ts))
            db.get_conn().commit()
            db.audit(user.user_id, "user", "bildungsweg_angelegt", {"id": bid})
            return {"ok": True, "id": bid}

        @r.get("/api/studien/{bw}")
        def studien_holen(bw: str, user: UserContext = Depends(current_user)):
            row = self._row("bildungsweg", user.user_id, bw)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return dict(row)

        @r.put("/api/studien/{bw}")
        def studien_aendern(bw: str, body: BildungswegPatch, user: UserContext = Depends(current_user)):
            if self._row("bildungsweg", user.user_id, bw) is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            werte = body.model_dump(exclude_none=True)
            if "art" in werte:
                werte["art"] = _in(werte["art"], BILDUNGSWEG_ART, "universitaet")
            if "abschluss" in werte:
                werte["abschluss"] = _in(werte["abschluss"], ABSCHLUSS_ART, "")
            if "status" in werte:
                werte["status"] = _in(werte["status"], BILDUNGSWEG_STATUS, "laufend")
            if "max_versuche" in werte:
                werte["max_versuche"] = max(1, int(werte["max_versuche"]))
            self._patch("bildungsweg", user.user_id, bw, werte)
            return {"ok": True, "id": bw}

        @r.delete("/api/studien/{bw}")
        def studien_loeschen(bw: str, user: UserContext = Depends(current_user)):
            if not self._soft_delete("bildungsweg", user.user_id, bw):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            conn = db.get_conn(); ts = now_iso()
            conn.execute("UPDATE studienmodul SET deleted_at=? WHERE bildungsweg_id=? AND user_id=? AND deleted_at IS NULL", (ts, bw, user.user_id))
            conn.execute("UPDATE studienfrist SET deleted_at=? WHERE bildungsweg_id=? AND user_id=? AND deleted_at IS NULL", (ts, bw, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "bildungsweg_geloescht", {"id": bw})
            return {"ok": True, "id": bw}

        @r.get("/api/studien/{bw}/cockpit")
        def studien_cockpit_ep(bw: str, user: UserContext = Depends(current_user)):
            row = self._row("bildungsweg", user.user_id, bw)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return self.studien_cockpit(user.user_id, dict(row))

        @r.get("/api/studien/{bw}/module")
        def module_liste(bw: str, bereich: str = "", status: str = "", user: UserContext = Depends(current_user)):
            q = "SELECT * FROM studienmodul WHERE user_id=? AND bildungsweg_id=? AND deleted_at IS NULL"
            p: list[Any] = [user.user_id, bw]
            if bereich in MODUL_BEREICH:
                q += " AND bereich=?"; p.append(bereich)
            if status in MODUL_STATUS:
                q += " AND status=?"; p.append(status)
            rows = db.get_conn().execute(q + " ORDER BY empf_semester, name", p).fetchall()
            return [dict(x) for x in rows]

        @r.post("/api/studien/{bw}/module")
        def modul_anlegen(bw: str, body: StudienmodulIn, user: UserContext = Depends(current_user)):
            if self._row("bildungsweg", user.user_id, bw) is None:
                return JSONResponse({"error": "Bildungsweg unbekannt"}, status_code=404)
            if not body.name.strip():
                return JSONResponse({"error": "Name fehlt"}, status_code=400)
            mid = new_id(); ts = now_iso()
            db.get_conn().execute(
                "INSERT INTO studienmodul (id,user_id,bildungsweg_id,code,name,typ,bereich,ects,empf_semester,"
                "pruefungsform,max_versuche,notiz,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, user.user_id, bw, body.code, body.name.strip(), _in(body.typ, MODUL_TYP, "pflicht"),
                 _in(body.bereich, MODUL_BEREICH, "hauptfach"), max(0, int(body.ects)), max(0, int(body.empf_semester)),
                 body.pruefungsform, max(0, int(body.max_versuche)), body.notiz, ts, ts))
            db.get_conn().commit()
            return {"ok": True, "id": mid}

        @r.put("/api/module/{mid}")
        def modul_aendern(mid: str, body: StudienmodulPatch, user: UserContext = Depends(current_user)):
            if self._row("studienmodul", user.user_id, mid) is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            werte = body.model_dump(exclude_none=True)
            if "typ" in werte:
                werte["typ"] = _in(werte["typ"], MODUL_TYP, "pflicht")
            if "bereich" in werte:
                werte["bereich"] = _in(werte["bereich"], MODUL_BEREICH, "hauptfach")
            if "status" in werte:
                werte["status"] = _in(werte["status"], MODUL_STATUS, "offen")
            self._patch("studienmodul", user.user_id, mid, werte)
            return {"ok": True, "id": mid}

        @r.delete("/api/module/{mid}")
        def modul_loeschen(mid: str, user: UserContext = Depends(current_user)):
            if not self._soft_delete("studienmodul", user.user_id, mid):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return {"ok": True, "id": mid}

        @r.post("/api/module/{mid}/ergebnis")
        def modul_ergebnis(mid: str, body: ModulErgebnisIn, user: UserContext = Depends(current_user)):
            row = self._row("studienmodul", user.user_id, mid)
            if row is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return self.modul_ergebnis_verbuchen(user.user_id, dict(row), body)

        @r.get("/api/studien/{bw}/fristen")
        def studienfristen_liste(bw: str, offen: int = -1, user: UserContext = Depends(current_user)):
            q = "SELECT * FROM studienfrist WHERE user_id=? AND bildungsweg_id=? AND deleted_at IS NULL"
            p: list[Any] = [user.user_id, bw]
            if offen == 1:
                q += " AND erledigt=0"
            rows = db.get_conn().execute(q + " ORDER BY faellig_am", p).fetchall()
            return [dict(x) for x in rows]

        @r.post("/api/studien/{bw}/fristen")
        def studienfrist_anlegen(bw: str, body: StudienfristIn, user: UserContext = Depends(current_user)):
            if self._row("bildungsweg", user.user_id, bw) is None:
                return JSONResponse({"error": "Bildungsweg unbekannt"}, status_code=404)
            if not body.titel.strip():
                return JSONResponse({"error": "Titel fehlt"}, status_code=400)
            fid = new_id(); ts = now_iso()
            db.get_conn().execute(
                "INSERT INTO studienfrist (id,user_id,bildungsweg_id,modul_id,titel,art,faellig_am,notiz,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (fid, user.user_id, bw, body.modul_id, body.titel.strip(),
                 _in(body.art, STUDIENFRIST_ART, "sonstiges"), body.faellig_am, body.notiz, ts, ts))
            db.get_conn().commit()
            return {"ok": True, "id": fid}

        @r.put("/api/studienfristen/{fid}")
        def studienfrist_aendern(fid: str, body: StudienfristPatch, user: UserContext = Depends(current_user)):
            if self._row("studienfrist", user.user_id, fid) is None:
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            werte = body.model_dump(exclude_none=True)
            if "art" in werte:
                werte["art"] = _in(werte["art"], STUDIENFRIST_ART, "sonstiges")
            if "erledigt" in werte:
                werte["erledigt"] = int(bool(werte["erledigt"]))
            self._patch("studienfrist", user.user_id, fid, werte)
            return {"ok": True, "id": fid}

        @r.delete("/api/studienfristen/{fid}")
        def studienfrist_loeschen(fid: str, user: UserContext = Depends(current_user)):
            if not self._soft_delete("studienfrist", user.user_id, fid):
                return JSONResponse({"error": "unbekannt"}, status_code=404)
            return {"ok": True, "id": fid}

        return r

    # --- interne Schreibhelfer ---------------------------------------------
    def _patch(self, tabelle: str, user_id: str, rid: str, werte: dict[str, Any]) -> None:
        if not werte:
            return
        sets = ", ".join(f"{k}=?" for k in werte) + ", updated_at=?"
        params = list(werte.values()) + [now_iso(), rid, user_id]
        conn = self.db.get_conn()
        conn.execute(f"UPDATE {tabelle} SET {sets} WHERE id=? AND user_id=?", params)
        conn.commit()

    def _positionen_schreiben(self, user_id: str, rechnung_id: str,
                              positionen: list[PositionIn]) -> None:
        conn = self.db.get_conn()
        for p in positionen:
            ts = now_iso()
            conn.execute(
                "INSERT INTO rechnung_positionen (id,user_id,rechnung_id,beschreibung,menge,"
                "einzelpreis_cent,ust_satz,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (new_id(), user_id, rechnung_id, p.beschreibung, float(p.menge),
                 max(0, int(p.einzelpreis_cent)), int(p.ust_satz), ts, ts))

    def _naechste_nummer(self, user_id: str) -> str:
        """Lückenlose Rechnungsnummer je Jahr: ``YYYY-NNNN``."""
        jahr = date.today().year
        n = self.db.get_conn().execute(
            "SELECT COUNT(*) AS n FROM rechnungen WHERE user_id=? AND nummer LIKE ?",
            (user_id, f"{jahr}-%")).fetchone()["n"]
        return f"{jahr}-{n + 1:04d}"

    # --- Mahnwesen (A8) — eigene Entität, Rechnung bleibt unangetastet -------
    def _hoechste_stufe(self, user_id: str, rechnung_id: str) -> int:
        """Höchste bereits vergebene Mahnstufe einer Rechnung (0 = noch keine)."""
        row = self.db.get_conn().execute(
            "SELECT COALESCE(MAX(stufe),0) AS s FROM mahnungen "
            "WHERE user_id=? AND rechnung_id=? AND deleted_at IS NULL",
            (user_id, rechnung_id)).fetchone()
        return int(row["s"] or 0)

    def _mahn_dict(self, row) -> dict[str, Any]:
        d = {k: row[k] for k in ("id", "rechnung_id", "stufe", "titel", "frist_am",
                                 "gebuehr_cent", "status", "notiz", "created_at")}
        # Rechnungs-Kontext (read-only), falls die Query ihn mitliefert.
        for k in ("nummer", "kunde_id", "brutto_cent", "rechnung_status"):
            if k in row.keys():
                d[k] = row[k]
        return d

    def mahnungen_liste(self, user_id: str, *, rechnung_id: str = "",
                        status: str = "") -> list[dict[str, Any]]:
        q = ("SELECT m.*, r.nummer AS nummer, r.kunde_id AS kunde_id, "
             "r.brutto_cent AS brutto_cent, r.status AS rechnung_status "
             "FROM mahnungen m LEFT JOIN rechnungen r ON r.id=m.rechnung_id "
             "WHERE m.user_id=? AND m.deleted_at IS NULL")
        p: list[Any] = [user_id]
        if rechnung_id:
            q += " AND m.rechnung_id=?"; p.append(rechnung_id)
        if status in MAHN_STATUS:
            q += " AND m.status=?"; p.append(status)
        rows = self.db.get_conn().execute(q + " ORDER BY m.created_at DESC", p).fetchall()
        return [self._mahn_dict(r) for r in rows]

    def mahn_vorschlaege(self, user_id: str) -> list[dict[str, Any]]:
        """Deterministischer Vorschlag: welche überfällige offene Rechnung braucht
        (eine erste / die nächste) Mahnstufe? Eskaliert erst, wenn auch die Frist der
        letzten Mahnung verstrichen ist. Reine Lese-Analyse — legt nichts an (HITL)."""
        heute = heute_iso()
        conn = self.db.get_conn()
        offene = conn.execute(
            "SELECT id, nummer, kunde_id, brutto_cent, faellig_am FROM rechnungen "
            "WHERE user_id=? AND status='offen' AND faellig_am<>'' AND faellig_am<? "
            "AND deleted_at IS NULL ORDER BY faellig_am", (user_id, heute)).fetchall()
        out: list[dict[str, Any]] = []
        for r in offene:
            stufe = self._hoechste_stufe(user_id, r["id"])
            if stufe >= MAHN_MAX_STUFE:
                continue                         # bereits maximal gemahnt
            if stufe > 0:
                # Es gibt schon eine Mahnung — erst eskalieren, wenn deren Frist um ist.
                letzte = conn.execute(
                    "SELECT frist_am FROM mahnungen WHERE user_id=? AND rechnung_id=? "
                    "AND stufe=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1",
                    (user_id, r["id"], stufe)).fetchone()
                if letzte and letzte["frist_am"] and letzte["frist_am"] >= heute:
                    continue                     # Mahnfrist läuft noch
            naechste = stufe + 1
            out.append({
                "rechnung_id": r["id"], "nummer": r["nummer"], "kunde_id": r["kunde_id"],
                "brutto_cent": r["brutto_cent"], "faellig_am": r["faellig_am"],
                "vorhandene_stufe": stufe, "naechste_stufe": naechste,
                "label": MAHN_STUFEN[naechste]["label"],
                "gebuehr_cent": MAHN_STUFEN[naechste]["gebuehr_cent"]})
        return out

    def neue_mahnung(self, user_id: str, *, rechnung_id: str, stufe: int | None = None,
                     frist_am: str = "", gebuehr_cent: int | None = None,
                     titel: str = "", notiz: str = "") -> dict[str, Any]:
        """Legt eine Mahnung zu einer offenen (gestellten, unbezahlten) Rechnung an.
        Ändert die Rechnung NICHT (GoBD). Stufe leer ⇒ nächste Stufe; Frist/Gebühr
        leer ⇒ Standard der Stufe. Wirft ValueError bei ungültigem Zustand."""
        r = self._row("rechnungen", user_id, rechnung_id)
        if r is None:
            raise ValueError("Rechnung unbekannt.")
        if r["status"] != "offen":
            raise ValueError("Nur eine gestellte, offene Rechnung kann gemahnt werden.")
        if stufe is None:
            stufe = min(self._hoechste_stufe(user_id, rechnung_id) + 1, MAHN_MAX_STUFE)
        stufe = max(1, min(int(stufe), MAHN_MAX_STUFE))
        cfg = MAHN_STUFEN[stufe]
        if not (frist_am or "").strip():
            frist_am = (date.today() + timedelta(days=cfg["frist_tage"])).isoformat()
        if gebuehr_cent is None:
            gebuehr_cent = cfg["gebuehr_cent"]
        gebuehr_cent = max(0, int(gebuehr_cent))
        nummer = r["nummer"] or rechnung_id[:8]
        titel = (titel or "").strip() or f"{cfg['label']} zu Rechnung {nummer}"
        mid = new_id(); ts = now_iso()
        self.db.get_conn().execute(
            "INSERT INTO mahnungen (id,user_id,rechnung_id,stufe,titel,frist_am,gebuehr_cent,"
            "status,notiz,created_at,updated_at) VALUES (?,?,?,?,?,?,?, 'offen', ?,?,?)",
            (mid, user_id, rechnung_id, stufe, titel, frist_am.strip(), gebuehr_cent,
             notiz.strip(), ts, ts))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "mahnung_erstellt",
                      {"id": mid, "rechnung_id": rechnung_id, "stufe": stufe})
        return {"ok": True, "id": mid, "stufe": stufe, "frist_am": frist_am,
                "gebuehr_cent": gebuehr_cent, "titel": titel}

    def schliesse_mahnungen(self, user_id: str, rechnung_id: str) -> int:
        """Offene Mahnungen einer Rechnung auf 'erledigt' setzen (wenn die Rechnung
        bezahlt/storniert wird). Berührt nur die Mahn-Entität, nie die Rechnung."""
        conn = self.db.get_conn()
        cur = conn.execute(
            "UPDATE mahnungen SET status='erledigt', updated_at=? "
            "WHERE user_id=? AND rechnung_id=? AND status='offen' AND deleted_at IS NULL",
            (now_iso(), user_id, rechnung_id))
        conn.commit()
        return cur.rowcount

    # --- Wiederkehrende Rechnungen / Abos (A6) ------------------------------
    @staticmethod
    def _abo_public(row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["positionen"] = json.loads(row["positionen"] or "[]")
        except (ValueError, TypeError):
            d["positionen"] = []
        d["aktiv"] = bool(row["aktiv"])
        d.pop("deleted_at", None)
        return d

    def abo_liste(self, user_id: str, *, aktiv: int = -1,
                  bereich_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM rechnung_abo WHERE user_id=? AND deleted_at IS NULL"
        p: list[Any] = [user_id]
        if aktiv in (0, 1):
            q += " AND aktiv=?"; p.append(aktiv)
        if bereich_id is not None:
            q += " AND bereich_id=?"; p.append(bereich_id)
        rows = self.db.get_conn().execute(q + " ORDER BY created_at DESC", p).fetchall()
        return [self._abo_public(r) for r in rows]

    def neue_abo(self, user_id: str, body: "RechnungAboIn") -> dict[str, Any]:
        if not recurrence.ist_gueltig((body.rrule or "").strip()):
            raise ValueError("Ungültige Wiederholungsregel (FREQ=DAILY|WEEKLY|MONTHLY).")
        if not body.positionen:
            raise ValueError("Abo ohne Positionen.")
        pos = [{"beschreibung": p.beschreibung, "menge": float(p.menge),
                "einzelpreis_cent": max(0, int(p.einzelpreis_cent)), "ust_satz": int(p.ust_satz)}
               for p in body.positionen]
        aid = new_id(); ts = now_iso()
        lauf = (body.naechster_lauf or "").strip() or heute_iso()
        self.db.get_conn().execute(
            "INSERT INTO rechnung_abo (id,user_id,kunde_id,titel,rrule,positionen,faellig_tage,"
            "naechster_lauf,aktiv,bereich_id,notiz,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, user_id, body.kunde_id, (body.titel or "").strip(), (body.rrule or "").strip(),
             json.dumps(pos, ensure_ascii=False), max(0, int(body.faellig_tage)), lauf,
             1 if body.aktiv else 0, body.bereich_id, (body.notiz or "").strip(), ts, ts))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "abo_angelegt", {"id": aid, "rrule": body.rrule})
        return {"ok": True, "id": aid, "naechster_lauf": lauf}

    def abo_faellig(self, user_id: str) -> list[dict[str, Any]]:
        """Aktive Abos, deren nächster Lauf erreicht ist (read-only Vorschau)."""
        heute = heute_iso()
        rows = self.db.get_conn().execute(
            "SELECT * FROM rechnung_abo WHERE user_id=? AND aktiv=1 AND deleted_at IS NULL "
            "AND naechster_lauf<>'' AND naechster_lauf<=? ORDER BY naechster_lauf",
            (user_id, heute)).fetchall()
        return [self._abo_public(r) for r in rows]

    def abo_ausfuehren(self, user_id: str, abo_id: str, *, force: bool = False) -> dict[str, Any]:
        """Erzeugt aus dem Abo EINE Entwurfs-Rechnung (Plan→Ist) und rückt den
        nächsten Lauf deterministisch vor (RRULE-light). GoBD: Entwurf, Nummer erst
        beim Stellen. Idempotent: ohne ``force`` nur, wenn der Lauf wirklich fällig
        ist (verhindert Doppel-Ziehung in derselben Periode)."""
        abo = self._row("rechnung_abo", user_id, abo_id)
        if abo is None:
            raise ValueError("Abo unbekannt.")
        heute = heute_iso()
        lauf = (abo["naechster_lauf"] or "").strip() or heute
        if not force and lauf > heute:
            return {"ok": True, "status": "nicht_faellig", "naechster_lauf": lauf}
        if not abo["aktiv"] and not force:
            return {"ok": True, "status": "inaktiv"}
        try:
            positionen = [PositionIn(**p) for p in json.loads(abo["positionen"] or "[]")]
        except (ValueError, TypeError):
            positionen = []
        if not positionen:
            raise ValueError("Abo ohne Positionen.")
        rid = new_id(); ts = now_iso()
        faellig_am = (date.today() + timedelta(days=max(0, int(abo["faellig_tage"])))).isoformat()
        titel = (abo["titel"] or "").strip() or "Abo-Rechnung"
        notiz = (abo["notiz"] or "").strip()
        notiz = (notiz + "\n\n" if notiz else "") + f"Aus Abo {abo_id} (Lauf {lauf})."
        conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO rechnungen (id,user_id,kunde_id,titel,faellig_am,notiz,status,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?, 'entwurf', ?,?)",
            (rid, user_id, abo["kunde_id"], titel, faellig_am, notiz, ts, ts))
        self._positionen_schreiben(user_id, rid, positionen)
        bereich_id = abo["bereich_id"] if "bereich_id" in abo.keys() else ""
        if bereich_id:                          # Bereichs-Achse der Vorlage übernehmen
            conn.execute("UPDATE rechnungen SET bereich_id=? WHERE id=? AND user_id=?",
                         (bereich_id, rid, user_id))
        naechster = recurrence.naechste_faellig((abo["rrule"] or "").strip(), lauf)
        felder: dict[str, Any] = {"letzter_lauf": lauf, "updated_at": ts}
        if naechster:
            felder["naechster_lauf"] = naechster
        else:                                   # Serie erschöpft (UNTIL) ⇒ Abo schläft ein
            felder["aktiv"] = 0
        sets = ", ".join(f"{k}=?" for k in felder)
        conn.execute(f"UPDATE rechnung_abo SET {sets} WHERE id=? AND user_id=?",
                     [*felder.values(), abo_id, user_id])
        conn.commit()
        self.db.audit(user_id, "user", "abo_rechnung_erzeugt",
                      {"abo_id": abo_id, "rechnung_id": rid, "lauf": lauf})
        return {"ok": True, "status": "erzeugt", "rechnung_id": rid, "lauf": lauf,
                "naechster_lauf": naechster, "faellig_am": faellig_am}

    def abo_lauf(self, user_id: str) -> dict[str, Any]:
        """Stellt ALLE fälligen Abos auf einmal (Entwürfe). HITL-Sammelaktion."""
        erzeugt = []
        for a in self.abo_faellig(user_id):
            res = self.abo_ausfuehren(user_id, a["id"])
            if res.get("status") == "erzeugt":
                erzeugt.append({"abo_id": a["id"], "rechnung_id": res["rechnung_id"],
                                "naechster_lauf": res["naechster_lauf"]})
        return {"ok": True, "erzeugt": erzeugt, "anzahl": len(erzeugt)}

    def abo_vorschlaege(self, user_id: str) -> list[dict[str, Any]]:
        """Erkennung/Anlage-Hilfe: aktive Abo-Produkte (monatlich/jährlich) als
        fertige Abo-Vorlagen vorschlagen — der Nutzer legt daraus per Klick ein Abo an."""
        rows = self.db.get_conn().execute(
            "SELECT id, name, preis_cent, abo_intervall FROM produkte WHERE user_id=? AND aktiv=1 "
            "AND abo_intervall IN ('monatlich','jaehrlich') AND deleted_at IS NULL", (user_id,)).fetchall()
        out = []
        for p in rows:
            rrule = "FREQ=MONTHLY" if p["abo_intervall"] == "monatlich" else "FREQ=MONTHLY;INTERVAL=12"
            out.append({"produkt_id": p["id"], "name": p["name"],
                        "abo_intervall": p["abo_intervall"], "rrule": rrule,
                        "titel": p["name"],
                        "positionen": [{"beschreibung": p["name"], "menge": 1,
                                        "einzelpreis_cent": p["preis_cent"], "ust_satz": 19}]})
        return out

    # --- Kennzahlen ---------------------------------------------------------
    def stats(self, user_id: str = "dizzi") -> dict[str, Any]:
        conn = self.db.get_conn()
        heute = heute_iso()

        def _one(sql: str, *p) -> int:
            return conn.execute(sql, (user_id, *p)).fetchone()[0] or 0

        kunden_n = _one("SELECT COUNT(*) FROM kunden WHERE user_id=? AND deleted_at IS NULL")
        offen_n = _one("SELECT COUNT(*) FROM rechnungen WHERE user_id=? AND status='offen' AND deleted_at IS NULL")
        offen_cent = _one("SELECT COALESCE(SUM(brutto_cent),0) FROM rechnungen WHERE user_id=? AND status='offen' AND deleted_at IS NULL")
        umsatz_cent = _one("SELECT COALESCE(SUM(brutto_cent),0) FROM rechnungen WHERE user_id=? AND status='bezahlt' AND deleted_at IS NULL")
        ueberfaellig_n = _one(
            "SELECT COUNT(*) FROM rechnungen WHERE user_id=? AND status='offen' "
            "AND faellig_am<>'' AND faellig_am<? AND deleted_at IS NULL", heute)
        support_offen = _one("SELECT COUNT(*) FROM support WHERE user_id=? AND status<>'geschlossen' AND deleted_at IS NULL")
        mahnungen_offen = _one("SELECT COUNT(*) FROM mahnungen WHERE user_id=? AND status='offen' AND deleted_at IS NULL")
        fristen_offen = _one("SELECT COUNT(*) FROM fristen WHERE user_id=? AND erledigt=0 AND deleted_at IS NULL")
        fristen_faellig = _one(
            "SELECT COUNT(*) FROM fristen WHERE user_id=? AND erledigt=0 "
            "AND faellig_am<>'' AND faellig_am<=? AND deleted_at IS NULL", heute)
        # MRR aus aktiven Abo-Produkten (per-Produkt-Beitrag — Basis der Zerlegung)
        mrr_cent = sum(self._mrr_posten(user_id).values())
        return {
            "kunden": kunden_n,
            "offene_rechnungen": offen_n, "offene_rechnungen_cent": offen_cent,
            "ueberfaellige_rechnungen": ueberfaellig_n,
            "umsatz_bezahlt_cent": umsatz_cent, "mrr_cent": mrr_cent,
            "support_offen": support_offen, "offene_mahnungen": mahnungen_offen,
            "fristen_offen": fristen_offen, "fristen_faellig": fristen_faellig,
        }

    def _mrr_posten(self, user_id: str = "dizzi") -> dict[str, int]:
        """Live: {produkt_id: mrr_cent} der aktiven Abo-Produkte (monatlich = Preis;
        jährlich = Preis/12). Basis für MRR-Summe UND die MRR-Zerlegung."""
        posten: dict[str, int] = {}
        for p in self.db.get_conn().execute(
                "SELECT id, preis_cent, abo_intervall FROM produkte WHERE user_id=? AND aktiv=1 "
                "AND deleted_at IS NULL", (user_id,)).fetchall():
            if p["abo_intervall"] == "monatlich":
                posten[p["id"]] = int(p["preis_cent"])
            elif p["abo_intervall"] == "jaehrlich":
                posten[p["id"]] = round(int(p["preis_cent"]) / 12)
        return posten

    # --- KPI-Verlauf: Snapshot + Trend + MRR-Zerlegung (UI/UX P1c) ----------
    def snapshot_now(self, user_id: str = "dizzi") -> None:
        """Schreibt/aktualisiert den heutigen KPI-Snapshot (idempotent je Tag, Upsert).
        Lazy beim Lesen aufgerufen ⇒ die Historie wächst durch normale Nutzung, ohne
        Scheduler. Reine Analytik aus bereits vorhandenen Daten — nichts Fachliches."""
        s = self.stats(user_id)
        posten = self._mrr_posten(user_id)
        ts = now_iso()
        self.db.get_conn().execute(
            """INSERT INTO kpi_snapshot
                 (id,user_id,datum,umsatz_cent,mrr_cent,offen_cent,offen_n,ueberfaellig_n,
                  kunden_n,mrr_posten,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (user_id,datum) DO UPDATE SET
                 umsatz_cent=excluded.umsatz_cent, mrr_cent=excluded.mrr_cent,
                 offen_cent=excluded.offen_cent, offen_n=excluded.offen_n,
                 ueberfaellig_n=excluded.ueberfaellig_n, kunden_n=excluded.kunden_n,
                 mrr_posten=excluded.mrr_posten, updated_at=excluded.updated_at, deleted_at=NULL""",
            (new_id(), user_id, heute_iso(), s["umsatz_bezahlt_cent"], s["mrr_cent"],
             s["offene_rechnungen_cent"], s["offene_rechnungen"], s["ueberfaellige_rechnungen"],
             s["kunden"], json.dumps(posten, separators=(",", ":")), ts, ts))
        self.db.get_conn().commit()

    def mrr_zerlegung(self, user_id: str, basis_row: dict[str, Any] | None) -> dict[str, Any]:
        """Zerlegt die MRR-Veränderung ggü. einem Basis-Snapshot in neu/Expansion/
        Contraction/Churn — deterministisch aus den per-Produkt-Posten. Ohne Basis-
        Historie ⇒ alle 0 + ``status='aufbauend'`` (ehrlich, bis Verlauf existiert)."""
        jetzt = self._mrr_posten(user_id)
        if not basis_row:
            return {"neu_cent": 0, "expansion_cent": 0, "contraction_cent": 0,
                    "churn_cent": 0, "netto_cent": 0, "basis_datum": None, "status": "aufbauend"}
        try:
            vorher = {k: int(v) for k, v in json.loads(basis_row.get("mrr_posten") or "{}").items()}
        except Exception:  # noqa: BLE001 — defekter JSON darf die Sicht nicht kippen
            vorher = {}
        neu = expansion = contraction = churn = 0
        for pid, v in jetzt.items():
            if pid not in vorher:
                neu += v
            else:
                d = v - vorher[pid]
                if d > 0:
                    expansion += d
                elif d < 0:
                    contraction += -d
        for pid, v in vorher.items():
            if pid not in jetzt:
                churn += v
        return {"neu_cent": neu, "expansion_cent": expansion, "contraction_cent": contraction,
                "churn_cent": churn, "netto_cent": neu + expansion - contraction - churn,
                "basis_datum": basis_row["datum"], "status": "ok"}

    def kpi_verlauf(self, user_id: str = "dizzi", tage: int = 30) -> dict[str, Any]:
        """KPI-Verlauf für die Kopfleiste: aktuelle Ist-Werte + Trend (ggü. Basis-
        Snapshot ~``tage`` zurück) + Sparkline-Reihen + MRR-Zerlegung. Stellt den
        heutigen Snapshot sicher (idempotent), damit die Historie mitwächst."""
        self.snapshot_now(user_id)
        rows = [dict(r) for r in self.db.get_conn().execute(
            "SELECT datum,umsatz_cent,mrr_cent,offen_cent,offen_n,ueberfaellig_n,kunden_n,mrr_posten "
            "FROM kpi_snapshot WHERE user_id=? AND deleted_at IS NULL ORDER BY datum",
            (user_id,)).fetchall()]
        ist = self.stats(user_id)
        # Basis = jüngster Snapshot, der mind. ``tage`` zurückliegt; sonst der älteste
        # Punkt VOR heute. Existiert nur der heutige Snapshot ⇒ keine Basis (Trend
        # „aufbauend"/flat, statt heute gegen heute zu vergleichen).
        heute = heute_iso()
        grenze = (date.today() - timedelta(days=max(1, tage))).isoformat()
        vergangene = [r for r in rows if r["datum"] < heute]
        aelter = [r for r in vergangene if r["datum"] <= grenze]
        basis = aelter[-1] if aelter else (vergangene[0] if vergangene else None)

        def _trend(ist_key: str, snap_key: str) -> dict[str, Any]:
            akt = ist[ist_key]
            if not basis:
                return {"wert": akt, "delta": None, "basis": None,
                        "basis_datum": None, "richtung": "flat"}
            vor = int(basis[snap_key])
            delta = akt - vor
            return {"wert": akt, "delta": delta, "basis": vor, "basis_datum": basis["datum"],
                    "richtung": "up" if delta > 0 else ("down" if delta < 0 else "flat")}

        return {
            "ist": ist,
            "trend": {  # richtung neutral (delta-Vorzeichen); gut/schlecht entscheidet die UI je Kennzahl
                "umsatz_cent": _trend("umsatz_bezahlt_cent", "umsatz_cent"),
                "mrr_cent": _trend("mrr_cent", "mrr_cent"),
                "offen_cent": _trend("offene_rechnungen_cent", "offen_cent"),
                "ueberfaellig_n": _trend("ueberfaellige_rechnungen", "ueberfaellig_n"),
                "kunden": _trend("kunden", "kunden_n"),
            },
            "verlauf": [{"datum": r["datum"], "umsatz_cent": r["umsatz_cent"],
                         "mrr_cent": r["mrr_cent"], "offen_cent": r["offen_cent"],
                         "ueberfaellig_n": r["ueberfaellig_n"]} for r in rows[-60:]],
            "mrr_zerlegung": self.mrr_zerlegung(user_id, basis),
            "tage": tage, "punkte": len(rows),
        }

    def summary(self) -> list[Kpi]:
        s = self.stats()
        return [
            Kpi(id="umsatz", label="Umsatz (bezahlt)", value=f'{s["umsatz_bezahlt_cent"]/100:,.0f} €'),
            Kpi(id="offen", label="Offene Rechnungen", value=s["offene_rechnungen"]),
            Kpi(id="kunden", label="Kunden", value=s["kunden"]),
            Kpi(id="mrr", label="MRR", value=f'{s["mrr_cent"]/100:,.0f} €'),
        ]

    def euer(self, user_id: str, jahr: int) -> dict[str, Any]:
        """EÜR-Sicht (licht): Einnahmen aus BEZAHLTEN Rechnungen des Jahres
        (Zufluss-Prinzip über ``bezahlt_am``) + **V16-Ausgabenseite**: die
        geschäftlichen (steuer-relevanten) Ausgaben aus Dizz Money — read-only über den
        Core-Relay (Aggregation statt Doppeln; ``ausgaben_reader``). Best-effort: ist
        Money/Core offline, bleibt die Ausgabenseite ehrlich leer (``ausgaben_ok=False``)
        und die EÜR zeigt nur die Einnahmen. KEIN Steuer-Filing — nur Aufstellung."""
        rows = self.db.get_conn().execute(
            "SELECT nummer,datum,bezahlt_am,kunde_id,netto_cent,ust_cent,brutto_cent,status "
            "FROM rechnungen WHERE user_id=? AND status='bezahlt' AND deleted_at IS NULL "
            "AND substr(bezahlt_am,1,4)=? ORDER BY bezahlt_am",
            (user_id, str(jahr))).fetchall()
        belege = [dict(x) for x in rows]
        einnahmen = sum(z["netto_cent"] for z in belege)
        ust = sum(z["ust_cent"] for z in belege)

        # V16: geschäftliche Ausgaben (steuer-relevant) aus Dizz Money dazuholen; die
        # steuer-relevanten Money-EINNAHMEN reisen informativ mit (s. u.).
        ausg = {"ok": False, "ausgaben_cent": 0, "je_kategorie": [], "quelle": "finanzen",
                "einnahmen_cent": 0, "einnahmen_je_kategorie": []}
        if self.ausgaben_reader is not None:
            try:
                ausg = self.ausgaben_reader(jahr) or ausg
            except Exception:  # noqa: BLE001 — best-effort, EÜR bleibt nutzbar
                pass
        ausgaben_cent = int(ausg.get("ausgaben_cent", 0) or 0)
        quelle = ausg.get("quelle", "finanzen")
        return {"jahr": jahr, "einnahmen_netto_cent": einnahmen, "ust_cent": ust,
                "brutto_cent": einnahmen + ust, "anzahl": len(belege), "belege": belege,
                "ausgaben_cent": ausgaben_cent,
                "ausgaben_je_kategorie": ausg.get("je_kategorie", []),
                "ausgaben_quelle": quelle,
                "ausgaben_ok": bool(ausg.get("ok")),
                "ueberschuss_cent": einnahmen - ausgaben_cent,
                # V16/(b): explizite Quellen-Kennzeichnung — welche Seite kommt woher.
                "quellen": {"einnahmen": "Dizz Admin (bezahlte Rechnungen)",
                            "ausgaben": f"Dizz Money / {quelle} (steuer-relevant)"},
                # Money-steuer-relevante Einnahmen: INFORMATIV, NICHT in ueberschuss_cent
                # addiert (dieselben Erlöse stecken i. d. R. schon in den eigenen Rechnungen
                # ⇒ Doppelzählungs-Schutz; Abgleich-Darstellung = UI/UX-Phase §5d).
                "money_einnahmen_cent": int(ausg.get("einnahmen_cent", 0) or 0),
                "money_einnahmen_je_kategorie": ausg.get("einnahmen_je_kategorie", []),
                "hinweis": ("EÜR-Aufstellung: Einnahmen = bezahlte eigene Rechnungen (Zufluss), "
                            "Ausgaben = steuer-relevante Posten aus Dizz Money. Money meldet ggf. "
                            "zusätzlich steuer-relevante Einnahmen (informativ, nicht addiert — "
                            "Doppelzählung mit Rechnungen vermeiden). Keine Steuer-Erklärung."
                            if ausg.get("ok") else
                            "Einnahmen-Aufstellung (Zufluss, eigene Rechnungen). Ausgabenseite aus "
                            "Dizz Money gerade nicht abrufbar — nur Einnahmen gezeigt. Keine Steuer-Erklärung.")}

    def frist_waechter(self, user_id: str) -> dict[str, Any]:
        heute = heute_iso()
        rechnungen = [dict(x) for x in self.db.get_conn().execute(
            "SELECT id,nummer,kunde_id,brutto_cent,faellig_am FROM rechnungen "
            "WHERE user_id=? AND status='offen' AND faellig_am<>'' AND faellig_am<? "
            "AND deleted_at IS NULL ORDER BY faellig_am", (user_id, heute)).fetchall()]
        fristen = [dict(x) for x in self.db.get_conn().execute(
            "SELECT id,titel,kategorie,faellig_am FROM fristen WHERE user_id=? AND erledigt=0 "
            "AND faellig_am<>'' AND faellig_am<=? AND deleted_at IS NULL ORDER BY faellig_am",
            (user_id, heute)).fetchall()]
        # A8: fällige Mahn-Fristen (offene Mahnungen, deren Zahlungsziel erreicht ist).
        mahnungen = [dict(x) for x in self.db.get_conn().execute(
            "SELECT m.id, m.stufe, m.titel, m.frist_am, r.nummer AS nummer FROM mahnungen m "
            "LEFT JOIN rechnungen r ON r.id=m.rechnung_id WHERE m.user_id=? AND m.status='offen' "
            "AND m.frist_am<>'' AND m.frist_am<=? AND m.deleted_at IS NULL ORDER BY m.frist_am",
            (user_id, heute)).fetchall()]
        # P-Stud-1: fällige Studien-Fristen + Module im Prüfungsversuch-Risiko mitziehen.
        studienfristen = [dict(x) for x in self.db.get_conn().execute(
            "SELECT s.id,s.titel,s.art,s.faellig_am,s.bildungsweg_id FROM studienfrist s "
            "JOIN bildungsweg b ON b.id=s.bildungsweg_id "
            "WHERE s.user_id=? AND s.erledigt=0 AND s.faellig_am<>'' AND s.faellig_am<=? "
            "AND s.deleted_at IS NULL AND b.deleted_at IS NULL ORDER BY s.faellig_am",
            (user_id, heute)).fetchall()]
        studien_risiko = self.studien_warnungen(user_id)
        return {"ueberfaellige_rechnungen": rechnungen, "faellige_fristen": fristen,
                "faellige_mahnungen": mahnungen,
                "faellige_studienfristen": studienfristen, "studien_risiko": studien_risiko,
                "gesamt": len(rechnungen) + len(fristen) + len(mahnungen)
                + len(studienfristen) + len(studien_risiko)}

    # --- Studienverwaltung: Aggregate (P-Stud-1) ---------------------------
    @staticmethod
    def _effektiv_max(modul: dict[str, Any], default_max: int) -> int:
        mv = int(modul.get("max_versuche") or 0)
        return mv if mv > 0 else max(1, int(default_max or 3))

    @staticmethod
    def _semester_count(start_semester: str) -> int:
        """Best-effort Fachsemester aus 'WS2024'/'SS2025'/'WiSe 2024/25' bis heute
        (Semester-Index = Jahr*2 + 1 für WS, +0 für SS). 0 wenn nicht parsebar."""
        import re
        m = re.match(r"\s*(WS|WiSe|SS|SoSe)\s*([0-9]{2,4})", start_semester or "", re.I)
        if not m:
            return 0
        ist_ws = m.group(1).lower().startswith(("ws", "wi"))
        jahr = int(m.group(2))
        if jahr < 100:
            jahr += 2000
        start_idx = jahr * 2 + (1 if ist_ws else 0)
        t = date.today()
        if t.month >= 10:
            cur_idx = t.year * 2 + 1
        elif t.month <= 3:
            cur_idx = (t.year - 1) * 2 + 1
        else:
            cur_idx = t.year * 2
        return max(0, cur_idx - start_idx) + 1 if cur_idx >= start_idx else 0

    def modul_ergebnis_verbuchen(self, user_id: str, row: dict[str, Any],
                                 body: "ModulErgebnisIn") -> dict[str, Any]:
        """Verbucht einen Prüfungsversuch: erhöht ``versuch_nr``; setzt bei Bestehen
        Status/Note/ECTS, sonst ``nicht_bestanden`` bzw. — beim Erreichen des Maximums —
        ``endgueltig`` (endgültig nicht bestanden ⇒ Exmatrikulations-Risiko)."""
        bw = self._row("bildungsweg", user_id, row["bildungsweg_id"])
        default_max = int(bw["max_versuche"]) if bw else 3
        emax = self._effektiv_max(row, default_max)
        versuch = int(row["versuch_nr"]) + 1
        if body.bestanden:
            status = "bestanden"
            ects_err = body.ects_erreicht if body.ects_erreicht is not None else int(row["ects"])
        else:
            status = "endgueltig" if versuch >= emax else "nicht_bestanden"
            ects_err = 0
        self._patch("studienmodul", user_id, row["id"], {
            "status": status, "versuch_nr": versuch, "note": body.note,
            "ects_erreicht": max(0, int(ects_err or 0)), "abgelegt_am": heute_iso()})
        self.db.audit(user_id, "user", "modul_ergebnis",
                      {"id": row["id"], "status": status, "versuch_nr": versuch})
        return {"ok": True, "id": row["id"], "status": status, "versuch_nr": versuch,
                "max_versuche": emax, "endgueltig": status == "endgueltig"}

    def _bildungsweg_kurz(self, user_id: str, row) -> dict[str, Any]:
        d = dict(row)
        c = self.db.get_conn().execute(
            "SELECT COALESCE(SUM(CASE WHEN status IN ('bestanden','anerkannt') THEN ects_erreicht ELSE 0 END),0) AS erreicht, "
            "COUNT(*) AS module FROM studienmodul WHERE user_id=? AND bildungsweg_id=? AND deleted_at IS NULL",
            (user_id, row["id"])).fetchone()
        d["ects_erreicht"], d["module_n"] = c["erreicht"], c["module"]
        d["fachsemester"] = self._semester_count(row["start_semester"])
        return d

    def studien_cockpit(self, user_id: str, bw: dict[str, Any]) -> dict[str, Any]:
        conn = self.db.get_conn()
        mods = [dict(x) for x in conn.execute(
            "SELECT * FROM studienmodul WHERE user_id=? AND bildungsweg_id=? AND deleted_at IS NULL",
            (user_id, bw["id"])).fetchall()]
        bestanden = [m for m in mods if m["status"] in ("bestanden", "anerkannt")]
        erreicht = sum(int(m["ects_erreicht"]) for m in bestanden)
        je_bereich: dict[str, int] = {}
        for m in bestanden:
            je_bereich[m["bereich"]] = je_bereich.get(m["bereich"], 0) + int(m["ects_erreicht"])
        gesamt = int(bw["ects_gesamt"])
        benotet = [(float(m["note"]), int(m["ects"])) for m in mods
                   if m["status"] == "bestanden" and m["note"] is not None and int(m["ects"]) > 0]
        note_schnitt = (round(sum(n * e for n, e in benotet) / sum(e for _, e in benotet), 2)
                        if benotet else None)
        zaehl: dict[str, int] = {}
        for m in mods:
            zaehl[m["status"]] = zaehl.get(m["status"], 0) + 1
        default_max = int(bw["max_versuche"])
        risiko = []
        for m in mods:
            emax = self._effektiv_max(m, default_max)
            if m["status"] == "endgueltig":
                risiko.append({"modul": m["name"], "versuch_nr": int(m["versuch_nr"]),
                               "max": emax, "stufe": "endgueltig"})
            elif m["status"] == "nicht_bestanden" and int(m["versuch_nr"]) >= emax - 1:
                risiko.append({"modul": m["name"], "versuch_nr": int(m["versuch_nr"]),
                               "max": emax, "stufe": "letzter_versuch"})
        fr = [dict(x) for x in conn.execute(
            "SELECT titel,art,faellig_am,modul_id FROM studienfrist WHERE user_id=? AND bildungsweg_id=? "
            "AND erledigt=0 AND deleted_at IS NULL ORDER BY faellig_am LIMIT 8",
            (user_id, bw["id"])).fetchall()]
        return {
            "bildungsweg": bw,
            "ects": {"erreicht": erreicht, "gesamt": gesamt,
                     "prozent": round(erreicht / gesamt * 100) if gesamt > 0 else 0,
                     "je_bereich": [{"bereich": b, "erreicht": e} for b, e in sorted(je_bereich.items())]},
            "note_schnitt": note_schnitt,
            "fachsemester": self._semester_count(bw["start_semester"]),
            "regelstudienzeit": int(bw["regelstudienzeit"]),
            "module": zaehl,
            "versuch_risiko": risiko,
            "naechste_fristen": fr,
        }

    def studien_uebersicht(self, user_id: str = "dizzi") -> dict[str, Any]:
        rows = self.db.get_conn().execute(
            "SELECT * FROM bildungsweg WHERE user_id=? AND status='laufend' AND deleted_at IS NULL "
            "ORDER BY created_at", (user_id,)).fetchall()
        return {"studien": [self.studien_cockpit(user_id, dict(x)) for x in rows]}

    def studien_warnungen(self, user_id: str = "dizzi") -> list[dict[str, Any]]:
        out = []
        for bw in self.db.get_conn().execute(
                "SELECT * FROM bildungsweg WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall():
            c = self.studien_cockpit(user_id, dict(bw))
            label = bw["studiengang"] or bw["institution"] or "Bildungsweg"
            for w in c["versuch_risiko"]:
                out.append({**w, "bildungsweg": label})
        return out

    def studienfristen_offen(self, user_id: str = "dizzi") -> list[dict[str, Any]]:
        rows = self.db.get_conn().execute(
            "SELECT s.*, b.studiengang AS bw_titel FROM studienfrist s "
            "JOIN bildungsweg b ON b.id=s.bildungsweg_id "
            "WHERE s.user_id=? AND s.erledigt=0 AND s.deleted_at IS NULL AND b.deleted_at IS NULL "
            "ORDER BY s.faellig_am", (user_id,)).fetchall()
        return [dict(x) for x in rows]

    def ki_kontext(self, user_id: str = "dizzi") -> str:
        """Kompakter Geschäfts-Kontext für die lokale KI (Mini-Dizzi)."""
        s = self.stats(user_id)
        w = self.frist_waechter(user_id)
        zeilen = [
            f"Kunden: {s['kunden']}",
            f"Offene Rechnungen: {s['offene_rechnungen']} ({s['offene_rechnungen_cent']/100:.2f} €), "
            f"davon überfällig: {s['ueberfaellige_rechnungen']}",
            f"Umsatz (bezahlt): {s['umsatz_bezahlt_cent']/100:.2f} €, MRR: {s['mrr_cent']/100:.2f} €",
            f"Support offen: {s['support_offen']}, Fristen fällig: {s['fristen_faellig']}",
        ]
        if w["gesamt"]:
            zeilen.append(f"WÄCHTER: {w['gesamt']} Posten brauchen Aufmerksamkeit "
                          f"({len(w['ueberfaellige_rechnungen'])} Rechnungen, {len(w['faellige_fristen'])} Fristen, "
                          f"{len(w.get('faellige_studienfristen', []))} Studien-Fristen, "
                          f"{len(w.get('studien_risiko', []))} Prüfungsversuch-Risiken).")
        studien = self.studien_uebersicht(user_id).get("studien", [])
        for c in studien:
            bw = c["bildungsweg"]
            zeilen.append(
                f"Studium {bw.get('studiengang') or bw.get('institution') or '—'}: "
                f"{c['ects']['erreicht']}/{c['ects']['gesamt']} ECTS ({c['ects']['prozent']}%), "
                f"Fachsemester {c['fachsemester']}"
                + (f", Notenschnitt {c['note_schnitt']}" if c['note_schnitt'] is not None else "")
                + (f", {len(c['versuch_risiko'])} Versuch-Risiko" if c['versuch_risiko'] else ""))
        return "\n".join(zeilen)


def build_domain(db: Database, http_post: Any | None = None,
                 ausgaben_reader: Any | None = None) -> Domain:
    return Domain(db, http_post=http_post, ausgaben_reader=ausgaben_reader)
