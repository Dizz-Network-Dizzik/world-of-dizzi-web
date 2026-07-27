"""TrendFollowEma — Katalog-System „Trendfolge" (EMA-Crossover + RSI-Filter).

Long bei EMA-Aufwaertskreuz + RSI-Bestaetigung; Exit per Gegenkreuz/ROI/Stop/Trailing.
Parametrisierbar: liest optimierte Parameter aus der Umgebungsvariable
``TBT_OPT_PARAMS`` (nur im Optimierungs-Backtest gesetzt). Live-Bots ohne diese
Variable nutzen die Defaults (unveraendertes Verhalten).
"""

from __future__ import annotations

import json
import os
import re

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IntParameter, IStrategy, merge_informative_pair


def _opt() -> dict:
    try:
        return json.loads(os.environ.get("TBT_OPT_PARAMS", "") or "{}")
    except Exception:
        return {}


_TF_RE = re.compile(r"(\d+)\s*([mhd])")


def _tf_minutes(tf: str) -> int:
    m = _TF_RE.match(str(tf).lower().replace("min", "m"))
    if not m:
        return 10 ** 9
    n, u = int(m.group(1)), m.group(2)
    return n * (60 if u == "h" else 1440 if u == "d" else 1)


def _informative_tfs() -> list:
    """Hoehere Timeframes (Multi-TF-Bestaetigung) aus Env TBT_INFORMATIVE_TFS; opt-in."""
    raw = os.environ.get("TBT_INFORMATIVE_TFS", "") or ""
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(x) for x in v if x]
    except Exception:
        pass
    return [s.strip() for s in raw.replace(";", ",").split(",") if s.strip()]


def _merge_htf(strategy, dataframe, metadata):
    """Mergt den hoechsten informativen TF als SMA50-Trendfilter (Spalte htf_up_<tf>).
    Setzt strategy._htf_col oder None. Gibt das (ggf. erweiterte) DataFrame zurueck."""
    strategy._htf_col = None
    tfs = _informative_tfs()
    if not tfs or strategy.dp is None:
        return dataframe
    htf = sorted(tfs, key=_tf_minutes)[-1]
    inf = strategy.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=htf)
    if inf is None or not len(inf):
        return dataframe
    inf = inf.copy()
    inf["htf_up"] = (inf["close"] > inf["close"].rolling(50).mean()).astype(int)
    dataframe = merge_informative_pair(
        dataframe, inf[["date", "htf_up"]], strategy.timeframe, htf, ffill=True)
    strategy._htf_col = f"htf_up_{htf}"
    return dataframe


def _htf_gate(strategy, dataframe, cond, base_tag):
    """Gated die Entry-Bedingung auf den Higher-TF-Uptrend + setzt enter_tag."""
    col = getattr(strategy, "_htf_col", None)
    tag = base_tag
    if col and col in dataframe.columns:
        cond = cond & (dataframe[col] == 1)
        tag = base_tag + "+HTF"
    dataframe.loc[cond, "enter_long"] = 1
    dataframe.loc[cond, "enter_tag"] = tag
    return dataframe


class TrendFollowEma(IStrategy):
    """Einfaches EMA-Trendfolge-System mit RSI-Bestaetigung."""

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 0.06, "120": 0.03, "360": 0.015, "720": 0.0}
    stoploss = -0.08
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
    trailing_only_offset_is_reached = True
    process_only_new_candles = True
    startup_candle_count: int = 100

    ema_fast = IntParameter(8, 20, default=12, space="buy")
    ema_slow = IntParameter(21, 60, default=26, space="buy")
    rsi_period = IntParameter(7, 21, default=14, space="buy")
    rsi_entry_min = IntParameter(45, 60, default=50, space="buy")
    rsi_overbought = IntParameter(70, 85, default=75, space="buy")

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = _opt()
        try:
            if "stop_loss_pct" in p:
                self.stoploss = -abs(float(p["stop_loss_pct"])) / 100.0
            if "trailing_distance_pct" in p:
                self.trailing_stop_positive = abs(float(p["trailing_distance_pct"])) / 100.0
            if "trailing_start_pct" in p:
                self.trailing_stop_positive_offset = abs(float(p["trailing_start_pct"])) / 100.0
        except Exception:
            pass

    def informative_pairs(self):
        tfs = _informative_tfs()
        if not tfs or self.dp is None:
            return []
        return [(p, tf) for p in self.dp.current_whitelist() for tf in tfs]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=int(p.get("ema_fast", self.ema_fast.value)))
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=int(p.get("ema_slow", self.ema_slow.value)))
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=int(p.get("rsi_period", self.rsi_period.value)))
        # Makro-Trendfilter (gleiche TF, langer SMA): EMA-Cross-Longs nur im uebergeordneten
        # Aufwaertstrend. OPT-IN (default 0 = aus -> Live-Bots unveraendert). Bringt hier keinen
        # Edge (WF-PF ~0.34, Winrate ~20% -> EMA-Cross-Whipsaw strukturell nicht rentabel).
        macro = int(p.get("macro_sma_period", 0))
        dataframe["macro_sma"] = ta.SMA(dataframe, timeperiod=macro) if macro > 0 else dataframe["close"]
        dataframe = _merge_htf(self, dataframe, metadata)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        emin = int(_opt().get("rsi_entry_min", self.rsi_entry_min.value))
        cond = (
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
            & (dataframe["rsi"] > emin)
            & (dataframe["rsi"] < int(self.rsi_overbought.value))
            & (dataframe["volume"] > 0)
        )
        if int(_opt().get("macro_sma_period", 0)) > 0:
            cond = cond & (dataframe["close"] > dataframe["macro_sma"])
        return _htf_gate(self, dataframe, cond, "ema_cross")

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
            & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1
        return dataframe
