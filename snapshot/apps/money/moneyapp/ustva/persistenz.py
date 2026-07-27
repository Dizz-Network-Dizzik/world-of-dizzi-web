"""UStVA-Datenschicht — Persistenz + CRUD (M4-1, docs/68 §3/§11). KEINE echte UStVA.

Die DB-Schicht UNTER dem Vertrag (``vertrag.py`` bleibt normativ + UNANGETASTET —
genau wie ``elster/persistenz.py`` unter docs/65). Vier Seiten-Tabellen (alle mit
``user_id`` + ``deleted_at`` ⇒ generische appkit-DSGVO-Kaskade, KEIN Per-App-Code):

  * ``ust_regeln`` — die Kategorie-Default-Achse (Money-Kategorie → ``UStKategorie``
    + Satz + Vorsteuer-Status), NEBEN ``kategorien.steuer_relevant``/``steuer_art``
    (die ESt-Achse bleibt, was sie ist — U-4),
  * ``ust_klassifikationen`` — der Buchungs-Override + Audit-Spur (``quelle=MANUELL``
    schlägt die Regel; referenziert ``buchung_id``, mutiert das Ledger nie — U-4),
  * ``ust_zeitraeume`` — der erzeugte Datensatz-Snapshot (GoBD-nah); in M4-1 nur als
    Tabelle angelegt, GESCHRIEBEN wird sie erst von M4-5 (M-2-Anbindung/Übergabe),
  * ``ku_status`` — die §19-Jahres-Konfiguration; ab **M4-2** verwaltet
    (``ku_status_setzen``: Form/Grund/Text via ``pruefe_kleinunternehmer`` — nie
    Form ohne Grund; gate G-M4-STATUS, Default Regelbesteuerung),
  * ``ust_konfig`` — die stehende Voranmeldungs-Konfiguration (M4-2, gate
    G-M4-ZEITRAUM; Default Quartal + Ist, umschaltbar),
  * ``ust_vorsteuer_aufteilung`` — die §15-Abs.-4-Aufteilung (M4-3, gate
    G-M4-VORSTEUER): teilweise abziehbare Vorsteuer mit PFLICHT-Doku (dokumentierter
    Schlüssel + Begründung — der Vertrag SPERRT ``TEILWEISE`` in der Klassifikation,
    diese Achse macht sie als eigenen Datensatz real; Logik in ``vorsteuer.py``).

M4-1 baute die CRUD/APIs für die ZWEI aktiven Arbeits-Tabellen (Regeln +
Klassifikationen) und die „offene Buchungen des Zeitraums"-Liste (U-1-
Arbeitsvorrat). **M4-2 ergänzt** (gate G-M4-STATUS/-ZEITRAUM, beide beantwortet):
die ``ku_status``-Verwaltung, den **Gesamtumsatz-Monitor** am Ledger (§19-Schwellen
mit 80 %/100 %-Warn-Stufen + unterjährigem Regime-Schnitt — Logik in ``monitor.py``)
und die ``ust_konfig``-CRUD. **M4-3 ergänzt** (gate G-M4-VORSTEUER, beantwortet):
die ``ust_vorsteuer_aufteilung``-CRUD, die Beleg-Ref-Warnregel „ABZIEHBAR ohne
Beleg-Ref" (Vorsteuer-Warnungen je Zeitraum) und den Bewirtungs-Vergleich —
Rechen-/Doku-Logik in ``vorsteuer.py``. Die Klassifikations-Logik
selbst ist EINE Quelle: die Wächter/Lookups leben im Vertrag (``klassifiziere``),
diese Schicht speichert nur, was der Vertrag als gültig anerkennt (jede Regel/
jeder Override wird VOR der Persistenz durch den Vertrags-Typ validiert — ein
strukturell ungültiger Entscheid erreicht die DB nie).

Härtung (docs/68 §9 / docs/61): keine Geheimnisse im Modell ⇒ Responses sind
schlichte Fach-Dicts; Auth/CSRF/Defense kommen aus dem appkit-``create_app``-
Hausmuster (Money steht bei 0 docs/61-Funden — das bleibt Akzeptanzkriterium).
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from appkit.auth import UserContext, current_user
from appkit.db import Database, new_id, now_iso

from . import monitor, vorsteuer
from .vertrag import (
    Besteuerung,
    BesteuerungsForm,
    Klassifikation,
    KlassifikationsQuelle,
    KlassifikationsRegel,
    KlassifikationUnklar,
    KonfigFehler,
    MIT_SPLIT,
    SchwellenUnbekannt,
    UStKategorie,
    UStVAZeitraum,
    UstSplit,
    VerzichtsErklaerung,
    VoranmeldungsKonfig,
    ZeitraumFehler,
    ZeitraumTyp,
    klassifiziere,
    pruefe_kleinunternehmer,
    schwellen_fuer,
    split_aus_brutto,
)

# Signatur einer Buchungs-Lade-Funktion (aus ``main.build_app`` injiziert): liefert
# je Buchung im Datumsfenster das Auswertungs-dict (``id``, ``datum``, ``netto``
# EUR-Minor signiert, ``kategorie_id`` …) — die Währungs-/Netto-Logik lebt EINMAL
# in main (kein Ledger-Zugriff/keine Kurs-Kopie in dieser Schicht, U-4).
BewegungenFn = Callable[[str, str, str], Iterable[Mapping[str, Any]]]


# ------------------------------------------------------------------------- Schema
# Vier neue Tabellen (keine ALTER-Migration — Bestands-DBs kennen sie nicht;
# CREATE TABLE IF NOT EXISTS legt sie samt Indizes vollständig an). Konventionen
# wie im Money-Hauptschema: TEXT-UUID-PK, user_id NOT NULL, created_at/updated_at,
# deleted_at (Soft-Delete ⇒ generische DSGVO-Kaskade). USt-Beträge in Cent (INTEGER),
# wie der Ledger; die BMG-in-vollen-Euro-Rundung (U-7) ist Rechen-Sache (M4-4),
# gespeichert wird centgenau.

SCHEMA_UST = """
CREATE TABLE IF NOT EXISTS ust_regeln (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL,
    kategorie_id            TEXT NOT NULL,               -- Money-Kategorie (kategorien.id) = Default-Anker
    ust_kategorie           TEXT NOT NULL,               -- UStKategorie-Wert
    satz_promille           INTEGER NOT NULL DEFAULT 0,  -- {0,70,190} — Widerspruchs-Schranke im Vertrag
    vorsteuer_status        TEXT NOT NULL DEFAULT '',    -- ''|abziehbar|nicht_abziehbar (teilweise wirft, §15 Abs.4=M4-3)
    vorsteuer_verbot_grund  TEXT NOT NULL DEFAULT '',    -- geschlossener Katalog (nur bei nicht_abziehbar)
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    deleted_at              TEXT
);
CREATE INDEX IF NOT EXISTS idx_ust_regeln ON ust_regeln (user_id, deleted_at);
-- EIN aktiver USt-Default je Money-Kategorie (Hausmuster „Konto-Default"); Soft-
-- Deletes fallen aus der Eindeutigkeit (Partial-Index ⇒ Neu-Anlage nach Löschen ok).
CREATE UNIQUE INDEX IF NOT EXISTS idx_ust_regeln_kat
    ON ust_regeln (user_id, kategorie_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS ust_klassifikationen (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL,
    buchung_id              TEXT NOT NULL,               -- buchungen.id (referenziert, mutiert nie — U-4)
    ust_kategorie           TEXT NOT NULL,
    satz_promille           INTEGER NOT NULL DEFAULT 0,
    netto_cent              INTEGER NOT NULL DEFAULT 0,  -- Split (nur MIT_SPLIT); brutto = netto+ust (konstruktiv)
    ust_cent                INTEGER NOT NULL DEFAULT 0,
    vorsteuer_status        TEXT NOT NULL DEFAULT '',
    vorsteuer_verbot_grund  TEXT NOT NULL DEFAULT '',
    quelle                  TEXT NOT NULL DEFAULT 'manuell',  -- KlassifikationsQuelle (Override = immer manuell)
    entschieden_am          TEXT NOT NULL DEFAULT '',    -- Audit: WANN der Mensch entschied
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    deleted_at              TEXT
);
CREATE INDEX IF NOT EXISTS idx_ust_klass ON ust_klassifikationen (user_id, deleted_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ust_klass_buchung
    ON ust_klassifikationen (user_id, buchung_id) WHERE deleted_at IS NULL;

-- Der erzeugte Datensatz-Snapshot (U-5/U-6-Hash). In M4-1 NUR angelegt (Schema-
-- Vollständigkeit + DSGVO-Shape) — geschrieben wird er erst von M4-5 (§8-Übergabe);
-- die Festschreibung selbst ist M-7.
CREATE TABLE IF NOT EXISTS ust_zeitraeume (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL,
    zeitraum_schluessel     TEXT NOT NULL,               -- 'YYYY-MM' / 'YYYY-Qn' (docs/65-Format)
    konfig_json             TEXT NOT NULL DEFAULT '',    -- VoranmeldungsKonfig-Snapshot
    datensatz_json          TEXT NOT NULL DEFAULT '',    -- kanonischer UStVADatensatz
    quell_stand_hash        TEXT NOT NULL DEFAULT '',    -- U-6 Hash-Bindung an M-2/M-1
    berichtigung            INTEGER NOT NULL DEFAULT 0,
    erstellt_am             TEXT NOT NULL DEFAULT '',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    deleted_at              TEXT
);
CREATE INDEX IF NOT EXISTS idx_ust_zeitraeume ON ust_zeitraeume (user_id, deleted_at);

-- Die §19-Jahres-Konfiguration + Befund. Angelegt in M4-1, VERWALTET ab M4-2
-- (``ku_status_setzen``: Form/Grund/Text kommen aus ``pruefe_kleinunternehmer`` —
-- nie Form ohne Grund; gate G-M4-STATUS). Die reine §19-Weiche + Schwellen leben
-- im Vertrag; der Gesamtumsatz-Monitor/Regime-Schnitt in ``monitor.py``.
CREATE TABLE IF NOT EXISTS ku_status (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL,
    jahr                    INTEGER NOT NULL,
    form                    TEXT NOT NULL,               -- BesteuerungsForm
    grund                   TEXT NOT NULL DEFAULT '',    -- StatusGrund
    verzicht_ab_jahr        INTEGER NOT NULL DEFAULT 0,  -- §19 Abs.3 (0 = kein Verzicht)
    befund_text             TEXT NOT NULL DEFAULT '',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    deleted_at              TEXT
);
CREATE INDEX IF NOT EXISTS idx_ku_status ON ku_status (user_id, jahr, deleted_at);
-- EIN aktiver §19-Status je Jahr (Upsert je jahr); Soft-Deletes fallen aus der
-- Eindeutigkeit (Partial-Index ⇒ Neu-Anlage nach Löschen ok). ku_status war in
-- M4-1 leer ⇒ die Index-Nachrüstung auf Bestands-DBs greift konfliktfrei.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ku_status_jahr
    ON ku_status (user_id, jahr) WHERE deleted_at IS NULL;

-- Die stehende Voranmeldungs-Konfiguration (Zeitraum-Rhythmus/Ist-Soll/Dauerfrist,
-- M4-2, gate G-M4-ZEITRAUM). EIN aktiver Datensatz je Nutzer (Upsert); Default =
-- Quartal + Ist + ohne Dauerfrist (``VoranmeldungsKonfig``-Default). SOLL wirft
-- im Vertrag (v1 gesperrt, U-8) ⇒ erreicht die DB nie.
CREATE TABLE IF NOT EXISTS ust_konfig (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL,
    zeitraum_typ            TEXT NOT NULL DEFAULT 'quartal',   -- ZeitraumTyp
    dauerfrist              INTEGER NOT NULL DEFAULT 0,
    besteuerung             TEXT NOT NULL DEFAULT 'ist',       -- Besteuerung (soll gesperrt)
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    deleted_at              TEXT
);
CREATE INDEX IF NOT EXISTS idx_ust_konfig ON ust_konfig (user_id, deleted_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ust_konfig_user
    ON ust_konfig (user_id) WHERE deleted_at IS NULL;

-- Die §15-Abs.-4-Aufteilung (M4-3, gate G-M4-VORSTEUER): teilweise abziehbare
-- Vorsteuer als EIGENER, dokumentierter Datensatz (der Vertrag sperrt das
-- Klassifikations-TEILWEISE — kein stiller Prozentsatz). Voller Beleg-Split
-- (netto+ust) + dokumentierter Schlüssel-Anteil (promille) + abgeleiteter
-- abziehbar_cent + PFLICHT-Begründung. Referenziert buchung_id, mutiert das
-- Ledger nie (U-4). EIN aktiver Split je Buchung (Partial-Unique-Index).
CREATE TABLE IF NOT EXISTS ust_vorsteuer_aufteilung (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL,
    buchung_id              TEXT NOT NULL,               -- buchungen.id (referenziert, mutiert nie — U-4)
    ust_kategorie           TEXT NOT NULL DEFAULT 'eingang_vst',  -- v1: nur EINGANG_VST (Beleg-Split, §15)
    satz_promille           INTEGER NOT NULL DEFAULT 0,           -- {70,190}
    netto_cent              INTEGER NOT NULL DEFAULT 0,           -- voller Beleg-Split (netto+ust=brutto konstruktiv)
    ust_cent                INTEGER NOT NULL DEFAULT 0,           -- volle Vorsteuer aus dem Split
    abziehbar_promille      INTEGER NOT NULL DEFAULT 0,           -- dokumentierter Schlüssel-Anteil (0<..<1000)
    abziehbar_cent          INTEGER NOT NULL DEFAULT 0,           -- abgeleitet: aufteilen(ust, promille) — konservativ abgerundet
    schluessel              TEXT NOT NULL DEFAULT '',             -- AufteilungsSchluessel (fläche/zeit/individuell/umsatz)
    grund_nicht_abziehbar   TEXT NOT NULL DEFAULT '',             -- VorsteuerVerbotsGrund (steuerfreie_verwendung|privat)
    begruendung             TEXT NOT NULL DEFAULT '',             -- PFLICHT-Doku (§15 Abs.4, nie leer)
    entschieden_am          TEXT NOT NULL DEFAULT '',             -- Audit: WANN der Mensch aufteilte
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    deleted_at              TEXT
);
CREATE INDEX IF NOT EXISTS idx_ust_vst_aufteilung ON ust_vorsteuer_aufteilung (user_id, deleted_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ust_vst_aufteilung_buchung
    ON ust_vorsteuer_aufteilung (user_id, buchung_id) WHERE deleted_at IS NULL;
"""


# ------------------------------------------------------------------ Request-Modelle

class RegelIn(BaseModel):
    """Anlege-/Update-Eingabe einer Kategorie-Default-Regel (Upsert je
    ``kategorie_id``). Leere Vorsteuer-Felder ⇒ ``None`` (Nicht-§15-Welt);
    die Fachlogik (Satz-Erwartung, §15-Pflichtfelder) erzwingt der Vertrag."""
    kategorie_id: str
    ust_kategorie: str
    satz_promille: int = 0
    vorsteuer_status: str = ""              # ''|abziehbar|nicht_abziehbar (teilweise wirft)
    vorsteuer_verbot_grund: str = ""        # nur bei nicht_abziehbar


class KlassifikationIn(BaseModel):
    """Buchungs-Override (Upsert je ``buchung_id``, ``quelle=MANUELL``).
    ``brutto_cent`` ist Pflicht für MIT_SPLIT-Kategorien (UMSATZ_19/7, EINGANG_VST) —
    der Zahlbetrag, den der Vertrag in netto/ust zerlegt. ``ust_cent`` optional:
    weist der Beleg die USt aus, gilt der Belegbetrag (schlägt den Rechenweg, §7)."""
    buchung_id: str
    ust_kategorie: str
    satz_promille: int = 0
    brutto_cent: int | None = None
    ust_cent: int | None = None
    vorsteuer_status: str = ""
    vorsteuer_verbot_grund: str = ""


class KuStatusIn(BaseModel):
    """§19-Status-Deklaration je Jahr (gate G-M4-STATUS). Der Nutzer gibt die
    FAKTEN an (Vorjahres-Gesamtumsatz, ggf. laufender, ggf. §19-Verzicht ab Jahr);
    die Form + der Grund werden IMMER via ``pruefe_kleinunternehmer`` abgeleitet
    (nie Form ohne Grund, docs/68 §6). Ergibt bei Vorjahr > 25 k oder aktivem
    Verzicht Regelbesteuerung (Davids Default), sonst Kleinunternehmer."""
    jahr: int
    vorjahr_umsatz_cent: int = 0
    laufend_umsatz_cent: int = 0
    verzicht_ab_jahr: int = 0               # 0 = kein §19-Verzicht (§19 Abs.3)


class KonfigIn(BaseModel):
    """Voranmeldungs-Konfiguration (gate G-M4-ZEITRAUM). Default Quartal + Ist +
    ohne Dauerfrist; SOLL-Versteuerung wirft im Vertrag (v1 gesperrt, U-8) ⇒ 400."""
    zeitraum_typ: str = "quartal"           # ZeitraumTyp (monat|quartal|jahr_befreit)
    dauerfrist: bool = False
    besteuerung: str = "ist"                # Besteuerung (ist; soll gesperrt)


class AufteilungIn(BaseModel):
    """§15-Abs.-4-Aufteilung einer teilweise abziehbaren Vorsteuer (M4-3, gate
    G-M4-VORSTEUER). ``brutto_cent`` ist Pflicht (der Zahlbetrag, aus dem der Vertrag
    netto/ust zerlegt); ``ust_cent`` optional ⇒ Belegausweis schlägt Rechenweg (§7).
    ``abziehbar_promille`` ist der DOKUMENTIERTE Schlüssel-Anteil (STRIKT 0<..<1000 —
    100 %/0 % gehören in die normale Klassifikation); ``begruendung`` ist PFLICHT
    (nie ein stiller %). ``satz_promille`` erwartet 190/70 (EINGANG_VST)."""
    buchung_id: str
    satz_promille: int = 190                 # {190,70} — EINGANG_VST
    brutto_cent: int | None = None           # der Zahlbetrag → Beleg-Split (Pflicht)
    ust_cent: int | None = None              # Belegausweis schlägt Rechenweg (§7)
    abziehbar_promille: int = 0              # dokumentierter Schlüssel-Anteil (0<..<1000)
    schluessel: str = "individuell"          # AufteilungsSchluessel
    grund_nicht_abziehbar: str = "steuerfreie_verwendung"   # steuerfreie_verwendung|privat
    begruendung: str = ""                    # PFLICHT-Doku (§15 Abs.4)


# ------------------------------------------------- Vertrags-Bau (validiert VOR DB)

def _regel_bauen(body: RegelIn) -> KlassifikationsRegel:
    """Baut den Vertrags-Typ (validiert alles: Satz-Erwartung, §15-Pflicht,
    geschlossene Enums) — ``KonfigFehler`` propagiert an den Router → 400."""
    return KlassifikationsRegel(
        kategorie_id=body.kategorie_id,
        ust_kategorie=body.ust_kategorie,
        satz_promille=body.satz_promille,
        vorsteuer_status=body.vorsteuer_status or None,
        vorsteuer_verbot_grund=body.vorsteuer_verbot_grund or None,
    )


def _klassifikation_bauen(body: KlassifikationIn) -> Klassifikation:
    """Baut den Vertrags-Typ eines Buchungs-Overrides. Für MIT_SPLIT-Kategorien
    entsteht der ``UstSplit`` entweder aus dem Belegausweis (``ust_cent`` gesetzt,
    §7) oder deterministisch aus dem Brutto (``split_aus_brutto``). Alle
    Widersprüche (Split-Pflicht, Satz-Konsistenz, §15-Status) wirft der Vertrag."""
    try:
        kat = UStKategorie(body.ust_kategorie)
    except ValueError:
        raise KonfigFehler(f"Unbekannte UStKategorie {body.ust_kategorie!r}")
    split: UstSplit | None = None
    if kat in MIT_SPLIT:
        if body.brutto_cent is None:
            raise KonfigFehler(
                f"{kat.value}: brutto_cent ist Pflicht — die Rechnungs-Zerlegung "
                "des Zahlbetrags (MIT_SPLIT-Kategorie, docs/68 §7)")
        brutto = int(body.brutto_cent)
        if body.ust_cent is not None:
            ust = int(body.ust_cent)
            # Belegausweis schlägt Rechenweg (§7): brutto = netto + ust.
            split = UstSplit(brutto_cent=brutto, netto_cent=brutto - ust,
                             ust_cent=ust, satz_promille=body.satz_promille)
        else:
            split = split_aus_brutto(brutto, body.satz_promille)
    return Klassifikation(
        buchung_id=body.buchung_id,
        ust_kategorie=kat,
        quelle=KlassifikationsQuelle.MANUELL,
        satz_promille=body.satz_promille,
        split=split,
        vorsteuer_status=body.vorsteuer_status or None,
        vorsteuer_verbot_grund=body.vorsteuer_verbot_grund or None,
    )


def _aufteilung_bauen(body: AufteilungIn):
    """Baut Beleg-Split + dokumentierte §15-Abs.-4-Aufteilung (M4-3, docs/68 §7).
    ``brutto_cent`` ist Pflicht; ``ust_cent`` gesetzt ⇒ Belegausweis schlägt Rechenweg.
    Alle Widersprüche (fehlende Doku, nicht-partieller Anteil, unzulässiger Grund,
    kein USt-Betrag) wirft die Vorsteuer-Schicht (``vorsteuer.aufteilung_aus_brutto``)
    als ``KonfigFehler`` → Router → 400. Gibt ``(UstSplit, VorsteuerAufteilung)``."""
    if body.brutto_cent is None:
        raise KonfigFehler(
            "Vorsteuer-Aufteilung: brutto_cent ist Pflicht — der Zahlbetrag, aus dem "
            "die Vorsteuer zerlegt wird (docs/68 §7)")
    return vorsteuer.aufteilung_aus_brutto(
        buchung_id=body.buchung_id, brutto_cent=int(body.brutto_cent),
        satz_promille=int(body.satz_promille), abziehbar_promille=int(body.abziehbar_promille),
        schluessel=body.schluessel, begruendung=body.begruendung,
        grund_nicht_abziehbar=body.grund_nicht_abziehbar,
        ust_cent=int(body.ust_cent) if body.ust_cent is not None else None)


# ---------------------------------------------------- Row → Vertrag (spricht Typen)

def _regel_aus_row(r: Any) -> KlassifikationsRegel:
    return KlassifikationsRegel(
        kategorie_id=r["kategorie_id"], ust_kategorie=r["ust_kategorie"],
        satz_promille=int(r["satz_promille"]),
        vorsteuer_status=r["vorsteuer_status"] or None,
        vorsteuer_verbot_grund=r["vorsteuer_verbot_grund"] or None)


def _klassifikation_aus_row(r: Any) -> Klassifikation:
    kat = UStKategorie(r["ust_kategorie"])
    satz = int(r["satz_promille"])
    split: UstSplit | None = None
    if kat in MIT_SPLIT:
        netto, ust = int(r["netto_cent"]), int(r["ust_cent"])
        split = UstSplit(brutto_cent=netto + ust, netto_cent=netto,
                         ust_cent=ust, satz_promille=satz)
    return Klassifikation(
        buchung_id=r["buchung_id"], ust_kategorie=kat, quelle=r["quelle"],
        satz_promille=satz, split=split,
        vorsteuer_status=r["vorsteuer_status"] or None,
        vorsteuer_verbot_grund=r["vorsteuer_verbot_grund"] or None)


def _aufteilung_aus_row(r: Any) -> "vorsteuer.VorsteuerAufteilung":
    """Vertrags-Rekonstruktion der §15-Abs.-4-Aufteilung (die Vorsteuer-Schicht
    spricht Typen, nicht Rows). Die Aufteilungs-Invarianten (Doku-Pflicht,
    Anteil-Ableitung, partiell) werden dabei erneut geprüft."""
    return vorsteuer.VorsteuerAufteilung(
        buchung_id=r["buchung_id"], ust_cent=int(r["ust_cent"]),
        abziehbar_promille=int(r["abziehbar_promille"]),
        abziehbar_cent=int(r["abziehbar_cent"]),
        schluessel=r["schluessel"], begruendung=r["begruendung"],
        grund_nicht_abziehbar=r["grund_nicht_abziehbar"])


# ------------------------------------------------------------- Response-Sichten

def regel_public(r: Any) -> dict[str, Any]:
    return {
        "id": r["id"], "kategorie_id": r["kategorie_id"],
        "ust_kategorie": r["ust_kategorie"], "satz_promille": r["satz_promille"],
        "vorsteuer_status": r["vorsteuer_status"] or "",
        "vorsteuer_verbot_grund": r["vorsteuer_verbot_grund"] or "",
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def klassifikation_public(r: Any) -> dict[str, Any]:
    return {
        "id": r["id"], "buchung_id": r["buchung_id"],
        "ust_kategorie": r["ust_kategorie"], "satz_promille": r["satz_promille"],
        "netto_cent": r["netto_cent"], "ust_cent": r["ust_cent"],
        "vorsteuer_status": r["vorsteuer_status"] or "",
        "vorsteuer_verbot_grund": r["vorsteuer_verbot_grund"] or "",
        "quelle": r["quelle"], "entschieden_am": r["entschieden_am"],
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def ku_status_public(r: Any) -> dict[str, Any]:
    """Ein GESPEICHERTER §19-Status (``konfiguriert=True``) — Form trägt IMMER
    einen maschinenlesbaren Grund (der Vertrag lässt keinen Befund ohne Grund zu)."""
    return {
        "jahr": r["jahr"], "form": r["form"], "grund": r["grund"],
        "verzicht_ab_jahr": r["verzicht_ab_jahr"], "befund_text": r["befund_text"],
        "konfiguriert": True,
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def ku_status_default(jahr: int) -> dict[str, Any]:
    """Der §19-DEFAULT ohne gespeicherten Status (gate G-M4-STATUS, David 06.07.):
    Regelbesteuerung — USt wird ausgewiesen, UStVA fällig. BEWUSST kein fabrizierter
    ``StatusBefund`` (der bräuchte einen Grund) — ``konfiguriert=False`` markiert
    „noch nicht bestätigt"; der Monitor misst den Gesamtumsatz trotzdem."""
    return {
        "jahr": int(jahr), "form": BesteuerungsForm.REGELBESTEUERUNG.value,
        "grund": "", "verzicht_ab_jahr": 0, "konfiguriert": False,
        "befund_text": "Default (Gate G-M4-STATUS): Regelbesteuerung — USt wird "
                       "ausgewiesen, UStVA fällig. Trage deine §19-Faktenlage ein, "
                       "um den Status zu bestätigen.",
    }


def konfig_public(r: Any, *, konfiguriert: bool = True) -> dict[str, Any]:
    return {
        "zeitraum_typ": r["zeitraum_typ"], "dauerfrist": bool(r["dauerfrist"]),
        "besteuerung": r["besteuerung"], "konfiguriert": konfiguriert,
    }


def aufteilung_public(r: Any) -> dict[str, Any]:
    """Eine gespeicherte §15-Abs.-4-Aufteilung. ``nicht_abziehbar_cent`` ist
    abgeleitet (ust − abziehbar); ``anteil_prozent`` = der abziehbare Anteil."""
    ust, abz = int(r["ust_cent"]), int(r["abziehbar_cent"])
    return {
        "id": r["id"], "buchung_id": r["buchung_id"],
        "ust_kategorie": r["ust_kategorie"], "satz_promille": r["satz_promille"],
        "netto_cent": r["netto_cent"], "ust_cent": ust,
        "abziehbar_promille": r["abziehbar_promille"], "abziehbar_cent": abz,
        "nicht_abziehbar_cent": ust - abz,
        "anteil_prozent": round(int(r["abziehbar_promille"]) / 10, 1),
        "schluessel": r["schluessel"], "grund_nicht_abziehbar": r["grund_nicht_abziehbar"],
        "begruendung": r["begruendung"], "entschieden_am": r["entschieden_am"],
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


# ------------------------------------------------------------------ Speicher-Schicht

class UstSpeicher:
    """Repository der UStVA-Datenschicht + der CRUD-Router (M4-1). Kapselt die
    Regel-/Klassifikations-Tabellen (Upsert je Kategorie/Buchung, Vertrags-
    validiert) und den U-1-Arbeitsvorrat. ``ust_zeitraeume``/``ku_status`` sind
    hier nur als Schema präsent (Schreib-Pfad = M4-5/M4-2)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # --- ust_regeln (Kategorie-Default-CRUD) ---------------------------------

    def regel_row(self, user_id: str, kategorie_id: str) -> Any | None:
        return self.db.get_conn().execute(
            "SELECT * FROM ust_regeln WHERE user_id=? AND kategorie_id=? "
            "AND deleted_at IS NULL", (user_id, kategorie_id)).fetchone()

    def regeln_rows(self, user_id: str) -> list[Any]:
        return self.db.get_conn().execute(
            "SELECT * FROM ust_regeln WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY created_at", (user_id,)).fetchall()

    def regel_speichern(self, user_id: str, regel: KlassifikationsRegel) -> str:
        """Upsert je ``kategorie_id`` (EIN aktiver Default je Money-Kategorie).
        Erwartet einen bereits VERTRAGS-validierten ``KlassifikationsRegel`` —
        nur was der Vertrag anerkennt, erreicht die DB."""
        conn = self.db.get_conn()
        ts = now_iso()
        vst = regel.vorsteuer_status.value if regel.vorsteuer_status else ""
        grund = regel.vorsteuer_verbot_grund.value if regel.vorsteuer_verbot_grund else ""
        vorhanden = self.regel_row(user_id, regel.kategorie_id)
        if vorhanden:
            conn.execute(
                "UPDATE ust_regeln SET ust_kategorie=?, satz_promille=?, "
                "vorsteuer_status=?, vorsteuer_verbot_grund=?, updated_at=? "
                "WHERE id=? AND user_id=?",
                (regel.ust_kategorie.value, regel.satz_promille, vst, grund, ts,
                 vorhanden["id"], user_id))
            rid = vorhanden["id"]
        else:
            rid = new_id()
            conn.execute(
                "INSERT INTO ust_regeln (id, user_id, kategorie_id, ust_kategorie, "
                "satz_promille, vorsteuer_status, vorsteuer_verbot_grund, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, user_id, regel.kategorie_id, regel.ust_kategorie.value,
                 regel.satz_promille, vst, grund, ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "ust_regel_gesetzt",
                      {"kategorie_id": regel.kategorie_id,
                       "ust_kategorie": regel.ust_kategorie.value})
        return rid

    def regel_loeschen(self, user_id: str, kategorie_id: str) -> bool:
        row = self.regel_row(user_id, kategorie_id)
        if row is None:
            return False
        ts = now_iso()
        self.db.get_conn().execute(
            "UPDATE ust_regeln SET deleted_at=?, updated_at=? WHERE id=? AND user_id=?",
            (ts, ts, row["id"], user_id))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "ust_regel_geloescht", {"kategorie_id": kategorie_id})
        return True

    def regel(self, user_id: str, kategorie_id: str) -> KlassifikationsRegel | None:
        """Vertrags-Rekonstruktion einer Regel (der Klassifikator spricht Typen,
        nicht Rows). ``None`` bei unbekannter/gelöschter Regel."""
        r = self.regel_row(user_id, kategorie_id)
        return _regel_aus_row(r) if r is not None else None

    def regeln_map(self, user_id: str) -> dict[str, KlassifikationsRegel]:
        """{kategorie_id → KlassifikationsRegel} aller aktiven Regeln — die
        Regel-Seite des Vertrags-Lookups ``klassifiziere``."""
        return {r["kategorie_id"]: _regel_aus_row(r) for r in self.regeln_rows(user_id)}

    # --- ust_klassifikationen (Buchungs-Override-CRUD) -----------------------

    def klassifikation_row(self, user_id: str, buchung_id: str) -> Any | None:
        return self.db.get_conn().execute(
            "SELECT * FROM ust_klassifikationen WHERE user_id=? AND buchung_id=? "
            "AND deleted_at IS NULL", (user_id, buchung_id)).fetchone()

    def klassifikationen_rows(self, user_id: str,
                              buchung_id: str | None = None) -> list[Any]:
        conn = self.db.get_conn()
        if buchung_id is None:
            return conn.execute(
                "SELECT * FROM ust_klassifikationen WHERE user_id=? AND deleted_at IS NULL "
                "ORDER BY created_at", (user_id,)).fetchall()
        return conn.execute(
            "SELECT * FROM ust_klassifikationen WHERE user_id=? AND buchung_id=? "
            "AND deleted_at IS NULL ORDER BY created_at", (user_id, buchung_id)).fetchall()

    def klassifikation_speichern(self, user_id: str, k: Klassifikation) -> str:
        """Upsert je ``buchung_id`` (der Override schlägt die Regel). Erwartet
        einen VERTRAGS-validierten ``Klassifikation``; speichert netto/ust aus dem
        Split (0 bei splitlosen Kategorien) — brutto = netto+ust ist konstruktiv."""
        conn = self.db.get_conn()
        ts = now_iso()
        netto = k.split.netto_cent if k.split else 0
        ust = k.split.ust_cent if k.split else 0
        vst = k.vorsteuer_status.value if k.vorsteuer_status else ""
        grund = k.vorsteuer_verbot_grund.value if k.vorsteuer_verbot_grund else ""
        vorhanden = self.klassifikation_row(user_id, k.buchung_id)
        if vorhanden:
            conn.execute(
                "UPDATE ust_klassifikationen SET ust_kategorie=?, satz_promille=?, "
                "netto_cent=?, ust_cent=?, vorsteuer_status=?, vorsteuer_verbot_grund=?, "
                "quelle=?, entschieden_am=?, updated_at=? WHERE id=? AND user_id=?",
                (k.ust_kategorie.value, k.satz_promille, netto, ust, vst, grund,
                 k.quelle.value, ts, ts, vorhanden["id"], user_id))
            kid = vorhanden["id"]
        else:
            kid = new_id()
            conn.execute(
                "INSERT INTO ust_klassifikationen (id, user_id, buchung_id, ust_kategorie, "
                "satz_promille, netto_cent, ust_cent, vorsteuer_status, vorsteuer_verbot_grund, "
                "quelle, entschieden_am, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (kid, user_id, k.buchung_id, k.ust_kategorie.value, k.satz_promille,
                 netto, ust, vst, grund, k.quelle.value, ts, ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "ust_klassifikation_gesetzt",
                      {"buchung_id": k.buchung_id, "ust_kategorie": k.ust_kategorie.value})
        return kid

    def klassifikation_loeschen(self, user_id: str, buchung_id: str) -> bool:
        """Override zurücknehmen (Soft-Delete) — die Buchung fällt zurück auf die
        Kategorie-Regel (oder wird wieder Arbeitsvorrat, wenn keine Regel greift)."""
        row = self.klassifikation_row(user_id, buchung_id)
        if row is None:
            return False
        ts = now_iso()
        self.db.get_conn().execute(
            "UPDATE ust_klassifikationen SET deleted_at=?, updated_at=? "
            "WHERE id=? AND user_id=?", (ts, ts, row["id"], user_id))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "ust_klassifikation_geloescht", {"buchung_id": buchung_id})
        return True

    def klassifikationen_map(self, user_id: str) -> dict[str, Klassifikation]:
        """{buchung_id → Klassifikation} aller aktiven Overrides — die Override-
        Seite des Vertrags-Lookups ``klassifiziere`` (MANUELL schlägt REGEL)."""
        return {r["buchung_id"]: _klassifikation_aus_row(r)
                for r in self.klassifikationen_rows(user_id)}

    # --- ust_vorsteuer_aufteilung (§15 Abs. 4, M4-3) -------------------------

    def aufteilung_row(self, user_id: str, buchung_id: str) -> Any | None:
        return self.db.get_conn().execute(
            "SELECT * FROM ust_vorsteuer_aufteilung WHERE user_id=? AND buchung_id=? "
            "AND deleted_at IS NULL", (user_id, buchung_id)).fetchone()

    def aufteilungen_rows(self, user_id: str) -> list[Any]:
        return self.db.get_conn().execute(
            "SELECT * FROM ust_vorsteuer_aufteilung WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY created_at", (user_id,)).fetchall()

    def aufteilung_speichern(self, user_id: str, split: UstSplit,
                             aufteilung: "vorsteuer.VorsteuerAufteilung",
                             ust_kategorie: UStKategorie = UStKategorie.EINGANG_VST) -> str:
        """Upsert je ``buchung_id`` (EINE aktive Aufteilung je Buchung). Erwartet ein
        VERTRAGS-/Vorsteuer-validiertes ``(UstSplit, VorsteuerAufteilung)``-Paar
        (``_aufteilung_bauen``) — nur eine vollständig dokumentierte, aus dem Schlüssel
        abgeleitete Aufteilung erreicht die DB. Speichert den vollen Beleg-Split
        (netto/ust) NEBEN dem abziehbaren Anteil; das Ledger bleibt unberührt (U-4)."""
        conn = self.db.get_conn()
        ts = now_iso()
        vorhanden = self.aufteilung_row(user_id, aufteilung.buchung_id)
        werte = (ust_kategorie.value, split.satz_promille, split.netto_cent, split.ust_cent,
                 aufteilung.abziehbar_promille, aufteilung.abziehbar_cent,
                 aufteilung.schluessel.value, aufteilung.grund_nicht_abziehbar.value,
                 aufteilung.begruendung)
        if vorhanden:
            conn.execute(
                "UPDATE ust_vorsteuer_aufteilung SET ust_kategorie=?, satz_promille=?, "
                "netto_cent=?, ust_cent=?, abziehbar_promille=?, abziehbar_cent=?, "
                "schluessel=?, grund_nicht_abziehbar=?, begruendung=?, entschieden_am=?, "
                "updated_at=? WHERE id=? AND user_id=?",
                (*werte, ts, ts, vorhanden["id"], user_id))
            aid = vorhanden["id"]
        else:
            aid = new_id()
            conn.execute(
                "INSERT INTO ust_vorsteuer_aufteilung (id, user_id, buchung_id, "
                "ust_kategorie, satz_promille, netto_cent, ust_cent, abziehbar_promille, "
                "abziehbar_cent, schluessel, grund_nicht_abziehbar, begruendung, "
                "entschieden_am, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, user_id, aufteilung.buchung_id, *werte, ts, ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "ust_vorsteuer_aufteilung_gesetzt",
                      {"buchung_id": aufteilung.buchung_id,
                       "abziehbar_promille": aufteilung.abziehbar_promille})
        return aid

    def aufteilung_loeschen(self, user_id: str, buchung_id: str) -> bool:
        """Aufteilung zurücknehmen (Soft-Delete) — die Buchung fällt zurück in den
        Arbeitsvorrat (bzw. auf ihre Kategorie-Regel, falls eine greift)."""
        row = self.aufteilung_row(user_id, buchung_id)
        if row is None:
            return False
        ts = now_iso()
        self.db.get_conn().execute(
            "UPDATE ust_vorsteuer_aufteilung SET deleted_at=?, updated_at=? "
            "WHERE id=? AND user_id=?", (ts, ts, row["id"], user_id))
        self.db.get_conn().commit()
        self.db.audit(user_id, "user", "ust_vorsteuer_aufteilung_geloescht",
                      {"buchung_id": buchung_id})
        return True

    def aufteilungen_map(self, user_id: str) -> dict[str, "vorsteuer.VorsteuerAufteilung"]:
        """{buchung_id → VorsteuerAufteilung} aller aktiven §15-Abs.-4-Aufteilungen."""
        return {r["buchung_id"]: _aufteilung_aus_row(r)
                for r in self.aufteilungen_rows(user_id)}

    # --- U-1-Arbeitsvorrat: offene Buchungen des Zeitraums -------------------

    def offene_buchungen(self, user_id: str, zeitraum: UStVAZeitraum,
                         bewegungen: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Der U-1-Arbeitsvorrat (docs/68 §4/§11): welche Buchungen des Zeitraums
        haben (noch) KEINE eindeutige USt-Klassifikation? EINE Wahrheit — die
        Frage ist exakt „für welche Buchung wirft ``klassifiziere`` ein
        ``KlassifikationUnklar``": Override → Kategorie-Regel → sonst offen
        (``netto == 0`` = interner Transfer ⇒ ``KEIN_UMSATZ``, gilt als geklärt).

        Reine Lese-Sicht des Vollständigkeits-Wächters (``pruefe_vollstaendig``);
        rechnet nichts, mutiert nichts (U-4). Erst wenn ``offen`` leer ist, darf
        ein Datensatz überhaupt entstehen (M4-4). Eine dokumentierte §15-Abs.-4-
        Aufteilung (M4-3) gilt als geklärt — sie ist der bewusste Entscheid für eine
        teilweise abziehbare Buchung (die der Vertrag als ``TEILWEISE`` sperrt, sodass
        ``klassifiziere`` sie sonst nie klären könnte)."""
        regeln = self.regeln_map(user_id)
        overrides = self.klassifikationen_map(user_id)
        aufteilungen = self.aufteilungen_map(user_id)
        offen: list[dict[str, Any]] = []
        klassifiziert = 0
        for b in bewegungen:
            if str(b.get("id", "") or "") in aufteilungen:   # §15-Abs.-4-Split = geklärt (M4-3)
                klassifiziert += 1
                continue
            try:
                klassifiziere(b, regeln, overrides)
                klassifiziert += 1
            except KlassifikationUnklar:
                offen.append({
                    "id": str(b.get("id", "") or ""),
                    "datum": b.get("datum", "") or "",
                    "netto": int(b.get("netto", 0) or 0),
                    "kategorie_id": b.get("kategorie_id") or "",
                    "kategorie_name": b.get("kategorie_name") or "",
                    "gegenpartei": b.get("gegenpartei") or "",
                    "verwendungszweck": b.get("verwendungszweck") or "",
                })
        von, bis = zeitraum.grenzen()
        return {
            "zeitraum": zeitraum.schluessel(), "von": von, "bis": bis,
            "offen": offen, "offen_anzahl": len(offen),
            "klassifiziert_anzahl": klassifiziert,
            "gesamt": klassifiziert + len(offen),
            "vollstaendig": not offen,
        }

    # --- Vorsteuer-Warnungen: „ABZIEHBAR ohne Beleg-Ref" (M4-3) --------------

    @staticmethod
    def _vst_warn(b: Mapping[str, Any], abziehbar_cent: int, art: str) -> dict[str, Any]:
        return {
            "id": str(b.get("id", "") or ""),
            "datum": (b.get("datum", "") or "")[:10],
            "gegenpartei": b.get("gegenpartei") or "",
            "verwendungszweck": b.get("verwendungszweck") or "",
            "kategorie_name": b.get("kategorie_name") or "",
            "abziehbar_cent": int(abziehbar_cent),
            "art": art,     # 'klassifikation' | 'aufteilung'
        }

    def vorsteuer_warnungen(self, user_id: str, zeitraum: UStVAZeitraum,
                            bewegungen: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Die Beleg-Ref-Warnregel (docs/68 §7): welche ABZIEHBAREN Vorsteuer-Abzüge
        des Zeitraums haben KEINE Beleg-Kante (``buchungen.beleg_ref``, V15
        ``admin:dokument:<id>``)? §15 Abs. 1 verlangt eine ordnungsgemäße Rechnung;
        fehlt der Beleg, ist der Abzug formal nicht nachgewiesen ⇒ WARNUNG (kein Block
        — Kleinbetragsrechnungen genügen erleichtert, der Beleg kann außerhalb Money
        liegen). Deckt BEIDE Abzugs-Wege ab: normale ABZIEHBAR-Klassifikationen
        (Regel/Override) UND den abziehbaren Teil einer §15-Abs.-4-Aufteilung.

        Reine Lese-Sicht über die injizierte Bewegungen-Naht (die ``beleg_ref``
        mitliefert) — kein Ledger-Zugriff, keine Mutation (U-4)."""
        regeln = self.regeln_map(user_id)
        overrides = self.klassifikationen_map(user_id)
        aufteilungen = self.aufteilungen_map(user_id)
        warnungen: list[dict[str, Any]] = []
        geprueft = 0
        for b in bewegungen:
            bid = str(b.get("id", "") or "")
            beleg = str(b.get("beleg_ref", "") or "")
            auf = aufteilungen.get(bid)
            if auf is not None:                         # §15-Abs.-4-Aufteilung (M4-3)
                if auf.abziehbar_cent > 0:
                    geprueft += 1
                    if not vorsteuer.hat_beleg_ref(beleg):
                        warnungen.append(self._vst_warn(b, auf.abziehbar_cent, "aufteilung"))
                continue
            try:
                k = klassifiziere(b, regeln, overrides)
            except KlassifikationUnklar:
                continue                                # offen ⇒ Arbeitsvorrat, kein Vorsteuer-Fall
            abz = vorsteuer.abziehbare_vorsteuer(k)     # ABZIEHBAR ⇒ Beleg-USt, sonst 0
            if abz > 0:
                geprueft += 1
                if not vorsteuer.hat_beleg_ref(beleg):
                    warnungen.append(self._vst_warn(b, abz, "klassifikation"))
        von, bis = zeitraum.grenzen()
        return {
            "zeitraum": zeitraum.schluessel(), "von": von, "bis": bis,
            "warnungen": warnungen, "warn_anzahl": len(warnungen),
            "geprueft_anzahl": geprueft, "sauber": not warnungen,
        }

    # --- ku_status (§19-Jahres-Status, M4-2) ---------------------------------

    def ku_status_row(self, user_id: str, jahr: int) -> Any | None:
        return self.db.get_conn().execute(
            "SELECT * FROM ku_status WHERE user_id=? AND jahr=? AND deleted_at IS NULL",
            (user_id, int(jahr))).fetchone()

    def ku_status_setzen(self, user_id: str, jahr: int, vorjahr_cent: int,
                         laufend_cent: int, verzicht_ab_jahr: int = 0):
        """Upsert des §19-Jahres-Status. Form + Grund + Text kommen IMMER aus dem
        Vertrags-Befund (``pruefe_kleinunternehmer``) — nie Form ohne Grund
        (docs/68 §6). Wirft ``SchwellenUnbekannt`` (Jahr < 2025) / ``KonfigFehler``
        (negativer Umsatz) → Router → 400. Der Verzicht bindet 5 Jahre (der
        Vertrag rechnet die Bindung; hier wird nur ``ab_jahr`` gemerkt)."""
        verzicht = VerzichtsErklaerung(ab_jahr=int(verzicht_ab_jahr)) if verzicht_ab_jahr else None
        befund = pruefe_kleinunternehmer(int(jahr), int(vorjahr_cent),
                                         int(laufend_cent), verzicht)
        conn = self.db.get_conn()
        ts = now_iso()
        vorhanden = self.ku_status_row(user_id, jahr)
        if vorhanden:
            conn.execute(
                "UPDATE ku_status SET form=?, grund=?, verzicht_ab_jahr=?, "
                "befund_text=?, updated_at=? WHERE id=? AND user_id=?",
                (befund.form.value, befund.grund.value, int(verzicht_ab_jahr),
                 befund.text, ts, vorhanden["id"], user_id))
        else:
            conn.execute(
                "INSERT INTO ku_status (id, user_id, jahr, form, grund, "
                "verzicht_ab_jahr, befund_text, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (new_id(), user_id, int(jahr), befund.form.value, befund.grund.value,
                 int(verzicht_ab_jahr), befund.text, ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "ust_ku_status_gesetzt",
                      {"jahr": int(jahr), "form": befund.form.value,
                       "grund": befund.grund.value})
        return befund

    def ku_status_holen(self, user_id: str, jahr: int) -> dict[str, Any]:
        """Der gespeicherte §19-Status oder der Regelbesteuerungs-Default
        (``konfiguriert=False``, gate G-M4-STATUS)."""
        row = self.ku_status_row(user_id, jahr)
        return ku_status_public(row) if row is not None else ku_status_default(jahr)

    def ku_status_loeschen(self, user_id: str, jahr: int) -> bool:
        """§19-Status zurücknehmen (Soft-Delete) — das Jahr fällt auf den Default
        (Regelbesteuerung, unkonfiguriert) zurück."""
        row = self.ku_status_row(user_id, jahr)
        if row is None:
            return False
        ts = now_iso()
        conn = self.db.get_conn()
        conn.execute("UPDATE ku_status SET deleted_at=?, updated_at=? WHERE id=? AND user_id=?",
                     (ts, ts, row["id"], user_id))
        conn.commit()
        self.db.audit(user_id, "user", "ust_ku_status_geloescht", {"jahr": int(jahr)})
        return True

    # --- ust_konfig (stehende Voranmeldungs-Konfiguration, M4-2) --------------

    def konfig_row(self, user_id: str) -> Any | None:
        return self.db.get_conn().execute(
            "SELECT * FROM ust_konfig WHERE user_id=? AND deleted_at IS NULL",
            (user_id,)).fetchone()

    def konfig_holen(self, user_id: str) -> dict[str, Any]:
        """Die stehende Konfig oder der Vertrags-Default (Quartal + Ist + ohne
        Dauerfrist, ``konfiguriert=False``)."""
        row = self.konfig_row(user_id)
        if row is not None:
            return konfig_public(row, konfiguriert=True)
        k = VoranmeldungsKonfig()   # Default: Quartal + Ist + ohne Dauerfrist (Vertrag)
        return {"zeitraum_typ": k.zeitraum_typ.value, "dauerfrist": k.dauerfrist,
                "besteuerung": k.besteuerung.value, "konfiguriert": False}

    def konfig_setzen(self, user_id: str, konfig: VoranmeldungsKonfig) -> None:
        """Upsert der stehenden Konfig (EIN aktiver Datensatz je Nutzer). Erwartet
        eine VERTRAGS-validierte ``VoranmeldungsKonfig`` (SOLL ist dort gesperrt)."""
        conn = self.db.get_conn()
        ts = now_iso()
        dauer = 1 if konfig.dauerfrist else 0
        vorhanden = self.konfig_row(user_id)
        if vorhanden:
            conn.execute(
                "UPDATE ust_konfig SET zeitraum_typ=?, dauerfrist=?, besteuerung=?, "
                "updated_at=? WHERE id=? AND user_id=?",
                (konfig.zeitraum_typ.value, dauer, konfig.besteuerung.value, ts,
                 vorhanden["id"], user_id))
        else:
            conn.execute(
                "INSERT INTO ust_konfig (id, user_id, zeitraum_typ, dauerfrist, "
                "besteuerung, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (new_id(), user_id, konfig.zeitraum_typ.value, dauer,
                 konfig.besteuerung.value, ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "ust_konfig_gesetzt",
                      {"zeitraum_typ": konfig.zeitraum_typ.value,
                       "besteuerung": konfig.besteuerung.value})

    # --- §19-Gesamtumsatz-Monitor (Schwellen-Wächter + Regime-Schnitt, M4-2) --

    def ku_monitor(self, user_id: str, jahr: int,
                   bewegungen_jahr: Iterable[Mapping[str, Any]],
                   bewegungen_vorjahr: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Der §19-Gesamtumsatz-Monitor (docs/68 §6/§11): misst den Ist-Zufluss
        (vereinnahmte Entgelte) des laufenden + des Vorjahres aus KLASSIFIZIERTEN
        Summen, vergleicht ihn mit den Jahres-Schwellen (U-2) und liefert die
        80 %/100 %-Warn-Stufen + den unterjährigen Regime-Schnitt.

        Reine Lese-Sicht — keine Ledger-Mutation (U-4); die Bewegungen kommen über
        die injizierte Naht (kein Ledger-Zugriff/keine Kurs-Kopie hier). Der
        gemessene Befund (``befund_gemessen``) nutzt die Live-Zahlen + einen ggf.
        gespeicherten Verzicht; ``status_erklaert`` ist der vom Nutzer deklarierte
        (oder Default-)Status. Jahr < 2025 ⇒ ``SchwellenUnbekannt`` (Router → 400)."""
        schwellen = schwellen_fuer(int(jahr))     # U-2: fail-closed (Alt-Recht wirft)
        regeln = self.regeln_map(user_id)
        overrides = self.klassifikationen_map(user_id)
        posten_j, offen_j = monitor.umsatz_posten(bewegungen_jahr, regeln, overrides)
        posten_v, offen_v = monitor.umsatz_posten(bewegungen_vorjahr, regeln, overrides)
        laufend = monitor.gesamtumsatz_cent((kat, e) for _, kat, e in posten_j)
        vorjahr = monitor.gesamtumsatz_cent((kat, e) for _, kat, e in posten_v)

        row = self.ku_status_row(user_id, jahr)
        verzicht_ab = int(row["verzicht_ab_jahr"]) if row and row["verzicht_ab_jahr"] else 0
        verzicht = VerzichtsErklaerung(ab_jahr=verzicht_ab) if verzicht_ab else None
        # Negativer Gesamtumsatz (Netto-Erstattungsüberhang) ist fürs Schwellen-Maß
        # 0 (weit unter der Grenze) — die WAHRE Messzahl bleibt ehrlich in „gemessen".
        befund = pruefe_kleinunternehmer(int(jahr), max(0, vorjahr), max(0, laufend), verzicht)

        warn_laufend = monitor.warnstufe(laufend, schwellen.laufend_max_cent)   # 100k HART, unterjährig
        warn_prognose = monitor.warnstufe(laufend, schwellen.vorjahr_max_cent)  # laufend vs 25k → nächstes Jahr KU-Verlust
        warn_vorjahr = monitor.warnstufe(vorjahr, schwellen.vorjahr_max_cent)   # Vorjahr vs 25k → dieses Jahr regelbesteuert?
        regime = monitor.regime_schnitt(int(jahr), posten_j, schwellen.laufend_max_cent)
        return {
            "jahr": int(jahr),
            "gemessen": {
                "laufend_cent": laufend, "vorjahr_cent": vorjahr,
                "offen_laufend": offen_j, "offen_vorjahr": offen_v,
                "hinweis_offen": bool(offen_j or offen_v),
            },
            "schwellen": {
                "vorjahr_max_cent": schwellen.vorjahr_max_cent,
                "laufend_max_cent": schwellen.laufend_max_cent,
                "modus": schwellen.modus,
            },
            "warn": {
                "laufend_100k": warn_laufend,
                "prognose_25k": warn_prognose,
                "vorjahr_25k": warn_vorjahr,
            },
            "ampel": monitor.schlimmste_ampel(warn_laufend, warn_prognose),
            "befund_gemessen": {"form": befund.form.value, "grund": befund.grund.value,
                                "text": befund.text},
            "status_erklaert": ku_status_public(row) if row is not None else ku_status_default(jahr),
            "regime_schnitt": regime,
        }

    # --- HTTP-Router (M4-1: Regeln-CRUD · Klassifikations-Override · Arbeitsvorrat) --

    def build_router(self, bewegungen_fn: BewegungenFn) -> APIRouter:
        """Der M4-1/M4-2-Router. Volle Pfade unter ``/api/ust/…`` (KEIN ``prefix=`` —
        das umgeht die Doppel-Präfix-Falle des M1-2-Konnektor-Routers). Arbeitsvorrat
        (M4-1) UND Gesamtumsatz-Monitor (M4-2) beziehen die Buchungen über die
        injizierte ``bewegungen_fn`` (Währungs-/Netto-Logik bleibt in main — kein
        Ledger-Zugriff/keine Kurs-Kopie hier, U-4). M4-2-Routen: ``ku-status``
        (GET/POST/DELETE), ``ku-monitor`` (GET), ``konfig`` (GET/POST). M4-3-Routen
        (gate G-M4-VORSTEUER): ``vorsteuer/aufteilung`` (GET/POST/DELETE),
        ``vorsteuer/warnungen`` (GET, Beleg-Ref-Kopplung), ``vorsteuer/bewirtung`` (GET)."""
        r = APIRouter()

        # --- ust_regeln --------------------------------------------------
        @r.get("/api/ust/regeln")
        def regeln_liste(user: UserContext = Depends(current_user)):
            return [regel_public(row) for row in self.regeln_rows(user.user_id)]

        @r.post("/api/ust/regeln")
        def regel_setzen(body: RegelIn, user: UserContext = Depends(current_user)):
            try:
                regel = _regel_bauen(body)
            except KonfigFehler as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            self.regel_speichern(user.user_id, regel)
            return regel_public(self.regel_row(user.user_id, regel.kategorie_id))

        @r.get("/api/ust/regeln/{kategorie_id}")
        def regel_holen(kategorie_id: str, user: UserContext = Depends(current_user)):
            row = self.regel_row(user.user_id, kategorie_id)
            if row is None:
                return JSONResponse({"error": "Regel unbekannt"}, status_code=404)
            return regel_public(row)

        @r.delete("/api/ust/regeln/{kategorie_id}")
        def regel_loeschen(kategorie_id: str, user: UserContext = Depends(current_user)):
            if not self.regel_loeschen(user.user_id, kategorie_id):
                return JSONResponse({"error": "Regel unbekannt"}, status_code=404)
            return {"ok": True}

        # --- ust_klassifikationen (Override) -----------------------------
        @r.get("/api/ust/klassifikationen")
        def klassifikationen_liste(buchung_id: str | None = None,
                                   user: UserContext = Depends(current_user)):
            return [klassifikation_public(row)
                    for row in self.klassifikationen_rows(user.user_id, buchung_id)]

        @r.post("/api/ust/klassifikationen")
        def klassifikation_setzen(body: KlassifikationIn,
                                  user: UserContext = Depends(current_user)):
            try:
                k = _klassifikation_bauen(body)
            except KonfigFehler as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            self.klassifikation_speichern(user.user_id, k)
            return klassifikation_public(self.klassifikation_row(user.user_id, k.buchung_id))

        @r.delete("/api/ust/klassifikationen/{buchung_id}")
        def klassifikation_loeschen(buchung_id: str,
                                    user: UserContext = Depends(current_user)):
            if not self.klassifikation_loeschen(user.user_id, buchung_id):
                return JSONResponse({"error": "Klassifikation unbekannt"}, status_code=404)
            return {"ok": True}

        # --- U-1-Arbeitsvorrat -------------------------------------------
        @r.get("/api/ust/offene")
        def offene_liste(jahr: int, nummer: int, typ: str = "quartal",
                         user: UserContext = Depends(current_user)):
            """Offene (unklassifizierte) Buchungen des Voranmeldungszeitraums —
            der U-1-Arbeitsvorrat. Ungültiger Zeitraum ⇒ 400 (der Vertrag
            validiert ``UStVAZeitraum`` konstruktiv, U-8)."""
            try:
                zeitraum = UStVAZeitraum(jahr=jahr, typ=typ, nummer=nummer)
            except (ZeitraumFehler, KonfigFehler) as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            von, bis = zeitraum.grenzen()
            bewegungen = list(bewegungen_fn(user.user_id, von, bis))
            return self.offene_buchungen(user.user_id, zeitraum, bewegungen)

        # --- §19-Status (ku_status, M4-2 · gate G-M4-STATUS) -------------
        @r.get("/api/ust/ku-status")
        def ku_status_get(jahr: int, user: UserContext = Depends(current_user)):
            """Der §19-Status des Jahres (gespeichert oder Regelbesteuerungs-Default)."""
            return self.ku_status_holen(user.user_id, jahr)

        @r.post("/api/ust/ku-status")
        def ku_status_post(body: KuStatusIn, user: UserContext = Depends(current_user)):
            """§19-Status je Jahr aus der Faktenlage ableiten + speichern. Form/Grund
            kommen aus ``pruefe_kleinunternehmer`` (nie Form ohne Grund); Jahr < 2025
            oder negativer Umsatz ⇒ 400 (U-2)."""
            try:
                self.ku_status_setzen(user.user_id, body.jahr, body.vorjahr_umsatz_cent,
                                      body.laufend_umsatz_cent, body.verzicht_ab_jahr)
            except (SchwellenUnbekannt, KonfigFehler) as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            return self.ku_status_holen(user.user_id, body.jahr)

        @r.delete("/api/ust/ku-status/{jahr}")
        def ku_status_del(jahr: int, user: UserContext = Depends(current_user)):
            if not self.ku_status_loeschen(user.user_id, jahr):
                return JSONResponse({"error": "Kein gespeicherter §19-Status für dieses Jahr"},
                                    status_code=404)
            return {"ok": True}

        # --- §19-Gesamtumsatz-Monitor (M4-2 · Schwellen-Ampel + Regime-Schnitt) --
        @r.get("/api/ust/ku-monitor")
        def ku_monitor_get(jahr: int, user: UserContext = Depends(current_user)):
            """Gesamtumsatz-Monitor des Jahres: Ist-Zufluss laufend + Vorjahr über die
            injizierte Bewegungen-Naht, Schwellen-Ampel (80 %/100 %) + Regime-Schnitt.
            Jahr < 2025 ⇒ 400 (Alt-Recht nicht modelliert, U-2)."""
            von, bis = f"{jahr:04d}-01-01", f"{jahr:04d}-12-31"
            vvon, vbis = f"{jahr - 1:04d}-01-01", f"{jahr - 1:04d}-12-31"
            bew = list(bewegungen_fn(user.user_id, von, bis))
            bewv = list(bewegungen_fn(user.user_id, vvon, vbis))
            try:
                return self.ku_monitor(user.user_id, jahr, bew, bewv)
            except (SchwellenUnbekannt, KonfigFehler) as e:
                return JSONResponse({"error": str(e)}, status_code=400)

        # --- Voranmeldungs-Konfiguration (ust_konfig, M4-2 · gate G-M4-ZEITRAUM) --
        @r.get("/api/ust/konfig")
        def konfig_get(user: UserContext = Depends(current_user)):
            """Die stehende Konfig (oder der Default Quartal + Ist + ohne Dauerfrist)."""
            return self.konfig_holen(user.user_id)

        @r.post("/api/ust/konfig")
        def konfig_post(body: KonfigIn, user: UserContext = Depends(current_user)):
            """Zeitraum-Rhythmus/Ist-Soll/Dauerfrist umschalten. SOLL-Versteuerung
            ist im Vertrag gesperrt (v1, U-8) ⇒ 400 mit Klartext-Grund."""
            try:
                konfig = VoranmeldungsKonfig(
                    zeitraum_typ=body.zeitraum_typ, dauerfrist=body.dauerfrist,
                    besteuerung=body.besteuerung)
            except KonfigFehler as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            self.konfig_setzen(user.user_id, konfig)
            return self.konfig_holen(user.user_id)

        # --- §15-Abs.-4-Aufteilung (ust_vorsteuer_aufteilung, M4-3 · gate G-M4-VORSTEUER) --
        @r.get("/api/ust/vorsteuer/aufteilung")
        def aufteilung_liste(user: UserContext = Depends(current_user)):
            """Alle gespeicherten §15-Abs.-4-Aufteilungen (teilweise abziehbare VoSt)."""
            return [aufteilung_public(row) for row in self.aufteilungen_rows(user.user_id)]

        @r.post("/api/ust/vorsteuer/aufteilung")
        def aufteilung_setzen(body: AufteilungIn, user: UserContext = Depends(current_user)):
            """Eine teilweise abziehbare Vorsteuer §15-Abs.-4-konform aufteilen (Upsert
            je Buchung). Fehlende Doku / nicht-partieller Anteil / unzulässiger Grund /
            kein USt-Betrag ⇒ 400 (der Vertrag/die Vorsteuer-Schicht ist der Torwächter)."""
            try:
                split, aufteilung = _aufteilung_bauen(body)
            except KonfigFehler as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            self.aufteilung_speichern(user.user_id, split, aufteilung)
            return aufteilung_public(self.aufteilung_row(user.user_id, body.buchung_id))

        @r.delete("/api/ust/vorsteuer/aufteilung/{buchung_id}")
        def aufteilung_del(buchung_id: str, user: UserContext = Depends(current_user)):
            if not self.aufteilung_loeschen(user.user_id, buchung_id):
                return JSONResponse({"error": "Keine §15-Abs.-4-Aufteilung für diese Buchung"},
                                    status_code=404)
            return {"ok": True}

        # --- Beleg-Ref-Warnungen „ABZIEHBAR ohne Beleg-Ref" (M4-3) -------
        @r.get("/api/ust/vorsteuer/warnungen")
        def vorsteuer_warnungen_ep(jahr: int, nummer: int, typ: str = "quartal",
                                   user: UserContext = Depends(current_user)):
            """Vorsteuer-Abzüge des Zeitraums, denen die Beleg-Kante fehlt (§15 Abs. 1
            — ordnungsgemäße Rechnung). Ungültiger Zeitraum ⇒ 400 (U-8)."""
            try:
                zeitraum = UStVAZeitraum(jahr=jahr, typ=typ, nummer=nummer)
            except (ZeitraumFehler, KonfigFehler) as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            von, bis = zeitraum.grenzen()
            bewegungen = list(bewegungen_fn(user.user_id, von, bis))
            return self.vorsteuer_warnungen(user.user_id, zeitraum, bewegungen)

        # --- Bewirtungs-Vergleich (rein informativ, M4-3) ----------------
        @r.get("/api/ust/vorsteuer/bewirtung")
        def bewirtung_ep(brutto_cent: int, satz_promille: int = 190,
                         user: UserContext = Depends(current_user)):
            """Die Bewirtungs-Falle sichtbar machen: Vorsteuer 100 % abziehbar (§15
            Abs. 1a S. 2), ertragsteuerlich nur 70 % Betriebsausgabe. Rein rechnerisch,
            KEINE Buchung. Unzulässiger Satz ⇒ 400."""
            try:
                split = split_aus_brutto(int(brutto_cent), int(satz_promille))
            except KonfigFehler as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            return {"netto_cent": split.netto_cent, "ust_cent": split.ust_cent,
                    **vorsteuer.bewirtung_vergleich(split.netto_cent, split.ust_cent)}

        return r
