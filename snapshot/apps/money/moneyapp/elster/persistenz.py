"""ELSTER-Transport — Persistenz + CRUD (M1-1, docs/65 §3/§12). KEIN FILING.

Die DB-Schicht UNTER dem Vertrag (``vertrag.py`` bleibt normativ + unangetastet):
drei Tabellen — Zugänge (Konfiguration), Filing-Läufe (der ``pruefe_doppel``-Speicher
= Idempotenz-Gedächtnis, I-6) und das Quittungs-Archiv (GoBD-Nachweis der tatsächlich
gesendeten Erklärung). M1-1 ist **gate-frei** und höchst-sensibel; die harte Linie
dieser Schicht ist die **Geheimnis-Freiheit der Responses** (I-2):

  * ``pin_vault_key`` (der Vault-Schlüssel-NAME) verlässt die Schicht NIE — die PIN
    selbst lebt erst ab M1-2 ausschließlich im appkit-Vault, nie in DB/Response/Log.
  * ``steuernummer`` wird in Responses maskiert (sensibel; der Klartext bleibt in der DB).
  * ``datensatz_xml`` + ``protokoll_roh`` (die Steuererklärung selbst) erscheinen NIE in
    einer Response — nur der ``transferticket``-Nachweis + Zeitstempel sind zeigbar (I-4).

Geschrieben werden Läufe/Quittungen später vom Sende-Motor (M1-5); hier existieren die
Persistenz-Nähte (``lauf_speichern``/``lauf_zustand_setzen``/``quittung_speichern``) samt
Idempotenz-Lese-Naht ``laeufe_paare`` (füttert ``vertrag.pruefe_doppel``) — Speichern,
nicht Entscheiden: die Zustandsmaschine (``pruefe_uebergang``) bleibt Sache des Motors.

DSGVO: alle drei Tabellen tragen ``user_id`` + ``deleted_at`` ⇒ die generische appkit-
Lösch-Kaskade (``soft_delete_user``) + der Export (``export_user``) greifen OHNE Per-App-
Code; die Hersteller-ID liegt im generischen ``app_settings``-KV (ebenfalls kaskadiert).
Die Purge-Warnung (das Quittungs-Archiv fällt mit) wird ehrlich ausgewiesen (``PURGE_WARNUNG``)
und in M1-6 sichtbar gemacht — die steuerliche Aufbewahrungspflicht liegt beim Nutzer.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from appkit.auth import UserContext, current_user
from appkit.db import Database, new_id, now_iso

from .vertrag import (
    ElsterDatensatz,
    ElsterZugang,
    FilingZustand,
    KonfigFehler,
    PIN_VAULT_PREFIX,
    Quittung,
    Scharfschaltung,
    SteuerFall,
    fall_schluessel,
)

# --------------------------------------------------------------------- Konstanten

#: Generischer app_settings-KV-Schlüssel der ERiC-Hersteller-ID (I-3: aus Settings,
#: NIE hartkodiert). Kein Geheimnis (Registrierungs-Kennung), aber Betriebsvoraussetzung.
SETTING_HERSTELLER_ID = "elster_hersteller_id"

#: Ehrliche DSGVO-Notiz (docs/65 §3): die Lösch-Kaskade nimmt das Quittungs-Archiv mit.
PURGE_WARNUNG = (
    "Beim Löschen aller Nutzerdaten wird auch das ELSTER-Quittungs-Archiv "
    "(Transfertickets + Übertragungsprotokolle, GoBD-Nachweise) entfernt. Die "
    "steuerliche Aufbewahrungspflicht liegt bei dir — sichere die Quittungen vorher."
)


# ------------------------------------------------------------------------- Schema
# Drei neue Tabellen (keine ALTER-Migration nötig — Bestands-DBs kennen sie nicht;
# CREATE TABLE IF NOT EXISTS legt sie samt Indizes vollständig an). Konventionen wie
# im Money-Hauptschema: TEXT-UUID-PK, user_id NOT NULL, created_at/updated_at,
# deleted_at (Soft-Delete ⇒ generische DSGVO-Kaskade). Minor-Units gibt es hier nicht.

SCHEMA_ELSTER = """
CREATE TABLE IF NOT EXISTS elster_zugaenge (
    id                     TEXT PRIMARY KEY,   -- = zugang_id; Scharf-Schlüssel + Vault-Key hängen daran (VREV-R-2)
    user_id                TEXT NOT NULL,
    zertifikat_pfad        TEXT NOT NULL,       -- Datei-REF (.pfx) unter data\\apps\\money\\elster\\ — NIE der Inhalt (I-2)
    pin_vault_key          TEXT NOT NULL,       -- Vault-Schlüssel-NAME (elster_pin_<id>) — NIE die PIN, NIE in Responses (I-2)
    zertifikat_typ         TEXT NOT NULL DEFAULT 'persoenlich',   -- persoenlich|organisation
    steuernummer           TEXT NOT NULL DEFAULT '',   -- sensibel — Responses maskieren
    zertifikat_importiert  INTEGER NOT NULL DEFAULT 0, -- M1-2: .pfx liegt real in der Daten-Wurzel
    angelegt_am            TEXT NOT NULL DEFAULT '',   -- Scharf-Schlüssel 1 (ISO) — gesetzt bei Anlage (§8 „Anlegen")
    bestaetigt_am          TEXT NOT NULL DEFAULT '',   -- Scharf-Schlüssel 2 (ISO) — getrennter Bestätigungs-Akt (M1-2)
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    deleted_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_elster_zugaenge ON elster_zugaenge (user_id, deleted_at);

CREATE TABLE IF NOT EXISTS filing_laeufe (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    zugang_id        TEXT NOT NULL DEFAULT '',   -- welcher Zugang den Lauf fuhr (lose Referenz)
    fall_schluessel  TEXT NOT NULL,              -- formular|jahr|zeitraum (Idempotenz-Anker, I-6; OHNE korrektur_nr)
    formular         TEXT NOT NULL DEFAULT '',
    jahr             INTEGER NOT NULL DEFAULT 0,
    zeitraum         TEXT NOT NULL DEFAULT '',
    korrektur_nr     INTEGER NOT NULL DEFAULT 0,
    zustand          TEXT NOT NULL,              -- FilingZustand-Wert (der Lauf wird VOR SENDET persistiert ⇒ Crash = sichtbare Leiche)
    transferticket   TEXT NOT NULL DEFAULT '',   -- amtlicher Nachweis (kein Geheimnis)
    fehler           TEXT NOT NULL DEFAULT '',   -- ehrlicher Fehlertext — trägt NIE ein Geheimnis (I-2)
    fehler_art       TEXT NOT NULL DEFAULT '',   -- ElsterFehler-Klassenname (maschinenlesbar)
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    deleted_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_filing_laeufe ON filing_laeufe (user_id, fall_schluessel, deleted_at);

CREATE TABLE IF NOT EXISTS filing_quittungen (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    lauf_id          TEXT NOT NULL DEFAULT '',
    fall_schluessel  TEXT NOT NULL,
    transferticket   TEXT NOT NULL,              -- Nachweis-Anker (zeigbar)
    uebermittelt_am  TEXT NOT NULL,              -- ISO (zeigbar)
    protokoll_roh    BLOB,                       -- unangetastetes Übertragungsprotokoll — SENSIBEL, NIE in Responses (I-2)
    datensatz_xml    TEXT NOT NULL DEFAULT '',   -- die gesendete Erklärung selbst — SENSIBEL, NIE in Responses (I-2)
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    deleted_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_filing_quittungen ON filing_quittungen (user_id, fall_schluessel, deleted_at);
"""


# ------------------------------------------------------------ Geheimnis-Maskierung

def maskiere_steuernummer(wert: str) -> str:
    """Steuernummer für Responses maskieren (I-2): Anfang/Ende bleiben zur
    Wiedererkennung sichtbar, die Mitte fällt weg. Der Klartext taucht nie auf."""
    w = (wert or "").strip()
    if len(w) <= 4:
        return "…" if w else ""
    return f"{w[:2]}…{w[-2:]}"


def zugang_public(row: Any, *, pin_gesetzt: bool = False) -> dict[str, Any]:
    """Response-Sicht eines Zugangs — **strukturell geheimnisfrei** (I-2):
    KEIN ``pin_vault_key`` (Vault-Bezug bleibt server-intern), Steuernummer nur
    maskiert. ``scharf`` spiegelt das Zwei-Schlüssel-Prinzip; ``pin_gesetzt``/
    ``zertifikat_importiert`` machen den Konfigurations-Fortschritt sichtbar,
    ohne je einen Geheimwert zu offenbaren."""
    angelegt = (row["angelegt_am"] or "").strip()
    bestaetigt = (row["bestaetigt_am"] or "").strip()
    return {
        "id": row["id"],
        "zertifikat_typ": row["zertifikat_typ"],
        "steuernummer_maskiert": maskiere_steuernummer(row["steuernummer"]),
        "zertifikat_importiert": bool(row["zertifikat_importiert"]),
        "pin_gesetzt": bool(pin_gesetzt),
        "angelegt": bool(angelegt),
        "bestaetigt": bool(bestaetigt),
        "scharf": bool(angelegt and bestaetigt),
        "angelegt_am": angelegt,
        "bestaetigt_am": bestaetigt,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def lauf_public(row: Any) -> dict[str, Any]:
    """Response-Sicht eines Filing-Laufs (Historie, read-only). Der Lauf selbst
    trägt kein Steuer-XML — nur Fall, Zustand, Nachweis + ehrlicher Fehlertext."""
    return {
        "id": row["id"],
        "zugang_id": row["zugang_id"],
        "fall_schluessel": row["fall_schluessel"],
        "formular": row["formular"],
        "jahr": row["jahr"],
        "zeitraum": row["zeitraum"],
        "korrektur_nr": row["korrektur_nr"],
        "zustand": row["zustand"],
        "transferticket": row["transferticket"],
        "fehler": row["fehler"],
        "fehler_art": row["fehler_art"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def quittung_public(row: Any) -> dict[str, Any]:
    """Response-Sicht einer Quittung — **ohne** ``protokoll_roh`` und ``datensatz_xml``
    (I-2: die Steuererklärung selbst verlässt die Schicht nie). Zeigbar sind der
    amtliche ``transferticket``-Nachweis + Zeitstempel; ``protokoll_bytes`` belegt nur,
    DASS ein Roh-Protokoll archiviert ist (Größe), ohne seinen Inhalt."""
    roh = row["protokoll_roh"]
    return {
        "id": row["id"],
        "lauf_id": row["lauf_id"],
        "fall_schluessel": row["fall_schluessel"],
        "transferticket": row["transferticket"],
        "uebermittelt_am": row["uebermittelt_am"],
        "protokoll_bytes": len(roh) if roh else 0,
        "created_at": row["created_at"],
    }


# ------------------------------------------------------------------ Request-Modelle

class ZugangIn(BaseModel):
    """Anlege-Eingabe eines Zugangs. Bewusst OHNE PIN und OHNE ``pin_vault_key``:
    die PIN kommt erst in M1-2 (→ Vault, ohne Echo), der Vault-Key wird server-
    seitig aus der ``zugang_id`` abgeleitet (``elster_pin_<id>``, I-2/VREV-R-2)."""
    zertifikat_pfad: str                         # Datei-REF (.pfx), nie der Inhalt
    zertifikat_typ: str = "persoenlich"          # persoenlich|organisation
    steuernummer: str = ""                       # sensibel — wird maskiert zurückgegeben


class HerstellerIdIn(BaseModel):
    hersteller_id: str                           # ERiC-Hersteller-ID (Settings, I-3)


# ------------------------------------------------------------------ Speicher-Schicht

class ElsterSpeicher:
    """Repository der ELSTER-Persistenz + der CRUD-Router. Kapselt die drei Tabellen
    und die geheimnis-freie Serialisierung; die native ERiC-Bindung, Vault/PIN und der
    Konnektor kommen erst in M1-2/M1-3 (docs/65 §12) und leben in eigenen Modulen."""

    def __init__(self, db: Database) -> None:
        self.db = db
        # Vault-agnostische Nähte (M1-2 verdrahtet sie NACH create_app, wenn der
        # Vault existiert): persistenz bleibt geheimnis-frei, kann aber die PIN-
        # PRÄSENZ anzeigen und beim Löschen die Geheimnisse mitnehmen lassen.
        self._pin_check: Callable[[str], bool] = lambda _key: False       # nur Präsenz, nie Wert
        self._zugang_aufraeumen: Callable[[Any], None] = lambda _row: None  # PIN/Zertifikat purgen

    def set_pin_check(self, fn: Callable[[str], bool]) -> None:
        """M1-2-Naht: eine ``pin_vault_key -> bool``-Sonde (nur Präsenz), damit die
        Zugangs-Liste ``pin_gesetzt`` ehrlich anzeigt, ohne dass persistenz den Vault
        kennt (der Geheim-WERT verlässt die Vault-Schicht nie)."""
        self._pin_check = fn

    def set_aufraeumer(self, fn: Callable[[Any], None]) -> None:
        """M1-2-Naht: beim Löschen eines Zugangs die zugehörigen Geheimnisse (Vault-PIN
        + .pfx-Datei) mit-entfernen — DSGVO „weg = weg" auch für den Secret-Rand."""
        self._zugang_aufraeumen = fn

    # --- Zugänge (CRUD) ------------------------------------------------------

    def zugang_anlegen(self, user_id: str, *, zertifikat_pfad: str,
                       zertifikat_typ: str = "persoenlich",
                       steuernummer: str = "") -> str:
        """Legt einen Zugang an (Scharf-Schlüssel 1 = ``angelegt_am`` gesetzt; §8
        „Anlegen"). Validiert VOR der Persistenz über den Vertrag (``ElsterZugang``
        wirft ``KonfigFehler`` bei ungültigem Pfad/Typ) — nur was der Vertrag als
        gültig anerkennt, erreicht die DB. Der ``pin_vault_key`` wird aus der frisch
        vergebenen ``zugang_id`` abgeleitet (I-2), die PIN selbst kommt erst in M1-2."""
        zid = new_id()
        pin_key = f"{PIN_VAULT_PREFIX}{zid}"
        # Vertrags-Validierung (KonfigFehler propagiert an den Router → 400):
        ElsterZugang(zugang_id=zid, zertifikat_pfad=zertifikat_pfad,
                     pin_vault_key=pin_key, zertifikat_typ=zertifikat_typ,
                     steuernummer=steuernummer)
        ts = now_iso()
        self.db.get_conn().execute(
            "INSERT INTO elster_zugaenge (id, user_id, zertifikat_pfad, pin_vault_key, "
            "zertifikat_typ, steuernummer, angelegt_am, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (zid, user_id, zertifikat_pfad.strip(), pin_key, zertifikat_typ,
             steuernummer.strip(), ts, ts, ts))
        self.db.get_conn().commit()
        # Audit trägt NIE ein Geheimnis (keine Steuernummer, keine PIN):
        self.db.audit(user_id, "user", "elster_zugang_angelegt",
                      {"zugang_id": zid, "typ": zertifikat_typ})
        return zid

    def zugang_row(self, user_id: str, zugang_id: str) -> Any | None:
        return self.db.get_conn().execute(
            "SELECT * FROM elster_zugaenge WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (zugang_id, user_id)).fetchone()

    def zugaenge_rows(self, user_id: str) -> list[Any]:
        return self.db.get_conn().execute(
            "SELECT * FROM elster_zugaenge WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY created_at", (user_id,)).fetchall()

    def zugang(self, user_id: str, zugang_id: str) -> ElsterZugang | None:
        """Rekonstruiert den Vertrags-Typ ``ElsterZugang`` aus der Zeile — der
        Motor (M1-5) spricht Verträge, nicht Rows. Kein Geheimnis: trägt nur
        Referenz + Vault-Key-NAME (I-2). ``None`` bei unbekanntem/gelöschtem Zugang."""
        r = self.zugang_row(user_id, zugang_id)
        if r is None:
            return None
        return ElsterZugang(
            zugang_id=r["id"], zertifikat_pfad=r["zertifikat_pfad"],
            pin_vault_key=r["pin_vault_key"], zertifikat_typ=r["zertifikat_typ"],
            steuernummer=r["steuernummer"])

    def scharfschaltung(self, user_id: str, zugang_id: str) -> Scharfschaltung | None:
        """Zwei-Schlüssel-Zustand eines Zugangs als Vertrags-Typ (``pruefe_scharf``-
        tauglich); ``None`` bei unbekanntem Zugang. Bindet an ``zugang_id`` (VREV-R-2)."""
        r = self.zugang_row(user_id, zugang_id)
        if r is None:
            return None
        return Scharfschaltung(zugang_id=zugang_id, angelegt_am=r["angelegt_am"],
                               bestaetigt_am=r["bestaetigt_am"])

    def zertifikat_setzen(self, user_id: str, zugang_id: str, pfad: str) -> bool:
        """Markiert das Zertifikat als importiert und schreibt die Datei-REFERENZ fort
        (die .pfx selbst liegt in der Daten-Wurzel, nie im Repo, nie hier als Inhalt —
        I-2). Das Schreiben der Bytes macht der Konnektor (M1-2), hier nur der DB-Stand."""
        if self.zugang_row(user_id, zugang_id) is None:
            return False
        self.db.get_conn().execute(
            "UPDATE elster_zugaenge SET zertifikat_pfad=?, zertifikat_importiert=1, "
            "updated_at=? WHERE id=? AND user_id=?", (pfad, now_iso(), zugang_id, user_id))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "elster_zertifikat_importiert", {"zugang_id": zugang_id})
        return True

    def scharf_bestaetigen(self, user_id: str, zugang_id: str) -> bool:
        """Scharf-Schlüssel 2 setzen (``bestaetigt_am``) — der getrennte Bestätigungs-Akt
        (§8). An ``zugang_id`` gebunden (VREV-R-2). Die Vorbedingung „Zertifikat+PIN da"
        prüft der Konnektor VOR diesem Aufruf; hier steht der reine Zustandsschritt."""
        if self.zugang_row(user_id, zugang_id) is None:
            return False
        self.db.get_conn().execute(
            "UPDATE elster_zugaenge SET bestaetigt_am=?, updated_at=? WHERE id=? AND user_id=?",
            (now_iso(), now_iso(), zugang_id, user_id))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "elster_scharfgeschaltet", {"zugang_id": zugang_id})
        return True

    def scharf_zuruecknehmen(self, user_id: str, zugang_id: str) -> bool:
        """Scharf-Schlüssel 2 löschen (``bestaetigt_am`` leeren) — Senken ist immer ein
        einziger Klick (§8), ohne Vorbedingung."""
        if self.zugang_row(user_id, zugang_id) is None:
            return False
        self.db.get_conn().execute(
            "UPDATE elster_zugaenge SET bestaetigt_am='', updated_at=? WHERE id=? AND user_id=?",
            (now_iso(), zugang_id, user_id))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "elster_entschaerft", {"zugang_id": zugang_id})
        return True

    def zugang_loeschen(self, user_id: str, zugang_id: str) -> bool:
        """Soft-Delete eines Zugangs. Vorher räumt der (M1-2-verdrahtete) Aufräumer die
        Geheimnisse mit weg — Vault-PIN + .pfx-Datei (DSGVO „weg = weg" am Secret-Rand);
        ohne M1-2 ist er ein No-op und der reine Soft-Delete der Zeile bleibt."""
        row = self.zugang_row(user_id, zugang_id)
        if row is None:
            return False
        self._zugang_aufraeumen(row)   # PIN aus dem Vault + .pfx-Datei (M1-2)
        ts = now_iso()
        self.db.get_conn().execute(
            "UPDATE elster_zugaenge SET deleted_at=?, updated_at=? WHERE id=? AND user_id=?",
            (ts, ts, zugang_id, user_id))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "elster_zugang_geloescht", {"zugang_id": zugang_id})
        return True

    # --- Filing-Läufe (Persistenz-Naht des Motors M1-5; hier read-only im HTTP) --

    def lauf_speichern(self, user_id: str, *, fall: SteuerFall, zustand: FilingZustand,
                       zugang_id: str = "", transferticket: str = "",
                       fehler: str = "", fehler_art: str = "") -> str:
        """Persistiert einen Filing-Lauf (Idempotenz-Gedächtnis, I-6). Reine
        Speicher-Naht — der Motor (M1-5) entscheidet Zustände via ``pruefe_uebergang``
        und persistiert den Lauf VOR dem Übergang nach SENDET, damit ein Crash eine
        sichtbare ``SENDET``-Leiche hinterlässt statt eines stillen Nichts (docs/65 §3)."""
        lid, ts = new_id(), now_iso()
        self.db.get_conn().execute(
            "INSERT INTO filing_laeufe (id, user_id, zugang_id, fall_schluessel, formular, "
            "jahr, zeitraum, korrektur_nr, zustand, transferticket, fehler, fehler_art, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lid, user_id, zugang_id, fall_schluessel(fall), fall.formular.value,
             fall.jahr, fall.zeitraum, fall.korrektur_nr, zustand.value,
             transferticket, fehler, fehler_art, ts, ts))
        self.db.get_conn().commit()
        return lid

    def lauf_zustand_setzen(self, user_id: str, lauf_id: str, zustand: FilingZustand, *,
                            transferticket: str | None = None, fehler: str | None = None,
                            fehler_art: str | None = None) -> bool:
        """Aktualisiert Zustand (+ optional Nachweis/Fehler) eines Laufs — die
        Persistenz-Seite eines Motor-Übergangs (M1-5). Die Legalität des Übergangs
        prüft der Motor (``pruefe_uebergang``), nicht die Speicher-Schicht."""
        r = self.db.get_conn().execute(
            "SELECT transferticket, fehler, fehler_art FROM filing_laeufe "
            "WHERE id=? AND user_id=? AND deleted_at IS NULL", (lauf_id, user_id)).fetchone()
        if r is None:
            return False
        self.db.get_conn().execute(
            "UPDATE filing_laeufe SET zustand=?, transferticket=?, fehler=?, fehler_art=?, "
            "updated_at=? WHERE id=? AND user_id=?",
            (zustand.value,
             r["transferticket"] if transferticket is None else transferticket,
             r["fehler"] if fehler is None else fehler,
             r["fehler_art"] if fehler_art is None else fehler_art,
             now_iso(), lauf_id, user_id))
        self.db.get_conn().commit()
        return True

    def laeufe_rows(self, user_id: str, fall_schluessel: str | None = None) -> list[Any]:
        conn = self.db.get_conn()
        if fall_schluessel is None:
            return conn.execute(
                "SELECT * FROM filing_laeufe WHERE user_id=? AND deleted_at IS NULL "
                "ORDER BY created_at DESC", (user_id,)).fetchall()
        return conn.execute(
            "SELECT * FROM filing_laeufe WHERE user_id=? AND fall_schluessel=? "
            "AND deleted_at IS NULL ORDER BY created_at DESC",
            (user_id, fall_schluessel)).fetchall()

    def laeufe_paare(self, user_id: str) -> list[tuple[str, FilingZustand]]:
        """Die Lese-Naht für ``vertrag.pruefe_doppel`` (I-6): (fall_schluessel, Zustand)
        aller nicht-gelöschten Läufe des Nutzers — der Doppel-Übermittlungs-Schutz baut
        allein auf dieser persistierten Historie auf."""
        rows = self.db.get_conn().execute(
            "SELECT fall_schluessel, zustand FROM filing_laeufe "
            "WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall()
        return [(r["fall_schluessel"], FilingZustand(r["zustand"])) for r in rows]

    # --- Quittungs-Archiv (GoBD; Persistenz-Naht M1-5, read-only ohne Geheimnisse) --

    def quittung_speichern(self, user_id: str, *, quittung: Quittung,
                           datensatz: ElsterDatensatz, lauf_id: str = "") -> str:
        """Archiviert eine erhaltene Quittung samt Roh-Protokoll UND der gesendeten
        Erklärung (``datensatz.xml``) — das GoBD-Archiv. Beide Nutzdaten sind sensibel
        und verlassen die Schicht nie (``quittung_public`` blendet sie aus, I-2)."""
        qid, ts = new_id(), now_iso()
        self.db.get_conn().execute(
            "INSERT INTO filing_quittungen (id, user_id, lauf_id, fall_schluessel, "
            "transferticket, uebermittelt_am, protokoll_roh, datensatz_xml, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (qid, user_id, lauf_id, fall_schluessel(datensatz.fall),
             quittung.transferticket, quittung.uebermittelt_am,
             quittung.protokoll_roh, datensatz.xml, ts, ts))
        self.db.get_conn().commit()
        self.db.audit(user_id, "system", "elster_quittung_archiviert",
                      {"lauf_id": lauf_id, "transferticket": quittung.transferticket})
        return qid

    def quittungen_rows(self, user_id: str, fall_schluessel: str | None = None) -> list[Any]:
        conn = self.db.get_conn()
        if fall_schluessel is None:
            return conn.execute(
                "SELECT * FROM filing_quittungen WHERE user_id=? AND deleted_at IS NULL "
                "ORDER BY created_at DESC", (user_id,)).fetchall()
        return conn.execute(
            "SELECT * FROM filing_quittungen WHERE user_id=? AND fall_schluessel=? "
            "AND deleted_at IS NULL ORDER BY created_at DESC",
            (user_id, fall_schluessel)).fetchall()

    # --- Hersteller-ID (Settings-Slot, I-3) ----------------------------------

    def hersteller_id(self, user_id: str) -> str:
        return (self.db.setting_get(user_id, SETTING_HERSTELLER_ID, "") or "").strip()

    def hersteller_id_setzen(self, user_id: str, wert: str) -> None:
        self.db.setting_put(user_id, SETTING_HERSTELLER_ID, (wert or "").strip())
        self.db.audit(user_id, "user", "elster_hersteller_id_gesetzt",
                      {"gesetzt": bool((wert or "").strip())})

    # --- HTTP-Router (M1-1: Zugänge-CRUD · Läufe read-only · Hersteller-ID) --

    def build_router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/api/elster/zugaenge")
        def zugaenge_liste(user: UserContext = Depends(current_user)):
            return [zugang_public(row, pin_gesetzt=self._pin_check(row["pin_vault_key"]))
                    for row in self.zugaenge_rows(user.user_id)]

        @r.post("/api/elster/zugaenge")
        def zugang_anlegen(body: ZugangIn, user: UserContext = Depends(current_user)):
            try:
                zid = self.zugang_anlegen(
                    user.user_id, zertifikat_pfad=body.zertifikat_pfad,
                    zertifikat_typ=body.zertifikat_typ, steuernummer=body.steuernummer)
            except KonfigFehler as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            row = self.zugang_row(user.user_id, zid)
            return zugang_public(row, pin_gesetzt=self._pin_check(row["pin_vault_key"]))

        @r.get("/api/elster/zugaenge/{zugang_id}")
        def zugang_holen(zugang_id: str, user: UserContext = Depends(current_user)):
            row = self.zugang_row(user.user_id, zugang_id)
            if row is None:
                return JSONResponse({"error": "Zugang unbekannt"}, status_code=404)
            return zugang_public(row, pin_gesetzt=self._pin_check(row["pin_vault_key"]))

        @r.delete("/api/elster/zugaenge/{zugang_id}")
        def zugang_loeschen(zugang_id: str, user: UserContext = Depends(current_user)):
            if not self.zugang_loeschen(user.user_id, zugang_id):
                return JSONResponse({"error": "Zugang unbekannt"}, status_code=404)
            return {"ok": True}

        @r.get("/api/elster/laeufe")
        def laeufe_liste(fall_schluessel: str | None = None,
                         user: UserContext = Depends(current_user)):
            """Filing-Lauf-Historie (read-only, I-6-Gedächtnis sichtbar; P8-Geist).
            Geschrieben wird sie vom Sende-Motor (M1-5), hier nur gelesen."""
            return [lauf_public(row)
                    for row in self.laeufe_rows(user.user_id, fall_schluessel)]

        @r.get("/api/elster/quittungen")
        def quittungen_liste(fall_schluessel: str | None = None,
                             user: UserContext = Depends(current_user)):
            """Quittungs-Archiv (read-only) — NUR Nachweis-Metadaten, nie XML/Protokoll (I-2)."""
            return [quittung_public(row)
                    for row in self.quittungen_rows(user.user_id, fall_schluessel)]

        @r.get("/api/elster/einstellungen")
        def einstellungen_holen(user: UserContext = Depends(current_user)):
            hid = self.hersteller_id(user.user_id)
            return {"hersteller_id": hid, "hersteller_id_gesetzt": bool(hid),
                    "purge_warnung": PURGE_WARNUNG}

        @r.put("/api/elster/einstellungen")
        def einstellungen_setzen(body: HerstellerIdIn,
                                 user: UserContext = Depends(current_user)):
            self.hersteller_id_setzen(user.user_id, body.hersteller_id)
            return {"ok": True, "hersteller_id_gesetzt": bool(self.hersteller_id(user.user_id))}

        return r
