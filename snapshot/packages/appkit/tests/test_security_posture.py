"""SF-1 — Sicherheits-Ampel (docs/82 §3): Magie-Byte-Checks, fail-closed,
Aggregation, Route. Alles rein lesend + ohne echte OS-Abhängigkeit (BitLocker-
Subprozess gemockt, Plattform-Zweige monkeypatchbar)."""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient

from appkit import auth, security_posture as sp
from appkit.app import create_app
from appkit.db import Database
from appkit.manifest import AppManifest


def _manifest(**over) -> AppManifest:
    base = dict(id="testapp", name="Test-App", brand="Dizz Test",
                version="0.1.0", port=8299, sensitivity="normal")
    base.update(over)
    return AppManifest(**base)


def _db(tmp_path) -> Database:
    return Database(tmp_path / "test.sqlite")


@pytest.fixture(autouse=True)
def _clean_auth():
    auth.reset_identity_provider()
    yield
    auth.reset_identity_provider()


# --- Aggregation: gesamt = schlechtester (unbekannt ≈ gelb) --------------------------

def test_aggregation_schlechtester_gewinnt():
    assert sp._schlechtester([sp.GRUEN, sp.GRUEN]) == sp.GRUEN
    assert sp._schlechtester([sp.GRUEN, sp.GELB]) == sp.GELB
    assert sp._schlechtester([sp.GELB, sp.ROT]) == sp.ROT
    assert sp._schlechtester([sp.GRUEN, sp.UNBEKANNT]) == sp.UNBEKANNT
    # gelb UND unbekannt ⇒ gelb ist die aussagekräftigere Farbe
    assert sp._schlechtester([sp.UNBEKANNT, sp.GELB]) == sp.GELB
    # rot sticht alles
    assert sp._schlechtester([sp.ROT, sp.UNBEKANNT, sp.GRUEN]) == sp.ROT
    assert sp._schlechtester([]) == sp.UNBEKANNT


# --- db_at_rest: Klartext-Magie erkennen, Sensibilität skaliert die Schwere ----------

def test_db_at_rest_klartext_hoechst_ist_rot(tmp_path):
    p = tmp_path / "k.sqlite"
    p.write_bytes(sp._SQLITE_MAGIC + b"restdaten")
    zustand, befund, _ = sp._check_db_at_rest(p, "hoechst")
    assert zustand == sp.ROT and "UNVERSCHLÜSSELT" in befund


def test_db_at_rest_klartext_hoch_ist_gelb(tmp_path):
    p = tmp_path / "k.sqlite"
    p.write_bytes(sp._SQLITE_MAGIC + b"x")
    assert sp._check_db_at_rest(p, "hoch")[0] == sp.GELB


def test_db_at_rest_verschluesselt_ist_gruen(tmp_path):
    p = tmp_path / "e.sqlite"
    p.write_bytes(b"\x9f\x3a" + b"verschluesselter-block")   # KEINE SQLite-Magie
    assert sp._check_db_at_rest(p, "hoechst")[0] == sp.GRUEN


def test_db_at_rest_fehlend_ist_gruen(tmp_path):
    # noch keine DB ⇒ keine ruhenden Klartext-Daten (nicht alarmieren)
    assert sp._check_db_at_rest(tmp_path / "fehlt.sqlite", "hoechst")[0] == sp.GRUEN


# --- vault_schluessel: OS-Schloss vs Klartext ---------------------------------------

def test_vault_dpapi_ist_gruen(tmp_path):
    (tmp_path / "vault.key").write_bytes(sp._DPAPI_MAGIC + b"blob")
    assert sp._check_vault_schluessel(tmp_path)[0] == sp.GRUEN


def test_vault_oskey_ist_gruen(tmp_path):
    (tmp_path / "vault.key").write_bytes(sp._OSKEY_MAGIC + b"token")
    assert sp._check_vault_schluessel(tmp_path)[0] == sp.GRUEN


def test_vault_klartext_auf_windows_ist_rot(tmp_path, monkeypatch):
    (tmp_path / "vault.key").write_bytes(b"gAAAAAB-klartext-fernet-key")
    monkeypatch.setattr(sp.sys, "platform", "win32")
    zustand, befund, _ = sp._check_vault_schluessel(tmp_path)
    assert zustand == sp.ROT and "KLARTEXT" in befund


def test_vault_klartext_nicht_windows_ist_gelb(tmp_path, monkeypatch):
    (tmp_path / "vault.key").write_bytes(b"klartext")
    monkeypatch.setattr(sp.sys, "platform", "linux")
    assert sp._check_vault_schluessel(tmp_path)[0] == sp.GELB


def test_vault_fehlend_ist_gruen(tmp_path):
    assert sp._check_vault_schluessel(tmp_path)[0] == sp.GRUEN


# --- backup_crypto: Slot-Präsenz -----------------------------------------------------

def test_backup_slot_gesetzt_ist_gruen(tmp_path):
    slot = tmp_path / "pass.bin"
    slot.write_bytes(b"DPAPI1\ngewickelt")
    assert sp._check_backup_crypto(slot)[0] == sp.GRUEN


def test_backup_slot_fehlt_ist_gelb(tmp_path):
    assert sp._check_backup_crypto(tmp_path / "kein_slot.bin")[0] == sp.GELB


# --- auto_lock: SF-6 folgt noch ------------------------------------------------------

def test_auto_lock_none_ist_unbekannt():
    zustand, befund, _ = sp._check_auto_lock(None, "hoch")
    assert zustand == sp.UNBEKANNT and "SF-6" in befund


def test_auto_lock_aktiv_ist_gruen():
    assert sp._check_auto_lock(15, "hoechst")[0] == sp.GRUEN


def test_auto_lock_aus_bei_hoch_ist_gelb():
    assert sp._check_auto_lock(0, "hoch")[0] == sp.GELB


def test_auto_lock_aus_bei_normal_ist_gruen():
    assert sp._check_auto_lock(0, "normal")[0] == sp.GRUEN


# --- fde: BitLocker-Subprozess gemockt ----------------------------------------------

def _mock_ps(monkeypatch, *, stdout="", returncode=0, exc=None):
    def fake_run(*a, **k):
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(a, returncode, stdout=stdout, stderr="")
    monkeypatch.setattr(sp.sys, "platform", "win32")
    monkeypatch.setattr(sp.subprocess, "run", fake_run)


def test_fde_an_ist_gruen(tmp_path, monkeypatch):
    _mock_ps(monkeypatch, stdout="On\n")
    assert sp._check_fde(tmp_path)[0] == sp.GRUEN


def test_fde_aus_ist_rot(tmp_path, monkeypatch):
    _mock_ps(monkeypatch, stdout="Off\n")
    zustand, befund, _ = sp._check_fde(tmp_path)
    assert zustand == sp.ROT and "NICHT verschlüsselt" in befund


def test_fde_keine_rechte_ist_unbekannt(tmp_path, monkeypatch):
    _mock_ps(monkeypatch, stdout="", returncode=1)
    assert sp._check_fde(tmp_path)[0] == sp.UNBEKANNT


def test_fde_timeout_ist_unbekannt(tmp_path, monkeypatch):
    _mock_ps(monkeypatch, exc=subprocess.TimeoutExpired("powershell", 3.0))
    assert sp._check_fde(tmp_path)[0] == sp.UNBEKANNT


def test_fde_nicht_windows_ist_unbekannt(tmp_path, monkeypatch):
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    zustand, _, empfehlung = sp._check_fde(tmp_path)
    assert zustand == sp.UNBEKANNT and "FileVault" in empfehlung


# --- fail-closed: ein werfender Check ⇒ unbekannt, nie Crash -------------------------

def test_lauf_faengt_ausnahme_zu_unbekannt():
    def boom():
        raise RuntimeError("kaputt")
    ergebnis = sp._lauf("fde", boom)
    assert ergebnis["zustand"] == sp.UNBEKANNT
    assert "RuntimeError" in ergebnis["befund"]
    assert ergebnis["id"] == "fde" and ergebnis["titel"]


# --- pruefe_lage: Vollstruktur + Gesamt ---------------------------------------------

def test_pruefe_lage_struktur_und_gesamt(tmp_path, monkeypatch):
    monkeypatch.setattr(sp.sys, "platform", "linux")     # fde ⇒ unbekannt (deterministisch)
    (tmp_path / "test.sqlite").write_bytes(sp._SQLITE_MAGIC + b"x")  # Klartext-DB
    lage = sp.pruefe_lage("healthy", tmp_path / "test.sqlite", tmp_path, "hoechst",
                          autolock_minuten=None, backup_slot=tmp_path / "kein.bin")
    assert lage["app"] == "healthy"
    assert lage["gesamt"] == sp.ROT                       # höchst + Klartext-DB
    assert lage["geprueft_am"]
    ids = {c["id"] for c in lage["checks"]}
    assert ids == {"fde", "db_at_rest", "vault_schluessel", "backup_crypto", "auto_lock"}
    for c in lage["checks"]:
        assert set(c) == {"id", "titel", "zustand", "befund", "empfehlung"}
        assert c["zustand"] in (sp.GRUEN, sp.GELB, sp.ROT, sp.UNBEKANNT)


def test_pruefe_lage_wirft_nie_bei_kaputten_pfaden():
    # Unsinnige Pfade dürfen NIE eine Ausnahme durchreichen (fail-closed).
    lage = sp.pruefe_lage("x", "/nicht/existent/\0/db", "/auch/nicht", "normal")
    assert lage["gesamt"] in (sp.GRUEN, sp.GELB, sp.ROT, sp.UNBEKANNT)
    assert len(lage["checks"]) == 5


# --- Route: erreichbar im Standalone (Stufe 'lokal'), korrekte Struktur --------------

def test_route_lage_im_standalone_erreichbar(tmp_path, monkeypatch):
    monkeypatch.setattr(sp.sys, "platform", "linux")
    app = create_app(_manifest(sensitivity="hoch"), _db(tmp_path),
                     summary_fn=lambda: [])
    client = TestClient(app)
    r = client.get("/api/sicherheit/lage")
    assert r.status_code == 200                           # NICHT 403 (Stufe lokal reicht)
    body = r.json()
    assert body["app"] == "testapp"
    assert body["gesamt"] in (sp.GRUEN, sp.GELB, sp.ROT, sp.UNBEKANNT)
    assert len(body["checks"]) == 5


def test_route_lage_liest_autolock_setting(tmp_path, monkeypatch):
    monkeypatch.setattr(sp.sys, "platform", "linux")
    db = _db(tmp_path)
    db.setting_put(auth.DEFAULT_USER_ID, sp.AUTOLOCK_SETTING, 20)
    app = create_app(_manifest(), db, summary_fn=lambda: [])
    r = TestClient(app).get("/api/sicherheit/lage")
    auto = next(c for c in r.json()["checks"] if c["id"] == "auto_lock")
    assert auto["zustand"] == sp.GRUEN and "20" in auto["befund"]


def test_route_abschaltbar(tmp_path):
    app = create_app(_manifest(), _db(tmp_path), summary_fn=lambda: [],
                     sicherheit=False)
    assert TestClient(app).get("/api/sicherheit/lage").status_code == 404
