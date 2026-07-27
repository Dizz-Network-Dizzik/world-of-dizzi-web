"""UtBotEma — UT-Bot (ATR-Trailing-Stop) + EMA-Trendfilter, Futures.

UT Bot (Yo_adriiiiaan): ein ATR-basierter Trailing-Stop, der mit dem Preis nachzieht; ein
Signal entsteht, wenn der Schlusskurs den Trailing-Stop von der falschen Seite kreuzt
(Close kreuzt über den Stop = Buy, darunter = Sell). Zusätzlicher EMA-Filter (fast > slow für
Long, fast < slow für Short) hält die Signale auf der Trendseite. Exit per Gegensignal; %-Stop via ``stoploss``.

Lookahead-frei: der ATR-Trailing-Stop trägt sich vorwärts (carry-forward) und nutzt ausschließlich
vergangene/aktuelle Werte; das Kreuz wird gegen die Vorkerze geprüft; Entry ab der Folgekerze.
Parametrisierbar via ``TBT_OPT_PARAMS`` (``key_value``/``atr_period``/``ema_fast``/``ema_slow``/
``stop_loss_pct``/``min_bars_between``); Live nutzt Defaults. Long + Short, optional Hebel (Futures).
"""

from __future__ import annotations


import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

from tbt_common import apply_cooldown, env_leverage, opt_params


def _ut_trailing(close: np.ndarray, atr: np.ndarray, key: float) -> np.ndarray:
    """UT-Bot ATR-Trailing-Stop (lookahead-frei, carry-forward).

    Standard-Algorithmus: nLoss = key·ATR. Der Stop zieht in Trendrichtung nach und springt
    erst auf die Gegenseite, wenn der Schlusskurs ihn durchbricht. Nutzt nur Werte bis t.
    """
    n = len(close)
    stop = np.full(n, np.nan)
    if n == 0:
        return stop
    i0 = 0
    while i0 < n and np.isnan(atr[i0]):
        i0 += 1
    if i0 >= n:
        return stop
    stop[i0] = close[i0] - key * atr[i0]      # Start im Aufwärtsmodus (Stop unter dem Preis)
    for i in range(i0 + 1, n):
        if np.isnan(atr[i]):
            stop[i] = stop[i - 1]
            continue
        nloss = key * atr[i]
        prev = stop[i - 1]
        c, cp = close[i], close[i - 1]
        if c > prev and cp > prev:            # über Stop bleibend -> Stop zieht nach oben nach
            stop[i] = max(prev, c - nloss)
        elif c < prev and cp < prev:          # unter Stop bleibend -> Stop zieht nach unten nach
            stop[i] = min(prev, c + nloss)
        elif c > prev:                        # von unten nach oben gekreuzt -> Flip Long-Stop
            stop[i] = c - nloss
        else:                                 # von oben nach unten gekreuzt -> Flip Short-Stop
            stop[i] = c + nloss
    return stop


class UtBotEma(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True

    minimal_roi = {"0": 0.06}
    stoploss = -0.02
    trailing_stop = False
    process_only_new_candles = True
    startup_candle_count: int = 60
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
        key = float(p.get("key_value", 1.0))
        atr_period = max(2, int(p.get("atr_period", 10)))
        ema_fast = max(2, int(p.get("ema_fast", 9)))
        ema_slow = max(ema_fast + 1, int(p.get("ema_slow", 21)))
        d = dataframe
        atr = ta.ATR(d, timeperiod=atr_period)
        d["ut_stop"] = _ut_trailing(d["close"].values, atr.values, key)
        d["ema_fast"] = ta.EMA(d, timeperiod=ema_fast)
        d["ema_slow"] = ta.EMA(d, timeperiod=ema_slow)
        return d

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        d = dataframe
        c, cp = d["close"], d["close"].shift(1)
        st, stp = d["ut_stop"], d["ut_stop"].shift(1)
        cross_up = (cp <= stp) & (c > st)        # Close kreuzt über den Trailing-Stop = Buy
        cross_dn = (cp >= stp) & (c < st)        # Close kreuzt unter den Trailing-Stop = Sell
        up_trend = d["ema_fast"] > d["ema_slow"]
        long_cond = cross_up & up_trend & (d["volume"] > 0)
        short_cond = cross_dn & (~up_trend) & (d["volume"] > 0)
        d.loc[long_cond, "enter_long"] = 1
        d.loc[long_cond, "enter_tag"] = "utbot_long"
        if self.can_short:
            d.loc[short_cond, "enter_short"] = 1
            d.loc[short_cond, "enter_tag"] = "utbot_short"
        gap = int(p.get("min_bars_between", 0) or 0)
        return apply_cooldown(d, gap, sides=("enter_long", "enter_short"))

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        d = dataframe
        c, cp = d["close"], d["close"].shift(1)
        st, stp = d["ut_stop"], d["ut_stop"].shift(1)
        d.loc[(cp >= stp) & (c < st), "exit_long"] = 1     # Stop nach unten gekreuzt schließt Long
        if self.can_short:
            d.loc[(cp <= stp) & (c > st), "exit_short"] = 1  # Stop nach oben gekreuzt schließt Short
        return d
