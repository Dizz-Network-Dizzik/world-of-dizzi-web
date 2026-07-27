"""DcaDip — DCA (gestaffeltes Nachkaufen / Dollar-Cost-Averaging), long-only, Spot.

Krypto-Klassiker: Erst-Einstieg per Dip-Signal (RSI-Oversold), dann gestaffelte
Safety-Orders bei weiteren Ruecksetzern (senkt den Einstand), Exit per Gesamt-ROI.
Begrenzte Anzahl Safety-Orders + weiter Stop kappen das Risiko (kein endloses Martingale).

Nutzt Freqtrades Position-Adjustment (``adjust_trade_position``): gleich grosse Safety-Orders,
je eine Stufe ``step_pct`` tiefer, bis ``max_safety_orders``. Parametrisierbar via
``TBT_OPT_PARAMS`` (Optimierungs-Backtest/Lern-Loop); Live nutzt Defaults bzw. opt_params.
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


class DcaDip(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = False
    position_adjustment_enable = True       # Safety-Orders (Nachkaufen) aktiv

    minimal_roi = {"0": 0.02}               # Gesamt-ROI Take-Profit (take_profit_pct)
    stoploss = -0.18                         # weiter Stop (DCA mittelt Dips) — per dca_stop_pct
    trailing_stop = False
    process_only_new_candles = True
    startup_candle_count: int = 50

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = _opt()
        self._max_so = max(0, _i(p, "max_safety_orders", 3))
        self._step = max(0.3, _f(p, "step_pct", 2.5))
        self.minimal_roi = {"0": round(abs(_f(p, "take_profit_pct", 2.0)) / 100.0, 5)}
        if "dca_stop_pct" in p:
            self.stoploss = -abs(_f(p, "dca_stop_pct", 18.0)) / 100.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=_i(p, "rsi_period", 14))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        oversold = _f(p, "rsi_oversold", 35)
        d = dataframe
        # Erst-Einstieg auf einen Ruecksetzer (RSI faellt unter Oversold-Schwelle).
        cond = (d["rsi"] < oversold) & (d["rsi"].shift(1) >= oversold) & (d["volume"] > 0)
        d.loc[cond, "enter_long"] = 1
        d.loc[cond, "enter_tag"] = "dca_initial"
        return d

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe  # Exit per Gesamt-ROI (minimal_roi) / Stop

    def adjust_trade_position(self, trade, current_time, current_rate, current_profit,
                              min_stake, max_stake, **kwargs):
        """Gestaffeltes Nachkaufen: fuegt eine gleich grosse Safety-Order hinzu, sobald der
        Verlust die naechste Stufe (n × step_pct unter dem Schnitt) erreicht — bis max_safety_orders."""
        try:
            filled = trade.nr_of_successful_entries
        except Exception:
            return None
        if filled > self._max_so:                       # alle Safety-Orders verbraucht
            return None
        if current_profit > -(filled * self._step) / 100.0:   # naechste Stufe noch nicht erreicht
            return None
        try:
            so_stake = trade.stake_amount / max(1, filled)   # gleich grosse SO (= Erst-Order-Groesse)
        except Exception:
            return None
        if max_stake and so_stake > max_stake:
            so_stake = max_stake
        if min_stake and so_stake < min_stake:
            return None
        return so_stake
