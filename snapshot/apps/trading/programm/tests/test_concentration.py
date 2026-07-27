"""Tests: Korrelations-/Konzentrations-Bewusstsein (P2) — Exposure je Asset, HHI, Cluster-Deckel."""
from types import SimpleNamespace

from backend.app import concentration


_idc = [0]


def _bot(pairs, *, stake=100.0, mot=3, mode="futures", opt=None, strategy="X", bid=None):
    _idc[0] += 1
    return SimpleNamespace(pairs=pairs, stake_amount=stake, max_open_trades=mot,
                           trading_mode=mode, opt_params=opt, strategy=strategy,
                           id=bid or f"b{_idc[0]}")


def _patch(monkeypatch, tmp_path, bots, open_positions=None):
    monkeypatch.setattr(concentration, "STATE_FILE", tmp_path / "concentration.json")
    monkeypatch.setattr(concentration.registry, "list_bots", lambda: list(bots))
    # Default: keine offenen Positionen → Kapazitäts-Fallback (deckt die Universum-Schätzungs-Tests ab).
    op = open_positions or {}
    monkeypatch.setattr(concentration.stats, "open_positions", lambda bid: op.get(bid, []))


def test_base_asset_parsing():
    assert concentration._base_asset("BTC/USDT:USDT") == "BTC"
    assert concentration._base_asset("eth/usdt") == "ETH"
    assert concentration._base_asset("badpair") is None


def test_exposure_split_equally_across_pairs(tmp_path, monkeypatch):
    # Ein Futures-Bot (Hebel 3) mit 3 Pairs: stake 100 × 3 Trades × 3 = 900 Notional, /3 Assets = 300 je.
    _patch(monkeypatch, tmp_path, [_bot(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"])])
    a = concentration.analyze()
    assert a["total_exposure"] == 900.0
    shares = {r["asset"]: r["share_pct"] for r in a["assets"]}
    assert round(shares["BTC"], 1) == 33.3 and a["n_assets"] == 3


def test_cluster_over_cap_warns(tmp_path, monkeypatch):
    # Viele Bots ausschließlich auf BTC/ETH/SOL → Krypto-Majors-Cluster = 100% > 85% Deckel.
    bots = [_bot(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]) for _ in range(10)]
    _patch(monkeypatch, tmp_path, bots)
    a = concentration.analyze()
    assert a["severity"] == "warn"
    maj = next(c for c in a["clusters"] if c["name"] == "Krypto-Majors")
    assert maj["over"] and maj["share_pct"] >= 99.9
    assert a["suggestions"]


def test_single_asset_over_cap_warns(tmp_path, monkeypatch):
    # Alles auf BTC → BTC 100% > 50% Asset-Deckel.
    _patch(monkeypatch, tmp_path, [_bot(["BTC/USDT:USDT"], mode="futures")])
    a = concentration.analyze()
    assert a["severity"] == "warn"
    assert a["top_asset"]["asset"] == "BTC" and a["top_asset"]["share_pct"] == 100.0


def test_diversified_is_ok(tmp_path, monkeypatch):
    # Gut gestreut über viele unkorrelierte Assets, Cluster nicht enthalten → ok.
    bots = [_bot([f"{s}/USDT"], mode="spot") for s in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")]
    _patch(monkeypatch, tmp_path, bots)
    a = concentration.analyze()
    assert a["severity"] == "ok" and not a["flags"]


def test_leverage_from_opt_params(tmp_path, monkeypatch):
    # MasterMeta-artiger Bot: Hebel aus opt_params.base_leverage (10) statt Futures-Default 3.
    _patch(monkeypatch, tmp_path, [_bot(["BTC/USDT:USDT"], stake=100, mot=1, opt={"base_leverage": 10})])
    a = concentration.analyze()
    assert a["total_exposure"] == 1000.0


def test_session_open_leverage_is_two(tmp_path, monkeypatch):
    # SessionOpenBreakout hat Hebel 2 (nicht der Futures-Default 3): 100×1×2 = 200 Notional.
    _patch(monkeypatch, tmp_path, [_bot(["BTC/USDT:USDT"], stake=100, mot=1, strategy="SessionOpenBreakout")])
    a = concentration.analyze()
    assert a["total_exposure"] == 200.0


def test_empty_when_no_pairs(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, [_bot([], mode="spot")])
    a = concentration.analyze()
    assert a["severity"] == "ok" and a["n_assets"] == 0 and a["total_exposure"] == 0.0


def test_live_mode_uses_open_positions(tmp_path, monkeypatch):
    # Zwei Bots, aber real nur BTC- und ETH-Positionen offen → live-Modus misst genau diese.
    b1 = _bot(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"], bid="b_a")
    b2 = _bot(["BTC/USDT:USDT", "XRP/USDT:USDT"], bid="b_b")
    op = {"b_a": [{"pair": "BTC/USDT:USDT", "notional": 300.0}],
          "b_b": [{"pair": "BTC/USDT:USDT", "notional": 100.0},
                  {"pair": "ETH/USDT:USDT", "notional": 100.0}]}
    _patch(monkeypatch, tmp_path, [b1, b2], open_positions=op)
    a = concentration.analyze()
    assert a["mode"] == "live" and a["open_trades"] == 3
    assert a["total_exposure"] == 500.0          # 300+100+100, NUR offene Positionen
    shares = {r["asset"]: r["exposure"] for r in a["assets"]}
    assert shares["BTC"] == 400.0 and shares["ETH"] == 100.0 and "SOL" not in shares
    btc = next(r for r in a["assets"] if r["asset"] == "BTC")
    assert btc["bots"] == 2                       # BTC in beiden Bots offen


def test_capacity_fallback_when_no_open_positions(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, [_bot(["BTC/USDT:USDT", "ETH/USDT:USDT"])])
    a = concentration.analyze()
    assert a["mode"] == "capacity" and a["open_trades"] == 0 and a["total_exposure"] > 0


def test_dynamic_bot_only_counts_eligible_number_assets(tmp_path, monkeypatch):
    # „Pairs streuen": ein dynamischer Scalping-Bot hat das volle Kandidaten-Universum als pairs, aber die
    # Konzentration darf nur die tatsächlich eligible (volumenstärkste, liquiditätsgeordnete) number_assets
    # zählen — sonst wird die Majors-Last kleingerechnet.
    from backend.app import universe
    cands = universe.candidates_for("scalping")           # 10 Kandidaten
    n = universe.number_assets_for("scalping")            # 5
    b = _bot(cands)
    b.pair_mode = "dynamic"
    b.horizon = "scalping"
    _patch(monkeypatch, tmp_path, [b])
    a = concentration.analyze()
    assert a["n_assets"] == n                              # nur die ersten 5 (nicht alle 10)
    bases = {r["asset"] for r in a["assets"]}
    assert bases == {universe.base_asset(p) for p in cands[:n]}
