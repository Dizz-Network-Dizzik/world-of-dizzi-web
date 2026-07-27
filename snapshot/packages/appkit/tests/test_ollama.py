"""Geteilter strukturierter Ollama-Chat (appkit/ollama.py, docs/50 Schleifen-Nachzug).
Ollama-frei: der Poster ist injiziert."""

from __future__ import annotations

import json

from pydantic import BaseModel

from appkit.ollama import strukturiert


class _Antwort(BaseModel):
    antwort: str
    belege: list[str] = []


def _resp(payload, status=200):
    class _R:
        status_code = status

        def json(self):
            return {"message": {"content": json.dumps(payload)
                                if not isinstance(payload, str) else payload}}
    return _R()


def test_gueltige_antwort_wird_validiert():
    gesehen = {}

    def fake(url, daten):
        gesehen["url"] = url
        gesehen["daten"] = daten
        return _resp({"antwort": "Hallo", "belege": ["A"]})

    res = strukturiert("sys", "frage", modell="qwen3:4b", schema=_Antwort, http_post=fake)
    assert res is not None and res.antwort == "Hallo" and res.belege == ["A"]
    # format = das Schema des Modells (constrained decoding), Endpoint /api/chat
    assert gesehen["url"].endswith("/api/chat")
    assert gesehen["daten"]["format"] == _Antwort.model_json_schema()
    assert gesehen["daten"]["model"] == "qwen3:4b"


def test_http_fehler_und_exception_und_schema_ungueltig():
    # HTTP != 200 ⇒ None
    assert strukturiert("s", "f", modell="m", schema=_Antwort,
                        http_post=lambda u, d: _resp({}, status=500)) is None

    # Poster wirft ⇒ None (fail-safe)
    def boom(u, d):
        raise OSError("ollama weg")
    assert strukturiert("s", "f", modell="m", schema=_Antwort, http_post=boom) is None

    # schema-ungültige Antwort (Pflichtfeld fehlt) ⇒ None
    assert strukturiert("s", "f", modell="m", schema=_Antwort,
                        http_post=lambda u, d: _resp({"falsch": 1})) is None
    # gar kein JSON ⇒ None
    assert strukturiert("s", "f", modell="m", schema=_Antwort,
                        http_post=lambda u, d: _resp("kein json")) is None


def test_temperature_durchgereicht():
    gesehen = {}

    def fake(url, daten):
        gesehen["t"] = daten["options"]["temperature"]
        return _resp({"antwort": "x"})

    strukturiert("s", "f", modell="m", schema=_Antwort, http_post=fake, temperature=0.3)
    assert gesehen["t"] == 0.3


def test_poster_positional_kompatibel_mit_keyword_json_fake():
    """Module, die ihren echten Poster mit ``json=`` füttern, deklarieren im Test
    ``def fake(url, json)`` — der POSITIONALE Helfer-Aufruf bindet ``daten`` korrekt
    an diesen Parameter (kein Bruch beim Migrieren keyword-json-basierter Module)."""
    def fake(url, json):                       # Parametername wie bei admin/memory-Tests
        return _resp({"antwort": json["model"]})
    res = strukturiert("s", "f", modell="qwen3:4b", schema=_Antwort, http_post=fake)
    assert res is not None and res.antwort == "qwen3:4b"
