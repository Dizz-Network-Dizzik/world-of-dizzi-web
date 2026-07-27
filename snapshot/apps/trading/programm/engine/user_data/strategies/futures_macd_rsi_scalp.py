"""FuturesMacdRsiScalp — Futures-Scalping (MACD-Kreuz + RSI-Filter), long-only, Hebel 3x.

Parametrisierbar via ``TBT_OPT_PARAMS`` (nur Optimierungs-Backtest); Live nutzt Defaults.
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
    col = getattr(strategy, "_htf_col", None)
    tag = base_tag
    if col and col in dataframe.columns:
        cond = cond & (dataframe[col] == 1)
        tag = base_tag + "+HTF"
    dataframe.loc[cond, "enter_long"] = 1
    dataframe.loc[cond, "enter_tag"] = tag
    return dataframe


def _apply_cooldown(strategy, dataframe):
    """Trade-Frequenz-Bremse (C2, opt-in via opt_param 'min_bars_between'): unterdrueckt
    Entry-Signale, die weniger als N Kerzen nach dem letzten ZUGELASSENEN Entry kommen.
    Default 0 = aus -> laufende Live-Bots (ohne opt_params) unveraendert. Gegen Overtrading."""
    p = _opt()
    try:
        gap = int(p.get("min_bars_between", 0) or 0)
    except Exception:
        gap = 0
    if gap <= 0 or "enter_long" not in dataframe.columns:
        return dataframe
    el = dataframe["enter_long"].fillna(0).astype(int).tolist()
    last = -10 ** 9
    for i, v in enumerate(el):
        if v == 1:
            if i - last < gap:
                el[i] = 0
            else:
                last = i
    dataframe["enter_long"] = el
    if "enter_tag" in dataframe.columns:
        dataframe.loc[dataframe["enter_long"] != 1, "enter_tag"] = None
    return dataframe


class FuturesMacdRsiScalp(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True   # Futures: short beim Bear-MACD-Cross (Momentum unten)

    minimal_roi = {"0": 0.025, "30": 0.012, "90": 0.0}
    stoploss = -0.04
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True
    process_only_new_candles = True
    startup_candle_count: int = 60

    rsi_min = IntParameter(48, 60, default=52, space="buy")

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = _opt()
        if "stop_loss_pct" in p:
            try:
                self.stoploss = -abs(float(p["stop_loss_pct"])) / 100.0
            except Exception:
                pass

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, side, **kwargs) -> float:
        try:
            u = float(os.environ.get("TBT_LEVERAGE", "") or 0)
        except Exception:
            u = 0.0
        base = u if u > 0 else 3.0
        return min(base, 5.0, float(max_leverage) or base)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        macd = ta.MACD(
            dataframe,
            fastperiod=int(p.get("macd_fast", 12)),
            slowperiod=int(p.get("macd_slow", 26)),
            signalperiod=int(p.get("macd_signal", 9)),
        )
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=int(p.get("rsi_period", 14)))
        # Makro-Trendfilter (gleiche TF, langer SMA): Long-Scalps nur im uebergeordneten Aufwaertstrend.
        # OPT-IN (default 0 = aus -> Live-Bots unveraendert). Gegen Cross-Whipsaw in Abwaerts-/Chop-Phasen.
        macro = int(p.get("macro_sma_period", 0))
        dataframe["macro_sma"] = ta.SMA(dataframe, timeperiod=macro) if macro > 0 else dataframe["close"]
        dataframe = _merge_htf(self, dataframe, metadata)
        return dataframe

    def informative_pairs(self):
        tfs = _informative_tfs()
        if not tfs or self.dp is None:
            return []
        return [(p, tf) for p in self.dp.current_whitelist() for tf in tfs]

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        rmin = int(p.get("rsi_buy_threshold", self.rsi_min.value))  # Mindest-RSI fuer Long
        macro = int(p.get("macro_sma_period", 0))
        bull = (dataframe["macd"] > dataframe["macdsignal"]) & (dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1))
        bear = (dataframe["macd"] < dataframe["macdsignal"]) & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1))
        long_cond = bull & (dataframe["rsi"] > rmin) & (dataframe["volume"] > 0)
        short_cond = bear & (dataframe["rsi"] < (100 - rmin)) & (dataframe["volume"] > 0)
        if macro > 0:
            long_cond = long_cond & (dataframe["close"] > dataframe["macro_sma"])
            short_cond = short_cond & (dataframe["close"] < dataframe["macro_sma"])
        dataframe = _apply_cooldown(self, _htf_gate(self, dataframe, long_cond, "macd_rsi"))
        if self.can_short:                  # Short-Spiegel: Bear-Cross + Momentum unten
            dataframe.loc[short_cond, "enter_short"] = 1
            dataframe.loc[short_cond, "enter_tag"] = "macd_rsi_short"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["macd"] < dataframe["macdsignal"])
            & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1)),
            "exit_long",
        ] = 1
        if self.can_short:                  # Short schliessen beim Bull-Cross
            dataframe.loc[
                (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1)),
                "exit_short",
            ] = 1
        return dataframe
