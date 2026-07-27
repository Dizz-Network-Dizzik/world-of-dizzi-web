from app import db


def test_setting_roundtrip():
    db.setting_put("dizzi", "theme", {"mode": "metal"})
    assert db.setting_get("dizzi", "theme") == {"mode": "metal"}


def test_setting_update_keeps_unique():
    db.setting_put("dizzi", "lang", "de")
    db.setting_put("dizzi", "lang", "en")
    assert db.setting_get("dizzi", "lang") == "en"
    assert list(db.settings_all("dizzi")) == ["lang"]


def test_settings_user_scoped():
    db.setting_put("dizzi", "lang", "de")
    db.setting_put("gast", "lang", "en")
    assert db.setting_get("dizzi", "lang") == "de"
    assert db.setting_get("gast", "lang") == "en"


def test_setting_default():
    assert db.setting_get("dizzi", "fehlt", default=42) == 42


def test_audit_log():
    db.audit("dizzi", "ki", "test_action", {"x": 1})
    entries = db.audit_recent("dizzi")
    assert entries[0]["action"] == "test_action"
    assert entries[0]["actor"] == "ki"
    assert entries[0]["detail"] == {"x": 1}
