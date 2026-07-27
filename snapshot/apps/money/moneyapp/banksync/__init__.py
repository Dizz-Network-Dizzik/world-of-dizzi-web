"""Bank-Sync (M-6, docs/64) — nur-lesender FinTS/HBCI-Abruf als Quelle VOR den importers.

Stufe 0 = Verträge-als-Code: Typen, Zustandsmaschine, Fehler-Taxonomie und die
Quelle→Import-Brücke (normativ: ``vertrag.py`` + docs/64). Die echte FinTS-Wire-
Implementierung baut Bau-KI nach docs/64 §12 (M6-1…M6-7) — dieses Paket öffnet
KEINE Verbindung und kennt KEINE Geheimnisse.
"""

from .vertrag import (
    AuszugsFormat,
    AuthFehler,
    BankSyncFehler,
    BankZugang,
    DateiQuelle,
    FinTSQuelle,
    FormatFehler,
    KonfigFehler,
    NichtScharf,
    RohAuszug,
    Scharfschaltung,
    SyncErgebnis,
    SyncStand,
    SyncZustand,
    TanAnfrage,
    TanFehler,
    TanVerfahren,
    TeilAbrufFehler,
    UmsatzQuelle,
    VerbindungsFehler,
    ZustandsFehler,
    abruf_fenster,
    als_import_auftrag,
    ist_terminal,
    pruefe_scharf,
    pruefe_uebergang,
    segment_erlaubt,
)

__all__ = [
    "AuszugsFormat", "AuthFehler", "BankSyncFehler", "BankZugang", "DateiQuelle",
    "FinTSQuelle", "FormatFehler", "KonfigFehler", "NichtScharf", "RohAuszug",
    "Scharfschaltung", "SyncErgebnis", "SyncStand", "SyncZustand", "TanAnfrage",
    "TanFehler", "TanVerfahren", "TeilAbrufFehler", "UmsatzQuelle",
    "VerbindungsFehler", "ZustandsFehler", "abruf_fenster", "als_import_auftrag",
    "ist_terminal", "pruefe_scharf", "pruefe_uebergang", "segment_erlaubt",
]
