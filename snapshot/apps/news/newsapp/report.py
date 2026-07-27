"""Sektor-Reports — der News-Skill des Nutzers als App-Funktion (Stufe 2b).

Vorbild ist der persönliche /news-Skill: ein nach SEKTOREN gegliederter
Report aus kuratierten Quellen, **Geopolitik immer enthalten und zuletzt**.
Zwei Betriebsarten (Nutzer-Entscheid 12.06.):
- **Wochen-Automatik**: alle 7 Tage (einstellbar) ein Voll-Report über ALLE
  Sektoren — der Überblicks-Rahmen.
- **Eigene Suche**: Sektoren vorher AUSWÄHLEN; die TIEFE skaliert invers —
  wenige Sektoren ⇒ je Sektor mehr Artikel betrachtet + detaillierterer
  Report; viele/alle Sektoren ⇒ kompakte Overall-News.

Alles lokal via Ollama; die KI arbeitet NUR auf dem Artikel-Bestand der
kuratierten Quellen (nichts erfinden; leerer Sektor wird ehrlich benannt).
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from appkit.ollama import strukturiert

# Sektoren-Katalog (aus dem /news-Skill des Nutzers; geopolitik = fix + zuletzt).
SEKTOREN: list[dict[str, str]] = [
    {"id": "finanzen", "name": "Finanzen & Märkte"},
    {"id": "makro", "name": "Makro & Geldpolitik"},
    {"id": "krypto", "name": "Krypto & Digital Assets"},
    {"id": "quantum", "name": "Quantum Computing"},
    {"id": "prozessoren", "name": "Prozessoren & Halbleiter"},
    {"id": "ki", "name": "Künstliche Intelligenz"},
    {"id": "biotech", "name": "Biotech & Life Science"},
    {"id": "rohstoffe", "name": "Seltene Erden & strategische Rohstoffe"},
    {"id": "energie", "name": "Energie"},
    {"id": "handel", "name": "Zölle, Handel & Lieferketten"},
    {"id": "deutschland", "name": "Deutschland (Gesetzgebung & Innenpolitik)"},
    {"id": "geopolitik", "name": "Geopolitik"},          # IMMER dabei, zuletzt
]
SEKTOR_IDS = [s["id"] for s in SEKTOREN]
PFLICHT_SEKTOR = "geopolitik"

# Welche QUELL-Sektoren einen Report-Sektor speisen (die KI filtert zusätzlich
# thematisch — das Mapping grenzt nur den Artikel-Pool sinnvoll vor).
QUELLEN_MAP: dict[str, list[str]] = {
    "finanzen": ["wirtschaft", "finanzen", "allgemein"],
    "makro": ["wirtschaft", "finanzen", "allgemein"],
    "krypto": ["krypto", "tech"],
    "quantum": ["tech"],
    "prozessoren": ["tech"],
    "ki": ["tech", "ki"],
    "biotech": ["tech", "allgemein"],
    "rohstoffe": ["wirtschaft", "geopolitik", "allgemein"],
    "energie": ["wirtschaft", "allgemein"],
    "handel": ["wirtschaft", "geopolitik", "allgemein"],
    "deutschland": ["allgemein"],
    "geopolitik": ["geopolitik", "allgemein"],
}


# Struktur-ERZWINGUNG (Live-Lehre 12.06.): format="json" garantiert nur
# irgendein JSON — bei großem Input wich qwen3:4b auf {"answer": …} aus.
# Pydantic = EINE Quelle für format= (Grammatik, Ollama ≥0.5) UND Validierung
# (docs/50 P2.1-Nachzug).
class _Punkte(BaseModel):
    punkte: list[str] = []


def tiefe_fuer(anzahl_sektoren: int) -> dict[str, Any]:
    """Die Kern-Mechanik: WENIGER Sektoren ⇒ MEHR Tiefe je Sektor."""
    if anzahl_sektoren <= 3:
        return {"stufe": "tief", "artikel_je_sektor": 25, "punkte": "5 bis 8",
                "stil": ("DETAILLIERT: Hintergrund, Einordnung und Konsequenz "
                         "je Punkt (2-3 Sätze) — AUSSCHLIESSLICH aus den "
                         "Meldungen, keine Zahlen oder Fakten dazuerfinden")}
    if anzahl_sektoren <= 6:
        return {"stufe": "mittel", "artikel_je_sektor": 15, "punkte": "4 bis 6",
                "stil": "PRÄGNANT: je Punkt 1-2 Sätze mit dem Wesentlichen"}
    return {"stufe": "kompakt", "artikel_je_sektor": 8, "punkte": "2 bis 4",
            "stil": "KOMPAKT: nur die Schlagzeilen-Essenz, 1 Satz pro Punkt"}


_SYSTEM = (
    "Du bist die Report-KI von Dizz News. Erstelle den Abschnitt für den "
    "Sektor '{sektor}'. Nutze NUR Meldungen aus der Liste, die thematisch "
    "WIRKLICH zu diesem Sektor gehören. Antworte NUR mit JSON: "
    '{{"punkte":["..."]}} mit {punkte} Stichpunkten, {stil}. '
    'Passt NICHTS aus der Liste zum Sektor: {{"punkte":[]}}. Nichts erfinden.'
)


def _zeilen(artikel: list[dict[str, Any]], limit: int) -> str:
    # Auszug-Länge bewusst großzügig (docs/33 §news): liegt ein extrahierter
    # Volltext vor, liefert er hier deutlich mehr Substanz als die Feed-Summary.
    return "\n".join(
        f"- {a.get('titel', '?')} ({a.get('quelle', '?')}): "
        f"{(a.get('zusammenfassung') or '')[:500]}"
        for a in artikel[:limit])


def normalisiere_sektoren(gewuenscht: list[str] | None) -> list[str]:
    """Leere/None ⇒ ALLE; sonst valide IDs + Pflicht-Sektor, Ordnung wie im
    Katalog (Geopolitik dadurch automatisch zuletzt)."""
    if not gewuenscht:
        return list(SEKTOR_IDS)
    menge = {s for s in gewuenscht if s in SEKTOR_IDS}
    menge.add(PFLICHT_SEKTOR)
    return [s for s in SEKTOR_IDS if s in menge]


def report_erstellen(artikel_holen: Callable[[list[str], int], list[dict[str, Any]]],
                     sektoren: list[str] | None = None,
                     modell: str = "qwen3:4b",
                     http_post: Callable | None = None) -> dict[str, Any]:
    """Erstellt den Report: ein Ollama-Lauf JE Sektor (skalierte Tiefe).
    ``artikel_holen(quell_sektoren, limit)`` liefert den Artikel-Pool.
    Wirft nie; Fehler je Sektor werden ehrlich vermerkt."""
    ausgewaehlt = normalisiere_sektoren(sektoren)
    t = tiefe_fuer(len(ausgewaehlt))
    namen = {s["id"]: s["name"] for s in SEKTOREN}
    abschnitte: list[dict[str, Any]] = []
    for sid in ausgewaehlt:
        pool = artikel_holen(QUELLEN_MAP[sid], t["artikel_je_sektor"])
        if not pool:
            abschnitte.append({"sektor": sid, "name": namen[sid], "punkte": [],
                               "hinweis": "keine Artikel im Bestand"})
            continue
        system = _SYSTEM.format(sektor=namen[sid], punkte=t["punkte"],
                                stil=t["stil"])
        # 120 s, weil ein Voll-Report bis 12 Sektor-Calls macht (Modell-Lade-Puffer).
        roh = strukturiert(system, _zeilen(pool, t["artikel_je_sektor"]),
                           modell=modell, schema=_Punkte, http_post=http_post, timeout=120.0)
        if roh is None:
            abschnitte.append({"sektor": sid, "name": namen[sid], "punkte": [],
                               "hinweis": "KI-Abschnitt fehlgeschlagen"})
            continue
        punkte = [p for p in roh.punkte[:10] if p.strip()]
        eintrag: dict[str, Any] = {"sektor": sid, "name": namen[sid],
                                   "punkte": punkte}
        if not punkte:
            eintrag["hinweis"] = "nichts Relevantes im Bestand"
        abschnitte.append(eintrag)
    return {"tiefe": t["stufe"], "sektoren_gewaehlt": ausgewaehlt,
            "abschnitte": abschnitte, "modell": modell}
