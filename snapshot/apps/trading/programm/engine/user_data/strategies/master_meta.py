"""MasterMeta — U7-Stufe 2: regime-schaltende Meta-Strategie.

EINE Engine, die je Kerze das Markt-Regime erkennt (SMA-Steigung, live ans HMM gekoppelt) und die
dafür passende Sub-Logik fährt (fixe Default-Zuordnung):
  • Aufwärtstrend  → MACD-Aufwärtskreuz (Trendfolge-Long)
  • Seitwärts      → Schlusskurs unter unterem Bollinger-Band (Mean-Reversion-Long)
  • Abwärtstrend   → MACD-Abwärtskreuz (Trendfolge-Short, Futures)
Plus Overtrading-Bremse (min_bars_between). Parametrisierbar via ``TBT_OPT_PARAMS``; opt-in wie die
übrigen Engines (Live-Bots ohne diese Variable nutzen Defaults). Setzt die Idee des Master-Algorithmus
in eine ausführbare Strategie um.

Drei Backend-Brücken (jede mehrfach gegated, jeder Fehlweg fail-safe = Default-Verhalten):
  1. ``hmm_regime.json`` (D1) — Live-Regime/Konfidenz/Event- + Exposure-Scale → jüngste Kerze + Hebel.
  2. ``suggested_sizing.json`` (FP-2, docs/KELLY_SIZING_SPEC.md) — geklemmter Portfolio-Stake
     → ``custom_stake_amount`` (opt-in ``use_sizing_bridge``, nur dry_run).
  3. ``suggested_policy.json`` (FP-T5, docs/POLICY_HAND_SPEC.md) — Politik-Bestauswahl je Regime
     → Sub-Logik-Wahl (L1) / Stake-Dämpfung ≤1 (L2) / Edge-Gating (L3); opt-in ``use_policy_bridge``,
     nur dry_run, ``mode=='apply'`` + Frische — Gate G-T5, Defaults inert.
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


def _bridge_path() -> str:
    """Pfad der HMM-Regime-Bridge-Datei. Primär ``TBT_REGIME_FILE`` (vom runner gesetzt); sonst
    Fallback relativ zu dieser Strategie-Datei (…/engine/user_data/strategies → …/data/hmm_regime.json),
    damit die Kopplung auch ohne explizite Env robust greift."""
    p = os.environ.get("TBT_REGIME_FILE")
    if p:
        return p
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "..", "data", "hmm_regime.json"))


def _bridge_data(max_age_s: float = 7200.0) -> dict | None:
    """Liest den frischen Markt-Kontext aus der Bridge-Datei (Regime + HMM-Konfidenz + Event-Risiko/
    Hebel-Scale). None bei fehlend/veraltet. So konsultiert der Bot live die HMM- und Fundamental-AI."""
    import time
    p = _bridge_path()
    if not p or not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.loads(fh.read())
        if (time.time() * 1000 - float(d.get("ts", 0))) / 1000.0 > max_age_s:
            return None
        return d
    except Exception:
        return None


def _hmm_regime_override(max_age_s: float = 7200.0):
    """Nur das LIVE-HMM-Regime der jüngsten Kerze (Live/Dry-Run). Backtests ohne/mit veralteter Datei
    nutzen das eigene Schwellen-Regime (kein Lookahead)."""
    d = _bridge_data(max_age_s)
    reg = (d or {}).get("regime")
    return reg if reg in ("trend_up", "trend_down", "range") else None


def _sizing_path() -> str:
    """Pfad der Sizing-Bridge-Datei (FP-2). Primär ``TBT_SIZING_FILE`` (vom runner gesetzt); sonst
    Fallback relativ zu dieser Strategie-Datei (…/data/suggested_sizing.json) — analog ``_bridge_path``."""
    p = os.environ.get("TBT_SIZING_FILE")
    if p:
        return p
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "..", "data", "suggested_sizing.json"))


def _sizing_bridge_stake(bot_id: str, max_age_s: float = 900.0) -> float | None:
    """Stake-Empfehlung für DIESEN Bot aus der Sizing-Bridge (Backend-Klemmkette K4–K6,
    docs/KELLY_SIZING_SPEC.md §4) — nur wenn die Datei frisch ist UND ``mode=='apply'``
    (Governor-breach degradiert Backend-seitig auf 'proposal' ⇒ hier None). None bei
    fehlend/veraltet/proposal/fremdem Bot/unsinnigem Wert — jeder Fehlweg ist fail-safe."""
    import time
    p = _sizing_path()
    if not bot_id or not p or not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.loads(fh.read())
        if d.get("mode") != "apply":
            return None
        if (time.time() * 1000 - float(d.get("ts", 0))) / 1000.0 > max_age_s:
            return None
        stake = float(((d.get("stakes") or {}).get(bot_id) or {}).get("stake"))
        return stake if stake > 0 else None
    except Exception:
        return None


def _policy_path() -> str:
    """Pfad der Politik-Bridge-Datei (FP-T5). Primär ``TBT_POLICY_FILE`` (vom runner gesetzt); sonst
    Fallback relativ zu dieser Strategie-Datei (…/data/suggested_policy.json) — analog ``_bridge_path``."""
    p = os.environ.get("TBT_POLICY_FILE")
    if p:
        return p
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "..", "data", "suggested_policy.json"))


# Sub-Logiken, die diese Engine je Regime real fahren kann (Whitelist der Politik-Umschaltung).
_POLICY_LOGICS = ("trend_macd", "range_bb", "trend_macd_short")
_DEFAULT_LONG_LOGIC = {"trend_up": "trend_macd", "range": "range_bb"}


def _policy_levers(config: dict, p: dict) -> dict | None:
    """Aufgelöste Politik-Hebel aus der Policy-Bridge (FP-T5, docs/POLICY_HAND_SPEC.md §4) —
    ``None``, sobald EIN Gate schließt (= fail-safe auf das fixe Default-Verhalten):
    (1) opt_param ``use_policy_bridge`` (Default 0 = AUS — ohne Opt-in wird die Datei NIE gelesen),
    (2) NUR ``dry_run`` (Echtgeld hart ausgeschlossen — M6 tabu),
    (3) Datei vorhanden + frisch (``policy_max_age_s``, Default 25200 s = Autopilot-Takt 6 h + 1 h
        Puffer, G-T5-Takt-Entscheid) + ``mode=='apply'`` (Governor-breach degradiert Backend-seitig
        auf 'proposal' ⇒ hier None).
    Alle Werte werden ENGINE-seitig validiert/geklemmt (Defense-in-Depth zur Backend-Klemme):
    unbekannte Logiken ⇒ Default bleibt, ``stake_scale`` hart in [0.1, 1.0] — ein manipulierter/
    kaputter Payload kann die Hand nie hochhebeln oder entgleisen."""
    import time
    try:
        if not int(p.get("use_policy_bridge", 0) or 0):
            return None
    except Exception:
        return None
    if not bool(config.get("dry_run", True)):
        return None
    try:
        max_age = float(p.get("policy_max_age_s", 25200) or 25200)
    except Exception:
        max_age = 25200.0
    fp = _policy_path()
    if not fp or not os.path.exists(fp):
        return None
    try:
        with open(fp, encoding="utf-8") as fh:
            d = json.loads(fh.read())
        if d.get("mode") != "apply":
            return None
        if (time.time() * 1000 - float(d.get("ts", 0))) / 1000.0 > max_age:
            return None
        levers = d.get("levers") or {}
        regs = d.get("regimes") or {}
        logic: dict = {}
        enabled: dict = {}
        for reg in ("trend_up", "range", "trend_down"):
            r = regs.get(reg) or {}
            lg = r.get("logic")
            logic[reg] = lg if lg in _POLICY_LOGICS else None
            en = r.get("enabled")
            enabled[reg] = bool(en) if en is not None else True
        scale = None
        s = (d.get("active") or {}).get("stake_scale")
        if s is not None:
            scale = max(0.1, min(1.0, float(s)))   # HARTE Engine-Klemme: nie > 1 (nie hochhebeln)
        return {"apply_logic": bool(levers.get("apply_logic")),
                "apply_stake": bool(levers.get("apply_stake")),
                "gate_unprofitable": bool(levers.get("gate_unprofitable")),
                "logic": logic, "enabled": enabled, "active_scale": scale}
    except Exception:
        return None


def _apply_cooldown(dataframe: DataFrame) -> DataFrame:
    """Trade-Frequenz-Bremse (opt-in via opt_param 'min_bars_between'): unterdrueckt Entry-Signale,
    die weniger als N Kerzen nach dem letzten zugelassenen Entry kommen. Default 0 = aus.
    Wirkt auf Long- UND Short-Entries (aggressiver Futures-Bot handelt beide Richtungen)."""
    p = _opt()
    try:
        gap = int(p.get("min_bars_between", 0) or 0)
    except Exception:
        gap = 0
    if gap <= 0:
        return dataframe
    for col in ("enter_long", "enter_short"):
        if col not in dataframe.columns:
            continue
        el = dataframe[col].fillna(0).astype(int).tolist()
        last = -10 ** 9
        for i, v in enumerate(el):
            if v == 1:
                if i - last < gap:
                    el[i] = 0
                else:
                    last = i
        dataframe[col] = el
    if "enter_tag" in dataframe.columns:
        # Robust: nur über tatsächlich vorhandene Entry-Spalten (kein int-Fallback → keine .fillna-Falle).
        cols = [c for c in ("enter_long", "enter_short") if c in dataframe.columns]
        if cols:
            any_entry = dataframe[cols[0]].fillna(0).eq(1)
            for c in cols[1:]:
                any_entry = any_entry | dataframe[c].fillna(0).eq(1)
            dataframe.loc[~any_entry, "enter_tag"] = None
    return dataframe


class MasterMeta(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True   # aggressiv: handelt Long UND Short (Futures), Shorts im Abwaerts-Regime

    minimal_roi = {"0": 0.03, "60": 0.015, "240": 0.0}
    stoploss = -0.04
    trailing_stop = True
    trailing_stop_positive = 0.012
    trailing_stop_positive_offset = 0.024
    trailing_only_offset_is_reached = True
    process_only_new_candles = True
    startup_candle_count: int = 100

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        p = _opt()
        if "stop_loss_pct" in p:
            try:
                self.stoploss = -abs(float(p["stop_loss_pct"])) / 100.0
            except Exception:
                pass

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs) -> float:
        """Gehirn→Hand-Brücke fürs STAKE-Sizing — zwei unabhängig gegatete Stufen, jede fail-safe
        auf den bisherigen Wert (= byte-identisches Verhalten ohne Opt-in):

        **Sizing-Bridge (FP-2, docs/KELLY_SIZING_SPEC.md §4):** (1) opt_param ``use_sizing_bridge``
        (Default 0 = AUS), (2) NUR ``dry_run`` (Echtgeld hart ausgeschlossen — M6/G-T5 tabu),
        (3) Bridge frisch (``sizing_max_age_s``, Default 900 s) + ``mode=='apply'`` + eigener Bot
        (``TBT_BOT_ID``). Der Bridge-Stake wird auf freqtrades ``[min_stake, max_stake]`` geklemmt.

        **Politik-Dämpfung (FP-T5, docs/POLICY_HAND_SPEC.md §3 L2 / §2 T3):** multipliziert den
        Sizing-GRUNDWERT (Kelly-Bridge-Stake ODER ``proposed_stake``) mit dem ``stake_scale`` des
        AKTIVEN Regimes — engine-seitig hart auf [0.1, 1.0] geklemmt: die Politik kann das Sizing
        nur DÄMPFEN, nie über die K4–K6-Klemmen hinaus erhöhen. Gates via ``_policy_levers``."""
        p = _opt()
        stake = proposed_stake
        try:
            use_sizing = int(p.get("use_sizing_bridge", 0) or 0)
        except Exception:
            use_sizing = 0
        if use_sizing and bool(self.config.get("dry_run", True)):
            try:
                max_age = float(p.get("sizing_max_age_s", 900) or 900)
            except Exception:
                max_age = 900.0
            bs = _sizing_bridge_stake(os.environ.get("TBT_BOT_ID", ""), max_age)
            if bs is not None:
                lo = float(min_stake) if min_stake else 0.0
                hi = float(max_stake) if max_stake else bs
                stake = max(lo, min(bs, hi))
        pol = _policy_levers(self.config, p)
        if pol is not None and pol.get("apply_stake") and pol.get("active_scale") is not None:
            scaled = stake * float(pol["active_scale"])   # Faktor ≤ 1 ⇒ monoton nicht-erhöhend
            lo = float(min_stake) if min_stake else 0.0
            hi = float(max_stake) if max_stake else scaled
            stake = max(lo, min(scaled, hi))
        return stake

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, side, **kwargs) -> float:
        """Aggressiver, regime-bewusster Hebel (Futures): Basis >=5, steigt mit der HMM-Konfidenz bis
        ``max_leverage``, wird aber nach Fundamental-Event-Risiko (``lev_scale`` aus der Bridge)
        gedrosselt. So konsultiert der Bot live die HMM- und Fundamental-Sub-AIs („nach eigenem
        Ermessen hochschrauben, wenn die Aussage sicher ist"). Defaults base 5 / max 10, opt-tunbar."""
        p = _opt()
        try:
            base = max(1.0, float(p.get("base_leverage", 5) or 5))
            maxl = max(base, float(p.get("max_leverage", 10) or 10))
        except Exception:
            base, maxl = 5.0, 10.0
        d = _bridge_data() or {}
        try:
            conf = float(d.get("confidence")) if d.get("confidence") is not None else 0.5
        except Exception:
            conf = 0.5
        lev = base + (maxl - base) * max(0.0, min(1.0, conf))   # mehr Konfidenz -> mehr Hebel
        try:
            scale = d.get("lev_scale")
            if scale is not None:
                lev *= max(0.2, min(1.0, float(scale)))          # Event-Risiko drosselt defensiv
        except Exception:
            pass
        try:
            es = d.get("exposure_scale")                         # D1: Master-Vol-Targeting-Exposure
            if es is not None:
                lev *= max(0.2, min(1.0, float(es)))             # defensiver Exposure-Skalierer (<=1); None=aus
        except Exception:
            pass
        cap = float(max_leverage) if max_leverage else maxl
        return max(1.0, min(lev, maxl, cap))

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        sma = int(p.get("sma_period", 50))
        dataframe["sma"] = ta.SMA(dataframe, timeperiod=sma)
        # Makro-Trendfilter (gleiche TF, langer SMA): nur Long im uebergeordneten Aufwaertstrend
        # -> gegen "fallende Messer" bei Range-Mean-Reversion. 0 = aus (opt-tunbar).
        macro = int(p.get("macro_sma_period", 150))
        dataframe["macro_sma"] = ta.SMA(dataframe, timeperiod=macro) if macro > 0 else dataframe["close"]
        macd = ta.MACD(dataframe,
                       fastperiod=int(p.get("macd_fast", 12)),
                       slowperiod=int(p.get("macd_slow", 26)),
                       signalperiod=int(p.get("macd_signal", 9)))
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        bb = ta.BBANDS(dataframe, timeperiod=int(p.get("bb_period", 20)),
                       nbdevup=float(p.get("bb_std", 2.0)), nbdevdn=float(p.get("bb_std", 2.0)))
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["bb_mid"] = bb["middleband"]
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)        # Trendstärke (gegen Whipsaws)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=int(p.get("rsi_period", 14)))
        # Regime VOLA-NORMIERT (gehärtet, konsistent mit backend tracker.classify_regime): Abweichung
        # vom SMA in Stdev-Einheiten (z) statt nackter SMA-Lage → das Trendband passt sich der
        # Volatilität an (kleine Moves im choppy Markt zählen NICHT als Trend). Plus SMA-Steigung
        # (über 3 Kerzen) + Hysterese (2 Kerzen stabil → kein Flip-Flop). ``regime_z`` opt-tunbar.
        # (Vollkopplung an das python-Gaussian-HMM bräuchte eine Regime-Export-Bridge über die venvs.)
        enter_z = float(p.get("regime_z", 0.8))
        std = dataframe["close"].rolling(sma).std()
        z = (dataframe["close"] - dataframe["sma"]) / std.where(std > 0, other=1e-9)
        rising = dataframe["sma"] > dataframe["sma"].shift(3)
        falling = dataframe["sma"] < dataframe["sma"].shift(3)
        up = ((z > enter_z) & rising).astype(int)
        down = ((z < -enter_z) & falling).astype(int)
        rng = ((up == 0) & (down == 0)).astype(int)
        dataframe["reg_up"] = (up & up.shift(1).fillna(0).astype(int)).astype(int)
        dataframe["reg_down"] = (down & down.shift(1).fillna(0).astype(int)).astype(int)
        dataframe["reg_range"] = (rng & rng.shift(1).fillna(0).astype(int)).astype(int)
        # Live-Kopplung ans Gaussian-HMM: jüngste Kerze nach dem exportierten HMM-Regime überschreiben.
        ovr = _hmm_regime_override()
        if ovr and len(dataframe):
            i = dataframe.index[-1]
            dataframe.loc[i, "reg_up"] = 1 if ovr == "trend_up" else 0
            dataframe.loc[i, "reg_down"] = 1 if ovr == "trend_down" else 0
            dataframe.loc[i, "reg_range"] = 1 if ovr == "range" else 0
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = _opt()
        adx_min = float(p.get("adx_min", 25))
        rsi_os = float(p.get("rsi_oversold", 35))
        confirm = int(p.get("range_confirm", 0))  # 1 = Bounce-Bestaetigung (RSI dreht); empirisch schlechter -> default aus
        macd_cross = (
            (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1))
        )
        vol = dataframe["volume"] > 0
        macro_on = int(p.get("macro_sma_period", 150)) > 0
        macro_rising_on = int(p.get("macro_rising", 0))  # opt: Makro-SMA muss steigen (empirisch leicht schlechter -> aus)
        if macro_on:
            macro_ok = dataframe["close"] > dataframe["macro_sma"]
            if macro_rising_on:
                macro_ok = macro_ok & (dataframe["macro_sma"] > dataframe["macro_sma"].shift(10))
        else:
            macro_ok = vol | True
        # Trend-Regime -> Trendfolge NUR bei echtem Trend (ADX); Range -> Mean-Reversion mit RSI-Bestaetigung.
        # Beide Entries zusaetzlich am Makro-Aufwaertstrend gegated (macro_ok). Die Signal-Familien
        # werden EINMAL berechnet — die Politik-Bridge (FP-T5, docs/POLICY_HAND_SPEC.md §3) kann je
        # Regime zwischen ihnen umschalten (L1) bzw. Regime ohne belegten Edge aussetzen (L3);
        # ohne Opt-in (``_policy_levers`` → None) ist die Zuordnung exakt die fixe von U7-Stufe 2.
        sig_trend = macd_cross & (dataframe["adx"] > adx_min) & vol & macro_ok
        rsi_turning = (dataframe["rsi"] > dataframe["rsi"].shift(1)) if confirm else vol
        sig_range = (dataframe["close"] < dataframe["bb_lower"]) \
            & (dataframe["rsi"] < rsi_os) & rsi_turning & vol & macro_ok
        pol = _policy_levers(self.config, p)
        first = True
        for regime, col in (("trend_up", "reg_up"), ("range", "reg_range")):
            default_logic = _DEFAULT_LONG_LOGIC[regime]
            logic, enabled = default_logic, True
            if pol is not None:
                if pol["apply_logic"]:
                    cand = (pol["logic"] or {}).get(regime)
                    if cand in ("trend_macd", "range_bb"):
                        logic = cand              # L1: gelernte Bestauswahl schaltet die Sub-Logik
                if pol["gate_unprofitable"]:
                    enabled = bool((pol["enabled"] or {}).get(regime, True))
            entry = (dataframe[col] == 1) & (sig_trend if logic == "trend_macd" else sig_range)
            if not enabled:                       # L3: Regime ohne belegten Edge ausgesetzt
                entry = entry & False
            tag = logic if logic == default_logic else "pol_" + logic   # Politik-Trades bleiben sichtbar
            if first:
                dataframe.loc[entry, "enter_long"] = 1
                dataframe.loc[entry, "enter_tag"] = tag
                first = False
            else:
                dataframe.loc[entry & (dataframe["enter_long"].fillna(0) == 0), "enter_long"] = 1
                dataframe.loc[entry & (dataframe["enter_tag"].isna()), "enter_tag"] = tag
        # Aggressiv (Futures, can_short): SHORT im Abwaerts-Regime — gespiegelte Trendfolge auf das
        # MACD-Abwaertskreuz, nur bei echtem Trend (ADX). Long-only-Verhalten kann per opt_param
        # 'allow_short'=0 wieder erzwungen werden. Die Hand hat genau EINE Short-Logik — die Politik
        # kann Shorts nur AUSSETZEN (L3), nicht umschalten (SPEC §1: kein Short-Pendant für range/volatil).
        if int(p.get("allow_short", 1)):
            macd_bear = (
                (dataframe["macd"] < dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1))
            )
            short_entry = (dataframe["reg_down"] == 1) & macd_bear & (dataframe["adx"] > adx_min) & vol
            if pol is not None and pol["gate_unprofitable"] \
                    and not bool((pol["enabled"] or {}).get("trend_down", True)):
                short_entry = short_entry & False
            dataframe.loc[short_entry, "enter_short"] = 1
            dataframe.loc[short_entry & (dataframe["enter_tag"].isna()), "enter_tag"] = "trend_macd_short"
        return _apply_cooldown(dataframe)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macd_down = (
            (dataframe["macd"] < dataframe["macdsignal"])
            & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1))
        )
        back_to_mid = dataframe["close"] >= dataframe["bb_mid"]
        dataframe.loc[(macd_down | back_to_mid) & (dataframe["volume"] > 0), "exit_long"] = 1
        # Short schliessen, wenn das MACD wieder nach oben kreuzt (Gegenbewegung).
        macd_up = (
            (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1))
        )
        dataframe.loc[macd_up & (dataframe["volume"] > 0), "exit_short"] = 1
        return dataframe
