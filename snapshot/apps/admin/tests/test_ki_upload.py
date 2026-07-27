"""Tests Dizz Admin — A4 KI-Klassifikation beim Dokument-Upload (docs/30 B).
Opt-in (Setting): beim Einzug schlägt lokales Ollama Typ/Korrespondent/Tags vor;
der Vorschlag landet im Posteingang zur Bestätigung (HITL — nie automatisch).
Lauf: pytest tests/ -q
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from adminapp import main as am


class _R:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _ki_post(antwort):
    def post(url, daten):
        return _R({"message": {"content": json.dumps(antwort)}})
    return post


def _client(tmp_path, http_post=None):
    kw = {"start_wachter": False}
    if http_post is not None:
        kw["http_post"] = http_post
    return TestClient(am.build_app(data_dir=tmp_path, **kw))


def _upload(c, name="r.pdf", titel="Strom"):
    return c.post("/api/dokumente/upload",
                  files={"datei": (name, b"%PDF rechnung stadtwerke", "application/pdf")},
                  data={"titel": titel}).json()


def test_setting_aus_kein_vorschlag(tmp_path):
    """Default (Setting aus): Upload klassifiziert NICHT — kein Vorschlag, kein Posteingang."""
    fake = _ki_post({"typ": "Rechnung", "korrespondent": "Stadtwerke", "tags": ["energie"]})
    with _client(tmp_path, http_post=fake) as c:
        up = _upload(c)
        assert up.get("ki_vorschlag") is None
        d = [x for x in c.get("/api/dokumente").json() if x["id"] == up["id"]][0]
        assert d["inbox_flag"] is False and "ki_vorschlag" not in d


def test_upload_klassifiziert_und_posteingang(tmp_path):
    fake = _ki_post({"typ": "Rechnung", "korrespondent": "Stadtwerke GmbH", "tags": ["energie", "2024"]})
    with _client(tmp_path, http_post=fake) as c:
        c.put("/api/settings", json={"key": "ki_klassifikation_upload", "value": True})
        up = _upload(c)
        # Vorschlag schon in der Upload-Antwort
        assert up["ki_vorschlag"]["typ"] == "Rechnung"
        assert up["ki_vorschlag"]["korrespondent"] == "Stadtwerke GmbH"
        # Dokument im Posteingang, Vorschlag gespeichert, aber NICHT angewendet (HITL)
        d = [x for x in c.get("/api/dokumente").json() if x["id"] == up["id"]][0]
        assert d["inbox_flag"] is True
        assert d["ki_vorschlag"]["typ"] == "Rechnung"
        assert d["typ"] == "Sonstiges"          # noch NICHT übernommen
        assert d["korrespondent"] == ""


def test_uebernehmen_wendet_an(tmp_path):
    fake = _ki_post({"typ": "Rechnung", "korrespondent": "Stadtwerke", "tags": ["energie", "2024"]})
    with _client(tmp_path, http_post=fake) as c:
        c.put("/api/settings", json={"key": "ki_klassifikation_upload", "value": True})
        up = _upload(c)
        res = c.post(f"/api/dokumente/{up['id']}/vorschlag-uebernehmen").json()
        assert res["ok"] and res["typ"] == "Rechnung" and res["korrespondent"] == "Stadtwerke"
        assert "energie" in res["tags"]
        d = [x for x in c.get("/api/dokumente").json() if x["id"] == up["id"]][0]
        assert d["typ"] == "Rechnung" and d["korrespondent"] == "Stadtwerke"
        assert d["steuer_relevant"] is True          # Rechnung ⇒ steuer-relevant
        assert d["inbox_flag"] is False              # Review abgeschlossen
        assert "ki_vorschlag" not in d               # Vorschlag geräumt


def test_uebernehmen_on_demand_ohne_gespeicherten_vorschlag(tmp_path):
    """Setting aus ⇒ kein gespeicherter Vorschlag; übernehmen berechnet on-demand."""
    fake = _ki_post({"typ": "Vertrag", "korrespondent": "Amt", "tags": ["miete"]})
    with _client(tmp_path, http_post=fake) as c:
        up = _upload(c, titel="Mietvertrag")
        assert up.get("ki_vorschlag") is None
        res = c.post(f"/api/dokumente/{up['id']}/vorschlag-uebernehmen").json()
        assert res["typ"] == "Vertrag" and res["korrespondent"] == "Amt"


def test_leerer_ki_vorschlag_kein_posteingang(tmp_path):
    """KI liefert nichts Brauchbares ⇒ kein Vorschlag, manueller Upload bleibt kuratiert."""
    fake = _ki_post({"typ": "", "korrespondent": "", "tags": []})
    with _client(tmp_path, http_post=fake) as c:
        c.put("/api/settings", json={"key": "ki_klassifikation_upload", "value": True})
        up = _upload(c)
        assert up.get("ki_vorschlag") is None
        d = [x for x in c.get("/api/dokumente").json() if x["id"] == up["id"]][0]
        assert d["inbox_flag"] is False
