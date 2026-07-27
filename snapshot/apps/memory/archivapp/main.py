"""Dizz Memory — Wissensspeicher-Kern (Markdown-Vault + Ordner/Labels + Suche).

Aufgesetzt aus ``templates/refapp`` (App-Vertrag K3). Alles Vertragliche kommt
aus ``appkit`` (Manifest, Stats, Settings, Dizzi-ID-Slot, Datenrechte, Defense,
Mini-Dizzi). Die Domäne steckt an den vom Vertrag vorgesehenen Stellen:
``_SCHEMA`` (Domänen-Tabellen + FTS-Index), die Domänen-Router und ``summary``.

Speicher-Modell (REV-5, docs/11 §5b · Recherche §6):
- **Markdown-Vault** (``vault.py``) = portables, Obsidian-kompatibles, RAG-fähiges
  Datei-Format — der Spiegel, den Dizzis L3-RAG später indexiert.
- **SQLite-Index** (hier) = operative Schicht: Vertrags-Konventionen
  (user_id/Zeitstempel/Soft-Delete) + FTS5-Volltextsuche. Jeder Schreibvorgang
  hält BEIDE synchron; ``POST /api/reindex`` repariert in beide Richtungen.

Start: <venv-python> -m uvicorn archivapp.main:app_factory --factory
       --host 127.0.0.1 --port 8212 --app-dir <archiv-ordner>
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import __version__, bereiche, ki
from .rag import EMBED_MODELL, EMBED_MODELLE, make_rag, rrf_fuse
from .vault import MarkdownVault

from appkit.app import create_app  # noqa: E402  (Pfad-Shim in __init__)
from appkit import ui_kit_path
from appkit.runtime import OllamaRuntime
from appkit.auth import DEFAULT_USER_ID, UserContext, current_user
from appkit.db import Database, default_db_path, new_id, now_iso
from appkit.dizzi_id import install_dizzi_id
from appkit.manifest import AppManifest, McpInfo, Shares
from appkit.mcp import namespaced
from appkit.settings_core import SettingDef, make_schema
from appkit.summary import Kpi
from appkit import extract   # geteilte Datei→Text-Naht (KA-M7): .pdf/.docx/.txt-Ingestion

APP_ID = "memory"   # Netzwerk-/MCP-Namensraum-id (Projektordner bleibt 'archiv', REV-5)

# Ordner-Import: Endungen, die die RAG-Ingestion aufnimmt. .md = Vault-Markdown
# (Frontmatter gemappt); .txt/.pdf/.docx laufen über appkit.extract (KA-M7 C1).
# Alles andere (.exe, Bilder in Stufe 1, …) wird bewusst ignoriert.
_IMPORT_ENDUNGEN = frozenset({".md", ".txt", ".pdf", ".docx"})

# MCP-Tools kurz deklarieren; namespaced() präfixt sie zu memory_<tool>
# (docs/16 §6) — derselbe Präfix, den build_http_mcp im mcp_server automatisch setzt.
_MCP_TOOLS = ["kachel_stats", "letzte_notizen", "ordner", "labels"]

MANIFEST = AppManifest(
    id=APP_ID, name="Wissensspeicher", brand="Dizz Memory", version=__version__,
    port=8212, icon="archive", sensitivity="hoch",   # private Notizen = SENSIBEL → lokal-first
    mcp=McpInfo(command=["<venv-python>", "mcp_server.py"],
                tools=[namespaced(APP_ID, t) for t in _MCP_TOOLS]),
    shares=Shares(summary=True,
                  tools=[namespaced(APP_ID, t) for t in ("kachel_stats", "letzte_notizen")]),
    depends=[],   # News→Memory-Brücke (docs/11 §4) = vorbereiteter Slot, noch nicht live
)

# Domänen-Schema — folgt den Vertrags-Konventionen (UUID/user_id/Zeitstempel/
# Soft-Delete, appkit/db.py). Der Vault ist kanonisch; diese Tabellen sind der
# rebuildbare Index. notizen_fts = FTS5-Volltextindex (eigene Inhalte, per
# notiz_id pflegbar). Vorbereiteter Slot (Gesetz 5): ein Vektor-Index
# (sqlite-vec/bge-m3) als RAG-Brücke zu Dizzi L3 dockt hier additiv an.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS ordner (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    parent_id   TEXT,
    sortierung  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_ordner ON ordner (user_id, parent_id);

CREATE TABLE IF NOT EXISTS labels (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    farbe       TEXT NOT NULL DEFAULT 'cyan',
    -- Label-Art (docs/26 §9.5): 'normal' = frei erstell-/löschbares Nutzer-Label ·
    -- 'herkunft' = system-verwaltetes Quell-App-Label (eigene Optik, eigener Namensraum).
    art         TEXT NOT NULL DEFAULT 'normal',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
    -- Eindeutigkeit getrennt JE Art über partielle Unique-Indizes (s. Migration in
    -- build_app): ein Nutzer-„Money" und ein Herkunfts-„Money" koexistieren.
);

CREATE TABLE IF NOT EXISTS notizen (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    ordner_id     TEXT,
    titel         TEXT NOT NULL,
    inhalt        TEXT NOT NULL DEFAULT '',
    pfad          TEXT,
    sensibel      INTEGER NOT NULL DEFAULT 0,
    quelle        TEXT,                    -- Herkunft (z. B. Mem-source-URL), in Frontmatter gespiegelt
    import_quelle TEXT,                    -- Importer-Kennung (z. B. 'mem.ai' | 'ordner')
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_notizen ON notizen (user_id, ordner_id, updated_at);

CREATE TABLE IF NOT EXISTS notiz_labels (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    notiz_id    TEXT NOT NULL,
    label_id    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    UNIQUE (user_id, notiz_id, label_id)
);
CREATE INDEX IF NOT EXISTS idx_notiz_labels ON notiz_labels (user_id, notiz_id);

-- Import-Dedupe: SHA-256 je importierter Datei (Mehrfach-Import überspringt).
CREATE TABLE IF NOT EXISTS import_quellen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    hash        TEXT NOT NULL,
    notiz_id    TEXT,
    pfad        TEXT,
    quelle      TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    UNIQUE (user_id, hash)
);

CREATE VIRTUAL TABLE IF NOT EXISTS notizen_fts
    USING fts5(notiz_id UNINDEXED, titel, inhalt, labels);

-- Wikilink-Index (P2.4): je [[Ziel]] einer Notiz eine Zeile (Ziel-Titel
-- normalisiert = lower/trim). Beim Speichern gepflegt (Save-Hook _sync_notiz),
-- aus dem Vault rebuildbar (Backfill) — löst den Roh-Text-Scan über ALLE Notizen
-- pro graph/verknuepfungen-Aufruf ab (indizierte Vorwärts- UND Rück-Lese).
CREATE TABLE IF NOT EXISTS notiz_links (
    notiz_id        TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    ziel_titel_norm TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notiz_links_von ON notiz_links (user_id, notiz_id);
CREATE INDEX IF NOT EXISTS idx_notiz_links_nach ON notiz_links (user_id, ziel_titel_norm);

-- Archiv-Regeln (docs/26 §8): je (Quell-App × Strom) steuert der Nutzer, was
-- automatisch ins Archiv wandert. Selbst-registrierend, Default 'manuell'.
CREATE TABLE IF NOT EXISTS archiv_regeln (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    app         TEXT NOT NULL,
    strom       TEXT NOT NULL DEFAULT '',
    modus       TEXT NOT NULL DEFAULT 'manuell',   -- aus|manuell|auto|auto_gefiltert
    filter      TEXT NOT NULL DEFAULT '{}',         -- JSON {tags:[], schluessel:''}
    ziel_ordner TEXT NOT NULL DEFAULT '',
    sensibel    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (user_id, app, strom)
);

-- Notiz-Vorlagen (docs/33): wiederverwendbare Markdown-Gerüste mit Platzhaltern
-- ({{datum}}/{{titel}}/{{zeit}}). ``ordner_default`` = Ordner-PFAD (z. B. "Tagebuch"),
-- beim Anwenden via _ordner_kette aufgelöst/angelegt; leer = lose Notiz.
CREATE TABLE IF NOT EXISTS templates (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    name           TEXT NOT NULL,
    inhalt         TEXT NOT NULL DEFAULT '',
    ordner_default TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    deleted_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_templates ON templates (user_id, updated_at);
"""

# Herkunfts-Label je absendender Netzwerk-App-id (docs/26 §9.1). Jedes über eine
# Querverbindung archivierte Element trägt GARANTIERT genau dieses eine Label —
# sender-unabhängig in Memory vergeben. Unbekannte id ⇒ Titlecase der id.
_HERKUNFT_NAME = {
    "news": "News", "creator": "Creating", "kommunikation": "Communication",
    "management": "Management", "finanzen": "Money", "admin": "Admin",
    "plans": "Plans", "health": "Healthy",
    # Dizz Trading sendet mit seiner Manifest-id "tradingbot" (V11, eigener Stack);
    # "trading" zusätzlich als Robustheits-Alias.
    "tradingbot": "Trading", "trading": "Trading",
}


def _herkunft_anzeige(app: str) -> str:
    app = (app or "").strip()
    return _HERKUNFT_NAME.get(app, app.title() or "App")


_WORT = re.compile(r"\w+", re.UNICODE)

# Obsidian-/Logseq-Wikilinks: [[Titel]] oder [[Titel|Alias]] — Ziel = Teil vor '|'.
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


def _wikilink_ziele(text: str) -> list[str]:
    """Alle [[Ziel]]-Titel eines Textes (Alias abgeschnitten, getrimmt)."""
    return [m.strip() for m in _WIKILINK.findall(text or "") if m.strip()]


def _snippet_text(text: str, n: int = 200) -> str:
    """Kurzer Vorschau-Auszug (Whitespace normalisiert) für die Hybrid-Trefferliste."""
    s = " ".join((text or "").split())
    return s[:n] + ("…" if len(s) > n else "")


# Notiz-Vorlagen-Platzhalter (docs/33): {{name}} mit optionalem Whitespace.
_TEMPLATE_PLATZHALTER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _fuelle_platzhalter(text: str, werte: dict[str, str]) -> str:
    """Ersetzt {{schluessel}} durch ``werte[schluessel]`` (case-insensitiv).
    UNBEKANNTE Platzhalter bleiben unverändert stehen — so sieht der Nutzer im
    Editor, dass dort noch etwas einzutragen ist (kein stilles Verschlucken)."""
    return _TEMPLATE_PLATZHALTER.sub(
        lambda m: werte.get(m.group(1).lower(), m.group(0)), text or "")


def _fts_query(roh: str) -> str | None:
    """Macht freie Nutzereingabe zu einer sicheren FTS5-MATCH-Abfrage:
    Wörter als Prefix-Phrasen, implizit UND-verknüpft. Sonderzeichen fallen
    durch den \\w-Filter weg ⇒ kein Syntax-Crash."""
    toks = _WORT.findall(roh or "")
    if not toks:
        return None
    return " ".join(f'"{t}"*' for t in toks)


# --- Request-Modelle (MODUL-Ebene zwingend — PEP-563-Falle, s. refapp/README) ---
class _NotizIn(BaseModel):
    titel: str = "Neue Notiz"
    inhalt: str = ""
    ordner_id: str | None = None
    labels: list[str] = []          # Label-IDs
    sensibel: bool = False


class _NotizPatch(BaseModel):
    titel: str | None = None
    inhalt: str | None = None
    sensibel: bool | None = None


class _OrdnerIn(BaseModel):
    name: str
    parent_id: str | None = None


class _OrdnerPatch(BaseModel):
    name: str | None = None
    parent_id: str | None = None    # zum Verschieben (None = an die Wurzel)
    parent_setzen: bool = False     # parent_id bewusst ändern (auch auf None)


class _LabelIn(BaseModel):
    name: str
    farbe: str = "cyan"


class _VerschiebenIn(BaseModel):
    ordner_id: str | None = None


class _LabelZuIn(BaseModel):
    label_id: str


class _FrageIn(BaseModel):
    frage: str
    # Gesprächs-Verlauf für den Vault-Chat (P3.1): vorangegangene Turns
    # ``[{rolle:'user'|'ki', text}]``. Optional ⇒ Einzel-Fragen bleiben kompatibel.
    verlauf: list[dict[str, str]] = []


class _ImportIn(BaseModel):
    # Jeder Eintrag: roher Markdown-String ODER {titel,inhalt,ordner,labels}.
    dokumente: list[Any] = []


class _ImportOrdnerIn(BaseModel):
    pfad: str
    rekursiv: bool = True


class _TagesnotizIn(BaseModel):
    datum: str = ""        # leer = heute (lokal); Tests übergeben ein festes Datum.


class _QuervIn(BaseModel):
    # Querverbindungs-Empfang: ein Element einer anderen App archivieren.
    titel: str = ""
    inhalt: str = ""
    quelle: str = ""           # URL/Referenz beim Absender
    app: str = ""              # absendende Netzwerk-App-id (news/creator/…)
    tags: list[str] = []
    ordner: str = ""           # Ziel-Ordner-Pfad (angelegt falls fehlt; Default = app)
    ref: str | None = None     # optionaler externer Idempotenz-Schlüssel
    sensibel: bool = False
    strom: str = ""            # Strom-/Inhalts-Typ (Archiv-Regel je app,strom — docs/26 §8)
    explizit: bool = False     # Nutzer-Zuruf „archivieren" ⇒ schlägt jede Regel


class _RegelIn(BaseModel):
    # Archiv-Regel (docs/26 §8): je (app, strom) steuern, was automatisch archiviert wird.
    app: str
    strom: str = ""
    modus: str = "manuell"              # aus | manuell | auto | auto_gefiltert
    filter: dict[str, Any] = {}          # {tags:[…], schluessel:"…"}
    ziel_ordner: str = ""
    sensibel: bool = False


class _TemplateIn(BaseModel):
    # Notiz-Vorlage (docs/33): Markdown-Gerüst mit Platzhaltern.
    name: str = "Neue Vorlage"
    inhalt: str = ""
    ordner_default: str = ""            # Ordner-Pfad (z. B. "Tagebuch"); leer = lose Notiz


class _TemplatePatch(BaseModel):
    name: str | None = None
    inhalt: str | None = None
    ordner_default: str | None = None


class _AusTemplateIn(BaseModel):
    titel: str = ""                     # füllt {{titel}} + wird Notiz-Titel; leer = Vorlagen-Name
    ordner_id: str | None = None        # optional: überschreibt den Vorlagen-ordner_default


def build_app(data_dir: Path | None = None, http_post=None,
              embed_fn=None, rag_dim: int | None = None, rag_autobuild: bool = True,
              start_import_timer: bool = True, embed_modell: str | None = None,
              use_ollama: bool = False, rerank_fn=None):
    root = data_dir or Path(os.environ.get("DIZZ_MEMORY_DATA_DIR",
                                           r"C:\Dizzik\data"))
    db = Database(default_db_path(APP_ID, data_root=root),
                  extra_schema=_SCHEMA + bereiche.SCHEMA_BEREICHE)
    # Migration (additiv): Bestands-DBs (vor Import-Paket) bekommen die neuen
    # Spalten. CREATE TABLE IF NOT EXISTS legt sie bei Neu-DBs an; ALTER ergänzt
    # Alt-DBs. Idempotent (Duplikat-Spalte ⇒ OperationalError, geschluckt).
    for _spalte in ("quelle", "import_quelle"):
        try:
            db.get_conn().execute(f"ALTER TABLE notizen ADD COLUMN {_spalte} TEXT")
        except sqlite3.OperationalError:
            pass
    # Label-Art (docs/26 §9.5): Boolean ``herkunft`` ⇒ Enum-Spalte ``art`` mit getrennten
    # Namensräumen je Art. Herkunfts-Labels werden eine eigene System-Art, kollidieren NICHT
    # mehr mit gleichnamigen Nutzer-Labels (keine Beförderung). Idempotent.
    _c = db.get_conn()
    try:
        _c.execute("ALTER TABLE labels ADD COLUMN art TEXT NOT NULL DEFAULT 'normal'")
    except sqlite3.OperationalError:
        pass
    try:   # Backfill aus dem Legacy-Boolean — nur solange die Spalte noch existiert (Alt-DBs).
        _c.execute("UPDATE labels SET art='herkunft' WHERE herkunft=1 AND art<>'herkunft'")
    except sqlite3.OperationalError:
        pass
    # Globales UNIQUE(user_id,name) ablösen ⇒ partielle Unique-Indizes je Art. SQLite kann
    # keine Constraint droppen ⇒ einmaliger Tabellen-Rebuild NUR für Alt-DBs. Signal = die
    # noch vorhandene Legacy-Spalte ``herkunft`` (eindeutig + kommentar-unabhängig; ein Test
    # am gespeicherten CREATE-SQL würde fälschlich auf das Wort „Unique" im Schema-Kommentar
    # anspringen). Alt-DBs tragen UNIQUE und ``herkunft`` stets gemeinsam; der Rebuild droppt beides.
    _spalten = [r[1] for r in _c.execute("PRAGMA table_info(labels)").fetchall()]
    if "herkunft" in _spalten:
        _c.executescript(
            "CREATE TABLE labels__neu ("
            " id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,"
            " farbe TEXT NOT NULL DEFAULT 'cyan', art TEXT NOT NULL DEFAULT 'normal',"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT);"
            "INSERT INTO labels__neu (id,user_id,name,farbe,art,created_at,updated_at,deleted_at)"
            " SELECT id,user_id,name,farbe,art,created_at,updated_at,deleted_at FROM labels;"
            "DROP TABLE labels;"
            "ALTER TABLE labels__neu RENAME TO labels;")
    _c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_labels_norm "
               "ON labels(user_id, name) WHERE art='normal'")
    _c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_labels_herk "
               "ON labels(user_id, name) WHERE art='herkunft'")
    _c.commit()
    # Bereichs-Achse (Über-Kategorisierung, Vorbild adminapp.bereiche): bereich_id-FK
    # idempotent an ordner + notizen nachrüsten (PRAGMA-Guard). Tabelle selbst kommt
    # via extra_schema (SCHEMA_BEREICHE).
    bereiche.migriere_bereich_fk(db)
    ber = bereiche.Bereiche(db)
    vault = MarkdownVault(root / "apps" / APP_ID / "vault")
    # RAG/Vektor-Brücke L3 (sqlite-vec). Embedding-Modell ist SWAPPBAR:
    # explizit (``embed_modell``) → Env ``DIZZ_MEMORY_EMBED_MODELL`` → Setting
    # ``embed_modell`` → Default ``bge-m3``. Wirkt beim (gegateten) Neustart; ein
    # Dim-/Modell-Wechsel migriert die vec-Tabelle (rag._migriere_modellwechsel)
    # ⇒ danach Re-Index nötig (Warm-Build/Tool). Ohne ``embed_fn`` (und ohne
    # ``use_ollama``) ist RAG deaktiviert ⇒ Tests laufen Ollama-frei; ``app_factory``
    # setzt ``use_ollama=True`` und bindet das echte Ollama-Embed an das Modell.
    rag_modell = (embed_modell
                  or os.environ.get("DIZZ_MEMORY_EMBED_MODELL", "").strip()
                  or str(db.setting_get(DEFAULT_USER_ID, "embed_modell", "") or "").strip()
                  or EMBED_MODELL)
    if embed_fn is None and use_ollama:
        # docs/62 M6: der Default-Embedder läuft über die LocalRuntime statt der
        # ollama_embed-Modulfunktion — derselbe /api/embed-Endpunkt, appkit-Kanon
        # DIZZ_OLLAMA_URL (url=None). Die embed_fn-Injektion BLEIBT die Naht (Tests
        # ohne use_ollama laufen Ollama-frei); rt.embed schluckt Fehler zu None ⇒
        # RagIndex._embed degradiert wie zuvor auf FTS (None-Safety dort vorhanden).
        _rt = OllamaRuntime()
        embed_fn = lambda texts: _rt.embed(texts, modell=rag_modell)  # noqa: E731
    rag = make_rag(root / "apps" / APP_ID / "rag.sqlite",
                   embed_fn=embed_fn, modell=rag_modell, dim=rag_dim,
                   rerank_fn=rerank_fn)

    # Wikilink-Index-Backfill (P2.4): EINMALIG aus dem Bestand aufbauen (Alt-DBs /
    # erster Start nach dem Feature), danach hält der Save-Hook (_sync_notiz) ihn
    # aktuell. Idempotent über ein Setting-Flag — wie der RAG-Warm-Build.
    if not db.setting_get(DEFAULT_USER_ID, "links_index_gebaut", False):
        _c2 = db.get_conn()
        _c2.execute("DELETE FROM notiz_links")
        for _r in _c2.execute(
                "SELECT id, user_id, inhalt FROM notizen WHERE deleted_at IS NULL").fetchall():
            _ziele = {z.strip().lower() for z in _wikilink_ziele(_r["inhalt"] or "") if z.strip()}
            if _ziele:
                _c2.executemany(
                    "INSERT INTO notiz_links (notiz_id, user_id, ziel_titel_norm) VALUES (?,?,?)",
                    [(_r["id"], _r["user_id"], z) for z in _ziele])
        _c2.commit()
        db.setting_put(DEFAULT_USER_ID, "links_index_gebaut", True)

    # ----- interne Helfer ---------------------------------------------------
    def _ordner_pfad(user_id: str, ordner_id: str | None) -> str:
        """Namens-Pfad eines Ordners (``"A/B"``) durch Hochlaufen der Kette."""
        if not ordner_id:
            return ""
        teile: list[str] = []
        cur = ordner_id
        for _ in range(64):  # Zyklus-/Tiefen-Schutz
            row = db.get_conn().execute(
                "SELECT name, parent_id FROM ordner WHERE id=? AND user_id=?",
                (cur, user_id)).fetchone()
            if row is None:
                break
            teile.append(row["name"])
            if not row["parent_id"]:
                break
            cur = row["parent_id"]
        return "/".join(reversed(teile))

    def _label_namen(user_id: str, notiz_id: str) -> list[str]:
        rows = db.get_conn().execute(
            "SELECT l.name FROM notiz_labels nl JOIN labels l ON l.id=nl.label_id "
            "WHERE nl.user_id=? AND nl.notiz_id=? AND nl.deleted_at IS NULL "
            "AND l.deleted_at IS NULL ORDER BY l.name", (user_id, notiz_id)).fetchall()
        return [r["name"] for r in rows]

    def _labels_of(user_id: str, notiz_id: str) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT l.id, l.name, l.farbe, l.art FROM notiz_labels nl "
            "JOIN labels l ON l.id=nl.label_id "
            "WHERE nl.user_id=? AND nl.notiz_id=? AND nl.deleted_at IS NULL "
            "AND l.deleted_at IS NULL ORDER BY (l.art='herkunft') DESC, l.name",
            (user_id, notiz_id)).fetchall()
        # ``herkunft`` (bool) als abgeleitete Bequemlichkeit zusätzlich zu ``art`` mitliefern.
        return [{**dict(r), "herkunft": r["art"] == "herkunft"} for r in rows]

    def _fts_set(notiz_id: str, titel: str, inhalt: str, labels: list[str]) -> None:
        conn = db.get_conn()
        conn.execute("DELETE FROM notizen_fts WHERE notiz_id=?", (notiz_id,))
        conn.execute(
            "INSERT INTO notizen_fts (notiz_id, titel, inhalt, labels) VALUES (?,?,?,?)",
            (notiz_id, titel, inhalt, " ".join(labels)))

    def _fts_del(notiz_id: str) -> None:
        db.get_conn().execute("DELETE FROM notizen_fts WHERE notiz_id=?", (notiz_id,))

    def _links_set(user_id: str, notiz_id: str, inhalt: str) -> None:
        """Wikilink-Index der Notiz neu setzen (P2.4): alte Kanten weg, dann je
        eindeutigem [[Ziel]] (normalisiert) eine Zeile. Dedupe case-insensitiv —
        wie die Auflösung in graph/verknuepfungen."""
        conn = db.get_conn()
        conn.execute("DELETE FROM notiz_links WHERE notiz_id=?", (notiz_id,))
        ziele = {z.strip().lower() for z in _wikilink_ziele(inhalt or "") if z.strip()}
        if ziele:
            conn.executemany(
                "INSERT INTO notiz_links (notiz_id, user_id, ziel_titel_norm) VALUES (?,?,?)",
                [(notiz_id, user_id, z) for z in ziele])

    def _links_del(notiz_id: str) -> None:
        db.get_conn().execute("DELETE FROM notiz_links WHERE notiz_id=?", (notiz_id,))

    def _rag_weg(notiz_id: str) -> None:
        try:
            rag.remove_notiz(notiz_id)
        except Exception:
            pass

    def _row(user_id: str, notiz_id: str):
        return db.get_conn().execute(
            "SELECT * FROM notizen WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (notiz_id, user_id)).fetchone()

    def _vault_schreiben(user_id: str, row, label_namen: list[str],
                         alt_pfad: str | None) -> str:
        """Schreibt die Markdown-Datei aus dem Index-Stand und gibt den neuen
        relativen Pfad zurück (Spiegel-Synchronisation)."""
        ordner_pfad = _ordner_pfad(user_id, row["ordner_id"])
        rel = vault.rel_path_for(ordner_pfad, row["titel"], row["id"])
        fm = {"id": row["id"], "titel": row["titel"], "ordner": ordner_pfad,
              "labels": label_namen, "sensibel": bool(row["sensibel"]),
              "created_at": row["created_at"], "updated_at": row["updated_at"]}
        spalten = row.keys()
        if "quelle" in spalten and row["quelle"]:
            fm["quelle"] = row["quelle"]
        if "import_quelle" in spalten and row["import_quelle"]:
            fm["import_quelle"] = row["import_quelle"]
        vault.write(user_id, rel, fm, row["inhalt"] or "", alt_pfad=alt_pfad)
        return rel

    def _sync_notiz(user_id: str, notiz_id: str) -> str:
        """Index→Vault+FTS+RAG für genau eine Notiz; gibt den (ggf. neuen) Pfad."""
        row = _row(user_id, notiz_id)
        if row is None:
            return ""
        namen = _label_namen(user_id, notiz_id)
        rel = _vault_schreiben(user_id, row, namen, alt_pfad=row["pfad"])
        if rel != row["pfad"]:
            db.get_conn().execute("UPDATE notizen SET pfad=? WHERE id=?", (rel, notiz_id))
        _fts_set(notiz_id, row["titel"], row["inhalt"] or "", namen)
        _links_set(user_id, notiz_id, row["inhalt"] or "")
        db.get_conn().commit()
        # RAG-Hook (best-effort): re-embeddet die Notiz. Schlägt nie auf den Save
        # durch — ohne Ollama/embed_fn ein No-op (RagIndex.aktiv == False).
        try:
            rag.update_notiz(user_id, notiz_id, row["titel"], row["inhalt"] or "",
                             row["created_at"])
        except Exception:
            pass
        return rel

    def _resync_unter_ordner(user_id: str, ordner_id: str) -> None:
        """Nach Ordner-Umbenennung/Verschiebung: Datei-Pfade aller Notizen im
        Teilbaum nachziehen (Ordner-Namen stecken im Vault-Pfad)."""
        betroffene = _nachfahren(user_id, ordner_id) | {ordner_id}
        rows = db.get_conn().execute(
            "SELECT id, ordner_id FROM notizen WHERE user_id=? AND deleted_at IS NULL",
            (user_id,)).fetchall()
        for r in rows:
            if r["ordner_id"] in betroffene:
                _sync_notiz(user_id, r["id"])

    def _nachfahren(user_id: str, ordner_id: str) -> set[str]:
        """Alle (transitiven) Unter-Ordner-IDs."""
        alle = db.get_conn().execute(
            "SELECT id, parent_id FROM ordner WHERE user_id=? AND deleted_at IS NULL",
            (user_id,)).fetchall()
        kinder: dict[str, list[str]] = {}
        for r in alle:
            kinder.setdefault(r["parent_id"], []).append(r["id"])
        out: set[str] = set()
        stack = list(kinder.get(ordner_id, []))
        while stack:
            k = stack.pop()
            if k in out:
                continue
            out.add(k)
            stack.extend(kinder.get(k, []))
        return out

    def _notiz_dict(user_id: str, row, voll: bool = False) -> dict[str, Any]:
        inhalt = row["inhalt"] or ""
        d = {"id": row["id"], "titel": row["titel"], "ordner_id": row["ordner_id"],
             "sensibel": bool(row["sensibel"]), "created_at": row["created_at"],
             "updated_at": row["updated_at"], "labels": _labels_of(user_id, row["id"])}
        if "bereich_id" in row.keys():
            d["bereich_id"] = row["bereich_id"]
        if voll:
            d["inhalt"] = inhalt
            spalten = row.keys()
            if "quelle" in spalten and row["quelle"]:
                d["quelle"] = row["quelle"]
            if "import_quelle" in spalten and row["import_quelle"]:
                d["import_quelle"] = row["import_quelle"]
                d["import_quelle_anzeige"] = _herkunft_anzeige(row["import_quelle"])
        else:
            d["auszug"] = inhalt.strip().replace("\n", " ")[:160]
        return d

    def _ordner_aktiv(user_id: str, ordner_id: str) -> bool:
        return db.get_conn().execute(
            "SELECT 1 FROM ordner WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (ordner_id, user_id)).fetchone() is not None

    router = APIRouter()

    # ===== Ordner ===========================================================
    @router.get("/api/ordner")
    def ordner_liste(bereich: str | None = None,
                     user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Ordnerliste; optional auf einen ``bereich`` gefiltert (Über-Kategorisierung)."""
        q = ("SELECT o.id, o.name, o.parent_id, o.sortierung, o.bereich_id, "
             "(SELECT COUNT(*) FROM notizen n WHERE n.ordner_id=o.id "
             " AND n.deleted_at IS NULL) AS anzahl "
             "FROM ordner o WHERE o.user_id=? AND o.deleted_at IS NULL")
        params: list[Any] = [user.user_id]
        if bereich:
            q += " AND o.bereich_id=?"; params.append(bereich)
        q += " ORDER BY o.sortierung, o.name"
        return [dict(r) for r in db.get_conn().execute(q, params).fetchall()]

    @router.post("/api/ordner")
    def ordner_anlegen(body: _OrdnerIn,
                       user: UserContext = Depends(current_user)):
        if body.parent_id and not _ordner_aktiv(user.user_id, body.parent_id):
            return JSONResponse({"error": "Eltern-Ordner unbekannt"}, status_code=400)
        ts = now_iso()
        oid = new_id()
        db.get_conn().execute(
            "INSERT INTO ordner (id, user_id, name, parent_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (oid, user.user_id, body.name.strip() or "Ordner", body.parent_id, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "ordner_angelegt", {"id": oid, "name": body.name})
        return {"ok": True, "id": oid}

    @router.put("/api/ordner/{oid}")
    def ordner_aendern(oid: str, body: _OrdnerPatch,
                       user: UserContext = Depends(current_user)):
        if not _ordner_aktiv(user.user_id, oid):
            return JSONResponse({"error": "Ordner unbekannt"}, status_code=404)
        if body.parent_setzen:
            # Schutz vor Schleifen: neuer Eltern darf kein Nachfahre sein.
            if body.parent_id and (body.parent_id == oid
                                   or body.parent_id in _nachfahren(user.user_id, oid)):
                return JSONResponse({"error": "Verschieben würde eine Schleife bilden"},
                                    status_code=400)
            if body.parent_id and not _ordner_aktiv(user.user_id, body.parent_id):
                return JSONResponse({"error": "Ziel-Ordner unbekannt"}, status_code=400)
        sets, params = [], []
        if body.name is not None:
            sets.append("name=?"); params.append(body.name.strip() or "Ordner")
        if body.parent_setzen:
            sets.append("parent_id=?"); params.append(body.parent_id)
        if not sets:
            return {"ok": True, "id": oid}
        sets.append("updated_at=?"); params.append(now_iso())
        params += [oid, user.user_id]
        db.get_conn().execute(
            f"UPDATE ordner SET {', '.join(sets)} WHERE id=? AND user_id=?", params)
        db.get_conn().commit()
        _resync_unter_ordner(user.user_id, oid)  # Pfade im Teilbaum nachziehen
        db.audit(user.user_id, "user", "ordner_geaendert", {"id": oid})
        return {"ok": True, "id": oid}

    @router.delete("/api/ordner/{oid}")
    def ordner_loeschen(oid: str, mit_inhalt: bool = False,
                        user: UserContext = Depends(current_user)):
        """Soft-Delete eines Ordners. ``mit_inhalt=false`` (Default) hängt
        Notizen + Unter-Ordner an die Wurzel um (nichts geht verloren);
        ``mit_inhalt=true`` löscht den ganzen Teilbaum weich mit."""
        if not _ordner_aktiv(user.user_id, oid):
            return JSONResponse({"error": "Ordner unbekannt"}, status_code=404)
        conn = db.get_conn()
        ts = now_iso()
        teilbaum = _nachfahren(user.user_id, oid) | {oid}
        if mit_inhalt:
            for t in teilbaum:
                conn.execute("UPDATE ordner SET deleted_at=? WHERE id=? AND user_id=?",
                             (ts, t, user.user_id))
            notizen = conn.execute(
                f"SELECT id, pfad FROM notizen WHERE user_id=? AND deleted_at IS NULL "
                f"AND ordner_id IN ({','.join('?' * len(teilbaum))})",
                (user.user_id, *teilbaum)).fetchall()
            for n in notizen:
                conn.execute("UPDATE notizen SET deleted_at=? WHERE id=?", (ts, n["id"]))
                _fts_del(n["id"])
                _links_del(n["id"])
                _rag_weg(n["id"])
                if n["pfad"]:
                    vault.trash(user.user_id, n["pfad"])
        else:
            # Nur DIESEN Ordner löschen; Kinder + Notizen an die Wurzel.
            conn.execute("UPDATE ordner SET deleted_at=? WHERE id=? AND user_id=?",
                         (ts, oid, user.user_id))
            conn.execute("UPDATE ordner SET parent_id=NULL, updated_at=? "
                         "WHERE parent_id=? AND user_id=?", (ts, oid, user.user_id))
            verschobene = conn.execute(
                "SELECT id FROM notizen WHERE ordner_id=? AND user_id=? "
                "AND deleted_at IS NULL", (oid, user.user_id)).fetchall()
            conn.execute("UPDATE notizen SET ordner_id=NULL, updated_at=? "
                         "WHERE ordner_id=? AND user_id=?", (ts, oid, user.user_id))
            conn.commit()
            for n in verschobene:
                _sync_notiz(user.user_id, n["id"])
        conn.commit()
        db.audit(user.user_id, "user", "ordner_geloescht",
                 {"id": oid, "mit_inhalt": mit_inhalt})
        return {"ok": True, "id": oid}

    # ===== Labels ===========================================================
    @router.get("/api/labels")
    def labels_liste(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT l.id, l.name, l.farbe, l.art, "
            "(SELECT COUNT(*) FROM notiz_labels nl JOIN notizen n ON n.id=nl.notiz_id "
            " WHERE nl.label_id=l.id AND nl.deleted_at IS NULL "
            " AND n.deleted_at IS NULL) AS anzahl "
            "FROM labels l WHERE l.user_id=? AND l.deleted_at IS NULL "
            "ORDER BY (l.art='herkunft') DESC, l.name", (user.user_id,)).fetchall()
        return [{**dict(r), "herkunft": r["art"] == "herkunft"} for r in rows]

    @router.post("/api/labels")
    def label_anlegen(body: _LabelIn, user: UserContext = Depends(current_user)):
        name = body.name.strip()
        if not name:
            return JSONResponse({"error": "Label-Name fehlt"}, status_code=400)
        # Bestehendes (auch weich gelöschtes) NUTZER-Label reaktivieren statt duplizieren.
        # Auf art='normal' eingegrenzt ⇒ greift nie versehentlich ein Herkunfts-Label (§9.5).
        vorhanden = db.get_conn().execute(
            "SELECT id FROM labels WHERE user_id=? AND name=? AND art='normal'",
            (user.user_id, name)).fetchone()
        ts = now_iso()
        if vorhanden:
            lid = vorhanden["id"]
            db.get_conn().execute(
                "UPDATE labels SET deleted_at=NULL, farbe=?, updated_at=? WHERE id=?",
                (body.farbe, ts, lid))
        else:
            lid = new_id()
            db.get_conn().execute(
                "INSERT INTO labels (id, user_id, name, farbe, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)", (lid, user.user_id, name, body.farbe, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "label_angelegt", {"id": lid, "name": name})
        return {"ok": True, "id": lid}

    @router.delete("/api/labels/{lid}")
    def label_loeschen(lid: str, user: UserContext = Depends(current_user)):
        conn = db.get_conn()
        ts = now_iso()
        conn.execute("UPDATE labels SET deleted_at=? WHERE id=? AND user_id=?",
                     (ts, lid, user.user_id))
        # Zuordnungen lösen + betroffene Notizen neu indexieren.
        betroffen = conn.execute(
            "SELECT DISTINCT notiz_id FROM notiz_labels WHERE label_id=? AND user_id=? "
            "AND deleted_at IS NULL", (lid, user.user_id)).fetchall()
        conn.execute("UPDATE notiz_labels SET deleted_at=? WHERE label_id=? AND user_id=?",
                     (ts, lid, user.user_id))
        conn.commit()
        for r in betroffen:
            _sync_notiz(user.user_id, r["notiz_id"])
        db.audit(user.user_id, "user", "label_geloescht", {"id": lid})
        return {"ok": True, "id": lid}

    # ===== Notizen ==========================================================
    @router.get("/api/notizen")
    def notizen_liste(ordner: str | None = None, label: str | None = None,
                      bereich: str | None = None, limit: int = 50,
                      user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        q = ("SELECT n.* FROM notizen n WHERE n.user_id=? AND n.deleted_at IS NULL")
        params: list[Any] = [user.user_id]
        if label:
            q = ("SELECT n.* FROM notizen n "
                 "JOIN notiz_labels nl ON nl.notiz_id=n.id "
                 "WHERE n.user_id=? AND n.deleted_at IS NULL "
                 "AND nl.label_id=? AND nl.deleted_at IS NULL")
            params.append(label)
        elif ordner == "lose":
            q += " AND n.ordner_id IS NULL"
        elif ordner:
            q += " AND n.ordner_id=?"
            params.append(ordner)
        if bereich:
            # Effektiver Bereich der Notiz: eigenes bereich_id gewinnt, sonst erbt sie
            # vom Ordner (positionale Form von bereiche.effektiv_bereich_where).
            q += (" AND ((n.bereich_id=?) OR (n.bereich_id='' AND n.ordner_id IN "
                  "(SELECT id FROM ordner WHERE user_id=? AND bereich_id=? AND deleted_at IS NULL)))")
            params.extend([bereich, user.user_id, bereich])
        q += " ORDER BY n.updated_at DESC LIMIT ?"
        params.append(min(limit, 500))
        rows = db.get_conn().execute(q, params).fetchall()
        return [_notiz_dict(user.user_id, r) for r in rows]

    @router.get("/api/kategorie")
    def kategorie(ordner: str = "", limit: int = 12, kanon: str = "",
                  user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """A5/V19 (docs/34) — read-only Notizen einer Memory-Kategorie/eines Ordners
        (= ``bereich.memory_ref``) für Dizz Admins Bereichs-Cockpit (über Core-Relay
        ``/querverbindung/memory/kategorie``). ``kanon`` = kanonische Bereichs-ID
        (docs/67 §6, kanon-only ①; Vererbung über ``effektiv_bereich_where``) — ein
        dangling kanon fällt auf ``ordner`` = Ordner-NAME durch (case-insensitiv; die
        Ordner-Struktur ist die natürliche Kategorie-Achse des Vaults). Liefert je
        Notiz Titel/id/Datum + Auszug — bei ``sensibel``-Notizen ist der Auszug
        UNTERDRÜCKT (kein Inhalts-Leak nach außen). Kein Treffer/leerer ``ordner`` ⇒ []."""
        def _auszug(rows) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for r in rows:
                sens = bool(r["sensibel"])
                out.append({
                    "id": r["id"], "titel": r["titel"], "sensibel": sens,
                    "updated_at": r["updated_at"], "created_at": r["created_at"],
                    "auszug": "" if sens else (r["inhalt"] or "").strip().replace("\n", " ")[:160]})
            return out
        conn = db.get_conn()
        lim = max(1, min(limit, 100))
        kanon = (kanon or "").strip()
        if kanon:                                   # ① kanon-only (§6), Vererbung Ordner→Notiz
            aufl = ber.register.aufloesen(user.user_id, kanon=kanon)
            if aufl.bereich_id:
                rows = conn.execute(
                    "SELECT n.id, n.titel, n.sensibel, n.inhalt, n.updated_at, n.created_at "
                    "FROM notizen n WHERE n.user_id=:user AND n.deleted_at IS NULL AND "
                    + bereiche.effektiv_bereich_where("n") +
                    " ORDER BY n.updated_at DESC LIMIT :lim",
                    {"user": user.user_id, "bereich": aufl.bereich_id, "lim": lim}).fetchall()
                return _auszug(rows)
        # ③ Alt-Fallback: Ordner-NAME (Bestand, unverändert)
        name = (ordner or "").strip()
        if not name:
            return []
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM ordner WHERE user_id=? AND deleted_at IS NULL "
            "AND LOWER(name)=LOWER(?)", (user.user_id, name)).fetchall()]
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT id, titel, sensibel, inhalt, updated_at, created_at FROM notizen "
            f"WHERE user_id=? AND deleted_at IS NULL AND ordner_id IN ({ph}) "
            f"ORDER BY updated_at DESC LIMIT ?", (user.user_id, *ids, lim)).fetchall()
        return _auszug(rows)

    @router.get("/api/notizen/{nid}")
    def notiz_holen(nid: str, user: UserContext = Depends(current_user)):
        row = _row(user.user_id, nid)
        if row is None:
            return JSONResponse({"error": "Notiz unbekannt"}, status_code=404)
        return _notiz_dict(user.user_id, row, voll=True)

    @router.get("/api/notizen/{nid}/verknuepfungen")
    def verknuepfungen(nid: str, user: UserContext = Depends(current_user)):
        """Bidirektionale Verknüpfungen einer Notiz (Obsidian/Logseq-Muster):
        - ``ausgehend``: die [[Links]] im eigenen Text, je auf eine Notiz aufgelöst
          (Titel-Match, case-insensitiv) — ``id=None`` ⇒ Ziel existiert noch nicht.
        - ``erwaehnt_in`` (Backlinks): Notizen, die ``[[diesen Titel]]`` enthalten."""
        row = _row(user.user_id, nid)
        if row is None:
            return JSONResponse({"error": "Notiz unbekannt"}, status_code=404)
        conn = db.get_conn()
        # Titel→ID-Auflösung (leicht: nur Titel, KEIN inhalt-Scan mehr).
        nach_titel: dict[str, str] = {}
        for r in conn.execute(
                "SELECT id, titel FROM notizen WHERE user_id=? AND deleted_at IS NULL",
                (user.user_id,)).fetchall():
            nach_titel.setdefault((r["titel"] or "").strip().lower(), r["id"])
        # ausgehend: aus dem EIGENEN Text (erhält Original-Schreibweise + Reihenfolge,
        # billig — eine Notiz), case-insensitiv dedupliziert.
        ausgehend, gesehen = [], set()
        for ziel in _wikilink_ziele(row["inhalt"]):
            key = ziel.lower()
            if key in gesehen:
                continue
            gesehen.add(key)
            ausgehend.append({"titel": ziel, "id": nach_titel.get(key)})
        # erwaehnt_in (Backlinks): INDIZIERT über notiz_links statt Roh-Scan aller
        # Notizen — alle Quellen, die [[diesen Titel]] führen (self ausgeschlossen).
        selbst = (row["titel"] or "").strip().lower()
        erwaehnt = []
        if selbst:
            for r in conn.execute(
                    "SELECT DISTINCT n.id, n.titel FROM notiz_links nl "
                    "JOIN notizen n ON n.id=nl.notiz_id "
                    "WHERE nl.user_id=? AND nl.ziel_titel_norm=? AND nl.notiz_id<>? "
                    "AND n.deleted_at IS NULL", (user.user_id, selbst, nid)).fetchall():
                erwaehnt.append({"id": r["id"], "titel": r["titel"]})
        return {"ausgehend": ausgehend, "erwaehnt_in": erwaehnt}

    @router.get("/api/titel")
    def titel_liste(user: UserContext = Depends(current_user)) -> list[dict[str, str]]:
        """Leichte Titel→ID-Liste aller aktiven Notizen — fürs [[…]]-Autocomplete
        und die Wikilink-Auflösung in der Editor-Vorschau (P2.1)."""
        rows = db.get_conn().execute(
            "SELECT id, titel FROM notizen WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY updated_at DESC", (user.user_id,)).fetchall()
        return [{"id": r["id"], "titel": r["titel"]} for r in rows]

    @router.get("/api/graph")
    def graph(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Wissens-Graph (P2.3): Knoten=Notiz, Kanten=[[Wikilinks]] (aufgelöst,
        gerichtet, dedupliziert). ``grad`` = Knotengrad (für die Knotengröße),
        ``herkunft`` = aus anderer App archiviert (für die Farbachse)."""
        conn = db.get_conn()
        alle = conn.execute(
            "SELECT id, titel FROM notizen WHERE user_id=? AND deleted_at IS NULL",
            (user.user_id,)).fetchall()
        nach_titel: dict[str, str] = {}
        for r in alle:
            nach_titel.setdefault((r["titel"] or "").strip().lower(), r["id"])
        herk = {row["notiz_id"] for row in conn.execute(
            "SELECT DISTINCT nl.notiz_id FROM notiz_labels nl JOIN labels l ON l.id=nl.label_id "
            "WHERE nl.user_id=? AND nl.deleted_at IS NULL AND l.deleted_at IS NULL "
            "AND l.art='herkunft'", (user.user_id,))}
        # Kanten INDIZIERT aus notiz_links (kein inhalt-Scan): je (Quelle, Ziel-Titel)
        # eine Zeile ⇒ auf Ziel-ID auflösen, Selbst-/Dublett-Kanten filtern.
        edges, gesehen, grad = [], set(), {r["id"]: 0 for r in alle}
        for r in conn.execute(
                "SELECT notiz_id, ziel_titel_norm FROM notiz_links WHERE user_id=?",
                (user.user_id,)).fetchall():
            von = r["notiz_id"]
            tid = nach_titel.get(r["ziel_titel_norm"])
            if tid and von in grad and tid != von and (von, tid) not in gesehen:
                gesehen.add((von, tid))
                edges.append({"von": von, "nach": tid})
                grad[von] += 1; grad[tid] += 1
        nodes = [{"id": r["id"], "titel": r["titel"], "grad": grad[r["id"]],
                  "herkunft": r["id"] in herk} for r in alle]
        return {"nodes": nodes, "edges": edges}

    @router.post("/api/tagesnotiz")
    def tagesnotiz(body: _TagesnotizIn, user: UserContext = Depends(current_user)):
        """Tagesnotiz-Landing (P2.2): öffnet/erzeugt die Notiz des Tages (Titel =
        Datum) im Ordner „Tagebuch". Idempotent — derselbe Tag liefert dieselbe
        Notiz (Journal-Muster wie Obsidian/Logseq Daily Notes)."""
        datum = (body.datum or "").strip() or date.today().isoformat()
        oid = _ordner_kette(user.user_id, "Tagebuch")
        conn = db.get_conn()
        row = conn.execute(
            "SELECT id FROM notizen WHERE user_id=? AND titel=? AND ordner_id=? "
            "AND deleted_at IS NULL", (user.user_id, datum, oid)).fetchone()
        if row:
            return {"ok": True, "id": row["id"], "ordner_id": oid, "neu": False, "titel": datum}
        nid = new_id(); ts = now_iso()
        conn.execute(
            "INSERT INTO notizen (id, user_id, ordner_id, titel, inhalt, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)", (nid, user.user_id, oid, datum, f"# {datum}\n\n", ts, ts))
        conn.commit()
        _sync_notiz(user.user_id, nid)
        db.audit(user.user_id, "user", "tagesnotiz_angelegt", {"id": nid, "datum": datum})
        return {"ok": True, "id": nid, "ordner_id": oid, "neu": True, "titel": datum}

    @router.get("/api/resurfacing")
    def resurfacing(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Readwise-artiges Wiederauftauchen (P3.2): „An diesem Tag" (Notizen mit
        gleichem Monat-Tag aus FRÜHEREN Jahren) + ein „Zufallsfund" (eine zufällige
        Notiz, älter als 30 Tage). Beides kompakt für die Start-Fläche, damit altes
        Wissen wieder hochkommt (Spaced-Review-Muster). ``created_at`` ist ISO
        (``YYYY-MM-DD…``) ⇒ Monat-Tag = ``substr(…,6,5)``, Jahr = ``substr(…,1,4)``."""
        heute = date.today()
        conn = db.get_conn()
        # „An diesem Tag": gleicher Monat-Tag, aber ein früheres Jahr (das laufende
        # Jahr ist kein Rückblick). Neueste zuerst, gedeckelt.
        rows = conn.execute(
            "SELECT id, titel, created_at FROM notizen "
            "WHERE user_id=? AND deleted_at IS NULL "
            "AND substr(created_at,6,5)=? AND substr(created_at,1,4) < ? "
            "ORDER BY created_at DESC LIMIT 8",
            (user.user_id, heute.strftime("%m-%d"), heute.strftime("%Y"))).fetchall()
        an_diesem_tag = [{
            "id": r["id"], "titel": r["titel"], "created_at": r["created_at"],
            "jahre_her": heute.year - int(str(r["created_at"])[:4])} for r in rows]
        # „Zufallsfund": eine zufällige Notiz, die älter als 30 Tage ist.
        grenze = (heute - timedelta(days=30)).isoformat()
        z = conn.execute(
            "SELECT id, titel, created_at FROM notizen "
            "WHERE user_id=? AND deleted_at IS NULL AND substr(created_at,1,10) < ? "
            "ORDER BY RANDOM() LIMIT 1", (user.user_id, grenze)).fetchone()
        zufall = ({"id": z["id"], "titel": z["titel"], "created_at": z["created_at"]}
                  if z else None)
        return {"an_diesem_tag": an_diesem_tag, "zufall": zufall}

    @router.post("/api/notizen")
    def notiz_anlegen(body: _NotizIn, user: UserContext = Depends(current_user)):
        if body.ordner_id and not _ordner_aktiv(user.user_id, body.ordner_id):
            return JSONResponse({"error": "Ordner unbekannt"}, status_code=400)
        ts = now_iso()
        nid = new_id()
        conn = db.get_conn()
        standard_sensibel = bool(db.setting_get(user.user_id, "notiz_standard_sensibel", False))
        conn.execute(
            "INSERT INTO notizen (id, user_id, ordner_id, titel, inhalt, sensibel, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (nid, user.user_id, body.ordner_id, body.titel.strip() or "Neue Notiz",
             body.inhalt, int(body.sensibel or standard_sensibel), ts, ts))
        for lid in body.labels:
            if db.get_conn().execute("SELECT 1 FROM labels WHERE id=? AND user_id=? "
                                     "AND deleted_at IS NULL",
                                     (lid, user.user_id)).fetchone():
                conn.execute(
                    "INSERT OR IGNORE INTO notiz_labels (id, user_id, notiz_id, label_id, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (new_id(), user.user_id, nid, lid, ts, ts))
        conn.commit()
        _sync_notiz(user.user_id, nid)
        db.audit(user.user_id, "user", "notiz_angelegt", {"id": nid})
        return {"ok": True, "id": nid}

    @router.put("/api/notizen/{nid}")
    def notiz_aendern(nid: str, body: _NotizPatch,
                      user: UserContext = Depends(current_user)):
        row = _row(user.user_id, nid)
        if row is None:
            return JSONResponse({"error": "Notiz unbekannt"}, status_code=404)
        sets, params = [], []
        if body.titel is not None:
            sets.append("titel=?"); params.append(body.titel.strip() or "Neue Notiz")
        if body.inhalt is not None:
            sets.append("inhalt=?"); params.append(body.inhalt)
        if body.sensibel is not None:
            sets.append("sensibel=?"); params.append(int(body.sensibel))
        if not sets:
            return {"ok": True, "id": nid}
        sets.append("updated_at=?"); params.append(now_iso())
        params += [nid, user.user_id]
        db.get_conn().execute(
            f"UPDATE notizen SET {', '.join(sets)} WHERE id=? AND user_id=?", params)
        db.get_conn().commit()
        _sync_notiz(user.user_id, nid)
        db.audit(user.user_id, "user", "notiz_geaendert", {"id": nid})
        return {"ok": True, "id": nid}

    @router.post("/api/notizen/{nid}/verschieben")
    def notiz_verschieben(nid: str, body: _VerschiebenIn,
                          user: UserContext = Depends(current_user)):
        row = _row(user.user_id, nid)
        if row is None:
            return JSONResponse({"error": "Notiz unbekannt"}, status_code=404)
        if body.ordner_id and not _ordner_aktiv(user.user_id, body.ordner_id):
            return JSONResponse({"error": "Ziel-Ordner unbekannt"}, status_code=400)
        db.get_conn().execute(
            "UPDATE notizen SET ordner_id=?, updated_at=? WHERE id=? AND user_id=?",
            (body.ordner_id, now_iso(), nid, user.user_id))
        db.get_conn().commit()
        _sync_notiz(user.user_id, nid)
        db.audit(user.user_id, "user", "notiz_verschoben",
                 {"id": nid, "ordner_id": body.ordner_id})
        return {"ok": True, "id": nid}

    @router.delete("/api/notizen/{nid}")
    def notiz_loeschen(nid: str, user: UserContext = Depends(current_user)):
        row = _row(user.user_id, nid)
        if row is None:
            return JSONResponse({"error": "Notiz unbekannt"}, status_code=404)
        db.get_conn().execute("UPDATE notizen SET deleted_at=? WHERE id=?",
                              (now_iso(), nid))
        db.get_conn().commit()
        _fts_del(nid)
        _links_del(nid)
        _rag_weg(nid)
        if row["pfad"]:
            vault.trash(user.user_id, row["pfad"])
        db.audit(user.user_id, "user", "notiz_geloescht", {"id": nid})
        return {"ok": True, "id": nid}

    # ===== Labels an Notizen ===============================================
    @router.post("/api/notizen/{nid}/labels")
    def notiz_label_zu(nid: str, body: _LabelZuIn,
                       user: UserContext = Depends(current_user)):
        if _row(user.user_id, nid) is None:
            return JSONResponse({"error": "Notiz unbekannt"}, status_code=404)
        if not db.get_conn().execute("SELECT 1 FROM labels WHERE id=? AND user_id=? "
                                     "AND deleted_at IS NULL",
                                     (body.label_id, user.user_id)).fetchone():
            return JSONResponse({"error": "Label unbekannt"}, status_code=400)
        ts = now_iso()
        db.get_conn().execute(
            "INSERT INTO notiz_labels (id, user_id, notiz_id, label_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT (user_id, notiz_id, label_id) "
            "DO UPDATE SET deleted_at=NULL, updated_at=excluded.updated_at",
            (new_id(), user.user_id, nid, body.label_id, ts, ts))
        db.get_conn().commit()
        _sync_notiz(user.user_id, nid)
        return {"ok": True}

    @router.delete("/api/notizen/{nid}/labels/{lid}")
    def notiz_label_weg(nid: str, lid: str,
                        user: UserContext = Depends(current_user)):
        db.get_conn().execute(
            "UPDATE notiz_labels SET deleted_at=? WHERE user_id=? AND notiz_id=? "
            "AND label_id=? AND deleted_at IS NULL", (now_iso(), user.user_id, nid, lid))
        db.get_conn().commit()
        _sync_notiz(user.user_id, nid)
        return {"ok": True}

    # ===== Notiz-Vorlagen / Templates (docs/33) ============================
    @router.get("/api/templates")
    def templates_liste(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT id, name, ordner_default, created_at, updated_at FROM templates "
            "WHERE user_id=? AND deleted_at IS NULL ORDER BY name", (user.user_id,)).fetchall()
        return [dict(r) for r in rows]

    @router.get("/api/templates/{tid}")
    def template_detail(tid: str, user: UserContext = Depends(current_user)):
        row = db.get_conn().execute(
            "SELECT id, name, inhalt, ordner_default, created_at, updated_at "
            "FROM templates WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (tid, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Vorlage unbekannt"}, status_code=404)
        return dict(row)

    @router.post("/api/templates")
    def template_anlegen(body: _TemplateIn, user: UserContext = Depends(current_user)):
        ts = now_iso(); tid = new_id()
        db.get_conn().execute(
            "INSERT INTO templates (id, user_id, name, inhalt, ordner_default, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (tid, user.user_id, body.name.strip() or "Neue Vorlage", body.inhalt,
             (body.ordner_default or "").strip(), ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "template_angelegt", {"id": tid})
        return {"ok": True, "id": tid}

    @router.put("/api/templates/{tid}")
    def template_aendern(tid: str, body: _TemplatePatch,
                         user: UserContext = Depends(current_user)):
        if db.get_conn().execute("SELECT 1 FROM templates WHERE id=? AND user_id=? "
                                 "AND deleted_at IS NULL",
                                 (tid, user.user_id)).fetchone() is None:
            return JSONResponse({"error": "Vorlage unbekannt"}, status_code=404)
        sets, params = [], []
        if body.name is not None:
            sets.append("name=?"); params.append(body.name.strip() or "Neue Vorlage")
        if body.inhalt is not None:
            sets.append("inhalt=?"); params.append(body.inhalt)
        if body.ordner_default is not None:
            sets.append("ordner_default=?"); params.append(body.ordner_default.strip())
        if not sets:
            return {"ok": True, "id": tid}
        sets.append("updated_at=?"); params.append(now_iso())
        params += [tid, user.user_id]
        db.get_conn().execute(
            f"UPDATE templates SET {', '.join(sets)} WHERE id=? AND user_id=?", params)
        db.get_conn().commit()
        db.audit(user.user_id, "user", "template_geaendert", {"id": tid})
        return {"ok": True, "id": tid}

    @router.delete("/api/templates/{tid}")
    def template_loeschen(tid: str, user: UserContext = Depends(current_user)):
        if db.get_conn().execute("SELECT 1 FROM templates WHERE id=? AND user_id=? "
                                 "AND deleted_at IS NULL",
                                 (tid, user.user_id)).fetchone() is None:
            return JSONResponse({"error": "Vorlage unbekannt"}, status_code=404)
        db.get_conn().execute("UPDATE templates SET deleted_at=? WHERE id=? AND user_id=?",
                              (now_iso(), tid, user.user_id))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "template_geloescht", {"id": tid})
        return {"ok": True, "id": tid}

    @router.post("/api/notizen/aus-template/{tid}")
    def notiz_aus_template(tid: str, body: _AusTemplateIn,
                           user: UserContext = Depends(current_user)):
        """Legt eine neue Notiz aus einer Vorlage an: Platzhalter ({{datum}}→heute,
        {{titel}}→übergebener Titel, {{zeit}}→jetzt HH:MM) werden gefüllt, dann läuft
        der NORMALE Notiz-Schreibpfad (Index + Vault + FTS/RAG via ``_sync_notiz``).
        Ziel-Ordner = ``ordner_id`` (Override) ODER der Vorlagen-``ordner_default``
        (Pfad, via ``_ordner_kette`` angelegt falls fehlt). Unbekannte Platzhalter
        bleiben stehen (der Nutzer füllt sie im Editor)."""
        t = db.get_conn().execute(
            "SELECT * FROM templates WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (tid, user.user_id)).fetchone()
        if t is None:
            return JSONResponse({"error": "Vorlage unbekannt"}, status_code=404)
        titel = body.titel.strip() or t["name"]
        werte = {"datum": date.today().isoformat(), "titel": titel,
                 "zeit": datetime.now().strftime("%H:%M")}
        inhalt = _fuelle_platzhalter(t["inhalt"] or "", werte)
        if body.ordner_id:
            if not _ordner_aktiv(user.user_id, body.ordner_id):
                return JSONResponse({"error": "Ordner unbekannt"}, status_code=400)
            ordner_id = body.ordner_id
        else:
            ordner_id = _ordner_kette(user.user_id, t["ordner_default"] or "")
        ts = now_iso(); nid = new_id()
        standard_sensibel = bool(db.setting_get(user.user_id, "notiz_standard_sensibel", False))
        conn = db.get_conn()
        conn.execute(
            "INSERT INTO notizen (id, user_id, ordner_id, titel, inhalt, sensibel, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (nid, user.user_id, ordner_id, titel, inhalt, int(standard_sensibel), ts, ts))
        conn.commit()
        _sync_notiz(user.user_id, nid)
        db.audit(user.user_id, "user", "notiz_aus_template", {"id": nid, "template": tid})
        return {"ok": True, "id": nid, "ordner_id": ordner_id, "titel": titel}

    # ===== Suche (FTS5, „cited") ============================================
    @router.get("/api/suche")
    def suche(q: str = "", limit: int = 30,
              user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        match = _fts_query(q)
        if match is None:
            return []
        try:
            rows = db.get_conn().execute(
                "SELECT f.notiz_id, "
                "snippet(notizen_fts, 2, '«', '»', '…', 12) AS auszug, "
                "bm25(notizen_fts) AS rang "
                "FROM notizen_fts f "
                "JOIN notizen n ON n.id=f.notiz_id "
                "WHERE notizen_fts MATCH ? AND n.user_id=? AND n.deleted_at IS NULL "
                "ORDER BY rang LIMIT ?", (match, user.user_id, min(limit, 100))).fetchall()
        except Exception:
            return []
        out = []
        for r in rows:
            row = _row(user.user_id, r["notiz_id"])
            if row is None:
                continue
            d = _notiz_dict(user.user_id, row)
            d["auszug"] = "" if d.get("sensibel") else r["auszug"]   # KA-M6: sensibel redigiert
            d["rang"] = r["rang"]
            out.append(d)
        return out

    # ===== Import (KnowledgeImporter-Einstieg: Markdown/Mem) ================
    @router.post("/api/import/markdown")
    def import_markdown(body: _ImportIn, user: UserContext = Depends(current_user)):
        """Importiert Markdown-Dokumente (roh oder mit Frontmatter). Ordner-
        Pfade werden bei Bedarf angelegt, Labels referenziert/erstellt.
        Einstieg für den Mem-(mem.ai)-Import (Live-MCP-Pull = Folgepaket)."""
        erstellt = 0
        for dok in body.dokumente:
            if isinstance(dok, str):
                fm, koerper = MarkdownVault.parse(dok)
                titel = str(fm.get("titel") or _erste_zeile(koerper) or "Importiert")
                ordner_pfad = str(fm.get("ordner") or "")
                labels = fm.get("labels") or []
                sensibel = bool(fm.get("sensibel", False))
            elif isinstance(dok, dict):
                koerper = str(dok.get("inhalt", ""))
                titel = str(dok.get("titel") or _erste_zeile(koerper) or "Importiert")
                ordner_pfad = str(dok.get("ordner") or "")
                labels = dok.get("labels") or []
                sensibel = bool(dok.get("sensibel", False))
            else:
                continue
            oid = _ordner_kette(user.user_id, ordner_pfad)
            lids = [_label_id(user.user_id, str(n)) for n in labels if str(n).strip()]
            nid = new_id(); ts = now_iso()
            conn = db.get_conn()
            conn.execute(
                "INSERT INTO notizen (id, user_id, ordner_id, titel, inhalt, sensibel, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (nid, user.user_id, oid, titel, koerper, int(sensibel), ts, ts))
            for lid in lids:
                conn.execute(
                    "INSERT OR IGNORE INTO notiz_labels (id, user_id, notiz_id, label_id, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (new_id(), user.user_id, nid, lid, ts, ts))
            conn.commit()
            _sync_notiz(user.user_id, nid)
            erstellt += 1
        db.audit(user.user_id, "user", "import_markdown", {"erstellt": erstellt})
        return {"ok": True, "erstellt": erstellt}

    def _ordner_kette(user_id: str, pfad: str) -> str | None:
        """Stellt eine Ordner-Kette ``"A/B/C"`` sicher (anlegen, falls fehlt);
        gibt die ID des letzten Ordners zurück (oder None bei leerem Pfad)."""
        teile = [p.strip() for p in (pfad or "").split("/") if p.strip()]
        parent: str | None = None
        conn = db.get_conn()
        for name in teile:
            row = conn.execute(
                "SELECT id FROM ordner WHERE user_id=? AND name=? AND deleted_at IS NULL "
                "AND ((parent_id IS NULL AND ? IS NULL) OR parent_id=?)",
                (user_id, name, parent, parent)).fetchone()
            if row:
                parent = row["id"]
            else:
                oid = new_id(); ts = now_iso()
                conn.execute("INSERT INTO ordner (id, user_id, name, parent_id, "
                             "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                             (oid, user_id, name, parent, ts, ts))
                parent = oid
        conn.commit()
        return parent

    def _label_id(user_id: str, name: str) -> str:
        # Tag-/Import-Labels sind immer Nutzer-Labels (art='normal') — eigener Namensraum (§9.5).
        conn = db.get_conn()
        row = conn.execute("SELECT id FROM labels WHERE user_id=? AND name=? AND art='normal'",
                           (user_id, name)).fetchone()
        ts = now_iso()
        if row:
            conn.execute("UPDATE labels SET deleted_at=NULL WHERE id=?", (row["id"],))
            conn.commit()
            return row["id"]
        lid = new_id()
        conn.execute("INSERT INTO labels (id, user_id, name, created_at, updated_at) "
                     "VALUES (?,?,?,?,?)", (lid, user_id, name, ts, ts))
        conn.commit()
        return lid

    def _herkunft_label_id(user_id: str, app: str) -> str:
        """Das (einzige) Herkunfts-Label (System-Art) einer Quell-App — eigener
        Namensraum ``art='herkunft'`` (docs/26 §9.5): kollidiert NICHT mit einem
        gleichnamigen Nutzer-Label und befördert keines. Idempotent je Name."""
        name = _herkunft_anzeige(app)
        conn = db.get_conn(); ts = now_iso()
        row = conn.execute(
            "SELECT id FROM labels WHERE user_id=? AND name=? AND art='herkunft'",
            (user_id, name)).fetchone()
        if row:
            conn.execute("UPDATE labels SET deleted_at=NULL, updated_at=? WHERE id=?",
                         (ts, row["id"]))
            conn.commit()
            return row["id"]
        lid = new_id()
        conn.execute("INSERT INTO labels (id, user_id, name, farbe, art, "
                     "created_at, updated_at) VALUES (?,?,?,?, 'herkunft', ?,?)",
                     (lid, user_id, name, "magenta", ts, ts))
        conn.commit()
        return lid

    # ===== Import aus lokalem Ordner (Mem.ai-Export / Markdown-Vault) =======
    def _erlaubte_wurzeln() -> list[Path]:
        """Allow-List der Import-Pfade: der Daten-Root + optionale per Env
        freigegebene Ordner (``DIZZ_MEMORY_IMPORT_DIRS``, semikolon-getrennt).
        Schützt vor Path-Traversal (kein Lesen beliebiger Systemdateien)."""
        wurzeln: list[Path] = []
        try:
            wurzeln.append(root.resolve())
        except Exception:
            pass
        for teil in os.environ.get("DIZZ_MEMORY_IMPORT_DIRS", "").split(";"):
            teil = teil.strip()
            if teil:
                try:
                    wurzeln.append(Path(teil).resolve())
                except Exception:
                    pass
        return wurzeln

    def _pfad_ok(roh: str) -> Path | None:
        """Löst den Pfad auf; gibt ihn NUR zurück, wenn er INNERHALB einer
        freigegebenen Wurzel liegt (sonst None ⇒ 403). ``relative_to`` wirft,
        wenn der Pfad nicht unter der Wurzel liegt — fängt ``..``-Traversal ab."""
        try:
            p = Path(roh).resolve()
        except Exception:
            return None
        for w in _erlaubte_wurzeln():
            try:
                p.relative_to(w)
                return p
            except ValueError:
                continue
        return None

    def _mem_mapping(fm: dict[str, Any]) -> dict[str, Any]:
        """Mappt Frontmatter (inkl. Mem.ai-Felder ``created``/``tags``/``source``)
        auf die Vault-Konventionen (``created_at``/``labels``/``quelle``)."""
        labels = fm.get("labels") or fm.get("tags") or []
        if isinstance(labels, str):
            labels = [labels]
        created = fm.get("created_at") or fm.get("created") or fm.get("date") or ""
        if hasattr(created, "isoformat"):     # YAML parst ISO-Stempel zu date/datetime
            created = created.isoformat()
        quelle = fm.get("quelle") or fm.get("source") or ""
        ist_mem = any(k in fm for k in ("created", "tags", "source"))
        return {
            "titel": str(fm.get("titel") or fm.get("title") or "").strip(),
            "created_at": str(created).strip(),
            "labels": [str(x) for x in labels if str(x).strip()],
            "quelle": str(quelle).strip(),
            "sensibel": bool(fm.get("sensibel", False)),
            "import_quelle": "mem.ai" if ist_mem else "ordner",
        }

    def _import_lauf(user_id: str, p: Path, rekursiv: bool,
                     ausloeser: str = "manuell") -> dict[str, Any]:
        """Importiert Dateien aus dem (bereits validierten) Ordner ``p``: ``.md`` als
        Vault-Markdown (Frontmatter gemappt), ``.txt/.pdf/.docx`` über die geteilte
        ``appkit.extract``-Naht (KA-M7). Unterverzeichnisse → Ordner-Hierarchie;
        Duplikate (SHA-256) übersprungen; eine Datei OHNE extrahierbaren Text wird
        ÜBERSPRUNGEN (``uebersprungen_ohne_text``) statt als stille 0-Chunk-Notiz
        angelegt. Wird vom Endpoint UND der getakteten Automatik genutzt. Läuft ohne
        Ollama (RAG-Indexierung in _sync_notiz best-effort)."""
        conn = db.get_conn()
        importiert = uebersprungen = uebersprungen_ohne_text = 0
        fehler: list[dict[str, str]] = []
        dateien = sorted(d for d in (p.rglob("*") if rekursiv else p.glob("*"))
                         if d.is_file() and d.suffix.lower() in _IMPORT_ENDUNGEN)
        for datei in dateien:
            ext = datei.suffix.lower()
            if ext == ".md":
                try:                             # utf-8-sig: BOM (Windows/Mem.ai) sauber lesen
                    roh = datei.read_text(encoding="utf-8-sig", errors="replace")
                except Exception as e:
                    fehler.append({"datei": datei.name, "fehler": str(e)})
                    continue
                h = hashlib.sha256(roh.encode("utf-8", "replace")).hexdigest()
                if conn.execute("SELECT 1 FROM import_quellen WHERE user_id=? AND hash=? "
                                "AND deleted_at IS NULL", (user_id, h)).fetchone():
                    uebersprungen += 1
                    continue
                fm, koerper = MarkdownVault.parse(roh)
                meta = _mem_mapping(fm)
                titel = meta["titel"] or _erste_zeile(koerper) or datei.stem
                quelle_wert = meta["quelle"] or None
                sensibel = int(meta["sensibel"])
                labels = meta["labels"]
                import_quelle = meta["import_quelle"]
                created_hint = meta["created_at"]
            else:                                # .txt/.pdf/.docx → geteilte Extraktions-Naht
                try:
                    daten = datei.read_bytes()
                except Exception as e:
                    fehler.append({"datei": datei.name, "fehler": str(e)})
                    continue
                h = hashlib.sha256(daten).hexdigest()        # Dedupe auf Roh-Bytes
                if conn.execute("SELECT 1 FROM import_quellen WHERE user_id=? AND hash=? "
                                "AND deleted_at IS NULL", (user_id, h)).fetchone():
                    uebersprungen += 1
                    continue
                koerper, methode = extract.extrahiere_text(daten, ext)
                if methode in ("keiner", "fehler") or not koerper.strip():
                    uebersprungen_ohne_text += 1             # NIE eine stille 0-Chunk-Notiz
                    continue
                try:                                         # Datei-Pfad relativ = Herkunft
                    quelle_wert = datei.relative_to(p).as_posix()
                except ValueError:
                    quelle_wert = datei.name
                titel = datei.name
                sensibel = 0
                labels = []
                import_quelle = "ordner"
                created_hint = ""
            try:                                     # Unterverzeichnis → Ordner-Hierarchie
                rel_dir = datei.parent.relative_to(p).as_posix()
            except ValueError:
                rel_dir = ""
            oid = _ordner_kette(user_id, "" if rel_dir in ("", ".") else rel_dir)
            lids = [_label_id(user_id, n) for n in labels]
            nid = new_id(); ts = now_iso()
            created = created_hint or ts
            conn.execute(
                "INSERT INTO notizen (id, user_id, ordner_id, titel, inhalt, sensibel, "
                "quelle, import_quelle, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (nid, user_id, oid, titel, koerper, sensibel,
                 quelle_wert, import_quelle, created, ts))
            for lid in lids:
                conn.execute(
                    "INSERT OR IGNORE INTO notiz_labels (id, user_id, notiz_id, label_id, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (new_id(), user_id, nid, lid, ts, ts))
            conn.execute(
                "INSERT INTO import_quellen (id, user_id, hash, notiz_id, pfad, quelle, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_id(), user_id, h, nid, str(datei), import_quelle, ts, ts))
            conn.commit()
            _sync_notiz(user_id, nid)
            importiert += 1
        db.audit(user_id, "user", "import_ordner",
                 {"pfad": str(p), "ausloeser": ausloeser, "importiert": importiert,
                  "uebersprungen": uebersprungen,
                  "uebersprungen_ohne_text": uebersprungen_ohne_text, "fehler": len(fehler)})
        return {"ok": True, "importiert": importiert, "uebersprungen": uebersprungen,
                "uebersprungen_ohne_text": uebersprungen_ohne_text, "fehler": fehler}

    @router.post("/api/import/ordner")
    def import_ordner(body: _ImportOrdnerIn,
                      user: UserContext = Depends(current_user)):
        """Massen-Import aus einem LOKALEN Ordner (Mem.ai-Export oder beliebiger
        Vault): ``.md`` als Markdown, ``.txt/.pdf/.docx`` via ``appkit.extract``
        (KA-M7). Der Pfad muss in der Freigabe liegen (kein Traversal)."""
        p = _pfad_ok(body.pfad)
        if p is None:
            return JSONResponse(
                {"error": "Pfad liegt außerhalb der Freigabe oder ist ungültig "
                          "(erlaubt: Daten-Ordner + DIZZ_MEMORY_IMPORT_DIRS)."},
                status_code=403)
        if not p.is_dir():
            return JSONResponse({"error": "Pfad ist kein Verzeichnis"}, status_code=400)
        return _import_lauf(user.user_id, p, body.rekursiv, ausloeser="manuell")

    # --- Getaktete Import-Automatik (Mem-Live-Pull, opt-in) -----------------
    def _auto_import_dirs() -> list[Path]:
        """NUR die explizit per Env freigegebenen externen Ordner — NICHT der
        Daten-Root (sonst würde die Automatik den eigenen Vault re-importieren)."""
        out: list[Path] = []
        for teil in os.environ.get("DIZZ_MEMORY_IMPORT_DIRS", "").split(";"):
            teil = teil.strip()
            if not teil:
                continue
            try:
                p = Path(teil).resolve()
                if p.is_dir():
                    out.append(p)
            except Exception:
                pass
        return out

    def _auto_import_einmal() -> dict[str, Any]:
        """Ein Automatik-Durchlauf über alle freigegebenen externen Ordner —
        nur wenn das K2-Setting ``auto_import_aktiv`` an ist. Idempotent (Dedupe);
        ohne Ollama läuft der Import trotzdem (FTS), RAG kommt beim nächsten Lauf
        bzw. Reindex nach. Vom Daemon-Tick aufgerufen; für Tests via app.state."""
        if not db.setting_get(DEFAULT_USER_ID, "auto_import_aktiv", False):
            return {"aktiv": False, "importiert": 0, "ordner": 0}
        dirs = _auto_import_dirs()
        gesamt = 0
        for d in dirs:
            try:
                gesamt += _import_lauf(DEFAULT_USER_ID, d, True, ausloeser="automatik")["importiert"]
            except Exception:
                pass
        return {"aktiv": True, "importiert": gesamt, "ordner": len(dirs)}

    # ===== Archiv-Regeln (Steuerung auto / auf Zuruf, docs/26 §8) ===========
    _MODI = ("aus", "manuell", "auto", "auto_gefiltert")

    def _regel_dict(row) -> dict[str, Any]:
        try:
            flt = json.loads(row["filter"] or "{}")
        except Exception:
            flt = {}
        return {"app": row["app"], "strom": row["strom"], "modus": row["modus"],
                "filter": flt, "ziel_ordner": row["ziel_ordner"],
                "sensibel": bool(row["sensibel"]), "updated_at": row["updated_at"]}

    def _regel_fuer(user_id: str, app: str, strom: str) -> dict[str, Any]:
        """Regel für (app, strom) — SELBST-REGISTRIEREND: ein neues Paar wird als
        'manuell' angelegt (taucht im Panel auf, flutet nie)."""
        conn = db.get_conn()
        row = conn.execute(
            "SELECT * FROM archiv_regeln WHERE user_id=? AND app=? AND strom=?",
            (user_id, app, strom)).fetchone()
        if row:
            return _regel_dict(row)
        ts = now_iso()
        conn.execute(
            "INSERT OR IGNORE INTO archiv_regeln (id, user_id, app, strom, modus, "
            "filter, ziel_ordner, sensibel, created_at, updated_at) "
            "VALUES (?,?,?,?, 'manuell', '{}', '', 0, ?, ?)",
            (new_id(), user_id, app, strom, ts, ts))
        conn.commit()
        return {"app": app, "strom": strom, "modus": "manuell", "filter": {},
                "ziel_ordner": "", "sensibel": False, "updated_at": ts}

    def _regel_trifft(regel: dict[str, Any], titel: str, inhalt: str,
                      tags: list[str]) -> tuple[bool, str]:
        """Entscheidet nach der Regel, ob archiviert wird (archivieren?, grund)."""
        modus = regel.get("modus", "manuell")
        if modus == "auto":
            return True, "auto"
        if modus == "auto_gefiltert":
            flt = regel.get("filter") or {}
            wunsch = [str(t).strip().lower() for t in (flt.get("tags") or []) if str(t).strip()]
            schluessel = str(flt.get("schluessel") or "").strip().lower()
            hay = {str(t).strip().lower() for t in tags}
            tag_ok = (not wunsch) or bool(hay & set(wunsch))
            wort_ok = (not schluessel) or (schluessel in f"{titel}\n{inhalt}".lower())
            treffer = tag_ok and wort_ok
            return treffer, ("filter-treffer" if treffer else "filter-kein-treffer")
        return False, modus   # 'manuell' | 'aus' | unbekannt ⇒ nicht automatisch

    # ===== Querverbindungs-EMPFANG (Memory-Seite) ==========================
    @router.post("/api/querverbindung/archivieren")
    def querverbindung_archivieren(body: _QuervIn,
                                   user: UserContext = Depends(current_user)):
        """Archiviert ein Element einer ANDEREN Netzwerk-App als Notiz (z. B.
        News-Briefing, Creating-Asset-Metadaten): Titel/Quelle/Tags/Body + Ziel-
        Ordner. **Idempotent** (per ``ref`` ODER Inhalts-Hash) + auditiert.
        Dies ist NUR der Empfangs-Slot — die Gegenseite (News/Creating ruft an)
        und der Übergabe-Vertrag sind World-Chat (s. FÜR-WORLD-CHAT)."""
        titel = (body.titel or "").strip() or _erste_zeile(body.inhalt) or "Eingang"
        conn = db.get_conn()
        schluessel = (body.ref or "").strip() or hashlib.sha256(
            f"{body.app}|{body.quelle}|{titel}|{body.inhalt}".encode("utf-8", "replace")
        ).hexdigest()
        # Idempotenz: bereits empfangen UND Notiz noch aktiv ⇒ nichts Neues anlegen.
        vorhanden = conn.execute(
            "SELECT notiz_id FROM import_quellen WHERE user_id=? AND hash=? "
            "AND deleted_at IS NULL", (user.user_id, schluessel)).fetchone()
        if vorhanden and vorhanden["notiz_id"] and _row(user.user_id, vorhanden["notiz_id"]):
            return {"ok": True, "status": "vorhanden", "id": vorhanden["notiz_id"]}

        # Archiv-Regel (docs/26 §8): explizit schlägt jede Regel; sonst entscheidet
        # die Regel je (app, strom) — Default 'manuell', selbst-registrierend.
        import_quelle = (body.app or "").strip() or "querverbindung"
        regel = _regel_fuer(user.user_id, import_quelle, (body.strom or "").strip())
        if not body.explizit:
            archivieren, grund = _regel_trifft(regel, titel, body.inhalt, list(body.tags))
            if not archivieren:
                db.audit(user.user_id, "system", "querverbindung_uebersprungen",
                         {"app": import_quelle, "strom": body.strom, "grund": grund})
                return {"ok": True, "status": "uebersprungen", "grund": grund,
                        "modus": regel["modus"]}

        oid = _ordner_kette(user.user_id,
                            (body.ordner or regel.get("ziel_ordner") or body.app or "").strip())
        quelle = (body.quelle or "").strip()
        sensibel = bool(body.sensibel or regel.get("sensibel"))
        nid = new_id(); ts = now_iso()
        conn.execute(
            "INSERT INTO notizen (id, user_id, ordner_id, titel, inhalt, sensibel, "
            "quelle, import_quelle, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (nid, user.user_id, oid, titel, body.inhalt, int(sensibel),
             quelle or None, import_quelle, ts, ts))
        for n in body.tags:
            name = str(n).strip()
            if name:
                lid = _label_id(user.user_id, name)
                conn.execute(
                    "INSERT OR IGNORE INTO notiz_labels (id, user_id, notiz_id, label_id, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (new_id(), user.user_id, nid, lid, ts, ts))
        # Herkunfts-Label (docs/26 §9.1): GARANTIERT genau ein Quell-App-Label je
        # Querverbindungs-Archiv — sender-unabhängig, immer (auch ohne Tags).
        hlid = _herkunft_label_id(user.user_id, import_quelle)
        conn.execute(
            "INSERT OR IGNORE INTO notiz_labels (id, user_id, notiz_id, label_id, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (new_id(), user.user_id, nid, hlid, ts, ts))
        # Idempotenz-Beleg; ON CONFLICT deckt das Re-Archivieren nach Notiz-Löschung ab.
        conn.execute(
            "INSERT INTO import_quellen (id, user_id, hash, notiz_id, pfad, quelle, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT (user_id, hash) DO UPDATE SET notiz_id=excluded.notiz_id, "
            "quelle=excluded.quelle, updated_at=excluded.updated_at, deleted_at=NULL",
            (new_id(), user.user_id, schluessel, nid, quelle, import_quelle, ts, ts))
        conn.commit()
        _sync_notiz(user.user_id, nid)
        db.audit(user.user_id, "system", "querverbindung_empfangen",
                 {"app": import_quelle, "id": nid, "titel": titel})
        return {"ok": True, "status": "archiviert", "id": nid, "ordner_id": oid}

    @router.get("/api/archiv-regeln")
    def archiv_regeln_liste(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Alle Archiv-Regeln (Quell-App × Strom) — fürs Steuer-Panel (docs/26 §8)."""
        rows = db.get_conn().execute(
            "SELECT * FROM archiv_regeln WHERE user_id=? ORDER BY app, strom",
            (user.user_id,)).fetchall()
        return [_regel_dict(r) for r in rows]

    @router.put("/api/archiv-regeln")
    def archiv_regel_setzen(body: _RegelIn, user: UserContext = Depends(current_user)):
        """Setzt/aktualisiert die Regel für (app, strom). modus ∈ {aus,manuell,auto,
        auto_gefiltert}; filter nur bei auto_gefiltert (docs/26 §8)."""
        if body.modus not in _MODI:
            return JSONResponse({"error": f"modus muss aus {list(_MODI)} sein"}, status_code=400)
        if not (body.app or "").strip():
            return JSONResponse({"error": "app fehlt"}, status_code=400)
        conn = db.get_conn(); ts = now_iso()
        conn.execute(
            "INSERT INTO archiv_regeln (id, user_id, app, strom, modus, filter, "
            "ziel_ordner, sensibel, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT (user_id, app, strom) DO UPDATE SET modus=excluded.modus, "
            "filter=excluded.filter, ziel_ordner=excluded.ziel_ordner, "
            "sensibel=excluded.sensibel, updated_at=excluded.updated_at",
            (new_id(), user.user_id, body.app.strip(), (body.strom or "").strip(),
             body.modus, json.dumps(body.filter or {}, ensure_ascii=False),
             (body.ziel_ordner or "").strip(), int(bool(body.sensibel)), ts, ts))
        conn.commit()
        db.audit(user.user_id, "user", "archiv_regel_gesetzt",
                 {"app": body.app, "strom": body.strom, "modus": body.modus})
        row = conn.execute(
            "SELECT * FROM archiv_regeln WHERE user_id=? AND app=? AND strom=?",
            (user.user_id, body.app.strip(), (body.strom or "").strip())).fetchone()
        return _regel_dict(row)

    @router.delete("/api/archiv-regeln")
    def archiv_regel_loeschen(app: str, strom: str = "",
                              user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Entfernt die Regel für (app, strom) (Query-Params). Taucht beim nächsten
        Eingang wieder als 'manuell' auf (Selbst-Registrierung)."""
        conn = db.get_conn()
        conn.execute("DELETE FROM archiv_regeln WHERE user_id=? AND app=? AND strom=?",
                     (user.user_id, app, strom))
        conn.commit()
        db.audit(user.user_id, "user", "archiv_regel_geloescht", {"app": app, "strom": strom})
        return {"ok": True}

    def _rag_build(user_id: str) -> dict[str, Any]:
        """Baut den RAG-Vektorindex aus allen aktiven Notizen neu (best-effort)."""
        rows = db.get_conn().execute(
            "SELECT id, user_id, titel, inhalt, created_at FROM notizen "
            "WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall()
        try:
            return rag.build_index([dict(r) for r in rows])
        except Exception as e:
            return {"aktiv": rag.aktiv, "fehler": type(e).__name__}

    # ===== Reindex (Vault ⇄ Index-Reparatur, inkl. RAG) ====================
    @router.post("/api/reindex")
    def reindex(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Baut FTS + RAG neu auf und schreibt alle Notiz-Dateien frisch aus dem
        Index (Index→Vault). Idempotent; nützlich nach Migration/Reparatur."""
        conn = db.get_conn()
        conn.execute("DELETE FROM notizen_fts")
        rows = conn.execute(
            "SELECT id FROM notizen WHERE user_id=? AND deleted_at IS NULL",
            (user.user_id,)).fetchall()
        for r in rows:
            _sync_notiz(user.user_id, r["id"])
        rag_info = _rag_build(user.user_id)
        db.audit(user.user_id, "system", "reindex",
                 {"notizen": len(rows), "rag": rag_info})
        return {"ok": True, "notizen": len(rows), "rag": rag_info}

    # ===== Semantische Suche (RAG/Vektor, ergänzt FTS) =====================
    @router.get("/api/suche/semantisch")
    def suche_semantisch(q: str = "", k: int = 8,
                         user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Bedeutungs-Suche über den Vektorindex (bge-m3). Ergänzt die FTS5-
        Wortsuche `/api/suche`. Liefert je Treffer Notiz-Metadaten + Snippet +
        score. Leer, wenn RAG aus/unbefüllt ist (degradiert sauber)."""
        treffer = []
        for hit in rag.search(user.user_id, q, k=min(k, 50)):
            row = _row(user.user_id, hit["notiz_id"])
            if row is None:
                continue
            d = _notiz_dict(user.user_id, row)
            d["auszug"] = "" if d.get("sensibel") else hit["snippet"]   # KA-M6: sensibel redigiert
            d["score"] = hit["score"]
            d["distanz"] = hit["distanz"]
            treffer.append(d)
        return treffer

    @router.get("/api/suche/hybrid")
    def suche_hybrid(q: str = "", k: int = 8,
                     user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Hybrid-Suche (docs/50 3.1): Vektor(Bedeutung) + FTS5(Wörter) → RRF-Fusion
        (+ optionaler Reranker). Vereint die beiden Einzel-Suchen in EINER Rangfolge;
        degradiert sauber zu reiner FTS, wenn RAG aus/unbefüllt ist."""
        treffer = []
        for nid in _hybrid_ids(user.user_id, q, min(k, 50)):
            row = _row(user.user_id, nid)
            if row is None:
                continue
            d = _notiz_dict(user.user_id, row)
            d["auszug"] = "" if d.get("sensibel") else _snippet_text(row["inhalt"] or "")  # KA-M6
            treffer.append(d)
        return treffer

    @router.get("/api/rag/status")
    def rag_status(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        return rag.status()

    # ===== RAG-Re-Index-Werkzeug (batched · Fortschritt · abbruch-sicher) ====
    # Eigener, schonender Re-Index NUR des Vektorindex (anders als /api/reindex,
    # das zusätzlich FTS + Vault neu schreibt und SYNCHRON läuft). Läuft im
    # Hintergrund-Thread (appkit-Lifespan ist read-only), Notiz-für-Notiz ⇒
    # verkraftet große Vaults und ist jederzeit abbrechbar. Für den Modellwechsel.
    _reindex_state: dict[str, Any] = {
        "laeuft": False, "gesamt": 0, "fertig": 0, "chunks": 0, "fehler": 0,
        "abbruch": False, "abgebrochen": False, "modell": None,
        "gestartet_at": None, "beendet_at": None}
    _reindex_lock = threading.Lock()

    def _rag_reindex_run(user_id: str) -> None:
        try:
            rows = db.get_conn().execute(
                "SELECT id, user_id, titel, inhalt, created_at FROM notizen "
                "WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall()
            _reindex_state["gesamt"] = len(rows)

            def _prog(fertig: int, gesamt: int, chunks: int) -> None:
                _reindex_state.update(fertig=fertig, gesamt=gesamt, chunks=chunks)

            res = rag.reindex([dict(r) for r in rows],
                              should_abort=lambda: _reindex_state["abbruch"],
                              on_progress=_prog)
            _reindex_state.update(chunks=res.get("chunks", 0), fehler=res.get("fehler", 0),
                                  abgebrochen=res.get("abgebrochen", False))
            db.audit(user_id, "system", "rag_reindex",
                     {k: res.get(k) for k in ("notizen", "chunks", "fehler", "abgebrochen")})
        except Exception as e:           # nie den Daemon-Thread crashen lassen
            _reindex_state["fehler"] = _reindex_state.get("fehler", 0) + 1
            db.audit(user_id, "system", "rag_reindex_fehler", {"fehler": type(e).__name__})
        finally:
            _reindex_state.update(laeuft=False, beendet_at=now_iso())

    @router.post("/api/rag/reindex")
    def rag_reindex(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Startet einen Hintergrund-Re-Index aller Notizen (idempotent, abbruch-
        sicher). Antwortet sofort; Fortschritt via ``GET /api/rag/reindex/status``,
        Abbruch via ``POST /api/rag/reindex/abbrechen``. Ein zweiter Start während
        eines laufenden Laufs wird abgewiesen (``laeuft``)."""
        if not rag.aktiv:
            return {"ok": False, "aktiv": False, "grund": "RAG inaktiv (kein Embedder)"}
        with _reindex_lock:
            if _reindex_state["laeuft"]:
                return {"ok": False, "laeuft": True}
            _reindex_state.update(
                laeuft=True, abbruch=False, abgebrochen=False, fertig=0, chunks=0,
                fehler=0, gesamt=0, modell=rag.modell, gestartet_at=now_iso(),
                beendet_at=None)
        threading.Thread(target=_rag_reindex_run, args=(user.user_id,),
                         daemon=True, name="memory-rag-reindex").start()
        db.audit(user.user_id, "system", "rag_reindex_start", {"modell": rag.modell})
        return {"ok": True, "gestartet": True, "modell": rag.modell, "dim": rag.dim}

    @router.get("/api/rag/reindex/status")
    def rag_reindex_status(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        s = dict(_reindex_state)
        g = int(s.get("gesamt") or 0)
        s["prozent"] = (round(100.0 * int(s.get("fertig", 0)) / g, 1) if g
                        else (0.0 if s["laeuft"] else 100.0))
        return s

    @router.post("/api/rag/reindex/abbrechen")
    def rag_reindex_abbrechen(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Fordert den Abbruch eines laufenden Re-Index an (greift vor der nächsten
        Notiz). Bereits indexierte Notizen bleiben gültig (abbruch-sicher)."""
        if _reindex_state["laeuft"]:
            _reindex_state["abbruch"] = True
            db.audit(user.user_id, "system", "rag_reindex_abbruch", {})
            return {"ok": True, "abbruch_angefordert": True}
        return {"ok": True, "laeuft": False}

    # ===== KI-Frage (quellen-gestützt) ======================================
    @router.post("/api/frage")
    def frage(body: _FrageIn, user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Beantwortet eine Frage aus den eigenen Notizen (Retrieval semantisch +
        FTS, lokale KI). Spiegelt /api/ki/frage, liefert aber zusätzlich die
        Quellen — und trägt den **Gesprächs-Verlauf** (P3.1): Folgefragen behalten
        den Kontext, und das Retrieval wird bei knappen Folgefragen um die letzte
        eigene Frage angereichert (terse-query-Problem im Chat)."""
        such = _retrieval_frage(body.frage, body.verlauf)
        out = ki.antwort(_retrieval(user.user_id, such), body.frage,
                         modell=_modell(user.user_id), http_post=http_post,
                         verlauf=body.verlauf)
        db.audit(user.user_id, "ki", "frage_beantwortet",
                 {"ok": "error" not in out, "verlauf": len(body.verlauf)})
        return out

    def _retrieval_frage(frage: str, verlauf: list[dict[str, str]]) -> str:
        """Retrieval-Query für den Chat: knappe Folgefragen („und 2027?") tragen
        zu wenig Signal ⇒ die zuletzt vom Nutzer gestellte Frage voranstellen, damit
        die semantische Suche das Thema findet. Erste Frage = unverändert."""
        for turn in reversed(verlauf or []):
            if turn.get("rolle") == "user" and str(turn.get("text") or "").strip():
                return f"{turn['text'].strip()} {frage}".strip()
        return frage

    def _fts_ids(user_id: str, frage: str, limit: int) -> list[str]:
        """BM25-geordnete Notiz-IDs zur Wortsuche (leere/ungültige Anfrage ⇒ [])."""
        match = _fts_query(frage)
        if not match:
            return []
        try:
            rows = db.get_conn().execute(
                "SELECT n.id FROM notizen_fts f JOIN notizen n ON n.id=f.notiz_id "
                "WHERE notizen_fts MATCH ? AND n.user_id=? AND n.deleted_at IS NULL "
                "ORDER BY bm25(notizen_fts) LIMIT ?", (match, user_id, limit)).fetchall()
            return [r["id"] for r in rows]
        except Exception:
            return []

    def _hybrid_ids(user_id: str, frage: str, n: int) -> list[str]:
        """Hybrid-Retrieval (docs/50 3.1): Vektor(sqlite-vec, Bedeutung) +
        FTS5(BM25, Wörter) → **RRF-Fusion** (rang-basiert, k=60) → optionaler
        Cross-Encoder-Reranker. Robust: fehlt eine Quelle (RAG aus / kein Wort-
        Treffer), trägt die andere allein. Gibt fusionierte Notiz-IDs (max n)."""
        tiefe = max(n * 3, 12)   # je Quelle großzügig holen, dann fusionieren/kürzen
        vektor_ids = [h["notiz_id"] for h in rag.search(user_id, frage, k=tiefe)]
        fts_ids = _fts_ids(user_id, frage, tiefe)
        fusion = [doc for doc, _ in rrf_fuse([vektor_ids, fts_ids])]
        if fusion and rag.hat_reranker:
            kand: list[tuple[str, str]] = []
            for nid in fusion[:tiefe]:
                row = db.get_conn().execute(
                    "SELECT titel, inhalt FROM notizen WHERE id=? AND user_id=? "
                    "AND deleted_at IS NULL", (nid, user_id)).fetchone()
                if row:
                    kand.append((nid, f"{row['titel']}\n\n{row['inhalt']}".strip()))
            fusion = rag.rerank(frage, kand)
        return fusion[:n]

    def _retrieval(user_id: str, frage: str, n: int = 6) -> list[dict[str, Any]]:
        """Top-N relevante Notizen für die KI-Frage über die **Hybrid-Fusion**
        (_hybrid_ids: Vektor + FTS5 → RRF (+ Reranker)); fällt — wenn beide Quellen
        nichts liefern — auf „zuletzt bearbeitet" zurück. Dedupe über die Notiz-ID."""
        treffer: list[dict[str, Any]] = []
        gesehen: set[str] = set()

        def _nimm(nid: str) -> None:
            if nid in gesehen:
                return
            row = db.get_conn().execute(
                "SELECT titel, inhalt FROM notizen WHERE id=? AND user_id=? "
                "AND deleted_at IS NULL", (nid, user_id)).fetchone()
            if row:
                treffer.append({"titel": row["titel"], "inhalt": row["inhalt"]})
                gesehen.add(nid)

        for nid in _hybrid_ids(user_id, frage, n):
            _nimm(nid)

        # Fallback: zuletzt bearbeitet (beide Quellen leer / RAG aus + kein Wort-Treffer)
        if not treffer:
            rows = db.get_conn().execute(
                "SELECT titel, inhalt FROM notizen WHERE user_id=? AND deleted_at IS NULL "
                "ORDER BY updated_at DESC LIMIT ?", (user_id, n)).fetchall()
            treffer = [dict(r) for r in rows]
        return treffer

    def _modell(user_id: str) -> str:
        return str(db.setting_get(user_id, "llm_modell", "qwen3:4b"))

    # ===== Frontend =========================================================
    @router.get("/", include_in_schema=False)
    def startseite(request: Request):
        # CSP voll-strikt: index.html mit Per-Request-Nonce ausliefern (inline <script>/
        # <style> bekommen den Nonce; Inline-onclick wurde auf data-dz-act umgestellt).
        from appkit.csp import serve_html_mit_csp
        return serve_html_mit_csp(request, Path(__file__).resolve().parents[1] / "static" / "index.html")

    _UI_KIT = {  # Whitelist: app-neutrales Vanilla-Bundle (Kopien aus ui-kit, docs/06 §6 + docs/14)
        "tokens.css": "text/css",        # Token-MASTER (K2.2 Achsen + K2.4 Komponenten-Tokens)
        "controls.css": "text/css",      # K2.4 Bedien-Elemente (.dz-check/.dz-select/.dz-stepper/…)
        "collapse.js": "text/javascript",   # K2.4 Verhalten (Collapse + Stepper)
        "spinfling.js": "text/javascript",  # Spin-Physik v4.3 (Panels greifen/schleudern/tauschen)
        "floats.js": "text/javascript",     # schwebende Knöpfe (Settings + Mini-Dizzi)
        "background.css": "text/css",        # D4/D5 Design-Hintergründe (je Design-Theme, tokenbasiert)
        "background.js": "text/javascript",  # D5 Hintergrund-Renderer-Slot
        "ui-builder-tool.html": "text/html",        # UI Builder Tool (vormals Panel-Bautool); Dev-Werkzeug, kein Runtime-Kit
        "ui-builder-tool.js": "text/javascript",    # Tool = html+js zusammen (CSP script-src 'self'); zuvor fehlte der js-Eintrag → 404 auf Memory
        "dzmenu.css": "text/css",            # Rechtsklick-„Dizzi"-Kontextmenü — Styles (netzweit, ex-memory-lokal)
        "dzmenu.js": "text/javascript",      # Rechtsklick-„Dizzi"-Kontextmenü — generische Engine (window.DzMenu)
        "bereichbar.css": "text/css",        # Geteilte Bereichs-Filter-Leiste (DzBereichBar) — Styles (W4)
        "bereichbar.js": "text/javascript",  # Geteilte Bereichs-Filter-Leiste — Engine (window.DzBereichBar, W4)
        "clickwave.css": "text/css",         # Klick-Wellen-Effekt (DzWave) — Styles (netzweit, token-/design-abhängig)
        "clickwave.js": "text/javascript",   # Klick-Wellen-Effekt — Engine (window.DzWave)
        "float_dock.css": "text/css",        # DzHalter Float-Andock-Schale (Spin v4.4) — Styles (netzweit, tokenbasiert)
        "float_dock.js": "text/javascript",  # DzHalter — Engine (window.DzHalter; greift erst nach gegatetem :8212-Neustart)
        "ux-kit.css": "text/css",            # UX-5a: UX-Konsolidierungs-Bausteine (F-1…F-8 + MG-1); hier für den KI-Offenlegungs-Chip
        "ux-kit.js": "text/javascript",      # UX-5a: DzUx-Engine (AI-Act Art. 50(1)-Chip an der Vault-Chat-Fläche)
    }

    @router.get("/ui-kit/{datei}", include_in_schema=False)
    def ui_kit(datei: str):
        """Serviert das tokenbasierte UI-Kit. Das Frontend ist AUSSCHLIESSLICH
        tokenbasiert + nutzt die K2.4-Control-Familie (Design-Pflicht)."""
        media = _UI_KIT.get(datei)
        if media is None:
            return JSONResponse({"error": "unbekannt"}, status_code=404)
        return FileResponse(ui_kit_path() / datei,
                            media_type=media, headers={"Cache-Control": "no-cache"})

    # ===== Dashboard-Kachel =================================================
    def summary() -> list[Kpi]:
        conn = db.get_conn()
        n_notizen = conn.execute(
            "SELECT COUNT(*) AS n FROM notizen WHERE deleted_at IS NULL").fetchone()["n"]
        n_ordner = conn.execute(
            "SELECT COUNT(*) AS n FROM ordner WHERE deleted_at IS NULL").fetchone()["n"]
        # H-10(a): nur kuratierte NUTZER-Labels zählen. Die System-Herkunfts-Labels
        # (art='herkunft', je Quell-App genau eines, §9.5) sind kein Nutzer-„Label" und
        # würden die KPI sonst verfälschen (mit jeder neuen Querverbindung +1).
        n_labels = conn.execute(
            "SELECT COUNT(*) AS n FROM labels WHERE deleted_at IS NULL AND art='normal'").fetchone()["n"]
        letzte = conn.execute(
            "SELECT MAX(updated_at) AS t FROM notizen WHERE deleted_at IS NULL").fetchone()["t"]
        return [Kpi(id="notizen", label="Notizen", value=n_notizen, unit="Stk"),
                Kpi(id="ordner", label="Ordner", value=n_ordner),
                Kpi(id="labels", label="Labels", value=n_labels),
                Kpi(id="letzte", label="Zuletzt", value=letzte or "—")]

    schema = make_schema(sensitivity=MANIFEST.sensitivity, extra=[
        SettingDef(key="llm_modell", category="ki", type="str", default="qwen3:4b",
                   label="Ollama-Modell (Notiz-KI)",
                   description="Lokales Modell für quellen-gestützte Antworten (0 €)."),
        SettingDef(key="embed_modell", category="ki", type="choice",
                   default=EMBED_MODELL, choices=list(EMBED_MODELLE),
                   label="Embedding-Modell (semantische Suche)",
                   description="Lokales Ollama-Modell für die Bedeutungs-Suche (RAG/L3). "
                               "Wechsel wirkt nach Neustart + Re-Index (Vektoren werden neu "
                               "berechnet; Dimension wird automatisch migriert)."),
        SettingDef(key="notiz_standard_sensibel", category="sicherheit", type="bool",
                   default=False, label="Neue Notizen sind sensibel",
                   description="Markiert neue Notizen als sensibel (lokal-first)."),
        SettingDef(key="auto_import_aktiv", category="daten", type="bool", default=False,
                   label="Automatischer Ordner-Import",
                   description="Beobachtet die freigegebenen Ordner (Env DIZZ_MEMORY_IMPORT_DIRS) "
                               "getaktet und importiert neue .md (SHA-256-Dedupe). Default AUS."),
        SettingDef(key="auto_import_intervall_min", category="daten", type="int",
                   default=30, min=5, max=1440, label="Import-Intervall (Minuten)",
                   description="Takt der Import-Automatik, wenn aktiv."),
    ])

    def _raeume_user_artefakte(user_id: str) -> None:
        """on_delete-Hook (appkit, H-7, docs/25): nach der DB-Soft-Delete-Kaskade
        räumt Memory seine EXTERNEN Artefakte des Nutzers — den RAG-Vektorindex +
        das Vault-Markdown-Verzeichnis (DSGVO „weg = weg"; die DB-Konvention allein
        lässt beide liegen). RAG zuerst (guarded, sqlite-vec kann fehlen), dann der
        Vault (rmtree, fehlertolerant)."""
        try:
            rag.remove_user(user_id)
        except Exception:
            pass  # RAG ist best-effort; die Vault-Räumung muss trotzdem laufen
        vault.purge_user(user_id)
        # archiv_regeln UND notiz_links haben KEIN deleted_at ⇒ soft_delete_user
        # überspringt beide; hier hart entfernen (weg = weg). notiz_links = der
        # Wikilink-Graph des Nutzers (RA-3, 28.06.): ``ziel_titel_norm`` sind die vom
        # Nutzer verlinkten Notiz-Titel = personenbezogen ⇒ dürfen nicht überleben.
        conn = db.get_conn()
        conn.execute("DELETE FROM archiv_regeln WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM notiz_links WHERE user_id=?", (user_id,))
        conn.commit()

    app = create_app(MANIFEST, db, summary_fn=summary, routers=[router, ber.build_router()],
                     version=__version__, schema=schema,
                     on_delete=_raeume_user_artefakte,
                     csp_mode="enforce", csp_strikt=True)  # CSP voll-strikt (Nonce); Inline-onclick→data-dz-act
    install_dizzi_id(app, MANIFEST, data_root=root)

    # Per-App-MCP-Gateway (docs/31 §7): im Standalone-Betrieb bietet Dizz Memory sein
    # EIGENES read-only MCP-Gate (/mcp) an (inkl. parametrischer Such-Tools); im Verbund
    # (Modus 'auto') schaltet es ab, sobald der Core sein zentrales Gateway führt.
    from . import mcp_tools  # noqa: E402  (Tool-Quelle, lokal importiert)
    from appkit.app_gateway import build_app_gateway  # noqa: E402
    app.include_router(build_app_gateway(
        MANIFEST, db, tools=mcp_tools.MCP_TOOLS,
        query_tools=mcp_tools.MCP_QUERY_TOOLS,
        base_url=f"http://127.0.0.1:{MANIFEST.port}"))
    app.state.db = db                # type: ignore[attr-defined]  (Tests: created_at-Setup)
    app.state.bereiche = ber         # type: ignore[attr-defined]  (Tests/Bereiche)
    app.state.vault = vault          # type: ignore[attr-defined]  (Tests/Reindex)
    app.state.rag = rag              # type: ignore[attr-defined]  (Tests/Status)
    app.state.auto_import = _auto_import_einmal  # type: ignore[attr-defined]  (Tests/Daemon)

    # Mini-Dizzi (Vertrag 1.5): die ECHTE Memory-KI als App-KI registrieren, damit
    # „frag Dizz Memory nach …" quellen-gestützt aus den Notizen antwortet.
    if getattr(app.state, "mini_dizzi", None) is not None:
        def _memory_ki(frage_text: str) -> dict[str, Any]:
            out = ki.antwort(_retrieval(DEFAULT_USER_ID, frage_text), frage_text,
                             modell=_modell(DEFAULT_USER_ID), http_post=http_post)
            return {"antwort": out.get("antwort", "")}
        app.state.mini_dizzi.set_app_ki(_memory_ki)

    # RAG-Initial-Build beim App-Start. appkit besitzt den Lifespan (read-only),
    # darum als Daemon-Thread (Muster News-_tick): einmalig, best-effort, baut nur,
    # wenn der Index leer ist und Ollama erreichbar — stört den Start nie.
    if rag.aktiv and rag_autobuild:
        def _rag_warm() -> None:
            time.sleep(8)            # App erst sauber hochfahren lassen
            try:
                if rag.status().get("chunks", 0) == 0:
                    _rag_build(DEFAULT_USER_ID)
            except Exception:
                pass
        threading.Thread(target=_rag_warm, daemon=True, name="memory-rag-warm").start()

    # Mem-Live-Pull: getaktete Import-Automatik (Muster News-_tick). Opt-in via
    # Setting auto_import_aktiv (Default AUS) ⇒ tut nichts, solange der Nutzer es
    # nicht einschaltet. appkit-Lifespan read-only ⇒ Daemon-Thread.
    if start_import_timer:
        def _import_tick() -> None:
            time.sleep(20)           # App erst sauber hochfahren lassen
            while True:
                try:
                    _auto_import_einmal()
                except Exception:
                    pass
                minuten = db.setting_get(DEFAULT_USER_ID, "auto_import_intervall_min", 30)
                time.sleep(max(5, int(minuten)) * 60)
        threading.Thread(target=_import_tick, daemon=True, name="memory-auto-import").start()

    return app


def _erste_zeile(text: str) -> str:
    for z in (text or "").splitlines():
        z = z.strip().lstrip("#").strip()
        if z:
            return z[:80]
    return ""


def app_factory():
    """Uvicorn-Einstieg (``--factory``): importseiteneffektfrei. Prod aktiviert
    die RAG-Brücke mit dem echten lokalen Ollama-Embed; das Modell ist swappbar
    (Env ``DIZZ_MEMORY_EMBED_MODELL`` / Setting ``embed_modell`` / Default bge-m3)."""
    return build_app(use_ollama=True)
