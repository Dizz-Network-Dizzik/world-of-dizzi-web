"""Tests Dizz Admin P1 (UI/UX-Ausbau, docs/27 §9): Korrespondent-Feld + Facetten
(Typ/Korrespondent/Jahr/Tags) + Thumbnails (Bild via PIL, PDF/DOCX = Typ-Icon) +
Grid/Liste + netkit-Einhängung.

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from adminapp import main as am

def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_wachter=False))

def _png(w=10, h=10, color=(210, 60, 90)) -> bytes:
    from PIL import Image
    im = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()

def _up(c, name, daten, mime, **felder):
    return c.post("/api/dokumente/upload", files={"datei": (name, daten, mime)}, data=felder).json()

# ===================== Korrespondent + Facetten =====================
def test_korrespondent_und_facetten(tmp_path):
    with _client(tmp_path) as c:
        _up(c, "a.pdf", b"%PDF a", "application/pdf",
            titel="Strom", typ="Rechnung", korrespondent="Stadtwerke", tags="2024")
        _up(c, "b.pdf", b"%PDF b", "application/pdf",
            titel="Bescheid", typ="Steuer", korrespondent="Finanzamt")
        docs = c.get("/api/dokumente").json()
        assert {d["korrespondent"] for d in docs} == {"Stadtwerke", "Finanzamt"}

        f = c.get("/api/facetten").json()
        assert {x["wert"]: x["anzahl"] for x in f["korrespondent"]} == {"Stadtwerke": 1, "Finanzamt": 1}
        typ = {x["wert"]: x["anzahl"] for x in f["typ"]}
        assert typ["Rechnung"] == 1 and typ["Steuer"] == 1
        assert [x["wert"] for x in f["tags"]] == ["2024"]

        nur = c.get("/api/dokumente?korrespondent=Finanzamt").json()
        assert len(nur) == 1 and nur[0]["titel"] == "Bescheid"

def test_jahr_facette_und_filter(tmp_path):
    with _client(tmp_path) as c:
        _up(c, "a.pdf", b"%PDF a", "application/pdf", titel="X")
        jahr = c.get("/api/dokumente").json()[0]["erstellt_am"][:4]
        f = c.get("/api/facetten").json()
        assert any(x["wert"] == jahr for x in f["jahr"])
        assert len(c.get("/api/dokumente?jahr=" + jahr).json()) == 1
        assert c.get("/api/dokumente?jahr=1999").json() == []

def test_korrespondent_patch(tmp_path):
    with _client(tmp_path) as c:
        rid = _up(c, "a.pdf", b"%PDF a", "application/pdf", titel="X")["id"]
        c.patch(f"/api/dokumente/{rid}", json={"korrespondent": "Neuer Partner"})
        assert c.get("/api/dokumente").json()[0]["korrespondent"] == "Neuer Partner"

# ===================== Thumbnails (Bild via PIL, PDF = Typ-Icon/404) =====================
def test_thumbnail_bild_vs_pdf(tmp_path):
    with _client(tmp_path) as c:
        rb = _up(c, "foto.png", _png(), "image/png", titel="Foto")["id"]
        d = [x for x in c.get("/api/dokumente").json() if x["id"] == rb][0]
        assert d["ist_bild"] is True
        t = c.get(f"/api/dokumente/{rb}/thumb")
        assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg" and len(t.content) > 0

        rp = _up(c, "x.pdf", b"%PDF x", "application/pdf")["id"]
        assert c.get(f"/api/dokumente/{rp}/thumb").status_code == 404   # kein Renderer ⇒ Typ-Icon

# ===================== Frontend P1 (Grid/Facetten/netkit) =====================
