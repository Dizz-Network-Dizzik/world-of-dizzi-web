"""FuturesBreakoutVol — Futures Volatility-Breakout (Donchian + Volumen), long-only, Hebel 3x.

Einstieg: Schlusskurs > N-Perioden-Hoch UND Volumen > Faktor*Durchschnitt.
Parametrisierbar via ``TBT_OPT_PARAMS`` (Katalog-Keys werden auf die Engine-Logik
gemappt: ``bb_period`` -> Kanal-Laenge N, ``volume_multiplier`` -> Volumen-Faktor,
``stop_loss_pct`` -> Stop). Live nutzt Defaults.
"""

from __future__ import annotations

import json
import os
import re

from pandas import DataFrame

from freqtrade.strategy import IntParameter, IStrategy, merge_informative_pair


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


class FuturesBreakoutVol(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True   # Futures: short beim Abwaerts-Ausbruch (Donchian-Tief)

    minimal_roi = {"0": 0.05, "45": 0.02, "120": 0.0}
    stoploss = -0.045
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True
    process_only_new_candles = True
    startup_candle_count: int = 60

    channel = IntParameter(20, 60, default=30, space="buy")
    vol_mult = IntParameter(1, 3, default=2, space="buy")

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
        n = int(p.get("bb_period", self.channel.value))  # Katalog bb_period -> Kanal-Laenge
        dataframe["hh"] = dataframe["high"].rolling(n).max()
        dataframe["ll"] = dataframe["low"].rolling(n).min()
        dataframe["vol_ma"] = dataframe["volume"].rolling(n).mean()
        dataframe = _merge_htf(self, dataframe, metadata)
        return dataframe

    def informative_pairs(self):
        tfs = _informative_tfs()
        if not tfs or self.dp is None:
            return []
        return [(p, tf) for p in self.dp.current_whitelist() for tf in tfs]

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        mult = float(_opt().get("volume_multiplier", self.vol_mult.value))
        volok = (dataframe["volume"] > dataframe["vol_ma"] * mult) & (dataframe["volume"] > 0)
        long_cond = (dataframe["close"] >= dataframe["hh"].shift(1)) & volok
        dataframe = _htf_gate(self, dataframe, long_cond, "donchian_breakout")
        if self.can_short:                  # Short-Spiegel: Ausbruch UNTER das Donchian-Tief
            short_cond = (dataframe["close"] <= dataframe["ll"].shift(1)) & volok
            dataframe.loc[short_cond, "enter_short"] = 1
            dataframe.loc[short_cond, "enter_tag"] = "donchian_breakdown"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["close"] <= dataframe["ll"].shift(1)), "exit_long"] = 1
        if self.can_short:                  # Short schliessen beim Gegen-Ausbruch nach oben
            dataframe.loc[(dataframe["close"] >= dataframe["hh"].shift(1)), "exit_short"] = 1
        return dataframe
