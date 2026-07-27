"""Tests: gestreutes Coin-Universum („Pairs streuen") — Kandidaten, dynamische Pairlist, Diversify."""
from backend.app import universe


def test_to_pairs_futures_suffix():
    assert universe.to_pairs(["BTC", "eth"], "futures") == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    assert universe.to_pairs(["BTC"], "spot") == ["BTC/USDT"]
    # idempotent für bereits formatierte Pairs
    assert universe.to_pairs(["BTC/USDT:USDT"], "futures") == ["BTC/USDT:USDT"]
    assert universe.to_pairs(["BTC/USDT"], "futures") == ["BTC/USDT:USDT"]


def test_base_asset():
    assert universe.base_asset("BTC/USDT:USDT") == "BTC"
    assert universe.base_asset("eth/usdt") == "ETH"


def test_candidates_are_broad_and_horizon_staggered():
    sc = universe.candidates_for("scalping")
    iv = universe.candidates_for("intraday")
    sw = universe.candidates_for("swing")
    # Streuung: deutlich mehr als die alten 3 Majors, und Swing am breitesten.
    assert len(sc) >= 8 and len(iv) == len(universe.FULL) and len(sw) == len(universe.FULL)
    assert len(sc) <= len(iv)
    # Alle enthalten die Majors und sind sauber im Futures-Format.
    assert "BTC/USDT:USDT" in sc and all(p.endswith(":USDT") for p in sw)


def test_number_assets_caps_below_candidates():
    # number_assets < Kandidaten ⇒ echte dynamische Auswahl (VolumePairList wählt die liquidesten).
    for h in ("scalping", "intraday", "swing"):
        assert universe.number_assets_for(h) < len(universe.candidates_for(h))


def test_unknown_horizon_falls_back_to_intraday():
    assert universe.candidates_for("bogus") == universe.candidates_for("intraday")
    assert universe.number_assets_for(None) == universe.number_assets_for("intraday")


def test_pairlists_chain_is_static_then_volume_then_spread():
    pl = universe.pairlists_for("intraday")
    assert [p["method"] for p in pl] == ["StaticPairList", "VolumePairList", "SpreadFilter"]
    assert pl[1]["number_assets"] == universe.number_assets_for("intraday")
    assert pl[1]["sort_key"] == "quoteVolume"
    assert pl[2]["max_spread_ratio"] == universe._MAX_SPREAD_RATIO


def test_label_and_model():
    lab = universe.label("swing")
    assert lab["mode"] == "dynamic" and lab["number_assets"] == 10
    assert "Top-10" in lab["text"] and lab["candidate_count"] == len(universe.FULL)
    m = universe.model()
    assert m["method"] == "dynamic_volume" and set(m["horizons"]) == {"scalping", "intraday", "swing"}
    assert m["candidate_count"] == len(universe.FULL)


def test_registry_diversify_raw_idempotent():
    from backend.app import registry
    raw = {"timeframe": "5m", "horizon": "scalping", "trading_mode": "futures",
           "pairs": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"], "pair_mode": "static"}
    assert registry._diversify_raw(raw) is True
    assert raw["pair_mode"] == "dynamic"
    assert raw["pairs"] == universe.candidates_for("scalping", "futures")
    # zweiter Aufruf ändert nichts mehr
    assert registry._diversify_raw(raw) is False
