"""FHIR-/Messwert-Katalog von Dizz Healthy — das interne Interop-Schema.

Warum FHIR (docs/RECHERCHE §2/§6, Gesetz 5 = Anschlüsse JETZT vorsehen):
Apple Clinical Records und Google Health Connect liefern medizinische Daten als
**HL7 FHIR**. Wer seine Vitalwerte von Anfang an FHIR-nah modelliert, kann später
Wearable-/Klinik-Daten OHNE Schema-Umbau einziehen — der ``HealthSource``-Adapter
normiert dann nur noch auf dieses Modell.

Dieses Modul ist der **kanonische Messwert-Katalog** der App:
- ``MESSWERT_ARTEN`` — jede erfassbare Vital-/Körpergröße mit Anzeigename,
  Standard-Einheit (UCUM), **LOINC-Code** (FHIR-Vokabular) und einem ORIENTIERENDEN
  Referenzbereich. Der Referenzbereich dient NUR der sanften Einordnung in der UI/KI
  (z. B. „außerhalb des üblichen Bereichs") — er ist **keine Diagnose** und
  individuell ärztlich zu bewerten.
- ``to_fhir_observation`` — baut aus einem Messwert eine FHIR-R4-``Observation``
  (vital-signs). v1 nutzt das für Export/Doku; die spätere Wearable-/Klinik-
  Anbindung spricht dasselbe Format (kein Mapping-Wildwuchs).

Die App speichert intern schlank (siehe domain.SCHEMA: art/wert/einheit/…); FHIR ist
die **Austauschsicht**, nicht der Speicher — so bleibt v1 einfach und der Anschluss
trotzdem bereit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MesswertArt:
    """Eine erfassbare Mess-/Körpergröße — Vokabular für UI, Validierung und FHIR.

    ``loinc`` = LOINC-Code (FHIR-``Observation.code``); ``ucum`` = UCUM-Einheit
    (FHIR-``valueQuantity.unit``/``code``). ``ref_min``/``ref_max`` sind ein
    ORIENTIERENDER Erwachsenen-Richtbereich (None = personenabhängig, kein Richtwert)
    — ausdrücklich KEINE Diagnose-Grenze.
    """

    art: str                       # interner Schlüssel (Speicher + API)
    label: str                     # Anzeigename
    einheit: str                   # Standard-Einheit (Anzeige)
    ucum: str                      # UCUM-Code (FHIR valueQuantity.code)
    loinc: str                     # LOINC-Code (FHIR Observation.code; "" = kein etablierter Code)
    loinc_text: str                # LOINC-Anzeigetext
    ref_min: float | None = None   # orientierend (kein Diagnose-Wert)
    ref_max: float | None = None
    kategorie: str = "vital"       # 'vital' (Vitalwerte/Körpermaße) | 'aktivitaet' (Tracker)
    ziel: float | None = None      # Tages-Zielwert (nur 'aktivitaet'; Ring-/Fortschritts-Vorgabe)
    icon: str = "activity"


# Kanonischer Katalog. Reihenfolge = UI-Vorschlagsreihenfolge.
# LOINC/UCUM nach den offiziellen Vital-Signs-Profilen (FHIR R4) gewählt.
MESSWERT_ARTEN: tuple[MesswertArt, ...] = (
    MesswertArt("gewicht", "Gewicht", "kg", "kg", "29463-7", "Body weight",
                icon="weight"),
    MesswertArt("koerperfett", "Körperfett", "%", "%", "41982-0",
                "Percentage of body fat", icon="weight"),
    MesswertArt("blutdruck_sys", "Blutdruck systolisch", "mmHg", "mm[Hg]",
                "8480-6", "Systolic blood pressure", 90, 129, icon="pulse"),
    MesswertArt("blutdruck_dia", "Blutdruck diastolisch", "mmHg", "mm[Hg]",
                "8462-4", "Diastolic blood pressure", 60, 84, icon="pulse"),
    MesswertArt("puls", "Puls", "/min", "/min", "8867-4", "Heart rate",
                50, 100, icon="pulse"),
    MesswertArt("ruhepuls", "Ruhepuls", "/min", "/min", "40443-4",
                "Heart rate --resting", 40, 90, icon="pulse"),
    MesswertArt("hrv", "Herzfrequenzvariabilität", "ms", "ms", "80404-7",
                "R-R interval.standard deviation (Heart rate variability)",
                icon="pulse"),
    MesswertArt("glukose", "Blutzucker", "mg/dL", "mg/dL", "2339-0",
                "Glucose [Mass/volume] in Blood", 70, 140, icon="drop"),
    MesswertArt("spo2", "Sauerstoffsättigung", "%", "%", "59408-5",
                "Oxygen saturation in Arterial blood by Pulse oximetry",
                94, 100, icon="drop"),
    MesswertArt("koerpertemperatur", "Körpertemperatur", "°C", "Cel", "8310-5",
                "Body temperature", 36.1, 37.5, icon="thermo"),
    MesswertArt("atemfrequenz", "Atemfrequenz", "/min", "/min", "9279-1",
                "Respiratory rate", 12, 20, icon="pulse"),
    MesswertArt("schlaf", "Schlafdauer", "h", "h", "93832-4", "Sleep duration",
                7, 9, kategorie="aktivitaet", ziel=8, icon="moon"),
    # ── Aktivitäts-/Tracker-Größen (P1d, Handy-Companion) ─────────────────────
    # Quelle künftig Pedometer/GPS bzw. HealthConnect/Apple Health über die
    # vorbereiteten HealthSource-Adapter (Gesetz 5, sources.py). v1: manuell.
    # Nicht alle haben einen etablierten LOINC-Code (loinc="" ⇒ FHIR ohne Coding,
    # UCUM trägt die Einheit) — bewusst ehrlich statt erfundener Codes.
    MesswertArt("schritte", "Schritte", "Stk", "{steps}", "55423-8",
                "Number of steps in unspecified time Pedometer",
                kategorie="aktivitaet", ziel=8000, icon="steps"),
    MesswertArt("distanz", "Distanz", "km", "km", "", "Distance walked/run",
                kategorie="aktivitaet", icon="route"),
    MesswertArt("etagen", "Etagen", "Etg", "{floors}", "", "Floors climbed",
                kategorie="aktivitaet", icon="stairs"),
    MesswertArt("aktive_minuten", "Aktive Minuten", "min", "min", "",
                "Active/Exercise minutes", kategorie="aktivitaet", ziel=30, icon="flame"),
    MesswertArt("kalorien", "Kalorien (aktiv)", "kcal", "kcal", "41981-2",
                "Calories burned", kategorie="aktivitaet", icon="flame"),
    MesswertArt("stehstunden", "Stehstunden", "h", "h", "", "Stand hours",
                kategorie="aktivitaet", ziel=12, icon="stand"),
)

ARTEN_BY_KEY: dict[str, MesswertArt] = {a.art: a for a in MESSWERT_ARTEN}
MESSWERT_KEYS: tuple[str, ...] = tuple(a.art for a in MESSWERT_ARTEN)


def art_info(art: str) -> MesswertArt | None:
    return ARTEN_BY_KEY.get(art)


def default_einheit(art: str) -> str:
    a = ARTEN_BY_KEY.get(art)
    return a.einheit if a else ""


def im_referenzbereich(art: str, wert: float) -> bool | None:
    """Orientierende Einordnung: True/False im üblichen Bereich, None wenn es für
    diese Art keinen allgemeinen Richtbereich gibt. KEINE Diagnose — nur ein sanfter
    Hinweis für UI/KI."""
    a = ARTEN_BY_KEY.get(art)
    if a is None or (a.ref_min is None and a.ref_max is None):
        return None
    if a.ref_min is not None and wert < a.ref_min:
        return False
    if a.ref_max is not None and wert > a.ref_max:
        return False
    return True


def aktivitaet_arten() -> tuple[MesswertArt, ...]:
    """Nur die Aktivitäts-/Tracker-Größen (kategorie='aktivitaet')."""
    return tuple(a for a in MESSWERT_ARTEN if a.kategorie == "aktivitaet")


def katalog_public() -> list[dict]:
    """Katalog für UI/MCP (Dropdown-Befüllung + Einheiten + Referenz + Kategorie)."""
    return [
        {"art": a.art, "label": a.label, "einheit": a.einheit, "ucum": a.ucum,
         "loinc": a.loinc, "loinc_text": a.loinc_text, "ref_min": a.ref_min,
         "ref_max": a.ref_max, "kategorie": a.kategorie, "ziel": a.ziel, "icon": a.icon}
        for a in MESSWERT_ARTEN
    ]


def to_fhir_observation(art: str, wert: float, gemessen_am: str,
                        einheit: str = "", quelle: str = "manuell",
                        extern_id: str = "", user_ref: str = "Patient/local") -> dict:
    """Baut eine FHIR-R4-``Observation`` (Profil ``vital-signs``) aus einem Messwert.

    Austausch-/Export-Format (kein Speicher): identisch für manuelle Eingabe und
    spätere Wearable-/Klinik-Quellen, damit ``HealthSource``-Adapter nur normieren.
    Unbekannte ``art`` wird tolerant ohne LOINC-Coding ausgegeben (Daten gehen nie
    verloren), bekannte ``art`` trägt das volle LOINC/UCUM-Coding.
    """
    a = ARTEN_BY_KEY.get(art)
    code: dict = {"text": a.label if a else art}
    if a is not None and a.loinc:   # nur mit etabliertem LOINC ein Coding (ehrlich)
        code["coding"] = [{"system": "http://loinc.org", "code": a.loinc,
                           "display": a.loinc_text}]
    quantity: dict = {"value": wert,
                      "unit": einheit or (a.einheit if a else ""),
                      "system": "http://unitsofmeasure.org",
                      "code": (a.ucum if a else (einheit or ""))}
    obs: dict = {
        "resourceType": "Observation",
        "status": "final",
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
            "code": "vital-signs", "display": "Vital Signs"}]}],
        "code": code,
        "subject": {"reference": user_ref},
        "effectiveDateTime": gemessen_am,
        "valueQuantity": quantity,
        "meta": {"source": f"dizz-healthy/{quelle}"},
    }
    if extern_id:
        obs["identifier"] = [{"system": "urn:dizz-healthy:extern_id",
                              "value": extern_id}]
    return obs
