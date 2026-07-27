"""appkit.vision — lokale VLM-Naht „Bild → Text" über Ollama (KA-M7 C3).

Dünn + fail-safe wie ``ollama.strukturiert``: Ollama down / Modell fehlt / Antwort
schema-ungültig ⇒ ``None`` (der Aufrufer degradiert — ``extract._bild_ocr`` fällt
auf pytesseract bzw. ``"keiner"`` zurück). Wirft NIE. Nutzt den ``bilder=``-
Parameter von ``runtime.OllamaRuntime.strukturiert`` (base64 ins ``images``-Feld
von Ollamas ``/api/chat``).

Vision-fähig ist heute NUR Ollama (``qwen2.5vl:7b``, schon gepullt); vLLM/llama.cpp
tragen den ``bilder``-Param bewusst nicht (Adapter-Extension, nicht im ABC-Vertrag).
Der ``modellprofil.py``-``vision``-Slot ist die künftige Quelle (dormant, FP-3:
niemand liest das Modul produktiv) — hier NICHT aktiviert.

Betriebs-Hinweis: das VLM belegt VRAM auf Ollama — großen Bild-Import NICHT parallel
zu laufender Serien-Produktion (:8214) fahren.
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from appkit.runtime import OllamaRuntime

VISION_MODELL = os.environ.get("DIZZ_VISION_MODELL", "qwen2.5vl:7b")   # Muster: creatorapp DIZZ_QA_MODELL
OLLAMA_URL = os.environ.get("DIZZ_OLLAMA_URL", "http://127.0.0.1:11434")


class _Transkription(BaseModel):
    text: str


class _Bildbeschreibung(BaseModel):
    beschreibung: str


def ocr_bild(daten: bytes, *, modell: str = VISION_MODELL, url: str = OLLAMA_URL,
             timeout: float = 120.0, http_post=None) -> str | None:
    """Transkribiert den sichtbaren Text eines Bildes (schema-constrained VLM).
    Rückgabe: der Text — oder ``None`` (Ollama/Modell/Antwort nicht verfügbar bzw.
    kein Text). Wirft NIE."""
    r = OllamaRuntime(url=url).strukturiert(
        "Du bist ein exakter OCR-Transkriptor. Gib NUR den im Bild sichtbaren Text "
        "wortgetreu wieder — keine Deutung, keine Zusätze, keine Anführungszeichen.",
        "Transkribiere den gesamten Text in diesem Bild.",
        schema=_Transkription, modell=modell, timeout=timeout,
        bilder=[daten], http_post=http_post)
    if r is None:
        return None
    text = (r.text or "").strip()
    return text or None


def beschreibe_bild(daten: bytes, *, modell: str = VISION_MODELL, url: str = OLLAMA_URL,
                    timeout: float = 120.0, http_post=None) -> str | None:
    """2–3 Sätze zum Bildinhalt (für Notiz-Inhalt/Alt-Text bei textlosen Bildern).
    Rückgabe: die Beschreibung — oder ``None`` (nicht verfügbar). Wirft NIE."""
    r = OllamaRuntime(url=url).strukturiert(
        "Du beschreibst Bilder knapp, sachlich und auf Deutsch.",
        "Beschreibe den Inhalt dieses Bildes in 2–3 Sätzen.",
        schema=_Bildbeschreibung, modell=modell, timeout=timeout,
        bilder=[daten], http_post=http_post)
    if r is None:
        return None
    b = (r.beschreibung or "").strip()
    return b or None


def verfuegbar(*, url: str = OLLAMA_URL, modell: str = VISION_MODELL,
               timeout: float = 1.5, http_get=None) -> bool:
    """Ist das lokale VLM einsatzbereit? (Ollama erreichbar + Modell vorhanden.)
    Kurzer, gekapselter ``/api/tags``-Ping — jeder Fehler ⇒ ``False`` (nie werfen).
    Für die ``extract.verfuegbarkeit()``-Diagnose; macht KEINEN Bild-Call.
    ``http_get`` ist ein Test-Injektions-Seam (wie ``http_post`` sonst)."""
    try:
        if http_get is not None:
            r = http_get(f"{url}/api/tags")
        else:
            import httpx
            r = httpx.get(f"{url}/api/tags", timeout=timeout)
        if getattr(r, "status_code", 0) != 200:
            return False
        namen = [str(m.get("name", "")) for m in (r.json().get("models") or [])]
        stamm = modell.split(":")[0]
        return any(n == modell or n.split(":")[0] == stamm for n in namen)
    except Exception:
        return False
