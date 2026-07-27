"""Geteilter strukturierter Ollama-Chat (Single-Source, docs/50 Schleifen-Nachzug).

Nach der Pydantic-Single-Source-Umstellung (P2.1) trugen ~7 App-KI-Module je eine
eigene Kopie desselben Helfer-Paars: ein ``_post`` (httpx → lokales Ollama) + ein
``_chat`` (``format=schema.model_json_schema()`` erzwingt die Grammatik,
``schema.model_validate_json`` validiert, fail-safe → ``None``). Das ist EIN Muster
⇒ EINE Quelle. Eine Änderung am Ollama-Call (Timeout, Retry, $ref-Handling …) wirkt
dann netzweit statt 7×.

**Aufruf-Konvention (wichtig für die Tests):** ``http_post`` wird POSITIONAL als
``http_post(url, daten)`` gerufen — kompatibel mit ALLEN App-Test-Fakes (die ihren
zweiten Parameter ``json``/``daten`` als positional-or-keyword deklarieren), auch den
Modulen, die ihren echten Poster sonst mit ``json=`` füttern.

**fail-safe:** kein Netz / HTTP≠200 / schema-ungültige Antwort ⇒ ``None``; der
Aufrufer degradiert auf seinen bisherigen ehrlichen Fallback. Wirft NIE.

**Single-Source ab M3 (docs/62 §4):** Der Rumpf von ``strukturiert`` lebt jetzt in
``runtime.OllamaRuntime.strukturiert`` (dem LocalRuntime-Adapter) — diese Modul-
Funktion ist nur noch ein *eingefrorener Shim* mit UNVERÄNDERTER Signatur +
positional-``http_post``-Konvention, damit die ~7 App-Importe und ihre Test-Fakes
1:1 weiterlaufen (Paritäts-Beweis: ``test_ollama.py`` unverändert grün). ``post``
bleibt der geteilte Default-Poster (u. a. direkt importiert von ``kommapp/triage``).
"""

from __future__ import annotations

import os
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from appkit.runtime import OllamaRuntime

OLLAMA_URL = os.environ.get("DIZZ_OLLAMA_URL", "http://127.0.0.1:11434")

M = TypeVar("M", bound=BaseModel)


def post(url: str, daten: dict[str, Any], *, timeout: float = 90.0):
    """Default-Poster: synchroner httpx-Call ans lokale Ollama. 90 s, weil der ERSTE
    Lauf das Modell in den VRAM lädt (Live-Lehre Triage); für längere Voll-Läufe
    (News-Report) ``timeout`` hochsetzen."""
    import httpx
    return httpx.post(url, json=daten, timeout=timeout)


def strukturiert(system: str, nutzer: str, *, modell: str, schema: type[M],
                 http_post: Callable | None = None, temperature: float = 0.0,
                 url: str = OLLAMA_URL, timeout: float = 90.0) -> M | None:
    """Struktur-erzwungener Chat gegen Ollama ``/api/chat``: ``format`` = das
    JSON-Schema des Pydantic-Modells (constrained decoding), Validierung über
    DASSELBE Modell. Gibt die validierte ``schema``-Instanz zurück — oder ``None``
    (Ollama weg / HTTP≠200 / Antwort schema-ungültig). Wirft NIE.

    ``http_post(url, daten)`` ist injizierbar (Tests/alternativer Client) und wird
    POSITIONAL gerufen. ``temperature``/``timeout`` je Aufrufer steuerbar.

    Eingefrorener Shim (docs/62 §4 M3): delegiert verhaltensgleich an
    ``runtime.OllamaRuntime.strukturiert`` (Single-Source des Ollama-Calls); wenn
    ``http_post is None``, nutzt der Adapter seinen eigenen httpx-Default — byte-
    gleich zu ``post`` hier. Signatur + positional-Konvention bleiben UNVERÄNDERT."""
    return OllamaRuntime(url=url).strukturiert(
        system, nutzer, schema=schema, modell=modell,
        temperature=temperature, timeout=timeout, http_post=http_post)
