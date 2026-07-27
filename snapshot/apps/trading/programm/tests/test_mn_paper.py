"""Tests der MN-Paper-Bots (mn_paper): CRUD-Persistenz, Config-Coercion, Sim-Bewertung, Track.

Hermetisch: PAPER_FILE wird auf ein tmp_path umgebogen (keine Berührung der echten
mn_paper_bots.json), und die Preis-Quelle ``csm._load_prices`` wird mit einer synthetischen
Trend-Welt gemockt (keine ccxt/DB nötig — gleiches Muster wie test_csm)."""
import json

import pytest

from backend.app import csm, mn_paper

DAY = 24 * 60 * 60 * 1000


def _ts(n):
    return [i * DAY for i in range(n)]


def _trend(rate, n, p0=100.0):
    out, p = [], p0
    for _ in range(n):
        out.append(round(p, 6))
        p *= rate
    return out


def _universe(n=60):
    rates = {"UP0": 1.005, "UP1": 1.008, "UP2": 1.012, "UP3": 1.015,
             "DN0": 0.995, "DN1": 0.992, "DN2": 0.988, "DN3": 0.985}
    return list(rates), _ts(n), {s: _trend(r, n) for s, r in rates.items()}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Lenkt die Persistenz auf eine Wegwerf-Datei + mockt die Preisquelle (synthetische Trend-Welt)."""
    monkeypatch.setattr(mn_paper, "PAPER_FILE", tmp_path / "mn_paper_bots.json")
    syms, ts, closes = _universe()
    monkeypatch.setattr(csm, "_load_prices", lambda min_history: (syms, ts, closes))
    monkeypatch.setattr(csm, "_meta_get", lambda key: None)
    return tmp_path


# ---------------- Katalog + Config-Coercion ----------------
def test_engines_catalog_has_four_mn_engines():
    cat = mn_paper.engines_catalog()
    assert {e["engine"] for e in cat} == {"csm", "pairs", "statarb", "mm"}
    for e in cat:
        assert e["defaults"] and set(e["defaults"]) == set(e["tunable"])


def test_coerce_keeps_only_tunable_and_casts():
    c = mn_paper._coerce_config("csm", {"lookback": "21", "bogus": 99, "vol_scaled": True})
    assert c["lookback"] == 21 and isinstance(c["lookback"], int)
    assert c["vol_scaled"] is True
    assert "bogus" not in c
    assert set(c) == set(mn_paper.ENGINES["csm"]["tunable"])


def test_coerce_unknown_engine_raises():
    with pytest.raises(ValueError):
        mn_paper._coerce_config("nope", {})


# ---------------- Winrate (rein) ----------------
def test_winrate_from_equity_and_rets():
    wr, up, n = mn_paper._winrate([[0, 100], [1, 101], [2, 100.5], [3, 102]])
    assert (up, n) == (2, 3) and wr == round(100 * 2 / 3, 1)
    wr2, up2, n2 = mn_paper._winrate([], rets=[0.01, -0.02, 0.0, 0.03])
    assert (up2, n2) == (2, 4) and wr2 == 50.0   # 0.0 zählt nicht als Gewinn


# ---------------- CRUD-Persistenz ----------------
def test_create_list_get_delete(store):
    rec = mn_paper.create("Mein CSM", "csm", {"lookback": 21})
    assert rec["engine"] == "csm" and rec["config"]["lookback"] == 21
    assert rec["status"] == "stopped" and rec["tag"] == 1 and rec["track"] == []
    assert len(mn_paper.list_bots()) == 1
    assert mn_paper.get(rec["id"])["name"] == "Mein CSM"
    # Persistenz auf Platte verifizieren
    on_disk = json.loads((store / "mn_paper_bots.json").read_text(encoding="utf-8"))
    assert rec["id"] in on_disk
    assert mn_paper.delete(rec["id"]) is True
    assert mn_paper.list_bots() == []
    assert mn_paper.delete("ghost") is False


def test_tag_increments(store):
    a = mn_paper.create("A", "csm", {})
    b = mn_paper.create("B", "pairs", {})
    assert (a["tag"], b["tag"]) == (1, 2)


def test_create_unknown_engine_raises(store):
    with pytest.raises(ValueError):
        mn_paper.create("X", "funding", {})


def test_update_config_and_rename_and_status(store):
    rec = mn_paper.create("A", "csm", {})
    up = mn_paper.update_config(rec["id"], {"lookback": 30})
    assert up["config"]["lookback"] == 30
    rn = mn_paper.rename(rec["id"], "Neu")
    assert rn["name"] == "Neu"
    st = mn_paper.set_status(rec["id"], "running")
    assert st["status"] == "running" and st["started_at"]
    with pytest.raises(ValueError):
        mn_paper.set_status(rec["id"], "bogus")


# ---------------- Sim-Bewertung (Adapter) ----------------
def test_evaluate_csm_profitable_trending(store):
    ev = mn_paper.evaluate("csm", {"lookback": 14, "hold": 1, "quantile": 0.3})
    assert ev["ok"] and ev["mode"] == "demo-simulation"
    assert ev["pnl_pct"] > 0 and ev["stats"]["sharpe"] > 0
    assert 0 <= ev["winrate_pct"] <= 100 and ev["n_periods"] > 0
    assert ev["pnl_abs"] == round(ev["capital"] * ev["pnl_pct"] / 100.0, 2)


def test_evaluate_statarb_runs(store):
    ev = mn_paper.evaluate("statarb", {})
    assert ev["ok"] and "winrate_pct" in ev and ev["n_periods"] > 0


def test_evaluate_no_prices_is_not_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(mn_paper, "PAPER_FILE", tmp_path / "p.json")
    monkeypatch.setattr(csm, "_load_prices", lambda mh: ([], [], {}))
    monkeypatch.setattr(csm, "_meta_get", lambda k: None)
    ev = mn_paper.evaluate("csm", {})
    assert ev["ok"] is False and "refresh" in ev["note"].lower()


# ---------------- state() + Kalender-Track ----------------
def test_state_records_track_only_when_running(store):
    rec = mn_paper.create("A", "csm", {})
    # gestoppt: kein Track
    st = mn_paper.state(rec["id"])
    assert st["evaluation"]["ok"] and st["track"] == []
    assert st["engine_label"]
    # running: ein Track-Eintrag, idempotent pro Tag
    mn_paper.set_status(rec["id"], "running")
    mn_paper.state(rec["id"])
    mn_paper.state(rec["id"])
    again = mn_paper.get(rec["id"])
    assert len(again["track"]) == 1
    entry = again["track"][0]
    assert "pnl_pct" in entry and "winrate_pct" in entry and "day" in entry


def test_state_unknown_returns_none(store):
    assert mn_paper.state("ghost") is None


# ---------------- seed_defaults ----------------
def test_seed_defaults_idempotent(store):
    first = mn_paper.seed_defaults()
    assert {b["engine"] for b in first} == {"csm", "pairs", "statarb", "mm"}
    assert mn_paper.seed_defaults() == []   # zweiter Lauf legt nichts Neues an
    assert len(mn_paper.list_bots()) == 4


def test_summary_shape(store):
    mn_paper.create("A", "csm", {})
    s = mn_paper.summary()
    assert len(s) == 1
    row = s[0]
    assert {"id", "tag", "name", "engine", "status", "ok", "pnl_pct", "winrate_pct"} <= set(row)
