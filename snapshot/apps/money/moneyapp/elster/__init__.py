"""ELSTER/ERiC-Filing-Transport (M-1, docs/65) — die Steuererklärung RAUS ans Finanzamt.

Stufe 0 = Verträge-als-Code: Typen, Zustandsmaschine, Fehler-Taxonomie, das
Fail-closed-Gate zur M-2-Plausibilisierung und die ERiC-Adapter-Grenze
(normativ: ``vertrag.py`` + docs/65). Die echte ERiC-Bindung, Feld-Mappings
und jede Übermittlung baut Bau-KI nach docs/65 §12 (M1-1…M1-8) — dieses Paket
lädt KEINE native Lib, kennt KEINE Geheimnisse und sendet NIE.
"""

from .vertrag import (
    BLOCKIERENDE_ZUSTAENDE,
    DatensatzBauer,
    DoppelFilingFehler,
    ElsterDatensatz,
    ElsterFehler,
    ElsterZugang,
    EricTransport,
    EuerBauer,
    FestschreibFehler,
    FilingErgebnis,
    FilingZustand,
    FormularArt,
    GateRot,
    KonfigFehler,
    NichtScharf,
    PlausiFreigabe,
    Quittung,
    Scharfschaltung,
    SendeUnklarFehler,
    SteuerFall,
    UebermittlungAbgelehnt,
    UstvaBauer,
    ValidierungsErgebnis,
    ValidierungsFehler,
    VerbindungsFehler,
    ZertifikatFehler,
    ZertifikatTyp,
    ZustandsFehler,
    berechne_quell_stand,
    fall_schluessel,
    ist_terminal,
    pruefe_doppel,
    pruefe_gate,
    pruefe_hersteller_id,
    pruefe_scharf,
    pruefe_sende_freigabe,
    pruefe_uebergang,
)

__all__ = [
    "BLOCKIERENDE_ZUSTAENDE", "DatensatzBauer", "DoppelFilingFehler",
    "ElsterDatensatz", "ElsterFehler", "ElsterZugang", "EricTransport",
    "EuerBauer", "FestschreibFehler", "FilingErgebnis", "FilingZustand",
    "FormularArt", "GateRot", "KonfigFehler", "NichtScharf", "PlausiFreigabe",
    "Quittung", "Scharfschaltung", "SendeUnklarFehler", "SteuerFall",
    "UebermittlungAbgelehnt", "UstvaBauer", "ValidierungsErgebnis",
    "ValidierungsFehler", "VerbindungsFehler", "ZertifikatFehler",
    "ZertifikatTyp", "ZustandsFehler", "berechne_quell_stand",
    "fall_schluessel", "ist_terminal", "pruefe_doppel", "pruefe_gate",
    "pruefe_hersteller_id", "pruefe_scharf", "pruefe_sende_freigabe",
    "pruefe_uebergang",
]
