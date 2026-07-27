"""RG-2b (docs/83 §5): kommapp speist den Ereignis-Spine.

Beweist am echten Sync-Pfad (FakeQuelle, runtime-frei): ein Posteingang-Sync legt
je NEUER Nachricht EIN ``mail_eingegangen``-Ereignis an — als ZEIGER (Konto/Kanal/
Ordner + nachricht-ref), NIE mit Betreff/Absender/Text. Ein zweiter Sync ohne neue
Mails erzeugt keine Dubletten. kommunikation ist ``hoechst`` ⇒ ``quelle_sens`` stimmt.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from kommapp.main import build_app
from kommapp.mail import KanalQuelle, OrdnerZustand


def _mail(betreff, mid, von="alice@example.org"):
    return {"kanal_typ": "email", "extern_id": mid, "von_adresse": von,
            "an_adressen": "dizzi@local", "betreff": betreff,
            "text": "GEHEIMER INHALT " + betreff, "gesendet_at": "2026-06-12",
            "thread_schluessel": mid}


class FakeQuelle(KanalQuelle):
    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:
            return ([_mail("Projekt", "<a@x>"),
                     _mail("Anderes", "<c@x>", von="carol@example.org")],
                    OrdnerZustand(2, 3))
        return ([], zustand)


def _client(tmp_path):
    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: FakeQuelle())
    return TestClient(app)


def _konto(c) -> str:
    return c.post("/api/konten", json={"name": "K", "host": "h",
                                       "benutzer": "u", "geheimnis": "g"}).json()["id"]


def test_sync_emittiert_mail_eingegangen_als_zeiger(tmp_path):
    with _client(tmp_path) as c:
        kid = _konto(c)
        c.post("/api/sync", json={"konto_id": kid})
        alle = c.get("/api/ereignisse").json()["eintraege"]
        eing = [e for e in alle if e["typ"] == "mail_eingegangen"]
        assert len(eing) == 2                       # je neue Nachricht ein Zeiger
        e = eing[0]
        assert e["payload"]["konto_id"] == kid
        assert e["payload"]["kanal_typ"] == "email"
        assert e["ref"].startswith("kommunikation:nachricht:")
        assert e["quelle_sens"] == "hoechst"        # kommapp ist höchst-sensibel
        # Zeiger, NIE Inhalt: kein Betreff/Absender/Text taucht im Spine auf.
        blob = json.dumps(alle)
        assert "GEHEIMER INHALT" not in blob
        assert "Projekt" not in blob and "alice@example.org" not in blob


def test_zweiter_sync_ohne_neue_keine_dubletten(tmp_path):
    with _client(tmp_path) as c:
        kid = _konto(c)
        c.post("/api/sync", json={"konto_id": kid})
        c.post("/api/sync", json={"konto_id": kid})   # uidnext>0 ⇒ 0 neue Mails
        eing = [e for e in c.get("/api/ereignisse").json()["eintraege"]
                if e["typ"] == "mail_eingegangen"]
        assert len(eing) == 2                          # keine Dubletten
