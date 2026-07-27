"""P1 — Termin-Auto-Erkennung (Triage-gekoppelt → Sammel-HITL → V5 Admin-Kalender).

erkenne_termine (lokal, JSON-Schema, ISO-Validierung, relative Daten gegen heute);
/api/triage liefert termine als VORSCHLÄGE (nicht angelegt); /api/termine/anlegen
trägt die bestätigten Termine über V5 (sende_termin) ein, idempotent. Netzfrei."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from kommapp.main import build_app
from kommapp.triage import erkenne_termine


# Ollama-Mock (triage-Konvention: http_post(url, daten) positional)
class _Ollama:
    def __init__(self, status, inhalt):
        self.status_code = status
        self._i = inhalt

    def json(self):
        return {"message": {"content": self._i}}


def _ollama(inhalt, status=200):
    return lambda url, daten: _Ollama(status, inhalt)


# Core-Relay-Mock (sende_termin-Konvention: http_post(url, json=...))
class _Relay:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._p = payload

    def json(self):
        return self._p


# ── erkenne_termine (rein) ────────────────────────────────────────────────────
def test_erkenne_termine_filtert_ungueltige_iso():
    n = [{"betreff": "Kino?", "von_adresse": "a@x", "text": "Donnerstag 19:00 Kino?"}]
    out = erkenne_termine(n, heute="2026-06-26", http_post=_ollama(json.dumps({
        "termine": [{"titel": "Kino", "beginn": "2026-07-02T19:00", "beleg": "Do 19:00"},
                    {"titel": "Vage", "beginn": "irgendwann"},          # keine ISO → raus
                    {"titel": "", "beginn": "2026-07-03"}]})))           # kein Titel → raus
    assert [t["titel"] for t in out["termine"]] == ["Kino"]
    assert out["termine"][0]["beginn"] == "2026-07-02T19:00"
    assert out["heute"] == "2026-06-26"


def test_erkenne_termine_leer_und_fehler():
    assert erkenne_termine([])["termine"] == []
    n = [{"betreff": "x", "von_adresse": "a", "text": "t"}]
    assert "error" in erkenne_termine(n, http_post=_ollama("kein json"))
    assert "error" in erkenne_termine(n, http_post=_ollama("{}", status=500))


# ── /api/triage liefert termine (Teil des Triage-Knopfs) ──────────────────────
def test_triage_endpoint_liefert_termine(tmp_path):
    def mock(url, daten):
        sys = daten["messages"][0]["content"]
        if "KONKRETE Termine" in sys:
            return _Ollama(200, json.dumps({"termine": [
                {"titel": "Kino", "beginn": "2026-07-02T19:00", "beleg": "Do 19:00"}]}))
        return _Ollama(200, json.dumps({"zusammenfassung": "ok", "wichtig": []}))
    with TestClient(build_app(data_dir=tmp_path, http_post=mock)) as c:
        c.put("/api/settings", json={"key": "ki_triage_aktiv", "value": True})
        c.post("/api/kanaele/telegram/simulieren",
               json={"von": "@bob", "text": "Donnerstag 19:00 Kino?"})
        out = c.post("/api/triage").json()
        assert out["zusammenfassung"] == "ok"
        assert [t["titel"] for t in out["termine"]] == ["Kino"]   # Vorschläge, NICHT angelegt
        # nichts wurde im Admin-Kalender angelegt (nur Vorschlag)
        assert c.get("/api/kalender/termine").json() == []


# ── /api/termine/anlegen (Sammel-HITL → V5) ───────────────────────────────────
def test_termine_anlegen_ueber_v5(tmp_path):
    calls = []

    def fake_relay(url, json):
        calls.append((url, json))
        return _Relay({"ok": True, "status": "eingetragen", "id": "t" + str(len(calls))})

    with TestClient(build_app(data_dir=tmp_path, archiv_post=fake_relay)) as c:
        r = c.post("/api/termine/anlegen", json={"termine": [
            {"titel": "Kino", "beginn": "2026-07-02T19:00"},
            {"titel": "Ohne Datum", "beginn": ""}]}).json()           # übersprungen
        assert r["angelegt"] == 1
        assert [e["status"] for e in r["ergebnisse"]] == ["eingetragen", "uebersprungen"]
        # genau ein V5-Aufruf an den Admin-Kalender, mit App/Quelle/idempotentem ref
        assert len(calls) == 1
        url, umschlag = calls[0]
        assert "/querverbindung/admin/kalender" in url
        assert umschlag["app"] == "kommunikation" and umschlag["titel"] == "Kino"
        assert umschlag["quelle"] == "komm:triage" and umschlag["ref"].startswith("komm:triage:")


def test_termine_anlegen_leer(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as c:
        assert c.post("/api/termine/anlegen", json={"termine": []}).json()["angelegt"] == 0
