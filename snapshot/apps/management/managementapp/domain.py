"""Domänen-Logik von Dizz Management — Kanäle · Social-Media-Bots · Posts/Entwürfe ·
Zeitplan · Creating-Empfang.

Hier sitzt die App-eigene Substanz; alles Vertragliche (Health/Summary/Settings/
Account/Datenrechte/Defense/Mini-Dizzi/Aktionen) liefert appkit über ``create_app``.

Datenmodell folgt zwingend den Vertrags-Konventionen (UUID/user_id/Timestamps/
Soft-Delete, appkit/db.py): so greifen DSGVO-Export, Lösch-Kaskade und Retention
ohne Per-App-Code.

── Drei Domänen-Bausteine (docs/00_VISION + APP_GRUNDLAGEN §B „Multi-Agent") ────
- **Kanäle** (``kanaele``): die angesteuerten Accounts je Plattform (IG/TikTok/X/
  LinkedIn/YouTube/…). Verbindung läuft über die ChannelSource-Adapter (channels.py,
  Gesetz 5 dormant) — v1 trägt der Nutzer die Kanäle ein, Posten bleibt DORMANT.
- **Social-Media-Bots** (``social_bots``): benannte Themen-/Marken-Profile (Ton,
  Zielgruppe, Standard-Hashtags). Sie sind die „Unter-Agenten", die einem oder mehreren
  Kanälen zugeordnet werden; der übergeordnete Manager (ki.py) beobachtet/plant über alle.
- **Posts/Entwürfe** (``posts``) + **Zeitplan**: Entwurf → Planung → Freigabe →
  (späteres) Veröffentlichen. Der Zeitplan ist KEINE eigene Tabelle, sondern die
  Sicht auf Posts mit ``geplant_fuer`` (idempotentes Scheduling, kein Doppel-Post).

── Außenwirkung = Human-in-the-Loop (K4, docs/RECHERCHE §3–§5) ──────────────────
Veröffentlichen ist eine Außenwirkungs-Aktion. Sie läuft NIE direkt, sondern als
HITL-Aktion ``post_veroeffentlichen`` (Stufe 'verifiziert', appkit/actions.py):
vorschlagen → Nutzer gibt frei → Handler ruft den Kanal-Adapter. v1 ist der Live-
Pfad DORMANT (channels.py) ⇒ die Freigabe wird gespeichert, echtes Posten bleibt aus.

── Creating-Empfang (REV-3, Management-Seite) ───────────────────────────────────
``POST /api/creating/empfang`` nimmt ein Asset + Metadaten von Dizz Creating entgegen
und legt je Kanal-Derivat einen **Post-Entwurf** an (idempotent über
``herkunft_asset_id`` + Plattform). NUR der Empfangs-Slot — die Creating-Gegenseite
+ der Übergabe-Vertrag sind World-Chat (FÜR-WORLD-CHAT, SYSTEMUEBERSICHT.md).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from appkit.actions import ActionRegistry, propose
from appkit.auth import UserContext, current_user
from appkit.db import Database, new_id, now_iso
from appkit.summary import Kpi

from . import ki
from .channels import (PLATTFORMEN, KanalNichtVerbunden, OutboundPost,
                       adapter_fuer, kanaele_status)

# --- Domänen-Vokabular (UI + Validierung teilen sich diese Listen) -----------
KANAL_STATUS = ("getrennt", "verbunden", "pausiert")
BOT_TON = ("sachlich", "locker", "humorvoll", "inspirierend", "werblich", "informativ")
POST_STATUS = ("entwurf", "geplant", "freigegeben", "veroeffentlicht", "abgelehnt", "fehler")
POST_QUELLE = ("manuell", "creating")

# Kurz-Aliase, die in Derivat-Zwecken vorkommen (z. B. 'yt_16_9' → youtube).
_PLATTFORM_ALIAS = {"yt": "youtube", "ig": "instagram", "li": "linkedin",
                    "fb": "facebook", "tt": "tiktok"}

# Default-Seitenverhältnis je Plattform (UI-Komfort beim Creating-Empfang).
_DEFAULT_FORMAT = {"tiktok": "9:16", "instagram": "9:16", "youtube": "16:9",
                   "threads": "1:1", "x": "16:9", "linkedin": "1:1",
                   "bluesky": "1:1", "mastodon": "1:1"}

# Zeichen-Limits je Plattform (Caption/Text, Stand 2026) — SINGLE SOURCE für die
# Composer-Validierung im Frontend (ausgeliefert über /api/plattformen, P2). Default
# für nicht gelistete Plattformen: DEFAULT_ZEICHEN_LIMIT.
ZEICHEN_LIMITS = {"x": 280, "bluesky": 300, "mastodon": 500, "threads": 500,
                  "instagram": 2200, "tiktok": 2200, "linkedin": 3000, "youtube": 5000}
DEFAULT_ZEICHEN_LIMIT = 2200

WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

# Domänen-Schema — direkt an create_app/Database übergeben (extra_schema).
SCHEMA = """
CREATE TABLE IF NOT EXISTS kanaele (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    plattform    TEXT NOT NULL,                  -- instagram|tiktok|x|linkedin|youtube|…
    handle       TEXT NOT NULL DEFAULT '',       -- @handle / Account-Name
    anzeigename  TEXT NOT NULL DEFAULT '',
    bot_id       TEXT NOT NULL DEFAULT '',       -- zugeordneter Social-Bot (optional)
    status       TEXT NOT NULL DEFAULT 'getrennt',-- getrennt|verbunden|pausiert
    token_name   TEXT NOT NULL DEFAULT '',       -- Name des OAuth-Tokens im Tresor (Slot)
    extern_id    TEXT NOT NULL DEFAULT '',       -- Plattform-Konto-ID (Sync-Slot)
    etag         TEXT NOT NULL DEFAULT '',
    notiz        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_kanaele ON kanaele (user_id, plattform);

CREATE TABLE IF NOT EXISTS social_bots (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    name         TEXT NOT NULL,
    thema        TEXT NOT NULL DEFAULT '',       -- Themen-/Marken-Beschreibung
    ton          TEXT NOT NULL DEFAULT 'sachlich',
    zielgruppe   TEXT NOT NULL DEFAULT '',
    hashtags     TEXT NOT NULL DEFAULT '',       -- Standard-Hashtags des Profils
    aktiv        INTEGER NOT NULL DEFAULT 1,
    notiz        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_social_bots ON social_bots (user_id, aktiv, name);

CREATE TABLE IF NOT EXISTS posts (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    kanal_id         TEXT NOT NULL DEFAULT '',   -- Zielkanal (optional, bis zugeordnet)
    bot_id           TEXT NOT NULL DEFAULT '',   -- erzeugender/zuständiger Social-Bot
    plattform        TEXT NOT NULL DEFAULT '',   -- Zielplattform (auch ohne konkreten Kanal)
    titel            TEXT NOT NULL DEFAULT '',
    text             TEXT NOT NULL DEFAULT '',   -- Caption/Body
    hashtags         TEXT NOT NULL DEFAULT '',
    medien           TEXT NOT NULL DEFAULT '[]', -- JSON: Asset-Pfade/-Refs (DAM)
    format           TEXT NOT NULL DEFAULT '',   -- 9:16 | 1:1 | 16:9 …
    status           TEXT NOT NULL DEFAULT 'entwurf',
    quelle           TEXT NOT NULL DEFAULT 'manuell', -- manuell|creating
    herkunft_asset_id TEXT NOT NULL DEFAULT '',  -- Creating-Asset-ID (Idempotenz/Herkunft)
    heikel             INTEGER NOT NULL DEFAULT 0, -- REV-4: kanal-/AVS-konforme Behandlung
    geplant_fuer     TEXT NOT NULL DEFAULT '',   -- ISO-8601 (Zeitplan-Slot)
    extern_id        TEXT NOT NULL DEFAULT '',   -- Plattform-Post-ID (nach Publish, Slot)
    etag             TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    deleted_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts ON posts (user_id, status, geplant_fuer);
CREATE INDEX IF NOT EXISTS idx_posts_herkunft ON posts (user_id, herkunft_asset_id, plattform);
"""


# --- Request-Modelle: MODUL-Ebene zwingend (PEP-563-Falle, s. refapp/README) -
class KanalIn(BaseModel):
    plattform: str
    handle: str = ""
    anzeigename: str = ""
    bot_id: str = ""
    bereich_id: str = ""        # Bereich-Achse ('' = Allgemein)
    notiz: str = ""


class KanalPatch(BaseModel):
    handle: str | None = None
    anzeigename: str | None = None
    bot_id: str | None = None
    bereich_id: str | None = None
    status: str | None = None
    notiz: str | None = None


class BotIn(BaseModel):
    name: str
    thema: str = ""
    ton: str = "sachlich"
    zielgruppe: str = ""
    hashtags: str = ""
    plattform: str = ""         # optionaler Ziel-Plattform-Slot ('' = plattform-übergreifend)
    bereich_id: str = ""        # Bereich-Achse ('' = Allgemein)
    notiz: str = ""


class BotPatch(BaseModel):
    name: str | None = None
    thema: str | None = None
    ton: str | None = None
    zielgruppe: str | None = None
    hashtags: str | None = None
    plattform: str | None = None
    bereich_id: str | None = None
    aktiv: bool | None = None
    notiz: str | None = None


class PostIn(BaseModel):
    titel: str = ""
    text: str = ""
    hashtags: str = ""
    plattform: str = ""
    kanal_id: str = ""
    bot_id: str = ""
    bereich_id: str = ""        # Bereich-Achse ('' = Allgemein)
    format: str = ""
    medien: list[str] = []
    geplant_fuer: str = ""
    heikel: bool = False


class PostPatch(BaseModel):
    titel: str | None = None
    text: str | None = None
    hashtags: str | None = None
    plattform: str | None = None
    kanal_id: str | None = None
    bot_id: str | None = None
    bereich_id: str | None = None
    format: str | None = None
    medien: list[str] | None = None
    status: str | None = None
    geplant_fuer: str | None = None


class PlanenIn(BaseModel):
    geplant_fuer: str


class BulkCsvIn(BaseModel):
    # Bulk-Import (P3): CSV-Text mit Spalten titel,text,plattform,hashtags,geplant_fuer.
    csv: str
    bereich_id: str = ""        # alle importierten Entwürfe in diesen Bereich ('' = Allgemein)


class CreatingAsset(BaseModel):
    """Übergabe-Nutzlast von Dizz Creating (REV-3, Empfangs-Slot). Felder spiegeln
    das Creating-DAM (Asset + pro-Kanal-Derivate/asset_varianten)."""

    asset_id: str = ""                  # Creating-Asset-ID (Idempotenz)
    titel: str = ""
    pfad: str = ""                      # Pfad/Ref des Haupt-Assets (DAM)
    modus: str = "video"               # bild|video|audio
    heikel: bool = False
    modell_lizenz: str = ""            # Verkaufs-Hygiene (informativ)
    rechte: str = ""
    text_vorschlag: str = ""          # optionaler Caption-Vorschlag
    hashtags: str = ""
    bot_id: str = ""                   # zuständiger Social-Bot (optional)
    bereich_id: str = ""               # Ziel-Bereich der empfangenen Entwürfe ('' = Allgemein)
    # Pro-Kanal-Derivate (asset_varianten): {"zweck","pfad","format","plattform"}
    derivate: list[dict[str, Any]] = []
    # Fallback-Ziele, falls keine Derivate mitkommen:
    kanal_plattformen: list[str] = []


def _in(wert: str, erlaubt: tuple[str, ...], default: str) -> str:
    return wert if wert in erlaubt else default


def _plattform_aus_zweck(zweck: str) -> str:
    """'tiktok_9_16' → 'tiktok', 'yt_16_9' → 'youtube'. Unbekannt ⇒ ''."""
    kopf = (zweck or "").strip().lower().split("_", 1)[0]
    if kopf in PLATTFORMEN:
        return kopf
    return _PLATTFORM_ALIAS.get(kopf, "")


class Domain:
    """Bündelt Router + Kennzahl-Funktionen der Management-Domäne. main.py reicht
    ``summary``/``stats`` an den Vertrag bzw. den MCP-Server, ``ki_kontext`` an die
    KI (Mini-Dizzi + /api/plan). Die HITL-Aktion ``post_veroeffentlichen`` wird in
    ``registry`` registriert. ``http_post`` ist der Test-Injektionspunkt für die
    lokale KI; ``vault`` wird von main NACH create_app gesetzt (Token-Prüfung)."""

    def __init__(self, db: Database, registry: ActionRegistry,
                 http_post: Any | None = None, archiv_post: Any | None = None) -> None:
        self.db = db
        self.registry = registry
        self.http_post = http_post
        self.archiv_post = archiv_post   # Querverbindungs-POST (V8 Management→Memory)
        self.vault = None  # main setzt das nach create_app (app.state.vault)
        registry.register(
            "post_veroeffentlichen", self._handle_veroeffentlichen, level="verifiziert",
            beschreibung="Post an den verbundenen Kanal veröffentlichen (Außenwirkung). "
                         "v1 DORMANT — echtes Posten erst mit verbundenem Kanal/Opt-in.")
        self.router = self._build_router()

    def set_vault(self, vault: Any) -> None:
        self.vault = vault

    def _vault_getter(self):
        vault = self.vault

        def _g(name: str):
            try:
                return "x" if (vault and name in vault.names()) else None
            except Exception:
                return None
        return _g

    # --- Kennzahlen (Kachel + /api/stats + MCP) -----------------------------
    def stats(self, user_id: str = "dizzi", bereich_id: str = "") -> dict[str, Any]:
        """Kennzahlen — optional auf einen Bereich gescoped (``bereich_id``). Default
        ('' ) = bereichs-übergreifender Gesamtstand (Kachel + /api/stats; die UI-Kachel
        bleibt Gesamt, der Bereich-Scope speist den Kontext-Kopf)."""
        conn = self.db.get_conn()
        jetzt = now_iso()
        bk = " AND bereich_id=?" if bereich_id else ""
        bp: tuple = (bereich_id.strip(),) if bereich_id else ()

        def _n(sql: str, params: tuple = ()) -> int:
            return conn.execute(sql, (user_id, *params)).fetchone()["n"]

        kanaele = _n(f"SELECT COUNT(*) AS n FROM kanaele WHERE user_id=? AND deleted_at IS NULL{bk}", bp)
        kanaele_verb = _n(f"SELECT COUNT(*) AS n FROM kanaele WHERE user_id=? AND deleted_at IS NULL "
                          f"AND status='verbunden'{bk}", bp)
        bots_aktiv = _n(f"SELECT COUNT(*) AS n FROM social_bots WHERE user_id=? AND deleted_at IS NULL "
                        f"AND aktiv=1{bk}", bp)
        entwuerfe = _n(f"SELECT COUNT(*) AS n FROM posts WHERE user_id=? AND deleted_at IS NULL "
                       f"AND status='entwurf'{bk}", bp)
        geplant = _n(f"SELECT COUNT(*) AS n FROM posts WHERE user_id=? AND deleted_at IS NULL "
                     f"AND status='geplant'{bk}", bp)
        veroeff = _n(f"SELECT COUNT(*) AS n FROM posts WHERE user_id=? AND deleted_at IS NULL "
                     f"AND status='veroeffentlicht'{bk}", bp)
        next_row = conn.execute(
            "SELECT geplant_fuer, titel FROM posts WHERE user_id=? AND deleted_at IS NULL "
            f"AND status='geplant' AND geplant_fuer>=?{bk} ORDER BY geplant_fuer ASC LIMIT 1",
            (user_id, jetzt, *bp)).fetchone()
        return {
            "kanaele_gesamt": kanaele, "kanaele_verbunden": kanaele_verb,
            "bots_aktiv": bots_aktiv, "entwuerfe": entwuerfe, "geplant": geplant,
            "veroeffentlicht": veroeff,
            "naechster_slot": (next_row["geplant_fuer"] if next_row else ""),
            "naechster_slot_titel": (next_row["titel"] if next_row else ""),
        }

    def summary(self, user_id: str = "dizzi") -> list[Kpi]:
        s = self.stats(user_id)
        return [
            Kpi(id="kanaele", label="Kanäle", value=s["kanaele_gesamt"]),
            Kpi(id="bots", label="Social-Bots aktiv", value=s["bots_aktiv"]),
            Kpi(id="entwuerfe", label="Entwürfe", value=s["entwuerfe"]),
            Kpi(id="geplant", label="Geplant", value=s["geplant"]),
            Kpi(id="naechster_slot", label="Nächster Slot",
                value=(s["naechster_slot"][:16].replace("T", " ") if s["naechster_slot"] else "—")),
        ]

    # --- Auswertung (P2): redaktionelle Analytik, rein lokal ----------------
    @staticmethod
    def _wd_stunde(iso: str) -> tuple[int | None, int]:
        """(Wochentag Mo=0…So=6, Stunde 0–23) aus einem ISO-Zeitstempel; tolerant."""
        try:
            d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return d.weekday(), d.hour
        except Exception:
            try:
                from datetime import date as _date
                h = int(iso[11:13]) if len(iso) >= 13 else 9
                return _date(int(iso[0:4]), int(iso[5:7]), int(iso[8:10])).weekday(), h
            except Exception:
                return None, 0

    @staticmethod
    def _beste_zeiten(heat: list[list[int]], top: int = 3) -> list[dict[str, Any]]:
        flat = [{"wochentag": wd, "stunde": h, "label": f"{WOCHENTAGE[wd]} {h:02d}:00",
                 "anzahl": heat[wd][h]}
                for wd in range(7) for h in range(24) if heat[wd][h] > 0]
        flat.sort(key=lambda x: -x["anzahl"])
        return flat[:top]

    def analytics(self, user_id: str, tage: int = 90, bereich_id: str = "") -> dict[str, Any]:
        """Redaktionelle Auswertung AUS DEM EIGENEN POST-BESTAND (lokal, 0 Abhängigkeit):
        KPIs · Verteilung je Plattform · Status-Verteilung · Posting-Zeiten-Heatmap
        (Wochentag×Stunde aus ``geplant_fuer``). ``reichweite`` (Follower/Engagement/
        Impressions) ist ein **DORMANT-Slot** (Gesetz 5): kein Kanal liefert v1 echte
        Live-Metriken — ehrlich getrennt von den eigenen Plan-Zahlen. ``bereich_id``
        ('' = alle) scoped die Auswertung optional auf einen Bereich."""
        conn = self.db.get_conn()
        bk = " AND bereich_id=?" if bereich_id else ""
        bp: tuple = (bereich_id.strip(),) if bereich_id else ()
        rows = conn.execute(
            "SELECT plattform, status, geplant_fuer FROM posts "
            f"WHERE user_id=? AND deleted_at IS NULL{bk}", (user_id, *bp)).fetchall()
        je_plattform: dict[str, dict[str, Any]] = {}
        status_vert = {s: 0 for s in POST_STATUS}
        heat = [[0] * 24 for _ in range(7)]
        for r in rows:
            p = r["plattform"] or "—"
            d = je_plattform.setdefault(p, {"plattform": p, "gesamt": 0, "entwurf": 0,
                                            "geplant": 0, "freigegeben": 0,
                                            "veroeffentlicht": 0})
            d["gesamt"] += 1
            if r["status"] in d:
                d[r["status"]] += 1
            if r["status"] in status_vert:
                status_vert[r["status"]] += 1
            gf = r["geplant_fuer"] or ""
            if r["status"] in ("geplant", "freigegeben", "veroeffentlicht") and len(gf) >= 13:
                wd, h = self._wd_stunde(gf)
                if wd is not None:
                    heat[wd][h] += 1
        verbundene = conn.execute(
            "SELECT COUNT(*) AS n FROM kanaele WHERE user_id=? AND deleted_at IS NULL "
            f"AND status='verbunden'{bk}", (user_id, *bp)).fetchone()["n"]
        return {
            "kpis": self.stats(user_id, bereich_id),
            "je_plattform": sorted(je_plattform.values(), key=lambda x: -x["gesamt"]),
            "status_verteilung": status_vert,
            "heatmap": heat,                       # heat[wochentag][stunde]
            "wochentage": list(WOCHENTAGE),
            "beste_zeiten": self._beste_zeiten(heat, top=3),
            "reichweite": {
                "verfuegbar": False, "verbundene_kanaele": verbundene,
                "hinweis": "Reichweite/Engagement/Impressions sind vorbereitet, aber "
                           "DORMANT (Gesetz 5): kein Kanal liefert v1 Live-Metriken "
                           "(ChannelSource.analytics). Aktiv, sobald ein Kanal verbunden "
                           "+ der Live-Pfad scharf ist (docs/04)."},
        }

    @property
    def _bereich_register(self):
        """D3b (docs/67): geteilter Register für ①kanon→②kontext-Auflösung. Lazy —
        die Domain instanziiert Bereiche nicht, darum ein eigenes DzBereichRegister
        über self.db (SQL-wertgleich zum ersetzten Inline-SELECT)."""
        reg = getattr(self, "_register", None)
        if reg is None:
            from appkit.bereich_register import DzBereichRegister
            reg = self._register = DzBereichRegister(self.db, kontext_spalte="kontext")
        return reg

    def social(self, user_id: str, kontext: str, kanon: str = "") -> dict[str, Any]:
        """A5/V18 (docs/34) — per-Bereich-Social-Spur für Dizz Admins Bereichs-Cockpit
        (über Core-Relay ``/querverbindung/management/bereich-social``). READ-ONLY
        (sensitivity ``hoch`` ⇒ keine Aktions-/Publish-Pfade hier).

        ``kontext`` = ``bereich.management_kontext``. **Bereich-Achse (neu):** zuerst wird
        ein lokaler **Bereich** über ``bereiche.kontext`` (case-insensitiv) aufgelöst und
        über dessen ``bereich_id`` aggregiert (Kanäle/Bots/Posts leben *im* Bereich).
        Findet sich kein passender Bereich, greift der **rückwärtskompatible Fallback**
        auf den **Social-Bot-NAMEN** (Alt-Mechanik über ``bot_id``), damit Admins
        Live-Cockpit grün bleibt, bis Bereiche+``kontext`` gepflegt sind. Liefert Bot(s),
        Kanäle, Post-Zähler je Status+Plattform, nächste geplante Posts. Leerer/kein
        Treffer ⇒ leere Spur (best-effort, wirft nie)."""
        leer: dict[str, Any] = {
            "kontext": kontext or "", "bots": [], "kanaele": [],
            "posts": {"gesamt": 0, "je_status": {}, "je_plattform": []},
            "naechste_posts": [], "anzahl_kanaele": 0, "anzahl_posts": 0, "quelle": ""}
        kontext = (kontext or "").strip()
        kanon = (kanon or "").strip()
        if not kontext and not kanon:
            return leer
        conn = self.db.get_conn()
        # 1) Bereich-Auflösung (V18-Kanon). Best-effort: fehlt die bereiche-Tabelle in
        #    einem isolierten Kontext, fällt es auf das Bot-Namen-Matching zurück.
        try:
            aufl = self._bereich_register.aufloesen(user_id, kanon=kanon, kontext=kontext)
        except Exception:   # noqa: BLE001 — read-only, darf das Cockpit nie kippen
            aufl = None
        if aufl is not None and aufl.bereich_id:
            bid = aufl.bereich_id
            bots = conn.execute(
                "SELECT id, name, thema, aktiv FROM social_bots WHERE user_id=? "
                "AND deleted_at IS NULL AND bereich_id=? ORDER BY name", (user_id, bid)).fetchall()
            kanaele = conn.execute(
                "SELECT plattform, handle, anzeigename, status FROM kanaele WHERE user_id=? "
                "AND deleted_at IS NULL AND bereich_id=? ORDER BY plattform, handle",
                (user_id, bid)).fetchall()
            posts = conn.execute(
                "SELECT plattform, status, titel, geplant_fuer FROM posts WHERE user_id=? "
                "AND deleted_at IS NULL AND bereich_id=?", (user_id, bid)).fetchall()
            return self._social_payload(kontext, bots, kanaele, posts, quelle=aufl.quelle)
        # 2) Fallback: Social-Bot-Namen-Matching (Alt-Mechanik, rückwärtskompatibel).
        bots = conn.execute(
            "SELECT id, name, thema, aktiv FROM social_bots WHERE user_id=? "
            "AND deleted_at IS NULL AND LOWER(name)=LOWER(?)",
            (user_id, kontext)).fetchall()
        if not bots:
            return leer
        bot_ids = [b["id"] for b in bots]
        ph = ",".join("?" * len(bot_ids))
        kanaele = conn.execute(
            f"SELECT plattform, handle, anzeigename, status FROM kanaele WHERE user_id=? "
            f"AND deleted_at IS NULL AND bot_id IN ({ph}) ORDER BY plattform, handle",
            (user_id, *bot_ids)).fetchall()
        posts = conn.execute(
            f"SELECT plattform, status, titel, geplant_fuer FROM posts WHERE user_id=? "
            f"AND deleted_at IS NULL AND bot_id IN ({ph})",
            (user_id, *bot_ids)).fetchall()
        return self._social_payload(kontext, bots, kanaele, posts, quelle="bot")

    @staticmethod
    def _social_payload(kontext: str, bots, kanaele, posts, quelle: str = "") -> dict[str, Any]:
        """Baut die V18-Social-Spur (Zähler je Status/Plattform + nächste Posts) aus den
        bereits gefilterten Bot-/Kanal-/Post-Zeilen — geteilt von Bereich- und Bot-Pfad."""
        je_status = {s: 0 for s in POST_STATUS}
        je_plattform: dict[str, int] = {}
        for p in posts:
            if p["status"] in je_status:
                je_status[p["status"]] += 1
            pl = p["plattform"] or "—"
            je_plattform[pl] = je_plattform.get(pl, 0) + 1
        jetzt = now_iso()
        naechste = sorted(
            ({"titel": p["titel"], "plattform": p["plattform"], "status": p["status"],
              "geplant_fuer": p["geplant_fuer"]} for p in posts
             if p["status"] in ("geplant", "freigegeben") and (p["geplant_fuer"] or "") >= jetzt),
            key=lambda x: x["geplant_fuer"])[:5]
        return {
            "kontext": kontext, "quelle": quelle,
            "bots": [{"id": b["id"], "name": b["name"], "thema": b["thema"],
                      "aktiv": bool(b["aktiv"])} for b in bots],
            "kanaele": [{"plattform": k["plattform"], "handle": k["handle"],
                         "anzeigename": k["anzeigename"], "status": k["status"]}
                        for k in kanaele],
            "posts": {"gesamt": len(posts), "je_status": je_status,
                      "je_plattform": sorted(
                          ({"plattform": p, "anzahl": n} for p, n in je_plattform.items()),
                          key=lambda x: -x["anzahl"])},
            "naechste_posts": naechste,
            "anzahl_kanaele": len(kanaele), "anzahl_posts": len(posts)}

    def beste_zeit_vorschlag(self, user_id: str) -> dict[str, Any]:
        """KI-Auto-Scheduling (P3): schlägt den NÄCHSTEN Slot vor — häufigste eigene
        Posting-Zeit (Wochentag/Stunde) aus dem Bestand; ohne Historie ⇒ Default Di 18:00.
        REIN VORSCHLAG (HITL): der Nutzer übernimmt ihn aktiv (kein Auto-Posten)."""
        beste = self.analytics(user_id)["beste_zeiten"]
        if beste:
            wd, h = beste[0]["wochentag"], beste[0]["stunde"]
            basis = (f"häufigste eigene Posting-Zeit ({WOCHENTAGE[wd]} {h:02d}:00, "
                     f"n={beste[0]['anzahl']})")
        else:
            wd, h, basis = 1, 18, "Standard-Vorschlag (noch keine Historie): Di 18:00"
        now = datetime.now(timezone.utc)
        ziel = now.replace(hour=h, minute=0, second=0, microsecond=0)
        ziel += timedelta(days=(wd - ziel.weekday()) % 7)
        if ziel <= now:
            ziel += timedelta(days=7)
        return {"vorschlag": ziel.isoformat(timespec="seconds"),
                "wochentag": WOCHENTAGE[wd], "stunde": h, "basis": basis}

    # --- KI-Kontext (Mini-Dizzi + /api/plan) --------------------------------
    def ki_kontext(self, user_id: str) -> dict[str, Any]:
        """Kontext für die Social-KI: Kanäle + Bots + jüngste Posts + Zeitplan.
        Die KI plant/schlägt nur daraus vor — sie erfindet keine Konten dazu."""
        conn = self.db.get_conn()
        kanaele = [{"plattform": r["plattform"], "handle": r["handle"],
                    "status": r["status"], "bot_id": r["bot_id"]}
                   for r in conn.execute(
                       "SELECT plattform, handle, status, bot_id FROM kanaele "
                       "WHERE user_id=? AND deleted_at IS NULL ORDER BY plattform LIMIT 40",
                       (user_id,)).fetchall()]
        bots = [{"name": r["name"], "thema": r["thema"], "ton": r["ton"],
                 "zielgruppe": r["zielgruppe"]}
                for r in conn.execute(
                    "SELECT name, thema, ton, zielgruppe FROM social_bots "
                    "WHERE user_id=? AND deleted_at IS NULL AND aktiv=1 ORDER BY name LIMIT 30",
                    (user_id,)).fetchall()]
        posts = [{"titel": r["titel"], "plattform": r["plattform"], "status": r["status"],
                  "geplant_fuer": r["geplant_fuer"]}
                 for r in conn.execute(
                     "SELECT titel, plattform, status, geplant_fuer FROM posts "
                     "WHERE user_id=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 25",
                     (user_id,)).fetchall()]
        zeitplan = [{"titel": r["titel"], "plattform": r["plattform"],
                     "geplant_fuer": r["geplant_fuer"]}
                    for r in conn.execute(
                        "SELECT titel, plattform, geplant_fuer FROM posts WHERE user_id=? "
                        "AND deleted_at IS NULL AND status='geplant' AND geplant_fuer>=? "
                        "ORDER BY geplant_fuer ASC LIMIT 15", (user_id, now_iso())).fetchall()]
        return {"kanaele": kanaele, "bots": bots, "posts": posts, "zeitplan": zeitplan}

    def _modell(self, user_id: str) -> str:
        return str(self.db.setting_get(user_id, "llm_modell", "qwen3:4b")) or "qwen3:4b"

    # --- HITL-Aktion: Veröffentlichen (Außenwirkung, v1 DORMANT) -------------
    def _handle_veroeffentlichen(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handler der HITL-Aktion ``post_veroeffentlichen`` (läuft NUR nach Freigabe
        über appkit/actions.decide). Ruft den Kanal-Adapter (channels.py). v1 ist der
        Live-Pfad DORMANT ⇒ die Freigabe wird gespeichert, echtes Posten bleibt aus."""
        pid = str(params.get("post_id", ""))
        conn = self.db.get_conn()
        row = conn.execute("SELECT * FROM posts WHERE id=? AND deleted_at IS NULL",
                           (pid,)).fetchone()
        if row is None:
            raise ValueError(f"Post unbekannt: {pid!r}")
        if row["status"] == "veroeffentlicht":
            return {"ok": True, "status": "veroeffentlicht",
                    "hinweis": "Post war bereits veröffentlicht."}
        plattform = row["plattform"] or self._kanal_plattform(row["kanal_id"])
        adapter = adapter_fuer(plattform, vault_get=self._vault_getter())
        post = OutboundPost(
            text=row["text"], hashtags=row["hashtags"],
            medien=json.loads(row["medien"] or "[]"), format=row["format"],
            heikel=bool(row["heikel"]), titel=row["titel"])
        ts = now_iso()
        # Scharfer Pfad NUR, wenn ein Adapter existiert UND verbunden ist:
        if adapter is not None and adapter.verbunden():
            try:
                res = adapter.publish(post)  # v1: wirft KanalNichtVerbunden (dormant)
                extern = str((res or {}).get("extern_ref", ""))
                conn.execute("UPDATE posts SET status='veroeffentlicht', extern_id=?, "
                             "updated_at=? WHERE id=?", (extern, ts, pid))
                conn.commit()
                self.db.audit(row["user_id"], "user", "post_veroeffentlicht",
                              {"id": pid, "plattform": plattform})
                return {"ok": True, "status": "veroeffentlicht", "extern_id": extern}
            except KanalNichtVerbunden as e:
                grund = str(e)
        else:
            grund = f"Kanal '{plattform or '—'}' nicht verbunden"
        # DORMANT: Freigabe gespeichert, echtes Posten v1 nicht scharf (Recht/Opt-in).
        conn.execute("UPDATE posts SET status='freigegeben', updated_at=? WHERE id=?",
                     (ts, pid))
        conn.commit()
        self.db.audit(row["user_id"], "user", "post_freigegeben_dormant",
                      {"id": pid, "plattform": plattform, "grund": grund})
        return {"ok": True, "status": "freigegeben", "dormant": True,
                "hinweis": "Freigabe gespeichert. Echtes Posten an den Kanal ist v1 "
                           "DORMANT (Recht/Opt-in/Plattform-Review): " + grund + "."}

    def _kanal_plattform(self, kanal_id: str) -> str:
        if not kanal_id:
            return ""
        row = self.db.get_conn().execute(
            "SELECT plattform FROM kanaele WHERE id=? AND deleted_at IS NULL",
            (kanal_id,)).fetchone()
        return row["plattform"] if row else ""

    # --- Serializer ---------------------------------------------------------
    @staticmethod
    def _kanal_public(r) -> dict[str, Any]:
        return {"id": r["id"], "plattform": r["plattform"], "handle": r["handle"],
                "anzeigename": r["anzeigename"], "bot_id": r["bot_id"],
                "bereich_id": r["bereich_id"], "status": r["status"],
                "token_name": r["token_name"], "notiz": r["notiz"],
                "created_at": r["created_at"]}

    @staticmethod
    def _bot_public(r) -> dict[str, Any]:
        return {"id": r["id"], "name": r["name"], "thema": r["thema"], "ton": r["ton"],
                "zielgruppe": r["zielgruppe"], "hashtags": r["hashtags"],
                "plattform": r["plattform"], "bereich_id": r["bereich_id"],
                "aktiv": bool(r["aktiv"]), "notiz": r["notiz"], "created_at": r["created_at"]}

    @staticmethod
    def _post_public(r) -> dict[str, Any]:
        return {"id": r["id"], "kanal_id": r["kanal_id"], "bot_id": r["bot_id"],
                "bereich_id": r["bereich_id"], "plattform": r["plattform"],
                "titel": r["titel"], "text": r["text"],
                "hashtags": r["hashtags"], "medien": json.loads(r["medien"] or "[]"),
                "format": r["format"], "status": r["status"], "quelle": r["quelle"],
                "herkunft_asset_id": r["herkunft_asset_id"], "heikel": bool(r["heikel"]),
                "geplant_fuer": r["geplant_fuer"], "extern_id": r["extern_id"],
                "created_at": r["created_at"]}

    def _archiviere_post(self, user_id: str, pid: str,
                         explizit: bool = False) -> dict[str, Any]:
        """Reicht einen Post (Plattform/Status/Text/Hashtags/Medien-Überblick) als
        Notiz an Dizz Memory weiter (Core-Relay, V8 docs/26) — Medien-Binärdaten
        bleiben im DAM/Verweis. Archiv-Regel je (management, post_log) gated;
        ``explizit`` (Nutzer-Knopf) schlägt jede Regel. Best-effort (wirft nie).
        Herkunftslabel „Management" vergibt Memory zentral (§9.1); die Plattform
        reist als ein nützliches Tag mit. HEIKEL ⇒ ``sensibel``."""
        from appkit.querverbindung import archiviere
        row = self.db.get_conn().execute(
            "SELECT * FROM posts WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (pid, user_id)).fetchone()
        if row is None:
            return {"ok": False, "fehler": "Post unbekannt"}
        text = (row["text"] or "").strip()
        titel = (row["titel"] or "").strip() or (text.split("\n", 1)[0][:60] if text else "") or "Post"
        medien = json.loads(row["medien"] or "[]")
        kopf = f"**Plattform:** {row['plattform'] or '—'} · **Status:** {row['status']} · **Quelle:** {row['quelle']}"
        if (row["geplant_fuer"] or "").strip():
            kopf += f" · **Geplant:** {row['geplant_fuer']}"
        zeilen = [kopf]
        if text:
            zeilen += ["", text]
        if (row["hashtags"] or "").strip():
            zeilen += ["", row["hashtags"].strip()]
        if medien:
            zeilen += ["", f"_Medien: {len(medien)} Asset(s) (im DAM / als Verweis)._"]
        inhalt = "\n".join(zeilen).strip()
        tags = [row["plattform"]] if (row["plattform"] or "").strip() else []
        return archiviere("management", "Post · " + titel, inhalt,
                          strom="post_log", ref="management:post:" + pid,
                          quelle="management:post:" + pid, tags=tags,
                          sensibel=bool(row["heikel"]), explizit=explizit,
                          http_post=self.archiv_post)

    # --- Router -------------------------------------------------------------
    def _build_router(self) -> APIRouter:  # noqa: C901  (viele schlanke CRUD-Endpunkte)
        r = APIRouter()
        db = self.db

        # ===================== STATS / KATALOG / KANAL-QUELLEN ==============
        @r.get("/api/stats")
        def stats_ep(bereich_id: str = "",
                     user: UserContext = Depends(current_user)) -> dict[str, Any]:
            return self.stats(user.user_id, bereich_id)

        @r.get("/api/plattformen")
        def plattformen() -> dict[str, Any]:
            """Plattform-Katalog (direkte Adapter) + Unified-Optionen + Zeichen-Limits
            (Single Source für die Composer-Validierung, P2) — für UI-Dropdowns."""
            return {"plattformen": list(PLATTFORMEN),
                    "unified": ["ayrshare", "postiz"],
                    "toene": list(BOT_TON), "post_status": list(POST_STATUS),
                    "zeichen_limits": ZEICHEN_LIMITS,
                    "zeichen_limit_default": DEFAULT_ZEICHEN_LIMIT}

        @r.get("/api/kanaele/quellen")
        def kanal_quellen(request: Request,
                          user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Vorbereitete Kanal-Adapter + Verbindungsstatus (Gesetz 5 sichtbar).
            Liest nur die TRESOR-NAMEN (keine Geheimnisse) zur Verfügbarkeits-Prüfung."""
            vault = getattr(request.app.state, "vault", None)

            def _vault_get(name: str):
                try:
                    return "x" if (vault and name in vault.names()) else None
                except Exception:
                    return None
            return {"quellen": kanaele_status(vault_get=_vault_get)}

        # ===================== KANÄLE =======================================
        @r.post("/api/kanaele")
        def kanal_anlegen(body: KanalIn,
                          user: UserContext = Depends(current_user)) -> dict[str, Any]:
            plattform = body.plattform.strip().lower()
            if plattform not in PLATTFORMEN:
                raise HTTPException(400, f"Unbekannte Plattform: {plattform!r}. "
                                         f"Erlaubt: {', '.join(PLATTFORMEN)}.")
            ts = now_iso()
            kid = new_id()
            db.get_conn().execute(
                "INSERT INTO kanaele (id, user_id, plattform, handle, anzeigename, bot_id, "
                "bereich_id, notiz, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (kid, user.user_id, plattform, body.handle.strip(), body.anzeigename.strip(),
                 body.bot_id.strip(), body.bereich_id.strip(), body.notiz.strip(), ts, ts))
            db.get_conn().commit()
            db.audit(user.user_id, "user", "kanal_angelegt", {"plattform": plattform})
            return {"ok": True, "id": kid}

        @r.get("/api/kanaele")
        def kanal_liste(plattform: str = "", bereich_id: str = "",
                        user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM kanaele WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if plattform:
                q += " AND plattform=?"; params.append(plattform.strip().lower())
            if bereich_id:                       # '' = kein Filter (alle Bereiche)
                q += " AND bereich_id=?"; params.append(bereich_id.strip())
            q += " ORDER BY plattform, created_at"
            return [self._kanal_public(row)
                    for row in db.get_conn().execute(q, params).fetchall()]

        @r.patch("/api/kanaele/{kid}")
        def kanal_patch(kid: str, body: KanalPatch,
                        user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM kanaele WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (kid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Kanal unbekannt"}, status_code=404)
            felder, werte = [], []
            if body.handle is not None:
                felder.append("handle=?"); werte.append(body.handle.strip())
            if body.anzeigename is not None:
                felder.append("anzeigename=?"); werte.append(body.anzeigename.strip())
            if body.bot_id is not None:
                felder.append("bot_id=?"); werte.append(body.bot_id.strip())
            if body.bereich_id is not None:
                felder.append("bereich_id=?"); werte.append(body.bereich_id.strip())
            if body.status is not None:
                felder.append("status=?"); werte.append(_in(body.status, KANAL_STATUS, "getrennt"))
            if body.notiz is not None:
                felder.append("notiz=?"); werte.append(body.notiz.strip())
            if not felder:
                return {"ok": True, "id": kid}
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [kid, user.user_id]
            conn.execute(f"UPDATE kanaele SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "kanal_geaendert", {"id": kid})
            return {"ok": True, "id": kid}

        @r.delete("/api/kanaele/{kid}")
        def kanal_delete(kid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM kanaele WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (kid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Kanal unbekannt"}, status_code=404)
            conn.execute("UPDATE kanaele SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), kid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "kanal_geloescht", {"id": kid})
            return {"ok": True, "id": kid}

        # ===================== SOCIAL-BOTS ==================================
        @r.post("/api/bots")
        def bot_anlegen(body: BotIn,
                        user: UserContext = Depends(current_user)) -> dict[str, Any]:
            if not body.name.strip():
                raise HTTPException(400, "Name ist Pflicht.")
            plattform = (body.plattform or "").strip().lower()
            if plattform and plattform not in PLATTFORMEN:
                raise HTTPException(400, f"Unbekannte Plattform: {plattform!r}. "
                                         f"Leer = plattform-übergreifend; sonst: {', '.join(PLATTFORMEN)}.")
            ts = now_iso()
            bid = new_id()
            db.get_conn().execute(
                "INSERT INTO social_bots (id, user_id, name, thema, ton, zielgruppe, "
                "hashtags, plattform, bereich_id, aktiv, notiz, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?)",
                (bid, user.user_id, body.name.strip(), body.thema.strip(),
                 _in(body.ton, BOT_TON, "sachlich"), body.zielgruppe.strip(),
                 body.hashtags.strip(), plattform, body.bereich_id.strip(),
                 body.notiz.strip(), ts, ts))
            db.get_conn().commit()
            db.audit(user.user_id, "user", "bot_angelegt",
                     {"name": body.name.strip(), "plattform": plattform})
            return {"ok": True, "id": bid}

        @r.get("/api/bots")
        def bot_liste(aktiv: str = "", bereich_id: str = "",
                      user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM social_bots WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if aktiv in ("0", "1"):
                q += " AND aktiv=?"; params.append(int(aktiv))
            if bereich_id:                       # '' = kein Filter (alle Bereiche)
                q += " AND bereich_id=?"; params.append(bereich_id.strip())
            q += " ORDER BY aktiv DESC, name ASC"
            return [self._bot_public(row)
                    for row in db.get_conn().execute(q, params).fetchall()]

        @r.patch("/api/bots/{bid}")
        def bot_patch(bid: str, body: BotPatch,
                      user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM social_bots WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (bid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Bot unbekannt"}, status_code=404)
            felder, werte = [], []
            if body.name is not None and body.name.strip():
                felder.append("name=?"); werte.append(body.name.strip())
            if body.thema is not None:
                felder.append("thema=?"); werte.append(body.thema.strip())
            if body.ton is not None:
                felder.append("ton=?"); werte.append(_in(body.ton, BOT_TON, "sachlich"))
            if body.zielgruppe is not None:
                felder.append("zielgruppe=?"); werte.append(body.zielgruppe.strip())
            if body.hashtags is not None:
                felder.append("hashtags=?"); werte.append(body.hashtags.strip())
            if body.plattform is not None:
                p = (body.plattform or "").strip().lower()
                if p and p not in PLATTFORMEN:
                    return JSONResponse({"error": f"Unbekannte Plattform: {p!r}"}, status_code=400)
                felder.append("plattform=?"); werte.append(p)
            if body.bereich_id is not None:
                felder.append("bereich_id=?"); werte.append(body.bereich_id.strip())
            if body.aktiv is not None:
                felder.append("aktiv=?"); werte.append(int(body.aktiv))
            if body.notiz is not None:
                felder.append("notiz=?"); werte.append(body.notiz.strip())
            if not felder:
                return {"ok": True, "id": bid}
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [bid, user.user_id]
            conn.execute(f"UPDATE social_bots SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "bot_geaendert", {"id": bid})
            return {"ok": True, "id": bid}

        @r.delete("/api/bots/{bid}")
        def bot_delete(bid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM social_bots WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (bid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Bot unbekannt"}, status_code=404)
            conn.execute("UPDATE social_bots SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), bid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "bot_geloescht", {"id": bid})
            return {"ok": True, "id": bid}

        # ===================== POSTS / ENTWÜRFE =============================
        @r.post("/api/posts")
        def post_anlegen(body: PostIn,
                         user: UserContext = Depends(current_user)) -> dict[str, Any]:
            plattform = (body.plattform or "").strip().lower()
            kanal_id = body.kanal_id.strip()
            if kanal_id:
                kp = self._kanal_plattform(kanal_id)
                if not kp:
                    raise HTTPException(400, "Unbekannter Kanal.")
                plattform = plattform or kp
            if plattform and plattform not in PLATTFORMEN:
                raise HTTPException(400, f"Unbekannte Plattform: {plattform!r}.")
            geplant = body.geplant_fuer.strip()
            status = "geplant" if geplant else "entwurf"
            ts = now_iso()
            pid = new_id()
            db.get_conn().execute(
                "INSERT INTO posts (id, user_id, kanal_id, bot_id, bereich_id, plattform, titel, "
                "text, hashtags, medien, format, status, quelle, heikel, geplant_fuer, created_at, "
                "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'manuell',?,?,?,?)",
                (pid, user.user_id, kanal_id, body.bot_id.strip(), body.bereich_id.strip(),
                 plattform, body.titel.strip(), body.text.strip(), body.hashtags.strip(),
                 json.dumps(list(body.medien), ensure_ascii=False), body.format.strip(),
                 status, int(bool(body.heikel)), geplant, ts, ts))
            db.get_conn().commit()
            db.audit(user.user_id, "user", "post_angelegt",
                     {"id": pid, "plattform": plattform, "status": status})
            return {"ok": True, "id": pid, "status": status}

        @r.get("/api/posts")
        def post_liste(status: str = "", kanal_id: str = "", bot_id: str = "",
                       quelle: str = "", bereich_id: str = "", limit: int = 200,
                       user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM posts WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if status:
                q += " AND status=?"; params.append(status)
            if kanal_id:
                q += " AND kanal_id=?"; params.append(kanal_id)
            if bot_id:
                q += " AND bot_id=?"; params.append(bot_id)
            if quelle:
                q += " AND quelle=?"; params.append(quelle)
            if bereich_id:                       # '' = kein Filter (alle Bereiche)
                q += " AND bereich_id=?"; params.append(bereich_id.strip())
            q += " ORDER BY created_at DESC LIMIT ?"
            params.append(min(max(limit, 1), 1000))
            return [self._post_public(row)
                    for row in db.get_conn().execute(q, params).fetchall()]

        @r.patch("/api/posts/{pid}")
        def post_patch(pid: str, body: PostPatch,
                       user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM posts WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (pid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Post unbekannt"}, status_code=404)
            felder, werte = [], []
            if body.titel is not None:
                felder.append("titel=?"); werte.append(body.titel.strip())
            if body.text is not None:
                felder.append("text=?"); werte.append(body.text.strip())
            if body.hashtags is not None:
                felder.append("hashtags=?"); werte.append(body.hashtags.strip())
            if body.plattform is not None:
                p = body.plattform.strip().lower()
                if p and p not in PLATTFORMEN:
                    return JSONResponse({"error": f"Unbekannte Plattform: {p!r}"}, status_code=400)
                felder.append("plattform=?"); werte.append(p)
            if body.kanal_id is not None:
                felder.append("kanal_id=?"); werte.append(body.kanal_id.strip())
            if body.bot_id is not None:
                felder.append("bot_id=?"); werte.append(body.bot_id.strip())
            if body.bereich_id is not None:
                felder.append("bereich_id=?"); werte.append(body.bereich_id.strip())
            if body.format is not None:
                felder.append("format=?"); werte.append(body.format.strip())
            if body.medien is not None:
                felder.append("medien=?"); werte.append(json.dumps(list(body.medien), ensure_ascii=False))
            if body.status is not None:
                felder.append("status=?"); werte.append(_in(body.status, POST_STATUS, "entwurf"))
            if body.geplant_fuer is not None:
                felder.append("geplant_fuer=?"); werte.append(body.geplant_fuer.strip())
            if not felder:
                return {"ok": True, "id": pid}
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [pid, user.user_id]
            conn.execute(f"UPDATE posts SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "post_geaendert", {"id": pid})
            return {"ok": True, "id": pid}

        @r.delete("/api/posts/{pid}")
        def post_delete(pid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM posts WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (pid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Post unbekannt"}, status_code=404)
            conn.execute("UPDATE posts SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), pid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "post_geloescht", {"id": pid})
            return {"ok": True, "id": pid}

        @r.post("/api/posts/{pid}/archivieren")
        def post_archivieren_ep(pid: str,
                                user: UserContext = Depends(current_user)):
            """„In Memory archivieren" (Nutzer-Zuruf): schickt den Post explizit
            an Dizz Memory — schlägt jede Archiv-Regel (V8, docs/26)."""
            conn = db.get_conn()
            if conn.execute("SELECT id FROM posts WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (pid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Post unbekannt"}, status_code=404)
            ergebnis = self._archiviere_post(user.user_id, pid, explizit=True)
            db.audit(user.user_id, "user", "post_archiviert",
                     {"id": pid, "status": ergebnis.get("status")})
            return ergebnis

        @r.post("/api/posts/{pid}/planen")
        def post_planen(pid: str, body: PlanenIn,
                        user: UserContext = Depends(current_user)):
            """Setzt einen Entwurf auf den Zeitplan (status='geplant' + geplant_fuer)."""
            conn = db.get_conn()
            if conn.execute("SELECT id FROM posts WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (pid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Post unbekannt"}, status_code=404)
            wann = body.geplant_fuer.strip()
            if not wann:
                return JSONResponse({"error": "geplant_fuer ist Pflicht"}, status_code=400)
            conn.execute("UPDATE posts SET status='geplant', geplant_fuer=?, updated_at=? "
                         "WHERE id=? AND user_id=?", (wann, now_iso(), pid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "post_geplant", {"id": pid, "geplant_fuer": wann})
            return {"ok": True, "id": pid, "geplant_fuer": wann}

        @r.get("/api/zeitplan")
        def zeitplan(tage: int = 30, bereich_id: str = "",
                     user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Redaktionsplan: geplante (und unplatzierte Entwurfs-)Posts, zeitlich
            sortiert. ``tage`` begrenzt das Vorausschau-Fenster für geplante Posts.
            ``bereich_id`` ist ein OPTIONALER Filter — ohne ihn ist der Redaktionsplan
            der **bereichs-übergreifende Gesamtplan** (Nutzer-Vision: je Bereich planen,
            in der Redaktion den Gesamtplan sehen)."""
            jetzt = datetime.now(timezone.utc)
            bis = (jetzt + timedelta(days=max(1, min(tage, 3650)))).isoformat(timespec="seconds")
            bk = " AND bereich_id=?" if bereich_id else ""
            bp: tuple = (bereich_id.strip(),) if bereich_id else ()
            conn = db.get_conn()
            geplant = [self._post_public(r) for r in conn.execute(
                "SELECT * FROM posts WHERE user_id=? AND deleted_at IS NULL AND status='geplant' "
                f"AND geplant_fuer<=?{bk} ORDER BY geplant_fuer ASC",
                (user.user_id, bis, *bp)).fetchall()]
            entwuerfe = [self._post_public(r) for r in conn.execute(
                "SELECT * FROM posts WHERE user_id=? AND deleted_at IS NULL AND status='entwurf'"
                f"{bk} ORDER BY created_at DESC LIMIT 100", (user.user_id, *bp)).fetchall()]
            return {"geplant": geplant, "entwuerfe": entwuerfe}

        # ===================== HITL-FREIGABE (Veröffentlichen) ==============
        @r.post("/api/posts/{pid}/freigabe-anfordern")
        def freigabe_anfordern(pid: str,
                               user: UserContext = Depends(current_user)):
            """Schlägt die HITL-Aktion ``post_veroeffentlichen`` vor (führt NICHTS aus).
            Freigabe danach über appkit ``POST /api/actions/{id}/approve`` (Stufe
            'verifiziert'). Veröffentlichen ist Außenwirkung ⇒ nie eigenmächtig."""
            row = db.get_conn().execute(
                "SELECT status FROM posts WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (pid, user.user_id)).fetchone()
            if row is None:
                return JSONResponse({"error": "Post unbekannt"}, status_code=404)
            if row["status"] == "veroeffentlicht":
                return JSONResponse({"error": "Post ist bereits veröffentlicht"}, status_code=400)
            res = propose(db, self.registry, user.user_id, "post_veroeffentlichen",
                          {"post_id": pid}, source="user")
            return res

        # ===================== CREATING-EMPFANG (REV-3) =====================
        @r.post("/api/creating/empfang")
        def creating_empfang(body: CreatingAsset,
                             user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Empfängt ein Asset + Metadaten von Dizz Creating und legt je Kanal-Derivat
            einen Post-ENTWURF an (HITL-Freigabe vor dem späteren Posten). Idempotent über
            (``herkunft_asset_id``, Plattform) — derselbe Übergabe-Call legt nichts doppelt an.

            NUR der Empfangs-Slot: die Creating-Gegenseite + der Übergabe-Vertrag sind
            World-Chat (FÜR-WORLD-CHAT, SYSTEMUEBERSICHT.md)."""
            # Ziele bestimmen: bevorzugt die mitgelieferten Derivate (pro-Kanal),
            # sonst die genannten Plattformen, sonst EIN generischer Entwurf.
            ziele: list[dict[str, str]] = []
            for d in body.derivate:
                plattform = (str(d.get("plattform") or "").strip().lower()
                             or _plattform_aus_zweck(str(d.get("zweck", ""))))
                ziele.append({"plattform": plattform,
                              "format": str(d.get("format", "")) or _DEFAULT_FORMAT.get(plattform, ""),
                              "pfad": str(d.get("pfad") or body.pfad)})
            if not ziele:
                for p in body.kanal_plattformen:
                    p = (p or "").strip().lower()
                    ziele.append({"plattform": p, "format": _DEFAULT_FORMAT.get(p, ""),
                                  "pfad": body.pfad})
            if not ziele:
                ziele.append({"plattform": "", "format": "", "pfad": body.pfad})

            conn = db.get_conn()
            ts = now_iso()
            angelegt: list[str] = []
            uebersprungen: list[str] = []
            for z in ziele:
                plattform = z["plattform"]
                # Idempotenz: gleicher Asset + gleiche Plattform ⇒ nicht doppelt anlegen.
                if body.asset_id:
                    vorhanden = conn.execute(
                        "SELECT id FROM posts WHERE user_id=? AND herkunft_asset_id=? "
                        "AND plattform=? AND deleted_at IS NULL",
                        (user.user_id, body.asset_id, plattform)).fetchone()
                    if vorhanden:
                        uebersprungen.append(vorhanden["id"])
                        continue
                # Passenden Kanal zuordnen: bevorzugt im Ziel-Bereich + derselben Plattform,
                # sonst irgendeinen Kanal derselben Plattform (best-effort).
                ber = body.bereich_id.strip()
                kanal_id = ""
                if plattform:
                    if ber:
                        k = conn.execute(
                            "SELECT id FROM kanaele WHERE user_id=? AND plattform=? AND bereich_id=? "
                            "AND deleted_at IS NULL ORDER BY created_at LIMIT 1",
                            (user.user_id, plattform, ber)).fetchone()
                        kanal_id = k["id"] if k else ""
                    if not kanal_id:
                        k = conn.execute(
                            "SELECT id FROM kanaele WHERE user_id=? AND plattform=? "
                            "AND deleted_at IS NULL ORDER BY created_at LIMIT 1",
                            (user.user_id, plattform)).fetchone()
                        kanal_id = k["id"] if k else ""
                medien = json.dumps([z["pfad"]] if z["pfad"] else [], ensure_ascii=False)
                pid = new_id()
                conn.execute(
                    "INSERT INTO posts (id, user_id, kanal_id, bot_id, bereich_id, plattform, titel, "
                    "text, hashtags, medien, format, status, quelle, herkunft_asset_id, heikel, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'entwurf','creating',?,?,?,?)",
                    (pid, user.user_id, kanal_id, body.bot_id.strip(), ber, plattform,
                     body.titel.strip(), body.text_vorschlag.strip(), body.hashtags.strip(),
                     medien, z["format"], body.asset_id.strip(), int(bool(body.heikel)), ts, ts))
                angelegt.append(pid)
            conn.commit()
            db.audit(user.user_id, "ki", "creating_empfangen",
                     {"asset_id": body.asset_id, "angelegt": len(angelegt),
                      "uebersprungen": len(uebersprungen), "heikel": bool(body.heikel)})
            return {"ok": True, "asset_id": body.asset_id, "angelegt": angelegt,
                    "uebersprungen": uebersprungen}

        # ===================== KI-PLANUNG (Vorschläge, HITL) ===============
        @r.post("/api/plan")
        def plan(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Lokale Social-KI: Vorschläge zu Content-Planung/Recycling/Posting-Zeiten
            aus dem App-Bestand. Reine VORSCHLÄGE (HITL) — nichts wird gepostet."""
            kontext = self.ki_kontext(user.user_id)
            erg = ki.plane(kontext, modell=self._modell(user.user_id), http_post=self.http_post)
            db.audit(user.user_id, "ki", "plan_erstellt",
                     {"vorschlaege": len(erg.get("vorschlaege", [])), "quelle": erg.get("quelle")})
            return erg

        # ===================== AUSWERTUNG (P2) / AUTO-ZEIT (P3) =============
        @r.get("/api/analytics")
        def analytics_ep(tage: int = 90, bereich_id: str = "",
                         user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Redaktionelle Auswertung (lokal): KPIs · je Plattform · Status ·
            Posting-Zeiten-Heatmap. Reichweite/Engagement = DORMANT-Slot (Gesetz 5).
            ``bereich_id`` ('' = alle) scoped optional auf einen Bereich."""
            return self.analytics(user.user_id, tage, bereich_id)

        @r.get("/api/bereich/social")
        def bereich_social(kontext: str = "", kanon: str = "",
                           user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """A5/V18 (docs/34) — read-only per-Bereich-Social-Spur für Dizz Admins
            Bereichs-Cockpit. ``kontext`` = ``bereich.management_kontext`` → Social-Bot-
            Name. Bots + Kanäle + Post-Zähler + nächste geplante Posts. READ-ONLY."""
            return self.social(user.user_id, kontext, kanon)

        @r.get("/api/auto-zeit")
        def auto_zeit(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """KI-Auto-Scheduling-Vorschlag (P3): nächster Slot aus der eigenen
            Posting-Historie. REIN VORSCHLAG (HITL) — der Nutzer übernimmt ihn."""
            return self.beste_zeit_vorschlag(user.user_id)

        # ===================== BULK-IMPORT (P3) ============================
        @r.post("/api/posts/bulk")
        def post_bulk(body: BulkCsvIn,
                      user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Bulk-Import von ENTWÜRFEN aus CSV (Spalten titel,text,plattform,hashtags,
            geplant_fuer; Kopfzeile optional). Legt nur Entwürfe/geplante Posts an —
            **kein Posten** (Außenwirkung bleibt HITL). Zeilen mit Fehlern werden
            gemeldet, nicht stillschweigend verworfen."""
            import csv as _csv
            import io as _io
            text = (body.csv or "").strip()
            if not text:
                return JSONResponse({"error": "Leere CSV"}, status_code=400)
            zeilen = [c for c in _csv.reader(_io.StringIO(text))
                      if any((x or "").strip() for x in c)]
            if not zeilen:
                return {"ok": True, "angelegt": [], "fehler": []}
            felder = ("titel", "text", "plattform", "hashtags", "geplant_fuer")
            kopf = [c.strip().lower() for c in zeilen[0]]
            hat_kopf = any(h in felder for h in kopf)
            idx = {n: kopf.index(n) for n in felder if n in kopf} if hat_kopf else {}
            start = 1 if hat_kopf else 0

            def feld(cols: list[str], name: str, pos: int) -> str:
                i = idx[name] if name in idx else pos
                return cols[i].strip() if i < len(cols) else ""

            angelegt: list[str] = []
            fehler: list[dict[str, Any]] = []
            conn = db.get_conn()
            ts = now_iso()
            for nr, cols in enumerate(zeilen[start:], start=start + 1):
                titel = feld(cols, "titel", 0)
                txt = feld(cols, "text", 1)
                plattform = feld(cols, "plattform", 2).lower()
                ht = feld(cols, "hashtags", 3)
                gf = feld(cols, "geplant_fuer", 4)
                if not titel and not txt:
                    fehler.append({"zeile": nr, "grund": "Titel und Text leer"})
                    continue
                if plattform and plattform not in PLATTFORMEN:
                    fehler.append({"zeile": nr, "grund": f"Plattform {plattform!r} unbekannt"})
                    continue
                status = "geplant" if gf else "entwurf"
                pid = new_id()
                conn.execute(
                    "INSERT INTO posts (id, user_id, kanal_id, bot_id, bereich_id, plattform, titel, "
                    "text, hashtags, medien, format, status, quelle, heikel, geplant_fuer, "
                    "created_at, updated_at) VALUES (?,?,'','',?,?,?,?,?,'[]','',?,'manuell',0,?,?,?)",
                    (pid, user.user_id, body.bereich_id.strip(), plattform, titel, txt, ht,
                     status, gf, ts, ts))
                angelegt.append(pid)
            conn.commit()
            db.audit(user.user_id, "user", "bulk_import",
                     {"angelegt": len(angelegt), "fehler": len(fehler)})
            return {"ok": True, "angelegt": angelegt, "fehler": fehler}

        return r


def build_domain(db: Database, registry: ActionRegistry,
                 http_post: Any | None = None, archiv_post: Any | None = None) -> Domain:
    return Domain(db, registry, http_post=http_post, archiv_post=archiv_post)
