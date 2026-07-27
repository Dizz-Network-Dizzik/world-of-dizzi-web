"""Dizz Money — vertragskonforme App über dem Double-Entry-Ledger.

Start (Entwicklung):
    <venv-python> -m uvicorn moneyapp.main:app_factory --factory
        --host 127.0.0.1 --port 8210 --app-dir finanzen

Die Domäne setzt an genau drei Stellen an (Schema · Router · summary_fn);
alles Vertragliche (Health/Manifest/Settings/Account/Vault/Actions/Audit/
Datenrechte + Dizz Defense) kommt aus appkit. Der Buchungs-Router ruft NUR
den geprüften ``ledger``-Kern — die DB speichert, was der Kern als gültig
bestätigt hat (eine unbalancierte Buchung erreicht die DB nie).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from . import __version__
from . import ledger
from . import auswertung as ausw
from . import regeln as regelmodul
from . import chronik_naht          # V-BIZZI-1 B1 Runde 3: Chronik-Verdrahtung (docs/80 §6)
from . import wiederkehr as wkmodul
from . import trading_steuer as tsteuer
from . import bereiche as bereichmodul
from . import geschaefts_regie      # RG-8: Geschäfts-Kopplung (beleg_vorschlagen + beleg_angelegt)
from .elster import persistenz as elsterpersistenz
from .ustva import persistenz as ustvapersistenz
from .importers import ImportFehler, als_buchung, bewegung_hash, parse_inhalt
from .importers.csv_import import PROFILE

from appkit.app import create_app  # noqa: E402 (Pfad-Shim in __init__)
from appkit.actions import ActionRegistry   # RG-8: K4-Registry für beleg_vorschlagen
from appkit import chronik          # DzChronik-Kern (V-BIZZI-1)
from appkit import ereignis_spine   # RG-8: Ereignis-Spine (beleg_angelegt-Zeiger)
from appkit import ui_kit_path
from appkit.auth import DEFAULT_USER_ID, UserContext, current_user
from appkit.csv_safe import csv_safe  # CSV-Formel-Injection-Schutz (Steuer-Exporte → Dritte)
from appkit.db import Database, default_db_path, new_id, now_iso
from appkit.dizzi_id import install_dizzi_id
from appkit.manifest import AppManifest, McpInfo, Shares
from appkit.summary import Kpi

APP_ID = "finanzen"

MANIFEST = AppManifest(
    id=APP_ID, name="Finanzmanagement", brand="Dizz Money", version=__version__,
    port=8210, icon="wallet", sensitivity="hoch",   # hoch ⇒ lokal_only by default
    mcp=McpInfo(command=["<venv-python>", "mcp_server.py"],
                tools=["kontostand", "nettovermoegen", "cashflow"]),
    shares=Shares(summary=True, tools=["kontostand", "nettovermoegen", "cashflow"]),
)

# Domänen-Schema: Konten + Buchungen + Postings (Minor-Units als INTEGER!).
# Folgt den Vertrags-Konventionen (UUID/user_id/Timestamps/Soft-Delete).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS konten (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    typ         TEXT NOT NULL,          -- asset|liability|income|expense|equity
    waehrung    TEXT NOT NULL DEFAULT 'EUR',
    abgeglichen_bis    TEXT NOT NULL DEFAULT '',  -- Reconciliation: „abgeglichen bis" (Datum)
    abgeglichen_saldo  INTEGER,                   -- Auszug-Saldo zum Abgleich-Stichtag (Minor)
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_konten ON konten (user_id, typ);
CREATE TABLE IF NOT EXISTS buchungen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    notiz       TEXT NOT NULL DEFAULT '',
    datum       TEXT NOT NULL,
    gegenpartei TEXT NOT NULL DEFAULT '',     -- Import: Name/IBAN der Gegenseite
    verwendungszweck TEXT NOT NULL DEFAULT '', -- Import: Buchungstext (für Regeln)
    kategorie_id TEXT,                          -- Teil B: zugeordnete Kategorie
    import_hash TEXT,                           -- Dedupe-Schlüssel (NULL = manuell)
    quelle      TEXT NOT NULL DEFAULT 'manuell',-- 'manuell' | 'import:<format>'
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_buchungen ON buchungen (user_id, datum);
-- WICHTIG: Indizes auf import_hash/kategorie_id NICHT hier anlegen — Bestands-DBs (v0.1)
-- haben diese Spalten noch nicht, dann scheitert executescript() VOR der Migration.
-- Sie werden in _migriere() angelegt, NACHDEM die Spalten via ALTER sicher existieren.
CREATE TABLE IF NOT EXISTS postings (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    buchung_id  TEXT NOT NULL,
    konto_id    TEXT NOT NULL,
    betrag      INTEGER NOT NULL,       -- Minor-Units, vorzeichenbehaftet
    created_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_postings_konto ON postings (user_id, konto_id);
CREATE INDEX IF NOT EXISTS idx_postings_buchung ON postings (buchung_id);
CREATE TABLE IF NOT EXISTS kategorien (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    richtung    TEXT NOT NULL DEFAULT 'ausgabe',  -- einnahme|ausgabe|beides
    farbe       TEXT NOT NULL DEFAULT 'cyan',
    steuer_relevant  INTEGER NOT NULL DEFAULT 0,   -- Teil D: steuerrelevant?
    steuer_art  TEXT NOT NULL DEFAULT '',          -- Teil D: frei, z. B. 'Werbungskosten'
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_kategorien ON kategorien (user_id, deleted_at);
CREATE TABLE IF NOT EXISTS regeln (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    muster      TEXT NOT NULL,
    feld        TEXT NOT NULL DEFAULT 'beliebig',  -- gegenpartei|verwendungszweck|notiz|beliebig
    kategorie_id TEXT NOT NULL,
    bereich_id  TEXT NOT NULL DEFAULT '',          -- optional: Treffer ordnet die Buchung AUCH diesem Bereich zu
    prioritaet  INTEGER NOT NULL DEFAULT 100,
    treffer     INTEGER NOT NULL DEFAULT 0,        -- lernt aus bestätigten Treffern
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_regeln ON regeln (user_id, deleted_at);
CREATE TABLE IF NOT EXISTS budgets (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    kategorie_id TEXT NOT NULL,
    monat       TEXT NOT NULL,                      -- 'YYYY-MM' oder '*' (jeder Monat)
    betrag      INTEGER NOT NULL,                   -- Soll-Limit, Minor-Units
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    UNIQUE (user_id, kategorie_id, monat)
);
CREATE INDEX IF NOT EXISTS idx_budgets ON budgets (user_id, monat);
CREATE TABLE IF NOT EXISTS serien (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    schluessel  TEXT NOT NULL DEFAULT '',         -- Gruppierungs-Schlüssel (Gegenpartei)
    betrag      INTEGER NOT NULL,                  -- Minor-Units, signiert (− = Ausgabe)
    waehrung    TEXT NOT NULL DEFAULT 'EUR',
    intervall   TEXT NOT NULL DEFAULT 'monatlich', -- Label (woechentlich..jaehrlich)
    intervall_tage INTEGER NOT NULL DEFAULT 30,    -- gemessener/gewählter Abstand
    naechste_faelligkeit TEXT NOT NULL,            -- YYYY-MM-DD
    kategorie_id TEXT,
    richtung    TEXT NOT NULL DEFAULT 'ausgabe',   -- einnahme|ausgabe
    aktiv       INTEGER NOT NULL DEFAULT 1,
    quelle      TEXT NOT NULL DEFAULT 'manuell',   -- 'erkannt' | 'manuell'
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_serien ON serien (user_id, aktiv, deleted_at);
CREATE TABLE IF NOT EXISTS sparziele (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    zielbetrag  INTEGER NOT NULL,                  -- Soll-Betrag, Minor-Units (> 0)
    waehrung    TEXT NOT NULL DEFAULT 'EUR',
    konto_id    TEXT,                              -- optional: Auto-Tracking aus echtem Konto-Saldo
    faellig_am  TEXT NOT NULL DEFAULT '',          -- optional: Zieldatum YYYY-MM-DD
    aktuell_minor INTEGER NOT NULL DEFAULT 0,      -- manueller Stand (nur OHNE konto_id), Minor-Units
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sparziele ON sparziele (user_id, deleted_at);
CREATE TABLE IF NOT EXISTS wechselkurse (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    waehrung    TEXT NOT NULL,                     -- z. B. 'USD'
    kurs        TEXT NOT NULL,                      -- Decimal-String: EUR je 1 Einheit
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (user_id, waehrung)
);
-- V14 (docs/26 §13): Trading-Kapital + steuerpflichtige Realisierungen (Echtgeld-Schiene).
-- Eigenständige Tabellen (kein ALTER) ⇒ CREATE TABLE IF NOT EXISTS ist auf Bestands-DBs sicher.
CREATE TABLE IF NOT EXISTS trading_kapital (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    datum       TEXT NOT NULL,                     -- YYYY-MM-DD
    art         TEXT NOT NULL,                     -- einlage | entnahme | bewertung
    betrag_minor INTEGER NOT NULL,                 -- Euro-Cent (positiv; art gibt die Bedeutung)
    notiz       TEXT NOT NULL DEFAULT '',
    quelle      TEXT NOT NULL DEFAULT 'manuell',   -- manuell | tb | import
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_trading_kapital ON trading_kapital (user_id, datum);
CREATE TABLE IF NOT EXISTS trading_realisierung (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    datum       TEXT NOT NULL,                     -- Realisierungs-/Verkaufsdatum YYYY-MM-DD
    regime      TEXT NOT NULL DEFAULT 'futures',   -- futures (§20) | spot (§23)
    betrag_minor INTEGER NOT NULL,                 -- +Gewinn / −Verlust (netto n. Gebühren), Cent
    beschreibung TEXT NOT NULL DEFAULT '',
    kauf_datum  TEXT NOT NULL DEFAULT '',          -- §23-Haltefrist (nur spot)
    quelle      TEXT NOT NULL DEFAULT 'manuell',   -- manuell | tb | import
    extern_ref  TEXT NOT NULL DEFAULT '',          -- Idempotenz (z. B. tb:trade:<id>)
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_trading_real ON trading_realisierung (user_id, datum, regime);
CREATE TABLE IF NOT EXISTS trading_config (
    user_id     TEXT PRIMARY KEY,
    pauschbetrag_rest_cent INTEGER NOT NULL DEFAULT 100000,  -- § 20 Sparer-Pauschbetrag (frei)
    freigrenze_rest_cent   INTEGER NOT NULL DEFAULT 100000,  -- § 23 Freigrenze (frei)
    persoenlicher_satz REAL NOT NULL DEFAULT 0.42,           -- § 23: persönl. ESt-Satz (Schätzung)
    kirchensteuer_satz REAL NOT NULL DEFAULT 0.0,            -- 0.09 / 0.08 / 0.0
    updated_at  TEXT NOT NULL
);
"""

# Richtwert-Kurse (EUR je 1 Einheit) als Startwerte — der Nutzer pflegt sie selbst
# (0 €/offline, kein Netz-Abruf; FinTS/Live-Kurse sind Architektur-KI-Parkplatz). Rein
# informativ („≈"). EUR ist per Definition 1.
DEFAULT_KURSE: dict[str, str] = {
    "EUR": "1", "USD": "0.92", "GBP": "1.17", "CHF": "1.05",
    "JPY": "0.0061", "BTC": "60000",
}
# Stabiler Name der Währungstausch-Gegenkonten (je Währung eines, typ equity).
TAUSCHKONTO_NAME = "Währungstausch"


class KontoIn(BaseModel):
    name: str
    typ: str = "asset"
    waehrung: str = "EUR"
    bereich_id: str = ""   # optionaler Default-Bereich des Kontos ('' = Allgemein)


class KontoUpdateIn(BaseModel):
    name: str          # nur Umbenennen — Typ/Währung umzudeuten verbietet sich,
                       # solange Postings in der alten Bedeutung gebucht sind.


class BuchungIn(BaseModel):
    von_konto: str
    nach_konto: str
    betrag: str            # Eingabe-String ("12,50") in der Währung von ``von_konto``
    notiz: str = ""
    datum: str = ""
    betrag_nach: str = ""  # NUR bei FX: empfangener Betrag in der Währung von nach_konto;
                           # leer ⇒ aus hinterlegtem Kurs geschätzt
    bereich_id: str = ""   # optionaler Bereich-Override ('' = erbt vom Konto)


class SplitZeile(BaseModel):
    betrag: str                        # Magnitude ("70,00")
    richtung: str = "ausgabe"          # ausgabe|einnahme
    kategorie_id: str | None = None


class SplitIn(BaseModel):
    konto_id: str                      # Bank-/Vermögenskonto (eine Seite aller Zeilen)
    zeilen: list[SplitZeile]
    datum: str = ""
    gegenpartei: str = ""
    notiz: str = ""


class AbgleichIn(BaseModel):
    bis: str                           # Stichtag (YYYY-MM-DD) des Kontoauszugs
    saldo: str                         # Auszug-Endsaldo (Eingabe-String) zum Stichtag


class WechselkursIn(BaseModel):
    waehrung: str
    kurs: str              # Decimal-String: EUR je 1 Einheit (z. B. "0.92" für USD)


class ImportIn(BaseModel):
    inhalt: str                        # roher Datei-Inhalt (CSV/XML/MT940-Text)
    format: str = "auto"               # 'csv' | 'camt' | 'mt940' | 'auto'
    zielkonto: str                     # Bankkonto-ID, auf das gebucht wird
    profil: str = "auto"               # CSV-Spalten-Profil (nur bei format=csv)


class KategorieIn(BaseModel):
    name: str
    richtung: str = "ausgabe"          # einnahme|ausgabe|beides
    farbe: str = "cyan"
    steuer_relevant: bool = False      # Teil D
    steuer_art: str = ""               # Teil D, frei


class RegelIn(BaseModel):
    muster: str
    kategorie_id: str
    feld: str = "beliebig"             # gegenpartei|verwendungszweck|notiz|beliebig
    bereich_id: str = ""               # optional: Treffer ordnet die Buchung auch diesem Bereich zu
    prioritaet: int = 100


class RegelPatchIn(BaseModel):
    bereich_id: str = ""               # Bereich der Regel setzen/lösen ('' = kein Bereich)


class KategorieZuweisungIn(BaseModel):
    kategorie_id: str | None = None    # None = Zuordnung entfernen
    lernen: bool = False               # aus dieser Bestätigung eine Regel ableiten


class BudgetIn(BaseModel):
    kategorie_id: str
    monat: str = "*"                   # 'YYYY-MM' oder '*' (jeder Monat)
    betrag: str                        # Eingabe-String ("250,00") -> Minor-Units


class SparzielIn(BaseModel):
    name: str
    zielbetrag: str                    # Eingabe-String ("5000,00") -> Minor-Units (> 0)
    waehrung: str = "EUR"              # ignoriert, wenn konto_id gesetzt (dann = Konto-Währung)
    konto_id: str | None = None        # optional: aktueller Stand aus dem echten Konto-Saldo
    faellig_am: str = ""               # optional: Zieldatum YYYY-MM-DD
    aktuell: str = "0"                 # manueller Stand (nur OHNE konto_id), >= 0


class SerieIn(BaseModel):
    name: str
    betrag: str                        # Magnitude-String ("12,99"); Vorzeichen via richtung
    richtung: str = "ausgabe"          # einnahme|ausgabe
    intervall_tage: int = 30
    intervall: str = "monatlich"
    naechste_faelligkeit: str = ""     # YYYY-MM-DD; leer = heute + Intervall
    kategorie_id: str | None = None
    schluessel: str = ""               # optional (aus einem erkannten Kandidaten)
    bereich_id: str = ""               # optionaler Bereich des Abos ('' = Allgemein)


class VerbuchenIn(BaseModel):
    konto_id: str                      # Bank-/Vermögenskonto, auf das gebucht wird
    datum: str = ""                    # YYYY-MM-DD; leer = Fälligkeitsdatum der Serie


class BelegIn(BaseModel):
    """V15 (docs/26 §12): ein Admin-Dokument als Beleg an eine Buchung knüpfen."""
    ref: str                           # admin:dokument:<id>
    titel: str = ""                    # menschenlesbarer Beleg-Titel (Anzeige)


class FestschreibungIn(BaseModel):
    """V-BIZZI-1 (docs/80 §6.3): GoBD-Festschreibung eines abgeschlossenen Monats."""
    zeitraum: str                      # 'YYYY-MM'


class TradingKapitalIn(BaseModel):
    """V14 (docs/26 §13): eine Trading-Kapital-Bewegung (Echtgeld)."""
    datum: str                         # YYYY-MM-DD
    art: str                           # einlage | entnahme | bewertung
    betrag: str                        # Magnitude-String ("5000,00")
    notiz: str = ""


class TradingRealIn(BaseModel):
    """V14: eine steuerpflichtige Trading-Realisierung (Gewinn/Verlust)."""
    datum: str                         # Realisierungsdatum YYYY-MM-DD
    regime: str = "futures"            # futures (§20) | spot (§23)
    betrag: str                        # Magnitude-String (Vorzeichen via richtung)
    richtung: str = "gewinn"           # gewinn | verlust
    beschreibung: str = ""
    kauf_datum: str = ""               # §23-Haltefrist (nur spot)


class TradingConfigIn(BaseModel):
    """V14: steuerliche Schätz-Parameter (alle optional = Teil-Update)."""
    pauschbetrag_rest: str | None = None    # § 20 Sparer-Pauschbetrag-Rest ("1000,00")
    freigrenze_rest: str | None = None      # § 23 Freigrenze-Rest
    persoenlicher_satz: float | None = None # § 23 persönl. ESt-Satz (0..1)
    kirchensteuer_satz: float | None = None # 0.09 / 0.08 / 0.0


# Stabiler Name des Import-Sammelkontos (Gegenbuchung bis zur Kategorisierung).
# Typ EQUITY ⇒ neutral: zählt NICHT ins Nettovermögen (nur asset−liability),
# bis Teil B die Bewegung einer echten Einnahme-/Ausgabe-Kategorie zuordnet.
SAMMELKONTO_NAME = "Nicht zugeordnet"
SAMMELKONTO_TYP = "equity"


def _migriere(db: Database) -> None:
    """Idempotente Spalten-Migration für BESTANDS-Datenbanken (v0.1 kannte die
    Import-/Kategorie-Spalten noch nicht). ``CREATE TABLE IF NOT EXISTS`` legt
    sie nur in FRISCHEN DBs an; hier rüsten wir fehlende Spalten nach. Billig
    und gefahrlos: ``ALTER TABLE ADD COLUMN`` mit Default, je Spalte gekapselt."""
    conn = db.get_conn()
    vorhanden = {r["name"] for r in conn.execute("PRAGMA table_info(buchungen)")}
    nachzu = {
        "gegenpartei": "TEXT NOT NULL DEFAULT ''",
        "verwendungszweck": "TEXT NOT NULL DEFAULT ''",
        "kategorie_id": "TEXT",
        "import_hash": "TEXT",
        "quelle": "TEXT NOT NULL DEFAULT 'manuell'",
        "beleg_ref": "TEXT NOT NULL DEFAULT ''",     # V15: admin:dokument:<id> (verknüpfter Beleg)
        "beleg_titel": "TEXT NOT NULL DEFAULT ''",   # V15: menschenlesbarer Beleg-Titel
        "bereich_id": "TEXT NOT NULL DEFAULT ''",    # Bereich-Achse: Buchungs-Override ('' = erbt vom Konto)
    }
    for spalte, typ in nachzu.items():
        if spalte not in vorhanden:
            conn.execute(f"ALTER TABLE buchungen ADD COLUMN {spalte} {typ}")
    # Reconciliation- + Bereich-Spalten auf konten (Bestands-DBs).
    kvorhanden = {r["name"] for r in conn.execute("PRAGMA table_info(konten)")}
    for spalte, typ in {"abgeglichen_bis": "TEXT NOT NULL DEFAULT ''",
                        "abgeglichen_saldo": "INTEGER",
                        "bereich_id": "TEXT NOT NULL DEFAULT ''"}.items():  # Default-Bereich des Kontos
        if spalte not in kvorhanden:
            conn.execute(f"ALTER TABLE konten ADD COLUMN {spalte} {typ}")
    # Bereich-Achse auch an Serien (Abos) — ein Abo kann zu einem Bereich gehören.
    svorhanden = {r["name"] for r in conn.execute("PRAGMA table_info(serien)")}
    if svorhanden and "bereich_id" not in svorhanden:
        conn.execute("ALTER TABLE serien ADD COLUMN bereich_id TEXT NOT NULL DEFAULT ''")
    # Bereich-Achse auch an Regeln — eine Regel kann den Bereich mitsetzen (Auto-Zuordnung beim Treffer).
    rvorhanden = {r["name"] for r in conn.execute("PRAGMA table_info(regeln)")}
    if rvorhanden and "bereich_id" not in rvorhanden:
        conn.execute("ALTER TABLE regeln ADD COLUMN bereich_id TEXT NOT NULL DEFAULT ''")
    # Indizes auf die Import-/Kategorie-Spalten IMMER (idempotent, IF NOT EXISTS) — sie
    # gehören NICHT in die Basis-Schema (dort scheitern sie an Bestands-DBs ohne die
    # Spalte). Erst HIER sind die Spalten garantiert da: frisch aus CREATE TABLE, alt aus
    # dem ALTER oben. Auch für frische DBs nötig (sonst fehlte der Dedupe-Index).
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_buchungen_imphash "
        "ON buchungen (user_id, import_hash) WHERE import_hash IS NOT NULL")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_buchungen_kat "
        "ON buchungen (user_id, kategorie_id)")
    # Bereich-Achse: Indizes erst HIER (nach gesichertem ALTER), idempotent.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_konten_bereich ON konten (user_id, bereich_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_buchungen_bereich ON buchungen (user_id, bereich_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_serien_bereich ON serien (user_id, bereich_id)")
    conn.commit()


def _regeln_anwenden(db: Database, user_id: str) -> int:
    """Wendet die Kategorisierungs-Regeln auf noch unkategorisierte Buchungen an.
    Voll ausgebaut in Teil B (``moneyapp.regeln``); existiert die Regel-Tabelle
    noch nicht, ist nichts zu tun (Teil A)."""
    conn = db.get_conn()
    hat_tabelle = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='regeln'").fetchone()
    if not hat_tabelle:
        return 0
    from .regeln import regeln_anwenden
    return regeln_anwenden(db, user_id)


def _gesperrt_409(zeitraum: str) -> JSONResponse:
    """§6.3: einheitliche 409-Antwort, wenn ein Schreibpfad einen festgeschriebenen Zeitraum trifft."""
    return JSONResponse(
        {"error": f"Zeitraum {zeitraum} ist festgeschrieben — Korrektur als Gegenbuchung im offenen Monat"},
        status_code=409)


def build_app(data_dir: Path | None = None, archiv_post=None,
              verknuepfung_post=None, belege_get=None, tb_get=None):
    """``archiv_post`` injiziert den Querverbindungs-POST (V9 Money→Memory, docs/26;
    Test-Mock bzw. Prod = None ⇒ echter Core-Relay). ``verknuepfung_post`` injiziert
    den V15-Beleg-Link-POST (Money→Admin), ``belege_get`` den V15-Beleg-Lookup-GET
    (Money holt Admin-Dokumente), ``tb_get`` den V14-Trading-Bot-Performance-GET
    (read-only über den Core). Prod = None ⇒ echter Core-Relay."""
    root = data_dir or Path(os.environ.get("DIZZ_FINANZEN_DATA_DIR",
                                           r"C:\Dizzik\data"))
    db = Database(default_db_path(APP_ID, data_root=root),
                  extra_schema=_SCHEMA + bereichmodul.SCHEMA_BEREICHE
                  + elsterpersistenz.SCHEMA_ELSTER + ustvapersistenz.SCHEMA_UST
                  + chronik_naht.AUSGANG_SCHEMA + chronik_naht.FESTSCHREIBUNGEN_SCHEMA
                  + geschaefts_regie.SCHEMA_BELEG_VORSCHLAG   # RG-8: Beleg-Entwurf-Review
                  + ereignis_spine.SCHEMA_EREIGNISSE_SQL)     # RG-8: Ereignis-Spine (§6)
    _migriere(db)
    # V-BIZZI-1 (docs/80 §2.7): der Chronik-Kontext (Schlüssel/Pfeffer/Segmente) lebt unter moneys
    # Datenwurzel ⇒ Tests erben ihr tmp-Verzeichnis, die reale data\chronik bleibt unberührt.
    chronik_naht.setze_chronik_dir(chronik.chronik_dir(root))
    router = APIRouter()
    bereiche = bereichmodul.Bereiche(db)   # Bereich-Achse (CRUD-Router unten in routers=[…])
    elster_speicher = elsterpersistenz.ElsterSpeicher(db)  # ELSTER-Transport-Persistenz (M1-1, docs/65)
    ust_speicher = ustvapersistenz.UstSpeicher(db)         # UStVA-Datenschicht-Persistenz (M4-1, docs/68)

    def _konto(user_id: str, konto_id: str):
        return db.get_conn().execute(
            "SELECT * FROM konten WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (konto_id, user_id)).fetchone()

    def _bereich_ok(user_id: str, bereich_id: str) -> bool:
        """``''`` (Allgemein) oder ein existierender, nicht gelöschter Bereich."""
        return bereich_id == "" or bereiche.holen(user_id, bereich_id) is not None

    def _sammelkonto(user_id: str, waehrung: str) -> str:
        """Liefert die ID des Import-Sammelkontos „Nicht zugeordnet" der Währung
        (legt es bei Bedarf an). Gegenbuchungs-Topf, bis Teil B kategorisiert."""
        conn = db.get_conn()
        row = conn.execute(
            "SELECT id FROM konten WHERE user_id=? AND name=? AND typ=? "
            "AND waehrung=? AND deleted_at IS NULL",
            (user_id, SAMMELKONTO_NAME, SAMMELKONTO_TYP, waehrung)).fetchone()
        if row:
            return row["id"]
        kid, ts = new_id(), now_iso()
        conn.execute(
            "INSERT INTO konten (id, user_id, name, typ, waehrung, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (kid, user_id, SAMMELKONTO_NAME, SAMMELKONTO_TYP, waehrung, ts, ts))
        conn.commit()
        return kid

    def _waehrungstausch(user_id: str, waehrung: str) -> str:
        """ID des Währungstausch-Gegenkontos (typ equity) je Währung — Gegenstück
        einer FX-Buchung; legt es bei Bedarf an (wie das Sammelkonto)."""
        conn = db.get_conn()
        name = f"{TAUSCHKONTO_NAME} {waehrung}"
        row = conn.execute(
            "SELECT id FROM konten WHERE user_id=? AND name=? AND typ='equity' "
            "AND waehrung=? AND deleted_at IS NULL", (user_id, name, waehrung)).fetchone()
        if row:
            return row["id"]
        kid, ts = new_id(), now_iso()
        conn.execute(
            "INSERT INTO konten (id, user_id, name, typ, waehrung, created_at, updated_at)"
            " VALUES (?,?,?,'equity',?,?,?)", (kid, user_id, name, waehrung, ts, ts))
        conn.commit()
        return kid

    def _kurse(user_id: str) -> dict[str, str]:
        """Effektive Kurstabelle: Richtwerte (DEFAULT_KURSE) überschrieben durch
        die vom Nutzer gepflegten Kurse. EUR bleibt immer 1."""
        kurse = dict(DEFAULT_KURSE)
        for r in db.get_conn().execute(
                "SELECT waehrung, kurs FROM wechselkurse WHERE user_id=?",
                (user_id,)).fetchall():
            kurse[r["waehrung"]] = r["kurs"]
        kurse["EUR"] = "1"
        return kurse

    def _kategorie(user_id: str, kategorie_id: str):
        return db.get_conn().execute(
            "SELECT * FROM kategorien WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (kategorie_id, user_id)).fetchone()

    def _sparziel(user_id: str, sparziel_id: str):
        return db.get_conn().execute(
            "SELECT * FROM sparziele WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (sparziel_id, user_id)).fetchone()

    def _konto_anzeige_saldo(user_id: str, konto) -> int:
        """Aktueller Anzeige-Saldo eines Kontos in seiner eigenen Währung (Minor-
        Units) — exakt der Wert, den ``konten_liste`` ausweist. Quelle des Auto-
        Trackings eines Sparziels mit ``konto_id``."""
        roh = db.get_conn().execute(
            "SELECT COALESCE(SUM(betrag),0) AS s FROM postings "
            "WHERE konto_id=? AND user_id=? AND deleted_at IS NULL",
            (konto["id"], user_id)).fetchone()["s"]
        return ledger.anzeige_saldo(roh, konto["typ"])

    def _regel_lernen(user_id: str, muster: str, feld: str, kategorie_id: str,
                      prioritaet: int = 100, bereich_id: str = "") -> str:
        """Legt eine Regel an oder verstärkt eine identische (Muster+Feld+
        Kategorie): so wird aus wiederholter Bestätigung kein Regel-Wildwuchs.
        ``bereich_id`` (optional) wird mitgelernt: die Regel ordnet künftige
        Treffer auch diesem Bereich zu — gibt das Beispiel einen Bereich her,
        übernimmt ihn auch eine bereits bestehende Regel (sonst bleibt er)."""
        if bereich_id and not _bereich_ok(user_id, bereich_id):
            bereich_id = ""
        conn = db.get_conn()
        vorhanden = conn.execute(
            "SELECT id FROM regeln WHERE user_id=? AND muster=? AND feld=? "
            "AND kategorie_id=? AND deleted_at IS NULL",
            (user_id, muster, feld, kategorie_id)).fetchone()
        ts = now_iso()
        if vorhanden:
            if bereich_id:
                conn.execute("UPDATE regeln SET treffer=treffer+1, bereich_id=?, updated_at=? WHERE id=?",
                             (bereich_id, ts, vorhanden["id"]))
            else:
                conn.execute("UPDATE regeln SET treffer=treffer+1, updated_at=? WHERE id=?",
                             (ts, vorhanden["id"]))
            conn.commit()
            return vorhanden["id"]
        rid = new_id()
        conn.execute(
            "INSERT INTO regeln (id, user_id, muster, feld, kategorie_id, bereich_id, prioritaet, "
            "treffer, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, user_id, muster, feld, kategorie_id, bereich_id, prioritaet, 0, ts, ts))
        conn.commit()
        return rid

    def _bereich_je_buchung(user_id: str) -> dict[str, str]:
        """Effektiver Bereich je Buchung (deterministisch): der Buchungs-Override
        (``buchung.bereich_id``); sonst der Bereich des berührten asset/liability-
        Kontos, falls EINDEUTIG; sonst ``''`` (Allgemein). Reine Lese-Operation —
        die Bereich-Achse ändert NICHTS am Ledger."""
        rows = db.get_conn().execute(
            "SELECT b.id AS bid, b.bereich_id AS override, ko.bereich_id AS kb, ko.typ AS typ "
            "FROM buchungen b "
            "JOIN postings p ON p.buchung_id=b.id AND p.deleted_at IS NULL "
            "JOIN konten ko ON ko.id=p.konto_id "
            "WHERE b.user_id=? AND b.deleted_at IS NULL", (user_id,)).fetchall()
        override: dict[str, str] = {}
        konto_b: dict[str, set] = {}
        for r in rows:
            override[r["bid"]] = r["override"] or ""
            if r["typ"] in ("asset", "liability") and (r["kb"] or ""):
                konto_b.setdefault(r["bid"], set()).add(r["kb"])
        eff: dict[str, str] = {}
        for bid_, ov in override.items():
            if ov:
                eff[bid_] = ov
            else:
                s = konto_b.get(bid_, set())
                eff[bid_] = next(iter(s)) if len(s) == 1 else ""
        return eff

    def _bewegungen(user_id: str, von: str | None = None, bis: str | None = None,
                    bereich: str | None = None):
        """Lädt je Buchung den netto-Vermögenseffekt (asset/liability-Postings) +
        Kategorie/Steuer-Felder — die Eingabe der reinen Auswertungsfunktionen.

        Multi-Währung: der netto wird PRO WÄHRUNG ermittelt und über die
        hinterlegten Kurse nach EUR umgerechnet (informativ); Fremdwährungs-
        Bewegungen fließen so in Cashflow/Budget/Steuer ein.

        ``bereich`` (optional): filtert auf Buchungen, deren EFFEKTIVER Bereich
        (Override sonst Konto-Default, s. ``_bereich_je_buchung``) gleich ist —
        die Basis aller Pro-Bereich-Auswertungen (Cockpit)."""
        rows = db.get_conn().execute(
            "SELECT b.id, b.datum, b.kategorie_id, k.name AS kategorie_name, "
            "k.steuer_relevant, k.steuer_art, ko.waehrung AS waehrung, "
            "COALESCE(SUM(CASE WHEN ko.typ IN ('asset','liability') "
            "THEN p.betrag ELSE 0 END),0) AS netto_w "
            "FROM buchungen b "
            "JOIN postings p ON p.buchung_id=b.id AND p.deleted_at IS NULL "
            "JOIN konten ko ON ko.id=p.konto_id "
            "LEFT JOIN kategorien k ON k.id=b.kategorie_id AND k.deleted_at IS NULL "
            "WHERE b.user_id=? AND b.deleted_at IS NULL GROUP BY b.id, ko.waehrung",
            (user_id,)).fetchall()
        kurse = _kurse(user_id)
        agg: dict[str, dict] = {}
        for r in rows:
            e = agg.setdefault(r["id"], {
                "datum": r["datum"], "netto": 0, "kategorie_id": r["kategorie_id"],
                "kategorie_name": r["kategorie_name"],
                "steuer_relevant": bool(r["steuer_relevant"]), "steuer_art": r["steuer_art"]})
            if r["netto_w"]:
                try:
                    e["netto"] += ledger.umrechnen(r["netto_w"], r["waehrung"], "EUR", kurse)
                except ledger.LedgerError:
                    pass  # ohne Kurs: Fremdwährung bleibt unberücksichtigt (kein Rateraten)
        if bereich is not None:
            eff = _bereich_je_buchung(user_id)
            return [e for bid_, e in agg.items() if eff.get(bid_, "") == bereich]
        return list(agg.values())

    def _ust_bewegungen(user_id: str, von: str, bis: str) -> list[dict]:
        """Buchungen im Datumsfenster [von, bis] mit EUR-Netto-Effekt (asset/
        liability) + Kategorie/Gegenpartei/Zweck + Beleg-Ref — die Eingabe des
        U-1-Arbeitsvorrats UND der M4-3-Vorsteuer-Warnungen (UStVA, docs/68 §4/§7:
        die Beleg-Kante ``beleg_ref`` trägt die „ABZIEHBAR ohne Beleg"-Warnregel).
        Reine Lese-Operation über die bestehende Ledger-Sicht (Kurse wie
        ``_bewegungen``); berührt den Ledger nie (U-4). ``netto == 0`` (interner
        Transfer) bleibt erhalten — der Vertrag deutet das als ``KEIN_UMSATZ``
        (geklärt), nie als offen."""
        rows = db.get_conn().execute(
            "SELECT b.id, b.datum, b.gegenpartei, b.verwendungszweck, b.kategorie_id, "
            "b.beleg_ref, k.name AS kategorie_name, ko.waehrung AS waehrung, "
            "COALESCE(SUM(CASE WHEN ko.typ IN ('asset','liability') "
            "THEN p.betrag ELSE 0 END),0) AS netto_w "
            "FROM buchungen b "
            "JOIN postings p ON p.buchung_id=b.id AND p.deleted_at IS NULL "
            "JOIN konten ko ON ko.id=p.konto_id "
            "LEFT JOIN kategorien k ON k.id=b.kategorie_id AND k.deleted_at IS NULL "
            "WHERE b.user_id=? AND b.deleted_at IS NULL "
            "AND substr(b.datum,1,10)>=? AND substr(b.datum,1,10)<=? "
            "GROUP BY b.id, ko.waehrung", (user_id, von, bis)).fetchall()
        kurse = _kurse(user_id)
        agg: dict[str, dict] = {}
        for r in rows:
            e = agg.setdefault(r["id"], {
                "id": r["id"], "datum": r["datum"], "netto": 0,
                "kategorie_id": r["kategorie_id"], "kategorie_name": r["kategorie_name"],
                "gegenpartei": r["gegenpartei"], "verwendungszweck": r["verwendungszweck"],
                "beleg_ref": r["beleg_ref"]})
            if r["netto_w"]:
                try:
                    e["netto"] += ledger.umrechnen(r["netto_w"], r["waehrung"], "EUR", kurse)
                except ledger.LedgerError:
                    pass   # ohne Kurs: Fremdwährung unberücksichtigt (kein Raten)
        return list(agg.values())

    def _buchungen_erkennung(user_id: str):
        """Buchungen mit Gegenpartei/Zweck + netto-EUR-Betrag — Eingabe der
        Wiederkehr-Erkennung (``wiederkehr.erkenne_serien``)."""
        rows = db.get_conn().execute(
            "SELECT b.datum, b.gegenpartei, b.verwendungszweck, b.kategorie_id, "
            "k.name AS kategorie_name, "
            "COALESCE(SUM(CASE WHEN ko.typ IN ('asset','liability') "
            "AND ko.waehrung='EUR' THEN p.betrag ELSE 0 END),0) AS netto "
            "FROM buchungen b "
            "JOIN postings p ON p.buchung_id=b.id AND p.deleted_at IS NULL "
            "JOIN konten ko ON ko.id=p.konto_id "
            "LEFT JOIN kategorien k ON k.id=b.kategorie_id AND k.deleted_at IS NULL "
            "WHERE b.user_id=? AND b.deleted_at IS NULL GROUP BY b.id",
            (user_id,)).fetchall()
        return [{"datum": r["datum"], "betrag": r["netto"],
                 "gegenpartei": r["gegenpartei"], "verwendungszweck": r["verwendungszweck"],
                 "kategorie_id": r["kategorie_id"], "kategorie_name": r["kategorie_name"]}
                for r in rows]

    def _serien_gespeichert(user_id: str):
        rows = db.get_conn().execute(
            "SELECT s.id, s.name, s.schluessel, s.betrag, s.waehrung, s.intervall, "
            "s.intervall_tage, s.naechste_faelligkeit, s.kategorie_id, s.richtung, "
            "s.quelle, s.bereich_id, k.name AS kategorie_name FROM serien s "
            "LEFT JOIN kategorien k ON k.id=s.kategorie_id AND k.deleted_at IS NULL "
            "WHERE s.user_id=? AND s.aktiv=1 AND s.deleted_at IS NULL "
            "ORDER BY s.naechste_faelligkeit", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    @router.post("/api/konten")
    def konto_anlegen(body: KontoIn,
                      user: UserContext = Depends(current_user)):
        if body.typ not in ledger.KONTO_TYPEN:
            return JSONResponse(
                {"error": f"Typ muss aus {ledger.KONTO_TYPEN} sein"}, status_code=400)
        if body.waehrung not in ledger.WAEHRUNG_DEZIMAL:
            return JSONResponse(
                {"error": f"Währung unbekannt: {body.waehrung}"}, status_code=400)
        if not _bereich_ok(user.user_id, body.bereich_id):
            return JSONResponse({"error": "Bereich unbekannt"}, status_code=400)
        kid = new_id()
        ts = now_iso()
        db.get_conn().execute(
            "INSERT INTO konten (id, user_id, name, typ, waehrung, bereich_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (kid, user.user_id, body.name.strip() or "Konto", body.typ,
             body.waehrung, body.bereich_id, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "konto_angelegt", {"typ": body.typ})
        return {"ok": True, "id": kid}

    @router.get("/api/konten")
    def konten_liste(user: UserContext = Depends(current_user)):
        rows = db.get_conn().execute(
            "SELECT id, name, typ, waehrung, abgeglichen_bis, bereich_id FROM konten "
            "WHERE user_id=? AND deleted_at IS NULL ORDER BY typ, name",
            (user.user_id,)).fetchall()
        out = []
        for k in rows:
            roh = db.get_conn().execute(
                "SELECT COALESCE(SUM(betrag),0) AS s FROM postings "
                "WHERE konto_id=? AND user_id=? AND deleted_at IS NULL",
                (k["id"], user.user_id)).fetchone()["s"]
            out.append({
                "id": k["id"], "name": k["name"], "typ": k["typ"],
                "waehrung": k["waehrung"], "abgeglichen_bis": k["abgeglichen_bis"] or "",
                "bereich_id": k["bereich_id"] or "",
                "saldo_minor": ledger.anzeige_saldo(roh, k["typ"]),
                "saldo": ledger.format_betrag(
                    ledger.anzeige_saldo(roh, k["typ"]), k["waehrung"])})
        return out

    @router.put("/api/konten/{konto_id}")
    def konto_umbenennen(konto_id: str, body: KontoUpdateIn,
                         user: UserContext = Depends(current_user)):
        if _konto(user.user_id, konto_id) is None:
            return JSONResponse({"error": "Konto unbekannt"}, status_code=404)
        if not body.name.strip():
            return JSONResponse({"error": "Name ist Pflicht"}, status_code=400)
        db.get_conn().execute(
            "UPDATE konten SET name=?, updated_at=? WHERE id=? AND user_id=?",
            (body.name.strip(), now_iso(), konto_id, user.user_id))
        db.get_conn().commit()
        return {"ok": True, "id": konto_id}

    @router.delete("/api/konten/{konto_id}")
    def konto_loeschen(konto_id: str, user: UserContext = Depends(current_user)):
        """Soft-Delete eines Kontos — NUR wenn es keine aktiven Buchungen mehr
        berührt (sonst risse das Löschen Buchungen auseinander). Der Nutzer muss
        die betroffenen Buchungen erst stornieren/umbuchen."""
        conn = db.get_conn()
        if _konto(user.user_id, konto_id) is None:
            return JSONResponse({"error": "Konto unbekannt"}, status_code=404)
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM postings WHERE konto_id=? AND user_id=? "
            "AND deleted_at IS NULL", (konto_id, user.user_id)).fetchone()["n"]
        if n:
            return JSONResponse(
                {"error": f"Konto hat {n} aktive Buchungs-Zeilen — erst stornieren/"
                          "umbuchen, dann löschen."}, status_code=400)
        conn.execute("UPDATE konten SET deleted_at=?, updated_at=? WHERE id=? AND user_id=?",
                     (now_iso(), now_iso(), konto_id, user.user_id))
        conn.commit()
        db.audit(user.user_id, "user", "konto_geloescht", {"konto": konto_id})
        return {"ok": True}

    def _saldo_bis(user_id: str, konto_id: str, typ: str, bis: str) -> int:
        """Anzeige-Saldo eines Kontos bis EINSCHLIESSLICH ``bis`` (für Reconciliation):
        Summe der Postings, deren Buchung am/vor dem Stichtag datiert ist."""
        roh = db.get_conn().execute(
            "SELECT COALESCE(SUM(p.betrag),0) AS s FROM postings p "
            "JOIN buchungen b ON b.id=p.buchung_id "
            "WHERE p.konto_id=? AND p.user_id=? AND p.deleted_at IS NULL "
            "AND b.deleted_at IS NULL AND substr(b.datum,1,10)<=?",
            (konto_id, user_id, bis)).fetchone()["s"]
        return ledger.anzeige_saldo(roh, typ)

    @router.get("/api/konten/{konto_id}/abgleich")
    def konto_abgleich_pruefen(konto_id: str, bis: str, saldo: str | None = None,
                               user: UserContext = Depends(current_user)):
        """Reconciliation-CHECK (read-only): Ledger-Saldo zum Stichtag vs. Auszug-
        Saldo. ``differenz`` = Auszug − Ledger; 0 ⇒ abgeglichen. Vertrauensanker
        für den Double-Entry-Kern (Actual-Muster „abgeglichen bis")."""
        k = _konto(user.user_id, konto_id)
        if k is None:
            return JSONResponse({"error": "Konto unbekannt"}, status_code=404)
        ledger_saldo = _saldo_bis(user.user_id, konto_id, k["typ"], bis)
        out = {"konto_id": konto_id, "waehrung": k["waehrung"], "bis": bis,
               "ledger_saldo": ledger_saldo,
               "ledger_saldo_text": ledger.format_betrag(ledger_saldo, k["waehrung"]),
               "abgeglichen_bis": k["abgeglichen_bis"] or ""}
        if saldo is not None and saldo != "":
            try:
                auszug = ledger.parse_betrag(saldo, k["waehrung"])
            except ledger.LedgerError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            diff = auszug - ledger_saldo
            out.update({"auszug_saldo": auszug, "differenz": diff,
                        "differenz_text": ledger.format_betrag(diff, k["waehrung"]),
                        "abgeglichen": diff == 0})
        return out

    @router.post("/api/konten/{konto_id}/abgleich")
    def konto_abgleich_markieren(konto_id: str, body: AbgleichIn,
                                 user: UserContext = Depends(current_user)):
        """Markiert das Konto als „abgeglichen bis" — NUR wenn Ledger- und Auszug-
        Saldo zum Stichtag exakt übereinstimmen (Differenz 0). Sonst wird die
        Differenz zurückgegeben, damit der Nutzer sie erst auflöst."""
        k = _konto(user.user_id, konto_id)
        if k is None:
            return JSONResponse({"error": "Konto unbekannt"}, status_code=404)
        try:
            auszug = ledger.parse_betrag(body.saldo, k["waehrung"])
        except ledger.LedgerError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        ledger_saldo = _saldo_bis(user.user_id, konto_id, k["typ"], body.bis)
        diff = auszug - ledger_saldo
        if diff != 0:
            return {"ok": False, "abgeglichen": False, "differenz": diff,
                    "differenz_text": ledger.format_betrag(diff, k["waehrung"]),
                    "ledger_saldo_text": ledger.format_betrag(ledger_saldo, k["waehrung"])}
        conn = db.get_conn()
        conn.execute(
            "UPDATE konten SET abgeglichen_bis=?, abgeglichen_saldo=?, updated_at=? "
            "WHERE id=? AND user_id=?", (body.bis, auszug, now_iso(), konto_id, user.user_id))
        conn.commit()
        db.audit(user.user_id, "user", "konto_abgeglichen", {"konto": konto_id, "bis": body.bis})
        return {"ok": True, "abgeglichen": True, "abgeglichen_bis": body.bis}

    @router.post("/api/buchungen")
    def buchung_anlegen(body: BuchungIn,
                        user: UserContext = Depends(current_user)):
        von, nach = _konto(user.user_id, body.von_konto), _konto(user.user_id, body.nach_konto)
        if von is None or nach is None:
            return JSONResponse({"error": "Konto unbekannt"}, status_code=404)
        if not _bereich_ok(user.user_id, body.bereich_id):
            return JSONResponse({"error": "Bereich unbekannt"}, status_code=400)
        try:
            if von["waehrung"] == nach["waehrung"]:
                minor = ledger.parse_betrag(body.betrag, von["waehrung"])
                buchung = ledger.einfache_buchung(
                    body.von_konto, body.nach_konto, minor, notiz=body.notiz)
            else:
                # FX-Umbuchung: empfangenen Betrag nehmen (explizit) oder aus dem
                # hinterlegten Kurs schätzen — dann über Tausch-Konten balancieren.
                betrag_von = ledger.parse_betrag(body.betrag, von["waehrung"])
                if betrag_von <= 0:
                    raise ledger.LedgerError("Betrag muss > 0 sein")
                if body.betrag_nach.strip():
                    betrag_nach = ledger.parse_betrag(body.betrag_nach, nach["waehrung"])
                else:
                    betrag_nach = ledger.pruefe_minor(ledger.umrechnen(
                        betrag_von, von["waehrung"], nach["waehrung"], _kurse(user.user_id)))
                if betrag_nach <= 0:
                    raise ledger.LedgerError("Empfangsbetrag muss > 0 sein")
                buchung = ledger.fx_buchung(
                    body.von_konto, betrag_von, von["waehrung"],
                    body.nach_konto, betrag_nach, nach["waehrung"],
                    _waehrungstausch(user.user_id, von["waehrung"]),
                    _waehrungstausch(user.user_id, nach["waehrung"]),
                    notiz=body.notiz)
        except ledger.LedgerError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        # Erst NACH erfolgreicher Ledger-Prüfung wird persistiert (atomar).
        bid = new_id()
        ts = now_iso()
        datum = _iso_tag(body.datum) or ts[:10]   # M-5: datum ISO-validiert (kein Freitext ⇒ keine CSV-Formel/EÜR-Lücke)
        try:
            with db.transaktion() as conn:
                chronik_naht.pruefe_offen(conn, user.user_id, datum)   # §6.3: 409 im festgeschriebenen Monat
                conn.execute(
                    "INSERT INTO buchungen (id, user_id, notiz, datum, bereich_id, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (bid, user.user_id, body.notiz, datum, body.bereich_id, ts, ts))
                for p in buchung.postings:
                    conn.execute(
                        "INSERT INTO postings (id, user_id, buchung_id, konto_id, betrag, created_at)"
                        " VALUES (?,?,?,?,?,?)",
                        (new_id(), user.user_id, bid, p.konto_id, p.betrag, ts))
                chronik_naht.schreibe_buchung(                          # C-1: Ereignis in DERSELBEN Txn
                    conn, user.user_id, buchung_id=bid, datum=datum, quelle="manuell",
                    postings=[(p.konto_id, p.betrag) for p in buchung.postings],
                    bereich_id=body.bereich_id, notiz=body.notiz)
        except chronik_naht.ZeitraumGesperrt as z:
            return _gesperrt_409(z.zeitraum)
        db.audit(user.user_id, "user", "buchung_angelegt",
                 {"volumen_minor": buchung.volumen})
        return {"ok": True, "id": bid}

    @router.post("/api/buchungen/split")
    def buchung_split(body: SplitIn, user: UserContext = Depends(current_user)):
        """Split-Buchung: EIN Beleg wird in mehrere kategorisierte Zeilen geteilt
        (z. B. Supermarkt 100 € = 70 € Lebensmittel + 30 € Haushalt). Jede Zeile
        wird eine eigene, balancierte Buchung (Bankkonto ↔ Sammelkonto) mit ihrer
        Kategorie — passt 1:1 ins bestehende Ein-Kategorie-je-Buchung-Modell.
        Alles-oder-nichts: erst ALLE Zeilen prüfen, dann persistieren."""
        bank = _konto(user.user_id, body.konto_id)
        if bank is None:
            return JSONResponse({"error": "Konto unbekannt"}, status_code=404)
        if bank["typ"] not in ("asset", "liability"):
            return JSONResponse({"error": "Split-Konto muss ein Bank-/Vermögenskonto sein"},
                                status_code=400)
        if not body.zeilen:
            return JSONResponse({"error": "Mindestens eine Split-Zeile nötig"}, status_code=400)
        geprueft = []
        for z in body.zeilen:
            if z.richtung not in ("ausgabe", "einnahme"):
                return JSONResponse({"error": "richtung muss ausgabe|einnahme sein"}, status_code=400)
            if z.kategorie_id and _kategorie(user.user_id, z.kategorie_id) is None:
                return JSONResponse({"error": "Kategorie unbekannt"}, status_code=404)
            try:
                minor = ledger.parse_betrag(z.betrag, bank["waehrung"])
            except ledger.LedgerError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            if minor <= 0:
                return JSONResponse({"error": "Jeder Zeilen-Betrag muss > 0 sein"}, status_code=400)
            geprueft.append((z, minor))
        ts = now_iso()
        datum = _iso_tag(body.datum) or ts[:10]   # M-5: ISO-validiert (kein Freitext-datum)
        sammel = _sammelkonto(user.user_id, bank["waehrung"])
        notiz = body.notiz or body.gegenpartei
        ids = []
        try:
            with db.transaktion() as conn:
                chronik_naht.pruefe_offen(conn, user.user_id, datum)   # §6.3: alle Zeilen teilen ein Datum
                for z, minor in geprueft:
                    if z.richtung == "ausgabe":
                        buchung = ledger.einfache_buchung(body.konto_id, sammel, minor, notiz=notiz)
                    else:
                        buchung = ledger.einfache_buchung(sammel, body.konto_id, minor, notiz=notiz)
                    bid = new_id()
                    conn.execute(
                        "INSERT INTO buchungen (id, user_id, notiz, datum, gegenpartei, "
                        "verwendungszweck, kategorie_id, quelle, created_at, updated_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (bid, user.user_id, body.notiz, datum, body.gegenpartei, body.notiz,
                         z.kategorie_id, "manuell", ts, ts))
                    for p in buchung.postings:
                        conn.execute(
                            "INSERT INTO postings (id, user_id, buchung_id, konto_id, betrag, created_at)"
                            " VALUES (?,?,?,?,?,?)",
                            (new_id(), user.user_id, bid, p.konto_id, p.betrag, ts))
                    chronik_naht.schreibe_buchung(
                        conn, user.user_id, buchung_id=bid, datum=datum, quelle="manuell",
                        postings=[(p.konto_id, p.betrag) for p in buchung.postings],
                        kategorie_id=z.kategorie_id, notiz=body.notiz,
                        gegenpartei=body.gegenpartei, verwendungszweck=body.notiz)
                    ids.append(bid)
        except chronik_naht.ZeitraumGesperrt as sperr:
            return _gesperrt_409(sperr.zeitraum)
        db.audit(user.user_id, "user", "split_gebucht", {"zeilen": len(ids)})
        return {"ok": True, "ids": ids, "anzahl": len(ids)}

    @router.post("/api/import")
    def daten_import(body: ImportIn, user: UserContext = Depends(current_user)):
        """Universeller Import: Auszug-Inhalt → eine Ledger-Buchung je Bewegung
        (Bankkonto ↔ Sammelkonto „Nicht zugeordnet"). DEDUPE über stabilen Hash:
        erneuter Import desselben Auszugs erzeugt keine Dubletten. Jede Buchung
        läuft durch den geprüften ``ledger``-Kern (unbalanciert erreicht die DB nie)."""
        bank = _konto(user.user_id, body.zielkonto)
        if bank is None:
            return JSONResponse({"error": "Zielkonto unbekannt"}, status_code=404)
        if bank["typ"] not in ("asset", "liability"):
            return JSONResponse(
                {"error": "Zielkonto muss ein Bank-/Vermögenskonto (asset/liability) sein"},
                status_code=400)
        try:
            bewegungen = parse_inhalt(body.inhalt, format=body.format,
                                      profil=body.profil,
                                      standard_waehrung=bank["waehrung"])
        except ImportFehler as e:
            return JSONResponse({"error": f"Import fehlgeschlagen: {e}"}, status_code=400)

        conn = db.get_conn()
        vorhanden = {r["import_hash"] for r in conn.execute(
            "SELECT import_hash FROM buchungen WHERE user_id=? AND import_hash IS NOT NULL",
            (user.user_id,)).fetchall()}
        sammel = _sammelkonto(user.user_id, bank["waehrung"])
        fmt = body.format if body.format != "auto" else "auto"
        ts = now_iso()
        importiert = dupliziert = uebersprungen = 0
        fehler: list[str] = []
        gesehen: set[str] = set()
        with db.transaktion() as conn:
            for b in bewegungen:
                if b.waehrung != bank["waehrung"]:
                    uebersprungen += 1
                    fehler.append(f"{b.datum}: Währung {b.waehrung} ≠ Konto {bank['waehrung']} (FX v1 nicht unterstützt)")
                    continue
                h = bewegung_hash(b)
                if h in vorhanden or h in gesehen:
                    dupliziert += 1
                    continue
                buchung = als_buchung(b, body.zielkonto, sammel)
                if buchung is None:                       # 0-€-Bewegung
                    uebersprungen += 1
                    continue
                if chronik_naht.ist_gesperrt(conn, user.user_id, b.datum):
                    uebersprungen += 1                        # §6.3: nicht in festgeschriebene Monate importieren
                    fehler.append(f"{b.datum}: Zeitraum festgeschrieben — übersprungen")
                    continue
                gesehen.add(h)
                bid = new_id()
                conn.execute(
                    "INSERT INTO buchungen (id, user_id, notiz, datum, gegenpartei, "
                    "verwendungszweck, import_hash, quelle, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (bid, user.user_id, buchung.notiz, b.datum, b.gegenpartei,
                     b.verwendungszweck, h, f"import:{fmt}", ts, ts))
                for p in buchung.postings:
                    conn.execute(
                        "INSERT INTO postings (id, user_id, buchung_id, konto_id, betrag, created_at)"
                        " VALUES (?,?,?,?,?,?)",
                        (new_id(), user.user_id, bid, p.konto_id, p.betrag, ts))
                chronik_naht.schreibe_buchung(
                    conn, user.user_id, buchung_id=bid, datum=b.datum, quelle=f"import:{fmt}",
                    postings=[(p.konto_id, p.betrag) for p in buchung.postings],
                    notiz=buchung.notiz, gegenpartei=b.gegenpartei, verwendungszweck=b.verwendungszweck)
                importiert += 1
        # Teil B: frisch importierte Bewegungen sofort gegen die Regeln prüfen.
        kategorisiert = _regeln_anwenden(db, user.user_id)
        db.audit(user.user_id, "user", "daten_importiert",
                 {"importiert": importiert, "dupliziert": dupliziert,
                  "format": fmt, "konto": body.zielkonto})
        return {"ok": True, "importiert": importiert, "dupliziert": dupliziert,
                "uebersprungen": uebersprungen, "auto_kategorisiert": kategorisiert,
                "fehler": fehler[:20], "gefunden": len(bewegungen)}

    @router.post("/api/import/vorschau")
    def import_vorschau(body: ImportIn, user: UserContext = Depends(current_user)):
        """Import-ASSISTENT (Dry-Run): parst den Auszug und zeigt VORHER, was
        passieren würde — neu vs. Dublette (stabiler Hash) + Regel-Kategorie-
        Vorschlag je Zeile. Schreibt NICHTS. Der Nutzer bestätigt dann mit
        POST /api/import."""
        bank = _konto(user.user_id, body.zielkonto)
        if bank is None:
            return JSONResponse({"error": "Zielkonto unbekannt"}, status_code=404)
        if bank["typ"] not in ("asset", "liability"):
            return JSONResponse({"error": "Zielkonto muss ein Bank-/Vermögenskonto sein"},
                                status_code=400)
        try:
            bewegungen = parse_inhalt(body.inhalt, format=body.format, profil=body.profil,
                                      standard_waehrung=bank["waehrung"])
        except ImportFehler as e:
            return JSONResponse({"error": f"Vorschau fehlgeschlagen: {e}"}, status_code=400)
        conn = db.get_conn()
        vorhanden = {r["import_hash"] for r in conn.execute(
            "SELECT import_hash FROM buchungen WHERE user_id=? AND import_hash IS NOT NULL",
            (user.user_id,)).fetchall()}
        regeln = [dict(r) for r in conn.execute(
            "SELECT id, muster, feld, kategorie_id, prioritaet, treffer, created_at FROM regeln "
            "WHERE user_id=? AND deleted_at IS NULL", (user.user_id,)).fetchall()]
        kat_namen = {r["id"]: r["name"] for r in conn.execute(
            "SELECT id, name FROM kategorien WHERE user_id=? AND deleted_at IS NULL",
            (user.user_id,)).fetchall()}
        neu = dupliziert = waehrung_fehler = 0
        gesehen: set[str] = set()
        zeilen = []
        for b in bewegungen:
            h = bewegung_hash(b)
            dup = h in vorhanden or h in gesehen
            gesehen.add(h)
            if dup:
                dupliziert += 1
            elif b.waehrung != bank["waehrung"]:
                waehrung_fehler += 1
            else:
                neu += 1
            regel = regelmodul.finde_regel(regeln, {
                "gegenpartei": b.gegenpartei, "verwendungszweck": b.verwendungszweck, "notiz": ""})
            kvor = kat_namen.get(regel["kategorie_id"]) if regel else None
            if len(zeilen) < 200:
                zeilen.append({
                    "datum": b.datum, "gegenpartei": b.gegenpartei,
                    "verwendungszweck": b.verwendungszweck, "waehrung": b.waehrung,
                    "betrag": ledger.format_betrag(b.betrag_minor, b.waehrung),
                    "betrag_minor": b.betrag_minor, "dupliziert": dup,
                    "kategorie_vorschlag": kvor})
        return {"ok": True, "gefunden": len(bewegungen), "neu": neu,
                "dupliziert": dupliziert, "waehrung_fehler": waehrung_fehler,
                "zeilen": zeilen, "konto_waehrung": bank["waehrung"]}

    # =================== Teil B: Buchungs-Liste (Filter/Suche) ===============

    def _buchungen_laden(user_id: str, konto=None, kategorie=None, q=None,
                         von=None, bis=None, limit=200, bereich=None):
        """Gefilterte Transaktionsliste (Konto/Kategorie/Zeitraum + Volltext-
        Suche). ``betrag_minor`` = netto-Vermögenseffekt (+ Zufluss, − Abfluss)
        in der Währung der Buchung; ``waehrung`` nennt sie. Berührt eine Buchung
        MEHRERE Währungen (FX-Umbuchung), wird in EUR ausgewiesen (≈).
        Gemeinsame Basis von Listen-Endpoint UND Export."""
        bedingungen = ["b.user_id=?", "b.deleted_at IS NULL"]
        params: list = [user_id]
        if von:
            bedingungen.append("substr(b.datum,1,10) >= ?"); params.append(von)
        if bis:
            bedingungen.append("substr(b.datum,1,10) <= ?"); params.append(bis)
        if kategorie == "_nicht":
            bedingungen.append("b.kategorie_id IS NULL")
        elif kategorie:
            bedingungen.append("b.kategorie_id = ?"); params.append(kategorie)
        if q:
            bedingungen.append("(b.notiz LIKE ? OR b.gegenpartei LIKE ? OR b.verwendungszweck LIKE ?)")
            like = f"%{q}%"; params += [like, like, like]
        if konto:
            bedingungen.append(
                "EXISTS (SELECT 1 FROM postings pk WHERE pk.buchung_id=b.id "
                "AND pk.konto_id=? AND pk.deleted_at IS NULL)")
            params.append(konto)
        if bereich:
            # Effektiver Bereich: Buchungs-Override ODER (kein Override) ein berührtes
            # asset/liability-Konto dieses Bereichs (= Konto-Default erbt auf die Buchung).
            bedingungen.append(
                "(b.bereich_id = ? OR (b.bereich_id = '' AND EXISTS "
                "(SELECT 1 FROM postings pb JOIN konten kb ON kb.id=pb.konto_id "
                "WHERE pb.buchung_id=b.id AND pb.deleted_at IS NULL "
                "AND kb.typ IN ('asset','liability') AND kb.bereich_id = ?)))")
            params += [bereich, bereich]
        where = " AND ".join(bedingungen)
        # Pro (Buchung, Währung) den asset/liability-netto holen; in Python je
        # Buchung zusammenführen (Limit auf Buchungen, nicht auf Währungs-Zeilen).
        _select = (
            "b.id, b.datum, b.created_at, b.notiz, b.gegenpartei, "
            "b.verwendungszweck, b.kategorie_id, b.quelle, b.beleg_ref, b.beleg_titel, "
            "b.bereich_id, k.name AS kategorie_name, ko.waehrung AS waehrung, "
            "COALESCE(SUM(CASE WHEN ko.typ IN ('asset','liability') "
            "THEN p.betrag ELSE 0 END),0) AS netto_w")
        _joins = (
            "FROM buchungen b "
            "JOIN postings p ON p.buchung_id=b.id AND p.deleted_at IS NULL "
            "JOIN konten ko ON ko.id=p.konto_id "
            "LEFT JOIN kategorien k ON k.id=b.kategorie_id AND k.deleted_at IS NULL")
        # Z-3b (28.06., geld-kritisch/test-getrieben): bei positivem ``limit`` die Top-N
        # Buchungen ZUERST b-seitig bestimmen (CTE, deterministische Gesamtordnung
        # ``substr(datum,1,10), created_at, id`` DESC — identisch zur Python-Sortierung
        # unten) und NUR diese aggregieren — statt die ganze gefilterte Tabelle zu laden
        # und in Python zu schneiden (O(alle)→O(N)). Alle WHERE-Bedingungen sind b-seitig
        # (Konto/Bereich via EXISTS), daher in der CTE auswertbar. ``limit<=0`` (Export)
        # lädt unverändert ALLES (s. Z-3a). Beweis-Äquivalenz: ``limit=N`` == erste N von
        # ``limit=0`` (gleiche Gesamtordnung) — test_app_buchungen_limit.
        if limit and limit > 0:
            n = min(limit, 5000)
            sql = (f"WITH topn AS (SELECT b.id FROM buchungen b WHERE {where} "
                   f"ORDER BY substr(b.datum,1,10) DESC, b.created_at DESC, b.id DESC "
                   f"LIMIT ?) "
                   f"SELECT {_select} {_joins} JOIN topn ON topn.id = b.id "
                   f"GROUP BY b.id, ko.waehrung")
            rows = db.get_conn().execute(sql, (*params, n)).fetchall()
        else:
            rows = db.get_conn().execute(
                f"SELECT {_select} {_joins} WHERE {where} GROUP BY b.id, ko.waehrung",
                (*params,)).fetchall()
        kurse = _kurse(user_id)
        je_buchung: dict[str, dict] = {}
        for r in rows:
            e = je_buchung.get(r["id"])
            if e is None:
                e = je_buchung[r["id"]] = {
                    "id": r["id"], "datum": r["datum"][:10], "_sort": r["created_at"],
                    "notiz": r["notiz"], "gegenpartei": r["gegenpartei"],
                    "verwendungszweck": r["verwendungszweck"], "kategorie_id": r["kategorie_id"],
                    "kategorie_name": r["kategorie_name"], "quelle": r["quelle"],
                    "beleg_ref": r["beleg_ref"], "beleg_titel": r["beleg_titel"],
                    "bereich_id": r["bereich_id"] or "", "_cur": {}}
            if r["netto_w"]:
                e["_cur"][r["waehrung"]] = e["_cur"].get(r["waehrung"], 0) + r["netto_w"]
        out = []
        for e in je_buchung.values():
            cur = e.pop("_cur")
            if len(cur) == 1:
                (w, val), = cur.items()
                e["waehrung"], e["betrag_minor"] = w, val
                e["betrag"] = ledger.format_betrag(val, w)
            else:                                     # FX/Transfer (mehrere Whg) → EUR
                eur = 0
                for w, val in cur.items():
                    try:
                        eur += ledger.umrechnen(val, w, "EUR", kurse)
                    except ledger.LedgerError:
                        pass
                e["waehrung"], e["betrag_minor"] = "EUR", eur
                e["betrag"] = ledger.format_betrag(eur, "EUR")
            out.append(e)
        # Deterministische Gesamtordnung (datum, created_at, id) DESC — der id-Tie-Break
        # macht die Reihenfolge eindeutig UND deckungsgleich mit der CTE-Top-N-Auswahl
        # (Z-3b) oben, sodass ``limit=N`` exakt die ersten N von ``limit=0`` liefert.
        # Z-3a-Garantie bleibt: ``limit<=0`` ⇒ UNBEGRENZT (Voll-Export schneidet NIE still
        # bei 5000 ab = kein Datenverlust); positiver limit ist bereits SQL-seitig auf
        # min(limit,5000) gedeckelt (kein Python-Slice mehr nötig).
        out.sort(key=lambda e: (e["datum"], e["_sort"], e["id"]), reverse=True)
        for e in out:
            e.pop("_sort", None)
        return out

    @router.get("/api/buchungen")
    def buchungen_liste(konto: str | None = None, kategorie: str | None = None,
                        q: str | None = None, von: str | None = None,
                        bis: str | None = None, limit: int = 200,
                        bereich: str | None = None,
                        user: UserContext = Depends(current_user)):
        # max(1,..) ⇒ die Liste kann nie versehentlich unbegrenzt werden (limit<=0
        # ist allein dem Voll-Export vorbehalten).
        return _buchungen_laden(user.user_id, konto, kategorie, q, von, bis,
                                max(1, limit), bereich=bereich)

    @router.get("/api/buchungen/export")
    def buchungen_export(format: str = "csv", konto: str | None = None,
                         kategorie: str | None = None, q: str | None = None,
                         von: str | None = None, bis: str | None = None,
                         user: UserContext = Depends(current_user)):
        """Export der (gefilterten) Transaktionsliste als CSV oder JSON (Download)
        — der Alltags-Export neben DSGVO-Voll-Export und Steuer-EÜR. Aggregierte
        Sicht ohne Geheimnisse ⇒ Stufe 'lokal'."""
        if format not in ("csv", "json"):
            return JSONResponse({"error": "format muss csv|json sein"}, status_code=400)
        zeilen = _buchungen_laden(user.user_id, konto, kategorie, q, von, bis, limit=0)  # 0=ALLES
        db.audit(user.user_id, "user", "buchungen_exportiert",
                 {"format": format, "anzahl": len(zeilen)})
        dateiname = f"dizz-money-transaktionen.{format}"
        if format == "json":
            import json as _json
            return PlainTextResponse(
                _json.dumps(zeilen, ensure_ascii=False, indent=2),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{dateiname}"'})
        import csv as _csv
        import io as _io
        puffer = _io.StringIO()
        schreiber = _csv.writer(puffer, delimiter=";")
        schreiber.writerow(["Datum", "Gegenpartei", "Verwendungszweck", "Kategorie",
                            "Betrag", "Währung", "Quelle", "Notiz"])
        for z in zeilen:
            schreiber.writerow([z["datum"], csv_safe(z["gegenpartei"]), csv_safe(z["verwendungszweck"]),
                               csv_safe(z["kategorie_name"] or ""), z["betrag"], z.get("waehrung", "EUR"),
                               z["quelle"], csv_safe(z["notiz"])])
        return PlainTextResponse(
            puffer.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{dateiname}"'})

    @router.post("/api/buchungen/{buchung_id}/kategorie")
    def buchung_kategorisieren(buchung_id: str, body: KategorieZuweisungIn,
                               user: UserContext = Depends(current_user)):
        """Ordnet einer Buchung eine Kategorie zu (oder entfernt sie). Mit
        ``lernen=true`` entsteht aus der Bestätigung eine Regel (Muster aus der
        Gegenpartei) — so kategorisiert die App künftige gleichartige Buchungen."""
        conn = db.get_conn()
        b = conn.execute(
            "SELECT * FROM buchungen WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (buchung_id, user.user_id)).fetchone()
        if b is None:
            return JSONResponse({"error": "Buchung unbekannt"}, status_code=404)
        if body.kategorie_id is not None and _kategorie(user.user_id, body.kategorie_id) is None:
            return JSONResponse({"error": "Kategorie unbekannt"}, status_code=404)
        try:
            with db.transaktion() as conn:
                chronik_naht.pruefe_offen(conn, user.user_id, b["datum"])   # §6.2: 409 im versiegelten Zeitraum
                conn.execute("UPDATE buchungen SET kategorie_id=?, updated_at=? WHERE id=?",
                             (body.kategorie_id, now_iso(), buchung_id))
                chronik_naht.schreibe_umklassung(conn, user.user_id, buchung_id=buchung_id,
                                                 kategorie_id=body.kategorie_id)
        except chronik_naht.ZeitraumGesperrt as sperr:
            return _gesperrt_409(sperr.zeitraum)
        gelernt = None
        if body.lernen and body.kategorie_id:
            muster, feld = regelmodul.lern_muster({
                "gegenpartei": b["gegenpartei"], "verwendungszweck": b["verwendungszweck"],
                "notiz": b["notiz"]})
            if muster:
                # Beispiel-Bereich der Buchung mitlernen ⇒ künftige Treffer fallen auch in diesen Bereich.
                gelernt = _regel_lernen(user.user_id, muster, feld, body.kategorie_id,
                                        bereich_id=b["bereich_id"] or "")
        db.audit(user.user_id, "user", "buchung_kategorisiert",
                 {"kategorie": body.kategorie_id, "gelernt": bool(gelernt)})
        return {"ok": True, "gelernt": gelernt}

    @router.delete("/api/buchungen/{buchung_id}")
    def buchung_stornieren(buchung_id: str, user: UserContext = Depends(current_user)):
        """Storniert eine Buchung: Soft-Delete der Buchung UND aller ihrer
        Postings (zusammen — eine halb gelöschte Buchung gäbe es sonst). Da eine
        ganze balancierte Buchung verschwindet, bleibt die globale Konsistenz
        (Summe aller aktiven Postings = 0) gewahrt. Das Audit-Log bleibt."""
        conn = db.get_conn()
        b = conn.execute(
            "SELECT datum, beleg_ref FROM buchungen WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (buchung_id, user.user_id)).fetchone()
        if b is None:
            return JSONResponse({"error": "Buchung unbekannt"}, status_code=404)
        original = conn.execute(                      # Original-Postings für das self-contained Storno-Ereignis
            "SELECT konto_id, betrag FROM postings WHERE buchung_id=? AND deleted_at IS NULL",
            (buchung_id,)).fetchall()
        ts = now_iso()
        try:
            with db.transaktion() as conn:
                # §6.3: Storno im festgeschriebenen Monat ⇒ 409 (Gegenbuchung statt Soft-Delete — GoBD)
                chronik_naht.pruefe_offen(conn, user.user_id, b["datum"])
                conn.execute("UPDATE buchungen SET deleted_at=?, updated_at=? WHERE id=?",
                             (ts, ts, buchung_id))
                conn.execute("UPDATE postings SET deleted_at=? WHERE buchung_id=? AND deleted_at IS NULL",
                             (ts, buchung_id))
                chronik_naht.schreibe_storno(
                    conn, user.user_id, buchung_id=buchung_id, datum_storno=ts[:10],
                    gegen_postings=[(r["konto_id"], r["betrag"]) for r in original])
        except chronik_naht.ZeitraumGesperrt as sperr:
            return _gesperrt_409(sperr.zeitraum)
        # Erst lokal stornieren (committet), DANN best-effort dem Ziel das Lösen melden (V15-
        # Audit-Fix a): War ein Beleg verknüpft, räumt Admin seine Rück-Referenz, sonst bliebe
        # ein verwaister „verwendet in 1 Buchung"-Hinweis. Reihenfolge robust = wie Beleg-Entfernen.
        _loese_beleg_verknuepfung(user.user_id, buchung_id, b["beleg_ref"])
        db.audit(user.user_id, "user", "buchung_storniert", {"buchung": buchung_id})
        return {"ok": True}

    # ============ V-BIZZI-1: GoBD-Festschreibung + Chronik-Status (docs/80 §6.3) ============
    @router.get("/api/chronik/status")
    def chronik_status_ep(user: UserContext = Depends(current_user)):
        """Chronik-Rückstand · letzte Epoche/Siegel-Zeit · Chronist-Zustand · fork_verdacht (B1-UI)."""
        return chronik_naht.chronik_status(db.get_conn())

    @router.get("/api/festschreibungen")
    def festschreibungen_liste(user: UserContext = Depends(current_user)):
        rows = db.get_conn().execute(
            "SELECT zeitraum, status, beweisgrad, bis_i, siegel_epoche, siegel_hash, created_at, updated_at "
            "FROM festschreibungen WHERE user_id=? AND deleted_at IS NULL ORDER BY zeitraum DESC",
            (user.user_id,)).fetchall()
        return [dict(r) for r in rows]

    @router.post("/api/festschreibung")
    def festschreibung_anlegen(body: FestschreibungIn, user: UserContext = Depends(current_user)):
        """§6.3: schreibt einen abgeschlossenen Monat fest — die Monats-Sperre IST eine Siegel-Referenz.
        Schritte (2)+(3) laufen in EINER Txn (salden_hash unter der Sperre), dann flush_und_warte NACH
        dem Commit (BZ-C-5). Die Quittung trägt Epoche + Siegel-Hash + Beweisgrad — ein kryptographischer
        Beweis, kein Toast. Crash zwischen (3) und (5) ⇒ idempotente Nachholung (Zeile bleibt 'offen')."""
        zeitraum = (body.zeitraum or "").strip()
        if not (len(zeitraum) == 7 and zeitraum[4] == "-"
                and zeitraum[:4].isdigit() and zeitraum[5:].isdigit() and "01" <= zeitraum[5:] <= "12"):
            return JSONResponse({"error": "zeitraum muss 'YYYY-MM' sein"}, status_code=400)
        if zeitraum >= now_iso()[:7]:                 # Wächter (1): Zeitraum muss vollständig vergangen sein
            return JSONResponse({"error": "Zeitraum ist noch nicht abgeschlossen"}, status_code=400)
        conn0 = db.get_conn()
        vorhanden = conn0.execute(
            "SELECT status FROM festschreibungen WHERE user_id=? AND zeitraum=? AND deleted_at IS NULL",
            (user.user_id, zeitraum)).fetchone()
        if vorhanden and vorhanden["status"] == "versiegelt":
            return JSONResponse({"error": f"Zeitraum {zeitraum} ist bereits festgeschrieben"}, status_code=409)
        beweisgrad = chronik_naht.beweisgrad_fuer(zeitraum, chronik_naht.lies_stichtag(conn0))
        luecken = chronik_naht.offene_vormonate_mit_buchungen(conn0, user.user_id, zeitraum)
        if vorhanden is None:
            # (2)+(3) in EINER Txn: salden_hash INNERHALB der Schreibsperre + Zeile 'offen' + Ereignis (BZ-C-5)
            with db.transaktion() as conn:
                sh, _salden = chronik_naht.salden_hash_des_zeitraums(conn, zeitraum)
                bis_i = chronik_naht.outbox_spitze(conn)
                ts = now_iso()
                conn.execute(
                    "INSERT INTO festschreibungen (id,user_id,zeitraum,status,bis_i,salden_hash,beweisgrad,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (new_id(), user.user_id, zeitraum, "offen", bis_i, sh, beweisgrad, ts, ts))
                chronik_naht.schreibe_festschreibung(conn, user.user_id, zeitraum=zeitraum,
                                                     bis_i=bis_i, salden_hash=sh, beweisgrad=beweisgrad)
        # (4) flush_und_warte → Siegel (Chronist tot ⇒ Fehler, nie „ok", C-9). (5) Zeile 'versiegelt' + Referenzen.
        try:
            siegel = chronik_naht.baue_chronist(db.db_path).flush_und_warte()
        except Exception as e:  # noqa: BLE001 — C-9: kein „ok" ohne Siegel; die Zeile bleibt 'offen' (idempotent)
            return JSONResponse(
                {"error": f"Chronist nicht verfügbar — Siegel ausstehend, bitte erneut auslösen ({e})",
                 "zeitraum": zeitraum, "status": "offen"}, status_code=503)
        siegel_hash = chronik.siegel_hash(siegel)
        conn0.execute(
            "UPDATE festschreibungen SET status='versiegelt', siegel_epoche=?, siegel_hash=?, updated_at=? "
            "WHERE user_id=? AND zeitraum=?",
            (siegel["epoche"], siegel_hash, now_iso(), user.user_id, zeitraum))
        conn0.commit()
        db.audit(user.user_id, "user", "festschreibung",
                 {"zeitraum": zeitraum, "epoche": siegel["epoche"], "beweisgrad": beweisgrad})
        antwort = {"ok": True, "zeitraum": zeitraum, "epoche": siegel["epoche"],
                   "siegel_hash": siegel_hash, "beweisgrad": beweisgrad}
        if luecken:
            antwort["hinweis_offene_vormonate"] = luecken   # Lücken-Ehrlichkeit (kein Zwang)
        return antwort

    # =================== V9: Money → Memory (docs/26) ======================
    def _archiviere_beleg(user_id: str, buchung_id: str,
                          explizit: bool = False) -> dict[str, Any]:
        """Reicht eine Buchung als Beleg-Notiz an Dizz Memory weiter (Core-Relay,
        V9 docs/26). **Immer `sensibel=True`** (Finanzdaten ⇒ Memory-KI nur lokal,
        docs/26 §5). NIE ein Echtgeld-/Aktions-Auslöser — nur Daten ablegen.
        Archiv-Regel je (finanzen, beleg) gated; ``explizit`` (Nutzer-Knopf) schlägt
        jede Regel. Best-effort (wirft nie). Herkunftslabel „Money" zentral via Memory."""
        from appkit.querverbindung import archiviere
        kopf = db.get_conn().execute(
            "SELECT datum FROM buchungen WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (buchung_id, user_id)).fetchone()
        if kopf is None:
            return {"ok": False, "fehler": "Buchung unbekannt"}
        tag = (kopf["datum"] or "")[:10]
        treffer = [b for b in _buchungen_laden(user_id, von=tag, bis=tag, limit=1000)
                   if b["id"] == buchung_id]
        if not treffer:
            return {"ok": False, "fehler": "Buchung unbekannt"}
        b = treffer[0]
        zeilen = [f"**Datum:** {b['datum']} · **Betrag:** {b['betrag']} · "
                  f"**Kategorie:** {b['kategorie_name'] or '—'} · **Quelle:** {b['quelle']}"]
        if (b.get("gegenpartei") or "").strip():
            zeilen.append(f"**Gegenpartei:** {b['gegenpartei'].strip()}")
        if (b.get("verwendungszweck") or "").strip():
            zeilen += ["", b["verwendungszweck"].strip()]
        if (b.get("notiz") or "").strip():
            zeilen += ["", "_Notiz:_ " + b["notiz"].strip()]
        inhalt = "\n".join(zeilen).strip()
        titel = "Beleg · " + ((b.get("gegenpartei") or "").strip()
                              or (b.get("verwendungszweck") or "").strip()[:50] or b["datum"])
        tags = [b["kategorie_name"]] if (b.get("kategorie_name") or "").strip() else []
        return archiviere("finanzen", titel, inhalt, strom="beleg",
                          ref="finanzen:beleg:" + buchung_id,
                          quelle="finanzen:beleg:" + buchung_id, tags=tags,
                          sensibel=True, explizit=explizit, http_post=archiv_post)

    @router.post("/api/buchungen/{buchung_id}/archivieren")
    def buchung_archivieren_ep(buchung_id: str,
                               user: UserContext = Depends(current_user)):
        """„In Memory archivieren" (Nutzer-Zuruf): schickt den Beleg explizit an
        Dizz Memory (sensibel) — schlägt jede Archiv-Regel (V9, docs/26)."""
        if db.get_conn().execute(
                "SELECT id FROM buchungen WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (buchung_id, user.user_id)).fetchone() is None:
            return JSONResponse({"error": "Buchung unbekannt"}, status_code=404)
        ergebnis = _archiviere_beleg(user.user_id, buchung_id, explizit=True)
        db.audit(user.user_id, "user", "beleg_archiviert",
                 {"buchung": buchung_id, "status": ergebnis.get("status")})
        return ergebnis

    # =================== V15: Beleg-Verknüpfung Money↔Admin (docs/26 §12) ====
    @router.get("/api/belege-auswahl")
    def belege_auswahl_ep(q: str = "", user: UserContext = Depends(current_user)):
        """V15-Lookup: holt die verknüpfbaren Belege/Dokumente aus Dizz Admin (über den
        Core-Relay) für die Beleg-Auswahl. Best-effort — leere Liste, wenn Admin/Core offline."""
        from appkit.querverbindung import belege_holen
        res = belege_holen("admin", q=q, limit=50, http_get=belege_get)
        return {"ok": bool(res.get("ok")), "belege": res.get("belege", []),
                "fehler": res.get("fehler", "")}

    @router.post("/api/buchungen/{buchung_id}/beleg")
    def buchung_beleg_setzen(buchung_id: str, body: BelegIn,
                             user: UserContext = Depends(current_user)):
        """V15: knüpft ein Admin-Dokument als Beleg an die Buchung. Money speichert die
        Vorwärts-Referenz (``beleg_ref``) UND meldet Admin die Rück-Referenz
        (``verknuepfe``) ⇒ bidirektional. Nur Daten, NIE ein Echtgeld-/Aktions-Auslöser."""
        ref = (body.ref or "").strip()
        if not ref.startswith("admin:dokument:"):
            return JSONResponse({"error": "ungültige Beleg-Referenz"}, status_code=400)
        conn = db.get_conn()
        row = conn.execute(
            "SELECT datum, gegenpartei, verwendungszweck, notiz, beleg_ref FROM buchungen "
            "WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (buchung_id, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Buchung unbekannt"}, status_code=404)
        alt_ref = (row["beleg_ref"] or "").strip()      # ggf. vorher schon ein Beleg verknüpft
        titel = (body.titel or "").strip()
        # §6.2: Beleg-Anhängen ist AUCH im versiegelten Zeitraum erlaubt (verbessert die
        # Nachvollziehbarkeit, ändert keine Werte) — daher kein pruefe_offen, aber money.beleg.
        with db.transaktion() as conn:
            conn.execute("UPDATE buchungen SET beleg_ref=?, beleg_titel=?, updated_at=? "
                         "WHERE id=? AND user_id=?",
                         (ref, titel, now_iso(), buchung_id, user.user_id))
            chronik_naht.schreibe_beleg(conn, user.user_id, buchung_id=buchung_id, titel=titel, ref=ref)
        # Wird ein ANDERER Beleg gesetzt, erst die alte Rück-Referenz bei Admin lösen — sonst bliebe
        # auf dem alten Dokument ein verwaister „verwendet in N"-Hinweis (Audit-Runde 4, H-18).
        if alt_ref and alt_ref != ref:
            _loese_beleg_verknuepfung(user.user_id, buchung_id, alt_ref)
        # Rück-Referenz an Admin (best-effort; die lokale Verknüpfung steht auch ohne Admin).
        # von_titel = sprechendster Buchungs-Bezug: Gegenpartei/Zweck (Import) ⇒ Notiz (manuell) ⇒ Datum.
        # BEWUSST nur ein KURZER Anzeige-Titel (max. 60 Z., Übergabe-Vertrag docs/23: die
        # eigentlichen Finanzdaten bleiben bei der Quelle Money/`hoch`; an Admin/`normal`
        # reist nur das Anzeige-Label für „verwendet in N Buchungen").
        von_titel = ((row["gegenpartei"] or "").strip()
                     or (row["verwendungszweck"] or "").strip()
                     or (row["notiz"] or "").strip() or (row["datum"] or ""))[:60]
        from appkit.querverbindung import verknuepfe
        erg = verknuepfe("finanzen", "finanzen:buchung:" + buchung_id, von_titel, ref,
                         ziel="admin", http_post=verknuepfung_post)
        db.audit(user.user_id, "user", "beleg_verknuepft",
                 {"buchung": buchung_id, "ziel_ref": ref, "rueck": erg.get("status", "fehler")})
        return {"ok": True, "beleg_ref": ref, "beleg_titel": titel,
                "admin": erg.get("status", "fehler")}

    def _loese_beleg_verknuepfung(user_id: str, buchung_id: str, beleg_ref: str) -> None:
        """V15-Audit-Fix (a): meldet Admin, dass der Beleg-Link gelöst ist (Storno/Beleg
        entfernt) ⇒ Admin räumt seine Rück-Referenz, kein verwaister „verwendet in N"-
        Hinweis. Best-effort (wirft nie)."""
        if not (beleg_ref or "").strip().startswith("admin:dokument:"):
            return
        from appkit.querverbindung import loese_verknuepfung
        # Kurzes Timeout (2,5 s statt 5 s): ist Admin/Core OFFLINE, soll der Storno/das Beleg-
        # Entfernen die Antwort an den Nutzer nicht spürbar verzögern (H-18, lokal <100 ms).
        loese_verknuepfung("finanzen", "finanzen:buchung:" + buchung_id, beleg_ref,
                           ziel="admin", timeout=2.5, http_post=verknuepfung_post)

    @router.delete("/api/buchungen/{buchung_id}/beleg")
    def buchung_beleg_loeschen(buchung_id: str, user: UserContext = Depends(current_user)):
        """V15: die Beleg-Verknüpfung entfernen — lokal UND beim Ziel (Admin räumt seine
        Rück-Referenz, sonst bliebe ein verwaister Hinweis; Audit-Fix 17.06.)."""
        conn = db.get_conn()
        row = conn.execute("SELECT datum, beleg_ref FROM buchungen WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (buchung_id, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Buchung unbekannt"}, status_code=404)
        alt_ref = row["beleg_ref"]
        try:
            with db.transaktion() as conn:
                # §6.2: Beleg-Entfernen im versiegelten Zeitraum ⇒ 409 (offen ⇒ erlaubt + money.beleg)
                chronik_naht.pruefe_offen(conn, user.user_id, row["datum"])
                conn.execute("UPDATE buchungen SET beleg_ref='', beleg_titel='', updated_at=? "
                             "WHERE id=? AND user_id=?", (now_iso(), buchung_id, user.user_id))
                chronik_naht.schreibe_beleg(conn, user.user_id, buchung_id=buchung_id)  # leere Hashes = Entfernung
        except chronik_naht.ZeitraumGesperrt as sperr:
            return _gesperrt_409(sperr.zeitraum)
        _loese_beleg_verknuepfung(user.user_id, buchung_id, alt_ref)
        db.audit(user.user_id, "user", "beleg_entfernt", {"buchung": buchung_id})
        return {"ok": True}

    # =================== V14: Trading & Steuer (docs/26 §13) ================
    # Money = die steuerlich maßgebliche Echtgeld-/Belegschicht für Trading-Gewinne.
    # KEINE Steuerberatung — ein Schätz-/Dokumentationswerkzeug (Engine: trading_steuer).
    def _trading_config(user_id: str):
        conn = db.get_conn()
        row = conn.execute("SELECT * FROM trading_config WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            # Erstanlage mit den gewählten Defaults (Nutzer 17.06.: KiSt 9 %).
            conn.execute(
                "INSERT INTO trading_config (user_id, pauschbetrag_rest_cent, freigrenze_rest_cent, "
                "persoenlicher_satz, kirchensteuer_satz, updated_at) VALUES (?,?,?,?,?,?)",
                (user_id, tsteuer.SPARER_PAUSCHBETRAG_CENT, tsteuer.FREIGRENZE_SPOT_CENT,
                 0.42, 0.09, now_iso()))
            conn.commit()
            row = conn.execute("SELECT * FROM trading_config WHERE user_id=?", (user_id,)).fetchone()
        return row

    def _eur(cent: int) -> str:
        return ledger.format_betrag(int(cent or 0), "EUR")

    def _iso_tag(s: str) -> str | None:
        """Validiert ein Tagesdatum (YYYY-MM-DD) und gibt es normalisiert zurück;
        None bei ungültigem/leerem Datum (statt es still nicht zu erfassen)."""
        from datetime import date as _date
        try:
            return _date.fromisoformat((s or "").strip()[:10]).isoformat()
        except (ValueError, TypeError):
            return None

    @router.get("/api/trading/config")
    def trading_config_get(user: UserContext = Depends(current_user)):
        c = _trading_config(user.user_id)
        return {"pauschbetrag_rest_cent": c["pauschbetrag_rest_cent"],
                "freigrenze_rest_cent": c["freigrenze_rest_cent"],
                "persoenlicher_satz": c["persoenlicher_satz"],
                "kirchensteuer_satz": c["kirchensteuer_satz"],
                "pauschbetrag_rest": _eur(c["pauschbetrag_rest_cent"]),
                "freigrenze_rest": _eur(c["freigrenze_rest_cent"])}

    @router.put("/api/trading/config")
    def trading_config_put(body: TradingConfigIn, user: UserContext = Depends(current_user)):
        c = _trading_config(user.user_id)
        pb = c["pauschbetrag_rest_cent"]; fg = c["freigrenze_rest_cent"]
        ps = c["persoenlicher_satz"]; ks = c["kirchensteuer_satz"]
        try:
            if body.pauschbetrag_rest is not None:
                pb = max(0, ledger.parse_betrag(body.pauschbetrag_rest))
            if body.freigrenze_rest is not None:
                fg = max(0, ledger.parse_betrag(body.freigrenze_rest))
        except ledger.LedgerError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if body.persoenlicher_satz is not None:
            ps = min(1.0, max(0.0, float(body.persoenlicher_satz)))
        if body.kirchensteuer_satz is not None:
            ks = min(0.15, max(0.0, float(body.kirchensteuer_satz)))
        db.get_conn().execute(
            "UPDATE trading_config SET pauschbetrag_rest_cent=?, freigrenze_rest_cent=?, "
            "persoenlicher_satz=?, kirchensteuer_satz=?, updated_at=? WHERE user_id=?",
            (pb, fg, ps, ks, now_iso(), user.user_id))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "trading_config_gesetzt", {})
        return {"ok": True}

    @router.get("/api/trading/kapital")
    def trading_kapital_liste(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT id, datum, art, betrag_minor, notiz, quelle FROM trading_kapital "
            "WHERE user_id=? AND deleted_at IS NULL ORDER BY datum DESC, created_at DESC",
            (user.user_id,)).fetchall()
        return [{**dict(r), "betrag": _eur(r["betrag_minor"])} for r in rows]

    @router.post("/api/trading/kapital")
    def trading_kapital_anlegen(body: TradingKapitalIn, user: UserContext = Depends(current_user)):
        if body.art not in ("einlage", "entnahme", "bewertung"):
            return JSONResponse({"error": "art muss einlage|entnahme|bewertung sein"}, status_code=400)
        datum = _iso_tag(body.datum)
        if datum is None:
            return JSONResponse({"error": "datum muss ein gültiges Datum (YYYY-MM-DD) sein"}, status_code=400)
        try:
            betrag = ledger.parse_betrag(body.betrag)
        except ledger.LedgerError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if betrag < 0:
            return JSONResponse({"error": "Betrag darf nicht negativ sein"}, status_code=400)
        ts = now_iso(); kid = new_id()
        db.get_conn().execute(
            "INSERT INTO trading_kapital (id, user_id, datum, art, betrag_minor, notiz, "
            "quelle, created_at, updated_at) VALUES (?,?,?,?,?,?,'manuell',?,?)",
            (kid, user.user_id, datum, body.art, betrag, body.notiz.strip(), ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "trading_kapital_angelegt", {"art": body.art})
        return {"ok": True, "id": kid}

    @router.delete("/api/trading/kapital/{kid}")
    def trading_kapital_loeschen(kid: str, user: UserContext = Depends(current_user)):
        conn = db.get_conn()
        if conn.execute("SELECT 1 FROM trading_kapital WHERE id=? AND user_id=? AND deleted_at IS NULL",
                        (kid, user.user_id)).fetchone() is None:
            return JSONResponse({"error": "Bewegung unbekannt"}, status_code=404)
        conn.execute("UPDATE trading_kapital SET deleted_at=? WHERE id=? AND user_id=?",
                     (now_iso(), kid, user.user_id))
        conn.commit()
        return {"ok": True}

    @router.get("/api/trading/kapital/stand")
    def trading_kapital_stand(user: UserContext = Depends(current_user)):
        rows = db.get_conn().execute(
            "SELECT datum, art, betrag_minor, created_at FROM trading_kapital "
            "WHERE user_id=? AND deleted_at IS NULL", (user.user_id,)).fetchall()
        s = tsteuer.kapital_stand([dict(r) for r in rows])
        return {**s, "investiert_eur": _eur(s["investiert"]),
                "aktueller_wert_eur": _eur(s["aktueller_wert"]),
                "unrealisiert_eur": _eur(s["unrealisiert"])}

    @router.get("/api/trading/realisierungen")
    def trading_real_liste(jahr: int = 0, user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        sql = ("SELECT id, datum, regime, betrag_minor, beschreibung, kauf_datum, quelle "
               "FROM trading_realisierung WHERE user_id=? AND deleted_at IS NULL")
        params: list[Any] = [user.user_id]
        if jahr:
            sql += " AND substr(datum,1,4)=?"; params.append(str(jahr))
        sql += " ORDER BY datum DESC, created_at DESC"
        rows = db.get_conn().execute(sql, tuple(params)).fetchall()
        return [{**dict(r), "betrag": _eur(r["betrag_minor"])} for r in rows]

    @router.post("/api/trading/realisierungen")
    def trading_real_anlegen(body: TradingRealIn, user: UserContext = Depends(current_user)):
        if body.regime not in tsteuer.REGIME:
            return JSONResponse({"error": "regime muss futures|spot sein"}, status_code=400)
        if body.richtung not in ("gewinn", "verlust"):
            return JSONResponse({"error": "richtung muss gewinn|verlust sein"}, status_code=400)
        datum = _iso_tag(body.datum)
        if datum is None:
            return JSONResponse({"error": "datum muss ein gültiges Datum (YYYY-MM-DD) sein"}, status_code=400)
        kauf_datum = ""
        if (body.kauf_datum or "").strip():           # nur Spot trägt ein Kaufdatum
            kauf_datum = _iso_tag(body.kauf_datum) or ""
            if not kauf_datum:
                return JSONResponse({"error": "kauf_datum muss ein gültiges Datum (YYYY-MM-DD) sein"}, status_code=400)
        try:
            mag = ledger.parse_betrag(body.betrag)
        except ledger.LedgerError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if mag < 0:
            return JSONResponse({"error": "Betrag darf nicht negativ sein"}, status_code=400)
        betrag = mag if body.richtung == "gewinn" else -mag
        ts = now_iso(); rid = new_id()
        db.get_conn().execute(
            "INSERT INTO trading_realisierung (id, user_id, datum, regime, betrag_minor, "
            "beschreibung, kauf_datum, quelle, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,'manuell',?,?)",
            (rid, user.user_id, datum, body.regime, betrag,
             body.beschreibung.strip(), kauf_datum, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "trading_realisierung_angelegt",
                 {"regime": body.regime, "richtung": body.richtung})
        return {"ok": True, "id": rid}

    @router.delete("/api/trading/realisierungen/{rid}")
    def trading_real_loeschen(rid: str, user: UserContext = Depends(current_user)):
        conn = db.get_conn()
        if conn.execute("SELECT 1 FROM trading_realisierung WHERE id=? AND user_id=? AND deleted_at IS NULL",
                        (rid, user.user_id)).fetchone() is None:
            return JSONResponse({"error": "Realisierung unbekannt"}, status_code=404)
        conn.execute("UPDATE trading_realisierung SET deleted_at=? WHERE id=? AND user_id=?",
                     (now_iso(), rid, user.user_id))
        conn.commit()
        return {"ok": True}

    @router.get("/api/trading/steuer")
    def trading_steuer_uebersicht(jahr: int = 0, user: UserContext = Depends(current_user)):
        """Jahres-Steuer-Schätzung je Regime (§20 Futures / §23 Spot) + Schwellen-
        Vorwarnung. Stützt sich auf die geprüfte Engine + die Nutzer-Parameter."""
        from datetime import datetime, timezone
        jahr = jahr or datetime.now(timezone.utc).year
        c = _trading_config(user.user_id)
        rows = db.get_conn().execute(
            "SELECT datum, regime, betrag_minor, kauf_datum FROM trading_realisierung "
            "WHERE user_id=? AND deleted_at IS NULL", (user.user_id,)).fetchall()
        real = [{"datum": r["datum"], "regime": r["regime"], "betrag_minor": r["betrag_minor"],
                 "kauf_datum": r["kauf_datum"] or None} for r in rows]
        a = tsteuer.jahres_auswertung(
            real, jahr,
            pauschbetrag_rest_cent=c["pauschbetrag_rest_cent"],
            freigrenze_rest_cent=c["freigrenze_rest_cent"],
            persoenlicher_satz=c["persoenlicher_satz"],
            kirchensteuer_satz=c["kirchensteuer_satz"])
        return a

    @router.get("/api/trading/tb-performance")
    def trading_tb_performance(user: UserContext = Depends(current_user)):
        """V14-Brücke (READ-ONLY, docs/26 §13): zieht die Trading-Bot-Kennzahlen über
        den Core (Kachel-Stats) — rein informativ für den Kapital-/Performance-Verlauf.
        **AKTUELL Paper/Backtest (0 Echtgeld)** ⇒ steuerlich NICHT maßgeblich (die
        Echtgeld-Schiene läuft über die manuell/importiert erfassten Realisierungen).
        Best-effort, **kein TB-Eingriff, nie ein Trade-Auslöser**."""
        from appkit.querverbindung import CORE_URL
        getter = tb_get or (lambda url: __import__("httpx").get(url, timeout=4.0))
        try:
            r = getter(f"{CORE_URL}/api/panels/tradingbot/stats")
            if getattr(r, "status_code", 0) == 200:
                return {"ok": True, "paper": True, "stats": r.json(),
                        "hinweis": ("Trading-Bot-Performance (read-only). Aktuell Paper/"
                                    "Backtest — noch kein Echtgeld, daher steuerlich nicht "
                                    "maßgeblich. Reale Gewinne erfasst du als Realisierungen.")}
            return {"ok": False, "paper": True, "stats": {},
                    "fehler": f"Trading-Bot antwortet nicht (HTTP {getattr(r, 'status_code', '?')})"}
        except Exception:
            return {"ok": False, "paper": True, "stats": {},
                    "fehler": "Trading-Bot/Core gerade nicht erreichbar"}

    @router.get("/api/trading/steuer/export")
    def trading_steuer_export(jahr: int = 0, format: str = "md",
                              user: UserContext = Depends(current_user)):
        """Vorzeigbarer Jahres-Bericht der Trading-Steuer (gegliedert nach Anlage KAP
        §20 / Anlage SO §23, mit Einzelposten + Summen) als **Markdown**, **CSV** oder
        **JSON** zum Download — die nachvollziehbare Aufstellung fürs Finanzamt.
        Schätzung, keine Steuerberatung. Aggregierte Zahlen ⇒ Stufe 'lokal'."""
        from datetime import datetime, timezone
        jahr = jahr or datetime.now(timezone.utc).year
        if format not in ("md", "csv", "json"):
            return JSONResponse({"error": "format muss md|csv|json sein"}, status_code=400)
        c = _trading_config(user.user_id)
        rows = db.get_conn().execute(
            "SELECT datum, regime, betrag_minor, beschreibung, kauf_datum FROM trading_realisierung "
            "WHERE user_id=? AND deleted_at IS NULL AND substr(datum,1,4)=? ORDER BY datum",
            (user.user_id, str(jahr))).fetchall()
        posten = [dict(r) for r in rows]
        real_alle = [{"datum": r["datum"], "regime": r["regime"], "betrag_minor": r["betrag_minor"],
                      "kauf_datum": r["kauf_datum"] or None} for r in rows]
        a = tsteuer.jahres_auswertung(
            real_alle, jahr, pauschbetrag_rest_cent=c["pauschbetrag_rest_cent"],
            freigrenze_rest_cent=c["freigrenze_rest_cent"],
            persoenlicher_satz=c["persoenlicher_satz"], kirchensteuer_satz=c["kirchensteuer_satz"])
        kap = db.get_conn().execute(
            "SELECT datum, art, betrag_minor, created_at FROM trading_kapital WHERE user_id=? AND deleted_at IS NULL",
            (user.user_id,)).fetchall()
        stand = tsteuer.kapital_stand([dict(r) for r in kap])
        db.audit(user.user_id, "user", "trading_steuer_exportiert", {"jahr": jahr, "format": format})
        name = f"dizz-money-trading-steuer-{jahr}.{format}"
        if format == "json":
            import json as _json
            return PlainTextResponse(
                _json.dumps({"auswertung": a, "posten": posten, "kapital": stand},
                            ensure_ascii=False, indent=2),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{name}"'})
        if format == "md":
            return PlainTextResponse(
                tsteuer.jahres_bericht_markdown(jahr, a, posten, stand),
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{name}"'})
        import csv as _csv
        import io as _io
        puffer = _io.StringIO(); w = _csv.writer(puffer, delimiter=";")
        w.writerow(["Datum", "Regime", "Beschreibung", "Kaufdatum", "steuerpflichtig", "Betrag_EUR"])
        for p in posten:
            stp = (tsteuer.spot_steuerpflichtig(p["kauf_datum"] or None, p["datum"])
                   if p["regime"] == "spot" else True)
            w.writerow([p["datum"], p["regime"], csv_safe(p["beschreibung"]), p["kauf_datum"] or "",
                        "ja" if stp else "nein", ledger.format_betrag(p["betrag_minor"], "EUR")])
        w.writerow([])
        w.writerow([f"§20 Netto {jahr}", "", "", "", "", ledger.format_betrag(a["futures"]["netto"], "EUR")])
        w.writerow(["§20 steuerpflichtig", "", "", "", "", ledger.format_betrag(a["futures"]["steuerpflichtig"], "EUR")])
        w.writerow(["§20 Steuer geschätzt", "", "", "", "", ledger.format_betrag(a["futures"]["gesamt"], "EUR")])
        w.writerow(["§23 Netto (Frist)", "", "", "", "", ledger.format_betrag(a["spot"]["netto"], "EUR")])
        w.writerow(["§23 Steuer geschätzt", "", "", "", "", ledger.format_betrag(a["spot"]["steuer_gesamt"], "EUR")])
        w.writerow([f"Steuer gesamt {jahr}", "", "", "", "", ledger.format_betrag(a["steuer_gesamt"], "EUR")])
        return PlainTextResponse(
            puffer.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # =================== Teil B: Kategorien-CRUD ============================

    @router.get("/api/kategorien")
    def kategorien_liste(user: UserContext = Depends(current_user)):
        rows = db.get_conn().execute(
            "SELECT id, name, richtung, farbe, steuer_relevant, steuer_art "
            "FROM kategorien WHERE user_id=? AND deleted_at IS NULL ORDER BY name",
            (user.user_id,)).fetchall()
        return [{**dict(r), "steuer_relevant": bool(r["steuer_relevant"])} for r in rows]

    @router.post("/api/kategorien")
    def kategorie_anlegen(body: KategorieIn, user: UserContext = Depends(current_user)):
        if body.richtung not in ("einnahme", "ausgabe", "beides"):
            return JSONResponse({"error": "richtung muss einnahme|ausgabe|beides sein"},
                                status_code=400)
        if not body.name.strip():
            return JSONResponse({"error": "Name ist Pflicht"}, status_code=400)
        kid, ts = new_id(), now_iso()
        db.get_conn().execute(
            "INSERT INTO kategorien (id, user_id, name, richtung, farbe, "
            "steuer_relevant, steuer_art, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (kid, user.user_id, body.name.strip(), body.richtung, body.farbe,
             int(body.steuer_relevant), body.steuer_art.strip(), ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "kategorie_angelegt", {"name": body.name})
        return {"ok": True, "id": kid}

    @router.put("/api/kategorien/{kategorie_id}")
    def kategorie_aendern(kategorie_id: str, body: KategorieIn,
                          user: UserContext = Depends(current_user)):
        if _kategorie(user.user_id, kategorie_id) is None:
            return JSONResponse({"error": "Kategorie unbekannt"}, status_code=404)
        if body.richtung not in ("einnahme", "ausgabe", "beides"):
            return JSONResponse({"error": "richtung ungültig"}, status_code=400)
        db.get_conn().execute(
            "UPDATE kategorien SET name=?, richtung=?, farbe=?, steuer_relevant=?, "
            "steuer_art=?, updated_at=? WHERE id=? AND user_id=?",
            (body.name.strip(), body.richtung, body.farbe, int(body.steuer_relevant),
             body.steuer_art.strip(), now_iso(), kategorie_id, user.user_id))
        db.get_conn().commit()
        return {"ok": True, "id": kategorie_id}

    @router.delete("/api/kategorien/{kategorie_id}")
    def kategorie_loeschen(kategorie_id: str, user: UserContext = Depends(current_user)):
        conn = db.get_conn()
        if _kategorie(user.user_id, kategorie_id) is None:
            return JSONResponse({"error": "Kategorie unbekannt"}, status_code=404)
        ts = now_iso()
        ausgespart = 0
        with db.transaktion() as conn:
            conn.execute("UPDATE kategorien SET deleted_at=? WHERE id=? AND user_id=?",
                         (ts, kategorie_id, user.user_id))
            # Zuordnungen lösen (Buchungen werden wieder „nicht zugeordnet") — §6.2 #4: versiegelte
            # Zeiträume ausklammern (sie behalten ihre archivierte Kategorie); jede offene Umklassung
            # ist ein money.umklassung-Ereignis (GoBD-Journalfunktion), die Aussparung wird gemeldet.
            betroffene = conn.execute(
                "SELECT id, datum FROM buchungen WHERE kategorie_id=? AND user_id=? AND deleted_at IS NULL",
                (kategorie_id, user.user_id)).fetchall()
            for bid, datum in betroffene:
                if chronik_naht.ist_gesperrt(conn, user.user_id, datum):
                    ausgespart += 1
                    continue
                conn.execute("UPDATE buchungen SET kategorie_id=NULL, updated_at=? WHERE id=?", (ts, bid))
                chronik_naht.schreibe_umklassung(conn, user.user_id, buchung_id=bid, kategorie_id="")
            # Regeln auf diese Kategorie ebenfalls deaktivieren — kein Verweis ins Leere.
            conn.execute("UPDATE regeln SET deleted_at=? WHERE kategorie_id=? AND user_id=?",
                         (ts, kategorie_id, user.user_id))
        antwort: dict[str, Any] = {"ok": True}
        if ausgespart:
            antwort["ausgespart"] = ausgespart      # versiegelte Buchungen behielten ihre Kategorie
        return antwort

    # =================== Teil B: Regeln-CRUD + Anwendung ====================

    @router.get("/api/regeln")
    def regeln_liste(user: UserContext = Depends(current_user)):
        rows = db.get_conn().execute(
            "SELECT r.id, r.muster, r.feld, r.kategorie_id, r.bereich_id, r.prioritaet, r.treffer, "
            "k.name AS kategorie_name, ber.name AS bereich_name FROM regeln r "
            "LEFT JOIN kategorien k ON k.id=r.kategorie_id AND k.deleted_at IS NULL "
            "LEFT JOIN bereiche ber ON ber.id=r.bereich_id AND ber.deleted_at IS NULL "
            "WHERE r.user_id=? AND r.deleted_at IS NULL ORDER BY r.prioritaet DESC, r.treffer DESC",
            (user.user_id,)).fetchall()
        return [dict(r) for r in rows]

    @router.post("/api/regeln")
    def regel_anlegen(body: RegelIn, user: UserContext = Depends(current_user)):
        if body.feld not in regelmodul.FELDER:
            return JSONResponse({"error": f"feld muss aus {regelmodul.FELDER} sein"},
                                status_code=400)
        if not body.muster.strip():
            return JSONResponse({"error": "Muster ist Pflicht"}, status_code=400)
        if _kategorie(user.user_id, body.kategorie_id) is None:
            return JSONResponse({"error": "Kategorie unbekannt"}, status_code=404)
        if body.bereich_id and not _bereich_ok(user.user_id, body.bereich_id):
            return JSONResponse({"error": "Bereich unbekannt"}, status_code=404)
        rid = _regel_lernen(user.user_id, body.muster.strip().lower(), body.feld,
                            body.kategorie_id, prioritaet=body.prioritaet,
                            bereich_id=body.bereich_id)
        return {"ok": True, "id": rid}

    @router.patch("/api/regeln/{regel_id}")
    def regel_aendern(regel_id: str, body: RegelPatchIn,
                      user: UserContext = Depends(current_user)):
        """Setzt/löst den Bereich einer Regel ('' = kein Bereich). Künftige Treffer
        ordnen die Buchung dann (auch) diesem Bereich zu (``regeln_anwenden``)."""
        if body.bereich_id and not _bereich_ok(user.user_id, body.bereich_id):
            return JSONResponse({"error": "Bereich unbekannt"}, status_code=404)
        conn = db.get_conn()
        cur = conn.execute("UPDATE regeln SET bereich_id=?, updated_at=? WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (body.bereich_id, now_iso(), regel_id, user.user_id))
        conn.commit()
        if not cur.rowcount:
            return JSONResponse({"error": "Regel unbekannt"}, status_code=404)
        return {"ok": True, "bereich_id": body.bereich_id}

    @router.delete("/api/regeln/{regel_id}")
    def regel_loeschen(regel_id: str, user: UserContext = Depends(current_user)):
        conn = db.get_conn()
        cur = conn.execute("UPDATE regeln SET deleted_at=? WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (now_iso(), regel_id, user.user_id))
        conn.commit()
        if not cur.rowcount:
            return JSONResponse({"error": "Regel unbekannt"}, status_code=404)
        return {"ok": True}

    @router.post("/api/regeln/anwenden")
    def regeln_anwenden_endpoint(user: UserContext = Depends(current_user)):
        n = regelmodul.regeln_anwenden(db, user.user_id)
        db.audit(user.user_id, "user", "regeln_angewendet", {"kategorisiert": n})
        return {"ok": True, "kategorisiert": n}

    # =================== Teil B: Budgets-CRUD ==============================

    @router.get("/api/budgets")
    def budgets_liste(user: UserContext = Depends(current_user)):
        rows = db.get_conn().execute(
            "SELECT b.id, b.kategorie_id, b.monat, b.betrag, k.name AS kategorie_name "
            "FROM budgets b LEFT JOIN kategorien k ON k.id=b.kategorie_id "
            "AND k.deleted_at IS NULL WHERE b.user_id=? AND b.deleted_at IS NULL "
            "ORDER BY b.monat DESC, k.name", (user.user_id,)).fetchall()
        return [{**dict(r), "betrag_text": ledger.format_betrag(r["betrag"], "EUR")}
                for r in rows]

    @router.post("/api/budgets")
    def budget_setzen(body: BudgetIn, user: UserContext = Depends(current_user)):
        if _kategorie(user.user_id, body.kategorie_id) is None:
            return JSONResponse({"error": "Kategorie unbekannt"}, status_code=404)
        try:
            betrag = ledger.parse_betrag(body.betrag, "EUR")
        except ledger.LedgerError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if betrag < 0:
            return JSONResponse({"error": "Budget darf nicht negativ sein"}, status_code=400)
        conn = db.get_conn()
        ts = now_iso()
        # Upsert je (Kategorie, Monat) — ein Budget je Kategorie/Monat.
        conn.execute(
            "INSERT INTO budgets (id, user_id, kategorie_id, monat, betrag, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT (user_id, kategorie_id, monat) "
            "DO UPDATE SET betrag=excluded.betrag, updated_at=excluded.updated_at, deleted_at=NULL",
            (new_id(), user.user_id, body.kategorie_id, body.monat.strip() or "*",
             betrag, ts, ts))
        conn.commit()
        return {"ok": True}

    @router.delete("/api/budgets/{budget_id}")
    def budget_loeschen(budget_id: str, user: UserContext = Depends(current_user)):
        conn = db.get_conn()
        cur = conn.execute("UPDATE budgets SET deleted_at=? WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (now_iso(), budget_id, user.user_id))
        conn.commit()
        if not cur.rowcount:
            return JSONResponse({"error": "Budget unbekannt"}, status_code=404)
        return {"ok": True}

    # =================== Sparziele (Sparkonten-Tracking) ==================
    # Ein Sparziel ist ein Soll-Betrag mit Fortschritt. Hängt ein echtes Konto
    # dran (``konto_id``), liest der Ist-Stand LIVE den Konto-Saldo (über den
    # geprüften Ledger-Kern) — sonst trägt der Nutzer ihn manuell. Geld bleibt
    # IMMER Minor-Units (Eingabe → parse_betrag, Ausgabe → format_betrag).

    def _sparziel_eingabe(user_id: str, body: SparzielIn):
        """Validiert + löst eine Sparziel-Eingabe auf; gemeinsam für POST/PUT.
        Liefert ``(felder, None)`` oder ``(None, Fehler-Response)``. Bei gesetztem
        ``konto_id`` zählt der ECHTE Konto-Saldo ⇒ Währung = Konto-Währung, ein
        manueller Stand entfällt (wäre widersprüchlich zum Auto-Tracking)."""
        if not body.name.strip():
            return None, JSONResponse({"error": "Name ist Pflicht"}, status_code=400)
        konto_id = (body.konto_id or "").strip() or None
        aktuell_minor = 0
        if konto_id:
            k = _konto(user_id, konto_id)
            if k is None:
                return None, JSONResponse({"error": "Konto unbekannt"}, status_code=404)
            waehrung = k["waehrung"]      # Auto-Tracking ⇒ Ziel-Währung = Konto-Währung
        else:
            waehrung = body.waehrung
            if waehrung not in ledger.WAEHRUNG_DEZIMAL:
                return None, JSONResponse(
                    {"error": f"Währung unbekannt: {waehrung}"}, status_code=400)
            try:
                aktuell_minor = ledger.parse_betrag(body.aktuell or "0", waehrung)
            except ledger.LedgerError as e:
                return None, JSONResponse({"error": str(e)}, status_code=400)
            if aktuell_minor < 0:
                return None, JSONResponse(
                    {"error": "Aktueller Stand darf nicht negativ sein"}, status_code=400)
        try:
            zielbetrag = ledger.parse_betrag(body.zielbetrag, waehrung)
        except ledger.LedgerError as e:
            return None, JSONResponse({"error": str(e)}, status_code=400)
        if zielbetrag <= 0:
            return None, JSONResponse(
                {"error": "Zielbetrag muss größer als 0 sein"}, status_code=400)
        return {"name": body.name.strip(), "zielbetrag": zielbetrag, "waehrung": waehrung,
                "konto_id": konto_id, "faellig_am": (body.faellig_am or "").strip(),
                "aktuell_minor": aktuell_minor}, None

    @router.post("/api/sparziele")
    def sparziel_anlegen(body: SparzielIn, user: UserContext = Depends(current_user)):
        felder, fehler = _sparziel_eingabe(user.user_id, body)
        if fehler is not None:
            return fehler
        sid, ts = new_id(), now_iso()
        db.get_conn().execute(
            "INSERT INTO sparziele (id, user_id, name, zielbetrag, waehrung, konto_id, "
            "faellig_am, aktuell_minor, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, user.user_id, felder["name"], felder["zielbetrag"], felder["waehrung"],
             felder["konto_id"], felder["faellig_am"], felder["aktuell_minor"], ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "sparziel_angelegt", {"name": felder["name"]})
        return {"ok": True, "id": sid}

    @router.get("/api/sparziele")
    def sparziele_liste(user: UserContext = Depends(current_user)):
        """Alle Sparziele mit Fortschritt. ``aktuell`` kommt LIVE aus dem echten
        Konto-Saldo (``konto_id`` gesetzt + Konto existiert) oder aus dem manuell
        gepflegten Wert. ``fortschritt_prozent`` = aktuell/ziel (reine Anzeige)."""
        rows = db.get_conn().execute(
            "SELECT id, name, zielbetrag, waehrung, konto_id, faellig_am, aktuell_minor "
            "FROM sparziele WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY faellig_am='', faellig_am, name", (user.user_id,)).fetchall()
        out = []
        for s in rows:
            w = s["waehrung"]
            k = _konto(user.user_id, s["konto_id"]) if s["konto_id"] else None
            if k is not None:
                aktuell = _konto_anzeige_saldo(user.user_id, k)
                quelle, konto_name = "konto", k["name"]
            else:
                # Kein (mehr existierendes) Konto ⇒ manueller Stand.
                aktuell = s["aktuell_minor"]
                quelle, konto_name = "manuell", None
            ziel = s["zielbetrag"]
            rest = max(ziel - aktuell, 0)
            # round() ist hier reine Verhältnis-Heuristik (Anzeige), KEIN Geldbetrag.
            prozent = round(aktuell / ziel * 100, 1) if ziel > 0 else 0.0
            out.append({
                "id": s["id"], "name": s["name"], "konto_id": s["konto_id"],
                "konto_name": konto_name, "waehrung": w, "quelle": quelle,
                "faellig_am": s["faellig_am"] or "",
                "zielbetrag": ziel, "zielbetrag_text": ledger.format_betrag(ziel, w),
                "aktuell_minor": aktuell, "aktuell_text": ledger.format_betrag(aktuell, w),
                "rest_minor": rest, "rest_text": ledger.format_betrag(rest, w),
                "fortschritt_prozent": prozent, "erreicht": aktuell >= ziel})
        return out

    @router.put("/api/sparziele/{sparziel_id}")
    def sparziel_aendern(sparziel_id: str, body: SparzielIn,
                         user: UserContext = Depends(current_user)):
        if _sparziel(user.user_id, sparziel_id) is None:
            return JSONResponse({"error": "Sparziel unbekannt"}, status_code=404)
        felder, fehler = _sparziel_eingabe(user.user_id, body)
        if fehler is not None:
            return fehler
        db.get_conn().execute(
            "UPDATE sparziele SET name=?, zielbetrag=?, waehrung=?, konto_id=?, "
            "faellig_am=?, aktuell_minor=?, updated_at=? WHERE id=? AND user_id=?",
            (felder["name"], felder["zielbetrag"], felder["waehrung"], felder["konto_id"],
             felder["faellig_am"], felder["aktuell_minor"], now_iso(), sparziel_id, user.user_id))
        db.get_conn().commit()
        return {"ok": True, "id": sparziel_id}

    @router.delete("/api/sparziele/{sparziel_id}")
    def sparziel_loeschen(sparziel_id: str, user: UserContext = Depends(current_user)):
        conn = db.get_conn()
        cur = conn.execute(
            "UPDATE sparziele SET deleted_at=?, updated_at=? WHERE id=? AND user_id=? "
            "AND deleted_at IS NULL", (now_iso(), now_iso(), sparziel_id, user.user_id))
        conn.commit()
        if not cur.rowcount:
            return JSONResponse({"error": "Sparziel unbekannt"}, status_code=404)
        db.audit(user.user_id, "user", "sparziel_geloescht", {"sparziel": sparziel_id})
        return {"ok": True}

    # =================== Teil B: Auswertungen ==============================

    @router.get("/api/auswertung/cashflow")
    def auswertung_cashflow(von: str | None = None, bis: str | None = None,
                            user: UserContext = Depends(current_user)):
        return ausw.cashflow(_bewegungen(user.user_id), von=von, bis=bis)

    def _bereich_name_aufloesen(user_id: str, kontext: str):
        """Stufe ③ App-Fallback (docs/67 §3.2): Bereichs-NAME case-insensitiv (Alt-
        Mechanik); deterministisch sort_order, name (B-2-Fix). ①kanon/②kontext macht
        jetzt der geteilte ``bereiche.register.aufloesen``."""
        row = db.get_conn().execute(
            "SELECT id FROM bereiche WHERE user_id=? AND deleted_at IS NULL "
            "AND LOWER(name)=LOWER(?) ORDER BY sort_order, name LIMIT 1",
            (user_id, kontext)).fetchone()
        return row["id"] if row else None

    @router.get("/api/bereich/finanzspur")
    def bereich_finanzspur(kontext: str = "", jahr: int = 0, kanon: str = "",
                           user: UserContext = Depends(current_user)):
        """A5/V17 (docs/34) — read-only per-Bereich-Finanzspur für Dizz Admins
        Bereichs-Cockpit (über Core-Relay ``/querverbindung/finanzen/finanzspur``).
        ``kontext`` = ``bereich.money_kontext`` ⇒ wird ZUERST auf einen echten
        Money-Bereich aufgelöst (kontext-Schlüssel/Name): dann zählt der ECHTE
        effektive Bereich (Buchungs-Override sonst Konto-Default). Existiert kein
        Money-Bereich, **Fallback** auf das bisherige Kategorie-Namen-Matching
        (Back-compat). Aggregiert **pro Währung** (Minor-Units, nie gemischt).
        ``jahr`` > 0 filtert aufs Kalenderjahr; leerer ``kontext`` ⇒ leere Spur."""
        kontext = (kontext or "").strip()
        kanon = (kanon or "").strip()
        if not kontext and not kanon:
            return {"kontext": "", "jahr": jahr, "je_waehrung": [],
                    "kategorien": [], "anzahl_buchungen": 0}
        aufl = bereiche.register.aufloesen(user.user_id, kanon=kanon, kontext=kontext)  # ①kanon→②kontext
        bid, quelle = aufl.bereich_id, aufl.quelle
        if bid is None and kontext:
            bid = _bereich_name_aufloesen(user.user_id, kontext)   # ③ Name-Fallback (docs/67 §3.2)
            if bid:
                quelle = "name"
        # Per-Währung-Roh-Aggregat je Buchung. Bei Bereich: LEFT JOIN (Buchungen ohne
        # Kategorie zählen); im Fallback: INNER JOIN + Kategorie-Name-Filter (alt).
        kat_join = "LEFT JOIN" if bid is not None else "JOIN"
        sql = ("SELECT b.id, k.name AS kategorie_name, ko.waehrung AS waehrung, "
               "COALESCE(SUM(CASE WHEN ko.typ IN ('asset','liability') "
               "THEN p.betrag ELSE 0 END),0) AS netto_w "
               "FROM buchungen b "
               "JOIN postings p ON p.buchung_id=b.id AND p.deleted_at IS NULL "
               "JOIN konten ko ON ko.id=p.konto_id "
               f"{kat_join} kategorien k ON k.id=b.kategorie_id AND k.deleted_at IS NULL "
               "WHERE b.user_id=? AND b.deleted_at IS NULL ")
        args: list[Any] = [user.user_id]
        if bid is None:
            sql += "AND LOWER(k.name)=LOWER(?) "
            args.append(kontext)
        if jahr:
            sql += "AND substr(b.datum,1,4)=? "
            args.append(str(jahr))
        sql += "GROUP BY b.id, ko.waehrung"
        rows = db.get_conn().execute(sql, args).fetchall()
        if bid is not None:
            eff = _bereich_je_buchung(user.user_id)
            rows = [r for r in rows if eff.get(r["id"], "") == bid]
        je_w = ausw.finanzspur([dict(r) for r in rows])
        for e in je_w:
            e["einnahmen_text"] = ledger.format_betrag(e["einnahmen"], e["waehrung"])
            e["ausgaben_text"] = ledger.format_betrag(e["ausgaben"], e["waehrung"])
            e["saldo_text"] = ledger.format_betrag(e["saldo"], e["waehrung"])
        namen = sorted({r["kategorie_name"] for r in rows if r["kategorie_name"]})
        return {"kontext": kontext, "jahr": jahr, "je_waehrung": je_w,
                "kategorien": namen, "anzahl_buchungen": len({r["id"] for r in rows}),
                "bereich_id": bid or "", "quelle": quelle if bid else "kategorie"}

    @router.get("/api/bereiche/{bid}/cockpit")
    def bereich_cockpit(bid: str, jahr: int = 0, monat: str | None = None,
                        user: UserContext = Depends(current_user)):
        """Pro-Bereich-Cockpit (analog Admins Bereichs-Cockpit): bündelt die Money-Module
        DIESES Bereichs — Konten/Vermögen · Cashflow · Budgets · EÜR · Sparziele ·
        Wiederkehr/Abos — über den EFFEKTIVEN Bereich (Buchungs-Override sonst Konto-
        Default). Read-only Sicht-Aggregat; ändert NICHTS am Ledger. Geld in Minor-Units;
        Cashflow/Budget/EÜR EUR-aggregiert (≈, konsistent mit den globalen Sichten),
        Vermögen je Währung. Die globale Gesamtübersicht (``/api/auswertung/*``) bleibt
        unberührt — dieses Cockpit ist additiv."""
        b = bereiche.holen(user.user_id, bid)
        if b is None:
            return JSONResponse({"error": "Bereich unbekannt"}, status_code=404)
        uid = user.user_id
        bew = _bewegungen(uid, bereich=bid)
        conn = db.get_conn()

        # Cashflow (EUR ≈, wie /api/auswertung/cashflow)
        cf = ausw.cashflow(bew)
        cashflow = {
            "einnahmen": cf["einnahmen"], "ausgaben": cf["ausgaben"], "saldo": cf["saldo"],
            "einnahmen_text": ledger.format_betrag(cf["einnahmen"], "EUR"),
            "ausgaben_text": ledger.format_betrag(cf["ausgaben"], "EUR"),
            "saldo_text": ledger.format_betrag(cf["saldo"], "EUR"),
            "je_kategorie": [{**k, "saldo_text": ledger.format_betrag(k["saldo"], "EUR")}
                             for k in cf["je_kategorie"][:8]]}

        # Konten/Vermögen — Konten dieses Bereichs (je Währung)
        krows = conn.execute(
            "SELECT k.id, k.name, k.typ, k.waehrung, "
            "COALESCE((SELECT SUM(p.betrag) FROM postings p WHERE p.konto_id=k.id "
            "AND p.user_id=k.user_id AND p.deleted_at IS NULL),0) AS roh_saldo "
            "FROM konten k WHERE k.user_id=? AND k.bereich_id=? AND k.deleted_at IS NULL",
            (uid, bid)).fetchall()
        verm = ausw.vermoegen([dict(r) for r in krows])
        for z in verm["konten"]:
            z["saldo_text"] = ledger.format_betrag(z["saldo_minor"], z["waehrung"])
        vermoegen = {"konten": verm["konten"], "netto_je_waehrung": verm["netto_je_waehrung"],
                     "je_waehrung_text": {w: ledger.format_betrag(s, w)
                                          for w, s in verm["netto_je_waehrung"].items()}}

        # Budgets — globale Limits vs. bereich-Ist (Schritt A: kein Constraint-Bruch)
        monat = monat or now_iso()[:7]
        budgets = conn.execute(
            "SELECT b.kategorie_id, b.monat, b.betrag, k.name AS kategorie_name "
            "FROM budgets b LEFT JOIN kategorien k ON k.id=b.kategorie_id "
            "WHERE b.user_id=? AND b.deleted_at IS NULL AND (b.monat=? OR b.monat='*')",
            (uid, monat)).fetchall()
        cf_monat = ausw.cashflow(bew, von=f"{monat}-01", bis=f"{monat}-31")
        ist = {e["kategorie_id"]: e["ausgaben"] for e in cf_monat["je_kategorie"]
               if e["kategorie_id"]}
        bstatus = ausw.budget_status([dict(x) for x in budgets], ist)
        for s in bstatus:
            s["soll_text"] = ledger.format_betrag(s["soll"], "EUR")
            s["ist_text"] = ledger.format_betrag(s["ist"], "EUR")
            s["rest_text"] = ledger.format_betrag(s["rest"], "EUR")

        # EÜR (bereich-gefiltert)
        jahr_eff = jahr or int(now_iso()[:4])
        eur = ausw.eur_jahr(bew, jahr_eff)
        euer = {"jahr": eur["jahr"], "ueberschuss": eur["ueberschuss"],
                "einnahmen_text": ledger.format_betrag(eur["einnahmen"], "EUR"),
                "ausgaben_text": ledger.format_betrag(eur["ausgaben"], "EUR"),
                "ueberschuss_text": ledger.format_betrag(eur["ueberschuss"], "EUR")}

        # Sparziele — über die dem Bereich zugeordneten Konten
        spar = conn.execute(
            "SELECT s.id, s.name, s.zielbetrag, s.waehrung, s.konto_id FROM sparziele s "
            "JOIN konten k ON k.id=s.konto_id AND k.deleted_at IS NULL "
            "WHERE s.user_id=? AND s.deleted_at IS NULL AND k.bereich_id=?",
            (uid, bid)).fetchall()
        sparziele = []
        for s in spar:
            k = _konto(uid, s["konto_id"])
            aktuell = _konto_anzeige_saldo(uid, k) if k else 0
            ziel = s["zielbetrag"]
            sparziele.append({
                "id": s["id"], "name": s["name"], "waehrung": s["waehrung"],
                "zielbetrag_text": ledger.format_betrag(ziel, s["waehrung"]),
                "aktuell_text": ledger.format_betrag(aktuell, s["waehrung"]),
                # round() ist reine Anzeige-Heuristik (kein Geldbetrag).
                "fortschritt_prozent": round(aktuell / ziel * 100, 1) if ziel > 0 else 0.0})

        # Wiederkehr/Abos — Serien dieses Bereichs + Monats-Fixlast
        srows = conn.execute(
            "SELECT id, name, betrag, intervall, intervall_tage, naechste_faelligkeit "
            "FROM serien WHERE user_id=? AND bereich_id=? AND aktiv=1 AND deleted_at IS NULL "
            "ORDER BY naechste_faelligkeit", (uid, bid)).fetchall()
        serien = [dict(r) for r in srows]
        fixlast = wkmodul.monatsbelastung(serien)
        abos = {"anzahl": len(serien),
                "fixlast_saldo": fixlast["saldo"],
                "fixlast_text": ledger.format_betrag(fixlast["saldo"], "EUR"),
                "serien": [{"name": s["name"], "intervall": s["intervall"],
                            "betrag_text": ledger.format_betrag(s["betrag"], "EUR"),
                            "naechste_faelligkeit": s["naechste_faelligkeit"]} for s in serien]}

        return {
            "bereich": {"id": b["id"], "name": b["name"], "art": b["art"],
                        "status": b["status"], "kontext": b["kontext"]},
            "cashflow": cashflow, "vermoegen": vermoegen,
            "budgets": {"monat": monat, "liste": bstatus},
            "euer": euer, "sparziele": sparziele, "abos": abos}

    @router.get("/api/auswertung/vermoegen")
    def auswertung_vermoegen(user: UserContext = Depends(current_user)):
        rows = db.get_conn().execute(
            "SELECT k.id, k.name, k.typ, k.waehrung, "
            "COALESCE((SELECT SUM(p.betrag) FROM postings p WHERE p.konto_id=k.id "
            "AND p.user_id=k.user_id AND p.deleted_at IS NULL),0) AS roh_saldo "
            "FROM konten k WHERE k.user_id=? AND k.deleted_at IS NULL",
            (user.user_id,)).fetchall()
        erg = ausw.vermoegen([dict(r) for r in rows])
        erg["netto_text"] = ledger.format_betrag(
            erg["netto_je_waehrung"].get("EUR", 0), "EUR")
        # Multi-Währung: alle Währungs-Nettos nach EUR umrechnen (informativ „≈").
        kurse = _kurse(user.user_id)
        netto_eur = 0
        for waehrung, roh in erg["netto_je_waehrung"].items():
            try:
                netto_eur += ledger.umrechnen(roh, waehrung, "EUR", kurse)
            except ledger.LedgerError:
                pass
        erg["netto_eur"] = netto_eur
        erg["netto_eur_text"] = ledger.format_betrag(netto_eur, "EUR")
        erg["je_waehrung_text"] = {w: ledger.format_betrag(b, w)
                                   for w, b in erg["netto_je_waehrung"].items()}
        return erg

    @router.get("/api/auswertung/budget")
    def auswertung_budget(monat: str | None = None,
                          user: UserContext = Depends(current_user)):
        """Soll/Ist je Budget für ``monat`` (Default: laufender Monat). Bezieht
        Budgets dieses Monats UND die monatsübergreifenden (``monat='*'``)."""
        monat = monat or now_iso()[:7]
        conn = db.get_conn()
        budgets = conn.execute(
            "SELECT b.kategorie_id, b.monat, b.betrag, k.name AS kategorie_name "
            "FROM budgets b LEFT JOIN kategorien k ON k.id=b.kategorie_id "
            "WHERE b.user_id=? AND b.deleted_at IS NULL AND (b.monat=? OR b.monat='*')",
            (user.user_id, monat)).fetchall()
        von, bis = f"{monat}-01", f"{monat}-31"
        cf = ausw.cashflow(_bewegungen(user.user_id), von=von, bis=bis)
        ist = {e["kategorie_id"]: e["ausgaben"] for e in cf["je_kategorie"]
               if e["kategorie_id"]}
        status = ausw.budget_status([dict(b) for b in budgets], ist)
        for s in status:
            s["soll_text"] = ledger.format_betrag(s["soll"], "EUR")
            s["ist_text"] = ledger.format_betrag(s["ist"], "EUR")
            s["rest_text"] = ledger.format_betrag(s["rest"], "EUR")
        # Envelope-/Zero-Based-Sicht (YNAB/Actual): „jeder Euro hat einen Job".
        einnahmen = cf["einnahmen"]
        zugewiesen = sum(s["soll"] for s in status)
        ausgegeben = sum(s["ist"] for s in status)
        zuzuweisen = einnahmen - zugewiesen        # > 0: noch zu verteilen; < 0: überbudgetiert
        envelope = {
            "einnahmen": einnahmen, "zugewiesen": zugewiesen,
            "ausgegeben": ausgegeben, "zuzuweisen": zuzuweisen,
            "einnahmen_text": ledger.format_betrag(einnahmen, "EUR"),
            "zugewiesen_text": ledger.format_betrag(zugewiesen, "EUR"),
            "ausgegeben_text": ledger.format_betrag(ausgegeben, "EUR"),
            "zuzuweisen_text": ledger.format_betrag(zuzuweisen, "EUR")}
        return {"monat": monat, "budgets": status, "envelope": envelope}

    # =================== FX / Wechselkurse ==================================

    @router.get("/api/wechselkurse")
    def wechselkurse_liste(user: UserContext = Depends(current_user)):
        """Effektive Kurstabelle (Richtwerte + selbst gepflegte). ``EUR`` = 1.
        Kurs = EUR je 1 Einheit der Währung. Informativ („≈"); Pflege durch den
        Nutzer (kein Netz-Abruf — FinTS/Live-Kurse sind Architektur-KI-Parkplatz)."""
        kurse = _kurse(user.user_id)
        eigene = {r["waehrung"] for r in db.get_conn().execute(
            "SELECT waehrung FROM wechselkurse WHERE user_id=?", (user.user_id,)).fetchall()}
        return {"kurse": kurse, "basis": "EUR",
                "selbst_gepflegt": sorted(eigene),
                "waehrungen": sorted(ledger.WAEHRUNG_DEZIMAL)}

    @router.put("/api/wechselkurse")
    def wechselkurs_setzen(body: WechselkursIn, user: UserContext = Depends(current_user)):
        w = body.waehrung.strip().upper()
        if w not in ledger.WAEHRUNG_DEZIMAL:
            return JSONResponse({"error": f"Währung unbekannt: {w}"}, status_code=400)
        if w == "EUR":
            return JSONResponse({"error": "EUR ist die Basis (immer 1)"}, status_code=400)
        try:
            from decimal import Decimal
            # M-7: 'Infinity'/'NaN' sind gültige Decimals und passieren den <=0-Check
            # (Inf <= 0 ist False) ⇒ landeten sonst in der DB und sprengten später
            # int(Decimal-Inf) in umrechnen (→ 500). Endlichkeit explizit fordern.
            _k = Decimal(body.kurs.strip().replace(",", "."))
            if not _k.is_finite() or _k <= 0:
                raise ValueError
        except Exception:
            return JSONResponse({"error": "Kurs muss eine positive, endliche Zahl sein"},
                                status_code=400)
        kurs = body.kurs.strip().replace(",", ".")
        conn = db.get_conn()
        ts = now_iso()
        conn.execute(
            "INSERT INTO wechselkurse (id, user_id, waehrung, kurs, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT (user_id, waehrung) "
            "DO UPDATE SET kurs=excluded.kurs, updated_at=excluded.updated_at",
            (new_id(), user.user_id, w, kurs, ts, ts))
        conn.commit()
        db.audit(user.user_id, "user", "wechselkurs_gesetzt", {"waehrung": w})
        return {"ok": True, "waehrung": w, "kurs": kurs}

    # =================== Wiederkehrende Posten (Abos/Daueraufträge) ==========

    @router.get("/api/wiederkehr")
    def wiederkehr_liste(user: UserContext = Depends(current_user)):
        """Erkannte Serien aus der Historie + gespeicherte (bestätigte) Serien +
        die auf den Monat normierte Fixkosten-Grundlast."""
        heute = datetime.now().date().isoformat()
        erkannt = wkmodul.erkenne_serien(_buchungen_erkennung(user.user_id), heute=heute)
        gespeichert = _serien_gespeichert(user.user_id)
        bekannt = {s["schluessel"] for s in gespeichert if s["schluessel"]}
        for e in erkannt:
            e["schon_gespeichert"] = e["schluessel"] in bekannt
        # Abo-Kalender-Hilfen: Jahreskosten je Serie + „kündigen?"-Kandidat (das
        # teuerste Ausgabe-Abo) — datengetriebene Entscheidungshilfe, kein Auto-Eingriff.
        teuerste, teuerste_kosten = None, 0
        for s in gespeichert:
            tage = max(1, int(s.get("intervall_tage") or 30))
            jk = int(round(int(s.get("betrag", 0)) * 365 / tage))
            s["jahres_kosten"] = jk
            s["jahres_kosten_text"] = ledger.format_betrag(jk, "EUR")
            if jk < 0 and -jk > teuerste_kosten:        # Ausgabe (betrag<0)
                teuerste_kosten, teuerste = -jk, s["id"]
        for s in gespeichert:
            s["kuendigen_kandidat"] = (s["id"] == teuerste)
        return {"erkannt": erkannt, "gespeichert": gespeichert,
                "monatsbelastung": wkmodul.monatsbelastung(gespeichert)}

    @router.post("/api/wiederkehr")
    def wiederkehr_anlegen(body: SerieIn, user: UserContext = Depends(current_user)):
        """Speichert/bestätigt eine Serie (manuell oder aus einem Kandidaten).
        ``betrag`` ist die Magnitude; das Vorzeichen folgt aus ``richtung``."""
        if body.richtung not in ("einnahme", "ausgabe"):
            return JSONResponse({"error": "richtung muss einnahme|ausgabe sein"}, status_code=400)
        if body.kategorie_id and _kategorie(user.user_id, body.kategorie_id) is None:
            return JSONResponse({"error": "Kategorie unbekannt"}, status_code=404)
        if not _bereich_ok(user.user_id, body.bereich_id):
            return JSONResponse({"error": "Bereich unbekannt"}, status_code=400)
        try:
            magnitude = ledger.parse_betrag(body.betrag, "EUR")
        except ledger.LedgerError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if magnitude <= 0:
            return JSONResponse({"error": "Betrag muss > 0 sein"}, status_code=400)
        betrag = magnitude if body.richtung == "einnahme" else -magnitude
        tage = max(1, int(body.intervall_tage))
        # M-5: Fälligkeit ISO-validieren (Freitext wie '31.12.2026'/'=SUMME()' sprengte
        # sonst /wiederkehr/plan + /auswertung/kennzahlen dauerhaft mit 500); ungültig ⇒
        # das berechnete nächste Datum.
        faellig = _iso_tag(body.naechste_faelligkeit) or (
            datetime.now().date() + timedelta(days=tage)).isoformat()
        sid, ts = new_id(), now_iso()
        quelle = "erkannt" if body.schluessel else "manuell"
        db.get_conn().execute(
            "INSERT INTO serien (id, user_id, name, schluessel, betrag, waehrung, "
            "intervall, intervall_tage, naechste_faelligkeit, kategorie_id, richtung, "
            "aktiv, quelle, bereich_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)",
            (sid, user.user_id, body.name.strip() or "Serie", body.schluessel.strip(),
             betrag, "EUR", body.intervall, tage, faellig, body.kategorie_id,
             body.richtung, quelle, body.bereich_id, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "serie_gespeichert", {"name": body.name})
        return {"ok": True, "id": sid}

    @router.delete("/api/wiederkehr/{serie_id}")
    def wiederkehr_loeschen(serie_id: str, user: UserContext = Depends(current_user)):
        conn = db.get_conn()
        cur = conn.execute("UPDATE serien SET deleted_at=?, aktiv=0 WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (now_iso(), serie_id, user.user_id))
        conn.commit()
        if not cur.rowcount:
            return JSONResponse({"error": "Serie unbekannt"}, status_code=404)
        return {"ok": True}

    @router.get("/api/wiederkehr/plan")
    def wiederkehr_plan(von: str | None = None, bis: str | None = None,
                        user: UserContext = Depends(current_user)):
        """Vorschau der nächsten Fälligkeiten aus den gespeicherten Serien.
        Default-Fenster: ab heute über 90 Tage."""
        heute = datetime.now().date()
        von = von or heute.isoformat()
        bis = bis or (heute + timedelta(days=90)).isoformat()
        gespeichert = _serien_gespeichert(user.user_id)
        plan = wkmodul.plane(gespeichert, von, bis)
        for t in plan["termine"]:
            t["betrag_text"] = ledger.format_betrag(t["betrag"], "EUR")
        plan["monatsbelastung"] = wkmodul.monatsbelastung(gespeichert)
        return plan

    def _projektion(user_id: str, tage: int = 90) -> dict:
        """Liquiditäts-Projektion (auch von /insights genutzt): liquide Mittel
        heute + gespeicherte Fixposten fortgeschrieben; 30/60/90-Marken."""
        tage = max(7, min(int(tage), 366))
        heute = datetime.now().date()
        kurse = _kurse(user_id)
        start = 0
        for r in db.get_conn().execute(
                "SELECT ko.waehrung AS w, COALESCE(SUM(p.betrag),0) AS sm FROM postings p "
                "JOIN konten ko ON ko.id=p.konto_id WHERE ko.typ='asset' AND p.user_id=? "
                "AND p.deleted_at IS NULL GROUP BY ko.waehrung", (user_id,)).fetchall():
            try:
                start += ledger.umrechnen(r["sm"], r["w"], "EUR", kurse)
            except ledger.LedgerError:
                pass
        serien = _serien_gespeichert(user_id)
        plan = wkmodul.plane(serien, heute.isoformat(),
                             (heute + timedelta(days=tage)).isoformat())
        termine = sorted(plan["termine"], key=lambda t: t["datum"])
        marken = []
        for m in (30, 60, 90):
            if m <= tage:
                grenze = (heute + timedelta(days=m)).isoformat()
                saldo = start + sum(t["betrag"] for t in termine if t["datum"] <= grenze)
                marken.append({"tage": m, "datum": grenze, "saldo": saldo,
                               "saldo_text": ledger.format_betrag(saldo, "EUR"),
                               "negativ": saldo < 0})
        for t in termine:
            t["betrag_text"] = ledger.format_betrag(t["betrag"], "EUR")
        return {"tage": tage, "start": start,
                "start_text": ledger.format_betrag(start, "EUR"),
                "marken": marken, "termine": termine[:60]}

    @router.get("/api/auswertung/projektion")
    def auswertung_projektion(tage: int = 90, user: UserContext = Depends(current_user)):
        """P3: 30/60/90-Liquiditäts-Projektion (s. ``_projektion``)."""
        return _projektion(user.user_id, tage)

    @router.get("/api/auswertung/insights")
    def auswertung_insights(user: UserContext = Depends(current_user)):
        """P3: Spending-Insights / Anomalie-Hinweise — die App-Wächter-KI sichtbar
        gemacht. Deterministische Beobachtungen (Budget-Überzug, Liquiditäts-
        Warnung, Kategorie-Anomalie, Sparquote, größte Ausgabe). Kein Modell, 0 €.
        Beobachten + hinweisen, NIE eigenmächtig handeln (A1/HITL)."""
        heute = datetime.now().date().isoformat()
        bew = _bewegungen(user.user_id)
        ueberzogen = _finanz_schnappschuss(user.user_id)["budget_warnungen"]
        marken = _projektion(user.user_id, 90)["marken"]
        return {"insights": ausw.spending_insights(bew, heute,
                                                   budget_ueberzogen=ueberzogen,
                                                   projektion_marken=marken)}

    @router.post("/api/wiederkehr/{serie_id}/verbuchen")
    def wiederkehr_verbuchen(serie_id: str, body: VerbuchenIn,
                             user: UserContext = Depends(current_user)):
        """Bucht eine fällige Serie als echte Transaktion (schließt Plan → Ist):
        Bankkonto ↔ Sammelkonto „Nicht zugeordnet", Kategorie der Serie übernommen,
        danach rückt ``naechste_faelligkeit`` um ein Intervall weiter. Der Betrag
        (EUR) wird bei Fremdwährungs-Konto über den Kurs umgerechnet."""
        conn = db.get_conn()
        s = conn.execute(
            "SELECT * FROM serien WHERE id=? AND user_id=? AND aktiv=1 AND deleted_at IS NULL",
            (serie_id, user.user_id)).fetchone()
        if s is None:
            return JSONResponse({"error": "Serie unbekannt"}, status_code=404)
        bank = _konto(user.user_id, body.konto_id)
        if bank is None:
            return JSONResponse({"error": "Konto unbekannt"}, status_code=404)
        if bank["typ"] not in ("asset", "liability"):
            return JSONResponse(
                {"error": "Buchungskonto muss ein Bank-/Vermögenskonto sein"}, status_code=400)
        try:
            magnitude_eur = abs(int(s["betrag"]))
            betrag = ledger.pruefe_minor(ledger.umrechnen(magnitude_eur, "EUR", bank["waehrung"], _kurse(user.user_id)))
            if betrag <= 0:
                raise ledger.LedgerError("Betrag muss > 0 sein")
            sammel = _sammelkonto(user.user_id, bank["waehrung"])
            if s["richtung"] == "einnahme":
                buchung = ledger.einfache_buchung(sammel, body.konto_id, betrag, notiz=s["name"])
            else:
                buchung = ledger.einfache_buchung(body.konto_id, sammel, betrag, notiz=s["name"])
        except ledger.LedgerError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        bid, ts = new_id(), now_iso()
        datum = (body.datum.strip() or s["naechste_faelligkeit"])[:10]
        try:
            with db.transaktion() as conn:
                chronik_naht.pruefe_offen(conn, user.user_id, datum)   # §6.3: 409 im festgeschriebenen Monat
                conn.execute(
                    "INSERT INTO buchungen (id, user_id, notiz, datum, gegenpartei, "
                    "verwendungszweck, kategorie_id, quelle, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (bid, user.user_id, s["name"], datum, s["name"], s["name"],
                     s["kategorie_id"], "serie", ts, ts))
                for p in buchung.postings:
                    conn.execute(
                        "INSERT INTO postings (id, user_id, buchung_id, konto_id, betrag, created_at)"
                        " VALUES (?,?,?,?,?,?)",
                        (new_id(), user.user_id, bid, p.konto_id, p.betrag, ts))
                chronik_naht.schreibe_buchung(
                    conn, user.user_id, buchung_id=bid, datum=datum, quelle="serie",
                    postings=[(p.konto_id, p.betrag) for p in buchung.postings],
                    kategorie_id=s["kategorie_id"], notiz=s["name"],
                    gegenpartei=s["name"], verwendungszweck=s["name"])
                # Fälligkeit um ein Intervall weiterrücken (mind. einen Tag).
                from datetime import date as _date
                try:
                    naechste = (_date.fromisoformat(s["naechste_faelligkeit"][:10])
                                + timedelta(days=max(1, int(s["intervall_tage"])))).isoformat()
                except ValueError:
                    naechste = s["naechste_faelligkeit"]
                conn.execute("UPDATE serien SET naechste_faelligkeit=?, updated_at=? WHERE id=?",
                             (naechste, ts, serie_id))
        except chronik_naht.ZeitraumGesperrt as sperr:
            return _gesperrt_409(sperr.zeitraum)
        db.audit(user.user_id, "user", "serie_verbucht",
                 {"serie": serie_id, "buchung": bid})
        return {"ok": True, "buchung_id": bid, "naechste_faelligkeit": naechste}

    # =================== Teil D: Steuer-Sektor (licht) ======================

    def _steuer_jahr(user_id: str, jahr: int, nur_steuer: bool) -> dict:
        return ausw.eur_jahr(_bewegungen(user_id), jahr, nur_steuer=nur_steuer)

    @router.get("/api/steuer/jahr")
    def steuer_jahr(jahr: int | None = None, nur_steuer: bool = False,
                    user: UserContext = Depends(current_user)):
        """EÜR-artige Jahres-Übersicht: Einnahmen-Überschuss je Kategorie.
        KEINE Steuererklärung / kein Filing — nur eine Auswertung zum Überblick."""
        jahr = jahr or datetime.now().year
        erg = _steuer_jahr(user.user_id, jahr, nur_steuer)
        # Anzeige-Texte ergänzen (Beträge bleiben als Minor-Units erhalten).
        for feld in ("einnahmen", "ausgaben", "ueberschuss"):
            erg[f"{feld}_text"] = ledger.format_betrag(erg[feld], "EUR")
        for k in erg["je_kategorie"]:
            for feld in ("einnahmen", "ausgaben", "ueberschuss"):
                k[f"{feld}_text"] = ledger.format_betrag(k[feld], "EUR")
        return erg

    @router.get("/api/steuer/export")
    def steuer_export(jahr: int | None = None, format: str = "json",
                      nur_steuer: bool = False,
                      user: UserContext = Depends(current_user)):
        """Export der Jahres-Auswertung als JSON oder CSV (Download). Aggregierte
        Zahlen, keine Geheimnisse — daher Stufe 'lokal' (der Voll-Export mit
        Re-Auth ist /api/account/export aus dem Vertrag)."""
        jahr = jahr or datetime.now().year
        if format not in ("json", "csv"):
            return JSONResponse({"error": "format muss json|csv sein"}, status_code=400)
        erg = _steuer_jahr(user.user_id, jahr, nur_steuer)
        db.audit(user.user_id, "user", "steuer_exportiert",
                 {"jahr": jahr, "format": format})
        dateiname = f"dizz-money-euer-{jahr}.{format}"
        if format == "json":
            import json as _json
            return PlainTextResponse(
                _json.dumps(erg, ensure_ascii=False, indent=2),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{dateiname}"'})
        # CSV: eine Zeile je Kategorie + Summenzeile; Beträge als Dezimal (Punkt).
        import csv as _csv
        import io as _io
        puffer = _io.StringIO()
        schreiber = _csv.writer(puffer, delimiter=";")
        schreiber.writerow(["Kategorie", "steuerrelevant", "Steuer-Art",
                            "Einnahmen", "Ausgaben", "Ueberschuss"])
        for k in erg["je_kategorie"]:
            schreiber.writerow([
                csv_safe(k["kategorie_name"]), "ja" if k["steuer_relevant"] else "nein",
                csv_safe(k["steuer_art"]), ledger.format_betrag(k["einnahmen"], "EUR"),
                ledger.format_betrag(k["ausgaben"], "EUR"),
                ledger.format_betrag(k["ueberschuss"], "EUR")])
        schreiber.writerow([f"SUMME {jahr}", "", "",
                           ledger.format_betrag(erg["einnahmen"], "EUR"),
                           ledger.format_betrag(erg["ausgaben"], "EUR"),
                           ledger.format_betrag(erg["ueberschuss"], "EUR")])
        return PlainTextResponse(
            puffer.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{dateiname}"'})

    @router.get("/", include_in_schema=False)
    def startseite(request: Request):
        """Dizz-Money-Oberfläche (tokenbasiert, News-Muster). Eigenständig nutzbar.
        NONCE-VORBEREITET (docs/37): liefert die HTML über ``serve_html_mit_csp``
        mit Per-Request-Nonce aus (injiziert in jeden Inline-``<script>``/``<style>``).
        Die Inline-Event-Handler sind bereits auf ``data-dz-act`` (DzActions) umgestellt
        ⇒ voll-strikt einschaltbar, SOBALD ``build_csp`` style-src ``'unsafe-inline'``
        behält (s. ``csp_strikt`` unten + FÜR-WORLD-CHAT-Notiz). Unter der aktuellen
        Baseline-CSP ist die Nonce-Injektion inert (Inline läuft via 'unsafe-inline')."""
        datei = Path(__file__).resolve().parents[1] / "static" / "index.html"
        if not datei.is_file():
            return PlainTextResponse("Frontend nicht gefunden.", status_code=404)
        from appkit.csp import serve_html_mit_csp
        return serve_html_mit_csp(request, datei)

    def summary() -> list[Kpi]:
        # Kachel ist single-user (DEFAULT_USER_ID) — sie läuft ohne Request-
        # Kontext ("immer 200"-Endpoint des Vertrags).
        conn = db.get_conn()
        n_konten = conn.execute(
            "SELECT COUNT(*) AS n FROM konten WHERE user_id=? AND deleted_at IS NULL",
            (DEFAULT_USER_ID,)).fetchone()["n"]
        # Nettovermögen = Asset − Liability, je Währung roh summiert und nach EUR
        # umgerechnet (≈ bei Fremdwährung). Konsistent mit /vermoegen + /kennzahlen,
        # damit ein Nutzer mit Fremdwährungs-Konten nicht „0" in der Kachel sieht.
        kurse = _kurse(DEFAULT_USER_ID)
        netto = 0
        for r in conn.execute(
                "SELECT ko.waehrung AS w, COALESCE(SUM(p.betrag),0) AS s FROM postings p "
                "JOIN konten ko ON ko.id=p.konto_id "
                "WHERE ko.typ IN ('asset','liability') AND p.user_id=? "
                "AND p.deleted_at IS NULL GROUP BY ko.waehrung", (DEFAULT_USER_ID,)).fetchall():
            try:
                netto += ledger.umrechnen(r["s"], r["w"], "EUR", kurse)
            except ledger.LedgerError:
                pass
        # Cashflow der letzten 30 Tage (deterministisch über die reine Funktion).
        # LOKALES Datum (wie Buchungsdaten + restliche Endpoints) — UTC würde am
        # Tagesrand heutige Buchungen aus dem Fenster fallen lassen.
        heute = datetime.now().date()
        cf = ausw.cashflow(_bewegungen(DEFAULT_USER_ID),
                           von=(heute - timedelta(days=30)).isoformat(),
                           bis=heute.isoformat())
        kpis = [
            Kpi(id="netto", label="Nettovermögen",
                value=ledger.format_betrag(netto, "EUR"), unit="EUR"),
            Kpi(id="konten", label="Konten", value=n_konten, unit="Stk"),
        ]
        if cf["einnahmen"] or cf["ausgaben"]:
            trend = "up" if cf["saldo"] >= 0 else "down"
            kpis.append(Kpi(id="cashflow_30t", label="Cashflow 30T",
                            value=ledger.format_betrag(cf["saldo"], "EUR"),
                            unit="EUR", trend=trend))
            if cf["einnahmen"] > 0:
                # Sparquote = welcher Anteil der Einnahmen blieb übrig (30T).
                quote = round(cf["saldo"] * 100 / cf["einnahmen"])
                kpis.append(Kpi(id="sparquote_30t", label="Sparquote 30T",
                                value=quote, unit="%",
                                trend="up" if quote >= 0 else "down"))
        fix = wkmodul.monatsbelastung(_serien_gespeichert(DEFAULT_USER_ID))
        if fix["einnahmen"] or fix["ausgaben"]:
            kpis.append(Kpi(id="fixkosten_monat", label="Fixkosten/Monat",
                            value=ledger.format_betrag(fix["ausgaben"], "EUR"), unit="EUR"))
        return kpis

    # =================== App-Wächter-KI (Mini-Dizzi, set_app_ki) =============

    def _finanz_schnappschuss(user_id: str) -> dict:
        """Verdichtet die Finanzlage zu Kennzahlen — die Wissensbasis der App-KI.
        Reine Aggregation über die bestehenden (geprüften) Auswertungen."""
        heute = datetime.now().date()   # lokal (konsistent mit Buchungsdaten)
        bew = _bewegungen(user_id)
        cf30 = ausw.cashflow(bew, von=(heute - timedelta(days=30)).isoformat(),
                             bis=heute.isoformat())
        cf90 = ausw.cashflow(bew, von=(heute - timedelta(days=90)).isoformat(),
                             bis=heute.isoformat())
        rows = db.get_conn().execute(
            "SELECT k.id, k.name, k.typ, k.waehrung, "
            "COALESCE((SELECT SUM(p.betrag) FROM postings p WHERE p.konto_id=k.id "
            "AND p.user_id=k.user_id AND p.deleted_at IS NULL),0) AS roh_saldo "
            "FROM konten k WHERE k.user_id=? AND k.deleted_at IS NULL", (user_id,)).fetchall()
        verm = ausw.vermoegen([dict(r) for r in rows])
        kurse = _kurse(user_id)
        netto_eur = 0
        for w, roh in verm["netto_je_waehrung"].items():
            try:
                netto_eur += ledger.umrechnen(roh, w, "EUR", kurse)
            except ledger.LedgerError:
                pass
        # Budget-Warnungen laufender Monat
        monat = heute.isoformat()[:7]
        budgets = db.get_conn().execute(
            "SELECT b.kategorie_id, b.monat, b.betrag, k.name AS kategorie_name "
            "FROM budgets b LEFT JOIN kategorien k ON k.id=b.kategorie_id "
            "WHERE b.user_id=? AND b.deleted_at IS NULL AND (b.monat=? OR b.monat='*')",
            (user_id, monat)).fetchall()
        cfm = ausw.cashflow(bew, von=f"{monat}-01", bis=f"{monat}-31")
        ist = {e["kategorie_id"]: e["ausgaben"] for e in cfm["je_kategorie"] if e["kategorie_id"]}
        ueberzogen = [b for b in ausw.budget_status([dict(x) for x in budgets], ist)
                      if b["ueberzogen"]]
        # Fixkosten + nächster Termin
        serien = _serien_gespeichert(user_id)
        mb = wkmodul.monatsbelastung(serien)
        plan = wkmodul.plane(serien, heute.isoformat(),
                             (heute + timedelta(days=31)).isoformat())
        top_aus = [e for e in cf90["je_kategorie"] if e["ausgaben"] > 0][:3]
        return {"netto_eur": netto_eur, "je_waehrung": verm["netto_je_waehrung"],
                "cf30": cf30, "konten": verm["konten"], "top_ausgaben": top_aus,
                "fixkosten": mb, "naechster_termin": plan["termine"][0] if plan["termine"] else None,
                "budget_warnungen": ueberzogen}

    @router.get("/api/auswertung/kennzahlen")
    def auswertung_kennzahlen(user: UserContext = Depends(current_user)):
        """Kompaktes Kennzahlen-Bündel für die Kopf-Leiste (und Dizzis Kachel):
        Nettovermögen, Cashflow 30T, Sparquote, Fixkosten/Monat, nächste
        Fälligkeit, Anzahl überzogener Budgets. Formatiert + Roh-Minor."""
        s = _finanz_schnappschuss(user.user_id)
        cf = s["cf30"]
        sparquote = round(cf["saldo"] * 100 / cf["einnahmen"]) if cf["einnahmen"] > 0 else None
        # Liquide Mittel = Summe der ASSET-Konten (Bar/Bank, EUR-aggregiert) — das frei
        # verfügbare Geld (Norm-KPI), getrennt vom Nettovermögen (Asset − Schulden).
        kurse = _kurse(user.user_id)
        liquide = 0
        for r in db.get_conn().execute(
                "SELECT ko.waehrung AS w, COALESCE(SUM(p.betrag),0) AS sm FROM postings p "
                "JOIN konten ko ON ko.id=p.konto_id WHERE ko.typ='asset' AND p.user_id=? "
                "AND p.deleted_at IS NULL GROUP BY ko.waehrung", (user.user_id,)).fetchall():
            try:
                liquide += ledger.umrechnen(r["sm"], r["w"], "EUR", kurse)
            except ledger.LedgerError:
                pass
        return {
            "netto_eur": s["netto_eur"], "netto_eur_text": ledger.format_betrag(s["netto_eur"], "EUR"),
            "liquide_mittel": liquide, "liquide_mittel_text": ledger.format_betrag(liquide, "EUR"),
            "cashflow_30t": cf["saldo"], "cashflow_30t_text": ledger.format_betrag(cf["saldo"], "EUR"),
            "einnahmen_30t_text": ledger.format_betrag(cf["einnahmen"], "EUR"),
            "ausgaben_30t_text": ledger.format_betrag(cf["ausgaben"], "EUR"),
            "sparquote_30t": sparquote,
            "fixkosten_monat": s["fixkosten"]["ausgaben"],
            "fixkosten_monat_text": ledger.format_betrag(s["fixkosten"]["ausgaben"], "EUR"),
            "naechster_termin": s["naechster_termin"],
            "budget_warnungen": len(s["budget_warnungen"])}

    def _finanz_ki(frage: str):
        """App-eigene Finanz-KI (Vertrag A1/Mini-Dizzi): beantwortet die
        häufigsten Fragen DETERMINISTISCH aus den echten Zahlen. Unbekanntes ⇒
        leere Antwort → Mini-Dizzi fällt auf den lokalen Ollama-Kontext zurück."""
        t = (frage or "").lower()
        snap = _finanz_schnappschuss(DEFAULT_USER_ID)
        e = lambda c: ledger.format_betrag(c, "EUR")

        if any(w in t for w in ("vermög", "vermoeg", "netto", "reich", "gesamtwert", "wie viel hab")):
            zusatz = ""
            fremd = {w: v for w, v in snap["je_waehrung"].items() if w != "EUR" and v}
            if fremd:
                zusatz = " (inkl. Fremdwährungen, umgerechnet ≈)"
            return {"antwort": f"Dein Nettovermögen beträgt ≈ {e(snap['netto_eur'])} EUR{zusatz}."}
        if any(w in t for w in ("cashflow", "einnahm", "ausgab", "spar", "übrig", "uebrig")):
            cf = snap["cf30"]
            return {"antwort": f"Letzte 30 Tage: Einnahmen {e(cf['einnahmen'])} €, "
                    f"Ausgaben {e(cf['ausgaben'])} €, Saldo {e(cf['saldo'])} €."}
        if any(w in t for w in ("budget", "überzog", "ueberzog", "limit")):
            ub = snap["budget_warnungen"]
            if not ub:
                return {"antwort": "Alle Budgets liegen diesen Monat im Rahmen. 👍"}
            namen = ", ".join(f"{b['kategorie_name']} ({b['prozent']}%)" for b in ub)
            return {"antwort": f"Überzogen diesen Monat: {namen}."}
        if any(w in t for w in ("abo", "wiederkehr", "dauerauftrag", "fixkost", "monatlich")):
            mb = snap["fixkosten"]
            nt = snap["naechster_termin"]
            text = f"Fixkosten ≈ {e(abs(mb['ausgaben']))} €/Monat bei Fix-Einnahmen {e(mb['einnahmen'])} €/Monat."
            if nt:
                text += f" Nächste Fälligkeit: {nt['name']} am {nt['datum']} ({e(nt['betrag'])} €)."
            return {"antwort": text}
        if any(w in t for w in ("konto", "konten", "kontostand", "saldo", "guthaben")):
            zeilen = [f"{k['name']}: {ledger.format_betrag(k['saldo_minor'], k['waehrung'])} {k['waehrung']}"
                      for k in snap["konten"] if k["typ"] in ("asset", "liability")][:8]
            return {"antwort": "Konten — " + "; ".join(zeilen) if zeilen else
                    "Es sind noch keine Konten angelegt."}
        if any(w in t for w in ("wofür", "wofuer", "teuerst", "top ausgab", "größte ausgab", "groesste ausgab")):
            top = snap["top_ausgaben"]
            if not top:
                return {"antwort": "Noch keine Ausgaben erfasst."}
            namen = ", ".join(f"{k['kategorie_name']} ({e(k['ausgaben'])} €)" for k in top)
            return {"antwort": f"Größte Ausgaben (90 Tage): {namen}."}
        return ""   # nicht erkannt ⇒ Mini-Dizzi-Fallback (Ollama mit KPIs)

    def _raeume_money_artefakte(user_id: str) -> None:
        """on_delete-Hook (DSGVO „weg = weg", H-7-Muster): user-Tabellen OHNE
        ``deleted_at`` (reine Stamm-/Config-Daten) überspringt ``soft_delete_user`` —
        sie werden hier bei der Konto-Löschung HART entfernt. Aktuell: ``wechselkurse``
        (Kurs-Stammdaten) + ``trading_config`` (steuerliche Parameter)."""
        conn = db.get_conn()
        for t in ("wechselkurse", "trading_config"):
            conn.execute(f"DELETE FROM {t} WHERE user_id=?", (user_id,))
        conn.commit()

    # RG-8 (docs/83 §6): Geschäfts-Kopplung — dormante beleg_vorschlagen-Naht (Registry-
    # Vertrag, level hochsicher ⇒ Klasse geld ⇒ Boden pre_approval) + Ereignis-Spine
    # (beleg_angelegt + netzweit hitl_entschieden). Bucht NIE — der ledger/EÜR-Kern bleibt
    # unberührt (kein EÜR-/Buchungs-Code angefasst).
    _EREIGNIS_REGISTER = ereignis_spine.standard_register(APP_ID)
    geschaefts_regie.registriere_ereignis_typen(_EREIGNIS_REGISTER)
    actions = ActionRegistry()
    geschaefts_regie.registriere(actions, db, _EREIGNIS_REGISTER)

    app = create_app(MANIFEST, db, summary_fn=summary,
                     routers=[router, bereiche.build_router(),
                              elster_speicher.build_router(),
                              ust_speicher.build_router(bewegungen_fn=_ust_bewegungen),
                              geschaefts_regie.build_router(db)],
                     version=__version__, on_delete=_raeume_money_artefakte,
                     actions=actions, ereignis_register=_EREIGNIS_REGISTER,
                     # BZ-C-7 (docs/80 §6.3): §147-AO-Aufbewahrung überlagert die DSGVO-Löschung —
                     # buchungen/postings/festschreibungen bleiben als pseudonymes Gerippe.
                     bewahre_bei_loeschung=chronik_naht.BEWAHRE_BEI_LOESCHUNG,
                     # CSP: Inline-Handler sind auf data-dz-act umgestellt + GET / liefert Nonce
                     # (voll-strikt VORBEREITET, docs/37). Bleibt vorerst BASELINE (strikt=False):
                     # appkit 1.24.0 build_csp setzt im strikt-Modus style-src auf 'self' 'nonce-…'
                     # CSP voll-strikt (Nonce), docs/37. style-src bleibt seit appkit 1.24.1
                     # 'unsafe-inline' (Stil-Attribute bleiben erlaubt — der vom finanzen-Chat
                     # empirisch belegte Layout-Bruch ist damit behoben); nur script-src ist nonce-strikt.
                     csp_mode="enforce", csp_strikt=True)
    if getattr(app.state, "mini_dizzi", None) is not None:
        app.state.mini_dizzi.set_app_ki(_finanz_ki)   # A1: echter Finanz-Kontext
    install_dizzi_id(app, MANIFEST, data_root=root)

    # ELSTER M1-2 (docs/65 §8/§12): die VAULT-abhängigen Nähte NACH create_app
    # verdrahten — jetzt existiert app.state.vault. persistenz bleibt selbst vault-frei
    # (geheimnis-frei), bekommt hier aber die PIN-PRÄSENZ-Sonde (für die Zugangs-Liste)
    # + den Secret-Aufräumer beim Löschen (Vault-PIN + .pfx). Der Konnektor macht den
    # Sende-Kanal in /api/konnektoren sichtbar (verbunden erst mit Zertifikat+PIN+scharf).
    from .elster import konnektor as elsterkonnektor  # noqa: E402
    _elster_vault = app.state.vault
    elster_speicher.set_pin_check(lambda key: _elster_vault.get(key) is not None)
    elster_speicher.set_aufraeumer(
        elsterkonnektor.mache_aufraeumer(elster_speicher, _elster_vault))
    app.include_router(
        elsterkonnektor.build_konnektor_router(elster_speicher, _elster_vault))

    # Per-App-MCP-Gateway (docs/31 §7): im Standalone-Betrieb bietet die App ihr EIGENES
    # read-only MCP-Gate (/mcp) an; im Verbund (Modus 'auto') schaltet es ab, sobald der
    # Core sein zentrales Gateway führt. Gleiche Tool-Quelle wie der stdio-MCP. opt-in/Token.
    from . import mcp_tools  # noqa: E402  (Tool-Quelle, lokal importiert)
    from appkit.app_gateway import build_app_gateway  # noqa: E402
    app.include_router(build_app_gateway(
        MANIFEST, db, tools=mcp_tools.MCP_TOOLS,
        base_url=f"http://127.0.0.1:{MANIFEST.port}"))
    # K2.4: app-neutrales ui-kit-Bundle (controls.css/collapse.js/tokens.css) als
    # Single-Source ausliefern — das Frontend referenziert die Schicht (kopiert
    # keine Werte). Read-only statisch, kein Geheimnis.
    ui_kit = ui_kit_path()
    if ui_kit.is_dir():
        from fastapi.staticfiles import StaticFiles
        class _UiKitFiles(StaticFiles):  # H-1: Cache-Control no-cache -> Revalidierung via ETag
            async def get_response(self, path, scope):
                resp = await super().get_response(path, scope)
                resp.headers["Cache-Control"] = "no-cache"
                return resp
        app.mount("/ui-kit", _UiKitFiles(directory=str(ui_kit)), name="ui-kit")
    return app


def app_factory():
    return build_app()
