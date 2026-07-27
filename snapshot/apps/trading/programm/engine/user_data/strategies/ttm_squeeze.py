"""TtmSqueeze — TTM-Squeeze-Momentum-Release (Volatilitäts-Kompression, LazyBear/Carter), Futures.

Idee (Carter „TTM Squeeze"): liegen die Bollinger-Bänder INNERHALB der Keltner-Kanäle, ist der
Markt komprimiert/„geladen" (Squeeze ON). Beim LÖSEN der Kompression (BB verlassen KC wieder)
wird in Richtung des Momentum-Histogramms eingestiegen: Momentum > 0 → long, < 0 → short.
Exit, wenn das Momentum-Histogramm gegen die Position dreht; ATR-Stop via ``stoploss``.

Lookahead-frei: Squeeze-Release = ``squeeze_on(t-1) & ~squeeze_on(t)`` (nur Vergangenheit/Gegenwart);
das Momentum ist eine lineare Regression über das abgeschlossene Fenster bis t; Entry ab Folgekerze.
Parametrisierbar via ``TBT_OPT_PARAMS`` (``bb_period``/``bb_std``/``kc_mult``/``mom_period``/
``stop_loss_pct``/``min_bars_between``); Live nutzt Defaults. Long + Short, optional Hebel (Futures).
"""

from __future__ import annotations

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

from tbt_common import apply_cooldown, env_leverage, opt_params


class TtmSqueeze(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True   # Futures: Short beim Abwärts-Release (Momentum < 0)

    minimal_roi = {"0": 0.10}          # Release laufen lassen; Primär-Exit per Momentum-Dreh/Stop
    stoploss = -0.025
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
        bb_period = max(5, int(p.get("bb_period", 20)))
        bb_std = float(p.get("bb_std", 2.0))
        kc_mult = float(p.get("kc_mult", 1.5))
        mom_period = max(5, int(p.get("mom_period", 20)))
        d = dataframe

        # Bollinger-Bänder
        basis = ta.SMA(d, timeperiod=bb_period)
        dev = bb_std * d["close"].rolling(bb_period).std(ddof=0)
        d["bb_upper"] = basis + dev
        d["bb_lower"] = basis - dev
        # Keltner-Kanäle (EMA ± kc_mult·ATR)
        ema = ta.EMA(d, timeperiod=bb_period)
        atr = ta.ATR(d, timeperiod=bb_period)
        d["kc_upper"] = ema + kc_mult * atr
        d["kc_lower"] = ema - kc_mult * atr
        # Squeeze ON = BB INNERHALB KC (Kompression)
        d["squeeze_on"] = (d["bb_lower"] > d["kc_lower"]) & (d["bb_upper"] < d["kc_upper"])
        # TTM-Momentum (LazyBear): lineare Regression von (close − Mittel aus Donchian-Mitte & SMA)
        hh = d["high"].rolling(mom_period).max()
        ll = d["low"].rolling(mom_period).min()
        mid = ((hh + ll) / 2.0 + ta.SMA(d, timeperiod=mom_period)) / 2.0
        d["ttm_src"] = d["close"] - mid
        d["ttm_mom"] = ta.LINEARREG(d["ttm_src"], timeperiod=mom_period)
        return d

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        d = dataframe
        prev_sq = d["squeeze_on"].shift(1).fillna(False).astype(bool)
        # Release = war komprimiert (t-1), jetzt gelöst (t)
        release = prev_sq & (~d["squeeze_on"].fillna(False).astype(bool)) & (d["volume"] > 0)
        long_cond = release & (d["ttm_mom"] > 0)
        short_cond = release & (d["ttm_mom"] < 0)
        d.loc[long_cond, "enter_long"] = 1
        d.loc[long_cond, "enter_tag"] = "ttm_release_long"
        if self.can_short:
            d.loc[short_cond, "enter_short"] = 1
            d.loc[short_cond, "enter_tag"] = "ttm_release_short"
        gap = int(p.get("min_bars_between", 0) or 0)
        return apply_cooldown(d, gap, sides=("enter_long", "enter_short"))

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        d = dataframe
        # Exit, wenn das Momentum-Histogramm gegen die Position dreht.
        d.loc[d["ttm_mom"] < 0, "exit_long"] = 1
        if self.can_short:
            d.loc[d["ttm_mom"] > 0, "exit_short"] = 1
        return d
