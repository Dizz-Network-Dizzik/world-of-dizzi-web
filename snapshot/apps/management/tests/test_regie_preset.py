"""RG-7 (docs/83 §5.6/§5): Ton-Preset + VIP-Liste je Bereich (``agenten_preset``).

Reine Helfer (fail-closed saniert, kein Seiteneffekt) + der GET/PUT-Endpoint. Der Ton-Text
speist den Antwort-Entwurf-Zünd-Kontext, ``ist_vip`` die Eskalations-Weiche — die LIVE-
Einspeisung in den Core-Lauf ist gegatet (G-REGIE-LIVE), hier zählt Speicher + Logik.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from managementapp import agenten_preset as ap
from managementapp import main as mm


def _client(tmp_path) -> TestClient:
    return TestClient(mm.build_app(data_dir=tmp_path))


# --- Reine Helfer -----------------------------------------------------------

def test_ton_preset_text_traegt_ton_und_verbote():
    t = ap.ton_preset_text({"sprache": "de", "anrede": "Hallo", "signatur": "— David",
                            "verbote": ["keine Zusagen"]})
    assert "Sprache: de" in t and "Hallo" in t and "— David" in t
    assert "VERBOTEN im Entwurf: keine Zusagen." in t


def test_ton_preset_text_default_verbote_wenn_leer():
    t = ap.ton_preset_text({})
    assert "keine Preis-Zusagen" in t and "keine Anhänge versprechen" in t


def test_saniere_ton_default_und_deckel():
    p = ap.saniere_ton({})
    assert p["sprache"] == "de" and p["verbote"] == list(ap.STANDARD_VERBOTE)
    p2 = ap.saniere_ton({"sprache": "en", "signatur": "x" * 999, "verbote": ["a" * 200]})
    assert p2["sprache"] == "en" and len(p2["signatur"]) <= 500
    assert len(p2["verbote"][0]) <= 120


def test_saniere_vip_parseaddr_lowercase_dedupe():
    assert ap.saniere_vip(["A@X.de", "a@x.de", "Name <b@y.de>", "  ", ""]) \
        == ["a@x.de", "b@y.de"]


def test_ist_vip_case_insensitive_und_leer():
    vip = ["chef@firma.de"]
    assert ap.ist_vip(vip, "Chef <CHEF@Firma.de>") is True
    assert ap.ist_vip(vip, "fremd@x.de") is False
    assert ap.ist_vip([], "chef@firma.de") is False


# --- Endpoint (GET/PUT je Bereich) ------------------------------------------

def test_preset_default_ist_sicher(tmp_path):
    with _client(tmp_path) as c:
        d = c.get("/api/regie/preset").json()
        assert d["gesetzt"] is False
        assert d["ton_preset"]["sprache"] == "de"
        assert "keine Preis-Zusagen" in d["ton_preset"]["verbote"]
        assert d["vip_liste"] == []


def test_preset_setzen_und_lesen_saniert(tmp_path):
    with _client(tmp_path) as c:
        r = c.put("/api/regie/preset", json={
            "ton_preset": {"sprache": "de", "anrede": "Hallo", "signatur": "— David",
                           "verbote": ["keine Zusagen"]},
            "vip_liste": ["VIP <chef@firma.de>", "chef@firma.de", "  "]}).json()
        assert r["ok"] is True
        assert r["vip_liste"] == ["chef@firma.de"]           # parseaddr + dedupe + leer weg
        g = c.get("/api/regie/preset").json()
        assert g["gesetzt"] is True and g["ton_preset"]["anrede"] == "Hallo"
        assert g["ton_preset"]["verbote"] == ["keine Zusagen"]


def test_preset_je_bereich_getrennt(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/regie/preset?bereich_id=marke_a",
              json={"ton_preset": {"anrede": "Servus"}, "vip_liste": []})
        assert c.get("/api/regie/preset?bereich_id=marke_a").json()["ton_preset"]["anrede"] \
            == "Servus"
        # Ein anderer Bereich bleibt beim Default (getrennt gespeichert):
        assert c.get("/api/regie/preset?bereich_id=marke_b").json()["gesetzt"] is False
