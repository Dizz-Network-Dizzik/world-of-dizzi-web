"""Tests Dizz Admin — Demo-Seed für den Bereichs-Cockpit-Feel-Check (D2 Punkt 3).
Der Seed (tools/seed_demo_cockpit.seed) ist duck-typed auf einen httpx-/TestClient.
Lauf: pytest tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from adminapp import main as am

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import seed_demo_cockpit as seed_mod  # noqa: E402


def _client(tmp_path) -> TestClient:
    return TestClient(am.build_app(data_dir=tmp_path))


def test_seed_legt_demo_bereich_mit_kontexten_an(tmp_path):
    with _client(tmp_path) as c:
        erg = seed_mod.seed(c)
        assert erg["status"] == "angelegt"
        bid = erg["bereich_id"]
        b = c.get(f"/api/bereiche/{bid}").json()
        assert b["money_kontext"] == seed_mod.MONEY_KONTEXT
        assert b["management_kontext"] == seed_mod.MGMT_KONTEXT
        assert b["memory_ref"] == seed_mod.MEMORY_REF


def test_seed_finanz_und_module_im_bereich(tmp_path):
    with _client(tmp_path) as c:
        erg = seed_mod.seed(c)
        bid = erg["bereich_id"]
        rs = c.get(f"/api/rechnungen?bereich_id={bid}").json()
        assert len(rs) == 3
        status = {r["status"] for r in rs}
        assert {"entwurf", "offen", "bezahlt"} <= status
        # Mahnung zur überfälligen offenen Rechnung
        assert len(c.get("/api/mahnungen?status=offen").json()) == 1
        # Frist + Projekt + Aufgabe im Bereich
        assert len(c.get(f"/api/fristen?bereich_id={bid}").json()) == 1
        assert len(c.get(f"/api/projekte?bereich_id={bid}").json()) == 1
        # Cockpit liefert die 2 dormanten Konnektoren des Bereichs
        ck = c.get(f"/api/bereiche/{bid}/cockpit").json()
        assert len(ck["konnektoren"]) == 2
        assert ck["kontexte"]["money_kontext"] == seed_mod.MONEY_KONTEXT


def test_seed_idempotent(tmp_path):
    with _client(tmp_path) as c:
        a = seed_mod.seed(c)
        b = seed_mod.seed(c)
        assert b["status"] == "vorhanden" and b["bereich_id"] == a["bereich_id"]
        # kein Duplikat-Bereich, keine doppelten Rechnungen
        assert sum(1 for x in c.get("/api/bereiche").json() if x["name"] == seed_mod.DEMO_NAME) == 1
        assert len(c.get(f"/api/rechnungen?bereich_id={a['bereich_id']}").json()) == 3
