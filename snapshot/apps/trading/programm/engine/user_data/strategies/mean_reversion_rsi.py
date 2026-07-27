"""MeanReversionRsi — Katalog-System „Mean-Reversion (RSI-Oversold)".

Aktiveres System als reine Trendfolge: kauft ueberverkaufte Ruecksetzer
(RSI < Schwelle) und verkauft bei Rueckkehr nach oben (RSI > Schwelle) bzw. per
ROI/Stop. Auf kleinen Timeframes (z. B. 5m) deutlich handelsfreudiger.
"""

from __future__ import annotations

import json
import os
import re

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IntParameter, IStrategy, merge_informative_pair


def _opt_params() -> dict:
    """Optimierungs-Parameter aus der Umgebungsvariable TBT_OPT_PARAMS (nur im
    Optimierungs-Backtest gesetzt). Live-Bots haben sie NICHT -> Defaults gelten."""
    try:
        return json.loads(os.environ.get("TBT_OPT_PARAMS", "") or "{}")
    except Exception:
        return {}


_TF_RE = re.compile(r"(\d+)\s*([mhd])")


def _tf_minutes(tf: str) -> int:
    m = _TF_RE.match(str(tf).lower().replace("min", "m"))
    if not m:
        return 10 ** 9
    n, u = int(m.group(1)), m.group(2)
    return n * (60 if u == "h" else 1440 if u == "d" else 1)


def _informative_tfs() -> list:
    """Hoehere Timeframes fuer Multi-TF-Bestaetigung aus Env TBT_INFORMATIVE_TFS
    (opt-in; ohne Env = klassisch single-TF, Verhalten unveraendert)."""
    raw = os.environ.get("TBT_INFORMATIVE_TFS", "") or ""
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(x) for x in v if x]
    except Exception:
        pass
    return [s.strip() for s in raw.replace(";", ",").split(",") if s.strip()]


class MeanReversionRsi(IStrategy):
    INTERFACE_VERSION = 3
    # 15m: Mit dem Makro-Trendfilter ist die Strategie auf 15m honest-WF ~PF 1 (3/4 Fenster positiv);
    # auf 5m frisst Rauschen/Overtrading den Edge (WF-PF ~0.4). Edge ist klar TF-gebunden -> 15m Default.
    timeframe = "15m"
    can_short = False

    minimal_roi = {"0": 0.03, "30": 0.015, "90": 0.005, "180": 0.0}
    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True
    process_only_new_candles = True
    startup_candle_count: int = 50

    rsi_period = IntParameter(7, 21, default=14, space="buy")
    rsi_oversold = IntParameter(18, 35, default=30, space="buy")
    rsi_exit = IntParameter(50, 70, default=58, space="sell")

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        # Optimierungs-Override (nur Backtest via TBT_OPT_PARAMS): Stop-Loss anpassen.
        p = _opt_params()
        if "stop_loss_pct" in p:
            try:
                self.stoploss = -abs(float(p["stop_loss_pct"])) / 100.0
            except Exception:
                pass

    def informative_pairs(self):
        tfs = _informative_tfs()
        if not tfs or self.dp is None:
            return []
        pairs = self.dp.current_whitelist()
        return [(p, tf) for p in pairs for tf in tfs]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        period = int(_opt_params().get("rsi_period", self.rsi_period.value))
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=period)
        # Makro-Trendfilter (gleiche TF, langer SMA): nur Dip-Buys im uebergeordneten Aufwaertstrend
        # -> gegen "fallende Messer". OPT-IN (default 0 = aus -> Live-Bots unveraendert); validierter
        # Gewinner = 150 @15m (honest-WF PF ~1.06). Anwendung via opt_params (apply_opt), wie min_bars_between.
        macro = int(_opt_params().get("macro_sma_period", 0))
        dataframe["macro_sma"] = ta.SMA(dataframe, timeperiod=macro) if macro > 0 else dataframe["close"]
        # Multi-Timeframe (opt-in): hoechsten informativen TF als Trendfilter mergen.
        self._htf_col = None
        tfs = _informative_tfs()
        if tfs and self.dp is not None:
            htf = sorted(tfs, key=_tf_minutes)[-1]
            inf = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=htf)
            if inf is not None and len(inf):
                inf = inf.copy()
                inf["htf_up"] = (inf["close"] > ta.EMA(inf, timeperiod=50)).astype(int)
                dataframe = merge_informative_pair(
                    dataframe, inf[["date", "htf_up"]], self.timeframe, htf, ffill=True)
                self._htf_col = f"htf_up_{htf}"
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        oversold = int(_opt_params().get("rsi_oversold", self.rsi_oversold.value))
        cond = (dataframe["rsi"] < oversold) & (dataframe["volume"] > 0)
        if int(_opt_params().get("macro_sma_period", 0)) > 0:
            cond = cond & (dataframe["close"] > dataframe["macro_sma"])
        htf_col = getattr(self, "_htf_col", None)
        if htf_col and htf_col in dataframe.columns:
            cond = cond & (dataframe[htf_col] == 1)
            tag = "rsi_oversold+HTF"
        else:
            tag = "rsi_oversold"
        dataframe.loc[cond, "enter_long"] = 1
        dataframe.loc[cond, "enter_tag"] = tag
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_lvl = int(_opt_params().get("rsi_exit", self.rsi_exit.value))
        dataframe.loc[
            (dataframe["rsi"] > exit_lvl) & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1
        return dataframe
