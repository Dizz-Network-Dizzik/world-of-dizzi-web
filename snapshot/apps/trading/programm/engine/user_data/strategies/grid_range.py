"""GridRange — Grid/Raster-Trading (range-gebundene Mean-Reversion), long-only, Spot.

Krypto-Archetyp: nutzt die 24/7-Volatilitaet in Seitwaerts-/Range-Phasen. Kauft gestaffelt
Dips unterhalb einer gleitenden Referenz (Raster-Stufen) und verkauft je einen Raster-Schritt
hoeher (kleiner, fixer Take-Profit = Grid-Step). Begrenzt durch eine Range; bricht der Preis
die Range deutlich nach unten, greift der Stop (range_stop_pct).

In Freqtrades Ein-Trade-pro-Pair-Modell als „Dip kaufen / Grid-Step-Gewinn verkaufen" umgesetzt
(je Pair eine Position; Raster-Breite ueber viele Pairs/Zeit). Parametrisierbar via
``TBT_OPT_PARAMS`` (Optimierungs-Backtest/Lern-Loop); Live nutzt Defaults bzw. die am Bot
angewandten ``opt_params``.
"""

from __future__ import annotations

import json
import os

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


def _opt() -> dict:
    try:
        return json.loads(os.environ.get("TBT_OPT_PARAMS", "") or "{}")
    except Exception:
        return {}


def _f(p: dict, k: str, d: float) -> float:
    try:
        return float(p.get(k, d))
    except (TypeError, ValueError):
        return d


def _i(p: dict, k: str, d: int) -> int:
    try:
        return int(p.get(k, d))
    except (TypeError, ValueError):
        return d


class GridRange(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = False

    minimal_roi = {"0": 0.012}     # Grid-Step Take-Profit (wird aus span/levels gesetzt)
    stoploss = -0.03               # Range-Bruch (per range_stop_pct ueberschreibbar)
    trailing_stop = False
    process_only_new_candles = True
    startup_candle_count: int = 80

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = _opt()
        levels = max(2, _i(p, "grid_levels", 7))
        span = max(1.0, _f(p, "grid_span_pct", 7.0))
        step = max(0.2, span / levels)            # ein Raster-Schritt in %
        self._grid_step = step
        self._grid_span = span
        self.minimal_roi = {"0": round(step / 100.0, 5)}   # Take-Profit = 1 Grid-Step
        if "range_stop_pct" in p:
            self.stoploss = -abs(_f(p, "range_stop_pct", 3.0)) / 100.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        ref = _i(p, "ref_period", 60)
        dataframe["ref"] = ta.SMA(dataframe, timeperiod=ref)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        # Abstand des Preises UNTER die Referenz in % (positiv = unter der Referenz).
        dataframe["below_pct"] = (dataframe["ref"] - dataframe["close"]) / dataframe["ref"] * 100.0
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        step = getattr(self, "_grid_step", 0.6)
        span = getattr(self, "_grid_span", 6.0)
        rsi_floor = _f(p, "rsi_floor", 33)
        d = dataframe
        # Long, wenn der Preis ~1 Grid-Step unter die Referenz gefallen ist (Dip kaufen),
        # noch INNERHALB der Range (kein freier Fall) und RSI nicht extrem schwach. Die
        # Crossing-Bedingung (vorher < step) vermeidet Entry-Spam auf jeder Kerze.
        cond = (
            (d["below_pct"] >= step)
            & (d["below_pct"] <= span)
            & (d["below_pct"].shift(1) < step)
            & (d["rsi"] > rsi_floor)
            & (d["volume"] > 0)
        )
        d.loc[cond, "enter_long"] = 1
        d.loc[cond, "enter_tag"] = "grid_dip"
        return d

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        d = dataframe
        # Exit primaer per minimal_roi (Grid-Step-Gewinn). Zusatz: zurueck UEBER der Referenz
        # -> einen Schritt hoeher verkauft (Grid-Logik), Gewinn sichern.
        d.loc[d["close"] > d["ref"], "exit_long"] = 1
        return d
