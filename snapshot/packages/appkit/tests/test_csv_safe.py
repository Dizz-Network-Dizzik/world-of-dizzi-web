"""CSV-Formel-Injection-Schutz (Audit-Runde 3)."""

from __future__ import annotations

from appkit.csv_safe import csv_safe


def test_entschaerft_formel_praefixe():
    for p in ("=", "+", "-", "@", "\t", "\r"):
        out = csv_safe(p + "SUM(A1)")
        assert out.startswith("'" + p)        # führender Apostroph, sichtbarer Text bleibt
        assert out[1:] == p + "SUM(A1)"


def test_harmlose_werte_unveraendert():
    assert csv_safe("REWE Einkauf") == "REWE Einkauf"
    assert csv_safe("2026-01-01") == "2026-01-01"
    assert csv_safe("Konto 12") == "Konto 12"


def test_none_und_zahlen():
    assert csv_safe(None) == ""
    assert csv_safe(123) == "123"
    assert csv_safe("") == ""
