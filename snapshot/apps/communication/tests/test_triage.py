"""KI-Triage: Schema-Validierung, Opt-in-Gate, Ausfall-Ehrlichkeit."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from kommapp.main import build_app
from kommapp.triage import entwurf, klassifiziere, triagiere, zusammenfassung


class _Antwort:
    def __init__(self, status_code: int, inhalt: str):
        self.status_code = status_code
        self._inhalt = inhalt

    def json(self):
        return {"message": {"content": self._inhalt}}


def _post_mit(inhalt: str, status: int = 200):
    return lambda url, daten: _Antwort(status, inhalt)


def test_triagiere_gueltig():
    nachrichten = [{"betreff": "Rechnung 42", "von_adresse": "amt@example.org",
                    "text": "Bitte bis Freitag zahlen."}]
    out = triagiere(nachrichten, http_post=_post_mit(json.dumps({
        "zusammenfassung": "Eine Rechnung mit Frist.",
        "wichtig": [{"betreff": "Rechnung 42", "grund": "Zahlungsfrist"}]})))
    assert out["zusammenfassung"] == "Eine Rechnung mit Frist."
    assert out["wichtig"][0]["betreff"] == "Rechnung 42"
    assert out["nachrichten_betrachtet"] == 1


def test_triagiere_ehrlich_bei_muell_und_ausfall():
    n = [{"betreff": "x", "von_adresse": "a", "text": "t"}]
    assert "error" in triagiere(n, http_post=_post_mit("kein json"))
    assert "error" in triagiere(n, http_post=_post_mit("{}", status=500))

    def kaputt(url, daten):
        raise ConnectionError("down")
    assert "error" in triagiere(n, http_post=kaputt)
    # leerer Posteingang braucht kein LLM
    assert triagiere([], http_post=kaputt)["wichtig"] == []


def test_triage_endpoint_opt_in(tmp_path):
    app = build_app(data_dir=tmp_path, http_post=_post_mit(json.dumps({
        "zusammenfassung": "Alles ruhig.", "wichtig": []})))
    with TestClient(app) as client:
        # Default AUS (hoechst-App: bewusst opt-in)
        r = client.post("/api/triage")
        assert r.status_code == 409 and "opt-in" in r.json()["error"]
        client.put("/api/settings", json={"key": "ki_triage_aktiv", "value": True})
        out = client.post("/api/triage").json()
        assert out["zusammenfassung"] == "Posteingang ist leer."


def test_klassifiziere_je_nachricht():
    nachrichten = [{"id": "m1", "betreff": "Rechnung 42",
                    "von_adresse": "amt@example.org", "text": "Frist Freitag"},
                   {"id": "m2", "betreff": "20% Rabatt!",
                    "von_adresse": "shop@example.org", "text": "Nur heute"}]
    out = klassifiziere(nachrichten, http_post=_post_mit(json.dumps({"eintraege": [
        {"index": 0, "kategorie": "wichtig", "wichtigkeit": "hoch", "grund": "Frist"},
        {"index": 1, "kategorie": "werbung", "wichtigkeit": "niedrig"}]})))
    eintraege = out["eintraege"]
    assert len(eintraege) == 2
    assert eintraege[0]["betreff"] == "Rechnung 42"   # aus der Liste, nicht vom LLM
    assert eintraege[0]["id"] == "m1" and eintraege[0]["wichtigkeit"] == "hoch"
    assert eintraege[1]["kategorie"] == "werbung"


def test_klassifiziere_verwirft_muell_und_ist_ehrlich():
    n = [{"id": "a", "betreff": "x", "von_adresse": "a", "text": "t"}]
    # Unbekannte Kategorie / Index außerhalb / Dublette ⇒ verworfen.
    out = klassifiziere(n, http_post=_post_mit(json.dumps({"eintraege": [
        {"index": 0, "kategorie": "quatsch", "wichtigkeit": "hoch"},
        {"index": 9, "kategorie": "wichtig", "wichtigkeit": "hoch"},
        {"index": 0, "kategorie": "arbeit", "wichtigkeit": "mittel"}]})))
    assert [e["kategorie"] for e in out["eintraege"]] == ["arbeit"]   # nur der gültige, einmal
    # Müll/Ausfall ⇒ ehrlicher Fehler, kein Absturz
    assert "error" in klassifiziere(n, http_post=_post_mit("kein json"))
    assert "error" in klassifiziere(n, http_post=_post_mit("{}", status=500))
    assert klassifiziere([], http_post=_post_mit("{}"))["eintraege"] == []


def test_triage_nachrichten_endpoint_opt_in(tmp_path):
    app = build_app(data_dir=tmp_path,
                    http_post=_post_mit(json.dumps({"eintraege": []})))
    with TestClient(app) as client:
        assert client.post("/api/triage/nachrichten").status_code == 409
        client.put("/api/settings", json={"key": "ki_triage_aktiv", "value": True})
        out = client.post("/api/triage/nachrichten").json()
        assert out["eintraege"] == []          # leerer Posteingang braucht kein LLM


def test_zusammenfassung_gueltig_und_ehrlich():
    n = [{"von_adresse": "amt@example.org", "betreff": "Rechnung 42",
          "text": "Bitte bis Freitag zahlen."}]
    out = zusammenfassung(n, http_post=_post_mit(json.dumps({
        "zusammenfassung": "Rechnung 42, fällig Freitag."})))
    assert "Rechnung 42" in out["zusammenfassung"]
    assert zusammenfassung([])["zusammenfassung"] == "(leerer Thread)"
    assert "error" in zusammenfassung(n, http_post=_post_mit("kein json"))


def test_zusammenfassung_endpoint_gate_und_404(tmp_path):
    app = build_app(data_dir=tmp_path, http_post=_post_mit(json.dumps({
        "zusammenfassung": "Kurz."})))
    with TestClient(app) as client:
        # Default AUS ⇒ 409 (opt-in)
        assert client.post("/api/konversationen/x/zusammenfassung").status_code == 409
        client.put("/api/settings", json={"key": "ki_triage_aktiv", "value": True})
        # unbekannte/leere Konversation ⇒ 404
        assert client.post("/api/konversationen/x/zusammenfassung").status_code == 404


def test_entwurf_gueltig_und_ehrlich():
    n = [{"richtung": "ein", "von_adresse": "kunde@x.de", "betreff": "Termin?",
          "text": "Passt Dienstag 15 Uhr?"}]
    out = entwurf(n, hinweis="zusagen", http_post=_post_mit(json.dumps({
        "entwurf": "Gerne, Dienstag 15 Uhr passt."})))
    assert "Dienstag" in out["entwurf"]
    assert entwurf([])["entwurf"] == ""
    assert "error" in entwurf(n, http_post=_post_mit("kein json"))


def test_entwurf_endpoint_gate_und_404(tmp_path):
    app = build_app(data_dir=tmp_path,
                    http_post=_post_mit(json.dumps({"entwurf": "ok"})))
    with TestClient(app) as client:
        assert client.post("/api/konversationen/x/entwurf").status_code == 409
        client.put("/api/settings", json={"key": "ki_triage_aktiv", "value": True})
        assert client.post("/api/konversationen/x/entwurf").status_code == 404
