"""RsiDivergence — RSI-Divergenz-Scalping mit BESTÄTIGTEN Pivots, Futures.

Bullische Divergenz: der Preis macht ein tieferes Tief, der RSI aber ein höheres Tief
(Momentum-Erschöpfung der Abwärtsbewegung) → Long. Bärische Divergenz spiegelbildlich → Short.

KAUSAL/LOOKAHEAD-FREI (der heikle Punkt): ein Swing-Pivot bei Bar i gilt erst als „bestätigt",
wenn er das Minimum/Maximum über das ZENTRIERTE Fenster [i−k, i+k] ist — diese Bestätigung steht
frühestens bei Bar i+k fest. Die Engine emittiert den Pivot deshalb erst bei i+k (Lag k) und
vergleicht NUR bereits bestätigte Pivots; der Entry fällt auf die Bestätigungskerze mit
Turn-Bestätigung (Schlusskurs dreht). Kein Zukunftsblick.

Parametrisierbar via ``TBT_OPT_PARAMS`` (``rsi_period``/``pivot_lag``/``stop_loss_pct``/
``take_profit_pct``/``min_bars_between``); Live nutzt Defaults. Long + Short, optional Hebel (Futures).
"""

from __future__ import annotations


import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

from tbt_common import apply_cooldown, env_leverage, opt_params


def _divergence_signals(low, high, close, rsi, k: int):
    """Lookahead-freie Divergenz-Entries. Pivot bei i wird erst bei i+k bestätigt (zentriertes
    Fenster [i−k, i+k]); es werden nur bestätigte Pivots verglichen. Rückgabe: (long, short)
    Bool-Arrays mit Entry auf der Bestätigungskerze + Turn-Bestätigung (close dreht)."""
    n = len(close)
    longs = np.zeros(n, dtype=bool)
    shorts = np.zeros(n, dtype=bool)
    last_low = None    # (price, rsi) des zuletzt bestätigten Tief-Pivots
    last_high = None
    for t in range(2 * k, n):
        i = t - k      # Kandidat-Pivot-Bar (zentriert in [t-2k, t])
        win_lo = low[t - 2 * k:t + 1]
        win_hi = high[t - 2 * k:t + 1]
        if np.isnan(rsi[i]):
            continue
        # bestätigter Pivot-Tief: low[i] ist das Minimum des zentrierten Fensters
        if low[i] <= np.min(win_lo) + 1e-12:
            if last_low is not None and low[i] < last_low[0] and rsi[i] > last_low[1]:
                # bullische Divergenz bestätigt -> Long bei Turn-Bestätigung (close steigt)
                if close[t] > close[t - 1]:
                    longs[t] = True
            last_low = (low[i], rsi[i])
        # bestätigter Pivot-Hoch: high[i] ist das Maximum des zentrierten Fensters
        if high[i] >= np.max(win_hi) - 1e-12:
            if last_high is not None and high[i] > last_high[0] and rsi[i] < last_high[1]:
                if close[t] < close[t - 1]:
                    shorts[t] = True
            last_high = (high[i], rsi[i])
    return longs, shorts


class RsiDivergence(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True

    minimal_roi = {"0": 0.02}          # RR ~2:1 gegen den engen Stop
    stoploss = -0.01
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
        if "take_profit_pct" in p:
            try:
                self.minimal_roi = {"0": abs(float(p["take_profit_pct"])) / 100.0}
            except Exception:
                pass

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, side, **kwargs) -> float:
        return env_leverage(max_leverage, 2.0)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        d = dataframe
        d["rsi"] = ta.RSI(d, timeperiod=max(2, int(p.get("rsi_period", 14))))
        k = max(2, int(p.get("pivot_lag", 5)))
        longs, shorts = _divergence_signals(
            d["low"].values, d["high"].values, d["close"].values, d["rsi"].values, k)
        d["div_long"] = longs
        d["div_short"] = shorts
        return d

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        d = dataframe
        d.loc[d["div_long"] & (d["volume"] > 0), "enter_long"] = 1
        d.loc[d["div_long"] & (d["volume"] > 0), "enter_tag"] = "rsi_div_long"
        if self.can_short:
            d.loc[d["div_short"] & (d["volume"] > 0), "enter_short"] = 1
            d.loc[d["div_short"] & (d["volume"] > 0), "enter_tag"] = "rsi_div_short"
        gap = int(p.get("min_bars_between", 0) or 0)
        return apply_cooldown(d, gap, sides=("enter_long", "enter_short"))

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        d = dataframe
        # Exit per ROI/Stop; zusätzlich Gegen-Extrem des RSI (Momentum verbraucht).
        d.loc[d["rsi"] > 70, "exit_long"] = 1
        if self.can_short:
            d.loc[d["rsi"] < 30, "exit_short"] = 1
        return d
