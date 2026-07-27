"""Paket D1 (1/4) — ChannelConnector-Schicht (channels.py) + /api/kanaele.

Konnektivitäts-Vision docs/35 §2: E-Mail ist der EINE aktive Kanal,
Telegram/WhatsApp/Instagram/Snapchat sind vorbereitete, DORMANTE Stecker
(Gesetz 5). Getestet wird die Schicht (Status/Versand-Dormanz) und die
Sichtbarkeit über /api/kanaele (inkl. Aktivitäts-Zähler + Mode-Schalter)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kommapp import channels
from kommapp.channels import (AusgehendeNachricht, EmailConnector,
                              KanalNichtVerbunden, connector_fuer, registry)
from kommapp.main import build_app


# ── Reine Schicht (ohne App) ──────────────────────────────────────────────────
def test_kanaele_reihenfolge_und_aktiv_flag():
    assert channels.KANAELE[0] == "email"
    assert set(channels.KANAELE) == {"email", "telegram", "whatsapp",
                                     "instagram", "snapchat"}
    reg = registry()
    assert reg["email"].aktiv is True
    assert all(reg[k].aktiv is False for k in channels.KANAELE if k != "email")


def test_email_connector_verbunden_und_sendet():
    gesendet = {}
    conn = EmailConnector(konto_vorhanden=lambda: True,
                          sende=lambda out: gesendet.update(an=out.an) or {"ok": True})
    assert conn.verbunden() is True
    erg = conn.senden(AusgehendeNachricht(an="x@y.z", text="hi"))
    assert erg == {"ok": True} and gesendet["an"] == "x@y.z"


def test_email_connector_ohne_konto_fail_closed():
    conn = EmailConnector(konto_vorhanden=lambda: False, sende=lambda out: {"ok": True})
    assert conn.verbunden() is False
    with pytest.raises(KanalNichtVerbunden):
        conn.senden(AusgehendeNachricht(an="x@y.z"))


@pytest.mark.parametrize("kanal", ["telegram", "whatsapp", "instagram", "snapchat"])
def test_dormante_kanaele_fail_closed(kanal):
    conn = connector_fuer(kanal)
    assert conn is not None and conn.verbunden() is False and conn.aktiv is False
    with pytest.raises(KanalNichtVerbunden):
        conn.senden(AusgehendeNachricht(an="@handle", kanal_typ=kanal))
    s = conn.status()
    assert s["weg"] and "appkit/connectors.py" in s["integration_punkt"]


def test_connector_fuer_unbekannt_none():
    assert connector_fuer("signaltelepathie") is None


def test_kanaele_status_email_aktiv_ohne_konto_nicht_verbunden():
    st = {s["kanal_typ"]: s for s in channels.kanaele_status(
        email_konto_vorhanden=lambda: False)}
    assert st["email"]["aktiv"] is True and st["email"]["verbunden"] is False
    assert st["telegram"]["aktiv"] is False


# ── Über die App (/api/kanaele) ───────────────────────────────────────────────
def test_api_kanaele_zeigt_alle_kanaele(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        ks = client.get("/api/kanaele").json()
        typen = [k["kanal_typ"] for k in ks]
        assert typen == list(channels.KANAELE)         # Reihenfolge stabil
        email = next(k for k in ks if k["kanal_typ"] == "email")
        assert email["aktiv"] is True and email["verbunden"] is False  # noch kein Konto
        for k in ks:
            assert "nachrichten" in k and "kontakte" in k


def test_api_kanaele_email_verbunden_nach_konto(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        client.post("/api/konten", json={
            "name": "K", "host": "imap.example.org", "benutzer": "d@example.org",
            "geheimnis": "pw", "smtp_host": "smtp.example.org"})
        email = next(k for k in client.get("/api/kanaele").json()
                     if k["kanal_typ"] == "email")
        assert email["verbunden"] is True             # sendefähiges SMTP-Konto da


def test_api_kanaele_mode_schalter_sichtbar(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        tele = next(k for k in client.get("/api/kanaele").json()
                    if k["kanal_typ"] == "telegram")
        assert tele["modus_setting"] == "bridge_telegram_vorbereitet"
        assert tele["modus_an"] is False              # Default aus
