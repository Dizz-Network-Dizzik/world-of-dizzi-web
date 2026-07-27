"""Lokale Verwaltungs-KI von Dizz Admin (Mini-Dizzi-Schicht) — beantwortet Fragen
NUR aus dem gegebenen Modul-Kontext, schlägt nie eigenmächtig vor (HITL). Strikt lokal
(``sensitivity='hoch'`` ⇒ kein Cloud-/Boost-Modell). Ollama-``format`` = JSON-
SCHEMA (Netzwerk-Lehre: nur „json" ist zu unzuverlässig).

Schema-Quelle = Pydantic-Modell (docs/50 P2.1): ``_Antwort.model_json_schema()``
erzeugt das Ollama-``format`` (constrained decoding), ``model_validate_json`` prüft
die Antwort — EINE Quelle für Struktur UND Validierung (kein dict-Schema + Hand-Cast).
"""

from __future__ import annotations

import os

from typing import Any

from pydantic import BaseModel

# Konfigurierbar (CH-1, 28.06.): Ollama-Host via Env überschreibbar (Konsistenz mit
# tresor_ki/comm-triage/creating), statt hart verdrahtetem localhost.
OLLAMA_URL = os.environ.get("DIZZ_OLLAMA_URL", "http://127.0.0.1:11434")


class _Antwort(BaseModel):
    antwort: str


def frage(kontext: str, frage_text: str, *, modell: str = "qwen3:4b",
          http_post: Any | None = None) -> dict[str, Any]:
    """Antwortet aus dem Geschäfts-Kontext. Wirft nie — bei Fehler leere Antwort."""
    import httpx
    poster = http_post or (lambda url, json: httpx.post(url, json=json, timeout=60.0))
    prompt = (
        "Du bist die Verwaltungs-KI von Dizz Admin (Bereiche · Tresor · Projekte · "
        "Geschäft · Studium · Fristen). Antworte knapp, sachlich und auf Deutsch, "
        "AUSSCHLIESSLICH aus dem gegebenen Kontext. "
        "Erfinde keine Zahlen; schlage nichts eigenmächtig vor.\n\n"
        f"KONTEXT:\n{kontext}\n\nFRAGE: {frage_text}")
    try:
        r = poster(f"{OLLAMA_URL}/api/chat", json={
            "model": modell, "stream": False, "format": _Antwort.model_json_schema(),
            "messages": [{"role": "user", "content": prompt}]})
        res = _Antwort.model_validate_json(r.json()["message"]["content"])
        return {"antwort": res.antwort.strip()}
    except Exception as e:  # noqa: BLE001 — KI ist best-effort
        return {"antwort": "", "error": str(e)}
