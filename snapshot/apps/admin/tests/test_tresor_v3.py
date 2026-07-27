"""Tests Dizz Admin v3 (Vertiefung): Frist→Dizzi-Glocke + V12-Plans-Slot,
FTS5-Ranking/Snippet + Tagging, Memory-Rück-Lese (KI + Endpoint),
Cross-Money read-only-Slot, on_delete-Hygiene (Vault + FTS).

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, timedelta

from fastapi.testclient import TestClient

from adminapp import main as am

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

def _client(tmp_path, *, http_post=None, event_post=None, memory_get=None):
    kw = {"start_wachter": False}
    if http_post is not None:
        kw["http_post"] = http_post
    if event_post is not None:
        kw["event_post"] = event_post
    if memory_get is not None:
        kw["memory_get"] = memory_get
    return TestClient(am.build_app(data_dir=tmp_path, **kw))

def _docx(text: str) -> bytes:
    doc = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", doc)
    return buf.getvalue()

def _upload_docx(c, name, text, **felder):
    return c.post("/api/dokumente/upload",
                  files={"datei": (name, _docx(text), _DOCX_MIME)},
                  data=felder).json()

# --- Mocks (gleiches Muster wie _archiv_capture in test_admin.py) ---
class _R:
    status_code = 200

    def __init__(self, payload=None):
        self._p = payload or {}

    def json(self):
        return self._p

def _event_capture(store):
    def post(url, json):
        store.append({"url": url, "payload": json})
        return _R()
    return post

def _memory_get(treffer):
    def get(url, params):
        return _R({"ok": True, "treffer": treffer, "anzahl": len(treffer)})
    return get

def _chat_capture(store, antwort="Aus dem Archiv: Frist 3 Monate."):
    def post(url, json):
        store.append(json)
        return _R({"message": {"content": __import__("json").dumps({"antwort": antwort})}})
    return post

# ===================== V12: Frist → Dizz Plans (Kalender, V5-Vertrag) =====================
def _kalender_capture(store):
    def post(url, json):
        store.append({"url": url, "payload": json})
        return _R({"ok": True, "status": "eingetragen", "id": "k1"})
    return post

# ===================== A: Frist → Dizzi-Glocke (event_push) =====================

# ===================== A: V12-Sender-SLOT (Frist → Plans), nur Entwurf =====================

# ===================== B: FTS5-Ranking + Snippet =====================
def test_fts_ranking_und_snippet(tmp_path):
    with _client(tmp_path) as c:
        _upload_docx(c, "a.docx", "Mietvertrag Wohnung Kuendigung zum Quartalsende", titel="Vertrag A")
        res = c.get("/api/dokumente?suche=Quartalsende").json()
        assert len(res) == 1
        d = res[0]
        assert "schnipsel" in d and "Quartalsende" in d["schnipsel"] and "‹" in d["schnipsel"]
        assert "rang" in d and isinstance(d["rang"], float)

# ===================== B: Tagging (Cloud + Filter + Vorschläge) =====================
def test_tags_cloud_und_filter(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/dokumente/upload", files={"datei": ("a.pdf", b"%PDF a", "application/pdf")},
               data={"titel": "A", "tags": "steuer, 2024"})
        c.post("/api/dokumente/upload", files={"datei": ("b.pdf", b"%PDF b", "application/pdf")},
               data={"titel": "B", "tags": "steuer, miete"})
        cloud = {t["tag"]: t["anzahl"] for t in c.get("/api/tags").json()}
        assert cloud["steuer"] == 2 and cloud["2024"] == 1 and cloud["miete"] == 1
        nur_miete = c.get("/api/dokumente?tag=miete").json()
        assert len(nur_miete) == 1 and nur_miete[0]["titel"] == "B"
        assert len(c.get("/api/dokumente?tag=steuer").json()) == 2

def test_tag_vorschlaege(tmp_path):
    with _client(tmp_path) as c:
        r = _upload_docx(c, "r.docx", "Stromrechnung Finanzamt Zahlung 2024",
                         titel="Rechnung Mai", typ="Rechnung", tags="bestand")
        v = c.get(f"/api/dokumente/{r['id']}/tag-vorschlaege").json()["vorschlaege"]
        assert "rechnung" in v and "finanzamt" in v and "energie" in v and "2024" in v
        assert "bestand" not in v                       # vorhandene Tags ausgelassen

# ===================== C: Memory-Rück-Lese (Endpoint + KI-Kontext) =====================
def test_memory_ruecklese_endpoint(tmp_path):
    treffer = [{"titel": "Altvertrag 2019", "auszug": "Kuendigungsfrist 3 Monate"}]
    with _client(tmp_path, memory_get=_memory_get(treffer)) as c:
        r = c.get("/api/memory/suche?q=Kuendigung").json()
        assert r["ok"] is True and r["anzahl"] == 1
        assert r["treffer"][0]["titel"] == "Altvertrag 2019"
        assert "memory_ruecklese" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.get("/api/memory/suche?q=").json()["anzahl"] == 0   # leere Query: kein Core-Call

# ===================== D: Cross-Money read-only-SLOT =====================
def test_money_status_slot(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/dokumente/upload",
                   files={"datei": ("r.pdf", b"%PDF r", "application/pdf")},
                   data={"titel": "Rechnung", "typ": "Rechnung"}).json()
        m = c.get(f"/api/dokumente/{r['id']}/money-status").json()
        assert m["status"] == "slot" and m["richtung"] == "lese" and m["ziel_app"] == "finanzen"
        assert "anfrage_entwurf" in m

# ===================== Frontend v3 (Memory-Suche, Tag-Wolke, Slots) =====================

# ===================== E: on_delete-Hygiene (Vault + FTS) =====================
def test_on_delete_raeumt_vault_und_fts(tmp_path):
    app = am.build_app(data_dir=tmp_path, start_wachter=False)
    dom = app.state.tresor
    with TestClient(app) as c:
        _upload_docx(c, "x.docx", "Geheim Steuerbescheid Nachzahlung", titel="X")
        vault = tmp_path / "apps" / "admin" / "vault" / "dizzi"
        assert any(vault.iterdir())
        assert len(c.get("/api/dokumente?suche=Geheim").json()) == 1
        res = dom.on_delete("dizzi")                     # Hook direkt (appkit ruft ihn nach der Kaskade)
        assert res["vault_dateien_geloescht"] >= 1 and res["fts_geraeumt"] is True
        assert not vault.exists()
        assert c.get("/api/dokumente?suche=Geheim").json() == []     # FTS geräumt ⇒ kein Treffer
