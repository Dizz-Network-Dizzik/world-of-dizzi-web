"""SessionOpenBreakout — Sonder-Trade-Typ „Börseneröffnung" (Opening-Range-Breakout).

ZEITLICH getriggert statt rein indikator-getrieben: misst die High/Low-Range der
ersten N Minuten nach einer Markt-/Session-Eröffnung (Asia 00:00 / London 07:00 /
US 13:00 UTC) und handelt den Ausbruch aus dieser Eröffnungs-Range mit Volumen-
Bestaetigung; ausserhalb des Handelsfensters nach dem Open wird nicht eingestiegen.
Short-Spiegel (Futures): Ausbruch UNTER das Eröffnungs-Range-Low (Downside-ORB) — der
spiegelbildliche Abwaerts-Breakout; Zwangs-Exit ebenfalls am Fensterende.

Kanonische Session-Zeiten gespiegelt aus ``backend/app/sessions.py`` (bewusst inline
dupliziert — die Engine laeuft in einer eigenen venv ohne Backend-Import).

Parametrisierbar via ``TBT_OPT_PARAMS`` (Optimierungs-Backtest/Lern-Loop); Live nutzt
Defaults bzw. die am Bot angewandten ``opt_params``. Long + Short, optional Hebel (Futures).
"""

from __future__ import annotations

import json
import os

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

# Session-Open-Stunden (UTC) — Index 0=Asia, 1=London, 2=US (vgl. sessions.SESSION_OPENS).
_OPEN_HOURS = {0: 0, 1: 7, 2: 13}


def _opt() -> dict:
    try:
        return json.loads(os.environ.get("TBT_OPT_PARAMS", "") or "{}")
    except Exception:
        return {}


def _int(p: dict, key: str, default: int) -> int:
    try:
        return int(p.get(key, default))
    except Exception:
        return default


def _float(p: dict, key: str, default: float) -> float:
    try:
        return float(p.get(key, default))
    except Exception:
        return default


class SessionOpenBreakout(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True   # Futures: Downside-ORB (Ausbruch unter die Eröffnungs-Range)

    # Risiko/Exit: per opt_params ueberschreibbar (stop_loss_pct / take_profit_pct).
    minimal_roi = {"0": 0.03}
    stoploss = -0.02
    trailing_stop = False
    process_only_new_candles = True
    startup_candle_count: int = 60
    use_exit_signal = True

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = _opt()
        if "stop_loss_pct" in p:
            self.stoploss = -abs(_float(p, "stop_loss_pct", 2.0)) / 100.0
        if "take_profit_pct" in p:
            self.minimal_roi = {"0": abs(_float(p, "take_profit_pct", 3.0)) / 100.0}

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, side, **kwargs) -> float:
        try:
            u = float(os.environ.get("TBT_LEVERAGE", "") or 0)
        except Exception:
            u = 0.0
        base = u if u > 0 else 2.0
        return min(base, 5.0, float(max_leverage) or base)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        session = _int(p, "session", 2)
        open_hour = _OPEN_HOURS.get(session, 13)
        or_min = max(1, _int(p, "opening_range_min", 15))

        d = dataframe
        # Minuten seit dem heutigen Session-Open (UTC). Negativ = vor dem Open.
        min_since_open = (d["date"].dt.hour - open_hour) * 60 + d["date"].dt.minute
        d["min_since_open"] = min_since_open
        # Session-Tag (UTC-Kalendertag) als Gruppierungs-Schluessel der Eröffnungs-Range.
        sess_day = d["date"].dt.floor("D")
        in_or = (min_since_open >= 0) & (min_since_open < or_min)
        # Opening-Range High/Low je Session-Tag, auf alle Kerzen des Tages gebroadcastet.
        d["or_high"] = d["high"].where(in_or).groupby(sess_day).transform("max")
        d["or_low"] = d["low"].where(in_or).groupby(sess_day).transform("min")
        # Volumen-Bestaetigung relativ zum gleitenden Schnitt.
        d["vol_avg"] = d["volume"].rolling(20, min_periods=5).mean()
        # Optionaler Momentum-Filter (EMA) — fuer Session-Open-Momentum-Varianten.
        ema_period = _int(p, "ema_period", 0)
        d["ema"] = ta.EMA(d, timeperiod=ema_period) if ema_period > 0 else d["close"]
        return d

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        or_min = max(1, _int(p, "opening_range_min", 15))
        window = max(or_min + 1, _int(p, "session_window_min", 90))
        vol_mult = _float(p, "volume_multiplier", 1.5)
        ema_period = _int(p, "ema_period", 0)

        d = dataframe
        # Nur NACH der Eröffnungs-Range und INNERHALB des Handelsfensters nach dem Open.
        in_window = (d["min_since_open"] >= or_min) & (d["min_since_open"] < window)
        volok = (d["volume"] > vol_mult * d["vol_avg"]) & (d["volume"] > 0)  # Volumen-Bestaetigung
        cond = (
            in_window
            & d["or_high"].notna()
            & (d["close"] > d["or_high"])                      # Ausbruch ueber Eröffnungs-Range-High
            & volok
        )
        if ema_period > 0:
            cond = cond & (d["close"] > d["ema"])              # Momentum-Filter (opt-in)
        d.loc[cond, "enter_long"] = 1
        d.loc[cond, "enter_tag"] = "session_open_brk"
        if self.can_short:                                     # Short-Spiegel: Downside-ORB
            short_cond = (
                in_window
                & d["or_low"].notna()
                & (d["close"] < d["or_low"])                   # Ausbruch UNTER Eröffnungs-Range-Low
                & volok
            )
            if ema_period > 0:
                short_cond = short_cond & (d["close"] < d["ema"])   # Momentum-Filter unten (opt-in)
            d.loc[short_cond, "enter_short"] = 1
            d.loc[short_cond, "enter_tag"] = "session_open_brk_short"
        return d

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        or_min = max(1, _int(p, "opening_range_min", 15))
        window = max(or_min + 1, _int(p, "session_window_min", 90))
        d = dataframe
        # Zwangs-Exit am Ende des Eröffnungs-Handelsfensters (kein Tages-Carry des Open-Trades).
        d.loc[d["min_since_open"] >= window, "exit_long"] = 1
        if self.can_short:                                    # Short ebenso am Fensterende schliessen
            d.loc[d["min_since_open"] >= window, "exit_short"] = 1
        return d
