"""FuturesBbandsBounce — Futures Bollinger-Band Range-Bounce, Hebel 3x.

Einstieg (Long): Schlusskurs unter unterem Bollinger-Band; Exit an Mittelband bzw. ROI/Stop.
Short-Spiegel (Futures): Schlusskurs ueber OBEREM Bollinger-Band (ueberkauft) -> Abpraller
nach unten; Exit ebenfalls an der Mittellinie (Mean-Reversion-Ziel). Greift im trend_down.
Parametrisierbar via ``TBT_OPT_PARAMS`` (``bb_period`` -> Periode, ``bb_std`` ->
Standardabweichung, ``stop_loss_pct`` -> Stop). Live nutzt Defaults.
"""

from __future__ import annotations

import json
import os
import re

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, merge_informative_pair


def _opt() -> dict:
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
    """Hoehere Timeframes (Multi-TF-Bestaetigung) aus Env TBT_INFORMATIVE_TFS; opt-in."""
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


def _merge_htf(strategy, dataframe, metadata):
    strategy._htf_col = None
    tfs = _informative_tfs()
    if not tfs or strategy.dp is None:
        return dataframe
    htf = sorted(tfs, key=_tf_minutes)[-1]
    inf = strategy.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=htf)
    if inf is None or not len(inf):
        return dataframe
    inf = inf.copy()
    inf["htf_up"] = (inf["close"] > inf["close"].rolling(50).mean()).astype(int)
    dataframe = merge_informative_pair(
        dataframe, inf[["date", "htf_up"]], strategy.timeframe, htf, ffill=True)
    strategy._htf_col = f"htf_up_{htf}"
    return dataframe


def _htf_gate(strategy, dataframe, cond, base_tag):
    col = getattr(strategy, "_htf_col", None)
    tag = base_tag
    if col and col in dataframe.columns:
        cond = cond & (dataframe[col] == 1)
        tag = base_tag + "+HTF"
    dataframe.loc[cond, "enter_long"] = 1
    dataframe.loc[cond, "enter_tag"] = tag
    return dataframe


def _apply_cooldown(strategy, dataframe):
    """Trade-Frequenz-Bremse (C2, opt-in via opt_param 'min_bars_between'): unterdrueckt
    Entry-Signale, die weniger als N Kerzen nach dem letzten ZUGELASSENEN Entry kommen.
    Default 0 = aus -> laufende Live-Bots (ohne opt_params) unveraendert. Gegen Overtrading."""
    p = _opt()
    try:
        gap = int(p.get("min_bars_between", 0) or 0)
    except Exception:
        gap = 0
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


class FuturesBbandsBounce(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True   # Futures: short am oberen Bollinger-Band (greift im trend_down)

    minimal_roi = {"0": 0.02, "30": 0.01, "120": 0.0}
    stoploss = -0.035
    trailing_stop = True
    trailing_stop_positive = 0.008
    trailing_stop_positive_offset = 0.016
    trailing_only_offset_is_reached = True
    process_only_new_candles = True
    startup_candle_count: int = 40

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = _opt()
        if "stop_loss_pct" in p:
            try:
                self.stoploss = -abs(float(p["stop_loss_pct"])) / 100.0
            except Exception:
                pass

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, side, **kwargs) -> float:
        try:
            u = float(os.environ.get("TBT_LEVERAGE", "") or 0)
        except Exception:
            u = 0.0
        base = u if u > 0 else 3.0
        return min(base, 5.0, float(max_leverage) or base)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        period = int(p.get("bb_period", 20))
        std = float(p.get("bb_std", 2.0))
        bb = ta.BBANDS(dataframe, timeperiod=period, nbdevup=std, nbdevdn=std)
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["bb_mid"] = bb["middleband"]
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=int(p.get("rsi_period", 14)))
        # Makro-Trendfilter (gleiche TF, langer SMA): Dip-Buys nur im uebergeordneten Aufwaertstrend
        # -> gegen "fallende Messer" (wie bei MeanReversionRsi wirksam). OPT-IN (default 0 = aus).
        macro = int(p.get("macro_sma_period", 0))
        dataframe["macro_sma"] = ta.SMA(dataframe, timeperiod=macro) if macro > 0 else dataframe["close"]
        dataframe = _merge_htf(self, dataframe, metadata)
        return dataframe

    def informative_pairs(self):
        tfs = _informative_tfs()
        if not tfs or self.dp is None:
            return []
        return [(p, tf) for p in self.dp.current_whitelist() for tf in tfs]

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        # RSI-Oversold-Bestaetigung (opt-in via rsi_oversold>0): nur echte Ueberverkauftheit, gegen
        # schwache Band-Durchstiche. 0 = aus -> Live-Bots unveraendert. Bewaehrt in MeanReversionRsi.
        rsi_os = int(p.get("rsi_oversold", 0))
        macro = int(p.get("macro_sma_period", 0))
        long_cond = (dataframe["close"] < dataframe["bb_lower"]) & (dataframe["volume"] > 0)
        if rsi_os > 0:
            long_cond = long_cond & (dataframe["rsi"] < rsi_os)
        if macro > 0:
            long_cond = long_cond & (dataframe["close"] > dataframe["macro_sma"])
        dataframe = _apply_cooldown(self, _htf_gate(self, dataframe, long_cond, "bb_bounce"))
        if self.can_short:                  # Short-Spiegel: Abpraller am OBEREN Band (ueberkauft)
            short_cond = (dataframe["close"] > dataframe["bb_upper"]) & (dataframe["volume"] > 0)
            if rsi_os > 0:                  # Spiegel der Oversold-Bestaetigung -> Overbought-Schwelle
                short_cond = short_cond & (dataframe["rsi"] > (100 - rsi_os))
            if macro > 0:                   # Makro-Filter: Short nur im uebergeordneten Abwaertstrend
                short_cond = short_cond & (dataframe["close"] < dataframe["macro_sma"])
            dataframe.loc[short_cond, "enter_short"] = 1
            dataframe.loc[short_cond, "enter_tag"] = "bb_bounce_short"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] >= dataframe["bb_mid"]) & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1
        if self.can_short:                  # Short schliessen an der Mittellinie (Mean-Reversion-Ziel)
            dataframe.loc[
                (dataframe["close"] <= dataframe["bb_mid"]) & (dataframe["volume"] > 0),
                "exit_short",
            ] = 1
        return dataframe
