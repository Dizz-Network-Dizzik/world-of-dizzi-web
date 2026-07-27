"""Live-Daten-Migration Plans + Admin + Leading → Dizz Admin (docs/28 §15, Phase 4).

**Strategie (frische Ziel-DB):** statt in Admins Bestands-DB hineinzumigrieren (deren
altes ``aufgaben`` das schlanke Schema trägt), wird eine FRISCHE Ziel-DB mit dem vollen
vereinten Schema gebaut und spalten-intersektierend befüllt. Der Spalten-Schnitt löst
den Schema-Mismatch automatisch: fehlende Ziel-Spalten (z. B. ``bereich_id``,
``projekt_id``) bekommen ihren CREATE-Default. ``INSERT OR IGNORE`` (PK = ``id``) macht
den Lauf **idempotent**.

Quell-DBs werden NIE verändert (read-only). Der Aufrufer (CLI/Test) verifiziert die
Zeilen-Zähler gegen die Baseline; der Live-Swap (Server stoppen → Ziel an
``apps/admin/admin.sqlite``) ist ein bewusster Phase-5-Schritt mit Backup + Nutzer-Go.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from appkit.db import Database

from . import bereiche, domain, projekte, tresor

# Welche Domänen-Tabellen je Quelle übernommen werden (appkit-Infra-Tabellen
# app_settings/audit_log/app_actions/defense_* NICHT — die vereinte App startet mit
# eigenen Defaults; die Quell-DBs bleiben als Backup vollständig erhalten).
DOMAENE = {
    "plans":   ["projekte", "aufgaben", "termine"],
    "admin":   ["dokumente", "dokument_verknuepfungen", "aufgaben"],
    "leading": ["kunden", "produkte", "rechnungen", "rechnung_positionen",
                "fristen", "support", "kpi_snapshot",
                "bildungsweg", "studienmodul", "studienfrist"],
}


def ziel_db(pfad: Path) -> Database:
    """Baut die Ziel-DB mit dem VOLLEN vereinten Schema + allen Migrationen — exakt
    wie ``main.build_app`` (Bereiche/Projekte/Geschäft+Studium/Tresor)."""
    db = Database(pfad, extra_schema=domain.SCHEMA + bereiche.SCHEMA_BEREICHE
                  + projekte.SCHEMA_PROJEKTE + tresor.SCHEMA_TRESOR)
    bereiche.migriere_bereich_fk(db)                  # bereich_id-Spalten
    projekte.build_projekte(db)                       # projekte._migrate (aufgaben.rrule)
    tresor.build_tresor(db, pfad.parent / "vault")    # tresor._migrate (dokumente-ALTERs + FTS)
    return db


def _import_tabelle(src: sqlite3.Connection, tgt: sqlite3.Connection,
                    tabelle: str) -> tuple[int, int]:
    """Spalten-intersektierender, idempotenter Import einer Tabelle.
    Rückgabe (importiert, in_quelle_gefunden)."""
    try:
        src_cols = [r["name"] for r in src.execute(f"PRAGMA table_info({tabelle})")]
    except sqlite3.OperationalError:
        return 0, 0                                   # Tabelle in dieser Quelle nicht vorhanden
    if not src_cols:
        return 0, 0
    tgt_cols = {r["name"] for r in tgt.execute(f"PRAGMA table_info({tabelle})")}
    gemein = [c for c in src_cols if c in tgt_cols]   # nur überlappende Spalten
    rows = src.execute(f"SELECT {', '.join(gemein)} FROM {tabelle}").fetchall()
    spalten = ", ".join(gemein)
    platz = ", ".join("?" * len(gemein))
    imp = 0
    for row in rows:
        cur = tgt.execute(
            f"INSERT OR IGNORE INTO {tabelle} ({spalten}) VALUES ({platz})",
            [row[c] for c in gemein])
        imp += cur.rowcount
    return imp, len(rows)


def _fts_backfill(tgt: sqlite3.Connection) -> int:
    """FTS5-Index für importierte (noch nicht indexierte) Dokumente nachziehen."""
    vorhanden = {r[0] for r in tgt.execute("SELECT dok_id FROM dokumente_fts")}
    n = 0
    for d in tgt.execute("SELECT id, titel, notiz, tags, volltext FROM dokumente "
                         "WHERE deleted_at IS NULL").fetchall():
        if d["id"] in vorhanden:
            continue
        tgt.execute("INSERT INTO dokumente_fts (dok_id, titel, notiz, tags, volltext) "
                    "VALUES (?,?,?,?,?)",
                    (d["id"], d["titel"] or "", d["notiz"] or "",
                     tresor._tagtext(d["tags"]), d["volltext"] or ""))
        n += 1
    return n


def merge_quellen(ziel: Database, sources: dict[str, Path], *,
                  vault_src: Path | None = None,
                  vault_ziel: Path | None = None) -> dict[str, Any]:
    """Importiert die Domänen-Tabellen aller Quellen in die (frisch gebaute) Ziel-DB,
    zieht den FTS-Index nach und kopiert die Tresor-Vault-Dateien. Idempotent.
    Liefert einen Zähler-Bericht je (app, tabelle) + die Endsummen je Ziel-Tabelle."""
    tgt = ziel.get_conn()
    bericht: dict[str, Any] = {"quellen": {}, "ziel": {}, "vault_dateien": 0, "fts_indexiert": 0}
    for app, src_path in sources.items():
        if not Path(src_path).exists():
            continue
        src = sqlite3.connect(f"file:{Path(src_path).as_posix()}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        try:
            for t in DOMAENE.get(app, []):
                imp, total = _import_tabelle(src, tgt, t)
                if total:
                    bericht["quellen"][f"{app}.{t}"] = {"importiert": imp, "gefunden": total}
        finally:
            src.close()
    bericht["fts_indexiert"] = _fts_backfill(tgt)
    tgt.commit()
    # Vault-Dateien (Tresor) übernehmen
    if vault_src and vault_ziel and Path(vault_src).exists():
        shutil.copytree(vault_src, vault_ziel, dirs_exist_ok=True)
        bericht["vault_dateien"] = sum(1 for _ in Path(vault_ziel).rglob("*") if _.is_file())
    # Endsummen je Ziel-Tabelle: ``ziel_gesamt`` = alle übernommenen Zeilen
    # (Verlust-Verifikation gegen die Quell-Totale, inkl. soft-deleted) · ``ziel`` =
    # die aktiven (app-sichtbaren) Zeilen. (Hinweis: die echten Quell-DBs tragen
    # ausschließlich soft-deleted Test-Artefakte ⇒ aktiv = 0, gesamt = übernommen.)
    bericht["ziel_gesamt"] = {}
    for t in {x for ts in DOMAENE.values() for x in ts}:
        bericht["ziel_gesamt"][t] = tgt.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        bericht["ziel"][t] = tgt.execute(
            f"SELECT count(*) FROM {t} WHERE deleted_at IS NULL").fetchone()[0]
    return bericht
