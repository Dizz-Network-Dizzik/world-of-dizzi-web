"""KI-Ebene von Dizz Admin (App-KI-Slot für Mini-Dizzi, Vertrag 1.5).

Gleiche Schule wie Dizz News: lokales Ollama (0 €), striktes JSON-Schema als
Grammatik (gegen Format-Abdriften bei großem Input), ehrlicher Fehler statt
Halluzination. Die KI arbeitet AUSSCHLIESSLICH auf dem App-Kontext (letzte
Dokument-Titel + offene Aufgaben) — sie erfindet keine Vorgänge dazu.

Sensible Inhalte bleiben lokal (Manifest-Routing); ``main.py`` registriert
``frage`` über ``mini_dizzi.set_app_ki``. Liefert die KI nichts Brauchbares,
gibt sie ``{"antwort": ""}`` zurück ⇒ Mini-Dizzi fällt sauber auf seinen
generischen Ollama-Kontext zurück (kein erfundener Inhalt).
"""

from __future__ import annotations

import os
from typing import Any, Callable

from pydantic import BaseModel

OLLAMA_URL = os.environ.get("DIZZ_OLLAMA_URL", "http://127.0.0.1:11434")

_SYSTEM = (
    "Du bist die Büro-KI von Dizz Admin (Verwaltung von Dokumenten, Fristen und "
    "Aufgaben). Beantworte die Frage NUR aus dem gegebenen Kontext (Dokument-Titel, "
    "offene Aufgaben und ggf. Treffer aus dem zentralen Dizz-Memory-Archiv). "
    "Antworte knapp und auf Deutsch, NUR als JSON: "
    '{"antwort":"..."}. Gibt der Kontext nichts zur Frage her, sage das ehrlich. '
    "Nichts erfinden."
)


# Antwort-Schemas = EINE Quelle für format= (Grammatik) UND Validierung (docs/50
# P2.1-Nachzug). Pflichtfelder bilden die bisherigen `required`-Listen 1:1 ab.
class _Antwort(BaseModel):
    antwort: str


def _post(url: str, daten: dict[str, Any]):
    import httpx
    # 90 s: der erste Lauf lädt das Modell in den VRAM (Live-Lehre Triage).
    return httpx.post(url, json=daten, timeout=90.0)


def _kontext_text(kontext: dict[str, Any]) -> str:
    dok = kontext.get("dokumente") or []
    auf = kontext.get("aufgaben") or []
    mem = kontext.get("memory") or []           # Rück-Lese-Treffer (v3, optional)
    zeilen = ["DOKUMENTE (zuletzt abgelegt):"]
    zeilen += [f"- {t}" for t in dok[:10]] or ["- (keine)"]
    zeilen.append("OFFENE AUFGABEN:")
    if auf:
        for a in auf[:20]:
            faellig = a.get("faellig") or "ohne Frist"
            zeilen.append(f"- [{a.get('prioritaet', '?')}] {a.get('titel', '?')} "
                          f"(fällig: {faellig}, Status: {a.get('status', '?')})")
    else:
        zeilen.append("- (keine)")
    if mem:                                     # zentrales Dizz-Memory-Archiv (Querverbindung)
        zeilen.append("MEMORY-ARCHIV (zentrale Treffer zur Frage):")
        for t in mem[:6]:
            titel = t.get("titel") or t.get("name") or "?"
            auszug = (t.get("auszug") or t.get("vorschau") or "").strip().replace("\n", " ")
            zeilen.append(f"- {titel}: {auszug[:200]}")
    return "\n".join(zeilen)


_KLASSIFY_SYSTEM = (
    "Du klassifizierst ein Büro-Dokument aus Titel + Textauszug. Bestimme den "
    "Typ (GENAU einer aus: Rechnung, Vertrag, Steuer, Sonstiges), den "
    "Korrespondenten (Absender/Firma/Behörde, kurz) und 2–5 prägnante Tags. "
    'Antworte NUR als JSON: {"typ":"...","korrespondent":"...","tags":["..."]}. '
    "Nichts erfinden — bei Unsicherheit Typ=Sonstiges und korrespondent leer."
)
class _Klassifikation(BaseModel):
    typ: str
    korrespondent: str
    tags: list[str]


def klassifiziere(titel: str, volltext: str, modell: str = "qwen3:4b",
                  http_post: Callable | None = None) -> dict[str, Any]:
    """P2: KI-Vorschlag Typ/Korrespondent/Tags aus Titel+Volltext (lokales Ollama).
    Wirft nie; ``{}`` ⇒ der Aufrufer nutzt seinen heuristischen Fallback."""
    text = f"{titel or ''}\n{volltext or ''}".strip()
    if not text:
        return {}
    try:
        r = (http_post or _post)(f"{OLLAMA_URL}/api/chat", {
            "model": modell, "stream": False, "format": _Klassifikation.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": _KLASSIFY_SYSTEM},
                         {"role": "user", "content": text[:4000]}]})
        if getattr(r, "status_code", 0) != 200:
            return {}
        res = _Klassifikation.model_validate_json((r.json().get("message") or {}).get("content", ""))
    except Exception:
        return {}
    tags = [t.strip() for t in res.tags if t.strip()][:6]
    return {"typ": res.typ.strip(), "korrespondent": res.korrespondent.strip(), "tags": tags}


def frage(kontext: dict[str, Any], frage_text: str, modell: str = "qwen3:4b",
          http_post: Callable | None = None) -> dict[str, Any]:
    """Beantwortet eine Frage NUR aus dem Büro-Kontext. Wirft nie.
    ``{"antwort": ""}`` ⇒ Mini-Dizzi nutzt seinen generischen Fallback."""
    frage_text = (frage_text or "").strip()
    if not frage_text:
        return {"antwort": ""}
    try:
        r = (http_post or _post)(f"{OLLAMA_URL}/api/chat", {
            "model": modell, "stream": False, "format": _Antwort.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user",
                 "content": f"FRAGE: {frage_text}\n\nKONTEXT:\n{_kontext_text(kontext)}"}]})
        if getattr(r, "status_code", 0) != 200:
            return {"antwort": ""}
        res = _Antwort.model_validate_json((r.json().get("message") or {}).get("content", ""))
    except Exception:
        return {"antwort": ""}
    return {"antwort": res.antwort.strip()}
