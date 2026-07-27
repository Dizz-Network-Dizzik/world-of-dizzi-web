"""KI-Ebene von Dizz News (Stufe 2, Fragerunde 3) — Briefing + Fragen.

Gleiche Schule wie die Communication-Triage: lokales Ollama (0 €), strikte
Schema-Prüfung der Antwort, ehrlicher Fehler statt Halluzination. Die KI
arbeitet AUSSCHLIESSLICH auf den abgerufenen Artikeln (kuratierte Quellen) —
sie erfindet keine Nachrichten dazu; gibt der Bestand nichts her, sagt sie das.

Schema-Quelle = Pydantic-Modelle (docs/50 P2.1): ``Model.model_json_schema()``
erzeugt das Ollama-``format`` (constrained decoding), ``Model.model_validate_json``
prüft die Antwort — EINE Quelle für Struktur UND Validierung (kein Doppel-Schema).
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from appkit.ollama import strukturiert

_BRIEFING_SYSTEM = (
    "Du bist die Nachrichten-KI von Dizz News. Erstelle aus der Artikel-Liste "
    'ein kompaktes Briefing. Antworte NUR mit JSON: {{"ueberblick":"3-4 '
    'Saetze ueber die Lage","wichtig":[{{"titel":"...","warum":"..."}}]}}. '
    '"wichtig" = maximal {max_wichtig} Artikel mit echter Tragweite. '
    "Nichts erfinden: nur aus der Liste."
)

# Ohne .format-Platzhalter ⇒ normale Klammern (die {{}}-Falle gilt nur für
# Templates, die durch str.format laufen — Lehre aus musikapp/llm.py).
_FRAGE_SYSTEM = (
    "Du bist die Nachrichten-KI von Dizz News. Beantworte die Frage NUR aus "
    'der Artikel-Liste. Antworte NUR mit JSON: {"antwort":"...","belege":'
    '["Titel der genutzten Artikel"]}. Gibt die Liste nichts zur Frage her: '
    'sage das ehrlich in "antwort" und lasse "belege" leer. Nichts erfinden.'
)

# RÜCK-LESE-Variante (appkit 1.12, docs/26 §10.1): zusätzlich zum aktuellen
# Artikel-Bestand liegen FRÜHERE Berichte aus dem zentralen Archiv vor. Sie
# dürfen als Hintergrund/Einordnung dienen, sind aber nachrangig — Fakten
# kommen primär aus den AKTUELLEN Artikeln; weiterhin nichts erfinden.
_FRAGE_SYSTEM_ARCHIV = (
    "Du bist die Nachrichten-KI von Dizz News. Beantworte die Frage primär aus "
    "der AKTUELLEN Artikel-Liste; die FRÜHEREN BERICHTE (Archiv) darfst du als "
    'ergänzenden Hintergrund nutzen. Antworte NUR mit JSON: {"antwort":"...",'
    '"belege":["Titel der genutzten Artikel/Berichte"]}. Gibt beides nichts zur '
    'Frage her: sage das ehrlich in "antwort", "belege" leer. Nichts erfinden.'
)

_KURZ_SYSTEM = (
    "Du fasst eine Nachricht in 1-2 sachlichen deutschen Sätzen zusammen — knapp, "
    'ohne Floskeln. Antworte NUR mit JSON: {"kurz":"..."}. Nichts erfinden, nur aus '
    "dem gegebenen Text."
)


# --- Antwort-Schemas (Single-Source: format= UND Validierung, P2.1) -----------
class BriefingItem(BaseModel):
    titel: str
    warum: str = ""


class Briefing(BaseModel):
    ueberblick: str
    wichtig: list[BriefingItem] = []


class Frage(BaseModel):
    antwort: str
    belege: list[str] = []


class Kurz(BaseModel):
    kurz: str


def _zeilen(artikel: list[dict[str, Any]], limit: int = 40) -> str:
    # Auszug großzügiger (docs/33 §news): extrahierter Volltext liefert mehr
    # Substanz als die kurze Feed-Summary ⇒ bessere Briefings/Antworten.
    out = []
    for a in artikel[:limit]:
        out.append(f"- [{a.get('sektor', '?')}] {a.get('titel', '(ohne Titel)')} "
                   f"({a.get('quelle', '?')}): "
                   f"{(a.get('zusammenfassung') or '')[:400]}")
    return "\n".join(out)


def kurzfassung(titel: str, text: str, modell: str = "qwen3:4b",
                http_post: Callable | None = None) -> str | None:
    """Stylische 1-2-Satz-Kurzfassung für eine Watchlist-Karte (Phase 3, lokal,
    JSON-Schema-Grammatik). Wirft nie; ``None`` ⇒ der Aufrufer nimmt die Feed-Summary
    als Fallback (Ollama nicht erreichbar / leerer Text / unbrauchbare Antwort)."""
    quelle = (text or "").strip()
    if not quelle:
        return None
    res = strukturiert(_KURZ_SYSTEM, f"TITEL: {titel}\n\nTEXT:\n{quelle[:1500]}",
                       modell=modell, schema=Kurz, http_post=http_post)
    if res is None:
        return None
    return res.kurz.strip() or None


def briefing(artikel: list[dict[str, Any]], modell: str = "qwen3:4b",
             max_wichtig: int = 5, http_post: Callable | None = None) -> dict[str, Any]:
    """Kompakt-Briefing über die neuesten Artikel. Wirft nie."""
    if not artikel:
        return {"ueberblick": "Noch keine Artikel — erst Quellen abrufen.",
                "wichtig": []}
    res = strukturiert(_BRIEFING_SYSTEM.format(max_wichtig=max_wichtig),
                       _zeilen(artikel), modell=modell, schema=Briefing, http_post=http_post)
    if res is None:
        return {"error": "Briefing fehlgeschlagen (Ollama nicht erreichbar "
                         "oder Antwort unbrauchbar)"}
    wichtig = [{"titel": w.titel, "warum": w.warum} for w in res.wichtig[:max_wichtig]]
    return {"ueberblick": res.ueberblick.strip(), "wichtig": wichtig,
            "modell": modell, "artikel_betrachtet": min(len(artikel), 40)}


def frage(artikel: list[dict[str, Any]], frage_text: str,
          modell: str = "qwen3:4b",
          http_post: Callable | None = None,
          archiv_kontext: str = "") -> dict[str, Any]:
    """Beantwortet eine Frage aus dem Artikel-Bestand. Wirft nie.

    ``archiv_kontext`` (optional, RÜCK-LESE): frühere im zentralen Archiv
    abgelegte News-Berichte als ergänzender Hintergrund (docs/26 §10.1). Leer ⇒
    Verhalten unverändert (NUR aktuelle Artikel)."""
    if not artikel:
        return {"antwort": "Noch keine Artikel im Bestand — erst Quellen abrufen.",
                "belege": []}
    kontext = (archiv_kontext or "").strip()
    system = _FRAGE_SYSTEM_ARCHIV if kontext else _FRAGE_SYSTEM
    nutzer = f"FRAGE: {frage_text}\n\nARTIKEL:\n{_zeilen(artikel)}"
    if kontext:
        nutzer += "\n\nFRÜHERE BERICHTE (Archiv, nur Hintergrund):\n" + kontext
    res = strukturiert(system, nutzer, modell=modell, schema=Frage, http_post=http_post)
    if res is None:
        return {"error": "Antwort fehlgeschlagen (Ollama nicht erreichbar "
                         "oder Antwort unbrauchbar)"}
    return {"antwort": res.antwort.strip(), "belege": res.belege[:10],
            "modell": modell, "artikel_betrachtet": min(len(artikel), 40)}
