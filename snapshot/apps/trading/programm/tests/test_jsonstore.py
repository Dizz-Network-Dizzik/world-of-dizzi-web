"""Tests für jsonstore — atomares + crash-/korruptions-resilientes JSON-Speichern."""
import pytest

from backend.app import jsonstore


def test_write_atomic_roundtrip_and_bak(tmp_path):
    p = tmp_path / "s.json"
    jsonstore.write_atomic(p, {"a": 1})
    assert jsonstore.read_json(p, None) == {"a": 1}
    assert (tmp_path / "s.json.bak").exists()          # Recovery-Kopie angelegt
    assert not (tmp_path / "s.json.tmp").exists()       # tmp via os.replace aufgeräumt


def test_read_default_only_when_nothing_exists(tmp_path):
    assert jsonstore.read_json(tmp_path / "nope.json", {"d": True}) == {"d": True}


def test_read_falls_back_to_bak_on_corrupt_primary(tmp_path):
    p = tmp_path / "s.json"
    jsonstore.write_atomic(p, {"good": 1})              # erzeugt valides Ziel + .bak
    p.write_text("{ kaputt", encoding="utf-8")          # Primär korrumpieren (z. B. OneDrive-Konflikt)
    assert jsonstore.read_json(p, None) == {"good": 1}  # aus .bak gerettet


def test_read_raises_when_target_and_bak_unreadable(tmp_path):
    # Existiert eine Datei, ist aber unrettbar defekt → laut abbrechen statt still default (kein Datenverlust).
    p = tmp_path / "s.json"
    p.write_text("{ kaputt", encoding="utf-8")
    (tmp_path / "s.json.bak").write_text("auch kaputt", encoding="utf-8")
    with pytest.raises(RuntimeError):
        jsonstore.read_json(p, {})


def test_write_overwrites_atomically(tmp_path):
    p = tmp_path / "s.json"
    jsonstore.write_atomic(p, {"v": 1})
    jsonstore.write_atomic(p, {"v": 2})
    assert jsonstore.read_json(p, None) == {"v": 2}


def _oserr(winerror):
    # 4-Argument-Form (errno, strerror, filename, winerror) — nur so wird .winerror zuverlässig gesetzt
    # (mimt einen vom OS geworfenen Windows-Dateisperr-Fehler). errno egal für die Retry-Logik.
    return OSError(13, "simuliert", None, winerror)


def test_write_retries_on_transient_winerror(tmp_path, monkeypatch):
    # Simuliert eine transiente OneDrive/AV-Sperre (WinError 5) beim os.replace: die ersten 2 Versuche
    # scheitern, der 3. gelingt → write_atomic muss durch den Retry trotzdem erfolgreich sein.
    monkeypatch.setattr(jsonstore.time, "sleep", lambda *_: None)  # Test nicht ausbremsen
    real_replace = jsonstore.os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _oserr(5)
        return real_replace(src, dst)

    monkeypatch.setattr(jsonstore.os, "replace", flaky_replace)
    p = tmp_path / "s.json"
    jsonstore.write_atomic(p, {"ok": 1})
    assert calls["n"] == 3                       # 2× gescheitert, 3. erfolgreich
    assert jsonstore.read_json(p, None) == {"ok": 1}


def test_write_reraises_non_transient_error(tmp_path, monkeypatch):
    # Ein nicht-transienter Fehler (anderer WinError) wird NICHT wiederholt, sondern sofort durchgereicht.
    monkeypatch.setattr(jsonstore.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def hard_replace(src, dst):
        calls["n"] += 1
        raise _oserr(1337)                        # winerror 1337 ist nicht in der Retry-Liste

    monkeypatch.setattr(jsonstore.os, "replace", hard_replace)
    with pytest.raises(OSError):
        jsonstore.write_atomic(tmp_path / "s.json", {"x": 1})
    assert calls["n"] == 1                         # genau EIN Versuch (kein Retry)
