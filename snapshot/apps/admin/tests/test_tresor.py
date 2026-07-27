"""Tests Dizz Admin [AD]: Vertrags-Konformität + Dokument-Vault (Upload-Härtung:
Traversal/Typ/Größe) + Aufgaben-CRUD/Filter + Heute-fällig-KPI + KI-Frage-Smoke
+ MCP-Namensraum + UI-Kit/Marken-Lockup.

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from appkit import conformance
from adminapp import main as am
from adminapp.tresor import heute_iso

def _client(tmp_path, *, max_upload_bytes=None, http_post=None,
            archiv_post=None) -> TestClient:
    kw = {"start_wachter": False}      # Tests starten keinen Hintergrund-Poller
    if max_upload_bytes is not None:
        kw["max_upload_bytes"] = max_upload_bytes
    if http_post is not None:
        kw["http_post"] = http_post
    if archiv_post is not None:
        kw["archiv_post"] = archiv_post
    return TestClient(am.build_app(data_dir=tmp_path, **kw))

def _archiv_capture(store):
    """Mock für den Querverbindungs-POST (archiviere ruft mit keyword ``json=``)."""
    class _R:
        status_code = 200

        def json(self):
            return {"ok": True, "status": "uebersprungen", "grund": "manuell"}

    def post(url, json):
        store.append({"url": url, "umschlag": json})
        return _R()
    return post

def _pdf(name="datei.pdf", inhalt=b"%PDF-1.4 testinhalt", typ="Sonstiges",
         titel="", tags="", notiz=""):
    return {"files": {"datei": (name, inhalt, "application/pdf")},
            "data": {"titel": titel, "typ": typ, "tags": tags, "notiz": notiz}}

def _kpis(c):
    return {k["id"]: k["value"] for k in c.get("/api/summary").json()["kpis"]}

# ===================== Vertrag =====================
def test_vertrag_konform(tmp_path):
    with _client(tmp_path) as c:
        conformance.check_contract(c, "admin")
        # Dizzi-ID-Anschluss installiert; ohne Login = Standalone-Stufe 'lokal'.
        assert c.get("/auth/me").json() == {"angemeldet": False, "level": "lokal"}

# ===================== Dokument-Vault =====================
def test_dokument_upload_liste_kachel_download(tmp_path):
    with _client(tmp_path) as c:
        assert _kpis(c)["dokumente"] == 0
        up = _pdf(name="rechnung.pdf", titel="Stromrechnung", typ="Rechnung",
                  tags="energie, 2026", notiz="Q2")
        r = c.post("/api/dokumente/upload", **up).json()
        assert r["ok"] and r["typ"] == "Rechnung"

        liste = c.get("/api/dokumente").json()
        assert len(liste) == 1
        assert liste[0]["titel"] == "Stromrechnung" and liste[0]["tags"] == ["energie", "2026"]

        assert _kpis(c)["dokumente"] == 1
        assert "dokument_hochgeladen" in [e["action"] for e in c.get("/api/audit").json()]

        dl = c.get(f"/api/dokumente/{r['id']}/datei")
        assert dl.status_code == 200 and dl.content == b"%PDF-1.4 testinhalt"

# ===================== V7: Admin → Memory (docs/26) =====================
def test_dokument_archivieren_an_memory(tmp_path):
    """Der „⇲ Memory"-Knopf schickt die Dokument-METADATEN explizit über den
    Core-Relay an Dizz Memory (Binärdatei bleibt im Admin-Vault): Umschlag korrekt
    (app/strom/ref/explizit), Steuer/Vertrag ⇒ sensibel, nutzer-Tags reisen mit."""
    archiv: list = []
    with _client(tmp_path, archiv_post=_archiv_capture(archiv)) as c:
        up = _pdf(name="bescheid.pdf", titel="Steuerbescheid 2024", typ="Steuer",
                  tags="2024, finanzamt", notiz="Nachzahlung prüfen")
        dok_id = c.post("/api/dokumente/upload", **up).json()["id"]

        r = c.post(f"/api/dokumente/{dok_id}/archivieren")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert archiv, "kein Archiv-Versuch"
        u = archiv[-1]["umschlag"]
        assert u["app"] == "admin" and u["strom"] == "dokument"
        assert u["explizit"] is True and u["ref"] == "admin:dokument:" + dok_id
        assert u["sensibel"] is True                      # Steuer ⇒ sensibel
        assert u["tags"] == ["2024", "finanzamt"]         # Nutzer-Tags reisen mit
        assert u["titel"] == "Dokument · Steuerbescheid 2024"
        assert "Steuer" in u["inhalt"] and "Nachzahlung prüfen" in u["inhalt"]
        assert archiv[-1]["url"].endswith("/api/querverbindung/memory")
        # Audit-Beleg + unbekanntes Dokument ⇒ 404
        assert "dokument_archiviert" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.post("/api/dokumente/fehlt/archivieren").status_code == 404

def test_upload_traversal_abgewehrt(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/dokumente/upload", **_pdf(name="../../../evil.pdf"))
        assert r.status_code == 200
        gespeichert = r.json()["gespeichert_als"]
        assert ".." not in gespeichert and "/" not in gespeichert and "\\" not in gespeichert
        # Datei liegt IM Vault (user-scoped), nicht außerhalb.
        vault = tmp_path / "apps" / "admin" / "vault" / "dizzi"
        assert any(p.name.endswith("evil.pdf") for p in vault.iterdir())
        assert not (tmp_path.parent / "evil.pdf").exists()

def test_upload_typ_abgelehnt(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/dokumente/upload",
                   files={"datei": ("schad.exe", b"MZ\x90", "application/octet-stream")},
                   data={"typ": "Sonstiges"})
        assert r.status_code == 415

def test_upload_zu_gross(tmp_path):
    with _client(tmp_path, max_upload_bytes=64) as c:
        r = c.post("/api/dokumente/upload",
                   **_pdf(name="gross.pdf", inhalt=b"x" * 200))
        assert r.status_code == 413

def test_dokument_patch_und_archiv(tmp_path):
    with _client(tmp_path) as c:
        dok_id = c.post("/api/dokumente/upload", **_pdf(titel="Akte")).json()["id"]
        c.patch(f"/api/dokumente/{dok_id}",
                json={"typ": "Vertrag", "notiz": "neu", "archiv_flag": True, "tags": ["a"]})
        d = c.get("/api/dokumente").json()[0]
        assert d["typ"] == "Vertrag" and d["notiz"] == "neu"
        assert d["archiv_flag"] is True and d["tags"] == ["a"]
        assert len(c.get("/api/dokumente?archiv=1").json()) == 1
        assert len(c.get("/api/dokumente?archiv=0").json()) == 0

def test_dokument_soft_delete(tmp_path):
    with _client(tmp_path) as c:
        dok_id = c.post("/api/dokumente/upload", **_pdf(titel="Weg")).json()["id"]
        assert c.delete(f"/api/dokumente/{dok_id}").json()["ok"]
        assert c.get("/api/dokumente").json() == []
        assert _kpis(c)["dokumente"] == 0
        assert c.delete(f"/api/dokumente/{dok_id}").status_code == 404

def test_dokument_suche(tmp_path):
    with _client(tmp_path) as c:
        # Verschiedene Dokumente ⇒ verschiedene Bytes (sonst greift der SHA-256-Dedupe).
        c.post("/api/dokumente/upload",
               **_pdf(name="m.pdf", inhalt=b"%PDF-1.4 miet", titel="Mietvertrag Wohnung", notiz="Kaution"))
        c.post("/api/dokumente/upload",
               **_pdf(name="s.pdf", inhalt=b"%PDF-1.4 strom", titel="Stromrechnung"))
        assert len(c.get("/api/dokumente?suche=Miet").json()) == 1
        assert len(c.get("/api/dokumente?suche=Kaution").json()) == 1   # Notiz-Treffer
        assert len(c.get("/api/dokumente?suche=xyz").json()) == 0
        assert len(c.get("/api/dokumente?typ=Sonstiges").json()) == 2

# ===================== Aufgaben =====================
def test_aufgabe_crud(tmp_path):
    with _client(tmp_path) as c:
        aid = c.post("/api/aufgaben", json={"titel": "Antrag XY", "prioritaet": "hoch"}).json()["id"]
        lst = c.get("/api/aufgaben").json()
        assert len(lst) == 1 and lst[0]["prioritaet"] == "hoch" and lst[0]["status"] == "offen"
        c.patch(f"/api/aufgaben/{aid}", json={"status": "erledigt"})
        assert c.get("/api/aufgaben").json()[0]["status"] == "erledigt"
        assert c.delete(f"/api/aufgaben/{aid}").json()["ok"]
        assert c.get("/api/aufgaben").json() == []
        assert c.patch(f"/api/aufgaben/{aid}", json={"status": "offen"}).status_code == 404

def test_aufgabe_filter(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/aufgaben", json={"titel": "Heute", "faellig": heute_iso(), "status": "offen"})
        c.post("/api/aufgaben", json={"titel": "Spaeter", "faellig": "2030-01-01", "status": "offen"})
        c.post("/api/aufgaben", json={"titel": "Laufend", "status": "in-bearbeitung"})
        assert {a["titel"] for a in c.get("/api/aufgaben?status=offen").json()} == {"Heute", "Spaeter"}
        assert [a["titel"] for a in c.get("/api/aufgaben?status=in-bearbeitung").json()] == ["Laufend"]
        bis_heute = c.get(f"/api/aufgaben?faellig_bis={heute_iso()}").json()
        assert [a["titel"] for a in bis_heute] == ["Heute"]

# ===================== KI (App-KI-Slot via Mini-Dizzi) =====================
class _FakeResp:
    status_code = 200

    def __init__(self, antwort):
        self._antwort = antwort

    def json(self):
        return {"message": {"content": json.dumps({"antwort": self._antwort})}}

# ===================== MCP-Namensraum =====================

# ===================== Frontend: UI-Kit + K2.3-Marken-Lockup =====================
