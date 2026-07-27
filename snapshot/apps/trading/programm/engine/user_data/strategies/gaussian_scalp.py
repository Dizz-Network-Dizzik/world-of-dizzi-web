"""GaussianScalp — Ehlers-Gauß-Filter + SMA-Trendfilter + PMO-Oszillator, Futures.

YouTube-/Backtest-Strategie: ein Ehlers-Gauß-Filter (mehrpoliger Tiefpass, glatt + geringe Lag)
liefert die Richtung (Filter-Slope), ein langer SMA(149) den übergeordneten Trend-Bias, der PMO
(Price Momentum Oscillator) die Momentum-Bestätigung. Long, wenn Filter dreht hoch UND Preis > SMA
UND PMO > 0; Short spiegelbildlich. Exit per Filter-Gegendreh; RR-/%-Stop via ``stoploss``/``roi``.

Lookahead-frei: der Gauß-Filter ist ein REKURSIVER IIR (nutzt nur vergangene Filterwerte + den
aktuellen Schlusskurs); SMA/PMO/Slope sind kausal; Entry ab der Folgekerze. Parametrisierbar via
``TBT_OPT_PARAMS`` (``gauss_period``/``gauss_poles``/``sma_period``/``stop_loss_pct``/
``take_profit_pct``/``min_bars_between``); Live nutzt Defaults. Long + Short, optional Hebel.
"""

from __future__ import annotations

import math

import numpy as np
import talib.abstract as ta
from pandas import DataFrame, Series

from freqtrade.strategy import IStrategy

from tbt_common import apply_cooldown, env_leverage, opt_params


def _gaussian_filter(src: np.ndarray, period: int, poles: int) -> np.ndarray:
    """Ehlers' N-Pol-Gauß-Filter (rekursiv, kausal). Koeffizienten nach Ehlers:
    beta = (1−cos(2π/period)) / (2^(1/poles) − 1);  alpha = −beta + sqrt(beta²+2β).
    Implementiert für 1–4 Pole; höhere Pole = glatter, mehr Lag. Nutzt nur Werte bis i."""
    n = len(src)
    out = np.array(src, dtype=float)
    poles = max(1, min(4, int(poles)))
    if n < poles + 1 or period < 2:
        return out
    beta = (1.0 - math.cos(2.0 * math.pi / period)) / (2.0 ** (1.0 / poles) - 1.0)
    alpha = -beta + math.sqrt(beta * beta + 2.0 * beta)
    a = alpha
    g = 1.0 - a
    # Binomial-Koeffizienten der (1−α)·z^-1-Rekursion je Polzahl.
    coeffs = {
        1: [g],
        2: [2 * g, -g ** 2],
        3: [3 * g, -3 * g ** 2, g ** 3],
        4: [4 * g, -6 * g ** 2, 4 * g ** 3, -g ** 4],
    }[poles]
    gain = a ** poles
    for i in range(n):
        if i < poles or np.isnan(src[i]):
            continue
        val = gain * src[i]
        for j, c in enumerate(coeffs, start=1):
            val += c * out[i - j]
        out[i] = val
    return out


def _ema_alpha(series: Series, n: int) -> Series:
    """Custom-EMA mit Glättungsfaktor 2/n (PMO-Konvention, nicht talib 2/(n+1))."""
    return series.ewm(alpha=2.0 / max(1, n), adjust=False).mean()


class GaussianScalp(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True

    minimal_roi = {"0": 0.025}
    stoploss = -0.018
    trailing_stop = False
    process_only_new_candles = True
    startup_candle_count: int = 200          # SMA(149) + Filter-/PMO-Einschwingen
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
        period = max(2, int(p.get("gauss_period", 20)))
        poles = max(1, min(4, int(p.get("gauss_poles", 4))))
        sma_period = max(5, int(p.get("sma_period", 149)))
        d = dataframe
        d["gauss"] = _gaussian_filter(d["close"].values, period, poles)
        d["sma"] = ta.SMA(d, timeperiod=sma_period)
        # PMO: doppelt geglättete ROC (×10), Konvention 2/35 dann 2/20.
        roc = (d["close"] / d["close"].shift(1) - 1.0) * 100.0
        d["pmo"] = _ema_alpha(_ema_alpha(roc, 35) * 10.0, 20)
        return d

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = opt_params()
        d = dataframe
        g1, g2 = d["gauss"].shift(1), d["gauss"].shift(2)
        turn_up = (d["gauss"] > g1) & (g1 <= g2)        # Filter-Tief: Slope dreht von ab- auf aufwärts
        turn_dn = (d["gauss"] < g1) & (g1 >= g2)        # Filter-Hoch: Slope dreht von auf- auf abwärts
        long_cond = turn_up & (d["close"] > d["sma"]) & (d["pmo"] > 0) & (d["volume"] > 0)
        short_cond = turn_dn & (d["close"] < d["sma"]) & (d["pmo"] < 0) & (d["volume"] > 0)
        d.loc[long_cond, "enter_long"] = 1
        d.loc[long_cond, "enter_tag"] = "gauss_long"
        if self.can_short:
            d.loc[short_cond, "enter_short"] = 1
            d.loc[short_cond, "enter_tag"] = "gauss_short"
        gap = int(p.get("min_bars_between", 0) or 0)
        return apply_cooldown(d, gap, sides=("enter_long", "enter_short"))

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        d = dataframe
        g1, g2 = d["gauss"].shift(1), d["gauss"].shift(2)
        turn_up = (d["gauss"] > g1) & (g1 <= g2)
        turn_dn = (d["gauss"] < g1) & (g1 >= g2)
        # Exit beim ENTGEGENGESETZTEN Filter-Dreh (Trend läuft sonst weiter; ROI/Stop greifen zusätzlich).
        d.loc[turn_dn, "exit_long"] = 1
        if self.can_short:
            d.loc[turn_up, "exit_short"] = 1
        return d
