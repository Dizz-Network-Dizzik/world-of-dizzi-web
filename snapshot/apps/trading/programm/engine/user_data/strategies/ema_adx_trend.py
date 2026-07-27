"""EmaAdxTrend — EMA-Crossover-Trendfolge mit ADX-Trendstärke-Filter, Futures.

Klassische EMA(9/21)-Trendfolge, aber Entries NUR wenn ADX die Trendstärke bestätigt
(ADX > adx_min) — das filtert die teuren Fehlsignale in richtungslosen Seitwärtsphasen,
in denen ein nackter EMA-Cross am häufigsten sägt. Long beim Aufwärts-Cross + starkem Trend,
Short (Futures) beim Abwärts-Cross + starkem Trend. Exit per Gegen-Cross; ATR-/%-Stop via ``stoploss``.

Lookahead-frei: der Cross wird gegen die VORKERZE geprüft (``shift(1)``), ADX/EMA sind kausale
talib-Indikatoren; Entry ab der Folgekerze. Parametrisierbar via ``TBT_OPT_PARAMS``
(``ema_fast``/``ema_slow``/``adx_min``/``adx_period``/``stop_loss_pct``/``min_bars_between``);
Live nutzt Defaults. Long + Short, optional Hebel (Futures).
"""

from __future__ import annotations

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

from tbt_common import apply_cooldown, env_leverage, opt_params


class EmaAdxTrend(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True

    minimal_roi = {"0": 0.20}          # Trend laufen lassen; Exit primär per Gegen-Cross/Stop
    stoploss = -0.05
    trailing_stop = False
    process_only_new_candles = True
    startup_candle_count: int = 80
    use_exit_signal = True

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = opt_params()
        if "stop_loss_pct" in p:
            try:
                self.stoploss = -abs(float(p["stop_loss_pct"])) / 100.0
            except Exception:
                pass

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, side, **kwargs) -> float:
        return env_leverage(max_leverage, 3.0)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        ema_fast = max(2, int(p.get("ema_fast", 9)))
        ema_slow = max(ema_fast + 1, int(p.get("ema_slow", 21)))
        adx_period = max(2, int(p.get("adx_period", 14)))
        d = dataframe
        d["ema_fast"] = ta.EMA(d, timeperiod=ema_fast)
        d["ema_slow"] = ta.EMA(d, timeperiod=ema_slow)
        d["adx"] = ta.ADX(d, timeperiod=adx_period)
        return d

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        adx_min = float(p.get("adx_min", 25))
        d = dataframe
        f, s = d["ema_fast"], d["ema_slow"]
        fp, sp = f.shift(1), s.shift(1)
        cross_up = (fp <= sp) & (f > s)
        cross_dn = (fp >= sp) & (f < s)
        strong = d["adx"] > adx_min
        long_cond = cross_up & strong & (d["volume"] > 0)
        short_cond = cross_dn & strong & (d["volume"] > 0)
        d.loc[long_cond, "enter_long"] = 1
        d.loc[long_cond, "enter_tag"] = "ema_adx_long"
        if self.can_short:
            d.loc[short_cond, "enter_short"] = 1
            d.loc[short_cond, "enter_tag"] = "ema_adx_short"
        gap = int(p.get("min_bars_between", 0) or 0)
        return apply_cooldown(d, gap, sides=("enter_long", "enter_short"))

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        d = dataframe
        f, s = d["ema_fast"], d["ema_slow"]
        fp, sp = f.shift(1), s.shift(1)
        d.loc[(fp >= sp) & (f < s), "exit_long"] = 1       # Abwärts-Cross schließt Long
        if self.can_short:
            d.loc[(fp <= sp) & (f > s), "exit_short"] = 1   # Aufwärts-Cross schließt Short
        return d
