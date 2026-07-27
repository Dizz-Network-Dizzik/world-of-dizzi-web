"""P0 — Connector-Katalog (Gesetz 5): umfangreiche dormante Dienst-Slots im
/api/konnektoren neben den aktiven Adaptern (E-Mail/WhatsApp/Instagram/Telegram).
Ehrliche Aktivierungs-Pfade; KEINE Plattform-Calls; keine doppelten IDs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp import connectors_katalog
from kommapp.main import build_app


def test_katalog_liefert_dormante_slots():
    cs = {c.id: c for c in connectors_katalog.dormante_konnektoren()}
    for erwartet in ("facebook_messenger", "threads", "x_twitter", "linkedin",
                     "slack", "discord", "signal", "sms_rcs", "matrix", "snapchat"):
        assert erwartet in cs
    # alle dormant + ehrlicher Aktivierungs-Pfad
    for c in cs.values():
        assert c.verfuegbar() is False and c.aktivierung
    # Snapchat ist ehrlich „kein offener API-Pfad"
    assert "KEIN offener" in cs["snapchat"].aktivierung or "Webview" in cs["snapchat"].aktivierung


def test_api_konnektoren_zeigt_katalog_und_aktive(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        d = client.get("/api/konnektoren").json()
        ids = {c["id"] for c in d["konnektoren"]}
        # aktive Adapter weiterhin da
        assert {"whatsapp", "instagram", "telegram"} <= ids
        # Katalog-Slots ergänzt
        assert {"x_twitter", "linkedin", "slack", "discord", "signal",
                "facebook_messenger", "snapchat", "matrix", "sms_rcs", "threads"} <= ids
        # dormante Slots: nicht verbunden, mit Hinweis (Aktivierungs-Pfad)
        x = next(c for c in d["konnektoren"] if c["id"] == "x_twitter")
        assert x["verbunden"] is False and x["dormant"] is True and x["hinweis"]
        assert d["verbunden"] == 0                      # ohne Tokens alles dormant
