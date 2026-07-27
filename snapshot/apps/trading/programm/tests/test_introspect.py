"""Tests: Selbst-Analyse (Struktur-Erfassung + Audit + Schluss-Sammlung)."""
from backend.app import introspect, maintenance, stats


def test_assess_structure_and_health():
    a = introspect.assess()
    assert "categories" in a and len(a["categories"]) >= 6
    assert a["learning_target"] and a["top_improvements"]
    for c in a["categories"]:
        assert c["health"] in ("ok", "warn", "gap")
        assert isinstance(c["improvements"], list) and isinstance(c["findings"], list)
        assert c["name"] and c["label"]
    assert set(a["health_summary"]) >= {"ok", "warn"}


def test_self_collect_writes_ledger(tmp_path):
    stats.DATA_DIR = tmp_path
    stats.DB_FILE = tmp_path / "t.sqlite"
    r = introspect.self_collect()
    assert r["ok"] and r["recorded"] >= 1
    assert len(maintenance.get_ledger()) >= 1
