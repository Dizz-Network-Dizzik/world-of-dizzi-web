"""Supertrend — ATR-basierte Trendfolge (Supertrend-Indikator), long-only, Futures 3x.

Selektiver als EMA-/MACD-Kreuz: bleibt im vorherrschenden Trend und wechselt die Richtung
erst beim Supertrend-Flip (Schlusskurs durchbricht das gegenueberliegende ATR-Band). Klassik
ATR(10)*3.0; Scalping z. B. ATR(7)*2.0. Parametrisierbar via ``TBT_OPT_PARAMS`` (``atr_period``,
``atr_mult``, ``macro_sma_period``, ``stop_loss_pct``, ``min_bars_between``). Live nutzt Defaults.

Beleg: Supertrend ist breit dokumentiert; BTC-Backtests (ATR10*3) zeigen ~33 % CAGR bei deutlich
geringerem Drawdown als Buy&Hold und ~50 % Marktzeit (boringedge / quantifiedstrategies).
Lookahead-frei: Supertrend(t) nutzt ATR(t)/Close(t)/Supertrend(t-1); Entry ab der Folgekerze.
"""

from __future__ import annotations

import json
import os

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


def _opt() -> dict:
    try:
        return json.loads(os.environ.get("TBT_OPT_PARAMS", "") or "{}")
    except Exception:
        return {}


def _apply_cooldown(dataframe: DataFrame, gap: int) -> DataFrame:
    """Trade-Frequenz-Bremse (opt-in via opt_param 'min_bars_between'): unterdrueckt Entry-Signale,
    die weniger als N Kerzen nach dem letzten ZUGELASSENEN Entry kommen. 0 = aus (Default)."""
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


def _supertrend_up(high, low, close, atr, mult: float):
    """Supertrend-Richtung (True = Aufwaerts) nach dem Standard-Algorithmus, lookahead-frei.

    Final-Bands tragen sich vorwaerts (carry-forward); der Trend kippt, wenn der Schlusskurs das
    aktive Band durchbricht. Verwendet ausschliesslich vergangene/aktuelle Werte (kein Zukunftsblick).
    """
    n = len(close)
    up = np.zeros(n, dtype=bool)
    if n == 0:
        return up
    hl2 = (high + low) / 2.0
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    final_up = np.full(n, np.nan)
    final_lo = np.full(n, np.nan)
    start = 0
    while start < n and (np.isnan(atr[start]) or np.isnan(close[start])):
        start += 1
    if start >= n:
        return up
    final_up[start] = upper[start]
    final_lo[start] = lower[start]
    up[start] = True  # Start neutral im Aufwaertstrend; eingeschwungen nach wenigen Kerzen
    for i in range(start + 1, n):
        if np.isnan(atr[i]):
            up[i] = up[i - 1]
            final_up[i] = final_up[i - 1]
            final_lo[i] = final_lo[i - 1]
            continue
        final_up[i] = (upper[i] if (upper[i] < final_up[i - 1] or close[i - 1] > final_up[i - 1])
                       else final_up[i - 1])
        final_lo[i] = (lower[i] if (lower[i] > final_lo[i - 1] or close[i - 1] < final_lo[i - 1])
                       else final_lo[i - 1])
        if up[i - 1]:                       # war Aufwaerts (Stop = unteres Band)
            up[i] = close[i] >= final_lo[i]
        else:                               # war Abwaerts (Stop = oberes Band)
            up[i] = close[i] > final_up[i]
    return up


class Supertrend(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True   # Futures: short beim Abwaerts-Flip (greift im trend_down)

    minimal_roi = {"0": 0.30}          # locker: Trend laufen lassen, Exit primaer per Flip/Stop
    stoploss = -0.06
    trailing_stop = False
    process_only_new_candles = True
    startup_candle_count: int = 100

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
        period = max(2, int(p.get("atr_period", 10)))
        mult = float(p.get("atr_mult", 3.0))
        atr = ta.ATR(dataframe, timeperiod=period)
        dataframe["atr"] = atr
        dataframe["st_up"] = _supertrend_up(
            dataframe["high"].values, dataframe["low"].values,
            dataframe["close"].values, atr.values, mult)
        # Makro-Trendfilter (gleiche TF, langer SMA): Long-Flips nur im uebergeordneten
        # Aufwaertstrend. OPT-IN (default 0 = aus -> Live-Bots unveraendert).
        macro = int(p.get("macro_sma_period", 0))
        dataframe["macro_sma"] = ta.SMA(dataframe, timeperiod=macro) if macro > 0 else dataframe["close"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        macro = int(p.get("macro_sma_period", 0))
        prev_up = dataframe["st_up"].shift(1).fillna(False).astype(bool)
        long_cond = dataframe["st_up"] & (~prev_up) & (dataframe["volume"] > 0)
        short_cond = (~dataframe["st_up"]) & prev_up & (dataframe["volume"] > 0)
        if macro > 0:                       # Makro-Filter: Long nur im Aufwaerts-, Short nur im Abwaertstrend
            long_cond = long_cond & (dataframe["close"] > dataframe["macro_sma"])
            short_cond = short_cond & (dataframe["close"] < dataframe["macro_sma"])
        dataframe.loc[long_cond, "enter_long"] = 1
        dataframe.loc[long_cond, "enter_tag"] = "supertrend_flip"
        if self.can_short:                  # Short-Spiegel: Einstieg beim Abwaerts-Flip
            dataframe.loc[short_cond, "enter_short"] = 1
            dataframe.loc[short_cond, "enter_tag"] = "supertrend_flip_short"
        gap = int(p.get("min_bars_between", 0) or 0)
        return _apply_cooldown(dataframe, gap)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        prev_up = dataframe["st_up"].shift(1).fillna(False).astype(bool)
        dataframe.loc[(~dataframe["st_up"]) & prev_up, "exit_long"] = 1
        if self.can_short:                  # Short schliessen, wenn der Trend wieder nach oben dreht
            dataframe.loc[dataframe["st_up"] & (~prev_up), "exit_short"] = 1
        return dataframe
