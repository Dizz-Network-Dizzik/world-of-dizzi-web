"""Tests V11 Trading→Memory — NUR die Sendeseite.

Prüft: (a) der Umschlag entspricht exakt dem Vertrag (docs/26 §11.1), (b) der Sender ist **best-effort**
und wirft NIE in den Trading-Pfad (Core/Memory offline ⇒ ok=False, kein Throw). Alles isoliert — die
Datenaufnahme (`_gather`) und der Netz-POST (`_post_relay`) werden gemockt (kein Backend/Netz nötig).
"""
from datetime import datetime, timezone

from backend.app import report

SAMPLE = {
    "fleet": {"total": 51, "running": 50, "stale": 2, "stopped": 1, "stale_names": ["O04", "O13"]},
    "master": {"fitness": 0.631, "version": 33, "dir_edge": 0.093, "mn_share": 0.867, "mn_active": 1},
    "evidence": {"strategies": 9, "validated": 9, "mn_engines": 4},
}


def test_build_markdown_ref_stable_and_content():
    now = datetime(2026, 6, 16, 8, 30, tzinfo=timezone.utc)
    titel, md, ref = report.build_markdown(SAMPLE, now=now)
    assert ref == "trading:report:2026-06-16"          # stabiles Tages-ref ⇒ idempotent
    assert "Status-Report 2026-06-16" in titel
    assert "Flotte" in md and "Master-Ensemble" in md and "Evidenz" in md
    assert "0.631" in md and "O04" in md                # echte Werte sind eingebaut


def test_archivieren_envelope_matches_contract(monkeypatch):
    sent = {}

    def fake_post(payload, timeout=report.RELAY_TIMEOUT_S):
        sent.update(payload)
        return {"ziel": "memory", "ok": True, "status": "archiviert", "id": "abc123"}

    monkeypatch.setattr(report, "_gather", lambda: SAMPLE)
    monkeypatch.setattr(report, "_post_relay", fake_post)
    out = report.archivieren(explizit=True)
    # Umschlag exakt nach docs/26 §11.1
    assert sent["app"] == "tradingbot"
    assert sent["strom"] == "report"
    assert sent["sensibel"] is True
    assert sent["explizit"] is True
    assert sent["ref"].startswith("trading:report:")
    assert sent["titel"] and sent["inhalt"]
    # Relay-Antwort wird durchgereicht
    assert out["ok"] is True and out["status"] == "archiviert" and out["id"] == "abc123"


def test_archivieren_best_effort_when_relay_throws(monkeypatch):
    def boom(payload, timeout=report.RELAY_TIMEOUT_S):
        raise OSError("Core/Memory offline")
    monkeypatch.setattr(report, "_gather", lambda: SAMPLE)
    monkeypatch.setattr(report, "_post_relay", boom)
    out = report.archivieren(explizit=True)            # darf NICHT werfen
    assert out["ok"] is False and "error" in out


def test_archivieren_best_effort_when_gather_throws(monkeypatch):
    def boom():
        raise RuntimeError("Status-Aufnahme kaputt")
    monkeypatch.setattr(report, "_gather", boom)
    out = report.archivieren(explizit=True)            # auch hier kein Wurf in den Trading-Pfad
    assert out["ok"] is False


def test_relay_target_is_core_relay():
    assert report.RELAY_PATH == "/api/querverbindung/memory"
    assert "://" in report.CORE_BASE  # vollständige Basis-URL (Default lokaler Core :8200)
