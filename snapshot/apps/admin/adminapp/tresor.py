"""Domänen-Logik von Dizz Admin — Dokument-Vault (GoBD-bewusst) + Aufgaben.

Hier sitzt die App-eigene Substanz; alles Vertragliche (Health/Summary/Settings/
Account/Datenrechte/Defense/Mini-Dizzi/Actions) liefert appkit über ``create_app``.

Datenmodell folgt zwingend den Vertrags-Konventionen (UUID/user_id/Timestamps/
Soft-Delete, appkit/db.py): so greifen DSGVO-Export, Lösch-Kaskade und Retention
ohne Per-App-Code. Dokument-DATEIEN liegen NICHT im Repo, sondern im Vault unter
``<data>/apps/admin/vault/<user_id>/`` — die DB hält nur den RELATIVEN Pfad.

── v2-Ausbau (15.06.2026) ───────────────────────────────────────────────────
- **Volltext-Index (FTS5)** über Titel/Notiz/Tags/Volltext; Text-Extraktion via
  ``extract.py`` (DOCX/TXT stdlib; PDF/Bild-OCR optional, graceful). Suche-Endpoint
  nutzt FTS5 MATCH (Prefix) mit LIKE-Fallback.
- **SHA-256-Dedupe**: identische Dateien (egal aus welcher Quelle) erzeugen keine
  Duplikate — Grundlage für wiederholtes Ordner-/IMAP-Scannen.
- **Gemeinsamer Einzug-Kern** ``speichere_dokument`` für Upload UND DocumentSource-
  Adapter (``sources.py``): Härtung/Dedupe/Index gelten einheitlich.
- **Frist-Wächter**: ``frist_pruefen`` schlägt fällige Aufgaben als HITL-Aktionen
  vor (appkit actions); Freigabe quittiert ``frist_handler``.
- **Integrations-Slots** (``integrationen.py``): Buchungsvorschlag (Cross-Finanzen)
  + ELSTER-Referenz — READ-ONLY Entwürfe, nicht aktiv.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from appkit.auth import LEVELS, UserContext, current_user
from appkit.db import Database, new_id, now_iso
from appkit.io_safe import atomic_write_bytes
from appkit.summary import Kpi

from . import extract

# --- Domänen-Vokabular (UI + Validierung teilen sich diese Listen) -----------
DOK_TYPEN = ("Rechnung", "Vertrag", "Steuer", "Sonstiges")
AUFGABE_STATUS = ("offen", "in-bearbeitung", "erledigt")
PRIORITAETEN = ("hoch", "mittel", "niedrig")
# Erlaubte Endungen (Markt-Standard; gilt für Upload UND alle DocumentSources).
ALLOWED_EXT = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".docx"})
_BILD_EXT = frozenset({".jpg", ".jpeg", ".png"})   # thumbnail-fähig (PIL); Rest = Typ-Icon
MAX_UPLOAD_BYTES = 50 * 1024 * 1024            # 50 MB (Vertrags-Vorgabe)

# Domänen-Schema — direkt an create_app/Database übergeben (extra_schema).
# FTS5-Tabelle wird in-Code synchron gehalten (Insert/Update/Soft-Delete).
SCHEMA_TRESOR = """
CREATE TABLE IF NOT EXISTS dokumente (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    titel       TEXT NOT NULL,
    typ         TEXT NOT NULL DEFAULT 'Sonstiges',
    datei_pfad  TEXT NOT NULL,            -- relativ zum Vault-Wurzelpfad
    datei_name  TEXT NOT NULL,            -- Anzeigename (Basename, ohne UUID)
    groesse     INTEGER NOT NULL DEFAULT 0,
    erstellt_am TEXT NOT NULL,            -- fachliches Ablagedatum (= Upload-Zeit)
    tags        TEXT NOT NULL DEFAULT '[]',  -- JSON-Liste
    notiz       TEXT NOT NULL DEFAULT '',
    archiv_flag INTEGER NOT NULL DEFAULT 0,
    inbox_flag  INTEGER NOT NULL DEFAULT 0,  -- 1 = im Posteingang, wartet auf Review (P2)
    steuer_relevant INTEGER NOT NULL DEFAULT 0,  -- ELSTER/Beleg-Markierung (P3)
    sha256      TEXT,                     -- Dedupe (v2)
    volltext    TEXT NOT NULL DEFAULT '', -- extrahierter Text (v2)
    volltext_methode TEXT NOT NULL DEFAULT '',  -- docx|txt|pdf:pypdf|ocr:tesseract|keiner
    quelle      TEXT NOT NULL DEFAULT 'upload', -- upload|folder|imap|scan
    korrespondent TEXT NOT NULL DEFAULT '',  -- Absender/Partner (Paperless-Konzept, P1a-Facette)
    ki_vorschlag TEXT NOT NULL DEFAULT '',   -- A4: gespeicherter KI-Klassifikations-Vorschlag (JSON), HITL
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_dokumente ON dokumente (user_id, created_at);
-- idx_dokumente_sha (auf der v2-Spalte sha256) wird in _migrate() NACH dem ALTER
-- angelegt: sonst scheitert executescript auf einer v1-Bestands-DB an der noch
-- fehlenden Spalte und der App-Start bricht ab (Restart-Block bei Alt-DBs).
CREATE VIRTUAL TABLE IF NOT EXISTS dokumente_fts USING fts5(
    dok_id UNINDEXED, titel, notiz, tags, volltext,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS dokument_verknuepfungen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    dok_id      TEXT NOT NULL,             -- lokales Dokument (Ziel des Beleg-Links)
    von_app     TEXT NOT NULL,             -- verknüpfende App (z. B. finanzen)
    von_ref     TEXT NOT NULL,             -- Referenz beim Absender (z. B. finanzen:buchung:42)
    von_titel   TEXT NOT NULL DEFAULT '',  -- menschenlesbar (z. B. Buchungstext)
    notiz       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    deleted_at  TEXT,
    UNIQUE (user_id, von_ref, dok_id)
);
CREATE INDEX IF NOT EXISTS idx_dok_verkn ON dokument_verknuepfungen (user_id, dok_id);
"""

# Spalten, die einer v1-Bestands-DB per ALTER nachgerüstet werden (Migration).
_NEUE_SPALTEN = (
    "ALTER TABLE dokumente ADD COLUMN sha256 TEXT",
    "ALTER TABLE dokumente ADD COLUMN volltext TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE dokumente ADD COLUMN volltext_methode TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE dokumente ADD COLUMN quelle TEXT NOT NULL DEFAULT 'upload'",
    "ALTER TABLE dokumente ADD COLUMN korrespondent TEXT NOT NULL DEFAULT ''",  # P1a
    "ALTER TABLE dokumente ADD COLUMN inbox_flag INTEGER NOT NULL DEFAULT 0",   # P2
    "ALTER TABLE dokumente ADD COLUMN steuer_relevant INTEGER NOT NULL DEFAULT 0",  # P3
    "ALTER TABLE dokumente ADD COLUMN verschluesselt INTEGER NOT NULL DEFAULT 0",  # Phase 6: Fernet-at-rest
    "ALTER TABLE dokumente ADD COLUMN fach TEXT NOT NULL DEFAULT ''",              # Phase 6: kategorisiertes Fach
    "ALTER TABLE dokumente ADD COLUMN ki_vorschlag TEXT NOT NULL DEFAULT ''",      # A4: KI-Klassifikation beim Upload
)

# Extra-Sicherheitsstufe (docs/28 §6): Lesen verschlüsselter Dokumente verlangt
# mindestens diese Dizzi-ID-Stufe (Step-up über das normale lokale Gate hinaus).
TRESOR_LESE_STUFE = "verifiziert"

# P3 — gesetzliche Aufbewahrungsfristen je Dokumenttyp (Jahre, DE/GoBD-Orientierung;
# rein INFORMATIV: steuert die Anzeige „aufbewahren bis", löscht nichts).
RETENTION_JAHRE = {"Rechnung": 10, "Steuer": 10, "Vertrag": 10, "Sonstiges": 3}


def aufbewahrung_bis(typ: str, erstellt_am: str) -> str:
    """Aufbewahren-bis-Jahr (Ende des Jahres + Aufbewahrungsfrist). '' wenn unbekannt."""
    jahr = (erstellt_am or "")[:4]
    if not jahr.isdigit():
        return ""
    return str(int(jahr) + RETENTION_JAHRE.get(typ, 3))


# --- Request-Modelle: MODUL-Ebene zwingend (PEP-563-Falle, s. refapp/README) -
class DokumentPatch(BaseModel):
    titel: str | None = None
    typ: str | None = None
    tags: list[str] | None = None
    notiz: str | None = None
    korrespondent: str | None = None
    archiv_flag: bool | None = None
    inbox_flag: bool | None = None
    steuer_relevant: bool | None = None


class VerknuepfungEmpfangIn(BaseModel):
    """V15-Empfang (docs/26 §12): eine App (v1: Money) meldet einen Beleg-Link auf
    ein Admin-Dokument. ``ziel_ref`` = ``admin:dokument:<id>``."""
    von_app: str = ""
    von_ref: str = ""          # z. B. finanzen:buchung:42
    von_titel: str = ""
    ziel_ref: str = ""         # admin:dokument:<id>
    notiz: str = ""
    aktion: str = "anlegen"    # anlegen | loesen (Quelle storniert ⇒ Rück-Ref räumen)


class UploadAbgelehnt(Exception):
    """Domänen-Fehler des Einzug-Kerns. Der HTTP-Upload mappt ihn auf den HTTP-
    Code; DocumentSource-Adapter zählen ihn als Fehler (kein HTTP im Hintergrund)."""

    def __init__(self, code: int, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(detail)


def heute_iso() -> str:
    return date.today().isoformat()


def _safe_name(roh: str) -> str:
    """Dateinamen entschärfen — Pfad-Traversal & Sonderzeichen ausschließen.
    Nimmt NUR den Basisnamen (kein Verzeichnisanteil, weder / noch \\),
    streicht führende Punkte und ersetzt alles außerhalb [A-Za-z0-9._-]."""
    basis = roh.replace("\\", "/").split("/")[-1].strip().lstrip(".")
    basis = re.sub(r"[^A-Za-z0-9._-]", "_", basis)
    return basis or "datei"


def _tagtext(tags: Any) -> str:
    """Tags (Liste ODER JSON-String) → Leerzeichen-getrennter Text für den Index."""
    if isinstance(tags, str):
        try:
            tags = json.loads(tags or "[]")
        except ValueError:
            tags = [tags]
    return " ".join(str(t) for t in (tags or []))


def _fts_query(suche: str) -> str:
    """FTS5-MATCH aus Nutzereingabe: je Token Prefix-Suche (implizites AND).
    Tokens sind \\w+ (keine FTS-Sonderzeichen) ⇒ ohne Quoting sicher."""
    toks = re.findall(r"\w+", suche or "", flags=re.UNICODE)
    return " ".join(f"{t}*" for t in toks)


class TresorDomain:
    """Bündelt Router + Kennzahl-/Wächter-Funktionen der Admin-Domäne.
    ``vault``/``registry`` werden von main.py gesetzt bzw. injiziert
    (Tresor = appkit-Instanz, Registry = HITL-Aktionen)."""

    def __init__(self, db: Database, vault_root: Path,
                 max_upload_bytes: int = MAX_UPLOAD_BYTES,
                 archiv_post=None, memory_get=None, ki_post=None) -> None:
        self.db = db
        self.vault_root = Path(vault_root)
        self.max_upload_bytes = max_upload_bytes
        self.archiv_post = archiv_post     # Querverbindungs-POST (V7 Admin→Memory)
        self.memory_get = memory_get       # Memory-Rück-Lese GET (v3, injizierbar)
        self.ki_post = ki_post             # Ollama-POST für KI-Klassifikation (P2, injizierbar)
        self.vault = None                  # appkit-Vault, von main.py gesetzt
        self._migrate()
        self.router = self._build_router()

    # --- Migration v1→v2 (additive Spalten + FTS-Backfill) ------------------
    def _migrate(self) -> None:
        conn = self.db.get_conn()          # legt frisches Schema an (inkl. v2-Spalten)
        for ddl in _NEUE_SPALTEN:
            try:
                conn.execute(ddl)          # Bestands-DB nachrüsten
            except sqlite3.OperationalError:
                pass                       # Spalte existiert schon (frische DB)
        conn.commit()
        # Index auf der v2-Spalte sha256 ERST hier (nach dem ALTER) — gehört bewusst
        # NICHT ins SCHEMA, sonst scheitert executescript auf einer v1-DB.
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dokumente_sha "
                         "ON dokumente (user_id, sha256)")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        try:                               # FTS-Backfill für Bestands-Dokumente
            n_fts = conn.execute("SELECT COUNT(*) AS n FROM dokumente_fts").fetchone()["n"]
            if n_fts == 0:
                rows = conn.execute(
                    "SELECT id, titel, notiz, tags, volltext FROM dokumente "
                    "WHERE deleted_at IS NULL").fetchall()
                for d in rows:
                    self._fts_insert(conn, d["id"], d["titel"], d["notiz"],
                                     d["tags"], d["volltext"] or "")
                conn.commit()
        except sqlite3.OperationalError:
            pass

    # --- FTS-Synchronisation ------------------------------------------------
    def _fts_insert(self, conn, dok_id, titel, notiz, tags, volltext) -> None:
        conn.execute(
            "INSERT INTO dokumente_fts (dok_id, titel, notiz, tags, volltext) "
            "VALUES (?,?,?,?,?)",
            (dok_id, titel or "", notiz or "", _tagtext(tags), volltext or ""))

    def _fts_delete(self, conn, dok_id) -> None:
        conn.execute("DELETE FROM dokumente_fts WHERE dok_id=?", (dok_id,))

    def _fts_update(self, conn, dok_id, titel, notiz, tags, volltext) -> None:
        self._fts_delete(conn, dok_id)
        self._fts_insert(conn, dok_id, titel, notiz, tags, volltext)

    # --- Kennzahlen (Kachel + /api/stats + MCP admin_kachel_stats) ----------
    def stats(self, user_id: str) -> dict[str, int]:
        conn = self.db.get_conn()
        n_dok = conn.execute(
            "SELECT COUNT(*) AS n FROM dokumente WHERE user_id=? AND deleted_at IS NULL",
            (user_id,)).fetchone()["n"]
        n_offen = conn.execute(
            "SELECT COUNT(*) AS n FROM aufgaben WHERE user_id=? AND deleted_at IS NULL "
            "AND status!='erledigt'", (user_id,)).fetchone()["n"]
        n_heute = conn.execute(
            "SELECT COUNT(*) AS n FROM aufgaben WHERE user_id=? AND deleted_at IS NULL "
            "AND status!='erledigt' AND faellig=?", (user_id, heute_iso())).fetchone()["n"]
        n_inbox = conn.execute(
            "SELECT COUNT(*) AS n FROM dokumente WHERE user_id=? AND deleted_at IS NULL "
            "AND inbox_flag=1", (user_id,)).fetchone()["n"]
        return {"dokumente_gesamt": n_dok, "aufgaben_offen": n_offen,
                "aufgaben_heute_faellig": n_heute, "inbox_offen": n_inbox}

    def summary(self, user_id: str = "dizzi") -> list[Kpi]:
        s = self.stats(user_id)
        return [
            Kpi(id="dokumente", label="Dokumente", value=s["dokumente_gesamt"], unit="Stk"),
            Kpi(id="inbox_offen", label="Posteingang", value=s["inbox_offen"]),
        ]

    def ki_kontext(self, user_id: str) -> dict[str, Any]:
        """Kontext für die App-KI: die letzten 10 Dokument-Titel + offene Aufgaben."""
        conn = self.db.get_conn()
        dok = [r["titel"] for r in conn.execute(
            "SELECT titel FROM dokumente WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 10", (user_id,)).fetchall()]
        auf = [{"titel": r["titel"], "faellig": r["faellig"],
                "status": r["status"], "prioritaet": r["prioritaet"]}
               for r in conn.execute(
                   "SELECT titel, faellig, status, prioritaet FROM aufgaben "
                   "WHERE user_id=? AND deleted_at IS NULL AND status!='erledigt' "
                   "ORDER BY (faellig='') ASC, faellig ASC LIMIT 20", (user_id,)).fetchall()]
        return {"dokumente": dok, "aufgaben": auf}

    # --- A4: KI-Klassifikation (Vorschlag, HITL) ----------------------------
    def _ki_vorschlag_json(self, user_id: str, titel: str, volltext: str,
                           vorhandene_tags: list) -> tuple[str, bool]:
        """Ruft die lokale KI-Klassifikation (tresor_ki) und serialisiert den Vorschlag
        (Typ aus DOK_TYPEN · Korrespondent · NEUE Tags). Liefert ``("", False)`` wenn
        die KI nichts Brauchbares meldet (kein Vorschlag ⇒ kein Posteingang-Zwang)."""
        from . import tresor_ki as _ki
        vor = _ki.klassifiziere(titel, volltext, http_post=self.ki_post)
        if not vor:
            return "", False
        typ_v = vor.get("typ") if vor.get("typ") in DOK_TYPEN else ""
        tags_v = [t for t in (vor.get("tags") or []) if t and t not in (vorhandene_tags or [])]
        korr = (vor.get("korrespondent") or "").strip()
        if not (typ_v or tags_v or korr):
            return "", False
        return json.dumps({"typ": typ_v, "korrespondent": korr, "tags": tags_v,
                           "quelle": "ki"}, ensure_ascii=False), True

    # --- Einzug-Kern (Upload UND DocumentSources teilen ihn) ----------------
    def _fernet(self):
        """Fernet-Schlüssel der Tresor-Verschlüsselung — liegt im appkit-Vault
        (OS-Secret-Store, selbst Fernet-verschlüsselt), NIE in der DB. Wird beim
        ersten verschlüsselten Dokument erzeugt (docs/28 §6)."""
        from cryptography.fernet import Fernet
        if self.vault is None:
            raise UploadAbgelehnt(500, "Tresor-Schlüsselspeicher nicht verfügbar.")
        key = self.vault.get("tresor_fernet_key")
        if not key:
            key = Fernet.generate_key().decode()
            self.vault.put("tresor_fernet_key", key)
        return Fernet(key.encode())

    def speichere_dokument(self, user_id: str, daten: bytes, dateiname: str, *,
                           titel: str = "", typ: str = "Sonstiges",
                           tags: Any = None, notiz: str = "",
                           korrespondent: str = "", quelle: str = "upload",
                           verschluesselt: bool = False, fach: str = "") -> dict[str, Any]:
        """Härtet (Typ/Größe/Traversal), dedupiert (SHA-256), legt im Vault ab,
        extrahiert Volltext und indexiert (FTS5). ``UploadAbgelehnt`` bei Verstoß."""
        safe = _safe_name(dateiname or "datei")
        ext = Path(safe).suffix.lower()
        if ext not in ALLOWED_EXT:
            raise UploadAbgelehnt(415, f"Dateityp '{ext or '?'}' nicht erlaubt "
                                       f"(zulässig: {', '.join(sorted(ALLOWED_EXT))}).")
        if len(daten) > self.max_upload_bytes:
            raise UploadAbgelehnt(413, "Datei zu groß "
                                       f"(max. {self.max_upload_bytes // (1024 * 1024)} MB).")
        sha = hashlib.sha256(daten).hexdigest()
        conn = self.db.get_conn()
        vorhanden = conn.execute(
            "SELECT id FROM dokumente WHERE user_id=? AND sha256=? AND deleted_at IS NULL",
            (user_id, sha)).fetchone()
        if vorhanden:                      # identische Datei ⇒ kein Duplikat
            return {"ok": True, "id": vorhanden["id"], "dedupe": True,
                    "datei_name": safe, "gespeichert_als": None}

        user_dir = self.vault_root / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        stored = f"{new_id()}_{safe}"
        ziel = (user_dir / stored).resolve()
        if not ziel.is_relative_to(user_dir.resolve()):     # Defense-in-Depth
            raise UploadAbgelehnt(400, "Ungültiger Zielpfad.")
        # Extra-Sicherheit (docs/28 §6): verschlüsselte Fächer legen die Datei
        # Fernet-verschlüsselt at-rest ab; der Volltext wird NICHT extrahiert/indexiert
        # (Inhalt bleibt verschlossen — nur Titel/Tags bleiben auffindbar).
        if verschluesselt:
            atomic_write_bytes(ziel, self._fernet().encrypt(daten))
            volltext, methode = "", "verschluesselt"
        else:
            atomic_write_bytes(ziel, daten)
            volltext, methode = extract.extrahiere_text(daten, ext)
        typ_ok = typ if typ in DOK_TYPEN else "Sonstiges"
        tag_liste = (tags if isinstance(tags, list)
                     else [t.strip() for t in (tags or "").split(",") if t.strip()])
        anzeige_titel = (titel or "").strip() or Path(safe).stem
        rel = f"{user_id}/{stored}"
        # A4: KI-Klassifikation beim Einzug (opt-in Setting, lokales Ollama). Speichert
        # NUR einen Vorschlag (Typ/Korrespondent/Tags) — wird NIE automatisch angewendet
        # (HITL); ein Vorschlag schiebt das Dokument in den Posteingang zur Bestätigung.
        # Verschlüsselte Dokumente bleiben außen vor (kein Klartext für die KI).
        ki_vorschlag_json = ""
        ki_inbox = False
        if (not verschluesselt
                and self.db.setting_get(user_id, "ki_klassifikation_upload", False)):
            ki_vorschlag_json, ki_inbox = self._ki_vorschlag_json(
                user_id, anzeige_titel, volltext, tag_liste)
        # P2: aus Quellen (Ordner/IMAP/Scan) eingezogene Dokumente landen im Posteingang
        # (Review nötig); manuell Hochgeladenes ist kuratiert — außer die KI hat etwas
        # vorgeschlagen (A4), dann ebenfalls in den Posteingang zur Bestätigung.
        inbox = 1 if (quelle != "upload" or ki_inbox) else 0
        steuer = 1 if typ_ok in ("Rechnung", "Steuer") else 0   # P3: Default-Markierung
        ts = now_iso()
        dok_id = new_id()
        conn.execute(
            "INSERT INTO dokumente (id, user_id, titel, typ, datei_pfad, datei_name, "
            "groesse, erstellt_am, tags, notiz, archiv_flag, inbox_flag, steuer_relevant, "
            "sha256, volltext, volltext_methode, quelle, korrespondent, verschluesselt, fach, "
            "ki_vorschlag, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?)",
            (dok_id, user_id, anzeige_titel, typ_ok, rel, safe, len(daten), ts,
             json.dumps(tag_liste, ensure_ascii=False), notiz.strip(), inbox, steuer, sha, volltext,
             methode, quelle, (korrespondent or "").strip(),
             1 if verschluesselt else 0, (fach or "").strip(), ki_vorschlag_json, ts, ts))
        self._fts_insert(conn, dok_id, anzeige_titel, notiz.strip(), tag_liste, volltext)
        conn.commit()
        self.db.audit(user_id, "user" if quelle == "upload" else "system",
                      "dokument_hochgeladen",
                      {"typ": typ_ok, "groesse": len(daten), "quelle": quelle,
                       "volltext": methode, "ki_vorschlag": bool(ki_vorschlag_json)})
        return {"ok": True, "id": dok_id, "titel": anzeige_titel, "typ": typ_ok,
                "gespeichert_als": stored, "datei_name": safe,
                "volltext_methode": methode, "dedupe": False,
                "ki_vorschlag": json.loads(ki_vorschlag_json) if ki_vorschlag_json else None}

    def on_delete(self, user_id: str) -> dict[str, Any]:
        """H-7-Hook (appkit 1.11): nach der DB-Lösch-Kaskade die EXTERNEN Artefakte
        räumen — Vault-Verzeichnis des Nutzers + FTS-Index-Zeilen. DSGVO „weg = weg".
        Best-effort; appkit auditiert das Ergebnis (``artefakte_geraeumt``)."""
        import shutil
        conn = self.db.get_conn()
        try:                                   # FTS-Zeilen der Nutzer-Dokumente entfernen
            for row in conn.execute("SELECT id FROM dokumente WHERE user_id=?",
                                    (user_id,)).fetchall():
                self._fts_delete(conn, row["id"])
            conn.commit()
        except sqlite3.OperationalError:
            pass
        dateien = 0
        user_dir = self.vault_root / user_id
        if user_dir.is_dir():
            dateien = sum(1 for p in user_dir.rglob("*") if p.is_file())
            shutil.rmtree(user_dir, ignore_errors=True)
        # Phase 6: den Tresor-Fernet-Schlüssel mit-räumen (DSGVO „weg = weg" —
        # ohne Schlüssel sind etwaige Krypto-Reste ohnehin unlesbar).
        schluessel_weg = bool(self.vault is not None and self.vault.delete("tresor_fernet_key"))
        return {"vault_dateien_geloescht": dateien, "fts_geraeumt": True,
                "krypto_schluessel_geloescht": schluessel_weg}

    # --- Helfer -------------------------------------------------------------
    def _dok_row(self, conn, user_id: str, dok_id: str):
        return conn.execute(
            "SELECT * FROM dokumente WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (dok_id, user_id)).fetchone()

    def _dok_public(self, r) -> dict[str, Any]:
        vt = r["volltext"] or ""
        keys = r.keys()
        out = {"id": r["id"], "titel": r["titel"], "typ": r["typ"],
               "datei_name": r["datei_name"], "groesse": r["groesse"],
               "erstellt_am": r["erstellt_am"], "tags": json.loads(r["tags"] or "[]"),
               "notiz": r["notiz"], "archiv_flag": bool(r["archiv_flag"]),
               "inbox_flag": bool(r["inbox_flag"]) if "inbox_flag" in keys else False,
               "steuer_relevant": bool(r["steuer_relevant"]) if "steuer_relevant" in keys else False,
               "aufbewahren_bis": aufbewahrung_bis(r["typ"], r["erstellt_am"]),
               "quelle": r["quelle"], "volltext_methode": r["volltext_methode"],
               "korrespondent": (r["korrespondent"] if "korrespondent" in keys else "") or "",
               "verschluesselt": bool(r["verschluesselt"]) if "verschluesselt" in keys else False,
               "fach": (r["fach"] if "fach" in keys else "") or "",
               "bereich_id": (r["bereich_id"] if "bereich_id" in keys else "") or "",
               "ist_bild": Path(r["datei_name"] or "").suffix.lower() in _BILD_EXT,
               "volltext_vorschau": vt[:160], "created_at": r["created_at"]}
        if "ki_vorschlag" in keys and (r["ki_vorschlag"] or "").strip():   # A4: KI-Vorschlag (HITL)
            try:
                out["ki_vorschlag"] = json.loads(r["ki_vorschlag"])
            except ValueError:
                out["ki_vorschlag"] = None
        if "schnipsel" in keys and r["schnipsel"]:        # FTS-Trefferschnipsel (v3)
            out["schnipsel"] = r["schnipsel"]
        if "rang" in keys and r["rang"] is not None:      # bm25-Relevanz (kleiner = besser)
            out["rang"] = round(float(r["rang"]), 3)
        return out

    def _archiviere_dokument(self, user_id: str, dok_id: str,
                             explizit: bool = False) -> dict[str, Any]:
        """Reicht die METADATEN eines Dokuments (Typ/Datei/Notiz/Volltext-Auszug)
        als Notiz an Dizz Memory weiter (Core-Relay, V7 docs/26) — die Binärdatei
        bleibt im Admin-Vault (wie V3 Creating). Archiv-Regel je (admin, dokument)
        gated; ``explizit`` (Nutzer-Knopf) schlägt jede Regel. Best-effort (wirft
        nie). Herkunftslabel „Admin" vergibt Memory zentral (§9.1); die nutzer-
        kuratierten Dokument-Tags reisen mit. Steuer/Vertrag ⇒ ``sensibel``."""
        from appkit.querverbindung import archiviere
        row = self._dok_row(self.db.get_conn(), user_id, dok_id)
        if row is None:
            return {"ok": False, "fehler": "Dokument unbekannt"}
        tags = json.loads(row["tags"] or "[]")
        kb = round((row["groesse"] or 0) / 1024)
        zeilen = [f"**Typ:** {row['typ']} · **Datei:** {row['datei_name']} · {kb} KB · "
                  f"**Ablage:** {row['erstellt_am']} · **Quelle:** {row['quelle']}"]
        if (row["notiz"] or "").strip():
            zeilen += ["", row["notiz"].strip()]
        volltext = (row["volltext"] or "").strip()
        if volltext:
            zeilen += ["", "## Volltext-Auszug", volltext[:1500]]
        inhalt = "\n".join(zeilen).strip()
        sensibel = row["typ"] in ("Steuer", "Vertrag")
        return archiviere("admin", "Dokument · " + row["titel"], inhalt,
                          strom="dokument", ref="admin:dokument:" + dok_id,
                          quelle="admin:dokument:" + dok_id, tags=tags,
                          sensibel=sensibel, explizit=explizit,
                          http_post=self.archiv_post)

    def _build_router(self) -> APIRouter:
        r = APIRouter()
        db = self.db

        # ===================== DOKUMENTE ====================================
        @r.post("/api/dokumente/upload")
        async def dok_upload(
                datei: UploadFile = File(...),
                titel: str = Form(""),
                typ: str = Form("Sonstiges"),
                tags: str = Form(""),
                notiz: str = Form(""),
                korrespondent: str = Form(""),
                verschluesselt: str = Form("0"),
                fach: str = Form(""),
                user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Datei-Einzug in den Vault. Härtung: Typ-Whitelist (415, früh),
            Größenlimit (413, früh-abbrechend), Pfad-Traversal abgewehrt, Dedupe.
            ``verschluesselt=1`` legt die Datei Fernet-verschlüsselt ab (docs/28 §6)."""
            safe = _safe_name(datei.filename or "datei")
            if Path(safe).suffix.lower() not in ALLOWED_EXT:
                raise HTTPException(415, f"Dateityp nicht erlaubt "
                                         f"(zulässig: {', '.join(sorted(ALLOWED_EXT))}).")
            daten = bytearray()            # Größe früh begrenzen (kein OOM)
            while True:
                chunk = await datei.read(1 << 20)
                if not chunk:
                    break
                daten += chunk
                if len(daten) > self.max_upload_bytes:
                    raise HTTPException(413, "Datei zu groß "
                                             f"(max. {self.max_upload_bytes // (1024 * 1024)} MB).")
            try:
                return self.speichere_dokument(
                    user.user_id, bytes(daten), datei.filename or safe,
                    titel=titel, typ=typ, tags=tags, notiz=notiz,
                    korrespondent=korrespondent, quelle="upload",
                    verschluesselt=verschluesselt in ("1", "true", "on"), fach=fach)
            except UploadAbgelehnt as e:
                raise HTTPException(e.code, e.detail)

        @r.get("/api/dokumente")
        def dok_liste(typ: str = "", suche: str = "", archiv: str = "", tag: str = "",
                      korrespondent: str = "", jahr: str = "", inbox: str = "", steuer: str = "",
                      bereich_id: str | None = None,
                      user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            conn = db.get_conn()
            where = ["d.user_id=?", "d.deleted_at IS NULL"]
            params: list[Any] = [user.user_id]
            if bereich_id is not None:                     # None=alle · ''=nur „Allgemein" · id=Bereich
                where.append("d.bereich_id=?"); params.append(bereich_id)
            if inbox in ("0", "1"):                        # P2: Posteingang-Filter
                where.append("d.inbox_flag=?"); params.append(int(inbox))
            if steuer in ("0", "1"):                       # P3: steuerrelevant-Filter
                where.append("d.steuer_relevant=?"); params.append(int(steuer))
            if typ:
                where.append("d.typ=?"); params.append(typ)
            if korrespondent:                              # P1a-Facette
                where.append("d.korrespondent=?"); params.append(korrespondent)
            if jahr:                                       # P1a-Facette (Ablagejahr)
                where.append("substr(d.erstellt_am,1,4)=?"); params.append(jahr)
            if archiv in ("0", "1"):
                where.append("d.archiv_flag=?"); params.append(int(archiv))
            if tag:                                        # Tag-Filter (json_each über die Tag-Liste)
                where.append("EXISTS (SELECT 1 FROM json_each(d.tags) WHERE json_each.value=?)")
                params.append(tag)
            select, join, order = "SELECT d.*", "", " ORDER BY d.created_at DESC"
            if suche:
                fq = _fts_query(suche)
                if fq:                                     # v3: bm25-Ranking + Trefferschnipsel
                    join = " JOIN dokumente_fts ON dokumente_fts.dok_id=d.id "
                    select = ("SELECT d.*, "
                              "snippet(dokumente_fts, -1, '‹', '›', '…', 8) AS schnipsel, "
                              "bm25(dokumente_fts) AS rang")
                    where.append("dokumente_fts MATCH ?"); params.append(fq)
                    order = " ORDER BY bm25(dokumente_fts)"
                else:                                      # nur Sonderzeichen ⇒ LIKE
                    where.append("(d.titel LIKE ? OR d.notiz LIKE ? OR d.volltext LIKE ?)")
                    like = f"%{suche}%"; params += [like, like, like]
            sql = f"{select} FROM dokumente d{join} WHERE " + " AND ".join(where) + order
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:               # FTS/JSON-Query unbrauchbar ⇒ LIKE
                like = f"%{suche}%"
                bsql = "" if bereich_id is None else " AND d.bereich_id=?"
                bargs = [] if bereich_id is None else [bereich_id]
                rows = conn.execute(
                    "SELECT d.* FROM dokumente d WHERE d.user_id=? AND d.deleted_at IS NULL "
                    "AND (d.titel LIKE ? OR d.notiz LIKE ? OR d.volltext LIKE ?)" + bsql +
                    " ORDER BY d.created_at DESC",
                    (user.user_id, like, like, like, *bargs)).fetchall()
            return [self._dok_public(r_) for r_ in rows]

        @r.get("/api/tags")
        def tags_cloud(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            """Tag-Wolke: alle vergebenen Tags mit Häufigkeit (für Filter/Übersicht)."""
            from collections import Counter
            zaehler: Counter = Counter()
            for row in db.get_conn().execute(
                    "SELECT tags FROM dokumente WHERE user_id=? AND deleted_at IS NULL",
                    (user.user_id,)).fetchall():
                for t in json.loads(row["tags"] or "[]"):
                    if str(t).strip():
                        zaehler[str(t)] += 1
            return [{"tag": t, "anzahl": n} for t, n in zaehler.most_common()]

        @r.get("/api/facetten")
        def facetten(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Facetten-Zähler (Typ · Korrespondent · Jahr · Tags) für die Archiv-
            Filter (P1a, Paperless-Muster). Jeweils Wert + Häufigkeit."""
            from collections import Counter
            c_typ, c_korr, c_jahr, c_tag = Counter(), Counter(), Counter(), Counter()
            for row in db.get_conn().execute(
                    "SELECT typ, korrespondent, erstellt_am, tags FROM dokumente "
                    "WHERE user_id=? AND deleted_at IS NULL", (user.user_id,)).fetchall():
                c_typ[row["typ"] or "Sonstiges"] += 1
                if (row["korrespondent"] or "").strip():
                    c_korr[row["korrespondent"]] += 1
                jahr = (row["erstellt_am"] or "")[:4]
                if jahr.isdigit():
                    c_jahr[jahr] += 1
                for t in json.loads(row["tags"] or "[]"):
                    if str(t).strip():
                        c_tag[str(t)] += 1

            def _liste(c, nach_wert=False):
                items = (sorted(c.items(), reverse=True) if nach_wert else c.most_common())
                return [{"wert": k, "anzahl": v} for k, v in items]
            return {"typ": _liste(c_typ), "korrespondent": _liste(c_korr),
                    "jahr": _liste(c_jahr, nach_wert=True), "tags": _liste(c_tag)}

        @r.get("/api/steuer/uebersicht")
        def steuer_uebersicht(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """P3 ELSTER-Vorbereitung: steuerrelevante Dokumente je Jahr (Beleg-Sammlung
            für die Steuererklärung) + die Aufbewahrungsfristen-Tabelle (informativ)."""
            from collections import Counter
            jahre: Counter = Counter()
            for r_ in db.get_conn().execute(
                    "SELECT erstellt_am FROM dokumente WHERE user_id=? AND deleted_at IS NULL "
                    "AND steuer_relevant=1", (user.user_id,)).fetchall():
                j = (r_["erstellt_am"] or "")[:4]
                if j.isdigit():
                    jahre[j] += 1
            return {"jahre": [{"jahr": k, "anzahl": v} for k, v in sorted(jahre.items(), reverse=True)],
                    "gesamt": sum(jahre.values()), "retention_jahre": RETENTION_JAHRE}

        @r.get("/api/dokumente/{dok_id}/datei")
        def dok_datei(dok_id: str, user: UserContext = Depends(current_user)):
            """Datei-Download aus dem Vault — strikt user-scoped + Vault-gegrenzt.
            Verschlüsselte Dokumente verlangen die Step-up-Stufe (docs/28 §6) und
            werden erst beim Abruf entschlüsselt (Klartext liegt nie at-rest)."""
            row = self._dok_row(db.get_conn(), user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            voll = (self.vault_root / row["datei_pfad"]).resolve()
            if not voll.is_relative_to(self.vault_root.resolve()) or not voll.is_file():
                return JSONResponse({"error": "Datei fehlt"}, status_code=404)
            if "verschluesselt" in row.keys() and row["verschluesselt"]:
                if LEVELS.get(user.level, 0) < LEVELS[TRESOR_LESE_STUFE]:
                    return JSONResponse(
                        {"error": f"Verschlüsseltes Dokument — Step-up nötig (Stufe "
                                  f"'{TRESOR_LESE_STUFE}'). /auth/login?level={TRESOR_LESE_STUFE}"},
                        status_code=403)
                try:
                    klar = self._fernet().decrypt(voll.read_bytes())
                except Exception:                       # noqa: BLE001 — Schlüssel/Token defekt
                    return JSONResponse({"error": "Entschlüsselung fehlgeschlagen"}, status_code=500)
                db.audit(user.user_id, "user", "dokument_abgerufen",
                         {"id": dok_id, "verschluesselt": True})
                return Response(content=klar, media_type="application/octet-stream",
                                headers={"Content-Disposition":
                                         f'attachment; filename="{row["datei_name"]}"'})
            db.audit(user.user_id, "user", "dokument_abgerufen", {"id": dok_id})
            return FileResponse(str(voll), filename=row["datei_name"])

        @r.post("/api/dokumente/{dok_id}/verschluesseln")
        def dok_verschluesseln(dok_id: str, user: UserContext = Depends(current_user)):
            """Bestehendes Klartext-Dokument nachträglich Fernet-verschlüsseln (docs/28 §6):
            Datei verschlüsselt neu ablegen, Volltext aus dem Index nehmen. Schützen darf
            man jederzeit; das Entschlüsseln verlangt Step-up."""
            conn = db.get_conn()
            row = self._dok_row(conn, user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            if "verschluesselt" in row.keys() and row["verschluesselt"]:
                return {"ok": True, "verschluesselt": True, "schon": True}
            voll = (self.vault_root / row["datei_pfad"]).resolve()
            if not voll.is_relative_to(self.vault_root.resolve()) or not voll.is_file():
                return JSONResponse({"error": "Datei fehlt"}, status_code=404)
            atomic_write_bytes(voll, self._fernet().encrypt(voll.read_bytes()))
            conn.execute("UPDATE dokumente SET verschluesselt=1, volltext='', "
                         "volltext_methode='verschluesselt', updated_at=? WHERE id=? AND user_id=?",
                         (now_iso(), dok_id, user.user_id))
            self._fts_update(conn, dok_id, row["titel"], row["notiz"], row["tags"], "")
            conn.commit()
            db.audit(user.user_id, "user", "dokument_verschluesselt", {"id": dok_id})
            return {"ok": True, "verschluesselt": True}

        @r.post("/api/dokumente/{dok_id}/entschluesseln")
        def dok_entschluesseln(dok_id: str, user: UserContext = Depends(current_user)):
            """Verschlüsseltes Dokument zurück in Klartext — verlangt Step-up (der Inhalt
            wird wieder offengelegt). Volltext wird re-extrahiert + indexiert."""
            if LEVELS.get(user.level, 0) < LEVELS[TRESOR_LESE_STUFE]:
                return JSONResponse(
                    {"error": f"Step-up nötig (Stufe '{TRESOR_LESE_STUFE}'). "
                              f"/auth/login?level={TRESOR_LESE_STUFE}"}, status_code=403)
            conn = db.get_conn()
            row = self._dok_row(conn, user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            if not ("verschluesselt" in row.keys() and row["verschluesselt"]):
                return {"ok": True, "verschluesselt": False, "schon": True}
            voll = (self.vault_root / row["datei_pfad"]).resolve()
            if not voll.is_relative_to(self.vault_root.resolve()) or not voll.is_file():
                return JSONResponse({"error": "Datei fehlt"}, status_code=404)
            try:
                klar = self._fernet().decrypt(voll.read_bytes())
            except Exception:                       # noqa: BLE001 — Schlüssel/Token defekt
                return JSONResponse({"error": "Entschlüsselung fehlgeschlagen"}, status_code=500)
            atomic_write_bytes(voll, klar)
            volltext, methode = extract.extrahiere_text(
                klar, Path(row["datei_name"] or "").suffix.lower())
            conn.execute("UPDATE dokumente SET verschluesselt=0, volltext=?, volltext_methode=?, "
                         "updated_at=? WHERE id=? AND user_id=?",
                         (volltext, methode, now_iso(), dok_id, user.user_id))
            self._fts_update(conn, dok_id, row["titel"], row["notiz"], row["tags"], volltext)
            conn.commit()
            db.audit(user.user_id, "user", "dokument_entschluesselt", {"id": dok_id})
            return {"ok": True, "verschluesselt": False}

        @r.get("/api/dokumente/{dok_id}/thumb")
        def dok_thumb(dok_id: str, user: UserContext = Depends(current_user)):
            """Vorschaubild für Bild-Dokumente (JPG/PNG) via PIL. PDF/DOCX haben
            hier keinen Renderer ⇒ 404 ⇒ Frontend zeigt ein Typ-Icon (graceful)."""
            row = self._dok_row(db.get_conn(), user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            if "verschluesselt" in row.keys() and row["verschluesselt"]:
                return JSONResponse({"error": "Verschlüsseltes Dokument — keine Vorschau"},
                                    status_code=404)
            if Path(row["datei_name"] or "").suffix.lower() not in _BILD_EXT:
                return JSONResponse({"error": "kein Bild"}, status_code=404)
            voll = (self.vault_root / row["datei_pfad"]).resolve()
            if not voll.is_relative_to(self.vault_root.resolve()) or not voll.is_file():
                return JSONResponse({"error": "Datei fehlt"}, status_code=404)
            try:
                import io as _io
                from PIL import Image
                from fastapi.responses import Response as _Resp
                im = Image.open(voll)
                im.draft("RGB", (640, 640))                # schnelles Vorab-Downscale
                im = im.convert("RGB")
                im.thumbnail((320, 320))
                buf = _io.BytesIO()
                im.save(buf, format="JPEG", quality=80)
                return _Resp(content=buf.getvalue(), media_type="image/jpeg",
                             headers={"Cache-Control": "private, max-age=300"})
            except Exception:
                return JSONResponse({"error": "Vorschau fehlgeschlagen"}, status_code=404)

        @r.get("/api/dokumente/{dok_id}/buchungsvorschlag")
        def dok_buchung(dok_id: str, user: UserContext = Depends(current_user)):
            """Cross-Finanzen-SLOT (read-only Entwurf, NICHT aktiv): Buchungs-
            vorschlag aus einer Rechnung. Kein Push an Dizz Money."""
            row = self._dok_row(db.get_conn(), user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            from .integrationen import buchungsvorschlag
            return buchungsvorschlag(dict(row))

        @r.get("/api/dokumente/{dok_id}/elster")
        def dok_elster(dok_id: str, user: UserContext = Depends(current_user)):
            """ELSTER-Brücke-SLOT (dokumentiert, NICHT aktiv)."""
            row = self._dok_row(db.get_conn(), user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            from .integrationen import elster_referenz
            return elster_referenz(dict(row))

        @r.get("/api/dokumente/{dok_id}/money-status")
        def dok_money_status(dok_id: str, user: UserContext = Depends(current_user)):
            """Cross-Money **READ-ONLY**-SLOT (v3, NICHT aktiv): skizziert die
            Lese-Brücke „ist dieser Beleg in Dizz Money verbucht?". Löst NIEMALS
            eine Buchung/Echtgeld-Aktion aus."""
            row = self._dok_row(db.get_conn(), user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            from .integrationen import money_lese_bruecke
            return money_lese_bruecke(dict(row))

        @r.get("/api/dokumente/{dok_id}/tag-vorschlaege")
        def dok_tag_vorschlaege(dok_id: str, user: UserContext = Depends(current_user)):
            """Heuristische Tag-Vorschläge (Typ + Jahre + Schlagworte; 0 €, keine KI)."""
            row = self._dok_row(db.get_conn(), user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            from .integrationen import tag_vorschlaege
            dok = {"titel": row["titel"], "typ": row["typ"],
                   "tags": json.loads(row["tags"] or "[]"), "volltext": row["volltext"] or ""}
            return {"vorschlaege": tag_vorschlaege(dok)}

        @r.get("/api/dokumente/{dok_id}/ki-vorschlag")
        def dok_ki_vorschlag(dok_id: str, user: UserContext = Depends(current_user)):
            """P2-Review: KI-Vorschlag Typ/Korrespondent/Tags (lokales Ollama). Fällt
            auf die Heuristik zurück, wenn Ollama nichts Brauchbares liefert."""
            row = self._dok_row(db.get_conn(), user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            from . import tresor_ki as _ki
            from .integrationen import tag_vorschlaege
            vorhandene = json.loads(row["tags"] or "[]")
            res = _ki.klassifiziere(row["titel"], row["volltext"] or "", http_post=self.ki_post)
            heur = tag_vorschlaege({"titel": row["titel"], "typ": row["typ"],
                                    "tags": vorhandene, "volltext": row["volltext"] or ""})
            typ = res.get("typ") if res.get("typ") in DOK_TYPEN else ""
            tags = [t for t in (res.get("tags") or heur) if t not in vorhandene]
            db.audit(user.user_id, "ki", "dokument_ki_vorschlag",
                     {"id": dok_id, "quelle": "ki" if res else "heuristik"})
            return {"typ": typ, "korrespondent": res.get("korrespondent", ""),
                    "tags": tags, "quelle": "ki" if res else "heuristik"}

        @r.post("/api/dokumente/{dok_id}/vorschlag-uebernehmen")
        def dok_vorschlag_uebernehmen(dok_id: str,
                                      user: UserContext = Depends(current_user)):
            """A4-HITL: wendet den (beim Upload gespeicherten oder hier frisch
            berechneten) KI-Vorschlag an — Typ (falls gültig), Korrespondent (falls
            leer), Tags ergänzen — und räumt Vorschlag + Posteingang-Marke. Bewusst
            expliziter Klick (nie automatisch). Verschlüsselte Doks: kein On-demand-Lauf."""
            conn = db.get_conn()
            row = self._dok_row(conn, user.user_id, dok_id)
            if row is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            keys = row.keys()
            vor: dict[str, Any] = {}
            roh = (row["ki_vorschlag"] if "ki_vorschlag" in keys else "") or ""
            if roh:
                try:
                    vor = json.loads(roh)
                except ValueError:
                    vor = {}
            if not vor and not ("verschluesselt" in keys and row["verschluesselt"]):
                from . import tresor_ki as _ki    # kein gespeicherter Vorschlag ⇒ on-demand
                vor = _ki.klassifiziere(row["titel"], row["volltext"] or "", http_post=self.ki_post)
            if not vor:
                return JSONResponse({"error": "Kein KI-Vorschlag vorhanden."}, status_code=404)
            vorhandene = json.loads(row["tags"] or "[]")
            typ_neu = vor.get("typ") if vor.get("typ") in DOK_TYPEN else row["typ"]
            korr_neu = (vor.get("korrespondent") or "").strip() or \
                ((row["korrespondent"] if "korrespondent" in keys else "") or "")
            tags_neu = vorhandene + [t for t in (vor.get("tags") or [])
                                     if t and t not in vorhandene]
            steuer = 1 if typ_neu in ("Rechnung", "Steuer") else \
                (int(row["steuer_relevant"]) if "steuer_relevant" in keys else 0)
            conn.execute(
                "UPDATE dokumente SET typ=?, korrespondent=?, tags=?, steuer_relevant=?, "
                "ki_vorschlag='', inbox_flag=0, updated_at=? WHERE id=? AND user_id=?",
                (typ_neu, korr_neu, json.dumps(tags_neu, ensure_ascii=False), steuer,
                 now_iso(), dok_id, user.user_id))
            self._fts_update(conn, dok_id, row["titel"], row["notiz"], tags_neu,
                             row["volltext"] or "")
            conn.commit()
            db.audit(user.user_id, "user", "dokument_ki_uebernommen",
                     {"id": dok_id, "typ": typ_neu})
            return {"ok": True, "id": dok_id, "typ": typ_neu,
                    "korrespondent": korr_neu, "tags": tags_neu}

        @r.post("/api/dokumente/{dok_id}/archivieren")
        def dok_archivieren_ep(dok_id: str,
                               user: UserContext = Depends(current_user)):
            """„In Memory archivieren" (Nutzer-Zuruf): schickt die Dokument-
            Metadaten explizit an Dizz Memory — schlägt jede Archiv-Regel
            (V7, docs/26). Die Binärdatei bleibt im Admin-Vault."""
            if self._dok_row(db.get_conn(), user.user_id, dok_id) is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            ergebnis = self._archiviere_dokument(user.user_id, dok_id, explizit=True)
            db.audit(user.user_id, "user", "dokument_archiviert",
                     {"id": dok_id, "status": ergebnis.get("status")})
            return ergebnis

        # ===== V15: bidirektionaler Beleg-Link (Money↔Admin, docs/26 §12) =====
        @r.get("/api/belege")
        def belege_liste(q: str = "", limit: int = 50,
                         user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            """V15-LOOKUP: verknüpfbare Belege/Dokumente für die treibende App (Money).
            Liefert je Dokument einen stabilen ``ref`` (``admin:dokument:<id>``), Titel,
            Typ, Datum — daraus baut Money die Beleg-Auswahl. Read-only."""
            conn = db.get_conn()
            sql = ("SELECT id, titel, typ, erstellt_am FROM dokumente "
                   "WHERE user_id=? AND deleted_at IS NULL")
            params: list[Any] = [user.user_id]
            if (q or "").strip():
                like = f"%{q.strip()}%"
                sql += " AND (titel LIKE ? OR notiz LIKE ? OR volltext LIKE ?)"
                params += [like, like, like]
            sql += " ORDER BY erstellt_am DESC, created_at DESC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [{"ref": "admin:dokument:" + r_["id"], "titel": r_["titel"],
                     "typ": r_["typ"], "datum": r_["erstellt_am"]} for r_ in rows]

        @r.post("/api/querverbindung/verknuepfung")
        def verknuepfung_empfang(body: VerknuepfungEmpfangIn,
                                 user: UserContext = Depends(current_user)):
            """V15-EMPFANG: eine andere App (v1: Money) meldet, dass ``von_ref`` auf ein
            Admin-Dokument (``ziel_ref=admin:dokument:<id>``) zeigt. Admin legt die
            Rück-Referenz an. **Idempotent** (``von_ref × dok_id``), auditiert. Nur Daten."""
            ziel_ref = (body.ziel_ref or "").strip()
            praefix = "admin:dokument:"
            if not ziel_ref.startswith(praefix):
                return JSONResponse({"ok": False, "error": "ziel_ref ungültig"}, status_code=400)
            dok_id = ziel_ref[len(praefix):]
            von_ref = (body.von_ref or "").strip()
            if not von_ref:
                return JSONResponse({"ok": False, "error": "von_ref fehlt"}, status_code=400)
            conn = db.get_conn()
            # aktion="loesen": die Quelle (z. B. eine Buchung) wurde storniert/entkoppelt ⇒
            # die Rück-Referenz hart räumen, damit kein verwaister „verwendet in N"-Hinweis
            # bleibt. Idempotent + best-effort (unbekannte Verknüpfung ⇒ einfach „weg").
            if (body.aktion or "anlegen") == "loesen":
                cur = conn.execute(
                    "UPDATE dokument_verknuepfungen SET deleted_at=? WHERE user_id=? AND "
                    "von_ref=? AND dok_id=? AND deleted_at IS NULL",
                    (now_iso(), user.user_id, von_ref, dok_id))
                conn.commit()
                db.audit(user.user_id, "system", "verknuepfung_geloest",
                         {"dok_id": dok_id, "von_ref": von_ref, "anzahl": cur.rowcount})
                return {"ok": True, "status": "geloest", "anzahl": cur.rowcount}
            if self._dok_row(conn, user.user_id, dok_id) is None:
                return JSONResponse({"ok": False, "error": "Dokument unbekannt"}, status_code=404)
            vorhanden = conn.execute(
                "SELECT id FROM dokument_verknuepfungen WHERE user_id=? AND von_ref=? "
                "AND dok_id=? AND deleted_at IS NULL", (user.user_id, von_ref, dok_id)).fetchone()
            if vorhanden:
                return {"ok": True, "status": "vorhanden", "id": vorhanden["id"]}
            ts = now_iso()
            # Eine FRÜHER weich gelöschte Verknüpfung (gleiches von_ref × dok_id) wiederbeleben
            # statt neu anzulegen: das blanke INSERT kollidierte sonst mit UNIQUE(user_id,von_ref,
            # dok_id) (Beleg entfernt → erneut anknüpfen ⇒ HTTP 500 + Rück-Ref bliebe weg). Idiom
            # wie die Memory-Label-Reaktivierung (UPDATE deleted_at=NULL). Die LIVE-Prüfung oben ist
            # schon raus ⇒ ein Treffer hier ist garantiert weich gelöscht. (Audit-Runde 4, H-18.)
            geloescht = conn.execute(
                "SELECT id FROM dokument_verknuepfungen WHERE user_id=? AND von_ref=? AND dok_id=?",
                (user.user_id, von_ref, dok_id)).fetchone()
            if geloescht:
                vid = geloescht["id"]
                conn.execute(
                    "UPDATE dokument_verknuepfungen SET deleted_at=NULL, von_app=?, von_titel=?, "
                    "notiz=?, created_at=? WHERE id=?",
                    ((body.von_app or "").strip(), (body.von_titel or "").strip(),
                     (body.notiz or "").strip(), ts, vid))
            else:
                vid = new_id()
                conn.execute(
                    "INSERT INTO dokument_verknuepfungen (id, user_id, dok_id, von_app, von_ref, "
                    "von_titel, notiz, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (vid, user.user_id, dok_id, (body.von_app or "").strip(), von_ref,
                     (body.von_titel or "").strip(), (body.notiz or "").strip(), ts))
            conn.commit()
            db.audit(user.user_id, "system", "verknuepfung_empfangen",
                     {"dok_id": dok_id, "von_ref": von_ref, "von_app": body.von_app})
            return {"ok": True, "status": "verknuepft", "id": vid}

        @r.get("/api/verknuepfungen")
        def verknuepfungen_liste(dok_id: str = "",
                                 user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            """Verknüpfungen (für die UI „verwendet in N Buchungen"). Ohne ``dok_id``
            alle des Nutzers (eine Query ⇒ die UI baut eine dok_id→Liste-Map)."""
            conn = db.get_conn()
            sql = ("SELECT id, dok_id, von_app, von_ref, von_titel FROM dokument_verknuepfungen "
                   "WHERE user_id=? AND deleted_at IS NULL")
            params: list[Any] = [user.user_id]
            if (dok_id or "").strip():
                sql += " AND dok_id=?"; params.append(dok_id.strip())
            sql += " ORDER BY created_at DESC"
            return [dict(r_) for r_ in conn.execute(sql, tuple(params)).fetchall()]

        @r.delete("/api/verknuepfungen/{vid}")
        def verknuepfung_loeschen(vid: str, user: UserContext = Depends(current_user)):
            """Eine Beleg-Verknüpfung lösen (Soft-Delete; betrifft nur die Admin-Seite —
            die Quelle in Money bleibt unberührt)."""
            conn = db.get_conn()
            row = conn.execute("SELECT id FROM dokument_verknuepfungen WHERE id=? AND user_id=? "
                               "AND deleted_at IS NULL", (vid, user.user_id)).fetchone()
            if row is None:
                return JSONResponse({"error": "Verknüpfung unbekannt"}, status_code=404)
            conn.execute("UPDATE dokument_verknuepfungen SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), vid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "verknuepfung_geloescht", {"id": vid})
            return {"ok": True}

        @r.patch("/api/dokumente/{dok_id}")
        def dok_patch(dok_id: str, body: DokumentPatch,
                      user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if self._dok_row(conn, user.user_id, dok_id) is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            felder, werte = [], []
            if body.titel is not None:
                felder.append("titel=?"); werte.append(body.titel.strip())
            if body.typ is not None:
                felder.append("typ=?"); werte.append(body.typ if body.typ in DOK_TYPEN else "Sonstiges")
            if body.tags is not None:
                felder.append("tags=?"); werte.append(json.dumps(
                    [str(t).strip() for t in body.tags if str(t).strip()], ensure_ascii=False))
            if body.notiz is not None:
                felder.append("notiz=?"); werte.append(body.notiz.strip())
            if body.korrespondent is not None:
                felder.append("korrespondent=?"); werte.append(body.korrespondent.strip())
            if body.archiv_flag is not None:
                felder.append("archiv_flag=?"); werte.append(int(body.archiv_flag))
            if body.inbox_flag is not None:                # P2: Review abschließen ⇒ inbox_flag=false
                felder.append("inbox_flag=?"); werte.append(int(body.inbox_flag))
            if body.steuer_relevant is not None:           # P3: ELSTER-/Beleg-Markierung
                felder.append("steuer_relevant=?"); werte.append(int(body.steuer_relevant))
            if not felder:
                return {"ok": True, "id": dok_id}        # nichts zu ändern
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [dok_id, user.user_id]
            conn.execute(f"UPDATE dokumente SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            # FTS nachziehen (Titel/Notiz/Tags können sich geändert haben)
            row = self._dok_row(conn, user.user_id, dok_id)
            if row is not None:
                self._fts_update(conn, dok_id, row["titel"], row["notiz"],
                                 row["tags"], row["volltext"] or "")
            conn.commit()
            db.audit(user.user_id, "user", "dokument_geaendert", {"id": dok_id})
            return {"ok": True, "id": dok_id}

        @r.delete("/api/dokumente/{dok_id}")
        def dok_delete(dok_id: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if self._dok_row(conn, user.user_id, dok_id) is None:
                return JSONResponse({"error": "Dokument unbekannt"}, status_code=404)
            conn.execute("UPDATE dokumente SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), dok_id, user.user_id))
            self._fts_delete(conn, dok_id)               # aus dem Index nehmen
            conn.commit()
            db.audit(user.user_id, "user", "dokument_geloescht", {"id": dok_id})
            return {"ok": True, "id": dok_id}

        # ===================== QUELLEN (DocumentSource-Adapter) =============
        @r.get("/api/dokument-quellen")
        def quellen_status(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Konfigurations-/Verfügbarkeits-Übersicht der Einzugsquellen."""
            sg = db.setting_get
            return {
                "ordner": {"pfad": sg(user.user_id, "watch_ordner", ""),
                           "aktiv": bool(sg(user.user_id, "watch_aktiv", False))},
                "imap": {"host": sg(user.user_id, "imap_host", ""),
                         "user": sg(user.user_id, "imap_user", ""),
                         "ordner": sg(user.user_id, "imap_ordner", "INBOX"),
                         "aktiv": bool(sg(user.user_id, "imap_aktiv", False)),
                         "passwort_gesetzt": bool(self.vault and self.vault.get("imap_passwort"))},
                "scan": {"hinweis": "Mobile-Scan: Foto per Upload-Endpoint (Share-Ziel) "
                                    "— Slot vorbereitet (sources.MobileScanSource)."},
                "extraktoren": extract.verfuegbarkeit(),
            }

        @r.post("/api/dokument-quellen/ordner/scan")
        def quelle_ordner_scan(user: UserContext = Depends(current_user)):
            """Lokalen Watch-Ordner JETZT einlesen (manuell)."""
            ordner = db.setting_get(user.user_id, "watch_ordner", "")
            if not ordner:
                return JSONResponse({"error": "Kein Watch-Ordner konfiguriert "
                                              "(Einstellungen → Daten)."}, status_code=400)
            from .tresor_sources import FolderWatchSource, ingest_quelle
            res = ingest_quelle(self, user.user_id, FolderWatchSource(ordner))
            db.audit(user.user_id, "user", "quelle_ordner_gescannt", res)
            return res

        @r.post("/api/dokument-quellen/imap/abrufen")
        def quelle_imap_abrufen(user: UserContext = Depends(current_user)):
            """E-Mail-Postfach JETZT abrufen (manuell). Auto-Abruf ist standardmäßig
            AUS; braucht Host/User (Einstellungen) + App-Passwort im Tresor."""
            host = db.setting_get(user.user_id, "imap_host", "")
            imuser = db.setting_get(user.user_id, "imap_user", "")
            if not host or not imuser:
                return JSONResponse({"error": "IMAP nicht konfiguriert (Host/User in "
                                              "Einstellungen)."}, status_code=400)
            pw = self.vault.get("imap_passwort") if self.vault else None
            if not pw:
                return JSONResponse({"error": "Kein IMAP-Passwort im Tresor (Name "
                                              "'imap_passwort'). Gmail: App-Passwort."},
                                    status_code=400)
            from .tresor_sources import ImapSource, ingest_quelle
            ordner = db.setting_get(user.user_id, "imap_ordner", "INBOX")
            try:
                res = ingest_quelle(self, user.user_id,
                                    ImapSource(host, imuser, pw, ordner=ordner))
            except Exception as e:
                return JSONResponse({"error": f"IMAP-Abruf fehlgeschlagen: "
                                              f"{type(e).__name__}"}, status_code=502)
            db.audit(user.user_id, "user", "quelle_imap_abgerufen", res)
            return res

        @r.get("/api/fristen/uebersicht")
        def fristen_uebersicht(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """P2 Frist-Wächter-Ansicht: offene Aufgaben mit Frist, gruppiert nach
            Dringlichkeit (überfällig · diese Woche · dieser Monat · später)."""
            heute = date.today()
            woche = (heute + timedelta(days=7)).isoformat()
            monat = (heute + timedelta(days=30)).isoformat()
            h = heute.isoformat()
            rows = db.get_conn().execute(
                "SELECT id, titel, faellig, prioritaet, status FROM aufgaben "
                "WHERE user_id=? AND deleted_at IS NULL AND status!='erledigt' "
                "AND faellig!='' ORDER BY faellig ASC", (user.user_id,)).fetchall()
            gruppen: dict[str, list] = {"ueberfaellig": [], "woche": [], "monat": [], "spaeter": []}
            for r_ in rows:
                f = r_["faellig"]
                bucket = ("ueberfaellig" if f < h else "woche" if f <= woche
                          else "monat" if f <= monat else "spaeter")
                gruppen[bucket].append({"id": r_["id"], "titel": r_["titel"], "faellig": f,
                                        "prioritaet": r_["prioritaet"], "status": r_["status"]})
            return {"heute": h, "gruppen": gruppen,
                    "zaehler": {k: len(v) for k, v in gruppen.items()}}

        # ===================== RÜCK-LESE: Memory-Archiv =====================
        @r.get("/api/memory/suche")
        def memory_suche_ep(q: str = "", semantisch: str = "0", limit: int = 8,
                            user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Liest das zentrale Dizz-Memory-Archiv (Querverbindungs-Rück-Lese,
            appkit 1.10). Best-effort: ohne erreichbaren Core leere Treffer."""
            if not q.strip():
                return {"ok": True, "treffer": [], "anzahl": 0}
            from appkit.querverbindung import memory_suche
            res = memory_suche(q.strip(), semantisch=semantisch in ("1", "true"),
                               limit=min(max(limit, 1), 20), http_get=self.memory_get)
            db.audit(user.user_id, "ki", "memory_ruecklese",
                     {"q": q[:80], "ok": res.get("ok"),
                      "anzahl": len(res.get("treffer", []))})
            return res

        return r


def build_tresor(db: Database, vault_root: Path,
                 max_upload_bytes: int = MAX_UPLOAD_BYTES,
                 archiv_post=None, memory_get=None, ki_post=None) -> TresorDomain:
    return TresorDomain(db, vault_root, max_upload_bytes=max_upload_bytes,
                        archiv_post=archiv_post, memory_get=memory_get, ki_post=ki_post)
