"""ELSTER-Transport — Vault + Zertifikat + Konnektor + Scharfschalt-Akt (M1-2,
docs/65 §8/§11/§12). Akzeptanz dieser Stufe:

  * PIN → Vault OHNE Echo (nie in Response/Audit); der Wert liegt real im Tresor,
  * .pfx-Import in die Daten-Wurzel (nie im Repo, Bytes nie in der Response),
  * Konnektor „verbunden" ERST mit Zertifikat + PIN + Zwei-Schlüssel-Scharfschaltung,
  * ``pruefe_scharf`` end-to-end (der Scharfschalt-Akt geht nur mit Zertifikat+PIN),
  * Löschen eines Zugangs räumt die Geheimnisse mit (Vault-PIN + .pfx) — „weg = weg".
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from moneyapp import main as mm
from moneyapp.elster import persistenz as ep, vertrag as v

USER = mm.DEFAULT_USER_ID
_PFX = base64.b64encode(b"FAKE-PFX-BYTES-GEHEIM-4711").decode()


def _app(tmp_path):
    return mm.build_app(data_dir=tmp_path)


def _neuer_zugang(c) -> str:
    return c.post("/api/elster/zugaenge",
                  json={"zertifikat_pfad": "z.pfx", "steuernummer": "123/456/78901"}).json()["id"]


def _verbunden(c) -> int:
    return c.get("/api/konnektoren").json()["verbunden"]


# ------------------------------------------------------------------- PIN → Vault

def test_pin_setzen_kein_echo_aber_im_vault(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        zid = _neuer_zugang(c)
        r = c.post(f"/api/elster/zugaenge/{zid}/pin", json={"pin": "GEHEIM-PIN-9"})
        assert r.json() == {"ok": True, "pin_gesetzt": True}
        assert "GEHEIM-PIN-9" not in r.text                     # KEIN Echo
        # in der Zugangs-Liste erscheint nur die PRÄSENZ, nie der Wert:
        liste = c.get("/api/elster/zugaenge")
        assert liste.json()[0]["pin_gesetzt"] is True
        assert "GEHEIM-PIN-9" not in liste.text
        assert "GEHEIM-PIN-9" not in c.get("/api/konnektoren").text
    # der Wert liegt real im Tresor (unter elster_pin_<zid>):
    assert app.state.vault.get(f"{v.PIN_VAULT_PREFIX}{zid}") == "GEHEIM-PIN-9"


def test_pin_leer_400_und_unbekannt_404(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        zid = _neuer_zugang(c)
        assert c.post(f"/api/elster/zugaenge/{zid}/pin", json={"pin": "  "}).status_code == 400
        assert c.post("/api/elster/zugaenge/weg/pin", json={"pin": "x"}).status_code == 404


def test_pin_nie_in_audit(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        zid = _neuer_zugang(c)
        c.post(f"/api/elster/zugaenge/{zid}/pin", json={"pin": "GEHEIM-PIN-9"})
    # das Audit-Protokoll trägt den Vorgang, aber NIE die PIN:
    audit = json.dumps(app.state.db.audit_recent(USER))
    assert "elster_pin_gesetzt" in audit and "GEHEIM-PIN-9" not in audit


# ------------------------------------------------------------- Zertifikat-Import

def test_zertifikat_import_in_datenwurzel_ohne_echo(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        zid = _neuer_zugang(c)
        r = c.post(f"/api/elster/zugaenge/{zid}/zertifikat", json={"inhalt_b64": _PFX})
        assert r.json() == {"ok": True, "zertifikat_importiert": True}
        assert _PFX not in r.text and "FAKE-PFX" not in r.text        # Bytes nie zurück
        assert c.get("/api/elster/zugaenge").json()[0]["zertifikat_importiert"] is True
    # Datei liegt in der Daten-Wurzel (tmp_path), NICHT im Repo:
    ziel = app.state.db.db_path.parent / "elster" / f"{zid}.pfx"
    assert ziel.exists() and ziel.read_bytes() == b"FAKE-PFX-BYTES-GEHEIM-4711"


def test_zertifikat_ungueltig_leer_zu_gross(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        zid = _neuer_zugang(c)
        assert c.post(f"/api/elster/zugaenge/{zid}/zertifikat",
                      json={"inhalt_b64": "kein~base64!"}).status_code == 400
        assert c.post(f"/api/elster/zugaenge/{zid}/zertifikat",
                      json={"inhalt_b64": ""}).status_code == 400
        riesig = base64.b64encode(b"x" * (256 * 1024 + 1)).decode()
        assert c.post(f"/api/elster/zugaenge/{zid}/zertifikat",
                      json={"inhalt_b64": riesig}).status_code == 400
        assert c.post("/api/elster/zugaenge/weg/zertifikat",
                      json={"inhalt_b64": _PFX}).status_code == 404


# ------------------------------------------ Konnektor „verbunden" erst mit allem

def test_konnektor_verbunden_erst_mit_cert_pin_scharf(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        assert _verbunden(c) == 0                                  # frisch: nichts verbunden
        zid = _neuer_zugang(c)
        assert _verbunden(c) == 0                                  # nur Zugang: noch nicht
        c.post(f"/api/elster/zugaenge/{zid}/zertifikat", json={"inhalt_b64": _PFX})
        c.post(f"/api/elster/zugaenge/{zid}/pin", json={"pin": "PIN-1"})
        assert _verbunden(c) == 0                                  # Cert+PIN, aber nicht scharf
        assert c.post(f"/api/elster/zugaenge/{zid}/scharf").json() == {"ok": True, "scharf": True}
        assert _verbunden(c) == 1                                  # jetzt verbunden
        # der Konnektor deklariert richtung=senden, sensitivity=hoch:
        elster = [k for k in c.get("/api/konnektoren").json()["konnektoren"] if k["id"] == "elster"][0]
        assert elster["richtung"] == "senden" and elster["sensitivity"] == "hoch"
        assert elster["verbunden"] is True


def test_scharfschalten_verlangt_cert_und_pin(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        zid = _neuer_zugang(c)
        assert c.post(f"/api/elster/zugaenge/{zid}/scharf").status_code == 409   # nichts da
        c.post(f"/api/elster/zugaenge/{zid}/zertifikat", json={"inhalt_b64": _PFX})
        assert c.post(f"/api/elster/zugaenge/{zid}/scharf").status_code == 409   # PIN fehlt noch
        c.post(f"/api/elster/zugaenge/{zid}/pin", json={"pin": "PIN-1"})
        assert c.post(f"/api/elster/zugaenge/{zid}/scharf").json()["scharf"] is True
        assert c.get(f"/api/elster/zugaenge/{zid}").json()["scharf"] is True


def test_scharf_ist_pruefe_scharf_e2e(tmp_path):
    """Der HTTP-200 des Scharfschaltens IST der e2e-Beweis (der Endpoint ruft intern
    ``pruefe_scharf``); zusätzlich über die Vertrags-Naht gegengeprüft."""
    app = _app(tmp_path)
    db = mm.Database(mm.default_db_path(mm.APP_ID, data_root=tmp_path))
    speicher = ep.ElsterSpeicher(db)
    with TestClient(app) as c:
        zid = _neuer_zugang(c)
        with pytest.raises(v.NichtScharf):
            v.pruefe_scharf(speicher.scharfschaltung(USER, zid))    # vorher: nicht scharf
        c.post(f"/api/elster/zugaenge/{zid}/zertifikat", json={"inhalt_b64": _PFX})
        c.post(f"/api/elster/zugaenge/{zid}/pin", json={"pin": "PIN-1"})
        c.post(f"/api/elster/zugaenge/{zid}/scharf")
        v.pruefe_scharf(speicher.scharfschaltung(USER, zid))        # nachher: geht durch


def test_entschaerfen_ist_ein_klick(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        zid = _neuer_zugang(c)
        c.post(f"/api/elster/zugaenge/{zid}/zertifikat", json={"inhalt_b64": _PFX})
        c.post(f"/api/elster/zugaenge/{zid}/pin", json={"pin": "PIN-1"})
        c.post(f"/api/elster/zugaenge/{zid}/scharf")
        assert _verbunden(c) == 1
        assert c.delete(f"/api/elster/zugaenge/{zid}/scharf").json() == {"ok": True, "scharf": False}
        assert _verbunden(c) == 0
        assert c.get(f"/api/elster/zugaenge/{zid}").json()["scharf"] is False


# --------------------------------------- Löschen räumt die Geheimnisse mit (DSGVO)

def test_zugang_loeschen_purged_pin_und_zertifikat(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        zid = _neuer_zugang(c)
        c.post(f"/api/elster/zugaenge/{zid}/zertifikat", json={"inhalt_b64": _PFX})
        c.post(f"/api/elster/zugaenge/{zid}/pin", json={"pin": "PIN-1"})
        pin_key = f"{v.PIN_VAULT_PREFIX}{zid}"
        ziel = app.state.db.db_path.parent / "elster" / f"{zid}.pfx"
        assert app.state.vault.get(pin_key) == "PIN-1" and ziel.exists()
        # Löschen ⇒ Vault-PIN + .pfx sind weg (weg = weg am Secret-Rand):
        assert c.delete(f"/api/elster/zugaenge/{zid}").json()["ok"]
        assert app.state.vault.get(pin_key) is None
        assert not ziel.exists()
