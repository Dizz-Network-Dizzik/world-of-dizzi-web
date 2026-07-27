"""Mem-Live-Pull: getaktete Import-Automatik. Getestet wird der Durchlauf
(`app.state.auto_import`) deterministisch (ohne Daemon-Thread/Timing): Default
AUS, Ziehen + Dedupe aus freigegebenen Env-Ordnern, kein Self-Import des Daten-Roots."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from archivapp import main as am


def _schreib(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_auto_import_default_aus_und_im_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("DIZZ_MEMORY_IMPORT_DIRS", "")
    app = am.build_app(data_dir=tmp_path, start_import_timer=False)
    with TestClient(app) as c:
        kat = c.get("/api/settings/schema").json()["kategorien"]["daten"]
        keys = {d["key"] for d in kat}
        assert {"auto_import_aktiv", "auto_import_intervall_min"} <= keys
        s = c.get("/api/settings").json()
        assert s["auto_import_aktiv"] is False and s["auto_import_intervall_min"] == 30
        # Intervall-Validierung (min 5)
        assert c.put("/api/settings", json={"key": "auto_import_intervall_min", "value": 2}).status_code == 400
    # Default AUS ⇒ Durchlauf ist ein No-op
    assert app.state.auto_import()["aktiv"] is False


def test_auto_import_zieht_und_dedupt(tmp_path, monkeypatch):
    quelle = tmp_path / "extern"
    _schreib(quelle / "a.md", "---\ntitel: Extern A\n---\n\nInhalt a mit Findwort gibbon.")
    _schreib(quelle / "Unter" / "b.md", "---\ntitel: Extern B\n---\n\nInhalt b im Unterordner.")
    monkeypatch.setenv("DIZZ_MEMORY_IMPORT_DIRS", str(quelle))
    app = am.build_app(data_dir=tmp_path, start_import_timer=False)
    with TestClient(app) as c:
        c.put("/api/settings", json={"key": "auto_import_aktiv", "value": True})
        r1 = app.state.auto_import()
        assert r1["aktiv"] and r1["importiert"] == 2 and r1["ordner"] == 1
        # zweiter Durchlauf: identische Dateien ⇒ Dedupe (SHA-256)
        assert app.state.auto_import()["importiert"] == 0
        titel = {n["titel"] for n in c.get("/api/notizen").json()}
        assert {"Extern A", "Extern B"} <= titel
        assert "Unter" in {o["name"] for o in c.get("/api/ordner").json()}
        # neue Datei ⇒ wird beim nächsten Lauf gezogen
        _schreib(quelle / "c.md", "---\ntitel: Extern C\n---\n\nNeu hinzugekommen.")
        assert app.state.auto_import()["importiert"] == 1


def test_auto_import_scannt_nicht_den_datenroot(tmp_path, monkeypatch):
    """Ohne freigegebene Env-Ordner scannt die Automatik NICHTS — insbesondere
    nicht den Daten-Root (sonst re-importierte sie den eigenen Vault)."""
    monkeypatch.setenv("DIZZ_MEMORY_IMPORT_DIRS", "")
    app = am.build_app(data_dir=tmp_path, start_import_timer=False)
    with TestClient(app) as c:
        c.post("/api/notizen", json={"titel": "Eigene Notiz", "inhalt": "im Vault"})
        c.put("/api/settings", json={"key": "auto_import_aktiv", "value": True})
        r = app.state.auto_import()
        assert r["aktiv"] and r["importiert"] == 0 and r["ordner"] == 0
        # Bestand unverändert (kein Self-Import)
        assert len(c.get("/api/notizen").json()) == 1
