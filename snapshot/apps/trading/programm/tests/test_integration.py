"""Tests: Komponenten-Schnittstelle (descriptor/state/command) für übergeordnetes System."""
from backend.app import integration


def test_descriptor_contract():
    d = integration.descriptor()
    assert d["component_id"] == "trading-bot-eins"
    assert d["api_contract"] == "v1"
    actions = {c["action"] for c in d["capabilities"]}
    assert {"report", "introspect", "train_master", "pause_all"} <= actions


def test_command_safe_and_unknown_and_destructive_guard():
    assert integration.command("report")["ok"] is True
    assert integration.command("introspect")["ok"] is True
    assert integration.command("nonsense")["ok"] is False
    # destruktiv ohne confirm -> abgelehnt (kein Eingriff)
    r = integration.command("pause_all")
    assert r["ok"] is False and r.get("destructive") is True


def test_state_has_metrics():
    s = integration.state()
    assert "metrics" in s and "bots_registered" in s["metrics"] and "master_version" in s["metrics"]
