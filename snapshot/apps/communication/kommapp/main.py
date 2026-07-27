"""Dizz Communication — App-Zusammenbau auf dem App-Vertrag (Port 8218).

Kanal-agnostisches Schema (Dossier §5): konto → konversation → nachricht,
plus Kontakte als kanalübergreifende Klammer. E-Mail ist der erste Stecker
(mail.py); Matrix/Webview docken später an DASSELBE Schema an — kein Umbau.

Sicherheits-Linie (sensitivity hoechst):
- Geheimnisse (Passwort/Token) NUR im K2-Tresor (Konten-Tabelle hält tresor_ref).
- KI-Routing default lokal_only (kommt aus make_schema für hoechst-Apps).
- **Senden = HITL-Aktion** auf Stufe ``verifiziert`` — ohne Dizzi-ID-Login
  bleibt jeder Versand fail-closed liegen (K4-Pipeline, nie autonom).

Start: <venv-python> -m uvicorn kommapp.main:app_factory --factory
       --host 127.0.0.1 --port 8218 --app-dir <kommunikation-ordner>
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, channels, connectors_katalog, gmail, meta, telegram
from .channels import AusgehendeNachricht, KanalNichtVerbunden
from .kontakte import finde_merge_vorschlaege

from appkit.connectors import ConnectorRegistry  # noqa: E402 (Pfad-Shim)
from appkit import ui_kit_path
from .mail import (KANAL_EMAIL, MARKIER_FLAGS, STANDARD_ENTWURF_ORDNER,
                   ImapQuelle, JmapQuelle, KanalFehler, KanalQuelle,
                   OrdnerZustand, baue_entwurf_bytes, sende_mail, _re_betreff)

from appkit.actions import ActionRegistry  # noqa: E402  (Pfad-Shim in __init__)
from appkit.app import create_app
from appkit.auth import DEFAULT_USER_ID, UserContext, current_user
from appkit.db import Database, default_db_path, new_id, now_iso
from appkit import ereignis_spine
from appkit.dizzi_id import install_dizzi_id
from appkit.manifest import AppManifest, McpInfo, Shares
from appkit.settings_core import SettingDef, make_schema
from appkit.summary import Kpi

APP_ID = "kommunikation"

MANIFEST = AppManifest(
    id=APP_ID, name="Nachrichtenverkehr", brand="Dizz Communication",
    version=__version__, port=8218, icon="mail", sensitivity="hoechst",
    mcp=McpInfo(command=["<venv-python>", "mcp_server.py"],
                tools=["kachel_stats", "posteingang_uebersicht", "ungelesen",
                       "letzte_nachrichten", "konten",
                       "mail_senden_vorschlagen"]),   # einziges Aktions-Tool (HITL)
    shares=Shares(summary=True, tools=["kachel_stats"]),
    depends=[],
)

# RG-2 (docs/83 §5): Ereignis-Spine-Register — netzweite Standard-Typen
# (hitl_entschieden) + die zwei Mail-Typen des E-Mail-Piloten. NUR Zeiger/Skalare
# (Konto-ID, Kanal, Ordner) — kein Betreff/Absender/Text (der Register-Vertrag
# erzwingt es fail-closed). kommunikation ist sensitivity 'hoechst' ⇒ diese
# Ereignisse erreichen via ereignis_zustellbar nur höchst-Agenten (lokal_only).
_EREIGNIS_REGISTER = ereignis_spine.standard_register(APP_ID)
_EREIGNIS_REGISTER.register("mail_eingegangen", ("konto_id", "kanal_typ", "ordner"))
_EREIGNIS_REGISTER.register("mail_gesendet", ("konto_id", "kanal_typ"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS konten (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    art         TEXT NOT NULL DEFAULT 'imap',   -- imap | gmail_api | jmap | matrix (Slots)
    host        TEXT NOT NULL DEFAULT '',
    port        INTEGER NOT NULL DEFAULT 993,
    benutzer    TEXT NOT NULL DEFAULT '',
    auth        TEXT NOT NULL DEFAULT 'passwort',  -- passwort | xoauth2
    tresor_ref  TEXT NOT NULL DEFAULT '',       -- Name im K2-Tresor (NIE das Geheimnis!)
    smtp_host   TEXT NOT NULL DEFAULT '',
    smtp_port   INTEGER NOT NULL DEFAULT 587,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE TABLE IF NOT EXISTS ordner_zustand (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    konto_id     TEXT NOT NULL,
    ordner       TEXT NOT NULL,
    uidvalidity  INTEGER NOT NULL DEFAULT 0,
    uidnext      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT,
    UNIQUE (konto_id, ordner)
);
CREATE TABLE IF NOT EXISTS kontakte (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    kategorie   TEXT NOT NULL DEFAULT '',       -- '' | freund | familie | geschaeft | service | haendler | behoerde | sonstiges
    favorit     INTEGER NOT NULL DEFAULT 0,     -- 0/1; Favoriten immer oben in der Kontakte-Liste
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE TABLE IF NOT EXISTS kontakt_adressen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    kontakt_id  TEXT NOT NULL,
    kanal_typ   TEXT NOT NULL,                  -- email | matrix | whatsapp | …
    adresse     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    UNIQUE (user_id, kanal_typ, adresse)
);
CREATE TABLE IF NOT EXISTS konversationen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    konto_id    TEXT NOT NULL,
    kanal_typ   TEXT NOT NULL,
    extern_id   TEXT NOT NULL,                  -- Thread-Schlüssel des Kanals
    titel       TEXT NOT NULL DEFAULT '',
    schlummern_bis TEXT NOT NULL DEFAULT '',     -- ISO; > jetzt ⇒ aus dem Posteingang ausgeblendet (Snooze)
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    UNIQUE (user_id, konto_id, extern_id)
);
CREATE TABLE IF NOT EXISTS nachrichten (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    konversation_id  TEXT NOT NULL,
    kanal_typ        TEXT NOT NULL,
    extern_id        TEXT NOT NULL,             -- Message-ID/Event-ID des Kanals
    richtung         TEXT NOT NULL DEFAULT 'ein',  -- ein | aus
    von_adresse      TEXT NOT NULL DEFAULT '',
    an_adressen      TEXT NOT NULL DEFAULT '',
    betreff          TEXT NOT NULL DEFAULT '',
    text             TEXT NOT NULL DEFAULT '',
    ordner           TEXT NOT NULL DEFAULT 'INBOX', -- Quell-Ordner (Filter Teil B)
    gelesen          INTEGER NOT NULL DEFAULT 0,    -- 0=ungelesen, 1=gelesen
    gesendet_at      TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    deleted_at       TEXT,
    UNIQUE (user_id, konversation_id, extern_id)
);
CREATE INDEX IF NOT EXISTS idx_nachrichten ON nachrichten (user_id, created_at);
-- Perf (27.06.2026, Funktions-Forscher): /api/konversationen aggregiert per Konversation
-- (LEFT JOIN + 2 korrelierte Subqueries „jüngste Nachricht je Konversation"). OHNE Index auf
-- konversation_id scannt SQLite die ganze nachrichten-Tabelle je Konversation ⇒ O(K×N), ~12 s
-- live bei 2150 Konversationen (limit-unabhängig, da GROUP BY vor LIMIT). Mit diesem Index
-- (konversation_id, deleted_at) wird jede Aggregation/Subquery ein Index-SEEK ⇒ ~360× (12 s → ms).
CREATE INDEX IF NOT EXISTS idx_nachrichten_konv ON nachrichten (konversation_id, deleted_at);
CREATE TABLE IF NOT EXISTS kalender_termine (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    titel        TEXT NOT NULL DEFAULT 'Termin',
    beginn       TEXT NOT NULL,                  -- ISO-8601 (Date oder DateTime)
    ende         TEXT NOT NULL DEFAULT '',
    ganztags     INTEGER NOT NULL DEFAULT 0,
    ort          TEXT NOT NULL DEFAULT '',
    beschreibung TEXT NOT NULL DEFAULT '',
    quelle       TEXT NOT NULL DEFAULT 'querverbindung', -- absendende App-id
    extern_id    TEXT NOT NULL DEFAULT '',              -- ref (Idempotenz-Schlüssel)
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT,
    UNIQUE (user_id, quelle, extern_id)
);
CREATE INDEX IF NOT EXISTS idx_kalender_termine ON kalender_termine (user_id, beginn);
CREATE TABLE IF NOT EXISTS querverbindungen (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    konversation_id TEXT NOT NULL,
    ziel            TEXT NOT NULL,            -- 'memory' | 'admin' (Ziel-App)
    ref             TEXT NOT NULL DEFAULT '', -- Drill-down-/Idempotenz-Schlüssel (komm:konv:… / komm:termin:…)
    extern_id       TEXT NOT NULL DEFAULT '', -- id beim Ziel (best-effort)
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT,
    UNIQUE (user_id, konversation_id, ziel)
);
CREATE INDEX IF NOT EXISTS idx_querverbindungen ON querverbindungen (user_id, konversation_id);
CREATE TABLE IF NOT EXISTS labels (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    farbe       TEXT NOT NULL DEFAULT 'cy',     -- Token-Akzent: cy | mg | ok | warn
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    UNIQUE (user_id, name)
);
CREATE TABLE IF NOT EXISTS konversation_labels (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    konversation_id TEXT NOT NULL,
    label_id        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    deleted_at      TEXT,
    UNIQUE (user_id, konversation_id, label_id)
);
CREATE INDEX IF NOT EXISTS idx_konv_labels ON konversation_labels (user_id, konversation_id);
"""

# Spalten, die nach dem Erst-Release dazukamen (Teil B 13.06.). Frische DBs holen
# sie aus _SCHEMA; BESTANDS-DBs (live) bekommen sie hier per ALTER nachgezogen —
# ``CREATE TABLE IF NOT EXISTS`` ändert eine vorhandene Tabelle nicht.
_MIGRATIONEN: dict[str, list[tuple[str, str]]] = {
    "nachrichten": [
        ("ordner", "ALTER TABLE nachrichten ADD COLUMN ordner TEXT NOT NULL DEFAULT 'INBOX'"),
        ("gelesen", "ALTER TABLE nachrichten ADD COLUMN gelesen INTEGER NOT NULL DEFAULT 0"),
    ],
    "konversationen": [
        ("schlummern_bis",
         "ALTER TABLE konversationen ADD COLUMN schlummern_bis TEXT NOT NULL DEFAULT ''"),
    ],
    "kontakte": [
        ("kategorie", "ALTER TABLE kontakte ADD COLUMN kategorie TEXT NOT NULL DEFAULT ''"),
        ("favorit", "ALTER TABLE kontakte ADD COLUMN favorit INTEGER NOT NULL DEFAULT 0"),
    ],
}

# Kontakt-Kategorien (Nutzer-Entscheid „Erweitert", 26.06.): Slug → Anzeige übernimmt
# das Frontend. '' = unkategorisiert. Validierung der Setz-Endpoints gegen dieses Set.
KONTAKT_KATEGORIEN = ("", "freund", "familie", "geschaeft", "service",
                      "haendler", "behoerde", "sonstiges")


# Split-/Smart-Inbox (P1b, docs/27 §3): deterministische Sektion aus dem Absender —
# lokal, kein LLM nötig (die KI-Triage verfeinert später). Spark-Muster
# Wichtig/Benachrichtigungen/Newsletter.
_RE_NEWSLETTER = re.compile(
    r"news[-_.]?letter|mailing|newsletter|bulletin|digest|do[-_. ]?not[-_. ]?reply"
    r"|no[-_.]?reply|noreply|updates?@|marketing@", re.I)
_RE_BENACHR = re.compile(
    r"notif|alert|notify|automated|mailer-daemon|postmaster|git(hu|la)b|gitlab"
    r"|jira|trello|calendar|billing|invoice|receipt|support@|service@|account@"
    r"|security@|team@|hello@", re.I)


def sektion_aus_absender(von: str) -> str:
    """'wichtig' | 'benachrichtigung' | 'newsletter' aus der Absender-Adresse."""
    v = von or ""
    if _RE_NEWSLETTER.search(v):
        return "newsletter"
    if _RE_BENACHR.search(v):
        return "benachrichtigung"
    return "wichtig"


def _migriere(db: Database) -> None:
    """Idempotente Spalten-Migration für Bestands-DBs (s. _MIGRATIONEN)."""
    conn = db.get_conn()
    for tabelle, spalten in _MIGRATIONEN.items():
        vorhanden = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabelle})")}
        for name, ddl in spalten:
            if name not in vorhanden:
                conn.execute(ddl)
    conn.commit()

QuellenFactory = Callable[[dict[str, Any], str], KanalQuelle]


class _KontoIn(BaseModel):
    # Modul-Ebene zwingend (PEP-563-Falle, s. templates/refapp/README).
    name: str
    host: str
    benutzer: str
    geheimnis: str                       # wandert in den Tresor, NIE in die DB
    auth: str = "passwort"               # passwort | xoauth2
    port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587


class _SyncIn(BaseModel):
    konto_id: str
    ordner: str = "INBOX"


class _GelesenIn(BaseModel):
    gelesen: bool = True              # True=als gelesen, False=als ungelesen markieren


class _EntwurfIn(BaseModel):
    hinweis: str = ""                # optionales Stichwort, was der Nutzer sagen will


class _SchlummernIn(BaseModel):
    bis: str = ""                    # ISO-Zeit; leer ⇒ aufwecken (Snooze aufheben)


class _LabelIn(BaseModel):
    name: str = ""
    farbe: str = "cy"                # Token-Akzent: cy | mg | ok | warn


class _KontaktIn(BaseModel):
    name: str = ""                   # Smart Contacts: kanonischen Kontakt anlegen


class _AliasIn(BaseModel):
    kanal_typ: str = ""              # email | telegram | whatsapp | instagram | snapchat
    adresse: str = ""                # Kanal-Identität (Adresse/Handle/Telefon)


class _MergeIn(BaseModel):
    anderer_id: str = ""             # Kontakt, der in den Ziel-Kontakt aufgeht


class _SplitIn(BaseModel):
    adress_id: str = ""              # Alias, der zu einem eigenen Kontakt wird


class _KategorieIn(BaseModel):
    kategorie: str = ""              # eine aus KONTAKT_KATEGORIEN ('' = unkategorisiert)


class _FavoritIn(BaseModel):
    favorit: bool | None = None      # None = umschalten; sonst explizit setzen


class _SimIn(BaseModel):
    """Demo-Ingest (docs/35 §6: andere Kanäle simuliert): eine eingehende
    Nachricht auf einem dormanten Kanal vortäuschen, damit „ein Kontakt über alle
    Kanäle, ein Thread" real demonstrierbar ist. KEINE Plattform-Anbindung."""
    von: str = ""                    # Absender-Handle (=Kanal-Alias des Kontakts)
    text: str = ""
    betreff: str = ""


class _MetaVerbindenIn(BaseModel):
    """Meta-Verbinden-Flow (docs/38): Secrets → Tresor, nicht-geheime IDs → Settings.
    Leere Felder werden ignoriert (teil-aktualisierbar). KEINE Werte ins Audit."""
    kanal: str = ""                  # whatsapp | instagram
    token: str = ""                  # Access-Token → Tresor (meta_<kanal>_token)
    phone_number_id: str = ""        # WA-ID (kein Secret) → Setting
    ig_user_id: str = ""             # IG-User-ID (kein Secret) → Setting
    app_secret: str = ""             # Webhook-Signatur → Tresor (meta_app_secret)
    verify_token: str = ""           # Webhook-Verify → Tresor (meta_webhook_verify_token)


class _MetaTestIn(BaseModel):
    """Test-Sende aus der Config-UI — bleibt HITL (legt einen nachricht_senden-
    Vorschlag an, sendet nie autonom)."""
    kanal: str = ""
    an: str = ""                     # Empfänger (Telefon/IGSID)
    text: str = "Test von Dizz Communication"
    template: str = ""               # optional: WA-Template (außerhalb 24-h-Fenster)


class _TgVerbindenIn(BaseModel):
    """Telegram-Verbinden-Flow: Bot-Token → Tresor (telegram_bot_token). KEIN Wert ins Audit."""
    token: str = ""                  # Bot-Token von @BotFather → Tresor


class _TgTestIn(BaseModel):
    """Telegram-Test-Sende (HITL, sendet nie autonom). ``an`` = numerische chat_id."""
    an: str = ""                     # Empfänger: numerische chat_id
    text: str = "Test von Dizz Communication"


class _AntwortIn(BaseModel):
    """Unified Reply (docs/35 §2): aus dem Kontakt-Thread antworten — über einen
    explizit gewählten Kanal ODER (leer) automatisch den Kanal der zuletzt
    eingegangenen Nachricht. Senden bleibt HITL (verifiziert, fail-closed)."""
    text: str = ""
    kanal_typ: str = ""              # leer ⇒ „letzter eingegangener Kanal"
    an: str = ""                     # leer ⇒ aus den Kontakt-Aliassen abgeleitet
    betreff: str = ""                # nur E-Mail
    konto_id: str = ""               # E-Mail: absendendes Konto (leer ⇒ erstes sendefähige)


class _KalenderIn(BaseModel):
    """V5 (docs/26): aus einer Konversation einen Termin in den Plans-Kalender
    eintragen. Beginn (ISO-Datum/Zeit) ist Pflicht — Communication extrahiert v1
    kein Datum automatisch, der Nutzer gibt es beim Klick an."""
    beginn: str = ""
    ende: str = ""
    ort: str = ""


class _TerminIn(BaseModel):
    """Ein per Triage erkannter Termin-Vorschlag (für die Sammel-Anlage)."""
    titel: str = ""
    beginn: str = ""                 # ISO-8601 (Pflicht)
    ende: str = ""
    ganztags: bool = False
    ort: str = ""
    beschreibung: str = ""


class _TermineAnlegenIn(BaseModel):
    """Sammel-Anlage nach Nutzer-Bestätigung (HITL): die bestätigten Termin-
    Vorschläge werden über V5 in den Admin-Kalender eingetragen."""
    termine: list[_TerminIn] = []


class _KalenderEmpfangIn(BaseModel):
    """Querverbindungs-EMPFANG Kalender (V5-Rücksync, docs/26 §4b): eine andere App
    (z. B. Plans per „→ Kommunikation"-Knopf) legt einen Termin als read-only
    Erinnerung in Communication ab. Gleicher Kalender-Umschlag wie der Plans-
    Empfänger — Communication ist hier die ZIEL-Seite des bestehenden Vertrags."""
    titel: str = ""
    beginn: str = ""            # ISO-8601 (Pflicht)
    ende: str = ""
    ganztags: bool = False
    ort: str = ""
    beschreibung: str = ""
    app: str = ""               # absendende App-id → ``quelle`` (Idempotenz-Namensraum)
    quelle: str = ""            # Referenz/URL beim Absender → in die Beschreibung
    ref: str | None = None      # Idempotenz-Schlüssel → ``extern_id``


def _standard_quelle(konto: dict[str, Any], geheimnis: str) -> KanalQuelle:
    return ImapQuelle(host=konto["host"], benutzer=konto["benutzer"],
                      geheimnis=geheimnis, auth=konto["auth"],
                      port=int(konto["port"]))


def build_app(data_dir: Path | None = None,
              quelle_factory: QuellenFactory | None = None,
              schreib_quelle_factory: QuellenFactory | None = None,
              smtp_factory=None, http_post=None, archiv_post=None,
              start_timer: bool = True):
    root = data_dir or Path(os.environ.get("DIZZ_KOMMUNIKATION_DATA_DIR",
                                           r"C:\Dizzik\data"))
    db = Database(default_db_path(APP_ID, data_root=root),
                  extra_schema=_SCHEMA + ereignis_spine.SCHEMA_EREIGNISSE_SQL)
    _migriere(db)                        # Bestands-DBs auf den Spalten-Stand bringen

    def _gmail_access(refresh_token: str) -> str:
        """Frisches Access-Token (Gmail-Konten: im Tresor liegt das
        langlebige Refresh-Token, Access-Tokens leben nur ~1 h)."""
        creds = gmail.client_aus_env(root)
        if creds is None:
            raise KanalFehler("Google-Client nicht konfiguriert "
                              "(DIZZI_GOOGLE_CLIENT_ID/SECRET in der .env)")
        return gmail.access_token(creds[0], creds[1], refresh_token,
                                  http_post=http_post)

    def _quelle_default(konto: dict[str, Any], geheimnis: str) -> KanalQuelle:
        if konto["art"] == "gmail":
            return ImapQuelle("imap.gmail.com", konto["benutzer"],
                              _gmail_access(geheimnis), auth="xoauth2")
        if konto["art"] == "jmap":
            # Vorbereiteter Slot (Gesetz 5): scheitert ehrlich, bis der JMAP-
            # Adapter implementiert ist. Konto-Anlage für 'jmap' folgt später —
            # heute kann die API nur 'imap'/'gmail' anlegen.
            return JmapQuelle(konto["host"], konto["benutzer"], geheimnis,
                              port=int(konto["port"]))
        return _standard_quelle(konto, geheimnis)

    quelle_bauen = quelle_factory or _quelle_default
    # Schreib-Pfad des E-Mail-Piloten (RG-6): eigene Fabrik, damit Tests einen
    # schreibfähigen Fake injizieren können, ohne den (read-only) ``quelle_factory``-
    # Fake der Abruf-Tests anzufassen. Default = dieselbe ``ImapQuelle`` wie der Abruf
    # (sie trägt entwurf_ablegen/markiere/verschiebe); jmap/simulierte Konten scheitern
    # dort ehrlich (Gesetz 5), Senden bleibt ohnehin der eigene verifiziert-Pfad.
    schreib_quelle_bauen = schreib_quelle_factory or _quelle_default

    def _konto(konto_id: str, user_id: str) -> dict[str, Any] | None:
        row = db.get_conn().execute(
            "SELECT * FROM konten WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (konto_id, user_id)).fetchone()
        return dict(row) if row else None

    def _hat_sendekonto(user_id: str) -> bool:
        """True, wenn mindestens ein sendefähiges (SMTP-) E-Mail-Konto existiert —
        speist ``EmailConnector.verbunden`` (Kanal-Status + Unified-Reply-Gate)."""
        row = db.get_conn().execute(
            "SELECT 1 FROM konten WHERE user_id=? AND deleted_at IS NULL "
            "AND smtp_host != '' LIMIT 1", (user_id,)).fetchone()
        return row is not None

    def _zustand(konto_id: str, ordner: str) -> OrdnerZustand:
        row = db.get_conn().execute(
            "SELECT uidvalidity, uidnext FROM ordner_zustand "
            "WHERE konto_id=? AND ordner=?", (konto_id, ordner)).fetchone()
        return (OrdnerZustand(row["uidvalidity"], row["uidnext"])
                if row else OrdnerZustand())

    def _zustand_speichern(user_id: str, konto_id: str, ordner: str,
                           z: OrdnerZustand) -> None:
        ts = now_iso()
        db.get_conn().execute(
            """INSERT INTO ordner_zustand
               (id, user_id, konto_id, ordner, uidvalidity, uidnext, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT (konto_id, ordner) DO UPDATE SET
               uidvalidity=excluded.uidvalidity, uidnext=excluded.uidnext,
               updated_at=excluded.updated_at""",
            (new_id(), user_id, konto_id, ordner, z.uidvalidity, z.uidnext, ts, ts))
        db.get_conn().commit()

    def _kontakt_klammer(conn, user_id: str, von_adresse: str, ts: str,
                         kanal_typ: str = KANAL_EMAIL) -> None:
        """Kontakte-Klammer (Dossier §5, kanal-übergreifend): aus dem Absender eine
        Person ableiten. Dedupe über (Kanal, Adresse) — dieselbe Identität bekommt
        EINEN Kontakt. Bei E-Mail wird die Adresse aus „Name <a@b>" geparst; bei
        Messengern ist der Absender direkt der Handle/Identifier. Schlägt nie fehl
        (kaputte Absender stören den Sync/die Simulation nicht)."""
        if (kanal_typ or KANAL_EMAIL) == KANAL_EMAIL:
            from email.utils import parseaddr
            anzeige, adresse = parseaddr(von_adresse or "")
        else:
            anzeige, adresse = von_adresse or "", von_adresse or ""
        adresse = (adresse or "").strip().lower()
        if not adresse:
            return
        vorhanden = conn.execute(
            "SELECT kontakt_id FROM kontakt_adressen "
            "WHERE user_id=? AND kanal_typ=? AND adresse=? AND deleted_at IS NULL",
            (user_id, kanal_typ, adresse)).fetchone()
        if vorhanden:
            return
        kontakt_id = new_id()
        conn.execute(
            """INSERT INTO kontakte (id, user_id, name, created_at, updated_at)
               VALUES (?,?,?,?,?)""",
            (kontakt_id, user_id, (anzeige or adresse)[:120], ts, ts))
        conn.execute(
            """INSERT OR IGNORE INTO kontakt_adressen
               (id, user_id, kontakt_id, kanal_typ, adresse, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (new_id(), user_id, kontakt_id, kanal_typ, adresse, ts, ts))

    def _einsortieren(user_id: str, konto_id: str,
                      nachrichten: list[dict[str, Any]],
                      ordner: str = "INBOX") -> int:
        """Kanal-agnostische Ablage: Konversation (Thread-Schlüssel) finden/
        anlegen, Nachricht dedupe-sicher einfügen, Absender als Kontakt
        verklammern. Liefert Anzahl neuer Nachrichten."""
        conn = db.get_conn()
        neu = 0
        ts = now_iso()
        for n in nachrichten:
            schluessel = n.get("thread_schluessel") or n.get("extern_id") or new_id()
            conn.execute(
                """INSERT INTO konversationen
                   (id, user_id, konto_id, kanal_typ, extern_id, titel,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT (user_id, konto_id, extern_id) DO NOTHING""",
                (new_id(), user_id, konto_id, n["kanal_typ"], schluessel,
                 n.get("betreff", "")[:200], ts, ts))
            konv_id = conn.execute(
                "SELECT id FROM konversationen WHERE user_id=? AND konto_id=? AND extern_id=?",
                (user_id, konto_id, schluessel)).fetchone()["id"]
            msg_id = new_id()
            cur = conn.execute(
                """INSERT OR IGNORE INTO nachrichten
                   (id, user_id, konversation_id, kanal_typ, extern_id, richtung,
                    von_adresse, an_adressen, betreff, text, ordner, gelesen,
                    gesendet_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,'ein',?,?,?,?,?,0,?,?,?)""",
                (msg_id, user_id, konv_id, n["kanal_typ"],
                 n.get("extern_id") or new_id(), n.get("von_adresse", ""),
                 n.get("an_adressen", ""), n.get("betreff", ""),
                 n.get("text", ""), ordner, n.get("gesendet_at"), ts, ts))
            if cur.rowcount:
                _kontakt_klammer(conn, user_id, n.get("von_adresse", ""), ts,
                                 n.get("kanal_typ", KANAL_EMAIL))
                # RG-2 (docs/83 §5): mail_eingegangen als Zeiger in den Spine — in
                # DERSELBEN Tx wie der Nachrichten-Insert (Outbox-Garantie, docs/83 §1);
                # das conn.commit() unten schließt Nachricht + Ereignis gemeinsam ab.
                ereignis_spine.ereignis_anlegen(
                    conn, user_id, "mail_eingegangen", register=_EREIGNIS_REGISTER,
                    ref=f"{APP_ID}:nachricht:{msg_id}",
                    payload={"konto_id": konto_id,
                             "kanal_typ": n.get("kanal_typ", KANAL_EMAIL),
                             "ordner": ordner},
                    quelle_sens=MANIFEST.sensitivity)
            neu += cur.rowcount
        conn.commit()
        return neu

    # --- HITL: Senden ist die EINZIGE Wirkung nach außen (K4, verifiziert) ---

    vault_ref: dict[str, Any] = {}       # wird nach create_app gefüllt

    def _erstes_sendekonto(user_id: str) -> dict[str, Any] | None:
        row = db.get_conn().execute(
            "SELECT * FROM konten WHERE user_id=? AND deleted_at IS NULL "
            "AND smtp_host != '' ORDER BY created_at LIMIT 1", (user_id,)).fetchone()
        return dict(row) if row else None

    def _email_versand(out: AusgehendeNachricht,
                       user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
        """Der reale E-Mail-Versand (SMTP/Tresor) — gemeinsamer Kern von
        ``mail_senden`` (klassisch) und dem E-Mail-Connector (Unified Reply)."""
        konto = (_konto(out.konto_id, user_id) if out.konto_id
                 else _erstes_sendekonto(user_id))
        if konto is None:
            raise ValueError("Konto unbekannt")
        if not konto["smtp_host"]:
            raise ValueError("Konto hat keinen SMTP-Host (Versand nicht konfiguriert)")
        geheimnis = vault_ref["vault"].get(konto["tresor_ref"])
        if geheimnis is None:
            raise ValueError("Geheimnis fehlt im Tresor")
        if konto["art"] == "gmail":                      # Refresh → frisches Token
            geheimnis = _gmail_access(geheimnis)
        sende_mail(konto["smtp_host"], int(konto["smtp_port"]),
                   konto["benutzer"], geheimnis, konto["auth"],
                   von=konto["benutzer"], an=out.an, betreff=out.betreff,
                   text=out.text, smtp_factory=smtp_factory)
        try:  # RG-2 (docs/83 §5): mail_gesendet als Zeiger in den Spine. Best-effort —
              # der Versand IST erfolgt; ein Spine-Fehler darf ihn nie als Fehler melden.
            with db.transaktion() as _conn:
                ereignis_spine.ereignis_anlegen(
                    _conn, user_id, "mail_gesendet", register=_EREIGNIS_REGISTER,
                    ref=f"{APP_ID}:konto:{konto['id']}",
                    payload={"konto_id": konto["id"], "kanal_typ": out.kanal_typ},
                    quelle_sens=MANIFEST.sensitivity)
        except Exception:
            pass
        return {"gesendet": True, "an": out.an}

    # --- Meta-Konnektor (WhatsApp + Instagram, docs/38) ----------------------
    # Die echten Graph-API-Connectoren (meta.py), verdrahtet mit Tresor (Token)
    # + Einstellungen (nicht-geheime IDs/Version). DORMANT bis Token im Tresor.
    # ``http_post=None`` ⇒ meta.py nutzt httpx für echte Calls (in Tests fließt
    # nie ein echter Call: Senden ist HITL + standalone fail-closed).
    def _meta_config(key: str, default: Any = None) -> Any:
        return db.setting_get(DEFAULT_USER_ID, key, default)

    def _vault_get(n: str) -> Any:
        return vault_ref["vault"].get(n) if vault_ref.get("vault") else None

    _meta_connectoren = meta.baue_connectoren(vault_get=_vault_get, config_get=_meta_config)
    # Telegram (telegram.py, Bot-API) — dormant bis Token, lokal via Long-Polling.
    _telegram_conn = telegram.baue_connector(vault_get=_vault_get, config_get=_meta_config)
    # Alle echten Messenger-Adapter als kanal_typ → Adapter (Meta-Graph + Telegram-Bot-API).
    _adapter_connectoren: dict[str, Any] = {**_meta_connectoren, "telegram": _telegram_conn}
    _konn_reg = ConnectorRegistry()         # W4: /api/konnektoren-Sichtbarkeit
    for _c in _adapter_connectoren.values():
        _konn_reg.register(_c)
    # Connector-Katalog (Gesetz 5): weitere Dienste als dormante Slots sichtbar
    # machen (Facebook Messenger/Threads/X/LinkedIn/Slack/Discord/Signal/SMS/Matrix/
    # Snapchat) — ehrliche Aktivierungs-Pfade, kein echter Call ohne Tokens.
    for _c in connectors_katalog.dormante_konnektoren():
        _konn_reg.register(_c)

    def _kanal_connector(user_id: str, kanal_typ: str):
        """Connector zu einem Kanal, mit dem realen E-Mail-Versand UND den echten
        Adaptern (WhatsApp/Instagram via Meta, Telegram via Bot-API) verdrahtet."""
        return channels.connector_fuer(
            kanal_typ, email_konto_vorhanden=lambda: _hat_sendekonto(user_id),
            email_sende=lambda out: _email_versand(out, user_id),
            adapter=_adapter_connectoren)

    def _senden_handler(params: dict[str, Any]) -> dict[str, Any]:
        """Klassischer E-Mail-Versand (mail_senden) — Verhalten unverändert."""
        out = AusgehendeNachricht(
            an=params["an"], betreff=params.get("betreff", ""),
            text=params.get("text", ""), kanal_typ=KANAL_EMAIL,
            konto_id=params["konto_id"])
        return _email_versand(out, params.get("user_id", DEFAULT_USER_ID))

    def _kanal_senden_handler(params: dict[str, Any]) -> dict[str, Any]:
        """Unified Reply (nachricht_senden): über die Connector-Schicht senden —
        E-Mail real, dormante Kanäle fail-closed (``KanalNichtVerbunden`` ⇒ die
        Aktion scheitert ehrlich, selbst NACH Freigabe; Gesetz 5)."""
        user_id = params.get("user_id", DEFAULT_USER_ID)
        kt = (params.get("kanal_typ") or KANAL_EMAIL).strip().lower()
        conn_obj = _kanal_connector(user_id, kt)
        if conn_obj is None:
            raise ValueError(f"Unbekannter Kanal: {kt}")
        out = AusgehendeNachricht(
            an=params.get("an", ""), text=params.get("text", ""),
            betreff=params.get("betreff", ""), kanal_typ=kt,
            konto_id=params.get("konto_id", ""),
            kontakt_id=params.get("kontakt_id", ""),
            konversation_id=params.get("konversation_id", ""),
            template=params.get("template", ""))
        erg = conn_obj.senden(out)
        res = {"gesendet": True, "kanal_typ": kt, "an": out.an}
        if isinstance(erg, dict):
            res.update(erg)
        return res

    # --- E-Mail-Pilot: die drei kleinen lokal-Aktionen (RG-6, docs/83 §5.7) --
    # Alle level 'lokal' ⇒ Klasse 'entwurf' (harmlos). Sie wirken auf dem MAIL-
    # SERVER (IMAP), adressiert über unseren stabilen ``nachricht_ref`` (Zeiger
    # 'kommunikation:nachricht:<id>', docs/83 §1) → DB-Zeile → extern_id/Ordner/
    # Konto; die volatile IMAP-UID sucht die Schreib-Quelle zur Laufzeit.

    def _ref_zu_id(nachricht_ref: str) -> str:
        """Zeiger ``kommunikation:nachricht:<id>`` → nackte id (tolerant: eine
        bereits nackte id bleibt unverändert). Der Agent zündet mit dem Zeiger
        aus ``mail_eingegangen`` (docs/83 §5.2)."""
        return (nachricht_ref or "").rsplit(":", 1)[-1]

    def _nachricht_row(user_id: str, nachricht_id: str) -> dict[str, Any] | None:
        """Die EINE Nachricht + ihr Konto (join über die Konversation): id,
        extern_id (RFC-Message-ID = IMAP-Brücke), Ordner, Absender, Betreff."""
        if not nachricht_id:
            return None
        row = db.get_conn().execute(
            "SELECT n.id, n.extern_id, n.ordner, n.von_adresse, n.betreff, "
            "k.konto_id FROM nachrichten n JOIN konversationen k "
            "ON k.id = n.konversation_id WHERE n.id=? AND n.user_id=? "
            "AND n.deleted_at IS NULL", (nachricht_id, user_id)).fetchone()
        return dict(row) if row else None

    def _schreib_quelle(konto: dict[str, Any]):
        """Schreibfähige Quelle (Geheimnis aus dem Tresor). ``_quelle_default``
        baut für imap/gmail eine ``ImapQuelle`` (trägt die Schreib-Ops); jmap
        scheitert ehrlich (Gesetz-5-Slot)."""
        geheimnis = vault_ref["vault"].get(konto["tresor_ref"])
        if geheimnis is None:
            raise ValueError("Geheimnis fehlt im Tresor")
        return schreib_quelle_bauen(konto, geheimnis)

    def _pilot_ziel(params: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """Gemeinsamer Vorspann der drei Aktionen: Nutzer + Nachricht + Konto
        auflösen oder ehrlich scheitern (fail-closed)."""
        user_id = params.get("user_id", DEFAULT_USER_ID)
        row = _nachricht_row(user_id, _ref_zu_id(params.get("nachricht_ref", "")))
        if row is None:
            raise ValueError("Nachricht unbekannt (nachricht_ref)")
        konto = _konto(row["konto_id"], user_id)
        if konto is None:
            raise ValueError("Konto unbekannt")
        return user_id, row, konto

    def _entwurf_ablegen_handler(params: dict[str, Any]) -> dict[str, Any]:
        """``email_entwurf_ablegen``: Antwort-ENTWURF in den Drafts-Ordner
        (IMAP APPEND) — kein Versand. Antwortet standardmäßig an den Absender,
        threaded über die Ursprungs-Message-ID."""
        user_id, row, konto = _pilot_ziel(params)
        an = params.get("an") or row["von_adresse"]
        betreff = params.get("betreff") or _re_betreff(row["betreff"])
        roh = baue_entwurf_bytes(konto["benutzer"], an, betreff,
                                 params.get("text", ""), in_reply_to=row["extern_id"])
        ordner = params.get("ordner", STANDARD_ENTWURF_ORDNER)
        res = _schreib_quelle(konto).entwurf_ablegen(roh, ordner)
        db.audit(user_id, "user", "email_entwurf_abgelegt",
                 {"nachricht": row["id"], "ordner": ordner})
        return res

    def _markieren_handler(params: dict[str, Any]) -> dict[str, Any]:
        """``email_markieren``: ein IMAP-Flag (gelesen/wichtig) setzen/entfernen;
        bei 'gelesen' zieht die lokale Anzeige sofort mit (Server bleibt Wahrheit)."""
        user_id, row, konto = _pilot_ziel(params)
        flag_name = params.get("flag", "gelesen")
        flag = MARKIER_FLAGS.get(flag_name)
        if flag is None:
            raise ValueError(f"Unbekanntes Flag: {flag_name!r} "
                             f"(erlaubt: {list(MARKIER_FLAGS)})")
        setzen = bool(params.get("setzen", True))
        res = _schreib_quelle(konto).markiere(row["ordner"], row["extern_id"],
                                              flag, setzen)
        if flag_name == "gelesen":
            conn = db.get_conn()
            conn.execute("UPDATE nachrichten SET gelesen=?, updated_at=? "
                         "WHERE id=? AND user_id=?",
                         (1 if setzen else 0, now_iso(), row["id"], user_id))
            conn.commit()
        db.audit(user_id, "user", "email_markiert",
                 {"nachricht": row["id"], "flag": flag_name, "setzen": setzen})
        return res

    def _verschieben_handler(params: dict[str, Any]) -> dict[str, Any]:
        """``email_verschieben``: die Nachricht in einen anderen Ordner
        (IMAP COPY+Delete+Expunge); die lokale Zeile zieht mit."""
        user_id, row, konto = _pilot_ziel(params)
        ziel = (params.get("ziel_ordner") or "").strip()
        if not ziel:
            raise ValueError("ziel_ordner fehlt")
        res = _schreib_quelle(konto).verschiebe(row["ordner"], row["extern_id"], ziel)
        conn = db.get_conn()
        conn.execute("UPDATE nachrichten SET ordner=?, updated_at=? "
                     "WHERE id=? AND user_id=?", (ziel, now_iso(), row["id"], user_id))
        conn.commit()
        db.audit(user_id, "user", "email_verschoben",
                 {"nachricht": row["id"], "ziel": ziel})
        return res

    actions = ActionRegistry()
    actions.register(
        "mail_senden", _senden_handler, level="verifiziert",
        beschreibung="E-Mail über ein Konto versenden (nur nach Freigabe).")
    actions.register(
        "nachricht_senden", _kanal_senden_handler, level="verifiziert",
        beschreibung="Nachricht über einen Kanal senden — Unified Reply, "
                     "E-Mail real, andere Kanäle dormant (nur nach Freigabe).")
    # E-Mail-Pilot (RG-6): drei lokal-Aktionen (⇒ Klasse 'entwurf'). Senden bleibt
    # oben verifiziert (⇒ 'aussenwirkung', im Piloten IMMER pre_approval, docs/83 §5).
    actions.register(
        "email_entwurf_ablegen", _entwurf_ablegen_handler, level="lokal",
        beschreibung="Antwort-Entwurf in den Drafts-Ordner legen "
                     "(IMAP APPEND; nur nach Freigabe).")
    actions.register(
        "email_markieren", _markieren_handler, level="lokal",
        beschreibung="Nachricht markieren — gelesen/wichtig (IMAP-Flag; nur nach Freigabe).")
    actions.register(
        "email_verschieben", _verschieben_handler, level="lokal",
        beschreibung="Nachricht in einen anderen Ordner verschieben (nur nach Freigabe).")

    router = APIRouter()

    @router.get("/api/konten")
    def konten(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT id, name, art, host, benutzer, auth, smtp_host FROM konten "
            "WHERE user_id=? AND deleted_at IS NULL ORDER BY name",
            (user.user_id,)).fetchall()
        return [dict(r) for r in rows]

    @router.post("/api/konten")
    def konto_anlegen(body: _KontoIn,
                      user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Konto + Geheimnis: das Geheimnis geht in den TRESOR, die DB hält
        nur die Referenz — ein DB-/Backup-Leak gibt keine Zugänge her."""
        kid = new_id()
        ref = f"konto_{kid}"
        vault_ref["vault"].put(ref, body.geheimnis)
        ts = now_iso()
        db.get_conn().execute(
            """INSERT INTO konten (id, user_id, name, art, host, port, benutzer,
                                   auth, tresor_ref, smtp_host, smtp_port,
                                   created_at, updated_at)
               VALUES (?,?,?,'imap',?,?,?,?,?,?,?,?,?)""",
            (kid, user.user_id, body.name, body.host, body.port, body.benutzer,
             body.auth, ref, body.smtp_host, body.smtp_port, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "konto_angelegt",
                 {"name": body.name, "auth": body.auth})
        return {"id": kid, "name": body.name}

    def sync_lauf(user_id: str, konto_id: str, ordner: str) -> dict[str, Any]:
        """Ein Sync-Lauf für einen Ordner: Quelle bauen (Geheimnis aus dem
        Tresor), inkrementell holen, kanal-agnostisch einsortieren.
        Gemeinsamer Kern von HTTP-Endpoint und getakteter Automatik."""
        konto = _konto(konto_id, user_id)
        if konto is None:
            return {"error": "Konto unbekannt", "status": 404}
        if konto["art"] not in ("imap", "gmail", "jmap"):
            # Simulierte Kanal-„Konten" (telegram/whatsapp/…) haben keinen IMAP-
            # Abruf — ihre Nachrichten kommen über den Demo-Ingest, nicht per Sync.
            return {"geholt": 0, "neu": 0,
                    "hinweis": f"{konto['art']}: kein IMAP-Abruf (simulierter Kanal)"}
        geheimnis = vault_ref["vault"].get(konto["tresor_ref"])
        if geheimnis is None:
            return {"error": "Geheimnis fehlt im Tresor", "status": 409}
        try:
            quelle = quelle_bauen(konto, geheimnis)
            nachrichten, zustand = quelle.hole_neue(
                ordner, _zustand(konto["id"], ordner))
        except Exception as e:
            db.audit(user_id, "system", "sync_fehlgeschlagen",
                     {"konto": konto["name"], "fehler": f"{type(e).__name__}: {e}"})
            return {"error": f"{type(e).__name__}: {e}", "status": 502}
        neu = _einsortieren(user_id, konto["id"], nachrichten, ordner)
        _zustand_speichern(user_id, konto["id"], ordner, zustand)
        db.audit(user_id, "system", "sync_ok",
                 {"konto": konto["name"], "ordner": ordner,
                  "geholt": len(nachrichten), "neu": neu})
        return {"geholt": len(nachrichten), "neu": neu,
                "uidnext": zustand.uidnext}

    @router.delete("/api/konten/{konto_id}")
    def konto_entfernen(konto_id: str,
                        user: UserContext = Depends(current_user)):
        """Konto trennen: Soft-Delete der Zeile UND Wipe des Geheimnisses aus
        dem Tresor — ein orphaned Konto (Zeile ohne Geheimnis) wäre ein
        Footgun (Sync schlüge mit 'Geheimnis fehlt' fehl). Nachrichten/
        Konversationen bleiben lesbar (Soft-Delete nur des Kontos)."""
        konto = _konto(konto_id, user.user_id)
        if konto is None:
            return JSONResponse({"error": "Konto unbekannt"}, status_code=404)
        ts = now_iso()
        db.get_conn().execute(
            "UPDATE konten SET deleted_at=?, updated_at=? WHERE id=? AND user_id=?",
            (ts, ts, konto_id, user.user_id))
        db.get_conn().commit()
        if konto["tresor_ref"]:
            vault_ref["vault"].delete(konto["tresor_ref"])
        db.audit(user.user_id, "user", "konto_entfernt",
                 {"name": konto["name"], "tresor_geleert": bool(konto["tresor_ref"])})
        return {"ok": True, "id": konto_id}

    @router.post("/api/sync")
    def sync(body: _SyncIn,
             user: UserContext = Depends(current_user)):
        out = sync_lauf(user.user_id, body.konto_id, body.ordner)
        if "error" in out:
            return JSONResponse({"error": out["error"]},
                                status_code=out.get("status", 502))
        return out

    # --- Gmail-Anbindung (OAuth Loopback; Nutzer-Consent im Browser) ----------

    _gmail_flows: dict[str, dict[str, str]] = {}
    _gmail_redirect = f"http://127.0.0.1:{MANIFEST.port}/api/konten/gmail/callback"

    @router.get("/api/konten/gmail/start")
    def gmail_start(user: UserContext = Depends(current_user)):
        """Startet den Google-Consent (Mail-Scope, offline) — der Browser
        landet danach im Callback, das Refresh-Token im Tresor."""
        creds = gmail.client_aus_env(root)
        if creds is None:
            return JSONResponse({"error": (
                "Google-Client nicht konfiguriert — DIZZI_GOOGLE_CLIENT_ID/"
                "SECRET in C:\\Dizzik\\data\\.env (docs/17 §3).")},
                status_code=409)
        flow = gmail.flow_starten(creds[0], _gmail_redirect)
        _gmail_flows[flow["state"]] = flow
        return RedirectResponse(flow["url"], status_code=302)

    @router.get("/api/konten/gmail/callback")
    def gmail_callback(code: str = "", state: str = "",
                       user: UserContext = Depends(current_user)):
        flow = _gmail_flows.pop(state, None)
        if flow is None or not code:
            return JSONResponse({"error": "OAuth-Flow unbekannt/abgelaufen"},
                                status_code=400)
        creds = gmail.client_aus_env(root)
        try:
            t = gmail.code_einloesen(creds[0], creds[1], code, _gmail_redirect,
                                     flow["verifier"], http_post=http_post)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=502)
        kid = new_id()
        ref = f"konto_{kid}"
        vault_ref["vault"].put(ref, t["refresh_token"])
        ts = now_iso()
        db.get_conn().execute(
            """INSERT INTO konten (id, user_id, name, art, host, port, benutzer,
                                   auth, tresor_ref, smtp_host, smtp_port,
                                   created_at, updated_at)
               VALUES (?,?,?,'gmail','imap.gmail.com',993,?,'xoauth2',?,
                       'smtp.gmail.com',587,?,?)""",
            (kid, user.user_id, t["email"] or "Gmail", t["email"], ref, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "gmail_verbunden", {"email": t["email"]})
        return RedirectResponse("/?gmail=ok", status_code=302)

    @router.get("/api/posteingang")
    def posteingang(limit: int = 50, konto_id: str = "", ordner: str = "",
                    nur_ungelesen: bool = False,
                    user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Flache neueste-zuerst-Liste (Filter: Konto/Ordner/ungelesen)."""
        q = ("SELECT n.id, n.betreff, n.von_adresse, n.text, n.gesendet_at, "
             "n.kanal_typ, n.ordner, n.gelesen, k.id AS konversation_id, "
             "k.titel AS konversation, k.konto_id FROM nachrichten n "
             "JOIN konversationen k ON k.id = n.konversation_id "
             "WHERE n.user_id=? AND n.deleted_at IS NULL")
        params: list[Any] = [user.user_id]
        if konto_id:
            q += " AND k.konto_id=?"
            params.append(konto_id)
        if ordner:
            q += " AND n.ordner=?"
            params.append(ordner)
        if nur_ungelesen:
            q += " AND n.gelesen=0"
        q += " ORDER BY n.rowid DESC LIMIT ?"
        params.append(min(limit, 500))
        return [dict(r) for r in db.get_conn().execute(q, params).fetchall()]

    @router.get("/api/konversationen")
    def konversationen(limit: int = 50, konto_id: str = "", ordner: str = "",
                       nur_ungelesen: bool = False, geschlummert: bool = False,
                       label: str = "",
                       user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Konversations-Liste mit Zählern (gesamt/ungelesen), letztem Absender
        und Zeitstempel. Filter: Konto, Ordner (Konversation hat ≥1 Nachricht
        darin), nur-ungelesen."""
        # ``letzte``/``letzter_von`` kommen aus der JÜNGSTEN Nachricht (per rowid)
        # — NICHT aus MAX(gesendet_at): das ist ein roher RFC-Datumsstring, dessen
        # lexikografisches Maximum nicht dem chronologisch jüngsten entspricht.
        q = ("SELECT k.id, k.titel, k.kanal_typ, k.konto_id, k.schlummern_bis, "
             "COUNT(n.id) AS nachrichten, "
             "COALESCE(SUM(CASE WHEN n.gelesen=0 THEN 1 ELSE 0 END), 0) AS ungelesen, "
             "(SELECT COALESCE(NULLIF(gesendet_at, ''), created_at) "
             " FROM nachrichten WHERE konversation_id=k.id AND deleted_at IS NULL "
             " ORDER BY rowid DESC LIMIT 1) AS letzte, "
             "(SELECT von_adresse FROM nachrichten WHERE konversation_id=k.id "
             " AND deleted_at IS NULL ORDER BY rowid DESC LIMIT 1) AS letzter_von "
             "FROM konversationen k "
             "LEFT JOIN nachrichten n ON n.konversation_id=k.id AND n.deleted_at IS NULL "
             "WHERE k.user_id=? AND k.deleted_at IS NULL")
        params: list[Any] = [user.user_id]
        if konto_id:
            q += " AND k.konto_id=?"
            params.append(konto_id)
        if ordner:
            q += (" AND EXISTS (SELECT 1 FROM nachrichten nx WHERE "
                  "nx.konversation_id=k.id AND nx.ordner=? AND nx.deleted_at IS NULL)")
            params.append(ordner)
        # Snooze (P2): geschlummerte Konversationen sind aus dem Posteingang
        # ausgeblendet, bis ihre Zeit erreicht ist; ``geschlummert=1`` zeigt genau sie.
        jetzt = now_iso()
        if geschlummert:
            q += " AND k.schlummern_bis != '' AND k.schlummern_bis > ?"
        else:
            q += " AND (k.schlummern_bis = '' OR k.schlummern_bis <= ?)"
        params.append(jetzt)
        if label:
            q += (" AND EXISTS (SELECT 1 FROM konversation_labels kl "
                  "JOIN labels l ON l.id=kl.label_id WHERE kl.konversation_id=k.id "
                  "AND kl.deleted_at IS NULL AND l.deleted_at IS NULL AND l.name=?)")
            params.append(label)
        q += " GROUP BY k.id"
        if nur_ungelesen:
            q += " HAVING ungelesen > 0"
        q += " ORDER BY MAX(n.rowid) DESC LIMIT ?"
        params.append(min(limit, 500))
        rows = db.get_conn().execute(q, params).fetchall()
        ids = [r["id"] for r in rows]
        labelmap: dict[str, list[dict[str, Any]]] = {}
        if ids:
            ph = ",".join("?" * len(ids))
            for lr in db.get_conn().execute(
                    "SELECT kl.konversation_id AS kid, l.id, l.name, l.farbe "
                    "FROM konversation_labels kl JOIN labels l ON l.id=kl.label_id "
                    "WHERE kl.user_id=? AND kl.deleted_at IS NULL AND l.deleted_at IS NULL "
                    f"AND kl.konversation_id IN ({ph}) ORDER BY l.name",
                    [user.user_id, *ids]).fetchall():
                labelmap.setdefault(lr["kid"], []).append(
                    {"id": lr["id"], "name": lr["name"], "farbe": lr["farbe"]})
        out = []
        for r in rows:
            d = dict(r)
            d["sektion"] = sektion_aus_absender(d.get("letzter_von") or "")
            d["labels"] = labelmap.get(d["id"], [])
            out.append(d)
        return out

    @router.get("/api/konversationen/{konv_id}")
    def konversation_detail(konv_id: str,
                            user: UserContext = Depends(current_user)):
        """Thread-Detail: Konversations-Kopf + Nachrichten CHRONOLOGISCH
        (älteste zuerst) — das References-Threading liegt bereits beim Sync."""
        conn = db.get_conn()
        kopf = conn.execute(
            "SELECT id, titel, kanal_typ, konto_id FROM konversationen "
            "WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (konv_id, user.user_id)).fetchone()
        if kopf is None:
            return JSONResponse({"error": "Konversation unbekannt"}, status_code=404)
        rows = conn.execute(
            "SELECT id, richtung, von_adresse, an_adressen, betreff, text, "
            "ordner, gelesen, gesendet_at, created_at FROM nachrichten "
            "WHERE konversation_id=? AND user_id=? AND deleted_at IS NULL "
            "ORDER BY rowid ASC", (konv_id, user.user_id)).fetchall()
        return {"konversation": dict(kopf),
                "nachrichten": [dict(r) for r in rows]}

    @router.get("/api/nachricht/{nid}")
    def nachricht_detail(nid: str, user: UserContext = Depends(current_user)):
        """EINE Nachricht (Metadaten + Text) — die Lese-Fläche des E-Mail-Piloten
        (RG-6, [A-3]): der Triage-/Antwort-Worker holt über seinen ``nachricht_ref``
        aus ``mail_eingegangen`` GENAU diese Mail (docs/83 §1.1: Inhalte holt der
        Lauf per read-Tool bei der besitzenden App, nicht der Event). Metadaten +
        Text, keine Anhänge/keine externen Ressourcen (Tracking-Pixel-Block bleibt)."""
        row = db.get_conn().execute(
            "SELECT n.id, n.betreff, n.von_adresse, n.an_adressen, n.text, n.ordner, "
            "n.gelesen, n.richtung, n.gesendet_at, n.extern_id, "
            "k.id AS konversation_id, k.konto_id, k.kanal_typ "
            "FROM nachrichten n JOIN konversationen k ON k.id = n.konversation_id "
            "WHERE n.id=? AND n.user_id=? AND n.deleted_at IS NULL",
            (nid, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Nachricht unbekannt"}, status_code=404)
        return dict(row)

    @router.post("/api/konversationen/{konv_id}/gelesen")
    def konversation_gelesen(konv_id: str, body: _GelesenIn,
                             user: UserContext = Depends(current_user)):
        """Ganze Konversation als gelesen/ungelesen markieren (lokal, harmlos)."""
        conn = db.get_conn()
        kopf = conn.execute(
            "SELECT id FROM konversationen WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (konv_id, user.user_id)).fetchone()
        if kopf is None:
            return JSONResponse({"error": "Konversation unbekannt"}, status_code=404)
        cur = conn.execute(
            "UPDATE nachrichten SET gelesen=?, updated_at=? "
            "WHERE konversation_id=? AND user_id=? AND deleted_at IS NULL",
            (1 if body.gelesen else 0, now_iso(), konv_id, user.user_id))
        conn.commit()
        return {"ok": True, "geaendert": cur.rowcount, "gelesen": body.gelesen}

    @router.post("/api/konversationen/{konv_id}/schlummern")
    def konversation_schlummern(konv_id: str, body: _SchlummernIn = _SchlummernIn(),
                                user: UserContext = Depends(current_user)):
        """Snooze (P2): Konversation bis ``bis`` (ISO) aus dem Posteingang
        ausblenden; leeres ``bis`` weckt sie wieder. Rein lokal, harmlos."""
        conn = db.get_conn()
        kopf = conn.execute(
            "SELECT id FROM konversationen WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (konv_id, user.user_id)).fetchone()
        if kopf is None:
            return JSONResponse({"error": "Konversation unbekannt"}, status_code=404)
        bis = (body.bis or "").strip()
        conn.execute(
            "UPDATE konversationen SET schlummern_bis=?, updated_at=? WHERE id=? AND user_id=?",
            (bis, now_iso(), konv_id, user.user_id))
        conn.commit()
        db.audit(user.user_id, "user", "konv_schlummern", {"konv": konv_id, "bis": bis})
        return {"ok": True, "schlummern_bis": bis}

    # --- Labels (P2) ---------------------------------------------------------
    _LABEL_FARBEN = ("cy", "mg", "ok", "warn")

    @router.get("/api/labels")
    def labels_liste(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT id, name, farbe FROM labels WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY name", (user.user_id,)).fetchall()
        return [dict(r) for r in rows]

    @router.get("/api/konversationen/{konv_id}/labels")
    def konv_labels(konv_id: str,
                    user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT l.id, l.name, l.farbe FROM konversation_labels kl "
            "JOIN labels l ON l.id=kl.label_id "
            "WHERE kl.user_id=? AND kl.konversation_id=? AND kl.deleted_at IS NULL "
            "AND l.deleted_at IS NULL ORDER BY l.name",
            (user.user_id, konv_id)).fetchall()
        return [dict(r) for r in rows]

    @router.post("/api/konversationen/{konv_id}/labels")
    def konv_label_setzen(konv_id: str, body: _LabelIn = _LabelIn(),
                          user: UserContext = Depends(current_user)):
        """Label an eine Konversation hängen (legt das Label bei Bedarf an).
        Idempotent je (Konversation, Label)."""
        name = (body.name or "").strip()[:40]
        if not name:
            return JSONResponse({"error": "name ist Pflicht"}, status_code=400)
        conn = db.get_conn()
        kopf = conn.execute(
            "SELECT id FROM konversationen WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (konv_id, user.user_id)).fetchone()
        if kopf is None:
            return JSONResponse({"error": "Konversation unbekannt"}, status_code=404)
        farbe = body.farbe if body.farbe in _LABEL_FARBEN else "cy"
        ts = now_iso()
        conn.execute(
            """INSERT INTO labels (id, user_id, name, farbe, created_at, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT (user_id, name) DO UPDATE SET
               farbe=excluded.farbe, updated_at=excluded.updated_at, deleted_at=NULL""",
            (new_id(), user.user_id, name, farbe, ts, ts))
        lid = conn.execute("SELECT id FROM labels WHERE user_id=? AND name=?",
                           (user.user_id, name)).fetchone()["id"]
        conn.execute(
            """INSERT INTO konversation_labels
               (id, user_id, konversation_id, label_id, created_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT (user_id, konversation_id, label_id) DO UPDATE SET deleted_at=NULL""",
            (new_id(), user.user_id, konv_id, lid, ts))
        conn.commit()
        return {"ok": True, "id": lid, "name": name, "farbe": farbe}

    @router.delete("/api/konversationen/{konv_id}/labels/{label_id}")
    def konv_label_entfernen(konv_id: str, label_id: str,
                             user: UserContext = Depends(current_user)):
        conn = db.get_conn()
        cur = conn.execute(
            "UPDATE konversation_labels SET deleted_at=? WHERE user_id=? "
            "AND konversation_id=? AND label_id=? AND deleted_at IS NULL",
            (now_iso(), user.user_id, konv_id, label_id))
        conn.commit()
        return {"ok": True, "entfernt": cur.rowcount}

    def _archiviere_konversation(konv_id: str, user_id: str,
                                 explizit: bool = False) -> dict | None:
        """Reicht eine ganze Konversation (Thread) als Notiz an Dizz Memory weiter
        (über den Core-Relay, V4 docs/26): die Archiv-Regel je (kommunikation, mail)
        entscheidet auto / auf Zuruf; ``explizit`` (Knopf) schlägt jede Regel.
        Best-effort. None ⇒ Konversation unbekannt (der Endpoint macht daraus 404)."""
        conn = db.get_conn()
        kopf = conn.execute(
            "SELECT id, titel, kanal_typ FROM konversationen "
            "WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (konv_id, user_id)).fetchone()
        if kopf is None:
            return None
        rows = conn.execute(
            "SELECT von_adresse, betreff, text FROM nachrichten "
            "WHERE konversation_id=? AND user_id=? AND deleted_at IS NULL "
            "ORDER BY rowid ASC", (konv_id, user_id)).fetchall()
        from appkit.querverbindung import archiviere
        titel = (kopf["titel"] or "").strip()
        if not titel and rows:
            titel = (rows[0]["betreff"] or "").strip()
        if not titel:
            titel = "Konversation"
        teile: list[str] = []
        for r in rows:
            kopfzeile = "**Von:** " + str(r["von_adresse"] or "?")
            if r["betreff"]:
                kopfzeile += " · " + str(r["betreff"])
            teile.append(kopfzeile)
            teile.append(str(r["text"] or "").strip())
            teile.append("")
        inhalt = "\n".join(teile).strip() or "(leere Konversation)"
        return archiviere("kommunikation", titel, inhalt, strom="mail",
                          ref="komm:konv:" + konv_id, tags=[kopf["kanal_typ"]],
                          explizit=explizit, http_post=archiv_post)

    def _verkn_merken(user_id: str, konv_id: str, ziel: str, ref: str,
                      extern_id: str) -> None:
        """Hält lokal fest, dass diese Konversation mit einer Ziel-App verknüpft
        wurde (V4 Memory / V5 Admin-Kalender) — damit die UI die Querverbindung SICHTBAR
        macht (Leitlinie 17.06: Verknüpfungs-Chip mit Drill-down), auch nach dem
        Neuöffnen des Threads. Idempotent je (Konversation, Ziel)."""
        ts = now_iso()
        db.get_conn().execute(
            """INSERT INTO querverbindungen
               (id, user_id, konversation_id, ziel, ref, extern_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT (user_id, konversation_id, ziel) DO UPDATE SET
               ref=excluded.ref, extern_id=excluded.extern_id,
               updated_at=excluded.updated_at, deleted_at=NULL""",
            (new_id(), user_id, konv_id, ziel, ref, str(extern_id or ""), ts, ts))
        db.get_conn().commit()

    @router.post("/api/konversationen/{konv_id}/archivieren")
    def konversation_archivieren(konv_id: str,
                                 user: UserContext = Depends(current_user)):
        """„In Memory archivieren" (Nutzer-Zuruf): legt die ganze Konversation als
        Notiz in Dizz Memory ab — schlägt die Archiv-Regel (V4, docs/26)."""
        erg = _archiviere_konversation(konv_id, user.user_id, explizit=True)
        if erg is None:
            return JSONResponse({"error": "Konversation unbekannt"}, status_code=404)
        if erg.get("status") in ("archiviert", "vorhanden"):
            _verkn_merken(user.user_id, konv_id, "memory",
                          "komm:konv:" + konv_id, erg.get("id", ""))
        return erg

    def _sende_konv_termin(konv_id: str, user_id: str, beginn: str,
                           ende: str = "", ort: str = "") -> dict | None:
        """Trägt aus einer Konversation (z. B. Mail-Einladung) einen Termin in den
        Admin-Kalender ein (Core-Relay, ZWEITER Vertragstyp V5 docs/26; Admin hält
        seit dem Merge docs/28/29 den Kalender). Titel =
        Konversations-Betreff; Beschreibung = Absender + Auszug. Idempotent per
        ``ref=komm:termin:<konv_id>``. Best-effort. None ⇒ Konversation unbekannt."""
        conn = db.get_conn()
        kopf = conn.execute(
            "SELECT id, titel FROM konversationen "
            "WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (konv_id, user_id)).fetchone()
        if kopf is None:
            return None
        rows = conn.execute(
            "SELECT von_adresse, betreff, text FROM nachrichten "
            "WHERE konversation_id=? AND user_id=? AND deleted_at IS NULL "
            "ORDER BY rowid ASC LIMIT 1", (konv_id, user_id)).fetchall()
        from appkit.querverbindung import sende_termin
        titel = (kopf["titel"] or "").strip()
        if not titel and rows:
            titel = (rows[0]["betreff"] or "").strip()
        titel = titel or "Termin aus Nachricht"
        beschreibung = ""
        if rows:
            von = str(rows[0]["von_adresse"] or "")
            auszug = str(rows[0]["text"] or "").strip().replace("\n", " ")[:300]
            beschreibung = (f"Von: {von}\n\n{auszug}").strip()
        return sende_termin("kommunikation", titel, beginn, ende=ende, ort=ort,
                            beschreibung=beschreibung, quelle="komm:konv:" + konv_id,
                            ref="komm:termin:" + konv_id, ziel="admin",
                            http_post=archiv_post)

    @router.post("/api/konversationen/{konv_id}/kalender")
    def konversation_kalender(konv_id: str, body: _KalenderIn,
                              user: UserContext = Depends(current_user)):
        """„→ Admin-Kalender" (Nutzer-Zuruf): trägt aus dieser Konversation einen
        Termin in den Admin-Kalender ein (V5, docs/26). ``beginn`` ist Pflicht."""
        beginn = (body.beginn or "").strip()
        if not beginn:
            return JSONResponse({"error": "beginn (ISO-Datum/Zeit) ist Pflicht"},
                                status_code=400)
        erg = _sende_konv_termin(konv_id, user.user_id, beginn,
                                 (body.ende or "").strip(), (body.ort or "").strip())
        if erg is None:
            return JSONResponse({"error": "Konversation unbekannt"}, status_code=404)
        if erg.get("status") in ("eingetragen", "vorhanden"):
            _verkn_merken(user.user_id, konv_id, "admin",
                          "komm:termin:" + konv_id, erg.get("id", ""))
        db.audit(user.user_id, "user", "konv_in_kalender",
                 {"konv": konv_id, "status": erg.get("status")})
        return erg

    @router.post("/api/termine/anlegen")
    def termine_anlegen(body: _TermineAnlegenIn,
                        user: UserContext = Depends(current_user)):
        """Sammel-Anlage der per Triage erkannten Termine — **nach Nutzer-Bestätigung**
        (die UI-Sammel-Rückfrage „X Termine gefunden, anlegen?" IST der Human-in-the-
        Loop). Jeder Termin geht über V5 (`sende_termin`) in den Admin-Kalender;
        idempotent per ``ref`` (Titel+Beginn-Hash), auditiert. Nichts wird autonom
        angelegt — dieser Endpoint läuft nur auf expliziten Nutzer-Klick."""
        import hashlib
        from appkit.querverbindung import sende_termin
        angelegt = 0
        ergebnisse: list[dict[str, Any]] = []
        for t in body.termine:
            beginn = (t.beginn or "").strip()
            titel = (t.titel or "").strip() or "Termin"
            if not beginn:
                ergebnisse.append({"titel": titel, "status": "uebersprungen",
                                   "grund": "kein beginn"})
                continue
            ref = "komm:triage:" + hashlib.sha1(
                f"{titel}|{beginn}".encode("utf-8")).hexdigest()[:16]
            besch = (t.beschreibung or "").strip()
            if t.ganztags:
                besch = (besch + "\n" if besch else "") + "(ganztägig)"
            erg = sende_termin("kommunikation", titel, beginn,
                               ende=(t.ende or "").strip(), ort=(t.ort or "").strip(),
                               beschreibung=besch, quelle="komm:triage", ref=ref,
                               ziel="admin", http_post=archiv_post)
            st = erg.get("status") if isinstance(erg, dict) else None
            if st in ("eingetragen", "vorhanden"):
                angelegt += 1
            ergebnisse.append({"titel": titel, "beginn": beginn,
                               "status": st or "fehler"})
        db.audit(user.user_id, "user", "termine_angelegt",
                 {"angelegt": angelegt, "vorgeschlagen": len(body.termine)})
        return {"ok": True, "angelegt": angelegt, "ergebnisse": ergebnisse}

    @router.get("/api/konversationen/{konv_id}/verknuepfungen")
    def konversation_verknuepfungen(konv_id: str,
                                    user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Sichtbare Querverbindungen dieser Konversation (Leitlinie 17.06): je
        Ziel-App ein Eintrag (memory/plans) mit ref+extern_id für den Drill-down.
        Speist die feste Verknüpfungs-Chip-Leiste im Thread."""
        rows = db.get_conn().execute(
            "SELECT ziel, ref, extern_id, created_at FROM querverbindungen "
            "WHERE user_id=? AND konversation_id=? AND deleted_at IS NULL "
            "ORDER BY created_at", (user.user_id, konv_id)).fetchall()
        return [dict(r) for r in rows]

    @router.post("/api/querverbindung/kalender")
    def querverbindung_kalender(body: _KalenderEmpfangIn,
                                user: UserContext = Depends(current_user)):
        """Querverbindungs-EMPFANG (Communication-Kalender-Seite, V5-Rücksync, docs/26
        §4b): eine andere App (v1: Plans per „→ Kommunikation"-Knopf) legt einen Termin
        als **read-only Erinnerung** in Communication ab. **Idempotent** (``quelle=app``
        × ``extern_id=ref``), auditiert. Server-zu-Server über den Core-Relay
        (localhost-Guard + Single-User, kein Token). Nur Daten — kein Aktions-Auslöser."""
        beginn = (body.beginn or "").strip()
        if not beginn:
            return JSONResponse({"ok": False, "error": "beginn fehlt"}, status_code=400)
        titel = (body.titel or "").strip() or "Termin"
        app = (body.app or "").strip() or "querverbindung"
        ref = (body.ref or "").strip() or f"{app}:{titel}:{beginn}"
        beschreibung = (body.beschreibung or "").strip()
        if (body.quelle or "").strip():
            beschreibung = (beschreibung + "\n\n" if beschreibung else "") + \
                "Quelle: " + body.quelle.strip()
        conn = db.get_conn()
        vorhanden = conn.execute(
            "SELECT id FROM kalender_termine WHERE user_id=? AND quelle=? AND extern_id=? "
            "AND deleted_at IS NULL", (user.user_id, app, ref)).fetchone()
        if vorhanden:
            return {"ok": True, "status": "vorhanden", "id": vorhanden["id"]}
        ts = now_iso(); tid = new_id()
        conn.execute(
            "INSERT INTO kalender_termine (id, user_id, titel, beginn, ende, ganztags, ort, "
            "beschreibung, quelle, extern_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, user.user_id, titel, beginn, (body.ende or "").strip(),
             int(body.ganztags), (body.ort or "").strip(), beschreibung, app, ref, ts, ts))
        conn.commit()
        db.audit(user.user_id, "system", "querverbindung_kalender_empfangen",
                 {"app": app, "id": tid, "titel": titel})
        return {"ok": True, "status": "eingetragen", "id": tid}

    @router.get("/api/kalender/termine")
    def kalender_termine(von: str = "", limit: int = 50,
                         user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Read-only Sicht auf die per Querverbindung empfangenen Termine
        (V5-Rücksync). ``von`` (ISO-Datum) filtert auf Termine ab dem Tag —
        Default zeigt anstehende ab heute (kein Filter = alle)."""
        sql = ("SELECT id, titel, beginn, ende, ganztags, ort, beschreibung, quelle "
               "FROM kalender_termine WHERE user_id=? AND deleted_at IS NULL")
        params: list[Any] = [user.user_id]
        if (von or "").strip():
            sql += " AND substr(beginn,1,10) >= ?"
            params.append(von.strip()[:10])
        sql += " ORDER BY beginn ASC LIMIT ?"
        params.append(int(limit))
        rows = db.get_conn().execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    @router.delete("/api/kalender/termine/{tid}")
    def kalender_termin_loeschen(tid: str,
                                 user: UserContext = Depends(current_user)):
        """Eine empfangene Termin-Erinnerung entfernen (Soft-Delete). Betrifft nur
        die lokale Communication-Sicht — die Quelle (z. B. Plans) bleibt unberührt."""
        conn = db.get_conn()
        row = conn.execute("SELECT id FROM kalender_termine WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (tid, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Termin unbekannt"}, status_code=404)
        conn.execute("UPDATE kalender_termine SET deleted_at=? WHERE id=? AND user_id=?",
                     (now_iso(), tid, user.user_id))
        conn.commit()
        db.audit(user.user_id, "user", "kalender_termin_geloescht", {"id": tid})
        return {"ok": True}

    @router.get("/api/kontakte")
    def kontakte(limit: int = 200,
                 user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Kontakte-Klammer (Dossier §5): Personen + ihre Adressen je Kanal,
        mit Nachrichten-Zähler. Beim Sync aus den Absendern aufgebaut."""
        rows = db.get_conn().execute(
            "SELECT k.name, ka.kanal_typ, ka.adresse, "
            "(SELECT COUNT(*) FROM nachrichten n WHERE n.user_id=ka.user_id "
            " AND n.deleted_at IS NULL AND lower(n.von_adresse) LIKE '%'||ka.adresse||'%') "
            "AS nachrichten "
            "FROM kontakt_adressen ka JOIN kontakte k ON k.id=ka.kontakt_id "
            "WHERE ka.user_id=? AND ka.deleted_at IS NULL AND k.deleted_at IS NULL "
            "ORDER BY nachrichten DESC, k.name LIMIT ?",
            (user.user_id, min(limit, 1000))).fetchall()
        return [dict(r) for r in rows]

    # --- Smart Contacts (Kontakt-Unifikation über Kanäle, docs/35 §2/§5.3) ----
    # Das flache ``/api/kontakte`` (je Adresse eine Zeile) bleibt unangetastet;
    # diese ``/api/smartkontakte``-Fläche liefert den KANONISCHEN Kontakt mit
    # seinen Kanal-Aliassen und führt Merge/Split/Alias-Pflege. Nachrichten werden
    # über die AKTUELLEN Aliasse zugeordnet (LIKE je Kanal+Adresse) — Merge/Split
    # verschieben nur Aliasse, der Verlauf folgt automatisch (keine Re-Markierung).

    def _like_escape(text: str) -> str:
        return ("%" + str(text or "").lower().replace("\\", "\\\\")
                .replace("%", "\\%").replace("_", "\\_") + "%")

    def _alias_match_clause(aliasse: list[dict[str, Any]]) -> tuple[str, list[Any]]:
        """SQL-Fragment (+Params), das ``nachrichten n`` auf die Identitäten eines
        Kontakts einschränkt: je Alias der passende Kanal UND die Adresse in
        von_adresse (eingehend) bzw. an_adressen (ausgehend). Ohne Aliasse ⇒ '0'."""
        ors, params = [], []
        for a in aliasse:
            like = _like_escape(a["adresse"])
            ors.append("(n.kanal_typ=? AND (lower(n.von_adresse) LIKE ? ESCAPE '\\' "
                       "OR lower(n.an_adressen) LIKE ? ESCAPE '\\'))")
            params += [a["kanal_typ"], like, like]
        return ("(" + " OR ".join(ors) + ")", params) if ors else ("0", [])

    def _kontakt_aliasse(user_id: str, kontakt_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in db.get_conn().execute(
            "SELECT id, kanal_typ, adresse FROM kontakt_adressen "
            "WHERE user_id=? AND kontakt_id=? AND deleted_at IS NULL "
            "ORDER BY kanal_typ, adresse", (user_id, kontakt_id)).fetchall()]

    @router.get("/api/smartkontakte")
    def smartkontakte(limit: int = 200, q: str = "", sort: str = "relevanz",
                      nur_favoriten: bool = False, kategorie: str = "",
                      user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Kanonische Kontakte mit Kanal-Aliassen + Aktivitäts-Zählern + Kategorie/
        Favorit. Favoriten stehen IMMER oben; danach Sortierung ``relevanz`` (Default,
        jüngste Aktivität) | ``menge`` (Nachrichtenzahl) | ``name`` | ``kategorie``.
        ``q`` sucht in Name + Alias-Adressen; ``nur_favoriten``/``kategorie`` filtern.
        Basis von Dizz Chat + Kontakte-Panel (ein Kontakt, viele Kanäle)."""
        conn = db.get_conn()
        ks = conn.execute(
            "SELECT id, name, kategorie, favorit FROM kontakte "
            "WHERE user_id=? AND deleted_at IS NULL", (user.user_id,)).fetchall()
        ql = (q or "").strip().lower()
        kat = (kategorie or "").strip().lower()
        out = []
        for k in ks:
            if kat and (k["kategorie"] or "") != kat:
                continue
            if nur_favoriten and not k["favorit"]:
                continue
            al = _kontakt_aliasse(user.user_id, k["id"])
            if ql and ql not in (k["name"] or "").lower() and not any(
                    ql in (a["adresse"] or "").lower() for a in al):
                continue
            clause, params = _alias_match_clause(al)
            row = conn.execute(
                "SELECT COUNT(*) AS n, "
                "COALESCE(SUM(CASE WHEN n.gelesen=0 AND n.richtung='ein' THEN 1 ELSE 0 END), 0) "
                "AS ungelesen, (SELECT COALESCE(NULLIF(gesendet_at, ''), created_at) "
                " FROM nachrichten n WHERE n.user_id=? AND n.deleted_at IS NULL AND " + clause +
                " ORDER BY rowid DESC LIMIT 1) AS letzte "
                "FROM nachrichten n WHERE n.user_id=? AND n.deleted_at IS NULL AND " + clause,
                [user.user_id, *params, user.user_id, *params]).fetchone()
            out.append({"id": k["id"], "name": k["name"], "aliasse": al,
                        "kategorie": k["kategorie"] or "", "favorit": bool(k["favorit"]),
                        "kanaele": sorted({a["kanal_typ"] for a in al}),
                        "nachrichten": row["n"], "ungelesen": row["ungelesen"],
                        "letzte": row["letzte"] or ""})
        # Sortier-Schlüssel (ohne Favorit); Favoriten werden danach vorgezogen.
        if sort == "name":
            out.sort(key=lambda c: (c["name"] or "").lower())
        elif sort == "menge":
            out.sort(key=lambda c: c["nachrichten"], reverse=True)
        elif sort == "kategorie":
            out.sort(key=lambda c: ((c["kategorie"] or "~"), (c["name"] or "").lower()))
        else:  # relevanz (Default)
            out.sort(key=lambda c: (c["letzte"] or "", c["nachrichten"]), reverse=True)
        out.sort(key=lambda c: 0 if c["favorit"] else 1)   # stabile Vorsortierung: Favoriten oben
        return out[:min(limit, 1000)]

    @router.post("/api/smartkontakte")
    def smartkontakt_anlegen(body: _KontaktIn = _KontaktIn(),
                             user: UserContext = Depends(current_user)):
        """Kanonischen Kontakt manuell anlegen (z. B. um danach Kanal-Aliasse zu
        verknüpfen). Sync legt Kontakte ohnehin aus Absendern an."""
        name = (body.name or "").strip()[:120]
        if not name:
            return JSONResponse({"error": "name ist Pflicht"}, status_code=400)
        ts = now_iso(); kid = new_id()
        db.get_conn().execute(
            "INSERT INTO kontakte (id, user_id, name, created_at, updated_at) "
            "VALUES (?,?,?,?,?)", (kid, user.user_id, name, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "kontakt_angelegt", {"id": kid, "name": name})
        return {"id": kid, "name": name}

    @router.post("/api/smartkontakte/{kontakt_id}/kategorie")
    def smartkontakt_kategorie(kontakt_id: str, body: _KategorieIn,
                               user: UserContext = Depends(current_user)):
        """Kategorie eines Kontakts setzen (was er IST: Freund/Familie/Geschäft/…)."""
        kat = (body.kategorie or "").strip().lower()
        if kat not in KONTAKT_KATEGORIEN:
            return JSONResponse({"error": f"kategorie unbekannt: {kat!r}"}, status_code=400)
        conn = db.get_conn()
        cur = conn.execute(
            "UPDATE kontakte SET kategorie=?, updated_at=? WHERE id=? AND user_id=? "
            "AND deleted_at IS NULL", (kat, now_iso(), kontakt_id, user.user_id))
        conn.commit()
        if not cur.rowcount:
            return JSONResponse({"error": "Kontakt unbekannt"}, status_code=404)
        return {"ok": True, "kategorie": kat}

    @router.post("/api/smartkontakte/{kontakt_id}/favorit")
    def smartkontakt_favorit(kontakt_id: str, body: _FavoritIn = _FavoritIn(),
                             user: UserContext = Depends(current_user)):
        """Favorit umschalten (``favorit`` weggelassen) oder explizit setzen.
        Favoriten erscheinen immer ganz oben in der Kontakte-Liste."""
        conn = db.get_conn()
        row = conn.execute("SELECT favorit FROM kontakte WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (kontakt_id, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Kontakt unbekannt"}, status_code=404)
        neu = (not row["favorit"]) if body.favorit is None else bool(body.favorit)
        conn.execute("UPDATE kontakte SET favorit=?, updated_at=? WHERE id=? AND user_id=?",
                     (1 if neu else 0, now_iso(), kontakt_id, user.user_id))
        conn.commit()
        return {"ok": True, "favorit": neu}

    @router.get("/api/smartkontakte/vorschlaege")
    def smartkontakte_vorschlaege(
            user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Deterministische Merge-Vorschläge (kontakte.py): gleiche Namen / gleiche
        Identitäts-Stämme über Kanäle. NUR Vorschläge — Zusammenführen ist eine
        Nutzer-Aktion (eine Falsch-Verschmelzung wäre teuer)."""
        conn = db.get_conn()
        ks = conn.execute(
            "SELECT id, name FROM kontakte WHERE user_id=? AND deleted_at IS NULL",
            (user.user_id,)).fetchall()
        daten = [{"id": k["id"], "name": k["name"],
                  "aliasse": _kontakt_aliasse(user.user_id, k["id"])} for k in ks]
        return finde_merge_vorschlaege(daten)

    @router.post("/api/smartkontakte/{kontakt_id}/aliasse")
    def smartkontakt_alias_hinzu(kontakt_id: str, body: _AliasIn,
                                 user: UserContext = Depends(current_user)):
        """Kanal-Identität an einen kanonischen Kontakt hängen — so entsteht die
        Kontakt-Unifikation (z. B. Telegram-Handle zu einem E-Mail-Kontakt). Gehört
        die Identität schon einem anderen Kontakt, wird sie auf BefehL EXPLIZIT
        umgehängt (Nutzer behauptet die Identität)."""
        kt = (body.kanal_typ or "").strip().lower()
        adr = (body.adresse or "").strip().lower()
        if kt not in channels.KANAELE:
            return JSONResponse({"error": f"kanal_typ unbekannt: {kt!r}"}, status_code=400)
        if not adr:
            return JSONResponse({"error": "adresse ist Pflicht"}, status_code=400)
        conn = db.get_conn()
        if conn.execute("SELECT 1 FROM kontakte WHERE id=? AND user_id=? AND deleted_at IS NULL",
                        (kontakt_id, user.user_id)).fetchone() is None:
            return JSONResponse({"error": "Kontakt unbekannt"}, status_code=404)
        ts = now_iso()
        # UNIQUE(user, kanal_typ, adresse): vorhandene (ggf. soft-gelöschte) Zeile
        # wiederbeleben + umhängen statt zu kollidieren.
        vorhanden = conn.execute(
            "SELECT id, kontakt_id, deleted_at FROM kontakt_adressen "
            "WHERE user_id=? AND kanal_typ=? AND adresse=?", (user.user_id, kt, adr)).fetchone()
        if vorhanden:
            war_aktiv_hier = vorhanden["kontakt_id"] == kontakt_id and vorhanden["deleted_at"] is None
            conn.execute(
                "UPDATE kontakt_adressen SET kontakt_id=?, deleted_at=NULL, updated_at=? "
                "WHERE id=?", (kontakt_id, ts, vorhanden["id"]))
            conn.commit()
            status = "vorhanden" if war_aktiv_hier else "umgehaengt"
            db.audit(user.user_id, "user", "alias_" + status,
                     {"kontakt": kontakt_id, "kanal": kt})
            return {"ok": True, "status": status, "id": vorhanden["id"]}
        aid = new_id()
        conn.execute(
            "INSERT INTO kontakt_adressen (id, user_id, kontakt_id, kanal_typ, adresse, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (aid, user.user_id, kontakt_id, kt, adr, ts, ts))
        conn.commit()
        db.audit(user.user_id, "user", "alias_hinzugefuegt", {"kontakt": kontakt_id, "kanal": kt})
        return {"ok": True, "status": "hinzugefuegt", "id": aid}

    @router.delete("/api/smartkontakte/{kontakt_id}/aliasse/{adress_id}")
    def smartkontakt_alias_entfernen(kontakt_id: str, adress_id: str,
                                     user: UserContext = Depends(current_user)):
        """Eine Kanal-Identität vom Kontakt lösen (Soft-Delete). Nachrichten bleiben
        erhalten, sie sind nur nicht mehr diesem Kontakt zugeordnet."""
        conn = db.get_conn()
        cur = conn.execute(
            "UPDATE kontakt_adressen SET deleted_at=?, updated_at=? "
            "WHERE id=? AND kontakt_id=? AND user_id=? AND deleted_at IS NULL",
            (now_iso(), now_iso(), adress_id, kontakt_id, user.user_id))
        conn.commit()
        return {"ok": True, "entfernt": cur.rowcount}

    @router.post("/api/smartkontakte/{kontakt_id}/zusammenfuehren")
    def smartkontakt_zusammenfuehren(kontakt_id: str, body: _MergeIn,
                                     user: UserContext = Depends(current_user)):
        """Zwei kanonische Kontakte vereinen: alle Aliasse von ``anderer_id`` wandern
        auf ``kontakt_id`` (Ziel), der andere wird soft-gelöscht. Der Verlauf bündelt
        sich automatisch (Zuordnung folgt den Aliassen). Idempotent-tolerant."""
        anderer = (body.anderer_id or "").strip()
        if not anderer or anderer == kontakt_id:
            return JSONResponse({"error": "anderer_id (≠ Ziel) ist Pflicht"}, status_code=400)
        conn = db.get_conn()
        for kid in (kontakt_id, anderer):
            if conn.execute("SELECT 1 FROM kontakte WHERE id=? AND user_id=? AND deleted_at IS NULL",
                            (kid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": f"Kontakt unbekannt: {kid}"}, status_code=404)
        ts = now_iso()
        cur = conn.execute(
            "UPDATE kontakt_adressen SET kontakt_id=?, updated_at=? "
            "WHERE kontakt_id=? AND user_id=? AND deleted_at IS NULL",
            (kontakt_id, ts, anderer, user.user_id))
        conn.execute("UPDATE kontakte SET deleted_at=?, updated_at=? WHERE id=? AND user_id=?",
                     (ts, ts, anderer, user.user_id))
        conn.commit()
        db.audit(user.user_id, "user", "kontakte_zusammengefuehrt",
                 {"ziel": kontakt_id, "aufgegangen": anderer, "aliasse": cur.rowcount})
        return {"ok": True, "ziel": kontakt_id, "verschobene_aliasse": cur.rowcount}

    @router.post("/api/smartkontakte/{kontakt_id}/trennen")
    def smartkontakt_trennen(kontakt_id: str, body: _SplitIn,
                             user: UserContext = Depends(current_user)):
        """Eine Kanal-Identität aus einem Kontakt herauslösen: ``adress_id`` bekommt
        einen NEUEN eigenen Kontakt (Gegenstück zu Merge, falls fälschlich vereint)."""
        adress_id = (body.adress_id or "").strip()
        conn = db.get_conn()
        al = conn.execute(
            "SELECT id, adresse FROM kontakt_adressen WHERE id=? AND kontakt_id=? "
            "AND user_id=? AND deleted_at IS NULL", (adress_id, kontakt_id, user.user_id)).fetchone()
        if al is None:
            return JSONResponse({"error": "Alias gehört nicht zu diesem Kontakt"}, status_code=404)
        ts = now_iso(); neu = new_id()
        conn.execute("INSERT INTO kontakte (id, user_id, name, created_at, updated_at) "
                     "VALUES (?,?,?,?,?)", (neu, user.user_id, al["adresse"][:120], ts, ts))
        conn.execute("UPDATE kontakt_adressen SET kontakt_id=?, updated_at=? WHERE id=?",
                     (neu, ts, al["id"]))
        conn.commit()
        db.audit(user.user_id, "user", "kontakt_getrennt",
                 {"von": kontakt_id, "neuer": neu, "alias": adress_id})
        return {"ok": True, "neuer_id": neu, "name": al["adresse"]}

    def _letzter_eingang_kanal(user_id: str, aliasse: list[dict[str, Any]]) -> str:
        """Kanal der zuletzt EINGEGANGENEN Nachricht dieses Kontakts — die Default-
        Wahl für Unified Reply („antworte über den letzten Kanal")."""
        clause, params = _alias_match_clause(aliasse)
        row = db.get_conn().execute(
            "SELECT n.kanal_typ FROM nachrichten n WHERE n.user_id=? AND n.deleted_at "
            "IS NULL AND n.richtung='ein' AND " + clause +
            " ORDER BY n.rowid DESC LIMIT 1", [user_id, *params]).fetchone()
        return row["kanal_typ"] if row else ""

    @router.get("/api/smartkontakte/{kontakt_id}/verlauf")
    def smartkontakt_verlauf(kontakt_id: str, limit: int = 200,
                             user: UserContext = Depends(current_user)):
        """UNIFIED INBOX (docs/35 §2): EIN Kontakt-Thread, der die Nachrichten ALLER
        Kanäle dieses Kontakts chronologisch zusammenführt. Jede Nachricht trägt ihr
        ``kanal_typ`` = Herkunfts-Label (woher sie kam). Zuordnung über die aktuellen
        Aliasse (folgt Merge/Split). E-Mail ist real, andere Kanäle simuliert."""
        conn = db.get_conn()
        kopf = conn.execute(
            "SELECT id, name FROM kontakte WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (kontakt_id, user.user_id)).fetchone()
        if kopf is None:
            return JSONResponse({"error": "Kontakt unbekannt"}, status_code=404)
        al = _kontakt_aliasse(user.user_id, kontakt_id)
        clause, params = _alias_match_clause(al)
        rows = conn.execute(
            "SELECT n.id, n.kanal_typ, n.richtung, n.von_adresse, n.an_adressen, "
            "n.betreff, n.text, n.ordner, n.gelesen, n.gesendet_at, n.created_at, "
            "n.konversation_id FROM nachrichten n WHERE n.user_id=? AND n.deleted_at "
            "IS NULL AND " + clause + " ORDER BY n.rowid ASC LIMIT ?",
            [user.user_id, *params, min(limit, 500)]).fetchall()
        return {"kontakt": {"id": kopf["id"], "name": kopf["name"], "aliasse": al,
                            "kanaele": sorted({a["kanal_typ"] for a in al}),
                            "letzter_kanal": _letzter_eingang_kanal(user.user_id, al)},
                "nachrichten": [dict(r) for r in rows]}

    @router.post("/api/smartkontakte/{kontakt_id}/antwort")
    def smartkontakt_antwort(kontakt_id: str, body: _AntwortIn,
                             user: UserContext = Depends(current_user)):
        """UNIFIED REPLY (docs/35 §2): aus dem einen Kontakt-Thread antworten. Kanal
        = explizit (``kanal_typ``) ODER automatisch der zuletzt EINGEGANGENE Kanal.
        Empfänger = mitgegeben ODER aus den Kontakt-Aliassen abgeleitet. Senden ist
        IMMER HITL (``nachricht_senden``, verifiziert): es entsteht ein PENDING-
        Vorschlag, nie ein autonomer Versand. Dormante Kanäle: der Vorschlag wird
        vorbereitet/angezeigt, aber als ``gesperrt`` markiert — eine Freigabe würde
        fail-closed scheitern (Gesetz 5)."""
        conn = db.get_conn()
        if conn.execute("SELECT 1 FROM kontakte WHERE id=? AND user_id=? AND deleted_at IS NULL",
                        (kontakt_id, user.user_id)).fetchone() is None:
            return JSONResponse({"error": "Kontakt unbekannt"}, status_code=404)
        text = (body.text or "").strip()
        if not text:
            return JSONResponse({"error": "text ist Pflicht"}, status_code=400)
        al = _kontakt_aliasse(user.user_id, kontakt_id)
        if not al:
            return JSONResponse({"error": "Kontakt hat keine Kanal-Identitäten"},
                                status_code=400)
        # Kanal bestimmen: explizit → letzter Eingang → E-Mail bevorzugt → erster Alias.
        kt = (body.kanal_typ or "").strip().lower() or _letzter_eingang_kanal(user.user_id, al)
        if not kt:
            kt = (KANAL_EMAIL if any(a["kanal_typ"] == KANAL_EMAIL for a in al)
                  else al[0]["kanal_typ"])
        if kt not in channels.KANAELE:
            return JSONResponse({"error": f"kanal_typ unbekannt: {kt!r}"}, status_code=400)
        # Empfänger im gewählten Kanal ableiten (falls nicht mitgegeben).
        an = (body.an or "").strip()
        if not an:
            ziel = next((a for a in al if a["kanal_typ"] == kt), None)
            if ziel is None:
                return JSONResponse(
                    {"error": f"Kontakt hat keine Identität auf Kanal {kt!r}"},
                    status_code=400)
            an = ziel["adresse"]
        konto_id = (body.konto_id or "").strip()
        if kt == KANAL_EMAIL and not konto_id:
            erstes = _erstes_sendekonto(user.user_id)
            konto_id = erstes["id"] if erstes else ""
        verbunden = _kanal_connector(user.user_id, kt).verbunden()
        params = {"user_id": user.user_id, "kanal_typ": kt, "an": an, "text": text,
                  "betreff": (body.betreff or "").strip(), "konto_id": konto_id,
                  "kontakt_id": kontakt_id}
        from appkit.actions import propose
        v = propose(db, actions, user.user_id, "nachricht_senden", params, source="user")
        v.update(kanal_typ=kt, an=an, kanal_verbunden=verbunden, gesperrt=not verbunden)
        if not verbunden:
            v["hinweis"] = (f"Kanal {kt} ist noch nicht verbunden — Vorschlag liegt bereit, "
                            "eine Freigabe scheitert aber fail-closed (Gesetz 5).")
        db.audit(user.user_id, "user", "unified_antwort_vorgeschlagen",
                 {"kontakt": kontakt_id, "kanal": kt, "verbunden": verbunden})
        return v

    @router.get("/api/kanaele")
    def kanaele(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Kanal-Übersicht (Konnektivitäts-Vision docs/35 §2): E-Mail aktiv,
        Telegram/WhatsApp/Instagram/Snapchat vorbereitet (dormant). Je Kanal:
        Status (verbunden/aktiv/weg) + Mode-Schalter-Wert + Aktivitäts-Zähler
        (Kontakte/Nachrichten auf dem Kanal). Macht die Gesetz-5-Slots SICHTBAR."""
        conn = db.get_conn()
        n_je = {r["kanal_typ"]: r["n"] for r in conn.execute(
            "SELECT kanal_typ, COUNT(*) AS n FROM nachrichten "
            "WHERE user_id=? AND deleted_at IS NULL GROUP BY kanal_typ",
            (user.user_id,)).fetchall()}
        k_je = {r["kanal_typ"]: r["n"] for r in conn.execute(
            "SELECT kanal_typ, COUNT(DISTINCT kontakt_id) AS n FROM kontakt_adressen "
            "WHERE user_id=? AND deleted_at IS NULL GROUP BY kanal_typ",
            (user.user_id,)).fetchall()}
        out = []
        for s in channels.kanaele_status(
                email_konto_vorhanden=lambda: _hat_sendekonto(user.user_id),
                adapter=_adapter_connectoren):
            kt = s["kanal_typ"]
            s["nachrichten"] = int(n_je.get(kt, 0))
            s["kontakte"] = int(k_je.get(kt, 0))
            # Mode-Schalter-Wert (vorbereitet-Setting) transparent mitliefern.
            if s.get("modus_setting"):
                s["modus_an"] = bool(db.setting_get(user.user_id, s["modus_setting"], False))
            out.append(s)
        return out

    # --- Meta-Konnektor: Config-Flow + Webhook (docs/38) ---------------------
    @router.get("/api/konnektoren", include_in_schema=False)
    def konnektoren() -> dict[str, Any]:
        """W4-Sichtbarkeit: alle externen Connectoren + Status (read-only)."""
        st = _konn_reg.status()
        return {"konnektoren": st, "anzahl": len(st),
                "verbunden": sum(1 for c in st if c.get("verbunden"))}

    @router.get("/api/kanaele/meta/status")
    def meta_status(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Meta-Kanal-Status für die Config-UI: pro Kanal Token-/ID-Stand (NIE die
        Werte), Permissions, Aktivierung; + Webhook-Pfad/Secrets-Stand."""
        v = vault_ref["vault"]
        kanaele = []
        for kt, c in _meta_connectoren.items():
            kanaele.append({
                "kanal_typ": kt, "label": c.label,
                "verbunden": c.verfuegbar(), "token_gesetzt": bool(v.get(c.token_name)),
                "permissions": list(c.permissions), "aktivierung": c.aktivierung,
                "api_doc": c.API_DOC,
                "phone_number_id": db.setting_get(user.user_id, "whatsapp_phone_number_id", "")
                if kt == "whatsapp" else None,
                "ig_user_id": db.setting_get(user.user_id, "instagram_user_id", "")
                if kt == "instagram" else None})
        return {"kanaele": kanaele,
                "graph_version": db.setting_get(user.user_id, "graph_version", meta.GRAPH_VERSION),
                "webhook_pfad": "/api/kanaele/meta/webhook",
                "app_secret_gesetzt": bool(v.get("meta_app_secret")),
                "verify_token_gesetzt": bool(v.get("meta_webhook_verify_token")),
                "webhook_hinweis": ("Eingang braucht eine öffentliche HTTPS-URL "
                                    "(Tunnel/Server) — Outbound läuft auch rein lokal.")}

    @router.post("/api/kanaele/meta/verbinden")
    def meta_verbinden(body: _MetaVerbindenIn,
                       user: UserContext = Depends(current_user)):
        """Token/Secret → Tresor, nicht-geheime IDs → Settings. Teil-aktualisierbar;
        die Werte selbst werden NIE auditiert (nur welche Felder gesetzt wurden)."""
        kanal = (body.kanal or "").strip().lower()
        if kanal not in meta.META_KANAELE:
            return JSONResponse({"error": f"kanal unbekannt: {kanal!r}"}, status_code=400)
        v = vault_ref["vault"]
        gesetzt: list[str] = []
        if (body.token or "").strip():
            v.put(f"meta_{kanal}_token", body.token.strip()); gesetzt.append("token")
        if (body.app_secret or "").strip():
            v.put("meta_app_secret", body.app_secret.strip()); gesetzt.append("app_secret")
        if (body.verify_token or "").strip():
            v.put("meta_webhook_verify_token", body.verify_token.strip())
            gesetzt.append("verify_token")
        if kanal == "whatsapp" and (body.phone_number_id or "").strip():
            db.setting_put(user.user_id, "whatsapp_phone_number_id",
                           body.phone_number_id.strip()); gesetzt.append("phone_number_id")
        if kanal == "instagram" and (body.ig_user_id or "").strip():
            db.setting_put(user.user_id, "instagram_user_id",
                           body.ig_user_id.strip()); gesetzt.append("ig_user_id")
        db.audit(user.user_id, "user", "meta_verbunden", {"kanal": kanal, "gesetzt": gesetzt})
        return {"ok": True, "kanal": kanal, "gesetzt": gesetzt,
                "verbunden": _meta_connectoren[kanal].verfuegbar()}

    @router.delete("/api/kanaele/meta/verbinden")
    def meta_trennen(kanal: str = "", user: UserContext = Depends(current_user)):
        """Token eines Meta-Kanals aus dem Tresor löschen (⇒ wieder dormant)."""
        kanal = (kanal or "").strip().lower()
        if kanal not in meta.META_KANAELE:
            return JSONResponse({"error": f"kanal unbekannt: {kanal!r}"}, status_code=400)
        geloescht = vault_ref["vault"].delete(f"meta_{kanal}_token")
        db.audit(user.user_id, "user", "meta_getrennt",
                 {"kanal": kanal, "token_geloescht": geloescht})
        return {"ok": True, "kanal": kanal, "token_geloescht": geloescht}

    @router.post("/api/kanaele/meta/test")
    def meta_test_senden(body: _MetaTestIn,
                         user: UserContext = Depends(current_user)):
        """Test-Sende aus der Config-UI — bleibt HITL (legt einen ``nachricht_senden``-
        Vorschlag an; auf Freigabe geht der echte Graph-Call, dormant fail-closed)."""
        kanal = (body.kanal or "").strip().lower()
        if kanal not in meta.META_KANAELE:
            return JSONResponse({"error": f"kanal unbekannt: {kanal!r}"}, status_code=400)
        an = (body.an or "").strip()
        if not an:
            return JSONResponse({"error": "an (Empfänger) ist Pflicht"}, status_code=400)
        verbunden = _meta_connectoren[kanal].verfuegbar()
        params = {"user_id": user.user_id, "kanal_typ": kanal, "an": an,
                  "text": (body.text or "").strip(), "betreff": "",
                  "template": (body.template or "").strip()}
        from appkit.actions import propose
        vorschlag = propose(db, actions, user.user_id, "nachricht_senden", params, source="user")
        vorschlag.update(kanal_typ=kanal, an=an, kanal_verbunden=verbunden,
                         gesperrt=not verbunden)
        if not verbunden:
            vorschlag["hinweis"] = (f"{kanal} noch nicht verbunden — HITL-Vorschlag liegt "
                                    "bereit, Freigabe scheitert fail-closed (Token fehlt).")
        return vorschlag

    @router.get("/api/kanaele/meta/webhook", include_in_schema=False)
    def meta_webhook_verify_ep(request: Request):
        """Meta-Webhook-Verify (GET): Challenge zurückspielen, wenn der ``hub.verify_
        token`` mit dem im Tresor übereinstimmt (sonst 403)."""
        qp = request.query_params
        erwartet = vault_ref["vault"].get("meta_webhook_verify_token")
        ch = meta.webhook_verify(qp.get("hub.mode"), qp.get("hub.verify_token"),
                                 qp.get("hub.challenge"), erwartet)
        if ch is None:
            return JSONResponse({"error": "verify fehlgeschlagen"}, status_code=403)
        return PlainTextResponse(ch)

    @router.post("/api/kanaele/meta/webhook", include_in_schema=False)
    async def meta_webhook_ep(request: Request):
        """Meta-Webhook-Empfang (POST): Signatur prüfen (X-Hub-Signature-256 mit
        App-Secret), Events normieren (meta.webhook_parse) und in die Unified-Inbox
        einsortieren (+ Smart-Contact-Unifikation über ``_kontakt_klammer``). Das
        tatsächliche Eintreffen setzt eine öffentliche URL voraus (Tunnel/Server)."""
        raw = await request.body()
        app_secret = vault_ref["vault"].get("meta_app_secret")
        # Fail-closed: ohne hinterlegtes App-Secret ist der Eingang unverifizierbar ⇒
        # ablehnen (sonst könnte ein öffentlich erreichbarer Webhook gefälschte Events
        # einschleusen). Das App-Secret wird bei der Aktivierung in der Config-UI gesetzt.
        if not app_secret:
            db.audit(DEFAULT_USER_ID, "system", "meta_webhook_kein_secret", {})
            return JSONResponse({"error": "Webhook nicht aktiv (App-Secret fehlt)"},
                                status_code=403)
        if not meta.pruefe_signatur(raw, request.headers.get("x-hub-signature-256"),
                                    app_secret):
            db.audit(DEFAULT_USER_ID, "system", "meta_webhook_signatur_ungueltig", {})
            return JSONResponse({"error": "Signatur ungültig"}, status_code=403)
        import json as _json
        try:
            payload = _json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        nachrichten = meta.webhook_parse(payload)
        neu = 0
        for n in nachrichten:
            konto_id = _demo_kanal_konto(DEFAULT_USER_ID, n["kanal_typ"])
            neu += _einsortieren(DEFAULT_USER_ID, konto_id, [n], ordner="META")
        db.audit(DEFAULT_USER_ID, "system", "meta_webhook_empfangen",
                 {"empfangen": len(nachrichten), "neu": neu})
        return {"ok": True, "empfangen": len(nachrichten), "neu": neu}

    def _demo_kanal_konto(user_id: str, kanal_typ: str) -> str:
        """Findet/erzeugt das simulierte „Konto" eines dormanten Kanals (Träger der
        Demo-Nachrichten — die Schema-Kette ist konto→konversation→nachricht). Kein
        IMAP/Geheimnis; sync_lauf überspringt es (art ≠ imap/gmail/jmap)."""
        conn = db.get_conn()
        row = conn.execute(
            "SELECT id FROM konten WHERE user_id=? AND art=? AND deleted_at IS NULL "
            "LIMIT 1", (user_id, kanal_typ)).fetchone()
        if row:
            return row["id"]
        kid = new_id(); ts = now_iso()
        conn.execute(
            "INSERT INTO konten (id, user_id, name, art, host, port, benutzer, auth, "
            "tresor_ref, smtp_host, smtp_port, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kid, user_id, f"{kanal_typ} (simuliert)", kanal_typ, "", 0,
             "(simuliert)", "passwort", "", "", 0, ts, ts))
        conn.commit()
        return kid

    # --- Telegram-Konnektor: Config-Flow + Inbound-Polling (lokal, KEIN Webhook) ---
    @router.get("/api/kanaele/telegram/status")
    def telegram_status(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Telegram-Status für die Config-UI: Token-Stand (NIE der Wert), Bot-Identität
        (getMe, best-effort), Polling-Offset, Aktivierung. Lokal — KEIN Webhook/URL."""
        v = vault_ref["vault"]
        return {"kanal_typ": "telegram", "label": _telegram_conn.label,
                "verbunden": _telegram_conn.verfuegbar(),
                "token_gesetzt": bool(v.get(_telegram_conn.token_name)),
                "offset": int(db.setting_get(user.user_id, "telegram_offset", 0) or 0),
                "aktivierung": _telegram_conn.aktivierung, "api_doc": _telegram_conn.API_DOC,
                "transport": "long-polling (getUpdates) — lokal, kein Webhook/Review"}

    @router.post("/api/kanaele/telegram/verbinden")
    def telegram_verbinden(body: _TgVerbindenIn,
                           user: UserContext = Depends(current_user)):
        """Bot-Token → Tresor (telegram_bot_token); der Wert wird NIE auditiert (nur
        dass er gesetzt wurde). Lokaler Aktivierungs-Flow — kein App-Review."""
        token = (body.token or "").strip()
        if not token:
            return JSONResponse({"error": "token (Bot-Token von @BotFather) ist Pflicht"},
                                status_code=400)
        vault_ref["vault"].put("telegram_bot_token", token)
        db.audit(user.user_id, "user", "telegram_verbunden", {"gesetzt": ["token"]})
        return {"ok": True, "verbunden": _telegram_conn.verfuegbar()}

    @router.post("/api/kanaele/telegram/pruefen")
    def telegram_pruefen(user: UserContext = Depends(current_user)):
        """Bot-Identität live prüfen (getMe) — bestätigt, dass der Token gültig ist,
        und zeigt @username. Explizite Nutzer-Aktion (Netz nötig); dormant ⇒ 409."""
        if not _telegram_conn.verfuegbar():
            return JSONResponse(
                {"error": "Telegram nicht verbunden — Bot-Token fehlt im Tresor."},
                status_code=409)
        bot = _telegram_conn.bot_info()
        if not bot:
            return JSONResponse(
                {"error": "getMe fehlgeschlagen — Token ungültig oder Telegram nicht erreichbar."},
                status_code=502)
        return {"ok": True, "bot_username": bot.get("username", ""),
                "bot_name": bot.get("first_name", ""), "bot_id": bot.get("id")}

    @router.delete("/api/kanaele/telegram/verbinden")
    def telegram_trennen(user: UserContext = Depends(current_user)):
        """Bot-Token aus dem Tresor löschen (⇒ wieder dormant)."""
        geloescht = vault_ref["vault"].delete("telegram_bot_token")
        db.audit(user.user_id, "user", "telegram_getrennt", {"token_geloescht": geloescht})
        return {"ok": True, "token_geloescht": geloescht}

    @router.post("/api/kanaele/telegram/test")
    def telegram_test_senden(body: _TgTestIn,
                             user: UserContext = Depends(current_user)):
        """Test-Sende aus der Config-UI — bleibt HITL (legt einen ``nachricht_senden``-
        Vorschlag an; auf Freigabe geht der echte sendMessage, dormant fail-closed)."""
        an = (body.an or "").strip()
        if not an:
            return JSONResponse({"error": "an (chat_id) ist Pflicht"}, status_code=400)
        verbunden = _telegram_conn.verfuegbar()
        params = {"user_id": user.user_id, "kanal_typ": "telegram", "an": an,
                  "text": (body.text or "").strip(), "betreff": "", "template": ""}
        from appkit.actions import propose
        vorschlag = propose(db, actions, user.user_id, "nachricht_senden", params, source="user")
        vorschlag.update(kanal_typ="telegram", an=an, kanal_verbunden=verbunden,
                         gesperrt=not verbunden)
        if not verbunden:
            vorschlag["hinweis"] = ("Telegram noch nicht verbunden — HITL-Vorschlag liegt "
                                    "bereit, Freigabe scheitert fail-closed (Token fehlt).")
        return vorschlag

    @router.post("/api/kanaele/telegram/sync")
    def telegram_sync(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Inbound per Long-Polling: ``getUpdates`` ab dem persistierten Offset, neue
        Nachrichten in die Unified-Inbox einsortieren (+ Smart-Contact-Unifikation),
        Offset fortschreiben. Lokal, ohne Tunnel. Ohne Token ⇒ ehrlich 409."""
        if not _telegram_conn.verfuegbar():
            return JSONResponse(
                {"error": "Telegram nicht verbunden — Bot-Token fehlt im Tresor."},
                status_code=409)
        offset = int(db.setting_get(user.user_id, "telegram_offset", 0) or 0)
        try:
            nachrichten, next_off = _telegram_conn.abrufen(offset)
        except Exception as e:
            db.audit(user.user_id, "system", "telegram_sync_fehlgeschlagen",
                     {"fehler": f"{type(e).__name__}: {e}"})
            return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=502)
        konto_id = _demo_kanal_konto(user.user_id, "telegram")
        neu = _einsortieren(user.user_id, konto_id, nachrichten, ordner="TELEGRAM")
        if next_off and next_off != offset:
            db.setting_put(user.user_id, "telegram_offset", int(next_off))
        db.audit(user.user_id, "system", "telegram_sync_ok",
                 {"geholt": len(nachrichten), "neu": neu, "offset": int(next_off or offset)})
        return {"geholt": len(nachrichten), "neu": neu, "offset": int(next_off or offset)}

    @router.post("/api/kanaele/{kanal_typ}/simulieren")
    def kanal_simulieren(kanal_typ: str, body: _SimIn,
                         user: UserContext = Depends(current_user)):
        """Demo-Ingest (docs/35 §6): EINE eingehende Nachricht auf einem dormanten
        Kanal vortäuschen, damit die Unified Inbox „ein Kontakt über alle Kanäle"
        real demonstrierbar ist (E-Mail real, andere Kanäle simuliert). KEINE
        Plattform-Anbindung — rein lokale Daten. E-Mail nutzt den echten Sync."""
        kt = (kanal_typ or "").strip().lower()
        if kt not in channels.KANAELE:
            return JSONResponse({"error": f"kanal_typ unbekannt: {kt!r}"}, status_code=400)
        if kt == KANAL_EMAIL:
            return JSONResponse({"error": "E-Mail kommt über den echten Sync, nicht "
                                "über die Simulation."}, status_code=400)
        von = (body.von or "").strip()
        if not von:
            return JSONResponse({"error": "von (Absender-Handle) ist Pflicht"},
                                status_code=400)
        konto_id = _demo_kanal_konto(user.user_id, kt)
        n = {"kanal_typ": kt, "extern_id": f"sim:{kt}:{new_id()}",
             "von_adresse": von, "an_adressen": "ich",
             "betreff": (body.betreff or "").strip(),
             "text": (body.text or "").strip(), "gesendet_at": now_iso(),
             "thread_schluessel": f"sim:{kt}:{von.lower()}"}
        neu = _einsortieren(user.user_id, konto_id, [n], ordner="SIM")
        db.audit(user.user_id, "system", "kanal_simuliert",
                 {"kanal": kt, "von": von, "neu": neu})
        return {"ok": True, "kanal_typ": kt, "konto_id": konto_id, "neu": neu}

    @router.get("/api/suche")
    def suche(q: str = "", konto_id: str = "", nur_ungelesen: bool = False,
              limit: int = 50,
              user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Volltext-Suche im Posteingang (LOKAL): Mehrwort-UND über Betreff/
        Absender/Empfänger/Text, case-insensitiv. v1 = LIKE mit ESCAPE (für die
        persönliche Postfach-Größe ausreichend; FTS5-Ranking ist der spätere
        Ausbau). Liefert Treffer-Metadaten + Snippet + konversation_id (Klick
        in der UI öffnet den Thread). KEIN MCP-Tool (trägt Text-Snippet)."""
        # Such-Operator (P3, Superhuman-Stil): ``von:<x>`` schränkt auf den Absender
        # ein, der Rest ist Volltext über Betreff/Absender/Empfänger/Text.
        roh = [t for t in q.lower().split() if t][:8]
        von_terms = [t[4:] for t in roh if t.startswith("von:") and len(t) > 4]
        text_terms = [t for t in roh if not t.startswith("von:")][:6]
        if not von_terms and not text_terms:
            return []

        def _like(t: str) -> str:
            return "%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

        sql = ("SELECT n.id, n.betreff, n.von_adresse, n.gesendet_at, n.gelesen, "
               "n.kanal_typ, n.ordner, substr(n.text, 1, 200) AS snippet, "
               "n.konversation_id, k.konto_id, k.titel AS konversation "
               "FROM nachrichten n JOIN konversationen k ON k.id = n.konversation_id "
               "WHERE n.user_id=? AND n.deleted_at IS NULL")
        params: list[Any] = [user.user_id]
        for t in text_terms:
            like = _like(t)
            sql += (" AND (lower(n.betreff) LIKE ? ESCAPE '\\' OR "
                    "lower(n.von_adresse) LIKE ? ESCAPE '\\' OR "
                    "lower(n.an_adressen) LIKE ? ESCAPE '\\' OR "
                    "lower(n.text) LIKE ? ESCAPE '\\')")
            params += [like, like, like, like]
        for t in von_terms:
            sql += " AND lower(n.von_adresse) LIKE ? ESCAPE '\\'"
            params.append(_like(t))
        if konto_id:
            sql += " AND k.konto_id=?"
            params.append(konto_id)
        if nur_ungelesen:
            sql += " AND n.gelesen=0"
        sql += " ORDER BY n.rowid DESC LIMIT ?"
        params.append(min(limit, 200))
        return [dict(r) for r in db.get_conn().execute(sql, params).fetchall()]

    # --- MCP-Fläche (read-only, NUR Metadaten) -------------------------------
    # hoechst-App (Vertrag §3): der MCP-Host (Dizzis KI, ggf. Cloud-Boost) darf
    # NIE Volltexte sehen. /api/posteingang trägt ``text`` und ist daher KEINE
    # MCP-Quelle; diese Endpoints liefern bewusst nur Kopfzeilen/Zähler.

    @router.get("/api/mcp/letzte_nachrichten")
    def mcp_letzte_nachrichten(limit: int = 15,
                               user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Neueste Nachrichten als METADATEN (Betreff/Absender/Datum/Ordner/
        gelesen) — OHNE Nachrichten-Text. Für Dizzis Übersicht, nie Inhalte."""
        rows = db.get_conn().execute(
            "SELECT n.betreff, n.von_adresse, n.gesendet_at, n.gelesen, "
            "n.kanal_typ, n.ordner, k.konto_id, k.titel AS konversation "
            "FROM nachrichten n JOIN konversationen k ON k.id = n.konversation_id "
            "WHERE n.user_id=? AND n.deleted_at IS NULL "
            "ORDER BY n.rowid DESC LIMIT ?",
            (user.user_id, min(limit, 100))).fetchall()
        return [dict(r) for r in rows]

    @router.get("/api/mcp/ungelesen")
    def mcp_ungelesen(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Ungelesen-Zähler gesamt + je Konto (Kanal) — reine Metadaten."""
        conn = db.get_conn()
        je = conn.execute(
            "SELECT k.id AS konto_id, k.name, k.art, "
            "(SELECT COUNT(*) FROM nachrichten n "
            " JOIN konversationen kv ON kv.id = n.konversation_id "
            " WHERE kv.konto_id = k.id AND n.gelesen=0 AND n.deleted_at IS NULL) "
            "AS ungelesen "
            "FROM konten k WHERE k.user_id=? AND k.deleted_at IS NULL "
            "ORDER BY k.name", (user.user_id,)).fetchall()
        je_konto = [dict(r) for r in je]
        return {"gesamt": sum(r["ungelesen"] for r in je_konto),
                "je_konto": je_konto}

    def summary() -> list[Kpi]:
        conn = db.get_conn()
        n_k = conn.execute("SELECT COUNT(*) AS n FROM konten "
                           "WHERE deleted_at IS NULL").fetchone()["n"]
        n_n = conn.execute("SELECT COUNT(*) AS n FROM nachrichten "
                           "WHERE deleted_at IS NULL").fetchone()["n"]
        n_kv = conn.execute("SELECT COUNT(*) AS n FROM konversationen "
                            "WHERE deleted_at IS NULL").fetchone()["n"]
        n_ug = conn.execute("SELECT COUNT(*) AS n FROM nachrichten "
                            "WHERE deleted_at IS NULL AND gelesen=0").fetchone()["n"]
        return [Kpi(id="konten", label="Konten", value=n_k),
                Kpi(id="konversationen", label="Konversationen", value=n_kv),
                Kpi(id="nachrichten", label="Nachrichten", value=n_n),
                Kpi(id="ungelesen", label="Ungelesen", value=n_ug)]

    def _triage_gate(user_id: str) -> str | None:
        """Gemeinsames Gate beider Triage-Endpoints: opt-in-Schalter
        ``ki_triage_aktiv``. ``ki_routing`` ist hier IMMER respektiert — die
        Triage spricht ausschließlich das lokale Ollama an, nie eine Cloud
        (auch bei ``lokal_boost`` bliebe sie lokal; bei ``lokal_only`` ist das
        die geforderte Garantie der hoechst-App). Liefert eine Fehlermeldung
        oder None (= erlaubt)."""
        if not db.setting_get(user_id, "ki_triage_aktiv", False):
            return ("KI-Triage ist aus (Einstellung ki_triage_aktiv) — bewusst "
                    "opt-in für die hoechst-App.")
        return None

    @router.post("/api/triage")
    def triage_lauf(user: UserContext = Depends(current_user)):
        """KI-Triage über ALLE Chats (kanalübergreifend) — NUR lokal (Ollama),
        opt-in (K2-Setting). Liefert die gebündelte ``zusammenfassung``/``wichtig``
        UND (Termin-Erkennung, Teil des Triage-Knopfs) ``termine`` = VORSCHLÄGE, die
        NICHT angelegt werden — Anlage erst über die Sammel-Bestätigung
        (``/api/termine/anlegen``, HITL). hoechst-App: Inhalte bleiben lokal."""
        fehler = _triage_gate(user.user_id)
        if fehler:
            return JSONResponse({"error": fehler}, status_code=409)
        from .triage import erkenne_termine, triagiere
        rows = [dict(r) for r in db.get_conn().execute(
            "SELECT betreff, von_adresse, text FROM nachrichten "
            "WHERE user_id=? AND deleted_at IS NULL ORDER BY rowid DESC LIMIT 30",
            (user.user_id,)).fetchall()]
        modell = db.setting_get(user.user_id, "llm_modell", "qwen3:4b")
        ergebnis = triagiere(rows, modell=modell, http_post=http_post)
        # Termin-Erkennung gehört zum Triage-Run (Nutzer-Vision). Best-effort: ein
        # Fehler hier kippt die Zusammenfassung nicht.
        terg = erkenne_termine(rows, heute=now_iso()[:10], modell=modell,
                               http_post=http_post)
        ergebnis["termine"] = terg.get("termine", [])
        if "error" in terg and "error" not in ergebnis:
            ergebnis["termine_hinweis"] = terg["error"]
        db.audit(user.user_id, "ki", "triage_durchgefuehrt",
                 {"nachrichten": len(rows), "ok": "error" not in ergebnis,
                  "termine": len(ergebnis["termine"]),
                  "ki_routing": db.setting_get(user.user_id, "ki_routing",
                                               "lokal_only")})
        return ergebnis

    @router.post("/api/triage/nachrichten")
    def triage_nachrichten(user: UserContext = Depends(current_user)):
        """Per-Nachricht-Triage (Wichtigkeit/Kategorie) — lokal (Ollama),
        gleiches Gate. Die Einträge tragen die Nachrichten-id, damit die UI
        einzelne Mails markieren kann."""
        fehler = _triage_gate(user.user_id)
        if fehler:
            return JSONResponse({"error": fehler}, status_code=409)
        from .triage import klassifiziere
        rows = db.get_conn().execute(
            "SELECT id, betreff, von_adresse, text FROM nachrichten "
            "WHERE user_id=? AND deleted_at IS NULL ORDER BY rowid DESC LIMIT 30",
            (user.user_id,)).fetchall()
        ergebnis = klassifiziere([dict(r) for r in rows],
                                 modell=db.setting_get(user.user_id, "llm_modell",
                                                       "qwen3:4b"),
                                 http_post=http_post)
        db.audit(user.user_id, "ki", "triage_nachrichten",
                 {"nachrichten": len(rows), "ok": "error" not in ergebnis,
                  "ki_routing": db.setting_get(user.user_id, "ki_routing",
                                               "lokal_only")})
        return ergebnis

    @router.post("/api/konversationen/{konv_id}/zusammenfassung")
    def konversation_zusammenfassung(konv_id: str,
                                     user: UserContext = Depends(current_user)):
        """KI-Thread-Zusammenfassung (3-Spalten-Ansicht P1c) — lokal (Ollama),
        gleiches opt-in-Gate. 404 wenn die Konversation unbekannt/leer ist."""
        fehler = _triage_gate(user.user_id)
        if fehler:
            return JSONResponse({"error": fehler}, status_code=409)
        rows = db.get_conn().execute(
            "SELECT von_adresse, betreff, text FROM nachrichten "
            "WHERE konversation_id=? AND user_id=? AND deleted_at IS NULL "
            "ORDER BY rowid ASC LIMIT 30", (konv_id, user.user_id)).fetchall()
        if not rows:
            return JSONResponse({"error": "Konversation unbekannt oder leer"},
                                status_code=404)
        from .triage import zusammenfassung
        erg = zusammenfassung([dict(r) for r in rows],
                              modell=db.setting_get(user.user_id, "llm_modell",
                                                    "qwen3:4b"),
                              http_post=http_post)
        db.audit(user.user_id, "ki", "thread_zusammenfassung",
                 {"konv": konv_id, "ok": "error" not in erg})
        return erg

    @router.post("/api/konversationen/{konv_id}/entwurf")
    def konversation_entwurf(konv_id: str, body: _EntwurfIn = _EntwurfIn(),
                             user: UserContext = Depends(current_user)):
        """KI-Antwort-Entwurf (Compose-Draft P2a) — lokal (Ollama), gleiches
        opt-in-Gate. Liefert NUR Text fürs Eingabefeld; der Versand bleibt HITL
        (``mail_senden``, verifiziert). 404 bei unbekannter/leerer Konversation."""
        fehler = _triage_gate(user.user_id)
        if fehler:
            return JSONResponse({"error": fehler}, status_code=409)
        rows = db.get_conn().execute(
            "SELECT richtung, von_adresse, betreff, text FROM nachrichten "
            "WHERE konversation_id=? AND user_id=? AND deleted_at IS NULL "
            "ORDER BY rowid ASC LIMIT 30", (konv_id, user.user_id)).fetchall()
        if not rows:
            return JSONResponse({"error": "Konversation unbekannt oder leer"},
                                status_code=404)
        from .triage import entwurf
        erg = entwurf([dict(r) for r in rows], hinweis=(body.hinweis or "").strip(),
                      modell=db.setting_get(user.user_id, "llm_modell", "qwen3:4b"),
                      http_post=http_post)
        db.audit(user.user_id, "ki", "antwort_entwurf",
                 {"konv": konv_id, "ok": "error" not in erg})
        return erg

    @router.get("/", include_in_schema=False)
    def startseite(request: Request):
        """Posteingang-UI mit Per-Request-Nonce (CSP voll-strikt, docs/37): die
        inline <script>/<style> bekommen den Nonce injiziert; Inline-Handler sind
        auf DzActions-Delegation umgestellt (kein unsafe-inline mehr nötig)."""
        from appkit.csp import serve_html_mit_csp
        return serve_html_mit_csp(request, Path(__file__).resolve().parents[1]
                                  / "static" / "index.html")

    schema = make_schema(sensitivity=MANIFEST.sensitivity, extra=[
        SettingDef(key="sync_intervall_min", category="daten", type="int",
                   default=15, min=2, max=720,
                   label="Sync-Intervall (Minuten)",
                   description="Getakteter Abruf aller Konten (Automatik)."),
        SettingDef(key="automatik_aktiv", category="daten", type="bool",
                   default=True, label="Automatischer Abruf aktiv"),
        SettingDef(key="standard_ordner", category="daten", type="str",
                   default="INBOX", label="Standard-Ordner"),
        SettingDef(key="ki_triage_aktiv", category="ki", type="bool",
                   default=False, label="KI-Triage (nur lokal)",
                   description="Ollama sortiert/fasst zusammen — Inhalte "
                               "verlassen die Maschine nie (hoechst-App)."),
        SettingDef(key="llm_modell", category="ki", type="str",
                   default="qwen3:4b", label="Ollama-Modell (Triage)"),
        # --- VORBEREITETE Kanal-Slots (Gesetz 5): markiert, NOCH OHNE FUNKTION.
        # Die Zwei-Schienen-Architektur (docs/RECHERCHE.md) ist eine bewusste
        # Architektur-Entscheidung für eine eigene Session (nicht heute Nacht).
        # Diese Schalter existieren schon, damit das Bewusstsein über die
        # geplanten Anschlüsse herrscht; das Backend reagiert (noch) nicht darauf.
        SettingDef(key="webview_schiene_vorbereitet", category="vernetzung",
                   type="bool", default=False,
                   label="Webview-Schiene (Schiene A)",
                   description="VORBEREITET, ohne Funktion (Gesetz 5): WhatsApp "
                               "Web/Instagram per Webview einbetten (Tauri-ready). "
                               "Aktivierung folgt in einer eigenen Session."),
        SettingDef(key="matrix_homeserver", category="vernetzung", type="str",
                   default="", label="Matrix-Homeserver (Schiene B)",
                   description="VORBEREITET, ohne Funktion (Gesetz 5): URL des "
                               "lokalen Matrix-Homeservers (Conduit) für "
                               "mautrix-Bridges. Zugangsdaten gehören in den Tresor."),
        SettingDef(key="bridge_whatsapp_vorbereitet", category="vernetzung",
                   type="bool", default=False, label="Bridge WhatsApp",
                   description="VORBEREITET, ohne Funktion (Gesetz 5): opt-in je "
                               "Dienst mit Risiko-Aufklärung; KEINE Automatisierung."),
        SettingDef(key="bridge_signal_vorbereitet", category="vernetzung",
                   type="bool", default=False, label="Bridge Signal",
                   description="VORBEREITET, ohne Funktion (Gesetz 5): "
                               "mautrix-Signal-Bridge — Aktivierung folgt."),
        SettingDef(key="bridge_telegram_vorbereitet", category="vernetzung",
                   type="bool", default=False, label="Telegram (Bot-API)",
                   description="Echter Bot-API-Adapter (telegram.py): dormant bis Bot-Token "
                               "im Tresor (Config-UI). Lokal via Long-Polling, kein Webhook/Review."),
        # Mode-Schalter der dormanten Kanal-Connectoren (channels.py). Telegram/
        # WhatsApp teilen sich die Bridge-Schalter oben; Instagram/Snapchat haben
        # eigene. Alle VORBEREITET (Gesetz 5): das Backend reagiert (noch) nicht.
        SettingDef(key="kanal_instagram_vorbereitet", category="vernetzung",
                   type="bool", default=False, label="Kanal Instagram",
                   description="VORBEREITET, ohne Funktion (Gesetz 5): Instagram-DMs "
                               "über Meta-/mautrix-Bridge (Schiene B) oder Webview "
                               "(Schiene A) — Live-Pfad folgt."),
        SettingDef(key="kanal_snapchat_vorbereitet", category="vernetzung",
                   type="bool", default=False, label="Kanal Snapchat",
                   description="VORBEREITET, ohne Funktion (Gesetz 5): Snapchat hat "
                               "keine offene Messaging-API ⇒ nur Webview (Schiene A) — "
                               "Live-Pfad folgt."),
        # Meta-Konnektor (docs/38): nicht-geheime IDs/Version. Die GEHEIMNISSE
        # (Access-Token/App-Secret/Verify-Token) liegen im Tresor, NIE hier.
        SettingDef(key="graph_version", category="vernetzung", type="str",
                   default=meta.GRAPH_VERSION, label="Meta Graph-API-Version",
                   description="Version der Graph-API (z. B. v23.0). Meta rollt "
                               "regelmäßig neue Versionen — gegen die Live-Doku gegenchecken."),
        SettingDef(key="whatsapp_phone_number_id", category="vernetzung", type="str",
                   default="", label="WhatsApp phone_number_id",
                   description="ID der WABA-Telefonnummer (kein Secret; der Access-Token "
                               "gehört in den Tresor)."),
        SettingDef(key="whatsapp_template_sprache", category="vernetzung", type="str",
                   default="de", label="WhatsApp Template-Sprache",
                   description="Sprachcode für Template-Nachrichten außerhalb des 24-h-Fensters."),
        SettingDef(key="instagram_user_id", category="vernetzung", type="str",
                   default="", label="Instagram IG-User-ID",
                   description="IG-User-ID der verknüpften Seite (kein Secret; Token im Tresor)."),
        SettingDef(key="absender_screener_vorbereitet", category="sicherheit",
                   type="bool", default=False, label="Absender-Screener",
                   description="VORBEREITET, ohne Funktion (Gesetz 5, HEY-Muster): "
                               "Erst-Absender erst freigeben/blocken, bevor sie in "
                               "den Posteingang dürfen. (Tracking-Pixel-Block ist "
                               "bereits aktiv: Nachrichten werden als Klartext "
                               "dargestellt, keine externen Ressourcen geladen.)"),
        # Jitsi-Video v1 (FUNKTIONAL): Domain des Meet-Servers. Default = die
        # öffentliche Instanz; für volle Privatheit (hoechst-App) eine
        # self-hosted Jitsi-Domain eintragen. Verbindung erst beim Beitreten.
        SettingDef(key="jitsi_domain", category="vernetzung", type="str",
                   default="meet.jit.si", label="Jitsi-Server (Video)",
                   description="Domain der Jitsi-Meet-Instanz für Video-Calls. "
                               "Standard meet.jit.si (öffentlich); self-hosted "
                               "eintragen für volle Privatheit."),
    ])

    app = create_app(MANIFEST, db, summary_fn=summary, routers=[router],
                     version=__version__, schema=schema, actions=actions,
                     ereignis_register=_EREIGNIS_REGISTER,
                     csp_mode="enforce", csp_strikt=True)  # CSP voll-strikt (Nonce); Inline-onclick→data-dz-act
    install_dizzi_id(app, MANIFEST, data_root=root)

    # Per-App-MCP-Gateway (docs/31 §7): im Standalone-Betrieb bietet die App ihr EIGENES
    # read-only MCP-Gate (/mcp) an; im Verbund (Modus 'auto') schaltet es ab, sobald der
    # Core sein zentrales Gateway führt. Read-only (das HITL-Sende-Tool bleibt im stdio-
    # MCP). opt-in/Token/Hochsicher-Gate.
    from . import mcp_tools  # noqa: E402  (Tool-Quelle, lokal importiert)
    from appkit.app_gateway import build_app_gateway  # noqa: E402
    app.include_router(build_app_gateway(
        MANIFEST, db, tools=mcp_tools.MCP_TOOLS,
        base_url=f"http://127.0.0.1:{MANIFEST.port}"))
    ui_kit_dir = ui_kit_path()
    if ui_kit_dir.is_dir():
        class _UiKitFiles(StaticFiles):  # H-1: Cache-Control no-cache -> Revalidierung via ETag
            async def get_response(self, path, scope):
                resp = await super().get_response(path, scope)
                resp.headers["Cache-Control"] = "no-cache"
                return resp
        app.mount("/ui-kit", _UiKitFiles(directory=str(ui_kit_dir)), name="ui-kit")
    vault_ref["vault"] = app.state.vault

    # Mini-Dizzi (Vertrag 1.5): die ECHTE, INBOX-AWARE Komm-KI als App-KI
    # registrieren — „frag Dizz Communication nach …" wird aus dem Posteingang
    # beantwortet (Betreff/Absender/Text + Stand) statt aus dem generischen
    # Fallback. STRIKT LOKAL (Ollama): für die hoechst-App verlassen die Inhalte
    # die Maschine nie — ki_routing lokal_only ist hier baulich garantiert.
    if getattr(app.state, "mini_dizzi", None) is not None:
        def _stand_text() -> str:
            try:
                return "; ".join(f"{k.label}={k.value}" for k in summary())
            except Exception:
                return ""

        def _komm_ki(frage_text: str) -> dict[str, Any]:
            from .triage import frage as _frage
            rows = db.get_conn().execute(
                "SELECT betreff, von_adresse, text FROM nachrichten "
                "WHERE user_id=? AND deleted_at IS NULL "
                "ORDER BY rowid DESC LIMIT 30", (DEFAULT_USER_ID,)).fetchall()
            out = _frage([dict(r) for r in rows], frage_text,
                         modell=db.setting_get(DEFAULT_USER_ID, "llm_modell",
                                               "qwen3:4b"),
                         stand=_stand_text(), http_post=http_post)
            return {"antwort": out.get("antwort", ""),
                    "belege": out.get("belege", [])}

        app.state.mini_dizzi.set_app_ki(_komm_ki)

    if start_timer:
        # Getaktete Automatik (news-Muster): Daemon-Tick über ALLE Konten,
        # respektiert Intervall + Schalter aus den K2-Settings; Fehler je
        # Konto stören weder die anderen noch den Lauf.
        def _tick() -> None:
            time.sleep(20)               # App erst sauber hochfahren lassen
            while True:
                try:
                    if db.setting_get("dizzi", "automatik_aktiv", True):
                        ordner = db.setting_get("dizzi", "standard_ordner", "INBOX")
                        rows = db.get_conn().execute(
                            "SELECT id FROM konten WHERE user_id='dizzi' "
                            "AND deleted_at IS NULL").fetchall()
                        for r in rows:
                            try:
                                sync_lauf("dizzi", r["id"], ordner)
                            except Exception:
                                pass
                except Exception:
                    pass
                minuten = db.setting_get("dizzi", "sync_intervall_min", 15)
                time.sleep(max(2, int(minuten)) * 60)

        threading.Thread(target=_tick, daemon=True,
                         name="kommunikation-automatik").start()
    return app


def app_factory():
    """Uvicorn-Einstieg (``--factory``): importseiteneffektfrei."""
    return build_app()
