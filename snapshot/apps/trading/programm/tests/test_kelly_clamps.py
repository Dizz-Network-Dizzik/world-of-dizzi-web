"""Tests: FP-2 Portfolio-Klemmkette K4→K5→K6 + Edge-Quelle/Konfidenz-Abschlag (SPEC §1+§3).

Kern = PROPERTY-Tests (seeded random, 200 Fälle) gegen die reine Klemmkette
``sizing._apply_portfolio_clamps``: die normative Reihenfolge ist über die Invarianten am
ENDZUSTAND abgesichert (P1–P6, docs/KELLY_SIZING_SPEC.md §3) — nicht über Implementierungs-
Interna. Dazu Water-Filling-Units und die K0/K1-Mathematik (Quelle/Shrinkage/sim_discount).
Byte-Identitäts-Anker: test_expectancy_sizing.py bleibt UNVERÄNDERT grün (Defaults inert)."""
import random
from types import SimpleNamespace

from backend.app import sizing, stats


# ----------------------- Water-Filling (K4-Kern, rein) -----------------------
def test_waterfill_no_cap_needed():
    stakes, s, infeasible = sizing._water_fill({"a": 100.0, "b": 200.0}, {"a": 1, "b": 1}, 25.0, 400.0)
    assert stakes == {"a": 100.0, "b": 200.0} and s == 1.0 and not infeasible


def test_waterfill_proportional():
    stakes, s, infeasible = sizing._water_fill({"a": 100.0, "b": 200.0}, {"a": 1, "b": 1}, 25.0, 150.0)
    assert abs(stakes["a"] - 50.0) < 1e-9 and abs(stakes["b"] - 100.0) < 1e-9
    assert abs(s - 0.5) < 1e-9 and not infeasible


def test_waterfill_floor_engages_and_rest_rescales():
    # a würde auf 9.09 fallen → Floor 25; b trägt den Rest des Deckels (75) exakt.
    stakes, s, infeasible = sizing._water_fill({"a": 30.0, "b": 300.0}, {"a": 1, "b": 1}, 25.0, 100.0)
    assert stakes["a"] == 25.0 and abs(stakes["b"] - 75.0) < 1e-9 and not infeasible
    assert stakes["a"] + stakes["b"] <= 100.0 + 1e-9


def test_waterfill_weights_count():
    # mot=Gewicht: b belegt je Stake-Euro 10× Margin → wird entsprechend stärker gedrückt.
    stakes, s, infeasible = sizing._water_fill({"a": 100.0, "b": 100.0}, {"a": 1, "b": 10}, 10.0, 550.0)
    assert abs(sum(stakes[k] * w for k, w in {"a": 1, "b": 10}.items()) - 550.0) < 1e-6


def test_waterfill_infeasible_honest():
    # Selbst alle-auf-Floor (25×2 + 25×2 = 100) liegt über dem Deckel 80 → ehrliches Flag.
    stakes, s, infeasible = sizing._water_fill({"a": 100.0, "b": 100.0}, {"a": 2, "b": 2}, 25.0, 80.0)
    assert infeasible and stakes == {"a": 25.0, "b": 25.0} and s == 0.0


# ----------------------- K0 Edge-Quelle + K1 Konfidenz-Abschlag -----------------------
def _bot(bid="b1", stake=100.0, strategy="S"):
    return SimpleNamespace(id=bid, tag=1, name=bid.upper(), strategy=strategy, stake_amount=stake)


def _base(monkeypatch, tmp_path):
    monkeypatch.setattr(sizing, "STATE_FILE", tmp_path / "sizing.json")
    monkeypatch.setattr(sizing.meta, "consistency",
                        lambda bid: {"volatility_pct": 2.0, "days_tracked": 9})


def test_edge_source_strategy_pools_all_bots_of_strategy(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    fleet = [_bot("b1", strategy="S"), _bot("b2", strategy="S"), _bot("b3", strategy="T")]
    monkeypatch.setattr(sizing.registry, "list_bots", lambda: fleet)
    seen: dict = {}

    def _pooled(ids):
        seen["ids"] = list(ids)
        return {"n_decided": 80, "kelly": 0.4}
    monkeypatch.setattr(sizing.stats, "pooled_expectancy", _pooled)
    monkeypatch.setattr(sizing.stats, "trade_expectancy",
                        lambda bid: (_ for _ in ()).throw(AssertionError("bot-Pfad tabu bei edge_source=strategy")))
    cfg = sizing.set_config({"expectancy_enabled": True, "edge_source": "strategy"})
    r = sizing.recommend_for(fleet[0], cfg)
    assert seen["ids"] == ["b1", "b2"]                    # nur die S-Bots, nicht T
    assert r["expectancy_mult"] == 1.1                    # 1 + 0.25·0.4


def test_edge_source_auto_falls_back_to_pool(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(sizing.registry, "list_bots", lambda: [_bot("b1"), _bot("b2")])
    monkeypatch.setattr(sizing.stats, "trade_expectancy", lambda bid: {"n_decided": 5, "kelly": 2.0})
    monkeypatch.setattr(sizing.stats, "pooled_expectancy", lambda ids: {"n_decided": 100, "kelly": 0.4})
    cfg = sizing.set_config({"expectancy_enabled": True, "edge_source": "auto"})
    r = sizing.recommend_for(_bot("b1"), cfg)
    assert r["expectancy_mult"] == 1.1                    # Pool greift (Bot n=5 < 20)


def test_edge_source_auto_prefers_own_trades(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(sizing.stats, "trade_expectancy", lambda bid: {"n_decided": 50, "kelly": 1.0})
    monkeypatch.setattr(sizing.stats, "pooled_expectancy",
                        lambda ids: (_ for _ in ()).throw(AssertionError("Pool tabu, Bot hat genug Trades")))
    cfg = sizing.set_config({"expectancy_enabled": True, "edge_source": "auto"})
    assert sizing.recommend_for(_bot(), cfg)["expectancy_mult"] == 1.25


def test_strategy_pool_below_min_sample_neutral(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(sizing.registry, "list_bots", lambda: [_bot("b1")])
    monkeypatch.setattr(sizing.stats, "pooled_expectancy", lambda ids: {"n_decided": 59, "kelly": 3.0})
    cfg = sizing.set_config({"expectancy_enabled": True, "edge_source": "strategy"})
    assert sizing.recommend_for(_bot(), cfg)["expectancy_mult"] == 1.0   # 59 < min_trades_strategy 60


def test_shrink_and_sim_discount_math(monkeypatch, tmp_path):
    # kelly_eff = 1.0 × 40/(40+40) × 0.8 = 0.4 → mult = 1 + 0.25·0.4 = 1.1 (exakt).
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(sizing.stats, "trade_expectancy", lambda bid: {"n_decided": 40, "kelly": 1.0})
    cfg = sizing.set_config({"expectancy_enabled": True, "shrink_trades": 40, "sim_discount": 0.8})
    r = sizing.recommend_for(_bot(), cfg)
    assert r["expectancy_mult"] == 1.1
    assert r["expectancy"]["kelly"] == 1.0                # Roh-Kelly bleibt sichtbar (Transparenz)


def test_shrink_monotone_in_n(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    cfg = sizing.set_config({"expectancy_enabled": True, "shrink_trades": 40})
    mults = []
    for n in (20, 60, 200):
        monkeypatch.setattr(sizing.stats, "trade_expectancy", lambda bid, n=n: {"n_decided": n, "kelly": 1.0})
        mults.append(sizing.recommend_for(_bot(), cfg)["expectancy_mult"])
    assert mults[0] < mults[1] < mults[2] <= 1.25         # mehr Belege → näher am ungeschrumpften Tilt


def test_set_config_clamps_fraction_and_discount():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        old = sizing.STATE_FILE
        sizing.STATE_FILE = Path(td) / "sizing.json"
        try:
            cfg = sizing.set_config({"kelly_fraction": 5.0, "sim_discount": 2.0,
                                     "portfolio_budget_pct": -10, "bridge_mode": "yolo",
                                     "edge_source": "quatsch"})
            assert cfg["kelly_fraction"] == 1.0           # nie über Voll-Kelly
            assert cfg["sim_discount"] == 1.0             # Discount, nie Aufschlag
            assert cfg["portfolio_budget_pct"] == 0.0
            assert cfg["bridge_mode"] == "proposal" and cfg["edge_source"] == "bot"   # Whitelist hält
        finally:
            sizing.STATE_FILE = old


# ----------------------- Klemmkette K4–K6: Property-Tests (P1–P6) -----------------------
def _row(bid, rec, cur):
    return {"bot_id": bid, "recommended_stake": round(rec, 2), "current_stake": round(cur, 2),
            "factor": 1.0, "realized_vol_pct": 2.0, "name": bid, "strategy": "S"}


def _cfg(**over):
    cfg = dict(sizing._DEFAULTS)
    cfg.update(over)
    return cfg


def _rand_case(rng: random.Random):
    n = rng.randint(1, 12)
    cfg = _cfg(min_stake=25.0, max_stake=250.0,
               portfolio_budget_pct=rng.choice([0.0, 0.0, rng.uniform(5, 150)]))
    rows, mots, assets = [], {}, {}
    pool = ["BTC", "ETH", "SOL", "XRP", "ADA"]
    for i in range(n):
        bid = f"b{i}"
        rows.append(_row(bid, rng.uniform(25, 250), rng.choice([0.0, rng.uniform(10, 300)])))
        mots[bid] = rng.randint(1, 5)
        assets[bid] = set(rng.sample(pool, rng.randint(1, 3)))
    overexposed = set(rng.sample(pool, rng.randint(0, 2)))
    severity = rng.choice(["ok", "ok", "warn", "breach"])
    wallet = rng.uniform(500, 20000)
    return rows, mots, assets, wallet, overexposed, severity, cfg


def test_clamp_chain_properties_seeded():
    rng = random.Random(1234)
    for case in range(200):
        rows, mots, assets, wallet, overexposed, severity, cfg = _rand_case(rng)
        res = sizing._apply_portfolio_clamps(rows, mots=mots, assets=assets, wallet_total=wallet,
                                             overexposed=overexposed, governor_severity=severity,
                                             cfg=cfg)
        out = {r["bot_id"]: r for r in res["rows"]}
        budget = res["budget"]
        for r in rows:
            b, rec, cur = r["bot_id"], r["recommended_stake"], r["current_stake"]
            planned = out[b]["planned_stake"]
            # P3 Monotonie: die Kette erhöht NIE über die per-Bot-Empfehlung.
            assert planned <= rec + 1e-9, f"Fall {case}: {b} erhöht ({planned} > {rec})"
            # P1 Caps: obere Kante immer; untere Kante = min(min_stake, aktuell) (Freeze hebt nie an).
            assert planned <= cfg["max_stake"] + 1e-9
            floor_eff = min(cfg["min_stake"], cur) if cur > 0 else cfg["min_stake"]
            assert planned >= floor_eff - 0.01, f"Fall {case}: {b} unter Floor ({planned} < {floor_eff})"
            # P4 Governor-Freeze: warn/breach ⇒ kein Upsizing über den aktuellen Stake.
            if severity in ("warn", "breach") and cur > 0:
                assert planned <= cur + 1e-9, f"Fall {case}: {b} upsized trotz Governor {severity}"
            # K5-Freeze: betroffene Assets ⇒ kein Upsizing.
            if overexposed and (assets[b] & overexposed) and cur > 0:
                assert planned <= cur + 1e-9, f"Fall {case}: {b} upsized in den Klumpen"
        # P2 Budget: Deckel hält (bis auf Cent-Rundung der Ausgabe-Stakes: ≤ 0.005 × Σ mot) —
        # oder das ehrliche infeasible-Flag ist gesetzt.
        if cfg["portfolio_budget_pct"] > 0:
            cap = cfg["portfolio_budget_pct"] / 100.0 * wallet
            total = sum(out[r["bot_id"]]["planned_stake"] * mots[r["bot_id"]] for r in rows)
            round_tol = 0.005 * sum(mots.values()) + 1e-6
            assert total <= cap + round_tol or budget["infeasible"], \
                f"Fall {case}: Budget verletzt ohne Flag ({total} > {cap})"
        # P6 Idempotenz: den Plan auf seinem eigenen Ergebnis wiederholen ändert nichts
        # (Toleranz = Folge der Cent-Rundung; re-Skalierung dadurch ≤ 0.005/25 relativ).
        rows2 = [{**r, "recommended_stake": out[r["bot_id"]]["planned_stake"]} for r in rows]
        res2 = sizing._apply_portfolio_clamps(rows2, mots=mots, assets=assets, wallet_total=wallet,
                                              overexposed=overexposed, governor_severity=severity,
                                              cfg=cfg)
        for r2 in res2["rows"]:
            assert abs(r2["planned_stake"] - out[r2["bot_id"]]["planned_stake"]) <= 0.06, \
                f"Fall {case}: nicht idempotent ({r2['bot_id']})"


def test_clamp_chain_defaults_inert_exact():
    # Budget aus + Governor ok + keine Klumpen ⇒ planned == recommended EXAKT (byte-identisch).
    rng = random.Random(99)
    rows = [_row(f"b{i}", rng.uniform(25, 250), rng.uniform(10, 300)) for i in range(8)]
    res = sizing._apply_portfolio_clamps(rows, mots={r["bot_id"]: 3 for r in rows},
                                         assets={r["bot_id"]: {"BTC"} for r in rows},
                                         wallet_total=10000.0, overexposed=set(),
                                         governor_severity="ok", cfg=_cfg())
    for r, out in zip(rows, res["rows"]):
        assert out["planned_stake"] == r["recommended_stake"] and out["clamps"] == []
    assert res["trace"] == [] and res["budget"]["cap"] is None


def test_clamp_order_budget_before_freeze_documented():
    # Reihenfolge-Beleg: K4 skaliert proportional, K6 friert DANACH auf `aktuell` — ein Bot, dessen
    # skalierten Stake ÜBER aktuell liegt, endet bei aktuell (nicht beim skalierten Wert).
    rows = [_row("a", 200.0, 60.0), _row("b", 200.0, 500.0)]
    cfg = _cfg(min_stake=25.0, max_stake=250.0, portfolio_budget_pct=100.0)
    res = sizing._apply_portfolio_clamps(rows, mots={"a": 1, "b": 1}, assets={"a": set(), "b": set()},
                                         wallet_total=200.0, overexposed=set(),
                                         governor_severity="warn", cfg=cfg)
    out = {r["bot_id"]: r for r in res["rows"]}
    # K4: cap 200 → s=0.5 → beide 100. K6 (warn): a auf 60 (aktuell), b bleibt 100 (< aktuell 500).
    assert out["a"]["planned_stake"] == 60.0 and out["b"]["planned_stake"] == 100.0
    assert any("K4" in c for c in out["a"]["clamps"]) and any("K6" in c for c in out["a"]["clamps"])


def test_governor_breach_freezes_fleetwide():
    rows = [_row("a", 250.0, 100.0), _row("b", 30.0, 100.0)]
    res = sizing._apply_portfolio_clamps(rows, mots={"a": 1, "b": 1}, assets={"a": set(), "b": set()},
                                         wallet_total=0.0, overexposed=set(),
                                         governor_severity="breach", cfg=_cfg())
    out = {r["bot_id"]: r for r in res["rows"]}
    assert out["a"]["planned_stake"] == 100.0     # Upsizing eingefroren
    assert out["b"]["planned_stake"] == 30.0      # Downsizing bleibt erlaubt (kein Zwang nach oben)


def test_concentration_freeze_only_affected_assets():
    rows = [_row("btc", 200.0, 100.0), _row("xrp", 200.0, 100.0)]
    res = sizing._apply_portfolio_clamps(rows, mots={"btc": 1, "xrp": 1},
                                         assets={"btc": {"BTC"}, "xrp": {"XRP"}},
                                         wallet_total=0.0, overexposed={"BTC"},
                                         governor_severity="ok", cfg=_cfg())
    out = {r["bot_id"]: r for r in res["rows"]}
    assert out["btc"]["planned_stake"] == 100.0 and "K5" in out["btc"]["clamps"][0]
    assert out["xrp"]["planned_stake"] == 200.0 and out["xrp"]["clamps"] == []


def test_overexposed_assets_extraction():
    conc = {"severity": "warn",
            "config": {"max_asset_share_pct": 50.0},
            "assets": [{"asset": "BTC", "share_pct": 61.0}, {"asset": "ETH", "share_pct": 30.0}],
            "clusters": [{"name": "Majors", "assets": ["BTC", "ETH", "SOL"],
                          "present": ["BTC", "ETH"], "over": True}]}
    assert sizing._overexposed_assets(conc) == {"BTC", "ETH"}
    assert sizing._overexposed_assets({**conc, "severity": "ok"}) == set()


# ----------------------- portfolio_plan (Shell, gemockt) -----------------------
def _fleet_bot(bid, stake=100.0, dry=True, wallet=1000.0, pairs=("BTC/USDT:USDT",)):
    return SimpleNamespace(id=bid, tag=1, name=bid.upper(), strategy="S", stake_amount=stake,
                           max_open_trades=3, dry_run=dry, dry_run_wallet=wallet, pairs=list(pairs))


def test_portfolio_plan_defaults_match_recommend_and_skip_echtgeld(monkeypatch, tmp_path):
    from backend.app import concentration, governor
    _base(monkeypatch, tmp_path)
    fleet = [_fleet_bot("b1"), _fleet_bot("b2"), _fleet_bot("geld", dry=False)]
    monkeypatch.setattr(sizing.registry, "list_bots", lambda: fleet)
    monkeypatch.setattr(governor, "evaluate", lambda use_cache=True: {"severity": "ok"})
    monkeypatch.setattr(concentration, "analyze", lambda: {"severity": "ok"})
    plan = sizing.portfolio_plan()
    assert [r["bot_id"] for r in plan["rows"]] == ["b1", "b2"]          # Echtgeld NIE geplant
    assert plan["skipped"][0]["bot_id"] == "geld"
    cfg = sizing.get_config()
    for r in plan["rows"]:                                              # Defaults ⇒ Plan == Empfehlung
        rec = sizing.recommend_for(next(b for b in fleet if b.id == r["bot_id"]), cfg)
        assert r["planned_stake"] == rec["recommended_stake"] and r["clamps"] == []


def test_portfolio_plan_defensive_on_advisor_errors(monkeypatch, tmp_path):
    from backend.app import concentration, governor
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(sizing.registry, "list_bots", lambda: [_fleet_bot("b1")])
    monkeypatch.setattr(governor, "evaluate",
                        lambda use_cache=True: (_ for _ in ()).throw(RuntimeError("kaputt")))
    monkeypatch.setattr(concentration, "analyze",
                        lambda: (_ for _ in ()).throw(RuntimeError("kaputt")))
    plan = sizing.portfolio_plan()                                      # Fehler ⇒ ok/keine Klemme
    assert plan["governor_severity"] == "ok" and len(plan["rows"]) == 1
