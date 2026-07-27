"""Tracker — schlanke Lern-Datenbasis (Nordstern-Fundament).

Schreibt **einen kompakten Snapshot je Bot und Tag** in ``stats.snapshots``
(Equity, Profit %, Trades, Drawdown/Winrate aus dem letzten Backtest). Bewusst
**keine Tick-/Minutendaten** und **keine Duplikate** der Trade-DBs — Per-Trade-
Details bleiben in den Freqtrade-Trade-DBs und werden bei Bedarf gelesen.

Aufruf ist **debounced** (Prozess-Ebene + „nur 1×/Tag/Bot" in der DB), damit ein
Dashboard-Refresh keine Last/Speicher erzeugt. Spaeter liest die Lern-KI
(``meta.py``) diese Snapshots + Trade-DBs, um Strategien zu bewerten/verfeinern.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from . import hmm, mn_base, stats
from .config import DATA_DIR
from .registry import list_bots

# Regime-Bridge: das Backend exportiert das Live-HMM-Regime in eine Datei, die die Engine-Strategie
# (anderes venv/Prozess) lesen kann (master_meta.py). Pfad via Env TBT_REGIME_FILE überschreibbar.
REGIME_BRIDGE_FILE = Path(__import__("os").environ.get("TBT_REGIME_FILE") or (DATA_DIR / "hmm_regime.json"))


def write_regime_bridge(regime: str | None, confidence: float | None, path: Path | None = None,
                        event_risk: str | None = None, lev_scale: float | None = None,
                        exposure_scale: float | None = None) -> bool:
    """Schreibt den aktuellen Markt-Kontext in die Bridge-Datei (venv-übergreifend für master_meta.py).

    Felder: ``regime`` + ``confidence`` (HMM-AI), ``event_risk`` + ``lev_scale`` (Fundamental-AI:
    Hebel-Dämpfung vor High-Impact-Events), ``exposure_scale`` (Master-Vol-Targeting: defensiver
    Gesamt-Exposure-Skalierer ≤1; None/1.0 = aus) + ``ts``. So „spricht" der aggressive MasterMeta-Bot
    live mit den Sub-AIs: er hebelt nach HMM-Konfidenz hoch, drosselt aber nach Event-Risiko UND nach
    dem Vol-Targeting-Exposure (D1: schließt die Gehirn→Hand-Lücke aus der MasterMeta-Tiefenprüfung)."""
    p = path or REGIME_BRIDGE_FILE
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"regime": regime, "confidence": confidence,
                                 "event_risk": event_risk, "lev_scale": lev_scale,
                                 "exposure_scale": exposure_scale,
                                 "ts": int(time.time() * 1000)}), encoding="utf-8")
        return True
    except Exception:
        return False


def read_regime_bridge(path: Path | None = None, max_age_s: float = 7200.0) -> dict | None:
    """Liest die Bridge-Datei, wenn frisch (≤ max_age_s). None bei fehlend/veraltet/Fehler."""
    p = path or REGIME_BRIDGE_FILE
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if (time.time() * 1000 - float(d.get("ts", 0))) / 1000.0 > max_age_s:
            return None
        return d if d.get("regime") else None
    except Exception:
        return None

# Tunbare HMM-Parameter (Regime-Erkennung), persistiert via mn_base.
HMM_DEFAULTS = {"n_states": 3, "multivariate": 1, "vol_window": 6}


def get_hmm_config() -> dict:
    return mn_base.config_get(HMM_DEFAULTS, "hmm_config")


def set_hmm_config(patch: dict) -> dict:
    return mn_base.config_set(HMM_DEFAULTS, "hmm_config", patch)

_last_run: float = 0.0
_MIN_INTERVAL = 900.0  # Prozess-Debounce: hoechstens alle 15 min pruefen
_last_market: float = 0.0
_MARKET_INTERVAL = 3600.0  # Markt-Snapshot hoechstens 1x/Stunde

# Schwellen der Regime-Klassifikation (vola-normiert + Hysterese).
_TREND_ENTER = 0.8    # |z| >= enter -> in einen Trend wechseln
_TREND_EXIT = 0.3     # |z| muss unter exit fallen, um den Trend zu verlassen (sticky/HMM-artig)
_VOL_HIGH = 1.4       # cur/baseline-Vola-Ratio: >= -> turbulent
_VOL_LOW = 0.7        #                          <= -> calm


def classify_regime(closes: list[float], prev_regime: str | None = None) -> tuple[str, float]:
    """Richtungs-Regime aus Preisreihe — **vola-normiert** mit **Zustands-Persistenz**.

    Verbesserung gegenüber „Preis vs. SMA20 ± fixe 0,5 %": die Trendschwelle ist an die aktuelle
    Volatilität gekoppelt (z = Abweichung vom Slow-SMA in Stdev-Einheiten), zusätzlich Slope-
    Bestätigung (Fast- vs. Slow-SMA) und **Hysterese** — ein bestehender Trend bleibt sticky, bis
    die Stärke klar abebbt (entspricht der Übergangs-Glättung eines HMM, aber dependency-frei).

    Returns ``(regime, trend_z)``. ``regime`` ∈ {trend_up, trend_down, range}.
    """
    n = len(closes)
    if n < 10:
        return "range", 0.0
    price = closes[-1]
    fast = sum(closes[-10:]) / 10.0
    slow = sum(closes[-30:]) / 30.0 if n >= 30 else sum(closes) / n
    win = closes[-30:] if n >= 30 else closes
    sd = statistics.pstdev(win) if len(win) > 1 else 0.0
    z = (price - slow) / sd if sd > 0 else 0.0
    slope = (fast - slow) / slow if slow else 0.0
    if z >= _TREND_ENTER and slope > 0:
        regime = "trend_up"
    elif z <= -_TREND_ENTER and slope < 0:
        regime = "trend_down"
    elif prev_regime == "trend_up" and z > _TREND_EXIT and slope >= 0:
        regime = "trend_up"            # Persistenz: im Aufwärtstrend bleiben, solange Stärke hält
    elif prev_regime == "trend_down" and z < -_TREND_EXIT and slope <= 0:
        regime = "trend_down"
    else:
        regime = "range"
    return regime, round(z, 3)


def classify_volatility(rets_recent: list[float], rets_baseline: list[float]) -> tuple[str, float]:
    """Relatives Vola-Regime: aktuelle Return-Stdev gegen die eigene Baseline (robuster als eine
    absolute %-Schwelle). Returns ``(vol_regime, ratio)`` mit vol_regime ∈ {calm, normal, turbulent}."""
    cur = statistics.pstdev(rets_recent) if len(rets_recent) > 1 else 0.0
    base = statistics.pstdev(rets_baseline) if len(rets_baseline) > 1 else 0.0
    ratio = (cur / base) if base > 0 else 1.0
    if ratio >= _VOL_HIGH:
        reg = "turbulent"
    elif ratio <= _VOL_LOW:
        reg = "calm"
    else:
        reg = "normal"
    return reg, round(ratio, 3)


def decode_regime(closes: list[float], prev_regime: str | None = None,
                  hmm_init: dict | None = None) -> dict | None:
    """Vollständige Regime-Analyse einer Schlusskursreihe — **rein** (kein Netz).

    Primär ein gelerntes **Gaussian-HMM** (Baum-Welch + Viterbi, :mod:`hmm`) über die Renditen; das
    vola-normierte Schwellen-Modell (:func:`classify_regime`) dient als Fallback und liefert die
    kontinuierliche Trendstärke ``trend_z``. ``hmm_init`` = persistiertes Vorgänger-Modell als
    Warm-Start (Dual-Init gegen lokale EM-Optima + Label-Kontinuität über Re-Fits).
    Vola-Regime relativ zur Baseline. None bei zu wenig Daten.
    """
    if len(closes) < 31:
        return None
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1]]
    vol = round(statistics.pstdev(rets[-20:]) * 100, 3)            # absolute Stdev der letzten 20 Returns (%)
    thr_regime, trend_z = classify_regime(closes, prev_regime=prev_regime)
    vol_regime, vol_ratio = classify_volatility(rets[-20:], rets)  # letzte 20 vs. gesamte Baseline
    hm = None
    try:
        hcfg = get_hmm_config()
        n_states = max(2, min(5, int(hcfg["n_states"])))
        rp = [r * 100 for r in rets]
        if bool(int(hcfg.get("multivariate", 1))):
            w = max(2, int(hcfg.get("vol_window", 6)))
            vols = [(statistics.pstdev(rp[max(0, i - w + 1):i + 1]) if i >= 1 else 0.0) for i in range(len(rp))]
            obs = [[rp[i], vols[i]] for i in range(len(rp))]   # [Rendite%, rollende Vola%]
            hm = hmm.classify_mv(obs, n_states=n_states, init=hmm_init)
        else:
            hm = hmm.classify(rp, n_states=n_states)
    except Exception:
        hm = None
    regime = hm["regime"] if hm else thr_regime
    return {"regime": regime, "trend_z": trend_z, "threshold_regime": thr_regime,
            "vol_regime": vol_regime, "vol_ratio": vol_ratio, "volatility": vol,
            "next_regime": (hm or {}).get("next_regime"), "stay_prob": (hm or {}).get("stay_prob"),
            "hmm": hm, "source": "hmm" if hm else "threshold"}


# Markt-repräsentativer Korb (liquide Majors): das Regime wird aus einem gleichgewichteten Index ihrer
# Renditen abgeleitet statt nur aus BTC → robuster gegen BTC-Eigenbewegungen (Multi-Asset-Regime).
REGIME_BASKET = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def _index_closes(client, symbols: list[str], limit: int = 300) -> tuple[list[float] | None, list[str]]:
    """Gleichgewichteter Markt-Index aus mehreren Coins: je Schritt das Mittel der Pro-Coin-Renditen,
    aufkumuliert zu einer synthetischen „Index-Kurs"-Reihe (Start 100). Reihen werden auf die kürzeste
    Länge ausgerichtet. Returns (index_closes | None, verwendete Symbole). Einzelne Fehl-Fetches werden
    übersprungen; bei keinem brauchbaren Coin → None (Aufrufer fällt auf BTC zurück)."""
    series, used = [], []
    for s in symbols:
        try:
            ohlcv = client.fetch_ohlcv(s, timeframe="1h", limit=limit)
            cl = [float(c[4]) for c in ohlcv if c and c[4]]
            if len(cl) >= 31:
                series.append(cl)
                used.append(s)
        except Exception:
            continue
    if not series:
        return None, []
    n = min(len(c) for c in series)
    series = [c[-n:] for c in series]
    idx = [100.0]
    for t in range(1, n):
        rets = [(c[t] / c[t - 1] - 1.0) for c in series if c[t - 1]]
        idx.append(idx[-1] * (1.0 + (sum(rets) / len(rets) if rets else 0.0)))
    return idx, used


def market_snapshot(symbol: str = "BTC/USDT") -> bool:
    """Schreibt einen leichten Markt-Kontext-Snapshot (Preis, Regime, Vola + Vola-Regime).

    Regime aus einem **gleichgewichteten Markt-Index** der liquiden Majors (:data:`REGIME_BASKET`) statt
    nur BTC — robuster gegen Einzelcoin-Eigenbewegungen. ``symbol`` bleibt das Preis-Referenz-Asset
    (BTC) für die gespeicherte ``price``. Nutzt ccxt Public-Daten (keine Keys); HMM primär, Schwellen-
    Fallback; bei Netz-/Datenfehler wird defensiv nichts geschrieben."""
    try:
        import ccxt

        client = ccxt.bitget({"enableRateLimit": True})
        # 300 Kerzen (~12,5 Tage 1h): mehr Stützstellen je HMM-Parameter als die früheren 200.
        idx, used = _index_closes(client, REGIME_BASKET, limit=300)
        ref = client.fetch_ohlcv(symbol, timeframe="1h", limit=300)
        ref_closes = [float(c[4]) for c in ref if c and c[4]]
        closes = idx if idx else ref_closes          # Fallback: BTC-only, falls Korb-Fetch leer
        if not closes:
            return False
        ref_price = round(ref_closes[-1], 2) if ref_closes else round(closes[-1], 2)
        prev = (stats.get_market_snapshots(limit=1) or [{}])[-1].get("regime")
        # Warm-Start: persistiertes Vorgänger-Modell (Label-Kontinuität, Dual-Init).
        try:
            hmm_init = json.loads(mn_base.meta_get("hmm_model_mv") or "null")
        except Exception:
            hmm_init = None
        rep = decode_regime(closes, prev_regime=prev, hmm_init=hmm_init)
        if not rep:
            return False
        new_model = (rep.get("hmm") or {}).get("model")
        if new_model:
            try:
                mn_base.meta_set("hmm_model_mv", json.dumps(new_model))
            except Exception:
                pass  # Persistenz ist Komfort — nie den Snapshot brechen
        reg_conf = (rep.get("hmm") or {}).get("confidence")
        mkt_label = f"INDEX({'+'.join(s.split('/')[0] for s in used)})" if idx and used else symbol
        stats.save_market_snapshot(mkt_label, ref_price, rep["regime"], rep["volatility"],
                                   vol_regime=rep["vol_regime"], trend_z=rep["trend_z"],
                                   regime_conf=reg_conf, next_regime=rep.get("next_regime"),
                                   regime_stay_prob=rep.get("stay_prob"))
        # Fundamental-AI „befragen": Event-Risiko → Hebel-Scale (drosselt den aggressiven Bot vor Events).
        event_lvl, lev_scale = None, None
        try:
            from . import fundamental  # lazy: vermeidet Import-Zyklus
            event_lvl = fundamental.event_risk().get("event_risk")
            lev_scale = fundamental.dir_scale(event_lvl)
        except Exception:
            pass
        # D1 (Gehirn→Hand): den defensiven Vol-Targeting-Exposure-Skalierer (≤1) mitschreiben — Single-
        # Source master.exposure_scale (Default vol_target_pct=0 ⇒ 1.0 ⇒ kein Eingriff). Lazy-Import + best-effort.
        exp_scale = None
        try:
            from . import master  # lazy: vermeidet Import-Zyklus
            exp_scale = master.exposure_scale()
        except Exception:
            pass
        write_regime_bridge(rep["regime"], reg_conf, event_risk=event_lvl, lev_scale=lev_scale,
                            exposure_scale=exp_scale)
        return True
    except Exception:
        return False


def regime_report(symbol: str = "BTC/USDT") -> dict:
    """Live-Regime-Analyse für die Transparenz-Ansicht: dekodiert das aktuelle Regime per HMM aus dem
    **Markt-Index** der Majors (:data:`REGIME_BASKET`, konsistent mit ``market_snapshot``). Fällt bei
    Netz-/Datenfehler auf den letzten Snapshot zurück."""
    try:
        import ccxt

        client = ccxt.bitget({"enableRateLimit": True})
        idx, used = _index_closes(client, REGIME_BASKET, limit=300)
        ref = client.fetch_ohlcv(symbol, timeframe="1h", limit=300)
        ref_closes = [float(c[4]) for c in ref if c and c[4]]
        closes = idx if idx else ref_closes
    except Exception as exc:
        snaps = stats.get_market_snapshots(limit=1)
        return {"ok": False, "note": f"Live-Fetch fehlgeschlagen ({type(exc).__name__}); letzter Snapshot.",
                "stored": (snaps[-1] if snaps else None)}
    if not closes:
        return {"ok": False, "note": "Zu wenig Daten für die Regime-Analyse."}
    try:
        hmm_init = json.loads(mn_base.meta_get("hmm_model_mv") or "null")
    except Exception:
        hmm_init = None
    rep = decode_regime(closes, hmm_init=hmm_init)
    if not rep:
        return {"ok": False, "note": "Zu wenig Daten für die Regime-Analyse."}
    basket = f"INDEX({'+'.join(s.split('/')[0] for s in used)})" if idx and used else symbol
    rep.update({"ok": True, "symbol": basket, "price": round(ref_closes[-1], 2) if ref_closes else None,
                "basket": used if idx else [symbol],
                "explainer": "Gaussian-HMM (Baum-Welch + Viterbi) über die 1h-Renditen eines "
                             "gleichgewichteten Markt-Index der liquiden Majors (robuster als BTC-only): "
                             "lernt verborgene Regime-Zustände und dekodiert das aktuelle. Schwellen-Modell "
                             "als Fallback (liefert trend_z); Vola relativ zur Baseline. Read-only — keine Orders."})
    return rep


def snapshot_bot(bot) -> bool:
    """Schreibt den heutigen Snapshot eines Bots, falls noch nicht vorhanden.

    Returns True, wenn geschrieben wurde.
    """
    if stats.has_snapshot_today(bot.id):
        return False
    starting = bot.dry_run_wallet if bot.dry_run else 0.0
    eq = stats.equity_curve(bot.id, starting)
    pts = eq.get("points") or []
    equity = pts[-1]["equity"] if pts else starting
    start = eq.get("starting") or 0.0
    profit_pct = round((equity - start) / start * 100, 2) if start else None
    tr = stats.recent_trades(bot.id, limit=1)
    latest = stats.get_latest(bot.id) or {}
    stats.save_snapshot(bot.id, {
        "strategy": bot.strategy,
        "trading_mode": getattr(bot, "trading_mode", "spot"),
        "equity": equity,
        "profit_pct": profit_pct,
        "trades_closed": eq.get("closed_trades", tr.get("closed", 0)),
        "trades_open": tr.get("open", 0),
        "winrate_pct": latest.get("winrate_pct"),
        "max_drawdown_pct": latest.get("max_drawdown_pct"),
    })
    return True


def snapshot_all() -> int:
    """Schreibt fuer alle Bots den heutigen Snapshot (idempotent). Returns Anzahl."""
    written = 0
    for b in list_bots():
        try:
            written += 1 if snapshot_bot(b) else 0
        except Exception:
            pass  # Tracking darf den Betrieb nie stoeren
    return written


def maybe_snapshot_all() -> None:
    """Debounced Einstieg (aus /api/summary o. ae.). Billig & nicht-blockierend gemeint."""
    global _last_run, _last_market
    now = time.monotonic()
    if now - _last_run >= _MIN_INTERVAL:
        _last_run = now
        try:
            snapshot_all()
        except Exception:
            pass
    if now - _last_market >= _MARKET_INTERVAL:
        _last_market = now
        try:
            market_snapshot()
        except Exception:
            pass
