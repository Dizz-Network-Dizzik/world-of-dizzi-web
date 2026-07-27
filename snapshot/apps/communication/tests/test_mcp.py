"""MCP-Fläche geschärft: der MCP-Host (Dizzis KI, ggf. Cloud-Boost) bekommt für
die hoechst-App NUR Metadaten/Zähler — niemals Nachrichten-Volltexte. Die
dedizierten /api/mcp/*-Endpoints garantieren das; /api/posteingang (mit Text)
ist bewusst KEINE MCP-Quelle."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp.main import build_app
from kommapp.mail import KanalQuelle, OrdnerZustand

_VOLLTEXT = "VERTRAULICHER VOLLTEXT der privaten Nachricht"


class FakeQuelle(KanalQuelle):
    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:
            return ([{"kanal_typ": "email", "extern_id": "<a@x>",
                      "von_adresse": "alice@example.org", "an_adressen": "d@local",
                      "betreff": "Geheim Betreff", "text": _VOLLTEXT,
                      "gesendet_at": "2026-06-12", "thread_schluessel": "<a@x>"}],
                    OrdnerZustand(2, 3))
        return ([], zustand)


def _client(tmp_path):
    return TestClient(build_app(
        data_dir=tmp_path, quelle_factory=lambda konto, geheimnis: FakeQuelle()))


def test_mcp_metadaten_ohne_volltext(tmp_path):
    with _client(tmp_path) as c:
        kid = c.post("/api/konten", json={
            "name": "Privat", "host": "h", "benutzer": "u",
            "geheimnis": "g"}).json()["id"]
        c.post("/api/sync", json={"konto_id": kid})

        letzte = c.get("/api/mcp/letzte_nachrichten")
        daten = letzte.json()
        assert daten and daten[0]["betreff"] == "Geheim Betreff"
        # KERN-GARANTIE: keine Volltexte über die MCP-Fläche.
        assert all("text" not in m for m in daten)
        assert _VOLLTEXT not in letzte.text

        ung = c.get("/api/mcp/ungelesen").json()
        assert ung["gesamt"] == 1
        assert ung["je_konto"][0]["konto_id"] == kid
        assert ung["je_konto"][0]["ungelesen"] == 1

        # Kontrast: der LOKALE Posteingang trägt den Volltext (nur für die App,
        # nicht als MCP-Tool exponiert).
        assert _VOLLTEXT in c.get("/api/posteingang").text


def test_manifest_mcp_tools_sind_metadaten(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as c:
        tools = c.get("/api/manifest").json()["mcp"]["tools"]
        assert {"posteingang_uebersicht", "ungelesen", "letzte_nachrichten"} <= set(tools)
        assert "posteingang" not in tools     # das alte Volltext-Tool ist entfernt
        assert "mail_senden_vorschlagen" in tools   # einziges Aktions-Tool (HITL)


def test_mcp_aktion_ist_hitl_und_fail_closed(tmp_path):
    """Das MCP-Aktions-Tool mail_senden_vorschlagen ruft genau POST
    /api/actions/propose (source=mcp). Es legt NUR einen Vorschlag an; die
    Freigabe bleibt menschlich (verifiziert) und standalone fail-closed (403) —
    der MCP führt nie selbst aus. Hier die Endpoint-Garantie dahinter."""
    with _client(tmp_path) as c:
        kid = c.post("/api/konten", json={
            "name": "V", "host": "h", "benutzer": "u", "geheimnis": "g",
            "smtp_host": "smtp.h"}).json()["id"]
        v = c.post("/api/actions/propose", json={
            "name": "mail_senden", "source": "mcp",
            "params": {"konto_id": kid, "an": "z@example.org"}}).json()
        assert v["status"] == "pending" and v["level"] == "verifiziert"
        eintrag = next(a for a in c.get("/api/actions").json()["liste"]
                       if a["id"] == v["id"])
        assert eintrag["source"] == "mcp"
        assert c.post(f"/api/actions/{v['id']}/approve").status_code == 403
