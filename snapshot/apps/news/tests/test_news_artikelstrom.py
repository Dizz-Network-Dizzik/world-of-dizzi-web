"""Ausbau 15.06.: Artikel-Strom (Querverbindung strom="artikel") + RÜCK-LESE
(memory_suche als Kontext) + neue Fixquellen. Alle Außenkanäle injiziert
(archiv_post = Memory-Relay, archiv_get = RÜCK-LESE, http_post = Ollama) —
kein Netz, deterministisch."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from newsapp import main as nm


class _Resp:
    def __init__(self, code: int, payload: dict):
        self.status_code = code
        self._p = payload

    def json(self):
        return self._p


def _mit_artikel(tmp_path, monkeypatch, **kw):
    feeds = {nm.SEED_QUELLEN[0][1]: [
        {"titel": "Test-Artikel", "link": "https://x/a",
         "zusammenfassung": "<b>Inhalt</b> der Meldung", "published": "2026-06-15"}]}
    monkeypatch.setattr(nm, "_lade_feed", lambda url: feeds.get(url, []))
    return TestClient(nm.build_app(data_dir=tmp_path, start_timer=False, **kw))


# --- Feature 1: Artikel-Strom ------------------------------------------------

def test_artikel_strom_archivieren(tmp_path, monkeypatch):
    gesendet = {}

    def archiv_post(url, json):
        gesendet["url"] = url
        gesendet["body"] = json
        return _Resp(200, {"ok": True, "status": "archiviert", "id": "m1"})

    with _mit_artikel(tmp_path, monkeypatch, archiv_post=archiv_post) as c:
        c.post("/api/abrufen")
        arts = c.get("/api/artikel").json()
        assert arts and arts[0].get("id")           # id ist jetzt exponiert
        aid = arts[0]["id"]
        r = c.post("/api/artikel/" + aid + "/archivieren").json()
        assert r["ok"] and r["status"] == "archiviert"
        b = gesendet["body"]
        assert b["strom"] == "artikel"
        assert b["ref"] == "news:artikel:" + aid     # stabiler Idempotenz-Schlüssel
        assert b["explizit"] is True                 # Nutzer-Knopf schlägt jede Regel
        assert "Test-Artikel" in b["titel"]
        assert "memory" in gesendet["url"]
        assert "artikel_archiviert" in [e["action"] for e in c.get("/api/audit").json()]


def test_artikel_strom_unbekannt_404(tmp_path, monkeypatch):
    with _mit_artikel(tmp_path, monkeypatch) as c:
        assert c.post("/api/artikel/gibtsnicht/archivieren").status_code == 404


# --- Feature 3: RÜCK-LESE (memory_suche als Kontext) -------------------------

def test_rueck_lese_kontext_im_prompt(tmp_path, monkeypatch):
    fang = {}

    def ollama(url, daten):                          # ki._chat ruft positional (url, payload)
        fang["messages"] = daten.get("messages")
        return _Resp(200, {"message": {"content": json.dumps({"antwort": "OK", "belege": []})}})

    def archiv_get(url, params):                      # memory_suche ruft (url, params=...)
        fang["q"] = params.get("q")
        return _Resp(200, {"ok": True, "anzahl": 1, "treffer": [
            {"titel": "Früherer News-Report", "auszug": "Palantir verlor einen Prozess."}]})

    with _mit_artikel(tmp_path, monkeypatch, http_post=ollama, archiv_get=archiv_get) as c:
        c.post("/api/abrufen")
        j = c.post("/api/fragen", json={"frage": "Was ist mit Palantir?"}).json()
        assert j.get("archiv_kontext") is True
        assert fang["q"] == "Was ist mit Palantir?"  # RÜCK-LESE lief mit der Frage
        nutzer = [m for m in fang["messages"] if m["role"] == "user"][0]["content"]
        assert "FRÜHERE BERICHTE" in nutzer and "Palantir" in nutzer


def test_rueck_lese_archiv_aus_bleibt_still(tmp_path, monkeypatch):
    """Archiv/Core nicht erreichbar ⇒ kein Kontext, KI antwortet normal weiter."""
    def ollama(url, daten):
        return _Resp(200, {"message": {"content": json.dumps({"antwort": "OK", "belege": []})}})

    def archiv_get(url, params):
        return _Resp(500, {})                         # Archiv down

    with _mit_artikel(tmp_path, monkeypatch, http_post=ollama, archiv_get=archiv_get) as c:
        c.post("/api/abrufen")
        j = c.post("/api/fragen", json={"frage": "Test"}).json()
        assert "archiv_kontext" not in j
        assert j["antwort"] == "OK"


# --- P2: Highlight → Memory --------------------------------------------------

def test_highlight_strom_archivieren(tmp_path, monkeypatch):
    import hashlib
    gesendet = {}

    def archiv_post(url, json):
        gesendet["body"] = json
        return _Resp(200, {"ok": True, "status": "archiviert", "id": "h1"})

    with _mit_artikel(tmp_path, monkeypatch, archiv_post=archiv_post) as c:
        text = "Eine markierte Lesestelle aus dem Digest."
        r = c.post("/api/highlight/archivieren", json={"text": text}).json()
        assert r["ok"] and r["status"] == "archiviert"
        b = gesendet["body"]
        assert b["strom"] == "highlight" and b["explizit"] is True
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        assert b["ref"] == "news:highlight:" + h          # stabil/idempotent
        assert text in b["inhalt"]
        assert "highlight_archiviert" in [e["action"] for e in c.get("/api/audit").json()]


def test_highlight_leer_400(tmp_path, monkeypatch):
    with _mit_artikel(tmp_path, monkeypatch) as c:
        assert c.post("/api/highlight/archivieren", json={"text": "   "}).status_code == 400


# --- Feature 2: neue Fixquellen ----------------------------------------------

def test_neue_fixquellen_vorhanden(tmp_path, monkeypatch):
    urls = [u for _, u, _ in nm.SEED_QUELLEN]
    assert "https://www.theguardian.com/business/rss" in urls
    assert any("tagesschau.de/ausland" in u for u in urls)
    assert any("tagesschau.de/wissen" in u for u in urls)
    assert len(nm.SEED_QUELLEN) >= 8
