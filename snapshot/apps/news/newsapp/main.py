"""Dizz News — Feed-Kern (RSS/Atom, 0 €) + getaktete Automatik (Fragerunde 3).

Architektur (Dossier docs/RECHERCHE.md):
- Quellen sind KURATIERT (Fixquellen-Prinzip des News-Skills, kein Rauschen);
  Sektoren-Feld von Anfang an (Geopolitik, Finanzen, KI, …).
- Abruf über httpx (Timeout-kontrolliert) → feedparser; Dedupe über Link.
- **Getaktete Automatik**: Daemon-Timer ruft alle Quellen im eingestellten
  Intervall ab (K2-Setting ``abruf_intervall_min``); zusätzlich manuell
  über ``POST /api/abrufen``. Die KI-Ebene (Zusammenfassen/Fragen) kommt als
  nächste Stufe über Dizzi/Ollama dazu (lokal-first).

Start: <venv-python> -m uvicorn newsapp.main:app_factory --factory
       --host 127.0.0.1 --port 8216 --app-dir <news-ordner>
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import email.utils
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import json as _json

from . import __version__, cluster, extract, ki, mcp_tools, report, watchlist

from appkit.app import create_app  # noqa: E402  (Pfad-Shim in __init__)
from appkit import ui_kit_path
from appkit.app_gateway import build_app_gateway  # noqa: E402
from appkit.auth import DEFAULT_USER_ID, UserContext, current_user
from appkit.db import Database, default_db_path, new_id, now_iso
from appkit.dizzi_id import install_dizzi_id
from appkit.manifest import AppManifest, McpInfo, Shares
from appkit.settings_core import SettingDef, make_schema
from appkit.summary import Kpi

APP_ID = "news"

MANIFEST = AppManifest(
    id=APP_ID, name="News Compact", brand="Dizz News", version=__version__,
    port=8216, icon="globe", sensitivity="normal",
    mcp=McpInfo(command=["<venv-python>", "mcp_server.py"],
                tools=["kachel_stats", "letzte_artikel", "quellen"]),
    shares=Shares(summary=True, tools=["kachel_stats", "letzte_artikel"]),
    depends=[],
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS quellen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    url         TEXT NOT NULL,
    sektor      TEXT NOT NULL DEFAULT 'allgemein',
    letzter_ok      TEXT,                      -- Pro-Quelle-Gesundheit (Backlog docs/33)
    letzter_fehler  TEXT,
    fehler_zaehler  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE TABLE IF NOT EXISTS artikel (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    quelle_id    TEXT NOT NULL,
    titel        TEXT NOT NULL,
    link         TEXT NOT NULL,
    zusammenfassung TEXT,
    volltext        TEXT,                   -- Readability-Haupttext (docs/33 §news)
    volltext_status TEXT,                   -- NULL=offen | ok | leer | fehler
    published_at TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT,
    UNIQUE (user_id, link)
);
CREATE INDEX IF NOT EXISTS idx_artikel ON artikel (user_id, created_at);
CREATE TABLE IF NOT EXISTS reports (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    sektoren    TEXT NOT NULL,           -- JSON-Liste der gewählten Sektor-IDs
    tiefe       TEXT NOT NULL,           -- tief | mittel | kompakt
    inhalt      TEXT NOT NULL,           -- JSON: Abschnitte je Sektor
    ausloeser   TEXT NOT NULL DEFAULT 'manuell',  -- manuell | automatik
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
-- Watchlist (Phase 3): lebender Themen-Ordner. ``thema`` = freie Beschreibung,
-- gegen die neue Artikel beim Abruf thematisch gematcht werden (watchlist.py).
-- ``memory_sync``/``memory_ordner`` sind für Phase 4 (Watchlist→Memory) vorbereitet.
CREATE TABLE IF NOT EXISTS watchlists (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    name          TEXT NOT NULL,
    thema         TEXT NOT NULL DEFAULT '',
    embedding     TEXT,                  -- optionaler Embedding-Cache (Default ungenutzt)
    memory_sync   INTEGER NOT NULL DEFAULT 0,   -- Phase 4
    memory_ordner TEXT,                  -- Phase 4
    gesehen_at    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE TABLE IF NOT EXISTS watchlist_artikel (
    id            TEXT PRIMARY KEY,
    watchlist_id  TEXT NOT NULL,
    artikel_id    TEXT,
    titel         TEXT NOT NULL,
    link          TEXT NOT NULL,
    quelle        TEXT,
    sektor        TEXT,
    published_at  TEXT,
    zusammenfassung TEXT,                -- stylische KI-Kurzfassung (Fallback Feed-Summary)
    score         REAL,
    neu           INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    UNIQUE (watchlist_id, link)
);
"""

# Seriöse Start-Quellen (kuratiert, Fixquellen-Prinzip des News-Skills);
# Nutzer kann jederzeit ergänzen/löschen. Die Quell-Sektoren speisen die
# Report-Sektoren über report.QUELLEN_MAP.
SEED_QUELLEN = [
    ("tagesschau", "https://www.tagesschau.de/index~rss2.xml", "allgemein"),
    ("heise", "https://www.heise.de/rss/heise-atom.xml", "tech"),
    ("Guardian World", "https://www.theguardian.com/world/rss", "geopolitik"),
    ("tagesschau Wirtschaft",
     "https://www.tagesschau.de/wirtschaft/index~rss2.xml", "wirtschaft"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "krypto"),
    # Ausbau 15.06. (sehr seriöse Fixquellen, bewährte URL-Muster der Bestands-Seeds):
    ("tagesschau Ausland",
     "https://www.tagesschau.de/ausland/index~rss2.xml", "geopolitik"),
    ("tagesschau Wissen",
     "https://www.tagesschau.de/wissen/index~rss2.xml", "allgemein"),
    ("Guardian Business", "https://www.theguardian.com/business/rss", "wirtschaft"),
]


_FEED_MAX_BYTES = 5_000_000   # Feed-Abruf hart deckeln (DoS-/Speicher-Schutz)


def _lade_feed(url: str) -> list[dict[str, Any]]:
    """Holt + parst einen Feed (httpx-Timeout, dann feedparser).
    In Tests gemockt. Liefert [{titel, link, zusammenfassung, published}].

    Robustheit (Ausbau 15.06.): getrennte Connect-/Read-Timeouts (eine langsame
    Quelle blockiert nie den ganzen Lauf — fetch_all zählt Fehler je Quelle und
    macht weiter) + expliziter User-Agent (manche Feeds [u. a. Guardian] weisen
    den Default-Client-UA ab). Der eigentliche Fehler-Schirm sitzt in fetch_all
    (try/except je Quelle, kein harter Abbruch).

    SSRF-Härtung (NR-1, 28.06.): Feed-URLs sind nutzer-/OPML-geliefert; ein arglos
    gefolgter 302 darf NICHT auf interne Ziele (127.0.0.1:8200, 169.254.169.254,
    ...) zeigen. Wie ``extract._hole_html`` werden Redirects daher MANUELL verfolgt
    und JEDER Hop über ``extract.pin_ziel`` revalidiert UND auf die geprüfte IP
    gepinnt (httpx folgt sonst intern ungeprüft; der Pin schließt zusätzlich das
    DNS-Rebinding-Fenster — kein zweiter Lookup beim Abruf) — vorher war NUR die
    Volltext-Extraktion abgesichert, der Feed-Abruf nicht. Größe hart gedeckelt."""
    import feedparser
    import httpx
    from urllib.parse import urljoin

    ziel = url
    content = b""
    with httpx.Client(follow_redirects=False,
                      timeout=httpx.Timeout(10.0, connect=5.0),
                      headers={"User-Agent": "DizzNews/1.0 (+localhost; RSS-Leser)"}) as client:
        for _hop in range(4):                 # bis zu 3 Redirects, jeder neu geprüft + gepinnt
            pin = extract.pin_ziel(ziel)      # SSRF-Gate + IP-Pin gegen DNS-Rebinding
            if pin is None:
                raise ValueError(f"SSRF-Gate: nicht-oeffentliche Feed-URL {ziel!r}")
            pin_url, pin_headers, pin_ext = pin
            with client.stream("GET", pin_url, headers=pin_headers, extensions=pin_ext) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location")
                    if not loc:
                        raise ValueError(f"Redirect ohne Location: {ziel!r}")
                    ziel = urljoin(ziel, loc)
                    continue
                r.raise_for_status()
                total, buf = 0, []
                for chunk in r.iter_bytes():
                    total += len(chunk)
                    if total > _FEED_MAX_BYTES:
                        break
                    buf.append(chunk)
                content = b"".join(buf)
                break
        else:
            raise ValueError(f"Zu viele Redirects fuer Feed: {url!r}")
    parsed = feedparser.parse(content)
    out = []
    for e in parsed.entries[:50]:
        out.append({
            "titel": getattr(e, "title", "(ohne Titel)"),
            "link": getattr(e, "link", ""),
            "zusammenfassung": getattr(e, "summary", "")[:600],
            "published": getattr(e, "published", None) or getattr(e, "updated", None),
        })
    return out


class _QuelleIn(BaseModel):
    name: str
    url: str
    sektor: str = "allgemein"


class _FrageIn(BaseModel):
    # Modul-Ebene zwingend (PEP-563-Falle, s. templates/refapp/README).
    frage: str


class _ReportIn(BaseModel):
    sektoren: list[str] = []             # leer = ALLE (Voll-Report)


class _HighlightIn(BaseModel):
    # Markierte Lesestelle → Memory (Readwise-Muster, P2). Modul-Ebene zwingend (PEP-563).
    text: str
    quelle: str = ""
    titel: str = ""


class _WatchlistIn(BaseModel):
    # Neue Watchlist (Phase 3): Name + freies Thema (Beschreibung fürs Matching).
    name: str
    thema: str = ""


class _WatchlistPatch(BaseModel):
    name: str | None = None
    thema: str | None = None


class _WatchlistSyncIn(BaseModel):
    an: bool = True              # Memory-Sync ein-/ausschalten (Phase 4)


# ===================== OPML-Import/-Export (Backlog docs/33) =====================
# OPML ist das Standard-Austauschformat für Feed-Listen (RSS-Reader). Ein OPML-
# Dokument schachtelt <outline>-Elemente in <body>; Feeds tragen das Attribut
# ``xmlUrl`` (Feed-URL), dazu ``title``/``text`` (Name) und optional ``category``.
_OPML_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB hartes Eingabe-Limit (DoS-/Billion-Laughs-Schutz)

# Volltext-Extraktion (docs/33 §news): so viele frische Artikel je Abruf nachladen
# (Obergrenze hält den getakteten Hintergrund-Lauf beschränkt; best-effort/isoliert).
VOLLTEXT_CAP = 20


def _parse_opml(raw: bytes) -> list[dict[str, str]]:
    """Parst OPML SICHER → ``[{name, url, sektor}]`` je <outline> mit ``xmlUrl``.

    Sicherheit (docs/50 P4.1): DTD/Entities werden über den **geteilten**
    ``appkit.xml_safe``-Schutz abgewiesen — Billion-Laughs (interne Entity-
    Expansion) UND XXE (externe Entities) brauchen zwingend ein ``<!DOCTYPE …>``
    mit ``<!ENTITY …>``, das valides OPML nie nutzt. Dependency-frei (kein
    defusedxml), netzweit EINE Quelle (auch Money camt.053 nutzt sie). Zusammen
    mit dem Größen-Limit am Endpoint löst der Parser keinerlei Entities auf.
    Robust gegen fehlende Attribute: outline ohne ``xmlUrl`` (Ordner/Kategorie)
    wird übersprungen, Name fällt auf url zurück, Sektor auf 'allgemein'."""
    from appkit.xml_safe import sichere_wurzel
    root = sichere_wurzel(raw)  # weist DTD/Entities ab, dann stdlib-Parse (bytes-encoding-treu)
    out: list[dict[str, str]] = []
    for outline in root.iter("outline"):
        a = outline.attrib
        url = (a.get("xmlUrl") or a.get("xmlurl") or "").strip()
        if not url:
            continue  # Gruppen-/Ordner-outline ohne Feed-URL: kein Feed
        name = (a.get("title") or a.get("text") or "").strip() or url
        sektor = (a.get("category") or "").strip() or "allgemein"
        out.append({"name": name, "url": url, "sektor": sektor})
    return out


def _build_opml(quellen: list[dict[str, Any]]) -> str:
    """Erzeugt valides OPML 2.0 aus den aktiven Quellen (ElementTree ⇒ korrekte
    Attribut-Maskierung). head/title + body mit je einer <outline> pro Quelle."""
    import xml.etree.ElementTree as ET
    opml = ET.Element("opml", {"version": "2.0"})
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = "Dizz News — Quellen"
    ET.SubElement(head, "dateCreated").text = now_iso()
    body = ET.SubElement(opml, "body")
    for q in quellen:
        ET.SubElement(body, "outline", {
            "text": q.get("name") or q.get("url") or "",
            "title": q.get("name") or q.get("url") or "",
            "type": "rss",
            "xmlUrl": q.get("url") or "",
            "category": q.get("sektor") or "allgemein",
        })
    xml = ET.tostring(opml, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"


# Bessere KI-Eingabe (docs/33 §news): liegt ein extrahierter Volltext vor, speist
# ihn (HTML-frei, gedeckelt) statt der kurzen Feed-Summary in die KI-Prompts.
_KI_TEXT_MAX = 600


def _besser_text(volltext: str | None, summary: str | None) -> str:
    """Volltext bevorzugt (gedeckelt), sonst die Feed-Summary; immer HTML-frei."""
    quelle = (volltext or "").strip() or (summary or "")
    return re.sub(r"<[^>]+>", "", quelle).strip()[:_KI_TEXT_MAX]


# ---- Zeitfilter (Phase 2): Presets gegen das EFFEKTIVE Datum eines Artikels ----
# Veröffentlichung bevorzugt (``published_at``), Fallback Abrufzeit (``created_at``).
# In Python gefiltert (statt SQL), weil ``published_at`` aus Feeds uneinheitlich ist
# (ISO ODER RFC-822 „Mon, 12 Jun 2026 …"); ``created_at`` ist immer ISO ⇒ robuster Fallback.
_ZEIT_DELTA = {"7d": timedelta(days=7), "30d": timedelta(days=30),
               "6m": timedelta(days=183), "1y": timedelta(days=365)}


def _zeit_cutoff(zeit: str) -> datetime | None:
    """Untere Zeitgrenze für ein Preset; None ⇒ kein Filter (``all``/unbekannt)."""
    jetzt = datetime.now(timezone.utc)
    if zeit == "today":
        return jetzt.replace(hour=0, minute=0, second=0, microsecond=0)
    d = _ZEIT_DELTA.get(zeit)
    return (jetzt - d) if d else None


def _parse_dt(s: str | None) -> datetime | None:
    """Tolerantes Datum-Parsing (ISO oder RFC-822); naive ⇒ als UTC gedeutet."""
    if not s:
        return None
    dt = None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        try:
            dt = email.utils.parsedate_to_datetime(str(s))
        except Exception:
            dt = None
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _eff_datum(row: dict[str, Any]) -> datetime | None:
    """Effektives Artikel-Datum: Veröffentlichung, sonst Abrufzeit."""
    return _parse_dt(row.get("published_at")) or _parse_dt(row.get("created_at"))


def build_app(data_dir: Path | None = None, start_timer: bool = True,
              http_post=None, archiv_post=None, archiv_get=None,
              volltext_fn=None, kurzfassung_fn=None):
    """``volltext_fn(url) -> str`` ist der Volltext-Extraktor (docs/33 §news). Test-
    /Injektions-Seam wie ``http_post``: ist er ``None``, bleibt die Volltext-
    Extraktion AUS (kein Netz in Tests); ``app_factory`` setzt im Echtbetrieb den
    SSRF-geschützten ``extract.extrahiere_volltext`` ein. Best-effort, isoliert.

    ``kurzfassung_fn(titel, text) -> str|None`` ist der gleiche Seam für die Watchlist-
    KI-Kurzfassung (Phase 3): ``None`` ⇒ kein Netz in Tests (Fallback Feed-Summary);
    ``app_factory`` hängt ``ki.kurzfassung`` ein."""
    root = data_dir or Path(os.environ.get("DIZZ_NEWS_DATA_DIR",
                                           r"C:\Dizzik\data"))
    db = Database(default_db_path(APP_ID, data_root=root), extra_schema=_SCHEMA)

    # Migration (Backlog docs/33): Spalten idempotent für Bestands-DBs nachrüsten
    # (frische DBs haben sie bereits aus _SCHEMA). Pro-Quelle-Gesundheit (quellen)
    # + Volltext-Cache (artikel).
    for _tab, _sp, _typ in (
            ("quellen", "letzter_ok", "TEXT"),
            ("quellen", "letzter_fehler", "TEXT"),
            ("quellen", "fehler_zaehler", "INTEGER NOT NULL DEFAULT 0"),
            ("artikel", "volltext", "TEXT"),
            ("artikel", "volltext_status", "TEXT")):
        try:
            db.get_conn().execute(f"ALTER TABLE {_tab} ADD COLUMN {_sp} {_typ}")
        except Exception:
            pass
    db.get_conn().commit()

    def _seed(user_id: str = "dizzi") -> None:
        # Nachsaat per URL: wächst SEED_QUELLEN (neue Sektoren!), bekommen auch
        # BESTANDS-DBs die fehlenden Quellen. Bewusst gelöschte (deleted_at)
        # bleiben gelöscht — der Abgleich läuft ohne deleted_at-Filter.
        conn = db.get_conn()
        vorhandene = {r["url"] for r in conn.execute(
            "SELECT url FROM quellen WHERE user_id=?", (user_id,))}
        ts = now_iso()
        neu = False
        for name, url, sektor in SEED_QUELLEN:
            if url not in vorhandene:
                conn.execute(
                    "INSERT INTO quellen (id, user_id, name, url, sektor, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?)", (new_id(), user_id, name, url, sektor, ts, ts))
                neu = True
        if neu:
            conn.commit()

    def fetch_all(user_id: str = "dizzi") -> dict[str, int]:
        """Ruft alle Quellen ab; Dedupe über (user_id, link). Fehler je Quelle
        werden gezählt, stoppen aber nie den Gesamtlauf."""
        _seed(user_id)
        conn = db.get_conn()
        neu = fehler = 0
        neue: list[tuple[str, str]] = []     # (artikel_id, link) der frisch angelegten
        rows = conn.execute(
            "SELECT id, url FROM quellen WHERE user_id=? AND deleted_at IS NULL",
            (user_id,)).fetchall()
        # KA-N4: die NETZ-Abrufe laufen PARALLEL (I/O-gebunden, je Feed isoliert);
        # die DB-Writes bleiben SERIELL (eine conn = Single-Writer). Das SSRF-Gate NR-1
        # sitzt IN _lade_feed und bleibt je Feed unangetastet.
        def _hole(q):
            try:
                return q, _lade_feed(q["url"]), None
            except Exception as e:  # noqa: BLE001 — je Feed isoliert, stoppt nie den Lauf
                return q, None, e
        if rows:
            with ThreadPoolExecutor(max_workers=min(8, len(rows))) as pool:
                ergebnisse = list(pool.map(_hole, rows))
        else:
            ergebnisse = []
        for q, eintraege, _err in ergebnisse:
            ts = now_iso()
            if eintraege is None:            # Abruf-Fehler (isoliert je Feed)
                fehler += 1
                # Pro-Quelle-Gesundheit: Fehler vermerken + Zähler hoch (docs/33).
                conn.execute(
                    "UPDATE quellen SET letzter_fehler=?, fehler_zaehler=fehler_zaehler+1, "
                    "updated_at=? WHERE id=?", (ts, ts, q["id"]))
                conn.commit()
                continue
            for e in eintraege:
                if not e["link"]:
                    continue
                aid = new_id()
                cur = conn.execute(
                    """INSERT OR IGNORE INTO artikel
                       (id, user_id, quelle_id, titel, link, zusammenfassung,
                        published_at, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (aid, user_id, q["id"], e["titel"], e["link"],
                     e["zusammenfassung"], e["published"], ts, ts))
                neu += cur.rowcount
                if cur.rowcount:             # wirklich neu (nicht via UNIQUE ignoriert)
                    neue.append((aid, e["link"]))
            # Erfolgreicher Abruf: Quelle ist gesund ⇒ Zähler zurücksetzen.
            conn.execute(
                "UPDATE quellen SET letzter_ok=?, fehler_zaehler=0, updated_at=? WHERE id=?",
                (ts, ts, q["id"]))
            conn.commit()
        # Volltext-Extraktion (docs/33 §news) — best-effort, isoliert, gedeckelt;
        # nur im Echtbetrieb (volltext_fn gesetzt) + per Setting aktiv.
        extrahiert = _volltext_nachziehen(user_id, neue)
        # Watchlist-Auto-Population (Phase 3): neue Artikel den passenden Themen-
        # Ordnern zuordnen (deterministisch, best-effort, gated über watchlist_auto).
        wl_neu = _watchlist_autopop(user_id, neue)
        db.setting_put(user_id, "x_letzter_abruf", now_iso())
        db.audit(user_id, "system", "feeds_abgerufen",
                 {"neu": neu, "fehler": fehler, "quellen": len(rows),
                  "volltext": extrahiert, "watchlist": wl_neu})
        return {"neu": neu, "fehler": fehler, "quellen": len(rows),
                "volltext": extrahiert, "watchlist": wl_neu}

    # Volltext-Cache (docs/33 §news): pro Abruf bis VOLLTEXT_CAP frische Artikel
    # nachladen. Jeder Artikel isoliert (extract.* wirft nie); Status persistiert,
    # damit dieselbe URL nicht in jedem Lauf erneut versucht wird.
    def _volltext_nachziehen(user_id: str, neue: list[tuple[str, str]]) -> int:
        if volltext_fn is None or not neue:
            return 0
        if not db.setting_get(user_id, "volltext_extraktion", True):
            return 0
        conn = db.get_conn()
        versucht = ok = 0
        for aid, link in neue[:VOLLTEXT_CAP]:
            text, status = _volltext_einen(link)
            conn.execute(
                "UPDATE artikel SET volltext=?, volltext_status=?, updated_at=? "
                "WHERE id=? AND user_id=?",
                (text, status, now_iso(), aid, user_id))
            versucht += 1
            ok += (status == "ok")
        if versucht:
            conn.commit()
        return ok

    def _volltext_einen(link: str) -> tuple[str, str]:
        """Ein Artikel-Volltext (best-effort). Liefert (text, status)."""
        try:
            text = (volltext_fn(link) or "").strip() if link else ""
        except Exception:
            return "", "fehler"
        return (text, "ok") if text else ("", "leer")

    # ---- Watchlist (Phase 3) ----------------------------------------------
    def _watchlist_schwelle(user_id: str) -> float:
        try:
            return max(0.1, min(0.9, int(db.setting_get(
                user_id, "watchlist_schwelle_prozent", 34)) / 100))
        except Exception:
            return watchlist.SCHWELLE

    # KI-Kurzfassungen sind teuer (Ollama, je Artikel ein Call) ⇒ pro Auto-Pop-Lauf
    # gedeckelt; Backfill/Bestand nutzt die schnelle Feed-Summary (mit_ki=False).
    WATCHLIST_KI_CAP = 8

    def _watchlist_card_zus(a: dict[str, Any], mit_ki: bool) -> str:
        """Stylische Kurzfassung für die Watchlist-Karte: KI bevorzugt (kurzfassung_fn,
        nur wenn ``mit_ki``), sonst die HTML-freie Feed-/Volltext-Summary. Wirft nie."""
        if mit_ki and kurzfassung_fn is not None:
            try:
                kurz = kurzfassung_fn(str(a.get("titel") or ""),
                                      str(a.get("volltext") or a.get("zusammenfassung") or ""))
                if kurz:
                    return str(kurz).strip()
            except Exception:
                pass
        return _besser_text(a.get("volltext"), a.get("zusammenfassung"))

    def _watchlist_memory_push(wl: dict[str, Any], a: dict[str, Any], zus: str) -> dict[str, Any]:
        """Phase 4: einen Watchlist-Artikel in den Memory-Ordner der Watchlist
        spiegeln (Querverbindung, idempotent über ``ref``, best-effort — Archiv aus
        ⇒ still). Nutzt den vorhandenen Relay (``archiviere`` mit ``ordner``)."""
        from appkit.querverbindung import archiviere
        link = str(a.get("link") or "")
        if not link:
            return {"ok": False}
        h = hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]
        teile = [zus or "", "Quelle: " + str(a.get("quelle") or ""), link]
        return archiviere("news", str(a.get("titel") or "(ohne Titel)"),
                          "\n\n".join(t for t in teile if t),
                          strom="watchlist", ordner=str(wl.get("memory_ordner") or ""),
                          ref="news:watchlist:" + str(wl["id"]) + ":" + h,
                          quelle=link, explizit=True, http_post=archiv_post)

    def _watchlist_einfuegen(wl_id: str, a: dict[str, Any], score: float,
                             mit_ki: bool = False) -> tuple[bool, str]:
        """Idempotent (über watchlist_id+link) einen Artikel in eine Watchlist legen,
        mit stylischer Kurzfassung + Score. Existiert er schon ⇒ ``(False, "")`` (und
        KEINE KI verschwendet, da die Existenz ZUERST geprüft wird). Sonst
        ``(True, zusammenfassung)`` (zum optionalen Memory-Push)."""
        conn = db.get_conn()
        link = str(a.get("link") or "")
        if not link or conn.execute(
                "SELECT 1 FROM watchlist_artikel WHERE watchlist_id=? AND link=?",
                (wl_id, link)).fetchone():
            return (False, "")
        zus = _watchlist_card_zus(a, mit_ki)
        conn.execute(
            "INSERT OR IGNORE INTO watchlist_artikel (id, watchlist_id, artikel_id, "
            "titel, link, quelle, sektor, published_at, zusammenfassung, score, neu, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,1,?)",
            (new_id(), wl_id, a.get("id"), str(a.get("titel") or "(ohne Titel)"),
             link, a.get("quelle"), a.get("sektor"), a.get("published_at"),
             zus, round(score, 3), now_iso()))
        return (True, zus)

    def _artikel_voll(ids_oder_sql, params) -> list[dict[str, Any]]:
        return [dict(r) for r in db.get_conn().execute(ids_oder_sql, params).fetchall()]

    def _watchlist_zuordnen(user_id: str, wls, arts: list[dict[str, Any]]) -> int:
        """Kern: Artikel ``arts`` den Watchlists ``wls`` zuordnen (Score ≥ Schwelle).
        KI-Kurzfassung gedeckelt (WATCHLIST_KI_CAP) — Rest schnelle Feed-Summary.
        Synct die Watchlist (``memory_sync``), wandert der Treffer auch nach Memory."""
        schwelle = _watchlist_schwelle(user_id)
        ki_budget = WATCHLIST_KI_CAP
        # Artikel-Token einmal vorberechnen (für ALLE Watchlists wiederverwendet).
        getokt = [(a, watchlist.artikel_tokens(a)) for a in arts]
        zugefuegt = 0
        for wl in wls:
            wl = dict(wl)
            tt = watchlist.thema_tokens(wl["thema"])
            if not tt:
                continue
            for a, at in getokt:
                s = watchlist.score(tt, at)
                if s < schwelle:
                    continue
                mit_ki = ki_budget > 0
                ins, zus = _watchlist_einfuegen(wl["id"], a, s, mit_ki)
                if ins:
                    zugefuegt += 1
                    if mit_ki:
                        ki_budget -= 1
                    if wl.get("memory_sync"):
                        _watchlist_memory_push(wl, a, zus)
        if zugefuegt:
            db.get_conn().commit()
        return zugefuegt

    def _watchlist_autopop(user_id: str, neue: list[tuple[str, str]]) -> int:
        """Neue Artikel den thematisch passenden Watchlists zuordnen (deterministisch,
        best-effort). Gated über ``watchlist_auto``; ohne Watchlists ein No-Op."""
        if not neue or not db.setting_get(user_id, "watchlist_auto", True):
            return 0
        wls = db.get_conn().execute(
            "SELECT id, thema, memory_sync, memory_ordner FROM watchlists "
            "WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall()
        if not wls:
            return 0
        ph = ",".join("?" * len(neue))
        arts = _artikel_voll(
            f"SELECT a.id, a.titel, a.zusammenfassung, a.volltext, a.link, "
            f"a.published_at, q.name AS quelle, q.sektor FROM artikel a "
            f"JOIN quellen q ON q.id=a.quelle_id WHERE a.id IN ({ph})",
            [aid for aid, _ in neue])
        return _watchlist_zuordnen(user_id, wls, arts)

    def _watchlist_backfill(user_id: str, wid: str) -> int:
        """Beim Anlegen/Thema-Ändern: die zuletzt geholten Artikel EINMAL gegen das
        Thema scannen, damit die Watchlist sofort gefüllt ist (schnell, ohne KI)."""
        wl = db.get_conn().execute(
            "SELECT id, thema, memory_sync, memory_ordner FROM watchlists "
            "WHERE id=? AND user_id=? AND deleted_at IS NULL", (wid, user_id)).fetchone()
        if wl is None or not watchlist.thema_tokens(wl["thema"]):
            return 0
        arts = _artikel_voll(
            "SELECT a.id, a.titel, a.zusammenfassung, a.volltext, a.link, "
            "a.published_at, q.name AS quelle, q.sektor FROM artikel a "
            "JOIN quellen q ON q.id=a.quelle_id WHERE a.user_id=? AND a.deleted_at IS NULL "
            "ORDER BY a.created_at DESC LIMIT 300", [user_id])
        return _watchlist_zuordnen(user_id, [dict(wl)], arts)

    router = APIRouter()

    @router.get("/api/quellen")
    def quellen(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        _seed(user.user_id)
        rows = db.get_conn().execute(
            "SELECT id, name, url, sektor, letzter_ok, letzter_fehler, fehler_zaehler "
            "FROM quellen WHERE user_id=? AND deleted_at IS NULL ORDER BY name",
            (user.user_id,)).fetchall()
        return [dict(r) for r in rows]

    @router.post("/api/quellen")
    def quelle_anlegen(body: _QuelleIn,
                       user: UserContext = Depends(current_user)) -> dict[str, Any]:
        ts = now_iso()
        db.get_conn().execute(
            "INSERT INTO quellen (id, user_id, name, url, sektor, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (new_id(), user.user_id, body.name, body.url, body.sektor, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "quelle_angelegt", {"name": body.name})
        return {"ok": True}

    @router.post("/api/quellen/opml-import")
    async def quellen_opml_import(request: Request,
                                  user: UserContext = Depends(current_user)):
        """OPML-Import (Backlog docs/33): Body = OPML-XML (Text oder Datei-Upload).
        Legt neue Quellen aus den <outline>-Feeds an; Dedup über die ``url``
        (vorhandene UND gelöschte werden nicht doppelt angelegt; auch Doubletten
        innerhalb derselben Datei). XML wird SICHER geparst (kein DTD/Entity)."""
        raw = await request.body()
        if len(raw) > _OPML_MAX_BYTES:
            return JSONResponse({"error": "OPML zu groß (Limit 2 MiB)"}, status_code=413)
        try:
            kandidaten = _parse_opml(raw)
        except Exception as e:  # ungültiges/unsicheres XML
            return JSONResponse({"error": "OPML nicht lesbar: " + str(e)[:120]},
                                status_code=400)
        conn = db.get_conn()
        # Dedup-Basis = ALLE bekannten URLs des Nutzers (inkl. gelöschter): eine
        # bewusst entfernte Quelle kommt durch Re-Import nicht zurück.
        vorhandene = {r["url"] for r in conn.execute(
            "SELECT url FROM quellen WHERE user_id=?", (user.user_id,))}
        ts = now_iso()
        neu = uebersprungen = 0
        gesehen: set[str] = set()
        for k in kandidaten:
            url = k["url"]
            if url in vorhandene or url in gesehen:
                uebersprungen += 1
                continue
            gesehen.add(url)
            conn.execute(
                "INSERT INTO quellen (id, user_id, name, url, sektor, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (new_id(), user.user_id, k["name"], url, k["sektor"], ts, ts))
            neu += 1
        if neu:
            conn.commit()
        db.audit(user.user_id, "user", "quellen_opml_import",
                 {"neu": neu, "uebersprungen": uebersprungen})
        return {"neu": neu, "uebersprungen": uebersprungen}

    @router.get("/api/quellen/opml-export")
    def quellen_opml_export(user: UserContext = Depends(current_user)):
        """OPML-Export (Backlog docs/33): valides OPML 2.0 aus den aktiven Quellen
        (head/title + body mit je einer <outline>) — round-trip-fähig zum Import."""
        _seed(user.user_id)
        rows = db.get_conn().execute(
            "SELECT name, url, sektor FROM quellen "
            "WHERE user_id=? AND deleted_at IS NULL ORDER BY name",
            (user.user_id,)).fetchall()
        xml = _build_opml([dict(r) for r in rows])
        return Response(content=xml, media_type="text/x-opml",
                        headers={"Content-Disposition":
                                 'attachment; filename="dizz-news-quellen.opml"'})

    def _artikel_query(user_id: str, sektor: str, limit: int,
                       zeit: str = "all") -> list[dict[str, Any]]:
        # Kandidaten-Pool (neueste zuerst) groß genug ziehen, um den Zeit-Filter über
        # ALLE relevanten Artikel greifen zu lassen; dann hart auf ``limit`` deckeln.
        pool = min(max(limit, 400), 600)
        q = ("SELECT a.id, a.titel, a.link, a.zusammenfassung, a.published_at, "
             "a.created_at, a.volltext_status, q.name AS quelle, q.sektor FROM artikel a "
             "JOIN quellen q ON q.id=a.quelle_id "
             "WHERE a.user_id=? AND a.deleted_at IS NULL")
        params: list[Any] = [user_id]
        if sektor:
            q += " AND q.sektor=?"
            params.append(sektor)
        q += " ORDER BY a.created_at DESC LIMIT ?"
        params.append(pool)
        rows = [dict(r) for r in db.get_conn().execute(q, params).fetchall()]
        cut = _zeit_cutoff(zeit)
        if cut is not None:
            rows = [r for r in rows if (_eff_datum(r) or cut) >= cut]
        return rows[:limit]

    @router.get("/api/artikel")
    def artikel(limit: int = 30, sektor: str = "", zeit: str = "all",
                user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        return _artikel_query(user.user_id, sektor, limit, zeit)

    @router.get("/api/artikel/cluster")
    def artikel_cluster(limit: int = 200, sektor: str = "", zeit: str = "all",
                        user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Cross-Source-Dedup (docs/33 §news): dieselbe Story aus mehreren Feeds zu
        EINEM Eintrag zusammengefasst (deterministisch, lokal — keine KI/kein Netz).
        ``zeit`` ∈ {today,7d,30d,6m,1y,all} filtert über das effektive Artikel-Datum
        (Phase 2). Jeder Eintrag trägt ``anzahl``/``quellen``/``dubletten``."""
        return cluster.clustere(_artikel_query(user.user_id, sektor, limit, zeit))

    @router.post("/api/abrufen")
    def abrufen(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        return fetch_all(user.user_id)

    # --- KI-Ebene (Stufe 2): Briefing + Fragen, lokal via Ollama --------------

    def _artikel_fuer_ki(user_id: str) -> list[dict[str, Any]]:
        # Mehr ziehen als gebraucht (Dedup kann zusammenfassen) + Volltext bevorzugen.
        rows = db.get_conn().execute(
            "SELECT a.id, a.titel, a.zusammenfassung, a.volltext, a.link, "
            "q.name AS quelle, q.sektor "
            "FROM artikel a JOIN quellen q ON q.id=a.quelle_id "
            "WHERE a.user_id=? AND a.deleted_at IS NULL "
            "ORDER BY a.rowid DESC LIMIT 80", (user_id,)).fetchall()
        roh = [dict(r) for r in rows]
        for r in roh:
            r["zusammenfassung"] = _besser_text(r.get("volltext"), r.get("zusammenfassung"))
        # Cross-Source-Dedup: die KI sieht jede Story nur EINMAL (kein 5×-Rauschen).
        return cluster.dedupe(roh)[:40]

    def _modell(user_id: str) -> str:
        return db.setting_get(user_id, "llm_modell", "qwen3:4b")

    @router.post("/api/briefing")
    def briefing_lauf(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        out = ki.briefing(_artikel_fuer_ki(user.user_id),
                          modell=_modell(user.user_id), http_post=http_post)
        db.audit(user.user_id, "ki", "briefing_erstellt",
                 {"ok": "error" not in out})
        return out

    @router.post("/api/fragen")
    def frage_lauf(body: _FrageIn,
                   user: UserContext = Depends(current_user)) -> dict[str, Any]:
        kontext = _archiv_kontext(body.frage)   # RÜCK-LESE: frühere Archiv-Berichte
        out = ki.frage(_artikel_fuer_ki(user.user_id), body.frage,
                       modell=_modell(user.user_id), http_post=http_post,
                       archiv_kontext=kontext)
        if isinstance(out, dict) and kontext:
            out["archiv_kontext"] = True       # Frontend zeigt „inkl. Archiv" an
        db.audit(user.user_id, "ki", "frage_beantwortet",
                 {"ok": "error" not in out, "archiv_kontext": bool(kontext)})
        return out

    # --- Sektor-Reports (Stufe 2b, Vorbild = /news-Skill des Nutzers) ---------

    def _pool_holen(user_id: str):
        def holen(quell_sektoren: list[str], limit: int) -> list[dict[str, Any]]:
            ph = ",".join("?" * len(quell_sektoren))
            # Überziehen, damit der Dedup Spielraum hat; danach auf ``limit`` kappen.
            rows = db.get_conn().execute(
                f"SELECT a.id, a.titel, a.zusammenfassung, a.volltext, a.link, "
                f"q.name AS quelle "
                f"FROM artikel a JOIN quellen q ON q.id=a.quelle_id "
                f"WHERE a.user_id=? AND a.deleted_at IS NULL "
                f"AND q.sektor IN ({ph}) ORDER BY a.rowid DESC LIMIT ?",
                [user_id, *quell_sektoren, limit * 2]).fetchall()
            roh = [dict(r) for r in rows]
            for r in roh:
                r["zusammenfassung"] = _besser_text(r.get("volltext"),
                                                    r.get("zusammenfassung"))
            # Cross-Source-Dedup ⇒ der Digest zeigt jede Story nur EINMAL.
            return cluster.dedupe(roh)[:limit]
        return holen

    def _archiviere_report(out: dict[str, Any], rid: str, explizit: bool = False) -> dict[str, Any]:
        """Reicht den Report an Dizz Memory weiter (über den Core-Relay, V2 docs/26):
        die Archiv-Regel je (news, sektor_report) entscheidet auto / auf Zuruf;
        ``explizit`` (Nutzer-Knopf) schlägt jede Regel. Best-effort — stört den
        Report nie (``archiviere`` wirft nie)."""
        from appkit.querverbindung import archiviere
        namen = [str(a.get("name") or a.get("sektor")) for a in out.get("abschnitte", [])]
        titel = "News-Report · " + (", ".join(namen) if namen else "Sektoren")
        zeilen: list[str] = []
        for a in out.get("abschnitte", []):
            zeilen.append("## " + str(a.get("name") or a.get("sektor")))
            for p in (a.get("punkte") or []):
                zeilen.append("- " + str(p))
            if a.get("hinweis"):
                zeilen.append("_" + str(a["hinweis"]) + "_")
            zeilen.append("")
        inhalt = "\n".join(zeilen).strip() or "(leerer Report)"
        # Keine Sektor-Tags mehr (docs/26 §9.1): die Sektoren stehen als ##-Über-
        # schriften im Body; Memory vergibt zentral das eine Herkunftslabel „News".
        # Das hält den Memory-Label-Pool sauber statt mit 11 Sektor-Labels zu fluten.
        return archiviere("news", titel, inhalt, strom="sektor_report",
                          ref="news:report:" + rid, tags=[],
                          quelle="news:report:" + rid, explizit=explizit,
                          http_post=archiv_post)

    def _archiviere_artikel(row: dict[str, Any], explizit: bool = True) -> dict[str, Any]:
        """Reicht EINEN Artikel an Dizz Memory weiter (Strom 'artikel', V2-Muster
        docs/26 — analog zu _archiviere_report). Stabiler ``ref`` 'news:artikel:<id>'
        ⇒ idempotent (mehrfaches Senden = EINE Notiz). Nutzer-Knopf (``explizit``)
        schlägt jede Memory-Regel. Best-effort — ``archiviere`` wirft nie."""
        from appkit.querverbindung import archiviere
        titel = str(row.get("titel") or "(ohne Titel)")
        teile = [titel]
        zus = re.sub(r"<[^>]+>", "", str(row.get("zusammenfassung") or "")).strip()
        if zus:
            teile.append(zus)
        if row.get("quelle"):
            teile.append("Quelle: " + str(row["quelle"]))
        if row.get("link"):
            teile.append(str(row["link"]))
        inhalt = "\n\n".join(teile)
        return archiviere("news", titel, inhalt, strom="artikel",
                          ref="news:artikel:" + str(row.get("id")), tags=[],
                          quelle=str(row.get("link") or ""), explizit=explizit,
                          http_post=archiv_post)

    def _archiv_kontext(frage_text: str) -> str:
        """RÜCK-LESE (appkit 1.12, docs/26 §10.1): frühere im zentralen Archiv
        (Dizz Memory) abgelegte News-Berichte als Hintergrund für die Frage holen.
        Best-effort — nicht erreichbares Archiv ⇒ leerer Kontext (KI läuft normal)."""
        from appkit.querverbindung import memory_suche
        res = memory_suche(frage_text, limit=4, http_get=archiv_get)
        treffer = (res or {}).get("treffer") or []
        zeilen: list[str] = []
        for t in treffer[:4]:
            tt = str(t.get("titel") or t.get("name") or "Notiz")
            aus = re.sub(r"\s+", " ", str(t.get("auszug") or t.get("inhalt") or "")).strip()[:280]
            zeilen.append("- " + tt + (": " + aus if aus else ""))
        return "\n".join(zeilen)

    def report_lauf(user_id: str, sektoren: list[str],
                    ausloeser: str) -> dict[str, Any]:
        out = report.report_erstellen(
            _pool_holen(user_id), sektoren=sektoren,
            modell=db.setting_get(user_id, "llm_modell", "qwen3:4b"),
            http_post=http_post)
        ts = now_iso()
        rid = new_id()
        db.get_conn().execute(
            "INSERT INTO reports (id, user_id, sektoren, tiefe, inhalt, "
            "ausloeser, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (rid, user_id, _json.dumps(out["sektoren_gewaehlt"]), out["tiefe"],
             _json.dumps(out, ensure_ascii=False), ausloeser, ts, ts))
        db.get_conn().commit()
        db.audit(user_id, "ki", "report_erstellt",
                 {"sektoren": out["sektoren_gewaehlt"], "tiefe": out["tiefe"],
                  "ausloeser": ausloeser})
        out["id"] = rid
        out["created_at"] = ts
        _archiviere_report(out, rid)   # Auto-Versuch; die Memory-Regel gated (Default manuell)
        return out

    @router.get("/api/sektoren")
    def sektoren() -> list[dict[str, str]]:
        """Katalog für die Auswahl-UI (Geopolitik ist Pflicht + zuletzt)."""
        return report.SEKTOREN

    @router.post("/api/reports")
    def report_erstellen_ep(body: _ReportIn,
                            user: UserContext = Depends(current_user)):
        """Eigene Suche: gewählte Sektoren (leer = alle). WENIGER Sektoren ⇒
        TIEFERE Recherche je Sektor (Kern-Mechanik, s. report.tiefe_fuer)."""
        return report_lauf(user.user_id, body.sektoren, "manuell")

    @router.get("/api/reports")
    def reports_liste(limit: int = 10,
                      user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT id, sektoren, tiefe, ausloeser, created_at FROM reports "
            "WHERE user_id=? AND deleted_at IS NULL ORDER BY rowid DESC LIMIT ?",
            (user.user_id, min(limit, 50))).fetchall()
        return [{**dict(r), "sektoren": _json.loads(r["sektoren"])} for r in rows]

    @router.get("/api/reports/{rid}")
    def report_detail(rid: str, user: UserContext = Depends(current_user)):
        row = db.get_conn().execute(
            "SELECT inhalt, created_at FROM reports WHERE id=? AND user_id=? "
            "AND deleted_at IS NULL", (rid, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Report unbekannt"}, status_code=404)
        out = _json.loads(row["inhalt"])
        out["created_at"] = row["created_at"]
        return out

    @router.post("/api/reports/{rid}/archivieren")
    def report_archivieren_ep(rid: str, user: UserContext = Depends(current_user)):
        """„In Memory archivieren" (Nutzer-Zuruf): schickt den Report explizit an
        Dizz Memory — schlägt die Archiv-Regel (immer ablegen). V2, docs/26."""
        row = db.get_conn().execute(
            "SELECT inhalt FROM reports WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (rid, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Report unbekannt"}, status_code=404)
        return _archiviere_report(_json.loads(row["inhalt"]), rid, explizit=True)

    @router.post("/api/artikel/{aid}/archivieren")
    def artikel_archivieren_ep(aid: str, user: UserContext = Depends(current_user)):
        """„In Memory" (Nutzer-Knopf je Artikel): schickt EINEN Artikel explizit an
        Dizz Memory (Strom 'artikel', idempotent über ref). V2, docs/26."""
        row = db.get_conn().execute(
            "SELECT a.id, a.titel, a.zusammenfassung, a.link, q.name AS quelle "
            "FROM artikel a JOIN quellen q ON q.id=a.quelle_id "
            "WHERE a.id=? AND a.user_id=? AND a.deleted_at IS NULL",
            (aid, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Artikel unbekannt"}, status_code=404)
        res = _archiviere_artikel(dict(row), explizit=True)
        db.audit(user.user_id, "user", "artikel_archiviert",
                 {"id": aid, "ok": bool(res.get("ok"))})
        return res

    @router.get("/api/artikel/{aid}/volltext")
    def artikel_volltext_ep(aid: str, user: UserContext = Depends(current_user)):
        """Lesemodus (docs/33 §news): liefert den extrahierten Haupttext. Cache-
        first — ist noch keiner da, wird er hier ON-DEMAND geholt (SSRF-geschützt,
        best-effort) und gespeichert. Ohne Extraktor/Treffer ⇒ Feed-Summary als
        Rückfall, damit der Lesemodus nie leer bleibt."""
        row = db.get_conn().execute(
            "SELECT a.id, a.titel, a.link, a.zusammenfassung, a.volltext, "
            "a.volltext_status, q.name AS quelle, q.sektor "
            "FROM artikel a JOIN quellen q ON q.id=a.quelle_id "
            "WHERE a.id=? AND a.user_id=? AND a.deleted_at IS NULL",
            (aid, user.user_id)).fetchone()
        if row is None:
            return JSONResponse({"error": "Artikel unbekannt"}, status_code=404)
        d = dict(row)
        text, status = (d.get("volltext") or ""), d.get("volltext_status")
        if not text and status != "leer" and volltext_fn is not None:
            text, status = _volltext_einen(d.get("link") or "")
            db.get_conn().execute(
                "UPDATE artikel SET volltext=?, volltext_status=?, updated_at=? "
                "WHERE id=? AND user_id=?",
                (text, status, now_iso(), aid, user.user_id))
            db.get_conn().commit()
        rueckfall = not text
        anzeige = text or re.sub(r"<[^>]+>", "", d.get("zusammenfassung") or "").strip()
        return {"id": d["id"], "titel": d["titel"], "link": d["link"],
                "quelle": d["quelle"], "sektor": d["sektor"],
                "volltext": anzeige, "status": status or "offen",
                "rueckfall": rueckfall}

    @router.post("/api/highlight/archivieren")
    def highlight_archivieren_ep(body: _HighlightIn,
                                 user: UserContext = Depends(current_user)):
        """Highlight → Memory (P2, Readwise-Muster, docs/27 §10): eine MARKIERTE
        Lesestelle aus dem Digest/Artikel ins zentrale Archiv (Strom 'highlight').
        Stabiler ``ref`` = sha1(text) ⇒ dieselbe Stelle landet nur EINMAL im Archiv."""
        from appkit.querverbindung import archiviere
        text = (body.text or "").strip()
        if not text:
            return JSONResponse({"error": "Leere Markierung"}, status_code=400)
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        titel = (body.titel or "").strip() or ("News-Markierung: " + text[:48]
                                               + ("…" if len(text) > 48 else ""))
        inhalt = text + (("\n\n" + body.quelle) if body.quelle else "")
        res = archiviere("news", titel, inhalt, strom="highlight",
                         ref="news:highlight:" + h, quelle=body.quelle, tags=[],
                         explizit=True, http_post=archiv_post)
        db.audit(user.user_id, "user", "highlight_archiviert",
                 {"ref": "news:highlight:" + h, "ok": bool(res.get("ok"))})
        return res

    # ---- Watchlist-CRUD (Phase 3) -----------------------------------------
    def _wl_besitz(wid: str, user_id: str) -> bool:
        return db.get_conn().execute(
            "SELECT 1 FROM watchlists WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (wid, user_id)).fetchone() is not None

    @router.get("/api/watchlists")
    def watchlists(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        """Alle Watchlists mit Zählern (``anzahl`` gesamt, ``neu`` seit „gesehen")."""
        rows = db.get_conn().execute(
            "SELECT w.id, w.name, w.thema, w.memory_sync, w.gesehen_at, w.created_at, "
            "(SELECT COUNT(*) FROM watchlist_artikel wa WHERE wa.watchlist_id=w.id) AS anzahl, "
            "(SELECT COUNT(*) FROM watchlist_artikel wa WHERE wa.watchlist_id=w.id AND wa.neu=1) AS neu "
            "FROM watchlists w WHERE w.user_id=? AND w.deleted_at IS NULL "
            "ORDER BY w.created_at DESC", (user.user_id,)).fetchall()
        return [dict(r) for r in rows]

    @router.post("/api/watchlists")
    def watchlist_anlegen(body: _WatchlistIn,
                          user: UserContext = Depends(current_user)) -> dict[str, Any]:
        name = (body.name or "").strip()
        if not name:
            return JSONResponse({"error": "Name fehlt"}, status_code=400)
        ts = now_iso()
        wid = new_id()
        db.get_conn().execute(
            "INSERT INTO watchlists (id, user_id, name, thema, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)", (wid, user.user_id, name, (body.thema or "").strip(), ts, ts))
        db.get_conn().commit()
        # Sofort aus dem Bestand füllen, damit die Watchlist nicht leer startet.
        gefunden = _watchlist_backfill(user.user_id, wid)
        db.audit(user.user_id, "user", "watchlist_angelegt",
                 {"id": wid, "name": name, "backfill": gefunden})
        return {"ok": True, "id": wid, "backfill": gefunden}

    @router.get("/api/watchlists/{wid}")
    def watchlist_detail(wid: str, user: UserContext = Depends(current_user)):
        w = db.get_conn().execute(
            "SELECT id, name, thema, memory_sync, gesehen_at, created_at FROM watchlists "
            "WHERE id=? AND user_id=? AND deleted_at IS NULL", (wid, user.user_id)).fetchone()
        if w is None:
            return JSONResponse({"error": "Watchlist unbekannt"}, status_code=404)
        arts = db.get_conn().execute(
            "SELECT id, artikel_id, titel, link, quelle, sektor, published_at, "
            "zusammenfassung, score, neu, created_at FROM watchlist_artikel "
            "WHERE watchlist_id=? ORDER BY created_at DESC", (wid,)).fetchall()
        return {**dict(w), "artikel": [dict(r) for r in arts]}

    @router.put("/api/watchlists/{wid}")
    def watchlist_aendern(wid: str, body: _WatchlistPatch,
                          user: UserContext = Depends(current_user)):
        if not _wl_besitz(wid, user.user_id):
            return JSONResponse({"error": "Watchlist unbekannt"}, status_code=404)
        sets, params = [], []
        if body.name is not None and body.name.strip():
            sets.append("name=?"); params.append(body.name.strip())
        if body.thema is not None:
            sets.append("thema=?"); params.append(body.thema.strip())
        if sets:
            sets.append("updated_at=?"); params.append(now_iso())
            params += [wid, user.user_id]
            db.get_conn().execute(
                f"UPDATE watchlists SET {', '.join(sets)} WHERE id=? AND user_id=?", params)
            db.get_conn().commit()
        # Thema geändert ⇒ Bestand erneut scannen (neue Treffer nachziehen).
        gefunden = _watchlist_backfill(user.user_id, wid) if body.thema is not None else 0
        return {"ok": True, "backfill": gefunden}

    @router.delete("/api/watchlists/{wid}")
    def watchlist_loeschen(wid: str, user: UserContext = Depends(current_user)):
        db.get_conn().execute(
            "UPDATE watchlists SET deleted_at=?, updated_at=? WHERE id=? AND user_id=?",
            (now_iso(), now_iso(), wid, user.user_id))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "watchlist_geloescht", {"id": wid})
        return {"ok": True}

    @router.post("/api/watchlists/{wid}/gesehen")
    def watchlist_gesehen(wid: str, user: UserContext = Depends(current_user)):
        """„neu"-Badge zurücksetzen (alle Einträge der Watchlist als gesehen)."""
        if not _wl_besitz(wid, user.user_id):
            return JSONResponse({"error": "Watchlist unbekannt"}, status_code=404)
        conn = db.get_conn()
        conn.execute("UPDATE watchlist_artikel SET neu=0 WHERE watchlist_id=?", (wid,))
        conn.execute("UPDATE watchlists SET gesehen_at=?, updated_at=? WHERE id=?",
                     (now_iso(), now_iso(), wid))
        conn.commit()
        return {"ok": True}

    @router.post("/api/watchlists/{wid}/artikel/{aid}")
    def watchlist_artikel_zu(wid: str, aid: str,
                             user: UserContext = Depends(current_user)):
        """Einen Artikel MANUELL in eine Watchlist legen (idempotent)."""
        if not _wl_besitz(wid, user.user_id):
            return JSONResponse({"error": "Watchlist unbekannt"}, status_code=404)
        a = db.get_conn().execute(
            "SELECT a.id, a.titel, a.zusammenfassung, a.volltext, a.link, a.published_at, "
            "q.name AS quelle, q.sektor FROM artikel a JOIN quellen q ON q.id=a.quelle_id "
            "WHERE a.id=? AND a.user_id=? AND a.deleted_at IS NULL", (aid, user.user_id)).fetchone()
        if a is None:
            return JSONResponse({"error": "Artikel unbekannt"}, status_code=404)
        ins, zus = _watchlist_einfuegen(wid, dict(a), 1.0, mit_ki=True)   # manuell = volle Relevanz
        db.get_conn().commit()
        if ins:                                   # bei aktivem Sync auch nach Memory
            w = db.get_conn().execute(
                "SELECT id, memory_sync, memory_ordner FROM watchlists WHERE id=?", (wid,)).fetchone()
            if w and w["memory_sync"]:
                _watchlist_memory_push(dict(w), dict(a), zus)
        db.audit(user.user_id, "user", "watchlist_artikel_zu", {"wid": wid, "aid": aid})
        return {"ok": True, "neu": bool(ins)}

    @router.delete("/api/watchlists/{wid}/artikel/{aid}")
    def watchlist_artikel_weg(wid: str, aid: str,
                              user: UserContext = Depends(current_user)):
        if not _wl_besitz(wid, user.user_id):
            return JSONResponse({"error": "Watchlist unbekannt"}, status_code=404)
        db.get_conn().execute(
            "DELETE FROM watchlist_artikel WHERE watchlist_id=? AND artikel_id=?", (wid, aid))
        db.get_conn().commit()
        return {"ok": True}

    @router.post("/api/watchlists/{wid}/memory-sync")
    def watchlist_memory_sync(wid: str, body: _WatchlistSyncIn,
                              user: UserContext = Depends(current_user)):
        """Phase 4: Watchlist als Memory-Ordner führen. ``an=True`` schaltet die
        fortlaufende Sync ein UND spiegelt sofort den aktuellen Bestand nach Memory
        (idempotent über ``ref``); ``an=False`` schaltet nur ab (lässt Memory-Notizen
        stehen). Best-effort — Archiv aus ⇒ Flag gesetzt, Push still fehlgeschlagen."""
        conn = db.get_conn()
        w = conn.execute(
            "SELECT id, name, memory_ordner FROM watchlists "
            "WHERE id=? AND user_id=? AND deleted_at IS NULL", (wid, user.user_id)).fetchone()
        if w is None:
            return JSONResponse({"error": "Watchlist unbekannt"}, status_code=404)
        an = bool(body.an)
        ordner = w["memory_ordner"] or ("News-Watchlist: " + str(w["name"]))
        conn.execute(
            "UPDATE watchlists SET memory_sync=?, memory_ordner=?, updated_at=? "
            "WHERE id=? AND user_id=?", (1 if an else 0, ordner, now_iso(), wid, user.user_id))
        conn.commit()
        synchronisiert = 0
        if an:                                    # Voll-Sync des aktuellen Bestands
            wl = {"id": wid, "memory_ordner": ordner}
            for r in conn.execute(
                    "SELECT titel, link, quelle, zusammenfassung FROM watchlist_artikel "
                    "WHERE watchlist_id=?", (wid,)).fetchall():
                res = _watchlist_memory_push(
                    wl, {"titel": r["titel"], "link": r["link"], "quelle": r["quelle"]},
                    r["zusammenfassung"] or "")
                synchronisiert += 1 if res.get("ok") else 0
        db.audit(user.user_id, "user", "watchlist_memory_sync",
                 {"wid": wid, "an": an, "synchronisiert": synchronisiert})
        return {"ok": True, "memory_sync": an, "ordner": ordner,
                "synchronisiert": synchronisiert}

    @router.get("/", include_in_schema=False)
    def startseite(request: Request):
        """News-Oberfläche (Design-Baseline, eigenständig nutzbar).
        CSP voll-strikt (docs/37): liefert die HTML mit Per-Request-Nonce aus —
        inline <script>/<style> bekommen den Nonce; inline-onclick wurde auf
        data-dz-act (DzActions-Delegation) umgestellt."""
        from appkit.csp import serve_html_mit_csp
        return serve_html_mit_csp(request, Path(__file__).resolve().parents[1]
                                  / "static" / "index.html")

    def summary() -> list[Kpi]:
        _seed()
        conn = db.get_conn()
        n_q = conn.execute("SELECT COUNT(*) AS n FROM quellen WHERE deleted_at IS NULL").fetchone()["n"]
        n_a = conn.execute("SELECT COUNT(*) AS n FROM artikel WHERE deleted_at IS NULL").fetchone()["n"]
        letzter = db.setting_get("dizzi", "x_letzter_abruf", "—")
        return [Kpi(id="quellen", label="Quellen", value=n_q),
                Kpi(id="artikel", label="Artikel", value=n_a, unit="Stk"),
                Kpi(id="abruf", label="Letzter Abruf", value=letzter)]

    schema = make_schema(sensitivity=MANIFEST.sensitivity, extra=[
        SettingDef(key="abruf_intervall_min", category="daten", type="int",
                   default=60, min=5, max=1440,
                   label="Abruf-Intervall (Minuten)",
                   description="Getaktete Automatik: wie oft alle Quellen geholt werden."),
        SettingDef(key="automatik_aktiv", category="daten", type="bool",
                   default=True, label="Automatischer Abruf aktiv"),
        SettingDef(key="volltext_extraktion", category="daten", type="bool",
                   default=True, label="Volltext-Extraktion (Lesemodus + bessere KI)",
                   description="Holt zu frischen Artikeln den Haupttext (Readability-"
                               "artig, SSRF-geschützt) — speist Lesemodus & Sektor-"
                               "Briefings. Best-effort, je Artikel isoliert."),
        SettingDef(key="llm_modell", category="ki", type="str",
                   default="qwen3:4b", label="Ollama-Modell (Briefing/Fragen)"),
        SettingDef(key="report_automatik_aktiv", category="ki", type="bool",
                   default=True, label="Wochen-Report automatisch",
                   description="Voll-Report über ALLE Sektoren im eingestellten "
                               "Rhythmus (Vorbild: /news-Skill)."),
        SettingDef(key="report_intervall_tage", category="ki", type="int",
                   default=7, min=1, max=30,
                   label="Report-Intervall (Tage)"),
        SettingDef(key="watchlist_auto", category="ki", type="bool",
                   default=True, label="Watchlist: Auto-Themen-Ergänzung",
                   description="Ordnet neue Artikel beim Abruf automatisch den "
                               "thematisch passenden Watchlists zu (lokal/"
                               "deterministisch, still im Hintergrund)."),
        SettingDef(key="watchlist_schwelle_prozent", category="ki", type="int",
                   default=34, min=10, max=90,
                   label="Watchlist: Themen-Trefferschwelle (%)",
                   description="Anteil der Themen-Stichwörter, der in einem Artikel "
                               "vorkommen muss, damit er der Watchlist zugeordnet wird. "
                               "Höher = strenger/weniger Treffer."),
    ])

    def _raeume_news_artefakte(user_id: str) -> None:
        """on_delete-Hook (DSGVO „weg = weg", H-7-Muster): ``watchlist_artikel``
        trägt KEIN ``user_id``/``deleted_at`` (Kind der ``watchlists``, nur
        ``watchlist_id``) ⇒ die generische ``soft_delete_user``-Kaskade erfasst es
        nicht. Hier bei Konto-Löschung HART entfernen (die ``watchlists``-Zeilen
        selbst tragen die Konvention und werden generisch soft-deleted)."""
        conn = db.get_conn()
        conn.execute(
            "DELETE FROM watchlist_artikel WHERE watchlist_id IN "
            "(SELECT id FROM watchlists WHERE user_id=?)", (user_id,))
        conn.commit()

    app = create_app(MANIFEST, db, summary_fn=summary, routers=[router],
                     version=__version__, schema=schema, on_delete=_raeume_news_artefakte,
                     csp_mode="enforce", csp_strikt=True)  # CSP voll-strikt (Nonce), docs/37
                     # (data-dz-act) + Nonce-Route sind fertig & CSP-ready, ABER appkit 1.24.0 build_csp
                     # nonce't im strikt-Modus AUCH style-src (ohne 'unsafe-inline') ⇒ blockt ALLE inline
                     # style=-Attribute (318/321 in News verifiziert) — entgegen docs/37 („style-src behält
                     # unsafe-inline"). appkit ist read-only ⇒ Flip auf True erst nach appkit-Fix (s. WIEDEREINSTIEG §4).
    install_dizzi_id(app, MANIFEST, data_root=root)
    app.state.fetch_all = fetch_all  # Tests/MCP-Prozesse

    # Per-App-MCP-Gateway (docs/31 §7): im Standalone-Betrieb bietet Dizz News sein
    # EIGENES read-only MCP-Gate (/mcp) an; im Verbund (Modus 'auto') schaltet es ab,
    # sobald der Core sein zentrales Gateway führt. Gleiche Tool-Quelle wie der stdio-
    # MCP (mcp_tools.MCP_TOOLS). opt-in/Token/Hochsicher-Gate.
    app.include_router(build_app_gateway(
        MANIFEST, db, tools=mcp_tools.MCP_TOOLS,
        base_url=f"http://127.0.0.1:{MANIFEST.port}"))

    # K2.4: das ui-kit-Bundle (controls.css/collapse.js/tokens.css/spinfling.js/floats.js)
    # same-origin servieren, damit das Frontend die kanonische Komponenten-Schicht
    # referenzieren kann statt sie zu kopieren (docs/06 §6). News = Bundle-Halter.
    ui_kit_dir = ui_kit_path()
    if ui_kit_dir.is_dir():
        class _UiKitFiles(StaticFiles):  # H-1: Cache-Control no-cache -> Browser revalidiert via ETag (kein ?v=-Bump noetig)
            async def get_response(self, path, scope):
                resp = await super().get_response(path, scope)
                resp.headers["Cache-Control"] = "no-cache"
                return resp
        app.mount("/ui-kit", _UiKitFiles(directory=str(ui_kit_dir)), name="ui-kit")

    # Mini-Dizzi (Vertrag 1.5): die ECHTE News-KI als App-KI registrieren, damit
    # „frag Dizz News nach …" die Artikel-gestützte Antwort liefert (statt des
    # generischen Fallbacks). Mustern für jede App mit eigener KI.
    if getattr(app.state, "mini_dizzi", None) is not None:
        def _news_ki(frage_text: str) -> dict[str, Any]:
            out = ki.frage(_artikel_fuer_ki(DEFAULT_USER_ID), frage_text,
                           archiv_kontext=_archiv_kontext(frage_text))  # RÜCK-LESE
            return {"antwort": (out or {}).get("antwort", "")}
        app.state.mini_dizzi.set_app_ki(_news_ki)

    if start_timer:
        # Getaktete Automatik (Nutzer-Entscheid Fragerunde 3): Daemon-Tick,
        # respektiert Intervall+Schalter aus den K2-Settings; Fehler stören nie.
        def _vollreport_faellig() -> bool:
            """Wochen-Automatik: fällig, wenn der letzte VOLL-Report (alle
            Sektoren bzw. Automatik-Lauf) älter ist als das Intervall."""
            if not db.setting_get("dizzi", "report_automatik_aktiv", True):
                return False
            alle = _json.dumps(report.SEKTOR_IDS)
            row = db.get_conn().execute(
                "SELECT created_at FROM reports WHERE deleted_at IS NULL AND "
                "(ausloeser='automatik' OR sektoren=?) "
                "ORDER BY rowid DESC LIMIT 1", (alle,)).fetchone()
            if row is None:
                return True
            tage = db.setting_get("dizzi", "report_intervall_tage", 7)
            alter_s = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(row["created_at"])).total_seconds()
            return alter_s >= int(tage) * 86400

        def _tick() -> None:
            time.sleep(15)  # App erst sauber hochfahren lassen
            while True:
                try:
                    if db.setting_get("dizzi", "automatik_aktiv", True):
                        fetch_all("dizzi")
                    if _vollreport_faellig():       # Wochen-Report (alle Sektoren)
                        report_lauf("dizzi", [], "automatik")
                except Exception:
                    pass
                minuten = db.setting_get("dizzi", "abruf_intervall_min", 60)
                time.sleep(max(5, int(minuten)) * 60)

        threading.Thread(target=_tick, daemon=True, name="news-automatik").start()
    return app


def app_factory():
    """Uvicorn-Einstieg (``--factory``): importseiteneffektfrei. Im Echtbetrieb
    werden der SSRF-geschützte Volltext-Extraktor (docs/33 §news) und die Watchlist-
    KI-Kurzfassung (Phase 3) eingehängt; in Tests bleiben beide None ⇒ kein Netz."""
    return build_app(volltext_fn=extract.extrahiere_volltext,
                     kurzfassung_fn=lambda titel, text: ki.kurzfassung(titel, text))
