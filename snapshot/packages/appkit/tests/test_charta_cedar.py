"""Charta §B8 — Cedar-Schatten (§B7, dev): Übersetzung testbar ohne Cedar;
das Differential läuft nur mit installiertem Cedar-Paket (sonst skip)."""
import sys
from pathlib import Path

import pytest

# Das dev-Tool liegt bewusst außerhalb packages/ (CH-18) — Repo-Wurzel/tools.
_TOOLS = Path(__file__).resolve().parents[3] / "tools"
sys.path.insert(0, str(_TOOLS))

charta_cedar_schatten = pytest.importorskip("charta_cedar_schatten")

BEISPIEL = {"charta_version": "t", "artikel": [
    {"aktion": "fibu.buchen", "gewaehre": [[{"p": "rolle", "w": "buchhaltung"}]],
     "schranken": [{"wenn": [{"p": "bereich_fremd"}], "dann": ["verweigere"]}]}]}


def test_uebersetzung_erzeugt_permit_und_forbid():
    text = charta_cedar_schatten.nach_cedar(BEISPIEL)
    assert "permit(" in text and 'Action::"fibu.buchen"' in text
    assert "forbid(" in text                        # verweigere-Schranke ⇒ forbid


def test_antrag_kandidaten_deterministisch():
    a = list(charta_cedar_schatten.antrag_kandidaten(n=50))
    b = list(charta_cedar_schatten.antrag_kandidaten(n=50))
    assert len(a) == 50 and a == b                  # seeded ⇒ reproduzierbar


def test_differential_null_abweichungen():
    pytest.importorskip("cedarpy")                  # skip ohne Cedar-Paket (dev-extra)
    assert charta_cedar_schatten.differential(BEISPIEL, n=1000) == []
