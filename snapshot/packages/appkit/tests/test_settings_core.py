"""Tests K2: typisiertes Settings-Schema, Maskierung, Account, Token-Tresor."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from appkit.app import create_app
from appkit.db import Database
from appkit.manifest import AppManifest
from appkit.settings_core import SettingDef, make_schema
from appkit.summary import Kpi
from appkit.vault import Vault


def _app(tmp_path, sensitivity="normal", extra=None):
    manifest = AppManifest(id="k2app", name="K2-App", brand="Dizz K2",
                           version="0.1.0", port=8299, sensitivity=sensitivity)
    db = Database(tmp_path / "k2.sqlite")
    schema = make_schema(extra=extra, sensitivity=sensitivity)
    return create_app(manifest, db,
                      summary_fn=lambda: [Kpi(id="n", label="N", value=1)],
                      schema=schema)


def test_defaults_und_validierung(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        s = c.get("/api/settings").json()
        assert s["theme"] == "neon_dunkel" and s["sprache"] == "de"
        assert s["ki_routing"] == "lokal_boost"           # normal ⇒ Boost erlaubt

        # Choice-Verstoß, Typ-Verstoß, Grenz-Verstoß ⇒ 400
        assert c.put("/api/settings", json={"key": "theme", "value": "pink"}).status_code == 400
        assert c.put("/api/settings", json={"key": "backup_aktiv", "value": "ja"}).status_code == 400
        assert c.put("/api/settings", json={"key": "auto_logout_min", "value": 1}).status_code == 400

        assert c.put("/api/settings", json={"key": "theme", "value": "neon_hell"}).status_code == 200
        assert c.get("/api/settings").json()["theme"] == "neon_hell"


def test_k22_design_achsen(tmp_path):
    """K2.2: die zwei getrennten Design-Achsen sind typisiert vorhanden, mit
    den Token-Vertrag-Werten (ui-kit/tokens.css), Defaults und strikter Choice-
    Validierung — und die freien x_-Schlüssel bleiben unberührt nutzbar."""
    app = _app(tmp_path)
    with TestClient(app) as c:
        schema = c.get("/api/settings/schema").json()
        darstellung = {d["key"]: d for d in schema["kategorien"]["darstellung"]}
        # K2.2-b Katalog v1.1 (Nutzer-Feedback): 10 Design-Themes × 10 Farbschemata
        assert darstellung["design_vorlage"]["choices"] == \
            ["metall", "neon", "flach", "tag", "carbon", "pergament",
             "synthwave", "lagune", "inferno", "kobalt"]
        assert darstellung["farb_schema"]["choices"] == \
            ["cyan-magenta", "smaragd-gold", "violett-eis", "bernstein", "arktis",
             "koralle", "limette", "feuer", "toxic", "voltage"]

        s = c.get("/api/settings").json()
        assert s["design_vorlage"] == "metall"            # WoD-Mattstahl = Default
        assert s["farb_schema"] == "cyan-magenta"

        # gültige Wahl greift, ungültige ⇒ 400 (kein Mapping, exakt die Token-Werte)
        assert c.put("/api/settings",
                     json={"key": "design_vorlage", "value": "neon"}).status_code == 200
        assert c.put("/api/settings",
                     json={"key": "farb_schema", "value": "violett-eis"}).status_code == 200
        assert c.put("/api/settings",
                     json={"key": "farb_schema", "value": "neon-pink"}).status_code == 400
        s2 = c.get("/api/settings").json()
        assert s2["design_vorlage"] == "neon" and s2["farb_schema"] == "violett-eis"

        # der freie Namensraum bleibt parallel nutzbar (Übergangs-Persistenz)
        assert c.put("/api/settings",
                     json={"key": "x_farb_schema", "value": "irgendwas"}).status_code == 200


def test_sensible_apps_starten_lokal_only(tmp_path):
    app = _app(tmp_path, sensitivity="hoechst")
    with TestClient(app) as c:
        assert c.get("/api/settings").json()["ki_routing"] == "lokal_only"


def test_sensitive_setting_wird_maskiert(tmp_path):
    extra = [SettingDef(key="dienst_token_hinweis", category="vernetzung",
                        type="str", default=None, sensitive=True,
                        label="Dienst-Hinweis (write-only)")]
    app = _app(tmp_path, extra=extra)
    with TestClient(app) as c:
        c.put("/api/settings", json={"key": "dienst_token_hinweis", "value": "geheim!"})
        assert c.get("/api/settings").json()["dienst_token_hinweis"] == "•••"


def test_account_uebersicht(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        c.put("/api/settings", json={"key": "anzeigename", "value": "dizzi prime"})
        acc = c.get("/api/account").json()
        assert acc["profil"]["anzeigename"] == "dizzi prime"
        assert acc["identitaet"]["level"] == "lokal"      # standalone vor Login
        assert acc["sso"]["sso"] == "dizzi-id"


def test_vault_roundtrip_verschluesselt_und_api(tmp_path):
    v = Vault(tmp_path / "appdata")
    v.put("bitget_key", "SECRET-123")
    assert v.get("bitget_key") == "SECRET-123"
    assert v.names() == ["bitget_key"]
    raw = (tmp_path / "appdata" / "vault.dat").read_bytes()
    assert b"SECRET-123" not in raw                       # wirklich verschlüsselt
    assert v.delete("bitget_key") is True and v.names() == []

    app = _app(tmp_path)
    with TestClient(app) as c:
        c.put("/api/vault", json={"name": "google_token", "value": "tok-xyz"})
        assert c.get("/api/vault").json() == ["google_token"]   # NUR Namen
        assert "tok-xyz" not in c.get("/api/account").text      # Wert nirgends
        actions = [e["action"] for e in c.get("/api/audit").json()]
        assert "vault_eintrag_gesetzt" in actions
        assert c.delete("/api/vault/google_token").json()["ok"] is True


def test_schema_doppelte_keys_verboten():
    with pytest.raises(ValueError):
        make_schema(extra=[SettingDef(key="theme", category="darstellung",
                                      type="str", default="x")])
