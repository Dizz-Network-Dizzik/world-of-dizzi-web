"""Tests für die atomaren Datei-Schreibvorgänge (docs/50 P1.2)."""
from __future__ import annotations

import os

import pytest

from appkit.io_safe import atomic_write_bytes, atomic_write_text


def test_write_bytes_und_text(tmp_path):
    ziel = tmp_path / "unter" / "datei.bin"
    atomic_write_bytes(ziel, b"hallo")
    assert ziel.read_bytes() == b"hallo"
    t = tmp_path / "text.md"
    atomic_write_text(t, "äöü € test")
    assert t.read_text(encoding="utf-8") == "äöü € test"


def test_ueberschreiben_atomar(tmp_path):
    ziel = tmp_path / "x.txt"
    atomic_write_text(ziel, "alt")
    atomic_write_text(ziel, "neu")
    assert ziel.read_text(encoding="utf-8") == "neu"


def test_fehler_laesst_ziel_unberuehrt_und_raeumt_temp(tmp_path, monkeypatch):
    ziel = tmp_path / "wichtig.txt"
    atomic_write_text(ziel, "bestand")

    def boom(_a, _b):                       # simuliert Platte-voll beim finalen replace
        raise OSError("kein Platz auf dem Gerät")
    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError):
        atomic_write_bytes(ziel, b"neuer inhalt")

    assert ziel.read_text(encoding="utf-8") == "bestand"        # alte Version intakt
    reste = [p for p in tmp_path.iterdir() if p.name.startswith(".wichtig.txt.")]
    assert reste == []                                          # kein Temp-Leichnam
