"""VwapReversion — Mean-Reversion zum gleitenden VWAP mit Sigma-Baendern, long-only, Spot.

Volumen-gewichtetes Gegenstueck zum Bollinger-Bounce: misst die Abweichung des Preises vom
rollierenden VWAP in Standardabweichungen. Long, wenn der Preis unter das untere Band (-k*sigma)
faellt (ueberdehnt nach unten), Exit bei Rueckkehr zum VWAP (Mittel). Funktioniert in choppigen/
range-gebundenen Maerkten; ein optionaler Makro-Trendfilter haelt Dip-Buys im Aufwaertstrend.

Parametrisierbar via ``TBT_OPT_PARAMS`` (``vwap_window``, ``band_k``, ``rsi_oversold``,
``macro_sma_period``, ``stop_loss_pct``, ``min_bars_between``). Live nutzt Defaults.

Beleg: VWAP-Std-Reversion ist ein etabliertes Intraday-System (±2sigma/±3sigma als Reversion-Zonen);
Touch der Aussenbaender bei normaler Vola snapt oft zum VWAP zurueck. Lookahead-frei (nur
rollierende Vergangenheitsfenster; Entry ab der Folgekerze).
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


def _apply_cooldown(dataframe: DataFrame, gap: int) -> DataFrame:
    """Trade-Frequenz-Bremse (opt-in via opt_param 'min_bars_between'). 0 = aus (Default)."""
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


class VwapReversion(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = False

    minimal_roi = {"0": 0.02, "60": 0.008, "180": 0.0}  # kleiner Reversion-Gewinn zum VWAP
    stoploss = -0.03
    trailing_stop = False
    process_only_new_candles = True
    startup_candle_count: int = 130

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = _opt()
        if "stop_loss_pct" in p:
            try:
                self.stoploss = -abs(float(p["stop_loss_pct"])) / 100.0
            except Exception:
                pass

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        win = max(10, int(p.get("vwap_window", 48)))
        k = float(p.get("band_k", 2.0))
        tp = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3.0
        pv = (tp * dataframe["volume"]).rolling(win).sum()
        vol = dataframe["volume"].rolling(win).sum()
        dataframe["vwap"] = pv / vol.replace(0, float("nan"))
        dev = dataframe["close"] - dataframe["vwap"]
        dataframe["dev_std"] = dev.rolling(win).std()
        dataframe["vwap_lower"] = dataframe["vwap"] - k * dataframe["dev_std"]
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=int(p.get("rsi_period", 14)))
        # Makro-Trendfilter (gleiche TF, langer SMA): Dip-Buys nur im Aufwaertstrend. OPT-IN (0 = aus).
        macro = int(p.get("macro_sma_period", 0))
        dataframe["macro_sma"] = ta.SMA(dataframe, timeperiod=macro) if macro > 0 else dataframe["close"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        # Long beim Durchstich unter das untere Band (vorher >= Band): ueberdehnt nach unten.
        cond = (
            (dataframe["close"] < dataframe["vwap_lower"])
            & (dataframe["close"].shift(1) >= dataframe["vwap_lower"].shift(1))
            & (dataframe["volume"] > 0)
        )
        rsi_os = int(p.get("rsi_oversold", 0))
        if rsi_os > 0:
            cond = cond & (dataframe["rsi"] < rsi_os)
        if int(p.get("macro_sma_period", 0)) > 0:
            cond = cond & (dataframe["close"] > dataframe["macro_sma"])
        dataframe.loc[cond, "enter_long"] = 1
        dataframe.loc[cond, "enter_tag"] = "vwap_revert"
        gap = int(p.get("min_bars_between", 0) or 0)
        return _apply_cooldown(dataframe, gap)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit bei Rueckkehr zum VWAP (Mittel) — zusaetzlich greift minimal_roi/Stop.
        dataframe.loc[
            (dataframe["close"] >= dataframe["vwap"]) & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1
        return dataframe
