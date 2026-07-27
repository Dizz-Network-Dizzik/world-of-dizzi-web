"""Tests Dizz Admin P2 (docs/27 §9): Dokument-Inbox + Review-Flow + KI-Vorschlag
(Typ/Korrespondent/Tags) + Frist-Wächter-Übersicht.

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, timedelta

from fastapi.testclient import TestClient

from adminapp import main as am


def _inbox_kpi(c):
    return {k["id"]: k["value"] for k in c.get("/api/summary").json()["kpis"]}["inbox_offen"]

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

def _client(tmp_path, http_post=None):
    kw = {"start_wachter": False}
    if http_post is not None:
        kw["http_post"] = http_post
    return TestClient(am.build_app(data_dir=tmp_path, **kw))

def _docx(text):
    doc = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", doc)
    return buf.getvalue()

# ===================== Posteingang + Review-Flow =====================
def test_inbox_flow_und_review(tmp_path):
    with _client(tmp_path) as c:
        # manueller Upload ⇒ KEIN Posteingang (bereits kuratiert)
        c.post("/api/dokumente/upload", files={"datei": ("a.pdf", b"%PDF a", "application/pdf")},
               data={"titel": "Manuell"})
        assert c.get("/api/dokumente?inbox=1").json() == []
        # Ordner-Eingang ⇒ Posteingang
        ordner = tmp_path / "in"; ordner.mkdir()
        (ordner / "brief.pdf").write_bytes(b"%PDF brief")
        c.put("/api/settings", json={"key": "watch_ordner", "value": str(ordner)})
        c.post("/api/dokument-quellen/ordner/scan")
        inbox = c.get("/api/dokumente?inbox=1").json()
        assert len(inbox) == 1 and inbox[0]["quelle"] == "folder" and inbox[0]["inbox_flag"] is True
        assert _inbox_kpi(c) == 1

        did = inbox[0]["id"]
        c.patch(f"/api/dokumente/{did}", json={"typ": "Vertrag", "korrespondent": "Amt", "inbox_flag": False})
        assert c.get("/api/dokumente?inbox=1").json() == []
        assert _inbox_kpi(c) == 0
        d = [x for x in c.get("/api/dokumente").json() if x["id"] == did][0]
        assert d["typ"] == "Vertrag" and d["korrespondent"] == "Amt" and d["inbox_flag"] is False

# ===================== KI-Vorschlag (Typ/Korrespondent/Tags) =====================
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

def test_ki_vorschlag_klassifiziert(tmp_path):
    fake = _ki_post({"typ": "Rechnung", "korrespondent": "Stadtwerke", "tags": ["energie", "2024"]})
    with _client(tmp_path, http_post=fake) as c:
        rid = c.post("/api/dokumente/upload", files={"datei": ("r.pdf", b"%PDF r", "application/pdf")},
                     data={"titel": "Strom"}).json()["id"]
        s = c.get(f"/api/dokumente/{rid}/ki-vorschlag").json()
        assert s["quelle"] == "ki" and s["typ"] == "Rechnung" and s["korrespondent"] == "Stadtwerke"
        assert "energie" in s["tags"]

def test_ki_vorschlag_fallback_heuristik(tmp_path):
    # Ollama deterministisch als "nicht erreichbar" mocken (hermetisch — Disziplin
    # "Tests Ollama-frei"): ohne Mock klassifiziert ein LEBENDES Ollama echt -> quelle="ki"
    # und der Test wäre umgebungsabhängig flaky. klassifiziere() fängt den Fehler ab -> {}
    # -> heuristischer Fallback (genau die hier geprüfte Absicht).
    def _ki_down(url, daten):
        raise OSError("Ollama nicht erreichbar (Test)")
    with _client(tmp_path, http_post=_ki_down) as c:
        rid = c.post("/api/dokumente/upload",
                     files={"datei": ("r.docx", _docx("Stromrechnung Finanzamt Zahlung 2024"), _DOCX)},
                     data={"titel": "Rechnung", "typ": "Rechnung"}).json()["id"]
        s = c.get(f"/api/dokumente/{rid}/ki-vorschlag").json()
        assert s["quelle"] == "heuristik" and "finanzamt" in s["tags"]

# ===================== Frist-Wächter-Übersicht =====================
def test_fristen_uebersicht(tmp_path):
    with _client(tmp_path) as c:
        gestern = (date.today() - timedelta(days=1)).isoformat()
        morgen = (date.today() + timedelta(days=2)).isoformat()
        spaet = (date.today() + timedelta(days=200)).isoformat()
        c.post("/api/aufgaben", json={"titel": "Alt", "faellig": gestern})
        c.post("/api/aufgaben", json={"titel": "Bald", "faellig": morgen})
        c.post("/api/aufgaben", json={"titel": "Fern", "faellig": spaet})
        c.post("/api/aufgaben", json={"titel": "OhneFrist"})       # keine Frist ⇒ nicht in der Übersicht
        u = c.get("/api/fristen/uebersicht").json()
        z = u["zaehler"]
        assert z["ueberfaellig"] == 1 and z["woche"] == 1 and z["monat"] == 0 and z["spaeter"] == 1
        assert u["gruppen"]["ueberfaellig"][0]["titel"] == "Alt"

# ===================== Frontend P2 =====================
