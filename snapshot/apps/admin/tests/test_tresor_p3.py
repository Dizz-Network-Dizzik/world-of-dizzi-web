"""Tests Dizz Admin P3 (docs/27 §9): ELSTER-/steuerrelevant-Markierung +
Aufbewahrungsfristen (Retention je Typ) + Audit-Trail-Ansicht.

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from adminapp import main as am

def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_wachter=False))

def _up(c, name, typ, titel="X"):
    return c.post("/api/dokumente/upload",
                  files={"datei": (name, b"%PDF " + name.encode(), "application/pdf")},
                  data={"titel": titel, "typ": typ}).json()

def test_steuer_default_und_aufbewahrung(tmp_path):
    with _client(tmp_path) as c:
        rid = _up(c, "r.pdf", "Rechnung")["id"]
        sid = _up(c, "s.pdf", "Sonstiges")["id"]
        docs = {d["id"]: d for d in c.get("/api/dokumente").json()}
        r, s = docs[rid], docs[sid]
        assert r["steuer_relevant"] is True and s["steuer_relevant"] is False
        jahr = int(r["erstellt_am"][:4])
        assert r["aufbewahren_bis"] == str(jahr + 10)      # Rechnung: 10 Jahre (GoBD)
        assert s["aufbewahren_bis"] == str(jahr + 3)       # Sonstiges: 3 Jahre

def test_steuer_toggle_filter_uebersicht(tmp_path):
    with _client(tmp_path) as c:
        sid = _up(c, "s.pdf", "Sonstiges")["id"]
        assert c.get("/api/dokumente?steuer=1").json() == []    # Sonstiges nicht steuer per Default
        c.patch(f"/api/dokumente/{sid}", json={"steuer_relevant": True})
        nur = c.get("/api/dokumente?steuer=1").json()
        assert len(nur) == 1 and nur[0]["steuer_relevant"] is True

        u = c.get("/api/steuer/uebersicht").json()
        assert u["gesamt"] == 1 and u["retention_jahre"]["Rechnung"] == 10
        jahr = nur[0]["erstellt_am"][:4]
        assert any(x["jahr"] == jahr and x["anzahl"] == 1 for x in u["jahre"])

def test_audit_trail_vorhanden(tmp_path):
    with _client(tmp_path) as c:
        _up(c, "r.pdf", "Rechnung")
        eintraege = c.get("/api/audit?limit=40").json()
        assert isinstance(eintraege, list)
        assert "dokument_hochgeladen" in [e["action"] for e in eintraege]

