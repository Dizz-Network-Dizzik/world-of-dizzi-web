"""Tests Dizz Admin — Tresor-Extra-Sicherheit (docs/28 §6, Phase 6): Fernet-at-rest
+ Dizzi-ID-Step-up beim Lesen/Entschlüsseln. Lauf: <venv-python> -m pytest tests/ -q
"""

from __future__ import annotations

import contextlib

from fastapi.testclient import TestClient

from appkit.auth import UserContext, current_user

from adminapp import main as lm


@contextlib.contextmanager
def _client_app(tmp_path):
    app = lm.build_app(data_dir=tmp_path)
    with TestClient(app) as c:
        yield app, c


def _vault_dateien(tmp_path):
    d = tmp_path / "apps" / "admin" / "vault" / "dizzi"
    return [p for p in d.rglob("*") if p.is_file()] if d.is_dir() else []


def _stepup(app):
    app.dependency_overrides[current_user] = lambda: UserContext(
        user_id="dizzi", level="verifiziert")


def test_verschluesselt_upload_at_rest_und_gate(tmp_path):
    with _client_app(tmp_path) as (app, c):
        did = c.post("/api/dokumente/upload",
                     files={"datei": ("akte.pdf", b"%PDF-1.4 STRENGGEHEIMERINHALT", "application/pdf")},
                     data={"titel": "Akte X", "verschluesselt": "1", "fach": "Tresor-A"}).json()["id"]
        d = [x for x in c.get("/api/dokumente").json() if x["id"] == did][0]
        assert d["verschluesselt"] is True and d["fach"] == "Tresor-A"
        assert d["volltext_methode"] == "verschluesselt"        # kein Volltext extrahiert/indexiert
        # Datei liegt at-rest VERSCHLÜSSELT (kein Klartext, Fernet-Token-Präfix)
        roh = _vault_dateien(tmp_path)[0].read_bytes()
        assert b"STRENGGEHEIMERINHALT" not in roh and roh.startswith(b"gAAAAA")
        # Titel bleibt auffindbar, Inhalt nicht (Inhalt war nie indexiert)
        assert len(c.get("/api/dokumente?suche=Akte").json()) == 1
        # Lesen bei Stufe 'lokal' ⇒ 403 (Step-up nötig)
        assert c.get(f"/api/dokumente/{did}/datei").status_code == 403


def test_stepup_entschluesselt_korrekt(tmp_path):
    with _client_app(tmp_path) as (app, c):
        did = c.post("/api/dokumente/upload",
                     files={"datei": ("g.pdf", b"%PDF KLARTEXT-INHALT", "application/pdf")},
                     data={"verschluesselt": "1"}).json()["id"]
        _stepup(app)                                            # verifizierte Verbindung
        dl = c.get(f"/api/dokumente/{did}/datei")
        assert dl.status_code == 200 and dl.content == b"%PDF KLARTEXT-INHALT"   # Round-Trip korrekt
        app.dependency_overrides.clear()


def test_nachtraeglich_verschluesseln_und_zurueck(tmp_path):
    with _client_app(tmp_path) as (app, c):
        did = c.post("/api/dokumente/upload",
                     files={"datei": ("r.pdf", b"%PDF Rechnung", "application/pdf")},
                     data={"titel": "Rechnung"}).json()["id"]
        assert c.get(f"/api/dokumente/{did}/datei").status_code == 200       # Klartext, lesbar
        # nachträglich schützen (darf man bei 'lokal')
        assert c.post(f"/api/dokumente/{did}/verschluesseln").json()["verschluesselt"] is True
        d = [x for x in c.get("/api/dokumente").json() if x["id"] == did][0]
        assert d["verschluesselt"] is True and d["volltext_methode"] == "verschluesselt"
        assert c.get(f"/api/dokumente/{did}/datei").status_code == 403       # jetzt gated
        # Entschlüsseln verlangt Step-up
        assert c.post(f"/api/dokumente/{did}/entschluesseln").status_code == 403
        _stepup(app)
        assert c.post(f"/api/dokumente/{did}/entschluesseln").json()["verschluesselt"] is False
        assert c.get(f"/api/dokumente/{did}/datei").status_code == 200       # wieder Klartext
        app.dependency_overrides.clear()


def test_on_delete_raeumt_krypto_schluessel(tmp_path):
    with _client_app(tmp_path) as (app, c):
        c.post("/api/dokumente/upload",
               files={"datei": ("g.pdf", b"%PDF x", "application/pdf")},
               data={"verschluesselt": "1"})
        tdom = app.state.tresor
        assert tdom.vault.get("tresor_fernet_key")              # Schlüssel angelegt
        assert tdom.on_delete("dizzi")["krypto_schluessel_geloescht"] is True
        assert tdom.vault.get("tresor_fernet_key") is None      # weg (DSGVO)
