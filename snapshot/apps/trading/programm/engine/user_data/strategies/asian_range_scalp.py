"""AsianRangeScalp — Session-Range-Fade (Asian Killzone), Futures.

Gegenstück zum Session-Open-BREAKOUT: die ruhige, enge Range einer Session (default Asia,
00:00 UTC) wird NICHT ausgebrochen, sondern GEFADET. Die ersten ``range_min`` Minuten nach
Session-Open definieren High/Low; danach im Handelsfenster: Long, wenn der Preis im UNTEREN
Drittel der Range liegt UND RSI/Stochastic überverkauft sind (Reversion zur Range-Mitte);
Short im OBEREN Drittel bei überkauften Oszillatoren. Zwangs-Exit am Fensterende (kein Carry).

Lookahead-frei: die Range-Extrema je Session-Tag werden nur aus den ABGESCHLOSSENEN Range-Kerzen
gebildet (``where(in_range).groupby(tag).transform``), RSI/Stochastic sind kausale talib-Indikatoren;
Entry ab der Folgekerze. Parametrisierbar via ``TBT_OPT_PARAMS`` (``session``/``range_min``/
``session_window_min``/``rsi_oversold``/``stoch_oversold``/``stop_loss_pct``); Live nutzt Defaults.
Long + Short, optional Hebel (Futures).
"""

from __future__ import annotations

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

from tbt_common import (OPEN_HOURS, env_leverage, opening_range_bounds,
                        opt_float, opt_int, opt_params)


class AsianRangeScalp(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True

    minimal_roi = {"0": 0.02}          # kleines Scalp-Ziel; Primär-Exit per Mitte/Fensterende/Stop
    stoploss = -0.012                  # eng — Stop knapp jenseits des Range-Extrems
    trailing_stop = False
    process_only_new_candles = True
    startup_candle_count: int = 60
    use_exit_signal = True

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = opt_params()
        if "stop_loss_pct" in p:
            self.stoploss = -abs(opt_float(p, "stop_loss_pct", 1.2)) / 100.0

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, side, **kwargs) -> float:
        return env_leverage(max_leverage, 2.0)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        session = opt_int(p, "session", 0)           # default Asia
        open_hour = OPEN_HOURS.get(session, 0)
        range_min = max(5, opt_int(p, "range_min", 30))
        d = dataframe

        # Session-Opening-Range (geteilter, lookahead-freier Helfer): Minuten seit Open + High/Low
        # der ersten range_min Minuten je Session-Tag.
        min_since_open, rng_high, rng_low = opening_range_bounds(d, open_hour, range_min)
        d["min_since_open"] = min_since_open
        d["rng_high"] = rng_high
        d["rng_low"] = rng_low
        d["rng_mid"] = (d["rng_high"] + d["rng_low"]) / 2.0
        d["rsi"] = ta.RSI(d, timeperiod=opt_int(p, "rsi_period", 14))
        stoch = ta.STOCH(d, fastk_period=14, slowk_period=3, slowd_period=3)
        d["stoch_k"] = stoch["slowk"]
        return d

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        range_min = max(5, opt_int(p, "range_min", 30))
        window = max(range_min + 1, opt_int(p, "session_window_min", 180))
        rsi_os = opt_float(p, "rsi_oversold", 30)
        rsi_ob = 100.0 - rsi_os
        stoch_os = opt_float(p, "stoch_oversold", 20)
        stoch_ob = 100.0 - stoch_os
        d = dataframe

        in_window = (d["min_since_open"] >= range_min) & (d["min_since_open"] < window)
        valid = in_window & d["rng_high"].notna() & (d["rng_high"] > d["rng_low"]) & (d["volume"] > 0)
        third = (d["rng_high"] - d["rng_low"]) / 3.0
        lower_third = d["close"] <= (d["rng_low"] + third)
        upper_third = d["close"] >= (d["rng_high"] - third)
        long_cond = valid & lower_third & (d["rsi"] < rsi_os) & (d["stoch_k"] < stoch_os)
        short_cond = valid & upper_third & (d["rsi"] > rsi_ob) & (d["stoch_k"] > stoch_ob)
        d.loc[long_cond, "enter_long"] = 1
        d.loc[long_cond, "enter_tag"] = "asia_range_fade_long"
        if self.can_short:
            d.loc[short_cond, "enter_short"] = 1
            d.loc[short_cond, "enter_tag"] = "asia_range_fade_short"
        return d

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        range_min = max(5, opt_int(p, "range_min", 30))
        window = max(range_min + 1, opt_int(p, "session_window_min", 180))
        d = dataframe
        # Reversion-Ziel = Range-Mitte; zusätzlich Zwangs-Exit am Fensterende.
        reached_mid_long = d["close"] >= d["rng_mid"]
        reached_mid_short = d["close"] <= d["rng_mid"]
        window_end = d["min_since_open"] >= window
        d.loc[reached_mid_long | window_end, "exit_long"] = 1
        if self.can_short:
            d.loc[reached_mid_short | window_end, "exit_short"] = 1
        return d
