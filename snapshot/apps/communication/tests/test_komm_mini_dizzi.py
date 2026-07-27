"""Inbox-aware App-KI (Vertrag 1.5): triage.frage beantwortet NUR aus dem
Posteingang-Auszug (lokal, Ollama, JSON-Schema), und build_app registriert sie
via set_app_ki — POST /api/ki/frage liefert dann die Quelle ``app_ki`` statt des
generischen Fallbacks. Ohne Ollama: ehrlicher Fehler, nie Halluzination."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from kommapp.main import build_app
from kommapp.mail import KanalQuelle, OrdnerZustand
from kommapp.triage import frage


class _Antwort:
    def __init__(self, status_code: int, inhalt: str):
        self.status_code = status_code
        self._inhalt = inhalt

    def json(self):
        return {"message": {"content": self._inhalt}}


def _post_mit(inhalt: str, status: int = 200):
    return lambda url, daten: _Antwort(status, inhalt)


def test_frage_antwortet_aus_posteingang():
    nachrichten = [{"betreff": "Rechnung 42", "von_adresse": "amt@example.org",
                    "text": "Bitte bis Freitag zahlen."}]
    out = frage(nachrichten, "Welche Rechnung ist offen?",
                http_post=_post_mit(json.dumps({
                    "antwort": "Rechnung 42 ist offen (Frist Freitag).",
                    "belege": ["Rechnung 42"]})))
    assert "Rechnung 42" in out["antwort"]
    assert out["belege"] == ["Rechnung 42"]
    assert out["nachrichten_betrachtet"] == 1


def test_frage_leer_und_ehrlich():
    # leerer Posteingang ohne Stand ⇒ kein LLM nötig
    assert frage([], "irgendwas")["belege"] == []
    n = [{"betreff": "x", "von_adresse": "a", "text": "t"}]
    assert frage(n, "")["antwort"] == "Keine Frage erhalten."      # keine Frage
    assert "error" in frage(n, "f", http_post=_post_mit("kein json"))
    assert "error" in frage(n, "f", http_post=_post_mit("{}", status=500))


class FakeQuelle(KanalQuelle):
    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:
            return ([{"kanal_typ": "email", "extern_id": "<a@x>",
                      "von_adresse": "amt@example.org", "an_adressen": "d@local",
                      "betreff": "Rechnung 42", "text": "Bitte bis Freitag zahlen",
                      "gesendet_at": "2026-06-12", "thread_schluessel": "<a@x>"}],
                    OrdnerZustand(2, 3))
        return ([], zustand)


def test_ki_frage_nutzt_inbox_aware_app_ki(tmp_path):
    """End-to-End: Konto → Sync → POST /api/ki/frage liefert die App-KI-Antwort
    (Quelle app_ki), gegründet auf den synchronisierten Posteingang."""
    fake = _post_mit(json.dumps({
        "antwort": "Rechnung 42 ist offen (Frist Freitag).",
        "belege": ["Rechnung 42"]}))
    app = build_app(data_dir=tmp_path, http_post=fake,
                    quelle_factory=lambda konto, geheimnis: FakeQuelle())
    with TestClient(app) as client:
        kid = client.post("/api/konten", json={
            "name": "K", "host": "h", "benutzer": "u", "geheimnis": "g"}).json()["id"]
        client.post("/api/sync", json={"konto_id": kid})
        r = client.post("/api/ki/frage", json={"frage": "Welche Rechnung ist offen?"}).json()
        assert r["quelle"] == "app_ki"
        assert "Rechnung 42" in r["antwort"]


def test_ki_frage_ohne_ollama_faellt_ehrlich_zurueck(tmp_path):
    """App-KI ohne brauchbares Ollama ⇒ leere Antwort ⇒ Mini-Dizzi-Fallback,
    nie eine erfundene Antwort. Hermetisch: auch der generische Ollama-Fallback
    bekommt einen 500-Poster injiziert (sonst träfe der Test ein evtl. real
    laufendes Ollama und hinge bis zu 90 s)."""
    app = build_app(data_dir=tmp_path, http_post=_post_mit("kaputt", status=500))
    # mini_dizzi._ollama ruft poster(url, json=...) ⇒ Signatur mit json-Keyword.
    app.state.mini_dizzi._http_post = lambda url, json=None: _Antwort(500, "")
    with TestClient(app) as client:
        r = client.post("/api/ki/frage", json={"frage": "Was liegt an?"}).json()
        assert r["quelle"] == "kein_ollama"      # deterministisch ohne echtes Ollama
        assert r["antwort"]
