"""FP-T5 Byte-Identitäts-/Funktions-Verifikation der Politik-Brücke mit ECHTEM pandas/talib.

Läuft bewusst NICHT in der Backend-Suite (dort fehlen pandas/talib — die Gate-Logik ist da über
Stubs getestet, tests/test_policy_bridge.py), sondern im Engine-venv:

    engine\\.venv\\Scripts\\python.exe tests\\engine_policy_verify.py

Beweist auf einem seeded synthetischen OHLCV-Frame (echte Indikator-/Entry-Pipeline):
  V1  Ohne Opt-in ist der DataFrame BYTE-IDENTISCH — auch wenn eine gültige apply-Datei daliegt.
  V2  ``mode='proposal'`` ⇒ ebenfalls byte-identisch (die Hand wendet nie an).
  V3  Apply + L1 (Logik-Tausch) ⇒ Entries entsprechen EXAKT der unabhängig nachgerechneten
      Soll-Maske (getauschte Signal-Familien, ``pol_``-Tags) — und nur dort.
  V4  Apply + L3 (alle Regime ohne Edge) ⇒ 0 Entries (long UND short).
  V5  ``custom_stake_amount``: L2-Dämpfung 55→44 (×0.8), freqtrade-min klemmt zuletzt, ohne
      aktives Regime no-op.
Ergebnis-Zeilen sind der Beleg für docs/POLICY_HAND_SPEC.md §6.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROGRAMM = Path(__file__).resolve().parents[1]
SCRATCH = PROGRAMM / "data"          # nur für die temporäre Bridge-Datei dieses Laufs
POLICY_FILE = SCRATCH / "_verify_suggested_policy.json"


def _load_master_meta():
    path = PROGRAMM / "engine" / "user_data" / "strategies" / "master_meta.py"
    spec = importlib.util.spec_from_file_location("master_meta_verify", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frame(n=800, seed=7) -> pd.DataFrame:
    """Synthetischer 15m-OHLCV-Pfad mit Trend- UND Seitwärtsphasen (beide Signal-Familien feuern)."""
    rng = np.random.default_rng(seed)
    drift = np.concatenate([np.full(n // 4, 0.0015), np.full(n // 4, 0.0),
                            np.full(n // 4, -0.0015), np.full(n - 3 * (n // 4), 0.0)])
    rets = drift + rng.normal(0.0, 0.006, n)
    close = 50000.0 * np.cumprod(1.0 + rets)
    high = close * (1.0 + np.abs(rng.normal(0, 0.002, n)))
    low = close * (1.0 - np.abs(rng.normal(0, 0.002, n)))
    open_ = np.roll(close, 1); open_[0] = close[0]
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.uniform(10, 1000, n)})


def _strategy(mm, dry_run=True):
    # Ohne freqtrade-Vollconfig instanziieren: die populate-/stake-Pfade brauchen nur self.config.
    strat = object.__new__(mm.MasterMeta)
    strat.config = {"dry_run": dry_run}
    return strat


def _populate(mm, base: pd.DataFrame) -> pd.DataFrame:
    strat = _strategy(mm)
    df = strat.populate_indicators(base.copy(), {"pair": "BTC/USDT:USDT"})
    return strat.populate_entry_trend(df, {"pair": "BTC/USDT:USDT"})


def _write_policy(mode="apply", levers=None, logic=None, enabled=None, active_scale=0.8):
    regimes = {}
    for reg, dflt in (("trend_up", "trend_macd"), ("range", "range_bb"),
                      ("trend_down", "trend_macd_short")):
        regimes[reg] = {"logic": (logic or {}).get(reg, dflt),
                        "enabled": (enabled or {}).get(reg, True)}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    POLICY_FILE.write_text(json.dumps({
        "ts": int(time.time() * 1000), "mode": mode,
        "levers": levers or {"apply_logic": False, "apply_stake": False, "gate_unprofitable": False},
        "active": {"regime": "range", "stake_scale": active_scale},
        "regimes": regimes}), encoding="utf-8")


def _expected_masks(df: pd.DataFrame, logic_up: str, logic_range: str):
    """Unabhängige Soll-Berechnung der Entry-Masken (Default-opt-params) — Gegenprobe zur Engine."""
    macd_cross = (df["macd"] > df["macdsignal"]) & (df["macd"].shift(1) <= df["macdsignal"].shift(1))
    vol = df["volume"] > 0
    macro_ok = df["close"] > df["macro_sma"]
    sig = {"trend_macd": macd_cross & (df["adx"] > 25) & vol & macro_ok,
           "range_bb": (df["close"] < df["bb_lower"]) & (df["rsi"] < 35) & vol & vol & macro_ok}
    up = (df["reg_up"] == 1) & sig[logic_up]
    rng_ = (df["reg_range"] == 1) & sig[logic_range]
    macd_bear = (df["macd"] < df["macdsignal"]) & (df["macd"].shift(1) >= df["macdsignal"].shift(1))
    short = (df["reg_down"] == 1) & macd_bear & (df["adx"] > 25) & vol
    return up, rng_, short


def main() -> int:
    os.environ["TBT_POLICY_FILE"] = str(POLICY_FILE)
    os.environ["TBT_REGIME_FILE"] = str(SCRATCH / "_verify_gibts_nicht.json")   # HMM-Override isolieren
    os.environ.pop("TBT_OPT_PARAMS", None)
    os.environ.pop("TBT_SIZING_FILE", None)
    if POLICY_FILE.exists():
        POLICY_FILE.unlink()
    mm = _load_master_meta()
    base = _frame()
    results = []

    df_base = _populate(mm, base)
    n_long = int(df_base.get("enter_long", pd.Series(dtype=float)).fillna(0).sum())
    n_short = int(df_base.get("enter_short", pd.Series(dtype=float)).fillna(0).sum())
    assert n_long > 0 and n_short > 0, "Testdaten müssen beide Entry-Familien produzieren"
    results.append(f"Basislauf: {len(base)} Kerzen, {n_long} Long- / {n_short} Short-Entries (Default-Logik)")

    # V1 — gültige apply-Datei mit getauschter Logik liegt da, aber KEIN Engine-Opt-in.
    _write_policy(mode="apply", levers={"apply_logic": True, "apply_stake": True,
                                        "gate_unprofitable": True},
                  logic={"trend_up": "range_bb", "range": "trend_macd"})
    df_v1 = _populate(mm, base)
    assert list(df_v1.columns) == list(df_base.columns) and df_v1.equals(df_base), "V1 verletzt!"
    results.append("V1 PASS: ohne Opt-in byte-identisch (df.equals) trotz gültiger apply-Datei")

    # V2 — Opt-in gesetzt, aber mode='proposal'.
    os.environ["TBT_OPT_PARAMS"] = json.dumps({"use_policy_bridge": 1})
    _write_policy(mode="proposal", levers={"apply_logic": True},
                  logic={"trend_up": "range_bb", "range": "trend_macd"})
    df_v2 = _populate(mm, base)
    assert df_v2.equals(df_base), "V2 verletzt!"
    results.append("V2 PASS: mode='proposal' ⇒ byte-identisch (die Hand wendet nie an)")

    # V3 — apply + L1: Logik je Regime GETAUSCHT; Soll-Maske unabhängig nachgerechnet.
    _write_policy(mode="apply", levers={"apply_logic": True},
                  logic={"trend_up": "range_bb", "range": "trend_macd"})
    df_v3 = _populate(mm, base)
    up, rng_, short = _expected_masks(df_v3, "range_bb", "trend_macd")
    want_long = (up | rng_)
    got_long = df_v3["enter_long"].fillna(0) == 1
    assert got_long.equals(want_long), "V3 verletzt: Entry-Maske ≠ Soll (getauschte Logik)"
    tags = set(df_v3.loc[got_long, "enter_tag"].dropna().unique())
    assert tags <= {"pol_range_bb", "pol_trend_macd"} and tags, f"V3-Tags falsch: {tags}"
    n3 = int(got_long.sum())
    assert not df_v3.equals(df_base), "V3: Umschaltung muss sich vom Basislauf unterscheiden"
    results.append(f"V3 PASS: L1-Logik-Tausch ⇒ {n3} Entries folgen EXAKT der Soll-Maske, Tags {sorted(tags)}")

    # V4 — apply + L3: kein Regime hat belegten Edge ⇒ 0 Entries (long und short).
    _write_policy(mode="apply", levers={"gate_unprofitable": True},
                  enabled={"trend_up": False, "range": False, "trend_down": False})
    df_v4 = _populate(mm, base)
    assert int(df_v4["enter_long"].fillna(0).sum()) == 0, "V4 long verletzt"
    assert int(df_v4.get("enter_short", pd.Series(dtype=float)).fillna(0).sum()) == 0, "V4 short verletzt"
    results.append("V4 PASS: L3-Edge-Gating (alle Regime aus) ⇒ 0 Long- und 0 Short-Entries")

    # V5 — custom_stake_amount: L2-Dämpfung mit echtem Strategie-Objekt.
    _write_policy(mode="apply", levers={"apply_stake": True}, active_scale=0.8)
    strat = _strategy(mm)
    s = strat.custom_stake_amount("BTC/USDT:USDT", None, 50000.0, 55.0, None, None, 5.0, "t", "long")
    assert abs(s - 44.0) < 1e-9, f"V5 verletzt: {s}"
    s2 = strat.custom_stake_amount("BTC/USDT:USDT", None, 50000.0, 55.0, 50.0, None, 5.0, "t", "long")
    assert abs(s2 - 50.0) < 1e-9, "V5 min_stake-Klemme verletzt"
    _write_policy(mode="apply", levers={"apply_stake": True}, active_scale=None)
    s3 = strat.custom_stake_amount("BTC/USDT:USDT", None, 50000.0, 55.0, None, None, 5.0, "t", "long")
    assert abs(s3 - 55.0) < 1e-9, "V5 no-op ohne aktives Regime verletzt"
    results.append("V5 PASS: L2-Stake-Dämpfung 55→44.0 (×0.8) · min_stake klemmt zuletzt · ohne aktives Regime no-op")

    POLICY_FILE.unlink(missing_ok=True)
    print("\n".join(results))
    print(f"ALLE {len(results) - 1} VERIFIKATIONEN PASS (pandas {pd.__version__}, seed 7, n=800)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
