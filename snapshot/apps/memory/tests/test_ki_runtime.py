"""docs/62 runtime-Konsistenz: der Vault-Chat (``ki.antwort``) spricht Ollama NICHT
mehr direkt via httpx, sondern über die austauschbare LocalRuntime
(``OllamaRuntime.strukturiert``). Diese Tests beweisen — Ollama-frei —:

1. das ROUTING geht über OllamaRuntime.strukturiert (nicht mehr roher httpx-Call),
2. der Gesprächs-``verlauf`` (P3.1) wird als Chat-Messages zwischen System- und
   User-Turn durchgereicht (Constrained decoding ``format`` + ``stream:False`` bleiben),
3. die Fehler-GRANULARITÄT ist 0-verhaltensgleich zum früheren Direkt-Call
   (HTTP≠200 ⇒ error "ollama"; Transportfehler ⇒ error = Exception-Typname),
4. die Kurzschluss-Pfade (leere Frage / keine Notizen) sind unverändert.

Ergänzt die Bestands-Suite ``test_chat.py`` (die über die ``http_post``-Naht
unverändert grün bleibt = der eigentliche Paritäts-Beweis)."""

from __future__ import annotations

import json

from archivapp import ki

NOTIZEN = [{"titel": "N", "inhalt": "Inhalt der Notiz."}]


class _Resp:
    """Ollama-``/api/chat``-Antwort-Fake (message.content = JSON-Dump), wie test_chat."""
    status_code = 200

    def __init__(self, antwort: str):
        self._a = antwort

    def json(self):
        return {"message": {"content": json.dumps({"antwort": self._a})}}


def test_antwort_laeuft_ueber_ollama_runtime_strukturiert(monkeypatch):
    """Routing-Beweis: ki.antwort ruft OllamaRuntime.strukturiert — mit den erwarteten
    Parametern (schema=_Antwort, temperature 0.2, strikt=True, verlauf durchgereicht)."""
    gesehen: dict = {}

    def fake_strukturiert(self, system, nutzer, *, schema, modell, **kw):
        gesehen["system"] = system
        gesehen["nutzer"] = nutzer
        gesehen["schema"] = schema
        gesehen["modell"] = modell
        gesehen["temperature"] = kw.get("temperature")
        gesehen["strikt"] = kw.get("strikt")
        gesehen["verlauf"] = kw.get("verlauf")
        return schema(antwort="OK aus der Runtime")

    monkeypatch.setattr(ki.OllamaRuntime, "strukturiert", fake_strukturiert)
    out = ki.antwort(NOTIZEN, "Was steht drin?", modell="qwen3:4b")

    assert out["antwort"] == "OK aus der Runtime"
    assert out["quellen"] == ["N"]
    assert gesehen["modell"] == "qwen3:4b"
    assert gesehen["schema"] is ki._Antwort
    assert gesehen["temperature"] == 0.2
    assert gesehen["strikt"] is True
    # ohne verlauf ⇒ leere Message-Liste durchgereicht (⇒ strukturiert baut [system, user])
    assert gesehen["verlauf"] == []
    assert "Inhalt der Notiz." in gesehen["nutzer"]


def test_verlauf_wird_als_messages_an_die_runtime_durchgereicht():
    """Der Verlauf (Folgefragen P3.1) landet im /api/chat-Payload ZWISCHEN system und
    user, korrekt gemappt (ki-Turn → assistant); ``format``/``stream`` bleiben erhalten."""
    gesehen: dict = {}

    def fake_post(url, json):     # POSITIONAL von strukturiert gerufen ⇒ bindet daten
        gesehen["url"] = url
        gesehen["json"] = json
        return _Resp("Folge-Antwort.")

    verlauf = [{"rolle": "user", "text": "Erste Frage"},
               {"rolle": "ki", "text": "Erste Antwort"}]
    out = ki.antwort(NOTIZEN, "Und dann?", http_post=fake_post, verlauf=verlauf)

    assert out["antwort"] == "Folge-Antwort."
    assert gesehen["url"].endswith("/api/chat")
    msgs = gesehen["json"]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user" and "Und dann?" in msgs[-1]["content"]
    # Verlauf dazwischen, korrekt gemappt (ki → assistant)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert any(m["role"] == "assistant" and "Erste Antwort" in m["content"] for m in msgs)
    # Constrained decoding + non-streaming bleiben erhalten (0 Verhaltenswechsel)
    assert gesehen["json"]["stream"] is False
    assert gesehen["json"]["format"] == ki._Antwort.model_json_schema()
    assert gesehen["json"]["options"]["temperature"] == 0.2


def test_fehlergranularitaet_bleibt_erhalten():
    """0-Verhaltenswechsel der zwei Fehlerpfade: HTTP≠200 ⇒ error 'ollama' (Ollama
    erreichbar, aber Fehlerstatus); Transportfehler ⇒ error = Exception-Typname."""
    class _R500:
        status_code = 500

        def json(self):
            return {}

    out_500 = ki.antwort(NOTIZEN, "Frage?", http_post=lambda url, json: _R500())
    assert out_500.get("error") == "ollama"
    assert "nicht erreichbar" in out_500["antwort"]
    assert out_500["quellen"] == ["N"]

    def boom(url, json):
        raise ConnectionError("Ollama weg")

    out_exc = ki.antwort(NOTIZEN, "Frage?", http_post=boom)
    assert out_exc.get("error") == "ConnectionError"
    assert "nicht erreichbar" in out_exc["antwort"]


def test_leere_antwort_wird_zu_platzhalter():
    """Validiert eine leere Antwort ⇒ Platzhalter '(keine Antwort)' (wie zuvor)."""
    out = ki.antwort(NOTIZEN, "Frage?", http_post=lambda url, json: _Resp(""))
    assert out["antwort"] == "(keine Antwort)"
    assert "error" not in out


def test_kurzschluss_pfade_unveraendert():
    """Leere Frage + keine Notizen: unveränderte Kurzschluss-Antworten (kein Runtime-Call)."""
    assert ki.antwort(NOTIZEN, "   ")["antwort"] == "Keine Frage erhalten."
    leer = ki.antwort([], "Echte Frage?")
    assert "keine Notiz" in leer["antwort"] and leer["quellen"] == []
