"""Domänen-Logik von Dizz Healthy — Messwerte · Supplements · Verletzungen ·
Training · Termine.

Hier sitzt die App-eigene Substanz; alles Vertragliche (Health/Summary/Settings/
Account/Datenrechte/Defense/Mini-Dizzi) liefert appkit über ``create_app``.

Datenmodell folgt zwingend den Vertrags-Konventionen (UUID/user_id/Timestamps/
Soft-Delete, appkit/db.py): so greifen DSGVO-Export, Lösch-Kaskade und Retention
ohne Per-App-Code — bei HOCHSENSIBLEN Gesundheitsdaten besonders wichtig.

── Trends deterministisch, Hinweise per KI (Trennung mit Absicht) ─────────────
``trends()`` rechnet rein deterministisch aus den Messwerten (jüngster Wert,
Richtung, Schnitt) — verlässlich, ohne Modell. Die SANFTEN HINWEISE legt die
lokale KI (ki.py) als Schicht obendrauf, immer mit Disclaimer und NIE als Diagnose.

── Vorbereitete Anschlüsse (Gesetz 5 · docs/RECHERCHE §3, sources.py) ──────────
- ``messwerte.quelle``/``extern_id``/``etag`` = SYNC-READY-Felder: Herkunft (manuell/
  apple_health/ble/…), stabiler Fremd-Schlüssel (Dedupe) und Versionsmarke für den
  späteren Wearable-Sync. v1 füllt ``quelle='manuell'``.
- ``GET /api/quellen`` macht die vorbereiteten ``HealthSource``-Adapter SICHTBAR
  (Apple/Health-Connect/Terra/BLE — alle dormant) — Bewusstsein über ihr Vorhandensein.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from appkit.auth import UserContext, current_user
from appkit.db import Database, new_id, now_iso
from appkit.summary import Kpi

from . import fhir, ki

# --- Domänen-Vokabular (UI + Validierung teilen sich diese Listen) -----------
SUPP_FREQUENZ = ("taeglich", "2x_taeglich", "woechentlich", "bei_bedarf")
SUPP_ZEITPUNKT = ("morgens", "mittags", "abends", "nacht", "egal")
VERLETZUNG_STATUS = ("akut", "heilend", "verheilt")
VERLETZUNG_SCHWERE = ("leicht", "mittel", "schwer")
TRAINING_INTENSITAET = ("locker", "moderat", "intensiv")
TERMIN_KATEGORIE = ("arzt", "vorsorge", "impfung", "therapie", "labor", "sonstiges")

# Domänen-Schema — direkt an create_app/Database übergeben (extra_schema).
SCHEMA = """
CREATE TABLE IF NOT EXISTS messwerte (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    art          TEXT NOT NULL,                  -- Schlüssel aus fhir.MESSWERT_ARTEN
    wert         REAL NOT NULL,
    einheit      TEXT NOT NULL DEFAULT '',
    gemessen_am  TEXT NOT NULL,                  -- ISO-8601 (Zeitpunkt der Messung)
    notiz        TEXT NOT NULL DEFAULT '',
    quelle       TEXT NOT NULL DEFAULT 'manuell',-- manuell|apple_health|ble|… (Sync-Herkunft)
    extern_id    TEXT NOT NULL DEFAULT '',       -- Fremd-ID (Dedupe + Wearable-Sync, Slot)
    etag         TEXT NOT NULL DEFAULT '',       -- Versionsmarke (Konfliktauflösung, Slot)
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_messwerte ON messwerte (user_id, art, gemessen_am);
CREATE INDEX IF NOT EXISTS idx_messwerte_extern ON messwerte (user_id, quelle, extern_id);

CREATE TABLE IF NOT EXISTS supplements (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    name         TEXT NOT NULL,
    dosis        TEXT NOT NULL DEFAULT '',       -- frei (z. B. '1000', '2 Kapseln')
    einheit      TEXT NOT NULL DEFAULT '',       -- z. B. 'mg', 'IE', 'µg'
    frequenz     TEXT NOT NULL DEFAULT 'taeglich',
    zeitpunkt    TEXT NOT NULL DEFAULT 'egal',
    aktiv        INTEGER NOT NULL DEFAULT 1,
    begonnen_am  TEXT NOT NULL DEFAULT '',
    notiz        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_supplements ON supplements (user_id, aktiv, name);

CREATE TABLE IF NOT EXISTS verletzungen (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    koerperregion TEXT NOT NULL,
    beschreibung  TEXT NOT NULL DEFAULT '',
    schweregrad   TEXT NOT NULL DEFAULT 'leicht',-- leicht|mittel|schwer
    status        TEXT NOT NULL DEFAULT 'akut',  -- akut|heilend|verheilt
    aufgetreten_am TEXT NOT NULL DEFAULT '',
    notiz         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_verletzungen ON verletzungen (user_id, status, created_at);

CREATE TABLE IF NOT EXISTS trainings (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    art             TEXT NOT NULL,               -- frei (z. B. 'Laufen', 'Kraft')
    dauer_min       INTEGER NOT NULL DEFAULT 0,
    intensitaet     TEXT NOT NULL DEFAULT 'moderat',
    kennzahl_name   TEXT NOT NULL DEFAULT '',    -- frei (z. B. 'Distanz', 'Gewicht')
    kennzahl_wert   REAL,
    kennzahl_einheit TEXT NOT NULL DEFAULT '',
    trainiert_am    TEXT NOT NULL,               -- ISO-Date/-DateTime
    notiz           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_trainings ON trainings (user_id, trainiert_am);

CREATE TABLE IF NOT EXISTS termine (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    titel        TEXT NOT NULL,
    kategorie    TEXT NOT NULL DEFAULT 'arzt',   -- arzt|vorsorge|impfung|therapie|labor|sonstiges
    beginn       TEXT NOT NULL,                  -- ISO-8601 (Date oder DateTime)
    ort          TEXT NOT NULL DEFAULT '',
    notiz        TEXT NOT NULL DEFAULT '',
    erinnerung   INTEGER NOT NULL DEFAULT 1,     -- Push an Dizzi-Meldungen (Wächter folgt)
    quelle       TEXT NOT NULL DEFAULT 'lokal',  -- lokal|ical|… (Sync-Slot)
    extern_id    TEXT NOT NULL DEFAULT '',
    etag         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_termine ON termine (user_id, beginn);

-- Tages-Aktivitäts-Aggregat (P1d, Hybrid): abgeleiteter CACHE der Aktivitäts-
-- Messwerte eines Tages (Schritte/Distanz/…). Quelle der Wahrheit bleibt
-- ``messwerte`` (roh, FHIR-/Sync-fähig) — diese Tabelle macht Tages-Ringe und
-- Wochen/Monats-Verläufe schnell. Wird aus den Messwerten neu berechnet
-- (``_recompute_aktivitaet_tag``), nie unabhängig editiert.
CREATE TABLE IF NOT EXISTS aktivitaet_tag (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    datum          TEXT NOT NULL,                -- YYYY-MM-DD
    schritte       REAL,
    distanz        REAL,                         -- km
    etagen         REAL,
    aktive_minuten REAL,
    kalorien       REAL,
    stehstunden    REAL,
    schlaf         REAL,                         -- h
    quelle         TEXT NOT NULL DEFAULT 'manuell',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    deleted_at     TEXT,
    UNIQUE (user_id, datum)
);
CREATE INDEX IF NOT EXISTS idx_aktivitaet_tag ON aktivitaet_tag (user_id, datum);
"""

# Aktivitäts-Messwert-Schlüssel (Tracker) — aus dem FHIR-Katalog abgeleitet.
AKTIVITAET_KEYS: tuple[str, ...] = tuple(a.art for a in fhir.aktivitaet_arten())
# Die drei Tages-RINGE (Apple-Health-Muster): Schritte · aktive Minuten · Stehstunden.
RING_ARTEN: tuple[str, ...] = ("schritte", "aktive_minuten", "stehstunden")
# Ziel-Settings je Ring-Art (Default kommt aus dem Katalog ``ziel``).
ZIEL_SETTING = {"schritte": "ziel_schritte", "aktive_minuten": "ziel_aktive_minuten",
                "stehstunden": "ziel_stehstunden"}

# P2-Korrelation: erlaubte Metriken (Belastung ↔ Erholung) — key: (label, einheit, gruppe).
# Whitelist ⇒ Spaltennamen in _tagesreihe sind injektionsfrei.
KORR_METRIK: dict[str, tuple[str, str, str]] = {
    "aktive_minuten": ("Aktive Minuten", "min", "belastung"),
    "schritte": ("Schritte", "Stk", "belastung"),
    "training_min": ("Trainingsdauer", "min", "belastung"),
    "ruhepuls": ("Ruhepuls", "/min", "erholung"),
    "hrv": ("HRV", "ms", "erholung"),
    "schlaf": ("Schlaf", "h", "erholung"),
}
# P2-Timeline: Farb-Token (Farbschema-folgend) je Domäne.
TIMELINE_FARBE = {"messwert": "cy", "training": "mg", "verletzung": "warn",
                  "termin": "cy", "supplement": "mg", "aktivitaet": "ok"}


# --- Request-Modelle: MODUL-Ebene zwingend (PEP-563-Falle, s. refapp/README) -
class MesswertIn(BaseModel):
    art: str
    wert: float
    einheit: str = ""
    gemessen_am: str = ""
    notiz: str = ""


class SampleIn(BaseModel):
    """Normierte Mess-Probe (Wearable-Ingest, FHIR-Observation-nah). ``extern_id``
    trägt die Idempotenz (Dedupe pro Quelle). Spiegelt ``sources.HealthSample``."""
    art: str
    wert: float
    gemessen_am: str = ""
    einheit: str = ""
    quelle: str = "extern"
    extern_id: str = ""
    geraet: str = ""
    etag: str = ""


class SamplesIngestIn(BaseModel):
    """Stapel normierter Proben — Slot für die Mobile-Brücke (Apple Health/Health
    Connect über die künftige Handy-Schale) bzw. Stapel-Import. Auth-gegatet, lokal."""
    samples: list[SampleIn] = []


class BleLesenIn(BaseModel):
    address: str
    profil: str = "heart_rate"
    dauer: float = 8.0


class SupplementIn(BaseModel):
    name: str
    dosis: str = ""
    einheit: str = ""
    frequenz: str = "taeglich"
    zeitpunkt: str = "egal"
    begonnen_am: str = ""
    notiz: str = ""


class SupplementPatch(BaseModel):
    name: str | None = None
    dosis: str | None = None
    einheit: str | None = None
    frequenz: str | None = None
    zeitpunkt: str | None = None
    aktiv: bool | None = None
    notiz: str | None = None


class VerletzungIn(BaseModel):
    koerperregion: str
    beschreibung: str = ""
    schweregrad: str = "leicht"
    status: str = "akut"
    aufgetreten_am: str = ""
    notiz: str = ""


class VerletzungPatch(BaseModel):
    koerperregion: str | None = None
    beschreibung: str | None = None
    schweregrad: str | None = None
    status: str | None = None
    aufgetreten_am: str | None = None
    notiz: str | None = None


class TrainingIn(BaseModel):
    art: str
    dauer_min: int = 0
    intensitaet: str = "moderat"
    kennzahl_name: str = ""
    kennzahl_wert: float | None = None
    kennzahl_einheit: str = ""
    trainiert_am: str = ""
    notiz: str = ""


class TerminIn(BaseModel):
    titel: str
    beginn: str
    kategorie: str = "arzt"
    ort: str = ""
    notiz: str = ""
    erinnerung: bool = True


class TerminPatch(BaseModel):
    titel: str | None = None
    beginn: str | None = None
    kategorie: str | None = None
    ort: str | None = None
    notiz: str | None = None
    erinnerung: bool | None = None


class AktivitaetIn(BaseModel):
    """Schnell-Eingabe der Tages-Aktivität (Handy-Companion-Ersatz bis Geräte-App
    live). Jeder gesetzte Wert wird als Aktivitäts-Messwert des Tages geschrieben
    (roh) und der Tages-Cache neu berechnet. Übergang: manuell/Schätzung → später
    Pedometer/GPS bzw. HealthConnect/Apple Health über die HealthSource-Adapter."""
    datum: str = ""
    schritte: float | None = None
    distanz: float | None = None
    etagen: float | None = None
    aktive_minuten: float | None = None
    kalorien: float | None = None
    stehstunden: float | None = None
    schlaf: float | None = None
    quelle: str = "manuell"


def heute_iso() -> str:
    return date.today().isoformat()


def _in(wert: str, erlaubt: tuple[str, ...], default: str) -> str:
    return wert if wert in erlaubt else default


def _num(wert: Any) -> float:
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        raise HTTPException(400, "Zahl erwartet.")
    return float(wert)


class Domain:
    """Bündelt Router + Kennzahl-Funktionen der Health-Domäne. main.py reicht
    ``summary``/``stats`` an den Vertrag bzw. den MCP-Server, ``ki_kontext`` an die
    KI (Mini-Dizzi + /api/analyse). ``http_post`` ist der Test-Injektionspunkt für
    die lokale KI (sonst echtes Ollama)."""

    def __init__(self, db: Database, http_post: Any | None = None,
                 archiv_post: Any | None = None,
                 kalender_post: Any | None = None) -> None:
        self.db = db
        self.http_post = http_post
        self.archiv_post = archiv_post     # Querverbindungs-POST (V10 Healthy→Memory)
        self.kalender_post = kalender_post # V13 Healthy→Plans Kalender-POST (injizierbar)
        self.router = self._build_router()

    # --- Kennzahlen (Kachel + /api/stats + MCP) -----------------------------
    def stats(self, user_id: str = "dizzi") -> dict[str, Any]:
        conn = self.db.get_conn()
        heute = heute_iso()
        vor30 = (date.today() - timedelta(days=30)).isoformat()
        vor7 = (date.today() - timedelta(days=7)).isoformat()
        mw_ges = conn.execute(
            "SELECT COUNT(*) AS n FROM messwerte WHERE user_id=? AND deleted_at IS NULL",
            (user_id,)).fetchone()["n"]
        mw_30 = conn.execute(
            "SELECT COUNT(*) AS n FROM messwerte WHERE user_id=? AND deleted_at IS NULL "
            "AND substr(gemessen_am,1,10)>=?", (user_id, vor30)).fetchone()["n"]
        supp = conn.execute(
            "SELECT COUNT(*) AS n FROM supplements WHERE user_id=? AND deleted_at IS NULL "
            "AND aktiv=1", (user_id,)).fetchone()["n"]
        verl = conn.execute(
            "SELECT COUNT(*) AS n FROM verletzungen WHERE user_id=? AND deleted_at IS NULL "
            "AND status!='verheilt'", (user_id,)).fetchone()["n"]
        train7 = conn.execute(
            "SELECT COUNT(*) AS n FROM trainings WHERE user_id=? AND deleted_at IS NULL "
            "AND substr(trainiert_am,1,10)>=?", (user_id, vor7)).fetchone()["n"]
        term_kommend = conn.execute(
            "SELECT COUNT(*) AS n FROM termine WHERE user_id=? AND deleted_at IS NULL "
            "AND substr(beginn,1,10)>=?", (user_id, heute)).fetchone()["n"]
        next_term = conn.execute(
            "SELECT beginn, titel FROM termine WHERE user_id=? AND deleted_at IS NULL "
            "AND substr(beginn,1,10)>=? ORDER BY beginn ASC LIMIT 1",
            (user_id, heute)).fetchone()
        gewicht = conn.execute(
            "SELECT wert, einheit FROM messwerte WHERE user_id=? AND deleted_at IS NULL "
            "AND art='gewicht' ORDER BY gemessen_am DESC LIMIT 1", (user_id,)).fetchone()
        schritte = conn.execute(
            "SELECT wert FROM messwerte WHERE user_id=? AND deleted_at IS NULL "
            "AND art='schritte' AND substr(gemessen_am,1,10)=? ORDER BY gemessen_am DESC "
            "LIMIT 1", (user_id, heute)).fetchone()
        return {
            "messwerte_gesamt": mw_ges, "messwerte_30t": mw_30,
            "supplements_aktiv": supp, "verletzungen_offen": verl,
            "trainings_7t": train7, "termine_kommend": term_kommend,
            "naechster_termin": (next_term["beginn"] if next_term else ""),
            "naechster_termin_titel": (next_term["titel"] if next_term else ""),
            "gewicht_letzt": (gewicht["wert"] if gewicht else None),
            "gewicht_einheit": (gewicht["einheit"] if gewicht else "kg"),
            "schritte_heute": (schritte["wert"] if schritte else None),
        }

    def summary(self, user_id: str = "dizzi") -> list[Kpi]:
        s = self.stats(user_id)
        gewicht_kpi = (f"{s['gewicht_letzt']:g}" if s["gewicht_letzt"] is not None else "—")
        return [
            Kpi(id="gewicht", label="Gewicht", value=gewicht_kpi,
                unit=(s["gewicht_einheit"] if s["gewicht_letzt"] is not None else None)),
            Kpi(id="messwerte_30t", label="Messwerte (30 T)", value=s["messwerte_30t"]),
            Kpi(id="supplements", label="Supplements aktiv", value=s["supplements_aktiv"]),
            Kpi(id="verletzungen", label="Verletzungen offen", value=s["verletzungen_offen"]),
            Kpi(id="termine", label="Nächster Termin",
                value=(s["naechster_termin"][:10] if s["naechster_termin"] else "—")),
        ]

    # --- Trends (deterministisch — die zuverlässige Hälfte der Auswertung) ---
    def trends(self, user_id: str, tage: int = 30) -> list[dict[str, Any]]:
        """Pro Messwert-Art im Zeitfenster: jüngster Wert, Richtung (steigend/
        fallend/stabil), Schnitt, Anzahl, orientierende Referenz-Einordnung des
        jüngsten Werts. Rein deterministisch — kein Modell, keine Diagnose."""
        tage = max(1, min(tage, 3650))
        seit = (datetime.now(timezone.utc) - timedelta(days=tage)).date().isoformat()
        conn = self.db.get_conn()
        out: list[dict[str, Any]] = []
        for art in fhir.MESSWERT_KEYS:
            rows = conn.execute(
                "SELECT wert, einheit, gemessen_am FROM messwerte WHERE user_id=? "
                "AND deleted_at IS NULL AND art=? AND substr(gemessen_am,1,10)>=? "
                "ORDER BY gemessen_am ASC", (user_id, art, seit)).fetchall()
            if not rows:
                continue
            werte = [r["wert"] for r in rows]
            info = fhir.art_info(art)
            letzter = werte[-1]
            mittel = round(sum(werte) / len(werte), 2)
            richtung = self._richtung(werte)
            out.append({
                "art": art, "label": info.label if info else art,
                "einheit": rows[-1]["einheit"] or (info.einheit if info else ""),
                "kategorie": info.kategorie if info else "vital",
                "letzter_wert": round(letzter, 2), "letzter_am": rows[-1]["gemessen_am"],
                "mittel": mittel, "anzahl": len(werte), "richtung": richtung,
                "delta": (round(werte[-1] - werte[0], 2) if len(werte) > 1 else 0),
                "im_referenzbereich": fhir.im_referenzbereich(art, letzter),
                "ref_min": info.ref_min if info else None,
                "ref_max": info.ref_max if info else None,
                "verlauf": [round(w, 2) for w in werte[-30:]],   # Sparkline (älteste→neueste)
            })
        # jüngste Aktivität zuerst
        out.sort(key=lambda t: t["letzter_am"], reverse=True)
        return out

    @staticmethod
    def _richtung(werte: list[float]) -> str:
        """Robuste Richtung: Mittel der älteren vs. neueren Hälfte; kleine
        Unterschiede gelten als stabil (kein Über-Interpretieren bei Rauschen)."""
        n = len(werte)
        if n < 2:
            return "neu"
        h = n // 2
        alt = werte[:h] or werte[:1]
        neu = werte[h:] or werte[-1:]
        m_alt = sum(alt) / len(alt)
        m_neu = sum(neu) / len(neu)
        if m_alt == 0:
            diff = m_neu - m_alt
            eps = 1e-9
        else:
            diff = m_neu - m_alt
            eps = abs(m_alt) * 0.02   # < 2 % Änderung ⇒ stabil
        if diff > eps:
            return "steigend"
        if diff < -eps:
            return "fallend"
        return "stabil"

    def ki_kontext(self, user_id: str, tage: int = 30) -> dict[str, Any]:
        """Kontext für die KI: Trends + aktive Supplements + offene Verletzungen +
        jüngstes Training + nächste Termine. Die KI erfindet nichts dazu."""
        conn = self.db.get_conn()
        supp = [{"name": r["name"], "dosis": r["dosis"], "einheit": r["einheit"],
                 "frequenz": r["frequenz"]}
                for r in conn.execute(
                    "SELECT name, dosis, einheit, frequenz FROM supplements WHERE user_id=? "
                    "AND deleted_at IS NULL AND aktiv=1 ORDER BY name LIMIT 20",
                    (user_id,)).fetchall()]
        verl = [{"koerperregion": r["koerperregion"], "beschreibung": r["beschreibung"],
                 "status": r["status"], "schweregrad": r["schweregrad"]}
                for r in conn.execute(
                    "SELECT koerperregion, beschreibung, status, schweregrad FROM verletzungen "
                    "WHERE user_id=? AND deleted_at IS NULL AND status!='verheilt' "
                    "ORDER BY created_at DESC LIMIT 12", (user_id,)).fetchall()]
        train = [{"art": r["art"], "dauer_min": r["dauer_min"],
                  "intensitaet": r["intensitaet"], "trainiert_am": r["trainiert_am"]}
                 for r in conn.execute(
                     "SELECT art, dauer_min, intensitaet, trainiert_am FROM trainings "
                     "WHERE user_id=? AND deleted_at IS NULL ORDER BY trainiert_am DESC LIMIT 10",
                     (user_id,)).fetchall()]
        term = [{"titel": r["titel"], "beginn": r["beginn"], "kategorie": r["kategorie"]}
                for r in conn.execute(
                    "SELECT titel, beginn, kategorie FROM termine WHERE user_id=? "
                    "AND deleted_at IS NULL AND substr(beginn,1,10)>=? "
                    "ORDER BY beginn ASC LIMIT 10", (user_id, heute_iso())).fetchall()]
        return {"trends": self.trends(user_id, tage), "supplements": supp,
                "verletzungen": verl, "training": train, "termine": term}

    # --- Vorschläge / Erinnerungen (deterministisch, lokal, NIE Diagnose) ----
    def vorschlaege(self, user_id: str = "dizzi") -> dict[str, Any]:
        """SANFTE, regelbasierte Nudges aus der aktuellen Datenlage — rein lokal,
        deterministisch, **keine Diagnose/Medizin**. Jede Art ist per Setting
        abschaltbar (Default an). Speist den Übersicht-Erinnerungs-Strip (in-App;
        kein OS-/Cross-App-Push, da `hoechst`). Die optionale weiche KI-Schicht
        (Mahlzeit/Erholung) liegt in ``ki.vorschlaege`` (eigener Endpunkt, on-demand)."""
        def _an(key: str) -> bool:                       # Toggle, Default an
            v = self.db.setting_get(user_id, key, True)
            return v not in (False, 0, "0", "false", "False", "aus", "nein")
        conn = self.db.get_conn()
        heute = date.today()
        out: list[dict[str, Any]] = []

        if _an("erinnerung_training"):
            row = conn.execute(
                "SELECT trainiert_am FROM trainings WHERE user_id=? AND deleted_at IS NULL "
                "ORDER BY trainiert_am DESC LIMIT 1", (user_id,)).fetchone()
            grenze = int(self.db.setting_get(user_id, "erinnerung_training_tage", 4) or 4)
            letzte = None
            if row is not None:
                try:
                    letzte = date.fromisoformat((row["trainiert_am"] or "")[:10])
                except Exception:
                    letzte = None
            if letzte is None:
                out.append({"typ": "training", "emoji": "🏃", "prio": "info",
                            "text": "Noch kein Training erfasst — magst du eine Einheit eintragen?"})
            else:
                d = (heute - letzte).days
                if d >= grenze:
                    out.append({"typ": "training", "emoji": "🏃", "prio": "warn",
                                "text": f"Vergiss das Training nicht — zuletzt vor {d} Tagen."})

        if _an("erinnerung_termine"):
            vorlauf = int(self.db.setting_get(user_id, "erinnerung_vorlauf_tage", 7) or 7)
            nt = conn.execute(
                "SELECT titel, beginn FROM termine WHERE user_id=? AND deleted_at IS NULL "
                "AND substr(beginn,1,10)>=? ORDER BY beginn ASC LIMIT 1",
                (user_id, heute.isoformat())).fetchone()
            if nt is not None:
                try:
                    tag = date.fromisoformat((nt["beginn"] or "")[:10])
                except Exception:
                    tag = None
                if tag is not None:
                    d = (tag - heute).days
                    if 0 <= d <= max(0, vorlauf):
                        wann = "heute" if d == 0 else ("morgen" if d == 1 else f"in {d} Tagen")
                        out.append({"typ": "termin", "emoji": "🩺", "prio": "info",
                                    "text": f"{nt['titel']} {wann} ({(nt['beginn'] or '')[:10]})."})

        if _an("erinnerung_supplements"):
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM supplements WHERE user_id=? AND deleted_at IS NULL "
                "AND aktiv=1 AND frequenz IN ('taeglich','2x_taeglich')", (user_id,)).fetchone()["n"]
            if n:
                out.append({"typ": "supplement", "emoji": "💊", "prio": "info",
                            "text": f"{n} Supplement(e) für heute eingeplant — schon genommen?"})

        if _an("erinnerung_bewegung"):
            ringe = (self.aktivitaet_tag(user_id) or {}).get("ringe") or []
            erreicht = sum(1 for x in ringe if x.get("erreicht"))
            if datetime.now().hour >= 18 and ringe and erreicht < len(ringe):
                out.append({"typ": "bewegung", "emoji": "🚶", "prio": "info",
                            "text": "Tagesziele noch nicht ganz erreicht — ein kurzer Spaziergang?"})

        if _an("vorschlag_mahlzeit"):
            tr_heute = conn.execute(
                "SELECT COUNT(*) AS n FROM trainings WHERE user_id=? AND deleted_at IS NULL "
                "AND substr(trainiert_am,1,10)=?", (user_id, heute.isoformat())).fetchone()["n"]
            if tr_heute:
                out.append({"typ": "mahlzeit", "emoji": "🍽", "prio": "info",
                            "text": "Nach dem Training an eine eiweißreiche Mahlzeit und genug "
                                    "Flüssigkeit denken."})

        return {"vorschlaege": out, "disclaimer": ki.DISCLAIMER, "quelle": "regel"}

    # --- Wearable-Ingest (BLE + Mobile-Brücke) — normiert, dedupt, lokal -----
    def _ingest_samples(self, user_id: str, samples) -> dict[str, Any]:
        """Schreibt normierte Proben (Objekte mit art/wert/gemessen_am/einheit/quelle/
        extern_id/etag — ``SampleIn`` ODER ``sources.HealthSample``) in ``messwerte``.
        Dedupe über (user, quelle, extern_id) (Index ``idx_messwerte_extern``); unbekannte
        Arten werden übersprungen (ehrlich). Aktivitäts-Arten frischen den Tages-Cache.
        HOCHSENSIBEL: rein lokal — Proben verlassen das Gerät nie."""
        conn = self.db.get_conn()
        geschrieben = uebersprungen = 0
        tage: set[str] = set()
        for s in samples or []:
            art = (getattr(s, "art", "") or "").strip()
            if art not in fhir.ARTEN_BY_KEY:
                uebersprungen += 1
                continue
            quelle = (getattr(s, "quelle", "") or "extern").strip() or "extern"
            extern_id = (getattr(s, "extern_id", "") or "").strip()
            if extern_id:
                vorhanden = conn.execute(
                    "SELECT 1 FROM messwerte WHERE user_id=? AND quelle=? AND extern_id=? "
                    "AND deleted_at IS NULL LIMIT 1", (user_id, quelle, extern_id)).fetchone()
                if vorhanden:
                    uebersprungen += 1
                    continue
            einheit = (getattr(s, "einheit", "") or "").strip() or fhir.default_einheit(art)
            gem = (getattr(s, "gemessen_am", "") or "").strip() or now_iso()
            ts = now_iso()
            conn.execute(
                "INSERT INTO messwerte (id, user_id, art, wert, einheit, gemessen_am, notiz, "
                "quelle, extern_id, etag, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_id(), user_id, art, _num(getattr(s, "wert", 0)), einheit, gem, "",
                 quelle, extern_id, (getattr(s, "etag", "") or ""), ts, ts))
            geschrieben += 1
            if art in AKTIVITAET_KEYS:
                tage.add(gem[:10])
        conn.commit()
        for t in tage:
            self._recompute_aktivitaet_tag(user_id, t)
        return {"geschrieben": geschrieben, "uebersprungen": uebersprungen}

    # --- Serializer ---------------------------------------------------------
    @staticmethod
    def _messwert_public(r) -> dict[str, Any]:
        info = fhir.art_info(r["art"])
        return {"id": r["id"], "art": r["art"],
                "label": info.label if info else r["art"], "wert": r["wert"],
                "einheit": r["einheit"], "gemessen_am": r["gemessen_am"],
                "notiz": r["notiz"], "quelle": r["quelle"],
                "im_referenzbereich": fhir.im_referenzbereich(r["art"], r["wert"]),
                "created_at": r["created_at"]}

    @staticmethod
    def _supplement_public(r) -> dict[str, Any]:
        return {"id": r["id"], "name": r["name"], "dosis": r["dosis"],
                "einheit": r["einheit"], "frequenz": r["frequenz"],
                "zeitpunkt": r["zeitpunkt"], "aktiv": bool(r["aktiv"]),
                "begonnen_am": r["begonnen_am"], "notiz": r["notiz"],
                "created_at": r["created_at"]}

    @staticmethod
    def _verletzung_public(r) -> dict[str, Any]:
        return {"id": r["id"], "koerperregion": r["koerperregion"],
                "beschreibung": r["beschreibung"], "schweregrad": r["schweregrad"],
                "status": r["status"], "aufgetreten_am": r["aufgetreten_am"],
                "notiz": r["notiz"], "created_at": r["created_at"]}

    def _archiviere_verletzung(self, user_id: str, vid: str,
                               explizit: bool = False) -> dict[str, Any]:
        """Reicht eine Verletzung als Notiz an Dizz Memory weiter (Core-Relay,
        V10 docs/26). Health ist `hoechst` ⇒ **immer `sensibel=True`** (Memory-KI
        lokal_only, docs/26 §5). Best-effort (wirft nie). Herkunftslabel „Healthy"
        vergibt Memory zentral. Die HITL-Freigabe ist der bewusste, bestätigte
        Nutzer-Knopf (`explizit`); die formale K4-Aktions-Stufe (verifiziert-Step-up)
        ist ein dokumentierter Folge-Ausbau (Health hat noch keine ActionRegistry)."""
        from appkit.querverbindung import archiviere
        row = self.db.get_conn().execute(
            "SELECT * FROM verletzungen WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (vid, user_id)).fetchone()
        if row is None:
            return {"ok": False, "fehler": "Verletzung unbekannt"}
        kopf = (f"**Körperregion:** {row['koerperregion']} · **Schweregrad:** "
                f"{row['schweregrad']} · **Status:** {row['status']}")
        if (row["aufgetreten_am"] or "").strip():
            kopf += f" · **Aufgetreten:** {row['aufgetreten_am']}"
        zeilen = [kopf]
        if (row["beschreibung"] or "").strip():
            zeilen += ["", row["beschreibung"].strip()]
        if (row["notiz"] or "").strip():
            zeilen += ["", "_Notiz:_ " + row["notiz"].strip()]
        inhalt = "\n".join(zeilen).strip()
        tags = [row["koerperregion"]] if (row["koerperregion"] or "").strip() else []
        return archiviere("health", "Verletzung · " + row["koerperregion"], inhalt,
                          strom="verletzung", ref="health:verletzung:" + vid,
                          quelle="health:verletzung:" + vid, tags=tags,
                          sensibel=True, explizit=explizit, http_post=self.archiv_post)

    def _termin_an_plans(self, user_id: str, termin_id: str,
                         explizit: bool = True) -> dict[str, Any]:
        """V13 Healthy→Plans: reicht die META eines Gesundheits-Termins (Titel, Datum,
        Ort, Kategorie) als Kalender-Termin an Dizz Plans weiter (V5-Vertrag
        ``sende_termin``). **`hoechst`-konform:** es reisen NUR Termin-Meta — KEINE
        Werte/Diagnosen; die ``notiz`` bleibt bewusst in Healthy. Best-effort (wirft
        nie), idempotent über ``ref=health:termin:<id>``."""
        from appkit.querverbindung import sende_termin
        row = self.db.get_conn().execute(
            "SELECT id, titel, kategorie, beginn, ort FROM termine WHERE id=? AND user_id=? "
            "AND deleted_at IS NULL", (termin_id, user_id)).fetchone()
        if row is None:
            return {"ok": False, "fehler": "Termin unbekannt"}
        beginn = (row["beginn"] or "").strip()
        if not beginn:
            return {"ok": False, "fehler": "Termin hat kein Datum."}
        # NUR Meta: Kategorie-Hinweis; die notiz (mögliche Werte/Diagnose) reist NICHT mit.
        beschreibung = "Gesundheits-Termin (Dizz Healthy) · " + (row["kategorie"] or "termin")
        return sende_termin("health", row["titel"], beginn,
                            ort=(row["ort"] or "").strip(), beschreibung=beschreibung,
                            quelle="health:termin:" + termin_id,
                            ref="health:termin:" + termin_id,
                            http_post=self.kalender_post)

    @staticmethod
    def _training_public(r) -> dict[str, Any]:
        return {"id": r["id"], "art": r["art"], "dauer_min": r["dauer_min"],
                "intensitaet": r["intensitaet"], "kennzahl_name": r["kennzahl_name"],
                "kennzahl_wert": r["kennzahl_wert"], "kennzahl_einheit": r["kennzahl_einheit"],
                "trainiert_am": r["trainiert_am"], "notiz": r["notiz"],
                "created_at": r["created_at"]}

    @staticmethod
    def _termin_public(r) -> dict[str, Any]:
        return {"id": r["id"], "titel": r["titel"], "kategorie": r["kategorie"],
                "beginn": r["beginn"], "ort": r["ort"], "notiz": r["notiz"],
                "erinnerung": bool(r["erinnerung"]), "quelle": r["quelle"],
                "created_at": r["created_at"]}

    def _modell(self, user_id: str) -> str:
        return str(self.db.setting_get(user_id, "llm_modell", "qwen3:4b")) or "qwen3:4b"

    # --- Aktivitäts-Tracker (P1d, Hybrid: roh in messwerte + Tages-Cache) ----
    _AKT_FELDER = ("schritte", "distanz", "etagen", "aktive_minuten",
                   "kalorien", "stehstunden", "schlaf")

    def ziele(self, user_id: str) -> dict[str, float]:
        """Tages-Zielwerte der drei Ringe (Setting ⟶ sonst Katalog-Default)."""
        out: dict[str, float] = {}
        for art, key in ZIEL_SETTING.items():
            info = fhir.art_info(art)
            std = float(info.ziel) if (info and info.ziel) else 0.0
            try:
                out[art] = float(self.db.setting_get(user_id, key, std) or std)
            except (TypeError, ValueError):
                out[art] = std
        return out

    def _recompute_aktivitaet_tag(self, user_id: str, datum: str) -> dict[str, Any]:
        """Berechnet den Tages-Aktivitäts-Cache aus den ROHEN Aktivitäts-Messwerten
        des Tages neu (Tageswert = jüngste Messung der Art an dem Tag). Persistiert
        nur, wenn Daten vorhanden sind oder bereits ein Cache-Eintrag besteht."""
        conn = self.db.get_conn()
        vals: dict[str, Any] = {f: None for f in self._AKT_FELDER}
        for art in self._AKT_FELDER:
            row = conn.execute(
                "SELECT wert FROM messwerte WHERE user_id=? AND art=? AND deleted_at IS NULL "
                "AND substr(gemessen_am,1,10)=? ORDER BY gemessen_am DESC LIMIT 1",
                (user_id, art, datum)).fetchone()
            vals[art] = row["wert"] if row else None
        hat_daten = any(v is not None for v in vals.values())
        vorhanden = conn.execute(
            "SELECT id FROM aktivitaet_tag WHERE user_id=? AND datum=?",
            (user_id, datum)).fetchone()
        if hat_daten or vorhanden:
            ts = now_iso()
            conn.execute(
                "INSERT INTO aktivitaet_tag (id, user_id, datum, schritte, distanz, etagen, "
                "aktive_minuten, kalorien, stehstunden, schlaf, quelle, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(user_id, datum) DO UPDATE SET schritte=excluded.schritte, "
                "distanz=excluded.distanz, etagen=excluded.etagen, "
                "aktive_minuten=excluded.aktive_minuten, kalorien=excluded.kalorien, "
                "stehstunden=excluded.stehstunden, schlaf=excluded.schlaf, "
                "updated_at=excluded.updated_at, deleted_at=NULL",
                (new_id(), user_id, datum, vals["schritte"], vals["distanz"], vals["etagen"],
                 vals["aktive_minuten"], vals["kalorien"], vals["stehstunden"], vals["schlaf"],
                 "manuell", ts, ts))
            conn.commit()
        return vals

    def aktivitaet_tag(self, user_id: str, datum: str = "") -> dict[str, Any]:
        """Tages-Aktivität: drei Ringe (Schritte/aktive Minuten/Stehstunden vs. Ziel,
        Apple-Health-Muster) + alle Tageswerte. Stets frisch aus den Roh-Messwerten."""
        datum = (datum or heute_iso())[:10]
        vals = self._recompute_aktivitaet_tag(user_id, datum)
        ziele = self.ziele(user_id)
        ringe = []
        for art in RING_ARTEN:
            info = fhir.art_info(art)
            wert = float(vals.get(art) or 0)
            ziel = float(ziele.get(art) or 0)
            prozent = int(min(100, round(100 * wert / ziel))) if ziel else 0
            ringe.append({"key": art, "label": info.label if info else art,
                          "wert": vals.get(art), "ziel": ziel, "prozent": prozent,
                          "erreicht": bool(ziel and wert >= ziel),
                          "einheit": info.einheit if info else ""})
        return {"datum": datum, "ringe": ringe, "werte": vals}

    def aktivitaet_verlauf(self, user_id: str, art: str, tage: int = 30) -> list[dict[str, Any]]:
        """Tages-Verlauf EINER Aktivitäts-Größe (für Wochen-/Monats-Trendchart).
        ``art`` ist gegen die feste Whitelist geprüft ⇒ Spaltenname injektionsfrei."""
        if art not in self._AKT_FELDER:
            return []
        tage = max(1, min(tage, 3650))
        seit = (date.today() - timedelta(days=tage - 1)).isoformat()
        rows = self.db.get_conn().execute(
            f"SELECT datum, {art} AS wert FROM aktivitaet_tag WHERE user_id=? "
            f"AND deleted_at IS NULL AND datum>=? AND {art} IS NOT NULL ORDER BY datum ASC",
            (user_id, seit)).fetchall()
        return [{"datum": r["datum"], "wert": r["wert"]} for r in rows]

    # --- P2: Unified Timeline (5 Domänen verschmolzen) ----------------------
    def timeline(self, user_id: str, von: str = "", bis: str = "",
                 limit: int = 80) -> list[dict[str, Any]]:
        """Chronologischer Ereignis-Strom über alle Domänen (Vitalwerte · Training ·
        Verletzungen · Termine · Supplements · Tages-Aktivität). Aktivität als EINE
        Tagesbilanz (nicht jeder Rohwert) ⇒ ruhige Timeline. Neueste zuerst."""
        conn = self.db.get_conn()
        ev: list[dict[str, Any]] = []
        aktkeys = set(AKTIVITAET_KEYS)
        for r in conn.execute(
                "SELECT art, wert, einheit, gemessen_am FROM messwerte WHERE user_id=? "
                "AND deleted_at IS NULL ORDER BY gemessen_am DESC LIMIT 400", (user_id,)):
            if r["art"] in aktkeys:
                continue   # Aktivität erscheint als Tagesbilanz (unten), nicht je Rohwert
            info = fhir.art_info(r["art"])
            ev.append({"datum": r["gemessen_am"], "domaene": "messwert",
                       "titel": info.label if info else r["art"],
                       "detail": f'{r["wert"]} {r["einheit"] or ""}'.strip(), "icon": "pulse"})
        for r in conn.execute(
                "SELECT art, dauer_min, intensitaet, trainiert_am FROM trainings WHERE "
                "user_id=? AND deleted_at IS NULL ORDER BY trainiert_am DESC LIMIT 200", (user_id,)):
            ev.append({"datum": r["trainiert_am"], "domaene": "training", "titel": r["art"],
                       "detail": (f'{r["dauer_min"]} min · {r["intensitaet"]}'
                                  if r["dauer_min"] else r["intensitaet"]), "icon": "flame"})
        for r in conn.execute(
                "SELECT koerperregion, schweregrad, status, aufgetreten_am, created_at FROM "
                "verletzungen WHERE user_id=? AND deleted_at IS NULL ORDER BY created_at DESC "
                "LIMIT 120", (user_id,)):
            ev.append({"datum": r["aufgetreten_am"] or r["created_at"], "domaene": "verletzung",
                       "titel": r["koerperregion"],
                       "detail": f'{r["schweregrad"]} · {r["status"]}', "icon": "shield"})
        for r in conn.execute(
                "SELECT titel, kategorie, beginn FROM termine WHERE user_id=? AND deleted_at "
                "IS NULL ORDER BY beginn DESC LIMIT 120", (user_id,)):
            ev.append({"datum": r["beginn"], "domaene": "termin", "titel": r["titel"],
                       "detail": r["kategorie"], "icon": "calendar"})
        for r in conn.execute(
                "SELECT name, dosis, einheit, begonnen_am, created_at FROM supplements WHERE "
                "user_id=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 120", (user_id,)):
            ev.append({"datum": r["begonnen_am"] or r["created_at"], "domaene": "supplement",
                       "titel": r["name"], "detail": f'{r["dosis"]} {r["einheit"]}'.strip() or "begonnen",
                       "icon": "pill"})
        for r in conn.execute(
                "SELECT datum, schritte, aktive_minuten FROM aktivitaet_tag WHERE user_id=? "
                "AND deleted_at IS NULL ORDER BY datum DESC LIMIT 90", (user_id,)):
            teile = []
            if r["schritte"] is not None:
                teile.append(f'{int(r["schritte"])} Schritte')
            if r["aktive_minuten"] is not None:
                teile.append(f'{int(r["aktive_minuten"])} aktive Min')
            if teile:
                ev.append({"datum": r["datum"], "domaene": "aktivitaet", "titel": "Aktivität",
                           "detail": " · ".join(teile), "icon": "steps"})

        def _k(e):
            return e["datum"] or ""
        if von:
            ev = [e for e in ev if _k(e)[:10] >= von]
        if bis:
            ev = [e for e in ev if _k(e)[:10] <= bis]
        ev.sort(key=_k, reverse=True)
        for e in ev:
            e["farbe"] = TIMELINE_FARBE.get(e["domaene"], "cy")
        return ev[:max(1, min(limit, 300))]

    # --- P2: Korrelation Belastung ↔ Erholung (deterministisch) -------------
    def _tagesreihe(self, user_id: str, metrik: str, tage: int) -> dict[str, float]:
        """Tageswert-Reihe EINER Metrik (Datum→Wert). Aktivität aus dem Tages-Cache,
        Training als Tagessumme der Minuten, Vitalwerte als jüngster Tageswert."""
        conn = self.db.get_conn()
        seit = (date.today() - timedelta(days=tage - 1)).isoformat()
        out: dict[str, float] = {}
        if metrik == "training_min":
            for r in conn.execute(
                    "SELECT substr(trainiert_am,1,10) AS d, SUM(dauer_min) AS s FROM trainings "
                    "WHERE user_id=? AND deleted_at IS NULL AND substr(trainiert_am,1,10)>=? "
                    "GROUP BY d", (user_id, seit)):
                out[r["d"]] = float(r["s"] or 0)
        elif metrik in self._AKT_FELDER:
            for r in conn.execute(
                    f"SELECT datum, {metrik} AS w FROM aktivitaet_tag WHERE user_id=? "
                    f"AND deleted_at IS NULL AND datum>=? AND {metrik} IS NOT NULL",
                    (user_id, seit)):
                out[r["datum"]] = float(r["w"])
        elif metrik in fhir.ARTEN_BY_KEY:
            for r in conn.execute(
                    "SELECT substr(gemessen_am,1,10) AS d, wert FROM messwerte WHERE user_id=? "
                    "AND deleted_at IS NULL AND art=? AND substr(gemessen_am,1,10)>=? "
                    "ORDER BY gemessen_am ASC", (user_id, metrik, seit)):
                out[r["d"]] = float(r["wert"])   # ASC ⇒ letzter (jüngster) Tageswert gewinnt
        return out

    @staticmethod
    def _pearson(xs: list[float], ys: list[float]) -> float | None:
        """Pearson-r. <3 Punkte oder keine Streuung ⇒ None (ehrlich statt Scheinwert)."""
        n = len(xs)
        if n < 3:
            return None
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        syy = sum((y - my) ** 2 for y in ys)
        sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        if sxx <= 0 or syy <= 0:
            return None
        return round(sxy / ((sxx * syy) ** 0.5), 3)

    @staticmethod
    def _raenge(werte: list[float]) -> list[float]:
        """Durchschnitts-Ränge (1-basiert) mit Tie-Mittelung (Spearman-Standard):
        gleich große Werte teilen sich den Mittel-Rang ihrer Gruppe."""
        ordnung = sorted(range(len(werte)), key=lambda i: werte[i])
        raenge = [0.0] * len(werte)
        i = 0
        while i < len(ordnung):
            j = i
            while j + 1 < len(ordnung) and werte[ordnung[j + 1]] == werte[ordnung[i]]:
                j += 1
            mittel = (i + j) / 2 + 1          # Mittel-Rang der Bindungsgruppe i..j
            for k in range(i, j + 1):
                raenge[ordnung[k]] = mittel
            i = j + 1
        return raenge

    @staticmethod
    def _spearman(xs: list[float], ys: list[float]) -> float | None:
        """Spearman-Rangkorrelation ρ = Pearson auf den RÄNGEN — misst MONOTONIE
        (nicht nur Linearität) und ist robuster gegen Ausreißer/nicht-lineare
        Zusammenhänge (für Belastung↔Erholung oft aussagekräftiger als Pearson).
        <3 Punkte oder keine Rang-Streuung (alle Werte gleich) ⇒ None."""
        if len(xs) < 3:
            return None
        return Domain._pearson(Domain._raenge(xs), Domain._raenge(ys))

    @staticmethod
    def _plus_tage(datum: str, n: int) -> str:
        y, m, d = (int(t) for t in datum.split("-"))
        return (date(y, m, d) + timedelta(days=n)).isoformat()

    def korrelation(self, user_id: str, x: str, y: str, tage: int = 90,
                    lag: int = 0) -> dict[str, Any]:
        """Streudiagramm-Daten + Pearson-r zweier tagesweise gepaarter Metriken.
        ``lag`` (Tage) verschiebt Y gegen X: lag=1 paart die Belastung von Tag d mit
        der Erholung von Tag d+1 (zeitverzögerter Zusammenhang). STRIKT NICHT-
        MEDIZINISCH: Korrelation ist KEINE Kausalität und KEINE Diagnose."""
        if x not in KORR_METRIK or y not in KORR_METRIK:
            return {"punkte": [], "n": 0, "r": None, "r_spearman": None,
                    "fehler": "unbekannte Metrik"}
        lag = max(0, min(int(lag), 7))
        sx = self._tagesreihe(user_id, x, tage + lag)
        sy = self._tagesreihe(user_id, y, tage + lag)
        punkte = []
        for d in sorted(sx):
            dy = self._plus_tage(d, lag) if lag else d
            if dy in sy:
                punkte.append({"datum": d, "x": round(sx[d], 2), "y": round(sy[dy], 2)})
        xs = [p["x"] for p in punkte]
        ys = [p["y"] for p in punkte]
        r = self._pearson(xs, ys)               # linear (Stärke des linearen Zusammenhangs)
        r_spearman = self._spearman(xs, ys)     # monoton (robuster, P3.3c) — bevorzugt fürs Urteil
        lx, ly = KORR_METRIK[x], KORR_METRIK[y]
        return {"x": x, "y": y, "lag": lag, "x_label": lx[0], "x_einheit": lx[1],
                "y_label": ly[0], "y_einheit": ly[1], "n": len(punkte), "r": r,
                "r_spearman": r_spearman, "punkte": punkte}

    # --- P3: Composite-Scores (Readiness · Fitness-/Bio-Alter) --------------
    # STRIKT NICHT-MEDIZINISCH: transparente Wellness-Heuristiken aus den eigenen
    # Werten — jede Komponente offengelegt, Konfidenz ausgewiesen, KEINE Diagnose
    # und kein klinisches „biologisches Alter". Rein deterministisch (kein Modell).
    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    def _reihe_werte(self, user_id: str, art: str, tage: int) -> list[float]:
        return list(self._tagesreihe(user_id, art, tage).values())

    def _letzter_tageswert(self, user_id: str, art: str, tage: int = 60):
        reihe = self._tagesreihe(user_id, art, tage)
        if not reihe:
            return None
        return reihe[max(reihe)]

    def readiness(self, user_id: str) -> dict[str, Any]:
        """Erholungs-/Bereitschafts-Score (0–100) aus Ruhepuls/HRV/Schlaf/Belastung
        gegen die eigene 30-Tage-Basislinie. Transparent: jede Komponente offengelegt.
        Wellness-Orientierung, KEINE medizinische Aussage."""
        komp: list[dict[str, Any]] = []

        def _vs_basis(art: str, label: str, hoeher_besser: bool, gewicht: float):
            reihe = self._tagesreihe(user_id, art, 30)
            if not reihe:
                return
            werte = list(reihe.values())
            heute = reihe[max(reihe)]
            basis = sum(werte) / len(werte)
            if basis <= 0:
                return
            rel = (heute - basis) / basis
            roh = 50 + (rel if hoeher_besser else -rel) * 250
            komp.append({"key": art, "label": label, "score": int(self._clamp(roh, 0, 100)),
                         "wert": round(heute, 1), "basis": round(basis, 1), "gewicht": gewicht})

        _vs_basis("ruhepuls", "Ruhepuls", hoeher_besser=False, gewicht=0.3)
        _vs_basis("hrv", "HRV", hoeher_besser=True, gewicht=0.3)
        # Schlaf: Nähe zum Ziel (Setting oder 8 h)
        schlaf = self._letzter_tageswert(user_id, "schlaf", 7)
        if schlaf is not None:
            ziel = float(self.db.setting_get(user_id, "x_schlaf_ziel", 8) or 8)
            roh = 100 - abs(schlaf - ziel) / max(ziel, 1) * 120
            komp.append({"key": "schlaf", "label": "Schlaf", "score": int(self._clamp(roh, 0, 100)),
                         "wert": round(schlaf, 1), "basis": ziel, "gewicht": 0.25})
        # Belastung: hohe aktive Minuten der letzten 3 Tage senken die Bereitschaft
        am = self._reihe_werte(user_id, "aktive_minuten", 3)
        if am:
            avg = sum(am) / len(am)
            ziel = float(self.db.setting_get(user_id, "ziel_aktive_minuten", 30) or 30)
            roh = 100 - max(0.0, avg - ziel) / max(ziel, 1) * 60
            komp.append({"key": "belastung", "label": "Belastung (3 T)",
                         "score": int(self._clamp(roh, 0, 100)), "wert": round(avg, 0),
                         "basis": ziel, "gewicht": 0.15})

        if not komp:
            return {"verfuegbar": False, "score": None, "konfidenz": "keine",
                    "komponenten": [], "hinweis": "Noch zu wenige Werte — trag Ruhepuls/"
                    "HRV/Schlaf oder Aktivität ein.", "disclaimer": ki.DISCLAIMER}
        gsum = sum(k["gewicht"] for k in komp)
        score = int(round(sum(k["score"] * k["gewicht"] for k in komp) / gsum))
        stufe = "bereit" if score >= 70 else ("okay" if score >= 45 else "geschont")
        konf = "hoch" if len(komp) >= 3 else ("mittel" if len(komp) == 2 else "niedrig")
        return {"verfuegbar": True, "score": score, "stufe": stufe, "konfidenz": konf,
                "komponenten": komp, "disclaimer": ki.DISCLAIMER}

    def bio_alter(self, user_id: str) -> dict[str, Any]:
        """Fitness-/Bio-Alter-SCHÄTZUNG (Wellness, NICHT klinisch) gegen das
        chronologische Alter: transparente Auf-/Abschläge aus Ruhepuls/Schritten/
        aktiven Minuten. Braucht das Geburtsjahr (Einstellung). Klar nicht-medizinisch."""
        jahr = int(self.db.setting_get(user_id, "geburtsjahr", 0) or 0)
        akt_jahr = date.today().year
        if jahr < 1900 or jahr > akt_jahr:
            return {"verfuegbar": False, "hinweis": "Geburtsjahr in den Einstellungen "
                    "hinterlegen, dann gibt es eine (nicht-medizinische) Schätzung.",
                    "disclaimer": ki.DISCLAIMER}
        chrono = akt_jahr - jahr
        komp: list[dict[str, Any]] = []
        delta = 0.0

        rp = self._letzter_tageswert(user_id, "ruhepuls", 30)
        if rp is not None:
            d = self._clamp((rp - 60) * 0.15, -8, 8)
            delta += d
            komp.append({"key": "ruhepuls", "label": "Ruhepuls", "wert": round(rp, 0),
                         "effekt_jahre": round(d, 1)})
        steps = self._reihe_werte(user_id, "schritte", 30)
        if steps:
            avg = sum(steps) / len(steps)
            d = self._clamp(-(avg - 8000) / 1000 * 0.6, -8, 8)
            delta += d
            komp.append({"key": "schritte", "label": "Schritte (Ø)", "wert": round(avg, 0),
                         "effekt_jahre": round(d, 1)})
        am = self._reihe_werte(user_id, "aktive_minuten", 30)
        if am:
            avg = sum(am) / len(am)
            d = self._clamp(-(avg - 30) / 10 * 0.8, -6, 6)
            delta += d
            komp.append({"key": "aktive_minuten", "label": "Aktive Min (Ø)",
                         "wert": round(avg, 0), "effekt_jahre": round(d, 1)})

        if not komp:
            return {"verfuegbar": False, "chrono_alter": chrono,
                    "hinweis": "Trag Ruhepuls oder Aktivität ein — dann kommt die Schätzung.",
                    "disclaimer": ki.DISCLAIMER}
        bio = self._clamp(chrono + delta, max(15, chrono - 15), chrono + 20)
        konf = "hoch" if len(komp) >= 3 else ("mittel" if len(komp) == 2 else "niedrig")
        return {"verfuegbar": True, "chrono_alter": chrono, "bio_alter": round(bio, 1),
                "differenz": round(bio - chrono, 1), "konfidenz": konf,
                "komponenten": komp, "disclaimer": ki.DISCLAIMER}

    def scores(self, user_id: str) -> dict[str, Any]:
        return {"readiness": self.readiness(user_id), "bio_alter": self.bio_alter(user_id),
                "disclaimer": ki.DISCLAIMER}

    # --- Router -------------------------------------------------------------
    def _build_router(self) -> APIRouter:  # noqa: C901  (viele schlanke CRUD-Endpunkte)
        r = APIRouter()
        db = self.db

        # ===================== STATS / KATALOG / TRENDS / QUELLEN ===========
        @r.get("/api/stats")
        def stats_ep(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            return self.stats(user.user_id)

        @r.get("/api/messwerte/arten")
        def arten() -> dict[str, Any]:
            """Messwert-Katalog (FHIR/LOINC) für UI-Dropdown + Einheiten + Referenz."""
            return {"arten": fhir.katalog_public()}

        @r.get("/api/trends")
        def trends_ep(tage: int = 30,
                      user: UserContext = Depends(current_user)) -> dict[str, Any]:
            return {"tage": tage, "trends": self.trends(user.user_id, tage)}

        @r.get("/api/quellen")
        def quellen(request: Request,
                    user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Vorbereitete Gesundheits-Quellen + Verbindungsstatus (Gesetz 5 sichtbar).
            Liest nur die TRESOR-NAMEN (keine Geheimnisse) zur Verfügbarkeits-Prüfung."""
            from .sources import quellen_status
            vault = getattr(request.app.state, "vault", None)

            def _vault_get(name: str):
                try:
                    return "x" if (vault and name in vault.names()) else None
                except Exception:
                    return None
            return {"quellen": quellen_status(vault_get=_vault_get)}

        # ===================== ANALYSE (KI-Hinweise, lokal) =================
        @r.post("/api/analyse")
        def analyse(tage: int = 30,
                    user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Strukturierte KI-Auswertung: deterministische Trends + SANFTE lokale
            KI-Hinweise (NIE Diagnose, immer Disclaimer). Hochsensibel ⇒ nur lokal."""
            kontext = self.ki_kontext(user.user_id, tage)
            erg = ki.analysiere(kontext, modell=self._modell(user.user_id),
                                http_post=self.http_post)
            db.audit(user.user_id, "ki", "analyse_erstellt",
                     {"hinweise": len(erg.get("hinweise", [])), "quelle": erg.get("quelle")})
            return {"trends": kontext["trends"], "hinweise": erg.get("hinweise", []),
                    "disclaimer": erg.get("disclaimer", ki.DISCLAIMER),
                    "quelle": erg.get("quelle")}

        # ===================== VORSCHLÄGE / ERINNERUNGEN (lokal) ===========
        @r.get("/api/vorschlaege")
        def vorschlaege_ep(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """SANFTE, deterministische Nudges aus der aktuellen Datenlage (Trainings-
            lücke/Supplements/Termine/Bewegung/Mahlzeit) — sofort, ohne Modell, lokal,
            NIE Diagnose. Speist den Übersicht-Erinnerungs-Strip (in-App)."""
            return self.vorschlaege(user.user_id)

        @r.post("/api/vorschlaege/ki")
        def vorschlaege_ki_ep(tage: int = 14,
                              user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Optionale WEICHE lokale KI-Schicht (on-demand, 10–60 s): 1–3 konkrete,
            sanfte Vorschläge (Mahlzeit/Bewegung/Erholung) auf Basis der Datenlage.
            HOCHSENSIBEL ⇒ strikt lokal (Ollama); ohne Ollama ⇒ leer (ehrlich)."""
            kontext = self.ki_kontext(user.user_id, tage)
            erg = ki.vorschlaege(kontext, modell=self._modell(user.user_id),
                                 http_post=self.http_post)
            db.audit(user.user_id, "ki", "vorschlaege_erstellt",
                     {"n": len(erg.get("vorschlaege", [])), "quelle": erg.get("quelle")})
            return {"vorschlaege": erg.get("vorschlaege", []),
                    "disclaimer": erg.get("disclaimer", ki.DISCLAIMER),
                    "quelle": erg.get("quelle")}

        # ===================== WEARABLES: BLE (lokal) + Ingest =============
        @r.get("/api/ble/scan")
        async def ble_scan_ep(timeout: float = 5.0,
                              user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Scannt nahe BLE-Geräte (lokal, 0 Cloud). Ohne installierten Stack ehrlich
            ``verfuegbar:false`` statt Fehler. HOCHSENSIBEL ⇒ alles bleibt auf dem Gerät."""
            from . import sources as _src
            if not _src.ble_stack_verfuegbar():
                return {"verfuegbar": False, "geraete": [],
                        "hinweis": "BLE-Stack nicht installiert — `pip install bleak`."}
            try:
                geraete = await _src.ble_scan(timeout=min(max(timeout, 1.0), 15.0))
            except Exception as e:                       # pragma: no cover - Hardware-Pfad
                raise HTTPException(503, f"BLE-Scan fehlgeschlagen: {e}")
            return {"verfuegbar": True, "geraete": geraete}

        @r.post("/api/ble/lesen")
        async def ble_lesen_ep(body: BleLesenIn,
                               user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Koppelt ein BLE-Gerät, liest die Measurement-Characteristic (v1 scharf:
            Herzfrequenz) und ingestet die Proben LOKAL (Dedupe). Nichts verlässt das Gerät."""
            from . import sources as _src
            if not _src.ble_stack_verfuegbar():
                raise HTTPException(400, "BLE-Stack nicht installiert — `pip install bleak`.")
            if not (body.address or "").strip():
                raise HTTPException(400, "Geräte-Adresse fehlt.")
            try:
                proben = await _src.ble_lesen(body.address.strip(), (body.profil or "heart_rate"),
                                              min(max(body.dauer or 8.0, 1.0), 30.0))
            except _src.QuelleNichtVerbunden as e:
                raise HTTPException(400, str(e))
            except Exception as e:                       # pragma: no cover - Hardware-Pfad
                raise HTTPException(503, f"BLE-Lesen fehlgeschlagen: {e}")
            erg = self._ingest_samples(user.user_id, proben)
            db.audit(user.user_id, "wearable", "ble_gelesen",
                     {"profil": body.profil, "geraet": body.address, **erg})
            return {"ok": True, "profil": body.profil, **erg}

        @r.post("/api/samples/ingest")
        def samples_ingest_ep(body: SamplesIngestIn,
                              user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Stapel-Ingest normierter Proben — Slot für die Mobile-Brücke (Apple Health/
            Health Connect über die künftige Handy-Schale, docs/04) + Stapel-Import. Auth-
            gegatet, dedupt über extern_id, LOKAL. HOCHSENSIBEL: Proben bleiben auf dem Gerät."""
            erg = self._ingest_samples(user.user_id, body.samples)
            db.audit(user.user_id, "wearable", "samples_ingest",
                     {"n_in": len(body.samples), **erg})
            return {"ok": True, **erg}

        # ===================== MESSWERTE ====================================
        @r.post("/api/messwerte")
        def messwert_anlegen(body: MesswertIn,
                             user: UserContext = Depends(current_user)) -> dict[str, Any]:
            art = body.art.strip()
            if art not in fhir.ARTEN_BY_KEY:
                raise HTTPException(400, f"Unbekannte Messwert-Art: {art!r}.")
            wert = _num(body.wert)
            einheit = body.einheit.strip() or fhir.default_einheit(art)
            gemessen = body.gemessen_am.strip() or now_iso()
            ts = now_iso()
            mid = new_id()
            conn = db.get_conn()
            conn.execute(
                "INSERT INTO messwerte (id, user_id, art, wert, einheit, gemessen_am, "
                "notiz, quelle, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'manuell',?,?)",
                (mid, user.user_id, art, wert, einheit, gemessen, body.notiz.strip(), ts, ts))
            conn.commit()
            if art in AKTIVITAET_KEYS:   # Tages-Cache konsistent halten (Hybrid)
                self._recompute_aktivitaet_tag(user.user_id, gemessen[:10])
            db.audit(user.user_id, "user", "messwert_angelegt", {"art": art})
            return {"ok": True, "id": mid}

        @r.get("/api/messwerte")
        def messwert_liste(art: str = "", von: str = "", bis: str = "", limit: int = 200,
                           user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM messwerte WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if art:
                q += " AND art=?"; params.append(art)
            if von:
                q += " AND substr(gemessen_am,1,10)>=?"; params.append(von)
            if bis:
                q += " AND substr(gemessen_am,1,10)<=?"; params.append(bis)
            q += " ORDER BY gemessen_am DESC LIMIT ?"
            params.append(min(max(limit, 1), 1000))
            return [self._messwert_public(row)
                    for row in db.get_conn().execute(q, params).fetchall()]

        @r.get("/api/messwerte/{mid}/fhir")
        def messwert_fhir(mid: str, user: UserContext = Depends(current_user)):
            """Einzelnen Messwert als FHIR-R4-Observation (Interop/Export-Sicht)."""
            row = db.get_conn().execute(
                "SELECT * FROM messwerte WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (mid, user.user_id)).fetchone()
            if row is None:
                return JSONResponse({"error": "Messwert unbekannt"}, status_code=404)
            return fhir.to_fhir_observation(
                row["art"], row["wert"], row["gemessen_am"], einheit=row["einheit"],
                quelle=row["quelle"], extern_id=row["extern_id"])

        @r.delete("/api/messwerte/{mid}")
        def messwert_delete(mid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            row = conn.execute("SELECT art, gemessen_am FROM messwerte WHERE id=? AND user_id=? "
                               "AND deleted_at IS NULL", (mid, user.user_id)).fetchone()
            if row is None:
                return JSONResponse({"error": "Messwert unbekannt"}, status_code=404)
            conn.execute("UPDATE messwerte SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), mid, user.user_id))
            conn.commit()
            if row["art"] in AKTIVITAET_KEYS:   # Tages-Cache konsistent halten (Hybrid)
                self._recompute_aktivitaet_tag(user.user_id, row["gemessen_am"][:10])
            db.audit(user.user_id, "user", "messwert_geloescht", {"id": mid})
            return {"ok": True, "id": mid}

        # ===================== AKTIVITÄT (Tracker, P1d) =====================
        @r.post("/api/aktivitaet")
        def aktivitaet_eintragen(body: AktivitaetIn,
                                 user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Tages-Aktivität schnell erfassen (Handy-Companion-Ersatz). Jeder
            gesetzte Wert wird als ROHER Aktivitäts-Messwert des Tages geschrieben
            (ersetzt einen bestehenden manuellen Tageswert derselben Art ⇒ Tages-
            Total statt Anhäufung); danach wird der Tages-Cache neu berechnet."""
            datum = (body.datum or heute_iso()).strip()[:10]
            gemessen = datum + "T12:00:00"
            conn = db.get_conn()
            ts = now_iso()
            geschrieben: list[str] = []
            felder = {"schritte": body.schritte, "distanz": body.distanz,
                      "etagen": body.etagen, "aktive_minuten": body.aktive_minuten,
                      "kalorien": body.kalorien, "stehstunden": body.stehstunden,
                      "schlaf": body.schlaf}
            for art, roh in felder.items():
                if roh is None:
                    continue
                wert = _num(roh)
                conn.execute(
                    "UPDATE messwerte SET deleted_at=? WHERE user_id=? AND art=? "
                    "AND quelle='manuell' AND deleted_at IS NULL AND substr(gemessen_am,1,10)=?",
                    (ts, user.user_id, art, datum))
                conn.execute(
                    "INSERT INTO messwerte (id, user_id, art, wert, einheit, gemessen_am, "
                    "notiz, quelle, created_at, updated_at) VALUES (?,?,?,?,?,?,'',?,?,?)",
                    (new_id(), user.user_id, art, wert, fhir.default_einheit(art), gemessen,
                     "manuell", ts, ts))
                geschrieben.append(art)
            conn.commit()
            self._recompute_aktivitaet_tag(user.user_id, datum)
            db.audit(user.user_id, "user", "aktivitaet_eingetragen",
                     {"datum": datum, "arten": geschrieben})
            return {"ok": True, "datum": datum, "geschrieben": geschrieben,
                    "tag": self.aktivitaet_tag(user.user_id, datum)}

        @r.get("/api/aktivitaet/tag")
        def aktivitaet_tag_ep(datum: str = "",
                              user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Tages-Aktivität: drei Ziel-Ringe + alle Tageswerte (datum leer = heute)."""
            return self.aktivitaet_tag(user.user_id, datum)

        @r.get("/api/aktivitaet/verlauf")
        def aktivitaet_verlauf_ep(art: str, tage: int = 30,
                                  user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Tages-Verlauf EINER Aktivitäts-Größe (Wochen-/Monats-Trendchart)."""
            return {"art": art, "tage": tage,
                    "punkte": self.aktivitaet_verlauf(user.user_id, art, tage)}

        # ===================== P2: TIMELINE / KORRELATION ===================
        @r.get("/api/timeline")
        def timeline_ep(von: str = "", bis: str = "", limit: int = 80,
                        user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Unified Timeline: Ereignisse aller fünf Domänen, neueste zuerst."""
            return {"events": self.timeline(user.user_id, von, bis, limit)}

        @r.get("/api/korrelation/metriken")
        def korrelation_metriken() -> dict[str, Any]:
            """Wählbare Belastungs-/Erholungs-Metriken fürs Streudiagramm."""
            return {"metriken": [{"key": k, "label": v[0], "einheit": v[1], "gruppe": v[2]}
                                 for k, v in KORR_METRIK.items()]}

        @r.get("/api/korrelation")
        def korrelation_ep(x: str = "aktive_minuten", y: str = "ruhepuls", tage: int = 90,
                           lag: int = 0,
                           user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Streudiagramm Belastung↔Erholung + Korrelation: ``r`` (Pearson, linear)
            UND ``r_spearman`` (Spearman-Rangkorrelation, Monotonie — robuster bei nicht-
            linearen Zusammenhängen, P3.3c). ``lag`` = Y-Verschiebung in Tagen
            (Vortag↔Folgetag). STRIKT NICHT-MEDIZINISCH: Korrelation ≠ Kausalität,
            keine Diagnose (die UI weist das aus)."""
            return self.korrelation(user.user_id, x, y, max(7, min(tage, 365)), lag)

        # ===================== P3: COMPOSITE-SCORES =========================
        @r.get("/api/scores")
        def scores_ep(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Readiness + Fitness-/Bio-Alter — transparente Wellness-Heuristiken mit
            Konfidenz. STRIKT NICHT-MEDIZINISCH, keine Diagnose (die UI weist das aus)."""
            return self.scores(user.user_id)

        # ===================== SUPPLEMENTS ==================================
        @r.post("/api/supplements")
        def supplement_anlegen(body: SupplementIn,
                               user: UserContext = Depends(current_user)) -> dict[str, Any]:
            if not body.name.strip():
                raise HTTPException(400, "Name ist Pflicht.")
            ts = now_iso()
            sid = new_id()
            conn = db.get_conn()
            conn.execute(
                "INSERT INTO supplements (id, user_id, name, dosis, einheit, frequenz, "
                "zeitpunkt, aktiv, begonnen_am, notiz, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,1,?,?,?,?)",
                (sid, user.user_id, body.name.strip(), body.dosis.strip(),
                 body.einheit.strip(), _in(body.frequenz, SUPP_FREQUENZ, "taeglich"),
                 _in(body.zeitpunkt, SUPP_ZEITPUNKT, "egal"),
                 body.begonnen_am.strip(), body.notiz.strip(), ts, ts))
            conn.commit()
            db.audit(user.user_id, "user", "supplement_angelegt", {"name": body.name.strip()})
            return {"ok": True, "id": sid}

        @r.get("/api/supplements")
        def supplement_liste(aktiv: str = "",
                             user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM supplements WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if aktiv in ("0", "1"):
                q += " AND aktiv=?"; params.append(int(aktiv))
            q += " ORDER BY aktiv DESC, name ASC"
            return [self._supplement_public(row)
                    for row in db.get_conn().execute(q, params).fetchall()]

        @r.patch("/api/supplements/{sid}")
        def supplement_patch(sid: str, body: SupplementPatch,
                             user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM supplements WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (sid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Supplement unbekannt"}, status_code=404)
            felder, werte = [], []
            if body.name is not None and body.name.strip():
                felder.append("name=?"); werte.append(body.name.strip())
            if body.dosis is not None:
                felder.append("dosis=?"); werte.append(body.dosis.strip())
            if body.einheit is not None:
                felder.append("einheit=?"); werte.append(body.einheit.strip())
            if body.frequenz is not None:
                felder.append("frequenz=?"); werte.append(_in(body.frequenz, SUPP_FREQUENZ, "taeglich"))
            if body.zeitpunkt is not None:
                felder.append("zeitpunkt=?"); werte.append(_in(body.zeitpunkt, SUPP_ZEITPUNKT, "egal"))
            if body.aktiv is not None:
                felder.append("aktiv=?"); werte.append(int(body.aktiv))
            if body.notiz is not None:
                felder.append("notiz=?"); werte.append(body.notiz.strip())
            if not felder:
                return {"ok": True, "id": sid}
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [sid, user.user_id]
            conn.execute(f"UPDATE supplements SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "supplement_geaendert", {"id": sid})
            return {"ok": True, "id": sid}

        @r.delete("/api/supplements/{sid}")
        def supplement_delete(sid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM supplements WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (sid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Supplement unbekannt"}, status_code=404)
            conn.execute("UPDATE supplements SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), sid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "supplement_geloescht", {"id": sid})
            return {"ok": True, "id": sid}

        # ===================== VERLETZUNGEN =================================
        @r.post("/api/verletzungen")
        def verletzung_anlegen(body: VerletzungIn,
                               user: UserContext = Depends(current_user)) -> dict[str, Any]:
            if not body.koerperregion.strip():
                raise HTTPException(400, "Körperregion ist Pflicht.")
            ts = now_iso()
            vid = new_id()
            conn = db.get_conn()
            conn.execute(
                "INSERT INTO verletzungen (id, user_id, koerperregion, beschreibung, "
                "schweregrad, status, aufgetreten_am, notiz, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (vid, user.user_id, body.koerperregion.strip(), body.beschreibung.strip(),
                 _in(body.schweregrad, VERLETZUNG_SCHWERE, "leicht"),
                 _in(body.status, VERLETZUNG_STATUS, "akut"),
                 body.aufgetreten_am.strip(), body.notiz.strip(), ts, ts))
            conn.commit()
            db.audit(user.user_id, "user", "verletzung_angelegt",
                     {"region": body.koerperregion.strip()})
            return {"ok": True, "id": vid}

        @r.get("/api/verletzungen")
        def verletzung_liste(status: str = "",
                             user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM verletzungen WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if status:
                q += " AND status=?"; params.append(status)
            q += " ORDER BY (status!='verheilt') DESC, created_at DESC"
            return [self._verletzung_public(row)
                    for row in db.get_conn().execute(q, params).fetchall()]

        @r.patch("/api/verletzungen/{vid}")
        def verletzung_patch(vid: str, body: VerletzungPatch,
                             user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM verletzungen WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (vid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Verletzung unbekannt"}, status_code=404)
            felder, werte = [], []
            if body.koerperregion is not None and body.koerperregion.strip():
                felder.append("koerperregion=?"); werte.append(body.koerperregion.strip())
            if body.beschreibung is not None:
                felder.append("beschreibung=?"); werte.append(body.beschreibung.strip())
            if body.schweregrad is not None:
                felder.append("schweregrad=?"); werte.append(_in(body.schweregrad, VERLETZUNG_SCHWERE, "leicht"))
            if body.status is not None:
                felder.append("status=?"); werte.append(_in(body.status, VERLETZUNG_STATUS, "akut"))
            if body.aufgetreten_am is not None:
                felder.append("aufgetreten_am=?"); werte.append(body.aufgetreten_am.strip())
            if body.notiz is not None:
                felder.append("notiz=?"); werte.append(body.notiz.strip())
            if not felder:
                return {"ok": True, "id": vid}
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [vid, user.user_id]
            conn.execute(f"UPDATE verletzungen SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "verletzung_geaendert", {"id": vid})
            return {"ok": True, "id": vid}

        @r.delete("/api/verletzungen/{vid}")
        def verletzung_delete(vid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM verletzungen WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (vid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Verletzung unbekannt"}, status_code=404)
            conn.execute("UPDATE verletzungen SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), vid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "verletzung_geloescht", {"id": vid})
            return {"ok": True, "id": vid}

        @r.post("/api/verletzungen/{vid}/archivieren")
        def verletzung_archivieren_ep(vid: str,
                                      user: UserContext = Depends(current_user)):
            """„In Memory archivieren" (bewusster, bestätigter Nutzer-Zuruf = HITL für
            `hoechst`-Daten): schickt die Verletzung explizit + sensibel an Dizz Memory
            — schlägt jede Archiv-Regel (V10, docs/26)."""
            if db.get_conn().execute(
                    "SELECT id FROM verletzungen WHERE id=? AND user_id=? "
                    "AND deleted_at IS NULL", (vid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Verletzung unbekannt"}, status_code=404)
            ergebnis = self._archiviere_verletzung(user.user_id, vid, explizit=True)
            db.audit(user.user_id, "user", "verletzung_archiviert",
                     {"id": vid, "status": ergebnis.get("status")})
            return ergebnis

        # ===================== TRAINING =====================================
        @r.post("/api/trainings")
        def training_anlegen(body: TrainingIn,
                             user: UserContext = Depends(current_user)) -> dict[str, Any]:
            if not body.art.strip():
                raise HTTPException(400, "Art ist Pflicht.")
            kennzahl_wert = (float(body.kennzahl_wert)
                             if body.kennzahl_wert is not None else None)
            trainiert = body.trainiert_am.strip() or heute_iso()
            ts = now_iso()
            tid = new_id()
            conn = db.get_conn()
            conn.execute(
                "INSERT INTO trainings (id, user_id, art, dauer_min, intensitaet, "
                "kennzahl_name, kennzahl_wert, kennzahl_einheit, trainiert_am, notiz, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, user.user_id, body.art.strip(), max(0, int(body.dauer_min)),
                 _in(body.intensitaet, TRAINING_INTENSITAET, "moderat"),
                 body.kennzahl_name.strip(), kennzahl_wert, body.kennzahl_einheit.strip(),
                 trainiert, body.notiz.strip(), ts, ts))
            conn.commit()
            db.audit(user.user_id, "user", "training_angelegt", {"art": body.art.strip()})
            return {"ok": True, "id": tid}

        @r.get("/api/trainings")
        def training_liste(von: str = "", limit: int = 100,
                           user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM trainings WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if von:
                q += " AND substr(trainiert_am,1,10)>=?"; params.append(von)
            q += " ORDER BY trainiert_am DESC LIMIT ?"
            params.append(min(max(limit, 1), 500))
            return [self._training_public(row)
                    for row in db.get_conn().execute(q, params).fetchall()]

        @r.delete("/api/trainings/{tid}")
        def training_delete(tid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM trainings WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (tid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Training unbekannt"}, status_code=404)
            conn.execute("UPDATE trainings SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), tid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "training_geloescht", {"id": tid})
            return {"ok": True, "id": tid}

        # ===================== TERMINE ======================================
        @r.post("/api/termine")
        def termin_anlegen(body: TerminIn,
                           user: UserContext = Depends(current_user)) -> dict[str, Any]:
            if not body.titel.strip():
                raise HTTPException(400, "Titel ist Pflicht.")
            if not body.beginn.strip():
                raise HTTPException(400, "Beginn ist Pflicht.")
            ts = now_iso()
            tid = new_id()
            conn = db.get_conn()
            conn.execute(
                "INSERT INTO termine (id, user_id, titel, kategorie, beginn, ort, notiz, "
                "erinnerung, quelle, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,'lokal',?,?)",
                (tid, user.user_id, body.titel.strip(),
                 _in(body.kategorie, TERMIN_KATEGORIE, "arzt"), body.beginn.strip(),
                 body.ort.strip(), body.notiz.strip(), int(body.erinnerung), ts, ts))
            conn.commit()
            db.audit(user.user_id, "user", "termin_angelegt", {"kategorie": body.kategorie})
            return {"ok": True, "id": tid}

        @r.get("/api/termine")
        def termin_liste(von: str = "", bis: str = "", kategorie: str = "",
                         kommend: str = "", limit: int = 200,
                         user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM termine WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if kommend in ("1", "true") and not von:
                von = heute_iso()    # bequemer Filter für UI/MCP („kommende Termine")
            if von:
                q += " AND substr(beginn,1,10)>=?"; params.append(von)
            if bis:
                q += " AND substr(beginn,1,10)<=?"; params.append(bis)
            if kategorie:
                q += " AND kategorie=?"; params.append(kategorie)
            q += " ORDER BY beginn ASC LIMIT ?"
            params.append(min(max(limit, 1), 1000))
            return [self._termin_public(row)
                    for row in db.get_conn().execute(q, params).fetchall()]

        @r.patch("/api/termine/{tid}")
        def termin_patch(tid: str, body: TerminPatch,
                         user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM termine WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (tid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Termin unbekannt"}, status_code=404)
            felder, werte = [], []
            if body.titel is not None and body.titel.strip():
                felder.append("titel=?"); werte.append(body.titel.strip())
            if body.beginn is not None and body.beginn.strip():
                felder.append("beginn=?"); werte.append(body.beginn.strip())
            if body.kategorie is not None:
                felder.append("kategorie=?"); werte.append(_in(body.kategorie, TERMIN_KATEGORIE, "arzt"))
            if body.ort is not None:
                felder.append("ort=?"); werte.append(body.ort.strip())
            if body.notiz is not None:
                felder.append("notiz=?"); werte.append(body.notiz.strip())
            if body.erinnerung is not None:
                felder.append("erinnerung=?"); werte.append(int(body.erinnerung))
            if not felder:
                return {"ok": True, "id": tid}
            felder.append("updated_at=?"); werte.append(now_iso())
            werte += [tid, user.user_id]
            conn.execute(f"UPDATE termine SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "termin_geaendert", {"id": tid})
            return {"ok": True, "id": tid}

        @r.delete("/api/termine/{tid}")
        def termin_delete(tid: str, user: UserContext = Depends(current_user)):
            conn = db.get_conn()
            if conn.execute("SELECT id FROM termine WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (tid, user.user_id)).fetchone() is None:
                return JSONResponse({"error": "Termin unbekannt"}, status_code=404)
            conn.execute("UPDATE termine SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), tid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "termin_geloescht", {"id": tid})
            return {"ok": True, "id": tid}

        @r.post("/api/termine/{tid}/an-plans")
        def termin_an_plans(tid: str, user: UserContext = Depends(current_user)):
            """V13 (Nutzer-Zuruf): überträgt die META dieses Termins (Titel/Datum/Ort/
            Kategorie — KEINE Werte) als Kalender-Termin an Dizz Plans (best-effort)."""
            ergebnis = self._termin_an_plans(user.user_id, tid, explizit=True)
            db.audit(user.user_id, "user", "termin_an_plans",
                     {"id": tid, "status": ergebnis.get("status"), "ok": ergebnis.get("ok")})
            return ergebnis

        return r


def build_domain(db: Database, http_post: Any | None = None,
                 archiv_post: Any | None = None,
                 kalender_post: Any | None = None) -> Domain:
    return Domain(db, http_post=http_post, archiv_post=archiv_post,
                  kalender_post=kalender_post)
