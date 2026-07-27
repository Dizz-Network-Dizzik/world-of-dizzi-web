"""KI-Module (M5) — Krypto-Strategie-Katalog + Performance-Analyse.

Ausrichtung: **ausschliesslich Kryptowaehrungen.** Der Katalog trennt zwei
Gruppen:
- ``krypto``     = krypto-spezifische Systeme (z. B. Grid, DCA, Funding-Rate).
- ``allgemein``  = klassische Systeme, die nachweislich auf Krypto anwendbar
                   sind (Trendfolge, Mean-Reversion, Breakout, Momentum).

Nicht krypto-taugliche Strategien werden **nicht** aufgenommen
(``crypto_applicable=false`` wird beim Refresh herausgefiltert).

Beide Kernfunktionen sind **key-aware**: ohne ``ANTHROPIC_API_KEY`` laufen sie
mit Seed-Katalog / Regel-Logik (0 Token); mit Key recherchiert Claude live und
bezieht konfigurierbare **Recherche-Quellen** ein.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import audit, jsonstore, sessions, stats, universe
from .config import DATA_DIR, Settings
from .registry import get_bot

CATALOG_FILE = DATA_DIR / "strategy_catalog.json"
SOURCES_FILE = DATA_DIR / "research_sources.json"
RESEARCH_CONFIG_FILE = DATA_DIR / "research_config.json"
SEED_VERSION = 8  # erhoehen, wenn sich der Seed-Katalog strukturell aendert -> Auto-Reseed
                  # v8: direction-Feld (long/short/both/neutral) + short-spezialisierte Seed-Systeme
WEB_SEARCH_TOOL = "web_search_20250305"  # Anthropic Web-Such-Tool (Console-Freischaltung noetig)
WEB_SEARCH_MAX_USES = 8  # genug fuer gruendliche (YouTube-)Recherche; Retry faengt Abbrueche ab

# Standard-Recherchequellen (immer aktiv, „validiert"). Nutzer-Quellen kommen hinzu.
DEFAULT_SOURCES: list[dict] = [
    {"name": "Freqtrade-Doku", "url": "https://www.freqtrade.io", "note": "Strategie-/Engine-Referenz", "validated": True},
    {"name": "Freqtrade Strategies (GitHub)", "url": "https://github.com/freqtrade/freqtrade-strategies", "note": "Beispielstrategien", "validated": True},
    {"name": "Benjamin Cowen (YouTube)", "url": "https://www.youtube.com/@intothecryptoverse", "note": "datengetrieben, Statistik", "validated": True},
    # Nutzer-YouTube-Kanaele: backtesten klar definierte Systeme -> PRIORISIEREN.
    {"name": "Trading Strategie Analyse (YouTube)", "url": "https://www.youtube.com/results?search_query=Trading+Strategie+Analyse",
     "note": "Nutzer-Quelle: klar definierte, getestete Systeme — priorisieren", "validated": True},
    {"name": "Trading Strategy Testing (YouTube)", "url": "https://www.youtube.com/results?search_query=Trading+Strategy+Testing",
     "note": "Nutzer-Quelle: klar definierte, getestete Systeme — priorisieren", "validated": True},
]

# Kurzfrist-Fokus: Futures erlaubt (Schwerpunkt), Horizont max. Intraday (<= 1 Tag).
# `opening_focus`: Sonder-Schwerpunkt „Börseneröffnungen" (Session-Open-Systeme) —
# fügt der Recherche ein eigenes Eröffnungs-Kapitel hinzu (siehe _research_with_ai).
RESEARCH_DEFAULTS = {"allow_futures": True, "horizon_scope": "intraday",
                     "max_systems": 8, "max_age_days": 30, "opening_focus": True}

# Einheitliche Felder fuer jede Strategie (siehe docs/RESEARCH_TOOL.md).
_FIELD_DEFAULTS = {
    "group": "allgemein", "context": "", "entry_rules": "", "exit_rules": "",
    "params": [], "timeframe": "5m", "horizon": "intraday", "market_type": "spot",
    "leverage": "1x", "session": "beliebig", "regime": "", "risk": "mittel",
    "crypto_applicable": True, "validated": False, "sources": [],
    "freqtrade_template": "(Vorlage folgt)", "pinned": False, "source": "seed",
    "added_at": "", "last_seen": "",  # Alter/Frische — gesetzt beim Recherche-Lauf
    # Sicherheits-/Vertrauens-Einschaetzung auf Basis von Backtest-Belegen.
    "certainty": "unbekannt",          # hoch | mittel | niedrig | unbekannt
    "backtest_evidence": "",           # kurzer Beleg-Text (Quelle/Anzahl/Zeitraum/Ergebnis)
    "backtest_count": None,            # geschaetzte Anzahl belegter Backtests (int | null)
    # Empfohlene Reaktivitaet (Loop-Tempo) je nach Strategie/Timeframe -> Bot-Setup.
    "reactivity": "standard",          # hoch (Scalping) | standard | ruhig
    # Effizienz-Einschaetzung (wie effizient die Strategie Gewinn je Risiko/Trade erwirtschaftet).
    "efficiency": "unbekannt",         # hoch | mittel | niedrig | unbekannt (KI-Schaetzung; per Eigen-PF gegroundet)
    # Makro-Event-Exposure (Fundamental-Schicht): wie stark reagiert die Strategie auf FOMC/CPI/NFP.
    "event_sensitivity": "mittel",     # hoch | mittel | niedrig
    # --- Sonder-Trade-Typ „Börseneröffnung" (Session-Open) ---------------------
    # trigger_type unterscheidet rein indikator-getriebene Systeme ('signal') von
    # ZEITLICH an einer Börseneröffnung verankerten Systemen ('session_open').
    "trigger_type": "signal",          # signal | session_open
    "opening_session": "none",         # asia | london | us | eu_us_overlap | none
    "opening_range_min": None,         # Opening-Range-Laenge in Minuten (ORB), sonst null
    # Markt-neutral / Arbitrage-Archetyp (Market-Making, Pairs-/Statistical-Arbitrage):
    # eigene Kategorie neben den richtungs-gerichteten Systemen.
    "market_neutral": False,           # bool — True fuer MM/Pairs/Stat-Arb (richtungsneutral)
    # KLAR DEKLARIERTE Handelsrichtung: long | short | both | neutral. Default 'long'
    # (abwaerts-kompatibel); market_neutral-Systeme werden in der Normalisierung auf 'neutral'
    # gesetzt. 'short'/'both' macht short-FAEHIGE bzw. short-SPEZIALISIERTE Systeme explizit sichtbar.
    "direction": "long",
}
CERTAINTY_LEVELS = {"hoch", "mittel", "niedrig", "unbekannt"}
REACTIVITY_LEVELS = {"hoch", "standard", "ruhig"}
EFFICIENCY_LEVELS = {"hoch", "mittel", "niedrig", "unbekannt"}
EVENT_SENS_LEVELS = {"hoch", "mittel", "niedrig"}
TRIGGER_TYPES = {"signal", "session_open"}
DIRECTION_LEVELS = {"long", "short", "both", "neutral"}


def get_research_config() -> dict:
    cfg = dict(RESEARCH_DEFAULTS)
    cfg.update(jsonstore.read_json(RESEARCH_CONFIG_FILE, {}))   # atomar + .bak-Recovery
    return cfg


def set_research_config(changes: dict) -> dict:
    cfg = get_research_config()
    for k in RESEARCH_DEFAULTS:
        if k in changes:
            cfg[k] = changes[k]
    jsonstore.write_atomic(RESEARCH_CONFIG_FILE, cfg)
    audit.record("research_config_changed", **cfg)
    return cfg


# Erlaubte Parameter-Kategorien (steuern Gruppierung + Relevanz in der UI).
# Irrelevante Kategorien entfallen je Strategie schlicht dadurch, dass keine
# Parameter dieser Kategorie gelistet sind. `optional`=True => einklappbar.
PARAM_CATEGORIES = ("indikator", "volumen", "risiko", "session", "krypto")


def _normalize_param(p: dict) -> dict:
    """Vereinheitlicht einen Strategie-Parameter (rueckwaerts-kompatibel).

    Ergaenzt fehlende `category` (Default 'indikator') und `optional` (Default
    False). Aeltere Parameter ohne diese Felder bleiben damit gueltig.
    """
    out = dict(p)
    cat = str(out.get("category", "indikator")).lower()
    out["category"] = cat if cat in PARAM_CATEGORIES else "indikator"
    out["optional"] = bool(out.get("optional", False))
    return out


def _normalize_system(s: dict) -> dict:
    """Stellt sicher, dass jedes System alle Felder hat (seed wie KI-Ergebnis)."""
    out = dict(_FIELD_DEFAULTS)
    out.update(s)
    # Rueckwaerts-Kompatibel: altes 'rules' -> entry_rules, falls vorhanden.
    if s.get("rules") and not s.get("entry_rules"):
        out["entry_rules"] = s["rules"]
    # Parameter vereinheitlichen (category/optional).
    out["params"] = [_normalize_param(p) for p in (out.get("params") or [])]
    # Certainty + Reaktivität auf bekannte Stufen normalisieren.
    cert = str(out.get("certainty", "unbekannt")).lower()
    out["certainty"] = cert if cert in CERTAINTY_LEVELS else "unbekannt"
    react = str(out.get("reactivity", "standard")).lower()
    if react not in REACTIVITY_LEVELS:
        # aus Horizont/Timeframe ableiten, wenn nicht (gueltig) gesetzt
        tf = str(out.get("timeframe", "")).lower().replace("min", "m")
        react = "hoch" if (out.get("horizon") == "scalp" or tf in ("1m", "3m")) else "standard"
    out["reactivity"] = react
    # Effizienz + Event-Sensitivität auf bekannte Stufen normalisieren.
    eff = str(out.get("efficiency", "unbekannt")).lower()
    out["efficiency"] = eff if eff in EFFICIENCY_LEVELS else "unbekannt"
    es = str(out.get("event_sensitivity", "mittel")).lower()
    out["event_sensitivity"] = es if es in EVENT_SENS_LEVELS else "mittel"
    # Sonder-Trade-Typ „Börseneröffnung" normalisieren.
    trig = str(out.get("trigger_type", "signal")).lower()
    out["trigger_type"] = trig if trig in TRIGGER_TYPES else "signal"
    osess = str(out.get("opening_session", "none")).lower()
    out["opening_session"] = osess if osess in sessions.OPENING_SESSIONS else "none"
    # Ein Eröffnungs-System ohne explizite Session gilt als 'beliebige' Eröffnung -> us-Open
    # ist die liquideste Default-Annahme; ein reines Signal-System bleibt 'none'.
    if out["trigger_type"] == "session_open" and out["opening_session"] == "none":
        out["opening_session"] = "us"
    if out["trigger_type"] != "session_open":
        out["opening_range_min"] = None
    out["market_neutral"] = bool(out.get("market_neutral", False))
    # Handelsrichtung deklarieren/normalisieren: market_neutral -> immer 'neutral'; sonst auf die
    # bekannten Stufen normalisieren (Default 'long', abwaerts-kompatibel fuer Alt-Systeme ohne Feld).
    if out["market_neutral"]:
        out["direction"] = "neutral"
    else:
        d = str(out.get("direction", "long")).lower()
        out["direction"] = d if d in DIRECTION_LEVELS else "long"
        if out["direction"] == "neutral":   # 'neutral' ohne market_neutral ist widerspruechlich
            out["direction"] = "long"
    return out


# ============================ Recherchetool 2.0 — Scoring ============================
# Zwei prominente Entscheidungs-Scores (0–100): SICHERHEIT (wie belastbar die Belege sind) und
# EFFIZIENZ (Gewinn je Risiko/Trade). Best Practice (Recherche): LLM-Selbsteinschätzung NICHT blind
# trauen — wo wir EIGENE OOS-Validierung haben (stats.strategy_validations), groundet sie die Scores
# (reproduzierbar). Bias/„schöner Backtest" hart abwerten. Reine, testbare Funktionen.
_BIAS_WORDS = ("overfit", "over-fit", "überfit", "selection", "selektions", "data-snoop", "data snoop",
               "look-ahead", "lookahead", "survivorship", "curve", "kurvenangepasst", "in-sample")
_OOS_WORDS = ("walk-forward", "walk forward", "out-of-sample", "out of sample", "oos", "embargo")


def _clamp(x: float, lo: float, hi: float) -> int:
    return int(max(lo, min(hi, round(x))))


def own_evidence() -> dict:
    """Reale OOS-Belege aus dem eigenen System (strategy_validations) je Strategie-Template —
    Grounding-Basis für die Scores. Liefert den vollen Metrik-Satz je Template (für ``compute_metrics``):
    {template_lower: {profit_factor, windows, max_drawdown_pct, total_trades, winrate_pct, profit_total_pct}}."""
    out: dict = {}
    try:
        from .meta import STRAT_REGIME
        for strat in STRAT_REGIME:
            v = stats.get_strategy_validation(strat) or {}
            if v.get("profit_factor") is not None:
                out[str(strat).lower()] = {
                    "profit_factor": float(v["profit_factor"]),
                    "windows": int(v.get("windows") or 1),
                    "max_drawdown_pct": v.get("max_drawdown_pct"),
                    "total_trades": v.get("total_trades"),
                    "winrate_pct": v.get("winrate_pct"),
                    "profit_total_pct": v.get("profit_total_pct"),
                }
    except Exception:
        pass
    return out


# --- Metrik-Kanon (Recherche-gegroundet) ---------------------------------------------------------
# „Never trust a single metric" → mehrere klar definierte Maße kombinieren. Quellen + Definitionen:
# docs/RECHERCHE_METRIKEN_2026-06-09.md (Sharpe/Sortino/Calmar/Profit-Faktor/MaxDD/Expectancy/SQN …).
def compute_metrics(ev: dict | None) -> dict | None:
    """Berechnet den klar definierten Metrik-Kanon aus der eigenen OOS-Evidenz (None ohne Evidenz).

    Roh: profit_factor, win_rate, max_drawdown, return, trades. Abgeleitet:
    - ``expectancy_r`` = w·RR − (1−w) mit RR = PF·(1−w)/w  (Erwartungswert je Trade in R-Vielfachen)
    - ``calmar`` = Return / MaxDD  (CAR/MDD — Rendite je Einheit Worst-Case-Verlust)
    - ``significant`` = ≥100 Trades (statistische Aussagekraft).
    """
    if not ev or ev.get("profit_factor") is None:
        return None
    pf = float(ev["profit_factor"])
    w = ev.get("winrate_pct")
    w = (float(w) / 100.0) if w is not None else None
    dd = ev.get("max_drawdown_pct")
    dd = float(dd) if dd is not None else None
    ret = ev.get("profit_total_pct")
    ret = float(ret) if ret is not None else None
    n = int(ev.get("total_trades") or 0)
    expectancy_r = None
    if w is not None and 0.0 < w < 1.0:
        rr = pf * (1.0 - w) / w                       # Ø Gewinn/Verlust aus PF & Trefferquote
        expectancy_r = round(w * rr - (1.0 - w), 3)   # Erwartungswert je Trade (in R)
    calmar = round(ret / dd, 2) if (ret is not None and dd and dd > 0) else None
    return {
        "profit_factor": round(pf, 2),
        "win_rate_pct": round(w * 100, 1) if w is not None else None,
        "max_drawdown_pct": round(dd, 1) if dd is not None else None,
        "return_pct": round(ret, 1) if ret is not None else None,
        "total_trades": n,
        "significant": n >= 100,
        "expectancy_r": expectancy_r,
        "calmar": calmar,
        "windows": int(ev.get("windows") or 1),
    }


def _match_evidence(s: dict, own: dict) -> dict | None:
    """Matcht ein Katalog-System an eine eigene Validierung (per Template/Name/Id, fuzzy)."""
    cands = [str(s.get(k) or "").strip().lower() for k in ("freqtrade_template", "name", "id")]
    cands = [c for c in cands if c and c != "(vorlage folgt)"]
    for key, val in own.items():
        for c in cands:
            if key == c or key in c:
                return val
    return None


def security_score(s: dict, own: dict | None = None) -> tuple[int, str, bool]:
    """SICHERHEIT 0–100: certainty + Methode (OOS/WF) + Beleg-Anzahl − Bias; durch EIGENE OOS-PF
    gegroundet (überschreibt die KI-Schätzung nach oben/unten). Returns (score, basis, validated)."""
    own = own_evidence() if own is None else own
    cert = str(s.get("certainty", "unbekannt")).lower()
    score = {"hoch": 70, "mittel": 45, "niedrig": 25, "unbekannt": 15}.get(cert, 15)
    ev = (str(s.get("backtest_evidence") or "")).lower()
    if any(w in ev for w in _OOS_WORDS):
        score += 15
    bc = s.get("backtest_count")
    if isinstance(bc, (int, float)):
        score += 15 if bc >= 300 else (10 if bc >= 100 else 0)
    if any(w in ev for w in _BIAS_WORDS) and not any(w in ev for w in _OOS_WORDS):
        score -= 10
    basis, validated = f"KI-Einschätzung: {cert}", False
    m = _match_evidence(s, own)
    if m and m.get("profit_factor") is not None:
        pf, win, validated = float(m["profit_factor"]), int(m.get("windows") or 1), True
        if win >= 3 and pf > 1.0:
            score, basis = max(score, 80), f"eigene OOS-Validierung (PF {pf:g}, {win} Fenster)"
        elif pf > 1.0:
            score, basis = max(score, 60), f"eigene Validierung (PF {pf:g})"
        else:
            score, basis = min(score, 40), f"eigene Validierung schwach (PF {pf:g})"
    return _clamp(score, 0, 100), basis, validated


def efficiency_score(s: dict, own: dict | None = None) -> tuple[int, str]:
    """EFFIZIENZ 0–100 als **Multi-Metrik-Komposit** über die eigene OOS-Evidenz (Recherche: „never trust
    a single metric"): Profit-Faktor-Basis, justiert nach Calmar (Return/MaxDD), Expectancy (R/Trade),
    Drawdown-Strafe und Trade-Signifikanz; Overfit-Deckel bei PF>3. Ohne Evidenz: KI-`efficiency`-Stufe
    ± Risiko. Returns (score, basis)."""
    own = own_evidence() if own is None else own
    mt = compute_metrics(_match_evidence(s, own))
    if mt:
        pf = mt["profit_factor"]
        score = (pf - 0.8) / (2.2 - 0.8) * 100                 # PF-Basis (1.5→50, 2.2→95)
        if mt.get("calmar") is not None:                        # Rendite je Worst-Case-Verlust
            score += 8 if mt["calmar"] >= 2 else (3 if mt["calmar"] >= 1 else -6)
        if mt.get("expectancy_r") is not None:                  # Erwartungswert je Trade
            score += 6 if mt["expectancy_r"] > 0.1 else (0 if mt["expectancy_r"] > 0 else -8)
        if mt.get("max_drawdown_pct") is not None and mt["max_drawdown_pct"] > 25:
            score -= 8                                          # tiefe Drawdowns abwerten
        if mt["total_trades"] and not mt["significant"]:
            score -= 6                                          # bekannte <100 Trades → schwächere Aussage
        if pf > 3:
            score = min(score, 80)                              # zu schön = Overfit-Verdacht
        basis = f"PF {pf:g} · Calmar {mt.get('calmar')} · Exp {mt.get('expectancy_r')}R · n{mt['total_trades']}"
        return _clamp(score, 5, 95), basis
    eff = str(s.get("efficiency", "unbekannt")).lower()
    score = {"hoch": 72, "mittel": 50, "niedrig": 30, "unbekannt": 42}.get(eff, 42)
    risk = (str(s.get("risk") or "")).lower()
    if "hoch" in risk:
        score -= 8
    elif "niedrig" in risk:
        score += 5
    return _clamp(score, 0, 100), f"KI-Einschätzung: {eff}"


def attach_scores(systems: list[dict], own: dict | None = None) -> list[dict]:
    """Hängt Sicherheits-/Effizienz-Scores (read-time, gegen aktuelle Eigen-Evidenz) an jedes System."""
    own = own_evidence() if own is None else own
    out = []
    for s in systems:
        s = dict(s)
        sec, sb, val = security_score(s, own)
        eff, eb = efficiency_score(s, own)
        s["security_score"], s["security_basis"], s["system_validated"] = sec, sb, val
        s["efficiency_score"], s["efficiency_basis"] = eff, eb
        s["metrics"] = compute_metrics(_match_evidence(s, own))   # Metrik-Kanon (None ohne Eigen-Evidenz)
        out.append(s)
    return out


# Eingebauter, krypto-fokussierter Seed-Katalog (Stand 2026).
# Parameter sind nach `category` gruppiert (indikator/volumen/risiko/session/krypto)
# und optional-markiert (einklappbar). Irrelevante Kategorien werden je Strategie
# schlicht weggelassen -> muessen nicht ausgefuellt werden.
SEED_CATALOG: list[dict] = [
    # --- Allgemein, aber krypto-tauglich ---
    {
        "id": "trendfolge_ema", "group": "allgemein", "name": "Trendfolge (EMA-Crossover + RSI)",
        "category": "trend", "crypto_applicable": True,
        "description": "Kauft beim Aufwaerts-Kreuzen zweier EMAs mit RSI-Bestaetigung; folgt etablierten Krypto-Trends. Trailing-Stop sichert Gewinne in laufenden Trends.",
        "rules": "Long, wenn EMA(fast) > EMA(slow) kreuzt und RSI im Momentum-Bereich; Exit per Gegen-Kreuz, ROI, Stop/Trailing.",
        "params": [
            {"name": "ema_fast", "role": "Schnelle EMA-Periode", "category": "indikator", "min": 8, "max": 20, "default": 12, "optional": False},
            {"name": "ema_slow", "role": "Langsame EMA-Periode", "category": "indikator", "min": 21, "max": 60, "default": 26, "optional": False},
            {"name": "rsi_period", "role": "RSI-Periode", "category": "indikator", "min": 7, "max": 21, "default": 14, "optional": False},
            {"name": "rsi_entry_min", "role": "RSI-Mindestwert fuer Entry (Momentum)", "category": "indikator", "min": 45, "max": 60, "default": 50, "optional": False},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 2.0, "max": 8.0, "default": 4.0, "optional": False},
            {"name": "trailing_start_pct", "role": "Trailing aktiv ab Gewinn %", "category": "risiko", "min": 1.0, "max": 5.0, "default": 2.0, "optional": True},
            {"name": "trailing_distance_pct", "role": "Trailing-Abstand %", "category": "risiko", "min": 0.5, "max": 3.0, "default": 1.5, "optional": True},
        ],
        "risk": "mittel", "suited_for": "trendige Krypto-Maerkte",
        "freqtrade_template": "TrendFollowEma", "pinned": False, "source": "seed",
    },
    {
        "id": "mean_reversion_rsi", "group": "allgemein", "name": "Mean-Reversion (RSI-Oversold)",
        "category": "mean_reversion", "crypto_applicable": True,
        "description": "Kauft ueberverkaufte Ruecksetzer in Range-Phasen, verkauft zur Mitte. In Krypto liefern Extremwerte (RSI<20 / >80) die saubersten Signale.",
        "rules": "Long bei RSI < Oversold-Schwelle; Exit bei Rueckkehr zum Mittel (RSI-Exit) oder ROI. Stop schuetzt vor Trend-Ausbruch.",
        "params": [
            {"name": "rsi_period", "role": "RSI-Periode", "category": "indikator", "min": 7, "max": 21, "default": 14, "optional": False},
            {"name": "rsi_oversold", "role": "RSI-Oversold (Kauf)", "category": "indikator", "min": 18, "max": 35, "default": 30, "optional": False},
            {"name": "rsi_exit", "role": "RSI-Exit (Rueckkehr Mitte)", "category": "indikator", "min": 45, "max": 60, "default": 50, "optional": False},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 1.5, "max": 6.0, "default": 3.0, "optional": False},
            {"name": "take_profit_pct", "role": "Take-Profit in %", "category": "risiko", "min": 1.0, "max": 5.0, "default": 2.5, "optional": True},
        ],
        "risk": "mittel", "suited_for": "Range-/Seitwaertsmaerkte",
        "freqtrade_template": "MeanReversionRsi", "pinned": False, "source": "seed",
    },
    {
        "id": "breakout_donchian", "group": "allgemein", "name": "Breakout (Donchian-Kanal)",
        "category": "breakout", "crypto_applicable": True,
        "description": "Kauft Ausbrueche ueber das N-Perioden-Hoch mit Volumen-Bestaetigung; reitet neue Krypto-Bewegungen. Low-Volume-Breakouts werden gefiltert.",
        "rules": "Long bei Schlusskurs > hoechstes Hoch der letzten N Perioden UND Volumen ueber Schwelle; Stop unter Kanal (ATR), Trailing aktiv.",
        "params": [
            {"name": "channel_period", "role": "Donchian-Kanal-Periode", "category": "indikator", "min": 20, "max": 80, "default": 40, "optional": False},
            {"name": "volume_multiplier", "role": "Volumen vs. 20-Bar-Schnitt (Bestaetigung)", "category": "volumen", "min": 1.2, "max": 2.5, "default": 1.5, "optional": False},
            {"name": "atr_period", "role": "ATR-Periode (Stop)", "category": "indikator", "min": 10, "max": 20, "default": 14, "optional": True},
            {"name": "atr_stop_mult", "role": "ATR-Stop-Multiplikator", "category": "risiko", "min": 1.0, "max": 3.0, "default": 2.0, "optional": False},
        ],
        "risk": "hoch", "suited_for": "Volatilitaets-Ausbrueche",
        "freqtrade_template": "(Vorlage folgt)", "pinned": False, "source": "seed",
    },
    {
        "id": "momentum_macd", "group": "allgemein", "name": "Momentum (MACD)",
        "category": "momentum", "crypto_applicable": True,
        "description": "Folgt der Beschleunigung des Trends ueber MACD-Signalkreuze. RSI-Filter vermeidet ueberdehnte Einstiege.",
        "rules": "Long bei MACD-Linie kreuzt Signallinie aufwaerts ueber Null; Exit bei Gegen-Kreuz/ROI. Stop begrenzt Fehlsignale.",
        "params": [
            {"name": "macd_fast", "role": "MACD schnelle EMA", "category": "indikator", "min": 8, "max": 16, "default": 12, "optional": False},
            {"name": "macd_slow", "role": "MACD langsame EMA", "category": "indikator", "min": 20, "max": 34, "default": 26, "optional": False},
            {"name": "macd_signal", "role": "MACD Signal-Glaettung", "category": "indikator", "min": 7, "max": 12, "default": 9, "optional": False},
            {"name": "rsi_filter_max", "role": "RSI-Obergrenze fuer Entry (Filter)", "category": "indikator", "min": 60, "max": 75, "default": 68, "optional": True},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 2.0, "max": 7.0, "default": 4.0, "optional": False},
        ],
        "risk": "mittel", "suited_for": "trendig mit klaren Impulsen",
        "freqtrade_template": "MomentumMacd", "pinned": False, "source": "seed",
    },
    {
        "id": "supertrend_atr", "group": "allgemein", "name": "Supertrend (ATR-Trend)",
        "category": "trend", "crypto_applicable": True,
        "description": "ATR-basierte Trendfolge: bleibt im vorherrschenden Trend und dreht erst beim Supertrend-Flip (Schlusskurs durchbricht das gegenueberliegende ATR-Band). Selektiver als EMA-/MACD-Kreuz, weniger Whipsaw.",
        "entry_rules": "Long, wenn Supertrend von Abwaerts auf Aufwaerts kippt (Close schliesst ueber das obere Final-Band); optionaler Makro-SMA-Filter laesst Longs nur im uebergeordneten Aufwaertstrend zu.",
        "exit_rules": "Exit beim Gegen-Flip (Supertrend dreht auf Abwaerts) bzw. Stop-Loss; lockeres ROI laesst Trends laufen.",
        "params": [
            {"name": "atr_period", "role": "ATR-Periode (Supertrend)", "category": "indikator", "min": 7, "max": 14, "default": 10, "optional": False},
            {"name": "atr_mult", "role": "ATR-Multiplikator (Band-Abstand)", "category": "indikator", "min": 2.0, "max": 4.0, "default": 3.0, "optional": False},
            {"name": "macro_sma_period", "role": "Makro-Trendfilter-SMA (0=aus)", "category": "indikator", "min": 0, "max": 200, "default": 0, "optional": True},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 3.0, "max": 10.0, "default": 6.0, "optional": False},
        ],
        "timeframe": "15m", "horizon": "intraday", "market_type": "futures", "leverage": "3x",
        "session": "beliebig", "regime": "trend", "reactivity": "standard",
        "risk": "mittel", "suited_for": "trendige Phasen, weniger Chop",
        "certainty": "mittel", "efficiency": "mittel",
        "backtest_evidence": "Supertrend (ATR10*3) auf BTC ueber 8+ Jahre: ~33% CAGR, MaxDD ~-61% (deutlich unter Buy&Hold), Marktzeit ~50% (boringedge/quantifiedstrategies). In-sample/Einzelcoin -> regime-/coin-abhaengig.",
        "backtest_count": 2,
        "freqtrade_template": "Supertrend", "pinned": False, "source": "seed",
    },
    {
        "id": "vwap_sigma_reversion", "group": "allgemein", "name": "VWAP-Reversion (Sigma-Baender)",
        "category": "mean_reversion", "crypto_applicable": True,
        "description": "Volumen-gewichtete Mean-Reversion: misst die Abweichung des Preises vom gleitenden VWAP in Standardabweichungen und handelt die Rueckkehr zum VWAP, wenn der Preis das untere Band (-k*sigma) durchbricht. Wirkt in choppigen/range-gebundenen Maerkten.",
        "entry_rules": "Long beim Durchstich unter das untere VWAP-Band (-k*sigma); optionale RSI-Oversold-Bestaetigung und Makro-SMA-Filter (Dip-Buy nur im Aufwaertstrend).",
        "exit_rules": "Exit bei Rueckkehr zum VWAP (Mittel) bzw. kleinem ROI; enger Stop jenseits des Bandes gegen anhaltenden Trend.",
        "params": [
            {"name": "vwap_window", "role": "VWAP-/Band-Fenster (Kerzen)", "category": "indikator", "min": 20, "max": 120, "default": 48, "optional": False},
            {"name": "band_k", "role": "Band-Abstand (Sigma vom VWAP)", "category": "indikator", "min": 1.5, "max": 3.0, "default": 2.0, "optional": False},
            {"name": "rsi_oversold", "role": "RSI-Oversold-Bestaetigung (0=aus)", "category": "indikator", "min": 0, "max": 40, "default": 0, "optional": True},
            {"name": "stop_loss_pct", "role": "Stop-Loss jenseits Band %", "category": "risiko", "min": 1.5, "max": 5.0, "default": 3.0, "optional": False},
        ],
        "timeframe": "15m", "horizon": "intraday", "market_type": "spot", "leverage": "1x",
        "session": "beliebig", "regime": "range", "reactivity": "standard",
        "risk": "mittel", "suited_for": "range-/seitwaerts-Phasen, ueberdehnte Ruecksetzer",
        "certainty": "mittel", "efficiency": "mittel",
        "backtest_evidence": "VWAP-Std-Reversion etabliertes Intraday-System (±2sigma/±3sigma als Reversion-Zonen); Touch der Aussenbaender snapt bei normaler Vola oft zum VWAP zurueck. Edge regime-abhaengig (nur Range).",
        "backtest_count": None,
        "freqtrade_template": "VwapReversion", "pinned": False, "source": "seed",
    },
    # --- Krypto-spezifisch ---
    {
        "id": "grid_range", "group": "krypto", "name": "Grid (Raster-Trading)",
        "category": "grid", "crypto_applicable": True,
        "description": "Nutzt die hohe 24/7-Volatilitaet von Krypto: festes Kauf/Verkauf-Raster, verdient an Schwankungen. Range-Begrenzung verhindert Trend-Verluste.",
        "rules": "Preisraster ueber/unter Mittelkurs; kauft tiefer, verkauft hoeher. Begrenzt durch Range; Stop bei Range-Bruch.",
        "params": [
            {"name": "grid_levels", "role": "Anzahl Raster-Stufen", "category": "indikator", "min": 4, "max": 20, "default": 10, "optional": False},
            {"name": "grid_span_pct", "role": "Gesamtspanne des Rasters %", "category": "indikator", "min": 2.0, "max": 15.0, "default": 6.0, "optional": False},
            {"name": "range_stop_pct", "role": "Stop bei Range-Bruch %", "category": "risiko", "min": 1.0, "max": 6.0, "default": 3.0, "optional": True},
        ],
        "risk": "mittel", "suited_for": "seitwaerts-volatile Coins",
        "freqtrade_template": "GridRange", "pinned": False, "source": "seed",
    },
    {
        "id": "dca_dip", "group": "krypto", "name": "DCA (gestaffeltes Nachkaufen)",
        "category": "dca", "crypto_applicable": True,
        "description": "Krypto-Klassiker: kauft in Tranchen bei Ruecksetzern (Dollar-Cost-Averaging), senkt den Einstand. Begrenzte Safety-Orders kappen das Risiko.",
        "rules": "Erst-Einstieg per Signal, weitere Tranchen bei definierten Ruecksetzern; Exit per Gesamt-ROI.",
        "params": [
            {"name": "max_safety_orders", "role": "Max. Nachkauf-Tranchen", "category": "risiko", "min": 1, "max": 5, "default": 3, "optional": False},
            {"name": "step_pct", "role": "Ruecksetzer-Abstand je Tranche %", "category": "indikator", "min": 1.0, "max": 5.0, "default": 2.5, "optional": False},
            {"name": "take_profit_pct", "role": "Gesamt-ROI Take-Profit %", "category": "risiko", "min": 1.0, "max": 5.0, "default": 2.0, "optional": True},
        ],
        "risk": "mittel-hoch", "suited_for": "langfristig aufwaerts, volatil",
        "freqtrade_template": "DcaDip", "pinned": False, "source": "seed",
    },
    {
        "id": "funding_rate_perp", "group": "krypto", "name": "Funding-Rate / Perp-Basis",
        "category": "funding", "crypto_applicable": True,
        "description": "Krypto-spezifisch: nutzt Finanzierungsraten von Perpetual-Futures (Cash-and-Carry-Idee). Benoetigt Futures.",
        "rules": "Position aufbauen, wenn Funding-Rate attraktiv (Long Spot / Short Perp o. ae.); neutralisiert Richtung.",
        "params": [
            {"name": "min_funding_bps", "role": "Mindest-Funding-Rate (bps, 8h)", "category": "krypto", "min": 1, "max": 30, "default": 5, "optional": False},
            {"name": "max_leverage", "role": "Maximaler Hebel", "category": "krypto", "min": 1, "max": 3, "default": 1, "optional": False},
            {"name": "max_hold_hours", "role": "Max. Haltedauer (Funding-Zyklen) h", "category": "session", "min": 8, "max": 48, "default": 24, "optional": True},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 1.0, "max": 3.0, "default": 1.5, "optional": False},
        ],
        "risk": "mittel (aber Futures-Komplexitaet)", "suited_for": "Funding-Phasen, marktneutral",
        "freqtrade_template": "(Vorlage folgt)", "pinned": False, "source": "seed",
    },
    # --- Börseneröffnungen (Session-Open / Sonder-Trade-Typ) -------------------
    # Zeitlich verankerte Systeme: Trigger ist die Eröffnung einer Handelszone,
    # nicht primär ein Indikator. Session-Zeiten in UTC (siehe sessions.py).
    {
        "id": "opening_range_breakout", "group": "krypto", "name": "Opening-Range-Breakout (ORB)",
        "category": "breakout", "crypto_applicable": True,
        "trigger_type": "session_open", "opening_session": "us", "opening_range_min": 15,
        "description": "Kern-Eröffnungssystem: misst die High/Low-Range der ersten 15 Min nach dem Session-Open (US/NY ~13:00 UTC) und handelt den Ausbruch aus dieser Eröffnungs-Range mit Volumen-Bestaetigung.",
        "entry_rules": "Nach dem Session-Open die Opening-Range (erste N Min) bilden; Long, wenn eine 5m-Kerze ueber das Range-High schliesst (Short unter Range-Low), Kerzen-Range > Ø der letzten 5 Kerzen und Volumen >= 1,5x Schnitt.",
        "exit_rules": "Stop am gegenueberliegenden Range-Ende; Take-Profit = Measured Move (Range-Hoehe), Teilgewinn bei 2:1; max. 1 Trade je Seite/Session; Zwangs-Exit am Ende des Handelsfensters.",
        "params": [
            {"name": "opening_range_min", "role": "Laenge der Eröffnungs-Range (Min)", "category": "session", "min": 5, "max": 60, "default": 15, "optional": False},
            {"name": "session", "role": "Session-Open (0=Asia,1=London,2=US)", "category": "session", "min": 0, "max": 2, "default": 2, "optional": False},
            {"name": "volume_multiplier", "role": "Volumen vs. Schnitt (Bestaetigung)", "category": "volumen", "min": 1.2, "max": 2.5, "default": 1.5, "optional": False},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 1.0, "max": 5.0, "default": 2.0, "optional": False},
            {"name": "take_profit_pct", "role": "Take-Profit in %", "category": "risiko", "min": 1.0, "max": 6.0, "default": 3.0, "optional": True},
            {"name": "session_window_min", "role": "Handelsfenster nach Open (Min)", "category": "session", "min": 30, "max": 180, "default": 90, "optional": True},
        ],
        "timeframe": "5m", "horizon": "intraday", "market_type": "futures", "leverage": "2x",
        "session": "us", "regime": "volatil", "reactivity": "hoch",
        "risk": "mittel-hoch", "suited_for": "Volatilitaets-Schub an der Eröffnung",
        "certainty": "mittel", "backtest_evidence": "ORB breit belegt (Aktien/Futures, out-of-sample), Trefferquote ~40-60%; Krypto-Uebertrag plausibel.",
        "freqtrade_template": "SessionOpenBreakout", "pinned": False, "source": "seed",
    },
    {
        "id": "session_open_momentum", "group": "krypto", "name": "Session-Open-Momentum (Killzone)",
        "category": "momentum", "crypto_applicable": True,
        "trigger_type": "session_open", "opening_session": "london", "opening_range_min": 30,
        "description": "Handelt den ersten gerichteten Impuls in der Eröffnungs-Killzone (London ~07:00 UTC bzw. US ~13:00 UTC): Grossakteure treiben Volumen/Volatilitaet. Ausserhalb des Open-Fensters pausiert der Bot.",
        "entry_rules": "Nur im Open-Fenster aktiv; Long bei Momentum-Ausbruch (Close > EMA(20) UND ueber dem Open-Range-High) mit steigendem Volumen.",
        "exit_rules": "Stop unter VWAP/Open-Range-Low; Exit bei VWAP-Verlust oder am Ende des Handelsfensters.",
        "params": [
            {"name": "session", "role": "Session-Open (0=Asia,1=London,2=US)", "category": "session", "min": 0, "max": 2, "default": 1, "optional": False},
            {"name": "opening_range_min", "role": "Impuls-Referenz-Range (Min)", "category": "session", "min": 10, "max": 45, "default": 30, "optional": False},
            {"name": "ema_period", "role": "Momentum-EMA-Periode", "category": "indikator", "min": 10, "max": 50, "default": 20, "optional": False},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 1.0, "max": 4.0, "default": 1.8, "optional": False},
            {"name": "session_window_min", "role": "Handelsfenster nach Open (Min)", "category": "session", "min": 30, "max": 120, "default": 75, "optional": True},
        ],
        "timeframe": "5m", "horizon": "intraday", "market_type": "futures", "leverage": "2x",
        "session": "london", "regime": "trend", "reactivity": "hoch",
        "risk": "mittel-hoch", "suited_for": "impulsstarke Eröffnungen (EU/US)",
        "certainty": "mittel", "backtest_evidence": "Session-Vola-Spitzen empirisch (amberdata, Springer 'tea time'); Killzone-Logik weit verbreitet, Belege gemischt.",
        "freqtrade_template": "SessionOpenBreakout", "pinned": False, "source": "seed",
    },
    {
        "id": "monday_asia_open_trend", "group": "krypto", "name": "Monday-Asia-Open-Trend",
        "category": "momentum", "crypto_applicable": True,
        "trigger_type": "session_open", "opening_session": "asia", "opening_range_min": 60,
        "description": "Nutzt den empirischen 'Monday-Asia-Open-Effekt': Intraday-Trendfolge ist ab So ~19:00 NY (≈ 00:00 UTC Mo, Tokio-Open) rund 24 h ueberdurchschnittlich. Geht zum Wochenstart mit dem Trend.",
        "entry_rules": "Aktiv ab dem Asia-Open am Wochenstart; Long, wenn der Preis ueber EMA(50) UND ueber dem Open-Range-High der ersten Stunde liegt.",
        "exit_rules": "Trailing-Stop; Exit nach ~24 h (Effekt-Fenster) oder bei Trendbruch unter EMA(50).",
        "params": [
            {"name": "opening_range_min", "role": "Open-Range-Laenge (Min)", "category": "session", "min": 30, "max": 120, "default": 60, "optional": False},
            {"name": "ema_period", "role": "Trend-EMA-Periode", "category": "indikator", "min": 20, "max": 100, "default": 50, "optional": False},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 1.5, "max": 5.0, "default": 3.0, "optional": False},
            {"name": "max_hold_hours", "role": "Max. Haltedauer (h)", "category": "session", "min": 6, "max": 36, "default": 24, "optional": True},
        ],
        "timeframe": "15m", "horizon": "intraday", "market_type": "spot", "leverage": "1x",
        "session": "asia", "regime": "trend", "reactivity": "standard",
        "risk": "mittel", "suited_for": "Wochenstart, Trend-Anschub",
        "certainty": "mittel", "backtest_evidence": "Concretum/Quantpedia: Intraday-Trend stark ab So 19:00 NY in 2018-2025; Effekt post-2020 ausgepraegter.",
        "freqtrade_template": "SessionOpenBreakout", "pinned": False, "source": "seed",
    },
    {
        "id": "opening_fade_reversion", "group": "krypto", "name": "Opening-Fade (Failed-Breakout)",
        "category": "mean_reversion", "crypto_applicable": True,
        "trigger_type": "session_open", "opening_session": "us", "opening_range_min": 15,
        "description": "Gegenstueck zum ORB: handelt gescheiterte Eröffnungs-Ausbrueche. Bricht der Preis nach dem Open kurz aus der Range aus, kehrt aber bei niedrigem Volumen schnell zurueck, wird die Gegenbewegung Richtung Range-Mitte/VWAP gehandelt.",
        "entry_rules": "Nach dem Session-Open: Ausbruch aus der Opening-Range OHNE Volumen-Bestaetigung (< 1x Schnitt) und schnelle Rueckkehr in die Range → Fade in Gegenrichtung des Fehlausbruchs.",
        "exit_rules": "Ziel Range-Mitte/VWAP; enger Stop knapp ausserhalb des Ausbruch-Extrems; Exit am Ende des Handelsfensters.",
        "params": [
            {"name": "opening_range_min", "role": "Eröffnungs-Range (Min)", "category": "session", "min": 5, "max": 45, "default": 15, "optional": False},
            {"name": "session", "role": "Session-Open (0=Asia,1=London,2=US)", "category": "session", "min": 0, "max": 2, "default": 2, "optional": False},
            {"name": "max_volume_multiplier", "role": "Max. Volumen fuer Fade (Schwaeche)", "category": "volumen", "min": 0.5, "max": 1.2, "default": 1.0, "optional": False},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 0.8, "max": 3.0, "default": 1.5, "optional": False},
        ],
        "timeframe": "5m", "horizon": "intraday", "market_type": "spot", "leverage": "1x",
        "session": "us", "regime": "range", "reactivity": "hoch",
        "risk": "mittel", "suited_for": "ruhige/range-artige Eröffnungen, Fehlausbrueche",
        "certainty": "niedrig", "backtest_evidence": "Failed-Breakout-Fade anekdotisch verbreitet; saubere Krypto-Belege schmal -> vorsichtig.",
        "freqtrade_template": "SessionOpenBreakout", "pinned": False, "source": "seed",
    },
    # --- Markt-neutral / Arbitrage (Market-Making, Pairs-/Statistical-Arbitrage) ---------
    # Richtungs-NEUTRAL: verdienen an Spread/Konvergenz/Liquiditaet, nicht an der Marktrichtung.
    {
        "id": "pairs_spread_reversion", "group": "krypto", "name": "Pairs-Trading (Spread-Reversion)",
        "category": "pairs_arb", "crypto_applicable": True, "market_neutral": True,
        "description": "Marktneutral: handelt den Spread zweier kointegrierter Krypto-Assets (z. B. ETH/BTC). Long das relativ schwache, short das relativ starke Bein, wenn der Spread (Z-Score) extrem ist — Gewinn bei Rueckkehr zum Mittel, unabhaengig von der Marktrichtung.",
        "entry_rules": "Spread = preisnormierte Differenz A-B; Z-Score ueber Rolling-Fenster. Long A / Short B bei Z < -entry_z (A relativ unterbewertet); Short A / Long B bei Z > +entry_z.",
        "exit_rules": "Schliessen bei Rueckkehr |Z| < exit_z (Konvergenz); Z-Stop bei weiterer Divergenz (|Z| > stop_z, Kointegration gebrochen); Zeit-Stop max_hold.",
        "params": [
            {"name": "lookback", "role": "Z-Score-Fenster (Kerzen)", "category": "indikator", "min": 30, "max": 200, "default": 80, "optional": False},
            {"name": "entry_z", "role": "Einstiegs-Z-Score", "category": "indikator", "min": 1.5, "max": 3.0, "default": 2.0, "optional": False},
            {"name": "exit_z", "role": "Ausstiegs-Z-Score (Mitte)", "category": "indikator", "min": 0.0, "max": 1.0, "default": 0.3, "optional": False},
            {"name": "stop_z", "role": "Z-Score-Stop (Divergenz)", "category": "risiko", "min": 3.0, "max": 5.0, "default": 3.5, "optional": False},
            {"name": "max_hold_hours", "role": "Max. Haltedauer (h)", "category": "session", "min": 6, "max": 72, "default": 24, "optional": True},
        ],
        "timeframe": "15m", "horizon": "intraday", "market_type": "futures", "leverage": "1x",
        "session": "beliebig", "regime": "range", "reactivity": "standard",
        "risk": "mittel (Kointegrations-Bruch)", "suited_for": "korrelierte Paare, Seitwaerts",
        "certainty": "mittel", "backtest_evidence": "Pairs-Trading klassisch belegt (Aktien/Krypto); Edge schwindet mit Crowding, Kointegration instabil -> laufend pruefen.",
        "freqtrade_template": "(Vorlage folgt)", "pinned": False, "source": "seed",
    },
    {
        "id": "statarb_basket_meanrev", "group": "krypto", "name": "Statistical-Arbitrage (Korb-Reversion)",
        "category": "pairs_arb", "crypto_applicable": True, "market_neutral": True,
        "description": "Marktneutral: bildet einen Korb korrelierter Altcoins, misst die Abweichung jedes Coins vom Korb-Mittel und setzt auf Konvergenz (long die Nachzuegler, short die Ausreisser). Verteiltes Pairs-Trading ueber viele Coins.",
        "entry_rules": "Je Coin Residuum ggue. Korb-Index (gleichgewichtet) als Z-Score. Long Coins mit Z < -entry_z, Short Coins mit Z > +entry_z; dollar-neutral gewichten.",
        "exit_rules": "Rebalancing bei Mittel-Rueckkehr (|Z| < exit_z); Korb periodisch neu schaetzen; Stop je Bein bei extremer Einzeldivergenz.",
        "params": [
            {"name": "basket_size", "role": "Anzahl Coins im Korb", "category": "indikator", "min": 4, "max": 20, "default": 8, "optional": False},
            {"name": "lookback", "role": "Residuum-Fenster", "category": "indikator", "min": 30, "max": 200, "default": 96, "optional": False},
            {"name": "entry_z", "role": "Einstiegs-Z-Score", "category": "indikator", "min": 1.0, "max": 2.5, "default": 1.5, "optional": False},
            {"name": "exit_z", "role": "Ausstiegs-Z-Score", "category": "indikator", "min": 0.0, "max": 1.0, "default": 0.3, "optional": True},
        ],
        "timeframe": "1h", "horizon": "intraday", "market_type": "futures", "leverage": "1x",
        "session": "beliebig", "regime": "range", "reactivity": "ruhig",
        "risk": "mittel (Faktor-/Regime-Risiko)", "suited_for": "viele korrelierte Altcoins",
        "certainty": "mittel", "backtest_evidence": "Cross-Sectional-Stat-Arb breit erforscht; Deflated-Sharpe beachten (viele Kombinationen) -> nach oben verzerrt.",
        "freqtrade_template": "(Vorlage folgt)", "pinned": False, "source": "seed",
    },
    {
        "id": "funding_market_making", "group": "krypto", "name": "Market-Making (Spread + Funding)",
        "category": "market_making", "crypto_applicable": True, "market_neutral": True,
        "description": "Stellt passiv Liquiditaet beidseitig nah am Mid-Price (Maker-Limit-Orders), verdient Bid-Ask-Spread + Maker-Rebate und haelt das Inventar nahe neutral. Zusaetzlich Funding-Vereinnahmung. Profitiert von Ruhe, leidet unter Trends.",
        "entry_rules": "Passive Quotes bei Mid ± spread_bps beidseitig; bei Fill Gegenseite nachlegen. Quote-Skew proportional zum Inventar (skew_factor), um Richtung neutral zu halten.",
        "exit_rules": "Inventar-Limit (inventory_limit): bei Ueberschreitung aggressiver abbauen; Quoting pausieren/weiten bei starkem Trend (trend_filter, MM-Killer); harter Stop bei Limit-Bruch.",
        "params": [
            {"name": "spread_bps", "role": "Quote-Abstand vom Mid (bps)", "category": "krypto", "min": 2, "max": 30, "default": 8, "optional": False},
            {"name": "order_size", "role": "Order-Groesse je Quote (USDT)", "category": "risiko", "min": 10, "max": 200, "default": 50, "optional": False},
            {"name": "inventory_limit", "role": "Max. Netto-Inventar (USDT)", "category": "risiko", "min": 50, "max": 500, "default": 200, "optional": False},
            {"name": "skew_factor", "role": "Quote-Skew je Inventar", "category": "indikator", "min": 0.2, "max": 2.0, "default": 1.0, "optional": True},
            {"name": "trend_filter", "role": "Trend-Pause (ATR/EMA-Schwelle)", "category": "indikator", "min": 0, "max": 3, "default": 1, "optional": True},
        ],
        "timeframe": "1m", "horizon": "scalp", "market_type": "spot", "leverage": "1x",
        "session": "beliebig", "regime": "range", "reactivity": "hoch",
        "risk": "mittel (Trend-/Adverse-Selection)", "suited_for": "liquide, ruhige Maerkte",
        "certainty": "mittel", "backtest_evidence": "Market-Making etabliert (Avellaneda-Stoikov); profitabel nur mit Maker-Fees/Rebate + striktem Inventar-Risk, Adverse-Selection real.",
        "freqtrade_template": "(Vorlage folgt)", "pinned": False, "source": "seed",
    },
    {
        "id": "avellaneda_inventory_mm", "group": "krypto", "name": "Inventory-MM (Avellaneda-Stoikov)",
        "category": "market_making", "crypto_applicable": True, "market_neutral": True,
        "description": "Modellbasiertes Market-Making: berechnet einen Reservationspreis (Mid, verschoben nach Inventar & Risikoaversion) und optimale Quote-Abstaende aus Volatilitaet/Orderflow. Haelt Inventar systematisch neutral — die quantitative Form des Liquiditaetsstellens.",
        "entry_rules": "Reservationspreis r = Mid - inventar·gamma·sigma²·(T-t); Quotes symmetrisch um r mit optimalem Half-Spread aus gamma/sigma und Orderbuch-Tiefe.",
        "exit_rules": "Kontinuierliches Requoting; Inventar-Mean-Reversion ueber den Skew; Notfall-Abbau bei Inventar-/Drawdown-Limit; Pause bei Vola-Spike.",
        "params": [
            {"name": "gamma", "role": "Risikoaversion (Inventar-Strafe)", "category": "risiko", "min": 0.01, "max": 1.0, "default": 0.1, "optional": False},
            {"name": "vol_window", "role": "Volatilitaets-Fenster (sigma)", "category": "indikator", "min": 20, "max": 120, "default": 60, "optional": False},
            {"name": "inventory_limit", "role": "Max. Netto-Inventar (USDT)", "category": "risiko", "min": 50, "max": 500, "default": 200, "optional": False},
            {"name": "order_size", "role": "Order-Groesse je Quote (USDT)", "category": "risiko", "min": 10, "max": 200, "default": 50, "optional": True},
        ],
        "timeframe": "1m", "horizon": "scalp", "market_type": "spot", "leverage": "1x",
        "session": "beliebig", "regime": "range", "reactivity": "hoch",
        "risk": "mittel-hoch (Modell-/Vola-Risiko)", "suited_for": "liquide Maerkte, quant. MM",
        "certainty": "mittel", "backtest_evidence": "Avellaneda-Stoikov (2008) breit zitiert; reale Profitabilitaet stark fee-/latenz-abhaengig -> in Demo vorsichtig bewerten.",
        "freqtrade_template": "(Vorlage folgt)", "pinned": False, "source": "seed",
    },
    # --- Short-FAEHIGE / short-SPEZIALISIERTE Systeme (klar deklariert via direction) -----------
    # GERICHTET (nicht market_neutral): verdienen an FALLENDEN Kursen (Futures). Ehrlich (Gesetz 2):
    # Krypto hat einen langfristigen Aufwaerts-Drift -> reine Short-Systeme sind schwerer als Longs;
    # die belegbarsten Short-Edges sind (a) Downside-MOMENTUM/Breakdown und (b) FUNDING-bewusste
    # Shorts (negatives Funding = anhaltende Baissestimmung). Mean-Reversion-Shorts gegen den Drift
    # = niedrige certainty. Validierungs-Tiefe (OOS/Funding/Slippage) bleibt der Engpass.
    {
        "id": "downside_breakout_short", "group": "krypto", "name": "Downside-Breakout (Short)",
        "category": "breakout", "crypto_applicable": True, "direction": "both",
        "description": "Spiegelbild des Volatilitaets-Breakouts nach UNTEN: short, wenn der Kurs unter ein N-Perioden-Tief (Donchian-Tief) bricht UND das Volumen bestaetigt. Downside-Momentum ist der robusteste gerichtete Short-Edge (Trendfortsetzung im Abwaerts-Regime). Futures.",
        "entry_rules": "Short, wenn close < rollendes N-Perioden-Tief (low.rolling(N).min()) UND Volumen > Faktor·Durchschnitt. Optional HMM-trend_down-Bestaetigung.",
        "exit_rules": "Deckeln beim Gegen-Ausbruch ueber das N-Perioden-Hoch; ATR-/Prozent-Stop; Trailing im Profit.",
        "params": [
            {"name": "bb_period", "role": "Kanal-Laenge N (Donchian)", "category": "indikator", "min": 20, "max": 60, "default": 30, "optional": False},
            {"name": "volume_multiplier", "role": "Volumen-Bestaetigung (×Schnitt)", "category": "volumen", "min": 1.0, "max": 3.0, "default": 2.0, "optional": False},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 2.0, "max": 6.0, "default": 4.5, "optional": False},
        ],
        "timeframe": "5m", "horizon": "intraday", "market_type": "futures", "leverage": "3x",
        "session": "beliebig", "regime": "volatil", "reactivity": "hoch",
        "risk": "mittel-hoch (Short-Squeeze)", "suited_for": "Abwaerts-Regime, Breakdown-Momentum",
        "certainty": "mittel", "backtest_evidence": "Volatilitaets-Breakout breit belegt (long); die Short-Spiegelung greift im Abwaerts-Regime, ist aber squeeze-anfaellig -> Stop diszipliniert.",
        "freqtrade_template": "FuturesBreakoutVol", "pinned": False, "source": "seed",
    },
    {
        "id": "trend_flip_short", "group": "krypto", "name": "Trend-Flip Short (Supertrend)",
        "category": "trend", "crypto_applicable": True, "direction": "both",
        "description": "ATR-Trendfolge in BEIDE Richtungen: short beim Supertrend-Abwaerts-Flip (Schlusskurs durchbricht das obere ATR-Band), Long-Exit/Short-Entry symmetrisch. Bleibt im vorherrschenden Trend statt jeden Pullback zu handeln. Futures.",
        "entry_rules": "Short, wenn der Supertrend von auf->ab kippt (close < oberes ATR-Band, vorher Aufwaerts). Optional Makro-SMA-Filter: Short nur unter dem langen SMA (Abwaertstrend).",
        "exit_rules": "Short decken beim Aufwaerts-Flip; ATR-/Prozent-Stop; Trend laufen lassen (lockeres ROI).",
        "params": [
            {"name": "atr_period", "role": "ATR-Periode", "category": "indikator", "min": 7, "max": 20, "default": 10, "optional": False},
            {"name": "atr_mult", "role": "ATR-Bandbreite", "category": "indikator", "min": 1.5, "max": 4.0, "default": 3.0, "optional": False},
            {"name": "macro_sma_period", "role": "Makro-Trendfilter (SMA)", "category": "indikator", "min": 0, "max": 300, "default": 0, "optional": True},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 3.0, "max": 8.0, "default": 6.0, "optional": False},
        ],
        "timeframe": "15m", "horizon": "intraday", "market_type": "futures", "leverage": "3x",
        "session": "beliebig", "regime": "trend", "reactivity": "standard",
        "risk": "mittel (Whipsaw im Chop)", "suited_for": "klare Abwaertstrends",
        "certainty": "mittel", "backtest_evidence": "Supertrend-Trendfolge dokumentiert (BTC ~33% CAGR long, boringedge/quantifiedstrategies); die Short-Seite traegt im Abwaerts-Regime, leidet im Chop.",
        "freqtrade_template": "Supertrend", "pinned": False, "source": "seed",
    },
    {
        "id": "funding_aware_short", "group": "krypto", "name": "Funding-bewusster Short",
        "category": "trend", "crypto_applicable": True, "direction": "short",
        "description": "Short-SPEZIALISIERT: nutzt die Perp-Funding-Rate als Regime-/Bias-Signal. Anhaltend NEGATIVES Funding signalisiert breite Baissestimmung (Shorts zahlen, Longs kapitulieren) -> bevorzugt gerichtete Shorts im Abwaerts-Regime; bei POSITIVEM Funding kassiert der Short zusaetzlich Carry. KEIN markt-neutraler Funding-Arb (das ist eine eigene Kategorie), sondern ein gerichteter Short mit Funding-Filter.",
        "entry_rules": "Short-Bias nur, wenn Funding-Bedingung erfuellt (z. B. Funding < funding_threshold ODER Funding > 0 fuer Carry) UND ein Abwaerts-Trigger feuert (EMA-/MACD-Abwaerts-Cross oder Breakdown). Im Aufwaerts-Regime KEIN Short.",
        "exit_rules": "Decken bei Trend-Umkehr (Aufwaerts-Cross) oder wenn Funding-Bedingung kippt; Stop-Loss; Funding-Vereinnahmung als Bonus, nie als alleinige These.",
        "params": [
            {"name": "funding_threshold", "role": "Funding-Schwelle (Bias-Gate)", "category": "krypto", "min": -0.0005, "max": 0.0005, "default": 0.0, "optional": False},
            {"name": "ema_fast", "role": "EMA schnell (Trigger)", "category": "indikator", "min": 8, "max": 30, "default": 12, "optional": False},
            {"name": "ema_slow", "role": "EMA langsam (Trigger)", "category": "indikator", "min": 30, "max": 100, "default": 50, "optional": False},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 2.0, "max": 6.0, "default": 4.0, "optional": False},
        ],
        "timeframe": "1h", "horizon": "intraday", "market_type": "futures", "leverage": "2x",
        "session": "beliebig", "regime": "trend", "reactivity": "ruhig",
        "risk": "hoch (Short gegen Krypto-Drift)", "suited_for": "Abwaerts-Regime, negatives Funding",
        "certainty": "niedrig", "backtest_evidence": "Funding als Stimmungs-/Regime-Signal gut dokumentiert (negatives Funding markiert Baisse-Phasen); als alleiniger gerichteter Short-Edge schmal belegt -> nur gefiltert + diszipliniert, NICHT gegen den langfristigen Drift dauer-shorten.",
        "freqtrade_template": "(Vorlage folgt)", "pinned": False, "source": "seed",
    },
    {
        "id": "squeeze_momentum_release", "group": "krypto", "name": "Squeeze-Momentum-Release (Long/Short)",
        "category": "breakout", "crypto_applicable": True, "direction": "both",
        "description": "Volatilitaets-Kompression (TTM-Squeeze, Carter): wenn die Bollinger-Baender INNERHALB der Keltner-Kanaele liegen, ist der Markt 'geladen'. Beim Loesen der Kompression in Richtung des Momentums ein- (long ODER short je Momentum-Vorzeichen). Richtungs-agnostisch -> liefert auch Short-Signale.",
        "entry_rules": "Squeeze aktiv, wenn BB innerhalb KC. Beim Loesen (BB verlassen KC) Position in Richtung des Momentum-Histogramms: Momentum>0 -> long, Momentum<0 -> short.",
        "exit_rules": "Exit, wenn das Momentum-Histogramm dreht (Vorzeichen-/Steigungswechsel); ATR-Stop; Zeit-Stop, falls die Kompression ohne Folge bleibt.",
        "params": [
            {"name": "bb_period", "role": "Bollinger-Periode", "category": "indikator", "min": 14, "max": 30, "default": 20, "optional": False},
            {"name": "kc_mult", "role": "Keltner-ATR-Faktor", "category": "indikator", "min": 1.0, "max": 2.5, "default": 1.5, "optional": False},
            {"name": "mom_period", "role": "Momentum-Fenster", "category": "indikator", "min": 8, "max": 20, "default": 12, "optional": True},
            {"name": "stop_loss_pct", "role": "Stop-Loss in %", "category": "risiko", "min": 2.0, "max": 6.0, "default": 4.0, "optional": False},
        ],
        "timeframe": "15m", "horizon": "intraday", "market_type": "futures", "leverage": "2x",
        "session": "beliebig", "regime": "volatil", "reactivity": "standard",
        "risk": "mittel (Fehlausbruch)", "suited_for": "Volatilitaets-Kompression vor Ausbruch",
        "certainty": "mittel", "backtest_evidence": "TTM-Squeeze (Carter) breit genutzt; richtungs-agnostisch -> liefert Short-Signale im Abwaerts-Ausbruch. Fehlausbrueche real -> Momentum-Bestaetigung + Stop.",
        "freqtrade_template": "(Vorlage folgt)", "pinned": False, "source": "seed",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Eröffnungs-Seed-Systeme (Sonder-Trade-Typ): sollen IMMER im Katalog verfuegbar
# sein — auch in einem KI-Katalog, der den Seed sonst nicht uebernimmt.
OPENING_SEED_SYSTEMS = [s for s in SEED_CATALOG if s.get("trigger_type") == "session_open"]
# Markt-neutrale Archetypen (Market-Making, Pairs-/Statistical-Arbitrage) — eigene Kategorie.
MARKET_NEUTRAL_SEED_SYSTEMS = [s for s in SEED_CATALOG if s.get("market_neutral")]
# Short-faehige/-spezialisierte Systeme (klar deklariert) — sollen IMMER im Katalog verfuegbar sein,
# auch im KI-Katalog (analog Opening/MN), damit die Short-Seite sichtbar bleibt.
SHORT_SEED_SYSTEMS = [s for s in SEED_CATALOG if s.get("direction") in ("short", "both")]


def _ensure_seeds(systems: list[dict], seeds: list[dict]) -> tuple[list[dict], bool]:
    """Injiziert fehlende Seed-Systeme (per id) und **heilt** leere Beleg-/Regelfelder
    bereits vorhandener Kopien — garantiert, dass eine Seed-Gruppe verfuegbar UND vollstaendig
    ist, unabhaengig von der Katalog-Quelle (seed/ai). Heilen fuellt nur LEERE Felder aus dem
    Seed nach; Nutzer-Zustand (pinned/activated/validated/freqtrade_template) bleibt unberuehrt.
    Idempotent. Returns (Systeme, changed)."""
    by_seed = {s["id"]: _normalize_system(s) for s in seeds}
    have = {s.get("id"): s for s in systems}
    changed = False
    for sid, seed in by_seed.items():
        cur = have.get(sid)
        if cur is None:
            continue
        for f in ("entry_rules", "exit_rules", "description"):
            if not cur.get(f) and seed.get(f):
                cur[f] = seed[f]
                changed = True
    added = [by_seed[sid] for sid in by_seed if sid not in have]
    if added:
        return systems + added, True
    return systems, changed


def _ensure_opening_systems(systems: list[dict]) -> tuple[list[dict], bool]:
    """Stellt die Eröffnungs-Seed-Systeme (Session-Open) sicher. Siehe ``_ensure_seeds``."""
    return _ensure_seeds(systems, OPENING_SEED_SYSTEMS)


def _ensure_market_neutral_systems(systems: list[dict]) -> tuple[list[dict], bool]:
    """Stellt die Markt-neutral-/Arbitrage-Seed-Systeme sicher. Siehe ``_ensure_seeds``."""
    return _ensure_seeds(systems, MARKET_NEUTRAL_SEED_SYSTEMS)


def _ensure_short_systems(systems: list[dict]) -> tuple[list[dict], bool]:
    """Stellt die short-faehigen/-spezialisierten Seed-Systeme sicher. Siehe ``_ensure_seeds``."""
    return _ensure_seeds(systems, SHORT_SEED_SYSTEMS)


# ---------------------------------------------------------------- Quellen
def get_research_sources() -> dict:
    custom = (jsonstore.read_json(SOURCES_FILE, {}) or {}).get("custom", [])
    return {"defaults": DEFAULT_SOURCES, "custom": custom}


def add_research_source(name: str, url: str, note: str = "") -> dict:
    data = get_research_sources()
    data["custom"] = [s for s in data["custom"] if s.get("name") != name]
    data["custom"].append({"name": name, "url": url, "note": note})
    jsonstore.write_atomic(SOURCES_FILE, {"custom": data["custom"]})
    audit.record("research_source_added", name=name, url=url)
    return get_research_sources()


def remove_research_source(name: str) -> dict:
    data = get_research_sources()
    data["custom"] = [s for s in data["custom"] if s.get("name") != name]
    jsonstore.write_atomic(SOURCES_FILE, {"custom": data["custom"]})
    audit.record("research_source_removed", name=name)
    return get_research_sources()


# ---------------------------------------------------------------- Katalog
def _needs_migration(systems: list[dict]) -> bool:
    return any("group" not in s or "crypto_applicable" not in s for s in systems)


def get_catalog() -> dict:
    doc = _get_catalog_raw()
    # Read-time: Sicherheits-/Effizienz-Scores gegen die AKTUELLE Eigen-Evidenz anhängen (reproduzierbar).
    own = own_evidence()
    doc = dict(doc)
    doc["systems"] = attach_scores(doc.get("systems", []), own)
    return doc


def _get_catalog_raw() -> dict:
    doc = jsonstore.read_json(CATALOG_FILE, None)   # None = keine Datei; .bak-Recovery bei Defekt
    if not doc:
        return _save_catalog(SEED_CATALOG, source="seed")
    # Altes Schema ODER veraltete Seed-Version -> neu seeden (uebernimmt neue Vorlagen).
    if _needs_migration(doc.get("systems", [])) or doc.get("seed_version", 0) < SEED_VERSION:
        if doc.get("source") != "ai":  # KI-Katalog nicht ueberschreiben
            return _save_catalog(SEED_CATALOG, source="seed")
    # Sonder-Archetypen immer sicherstellen (auch im KI-Katalog) + einmalig persistieren:
    # Börseneröffnungen (Session-Open) und Markt-neutral/Arbitrage (Market-Making, Pairs/Stat-Arb).
    merged, ch1 = _ensure_opening_systems(doc.get("systems", []))
    merged, ch2 = _ensure_market_neutral_systems(merged)
    merged, ch3 = _ensure_short_systems(merged)
    if ch1 or ch2 or ch3:
        return _save_catalog(merged, source=doc.get("source", "seed"))
    return doc


def _save_catalog(systems: list[dict], source: str) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    systems = [_normalize_system(s) for s in systems]  # einheitliches Schema
    doc = {"updated_at": _now(), "source": source, "focus": "crypto",
           "seed_version": SEED_VERSION, "systems": systems}
    jsonstore.write_atomic(CATALOG_FILE, doc)   # atomar (kein Crash-Halbschreiben) + .bak
    return doc


def refresh_catalog(settings: Settings, max_systems: int | None = None,
                    max_tokens: int | None = None, critique: bool = True,
                    focus: str | None = None) -> dict:
    """Aktualisiert den Krypto-Katalog mit Alters-Verwaltung.

    - Setzt `added_at` (Ersterfassung) und `last_seen` (zuletzt gefunden).
    - Angepinnte Systeme bleiben immer erhalten.
    - Nicht-gepinnte Systeme, die laenger als `max_age_days` nicht mehr gefunden
      wurden, werden **aussortiert** (veraltet).
    - **Kein Daten-Downgrade:** scheitert die Live-Recherche (oder fehlt der Key),
      bleibt ein bereits vorhandener Katalog unveraendert erhalten — nur beim allerersten
      Lauf (leerer Katalog) wird der Seed verwendet.
    - ``max_systems``/``max_tokens`` reichen „Max-Power"-Parameter durch.
    """
    cfg = get_research_config()
    now = _now()
    existing = {s["id"]: s for s in get_catalog()["systems"]}
    pinned_ids = {sid for sid, s in existing.items() if s.get("pinned")}

    if settings.anthropic_api_key:
        new_systems, source = _research_with_ai(settings, max_systems=max_systems,
                                                 max_tokens=max_tokens, critique=critique, focus=focus)
    else:
        new_systems, source = None, "no_key"
    if not new_systems:
        if existing:  # bestehenden Katalog NICHT mit Seed ueberschreiben
            audit.record("catalog_refresh_kept", reason=source, count=len(existing))
            return get_catalog()
        new_systems, source = SEED_CATALOG, "seed"
    new_systems = [s for s in new_systems if s.get("crypto_applicable", True)]

    result: list[dict] = []
    # 1) angepinnte erhalten (Daten behalten, frisch gesehen)
    for sid in pinned_ids:
        s = dict(existing[sid]); s["last_seen"] = now; result.append(s)
    # 2) neue/aktualisierte Systeme (added_at erhalten, last_seen=jetzt)
    for s in new_systems:
        if s["id"] in pinned_ids:
            continue
        s = dict(s)
        s["added_at"] = (existing.get(s["id"], {}).get("added_at") or now)
        s["last_seen"] = now
        result.append(s)

    # 3) Alter aussortieren (nur nicht-gepinnte)
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(cfg.get("max_age_days", 30)))
    fresh: list[dict] = []
    dropped = 0
    for s in result:
        if s.get("pinned"):
            fresh.append(s); continue
        try:
            if datetime.fromisoformat(s.get("last_seen")) >= cutoff:
                fresh.append(s)
            else:
                dropped += 1
        except Exception:
            fresh.append(s)

    doc = _save_catalog(fresh, source=source)
    audit.record("catalog_refreshed", source=source, count=len(fresh),
                 pinned=len(pinned_ids), dropped_old=dropped, max_age_days=cfg.get("max_age_days"))
    return doc


def _salvage_objects(text: str) -> list[dict]:
    """Extrahiert vollständige top-level JSON-Objekte aus einem (evtl. abgeschnittenen)
    Array. Ein am Ende abgeschnittenes Objekt (kein schließendes ``}``) wird einfach
    übersprungen — so liefert eine durch ``max_tokens`` gekürzte Antwort trotzdem die
    vollständigen Systeme statt gar nichts.
    """
    i = text.find("[")
    if i < 0:
        return []
    out: list[dict] = []
    depth = 0
    start: int | None = None
    in_str = False
    esc = False
    for j in range(i + 1, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = j
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    out.append(json.loads(text[start:j + 1]))
                except Exception:
                    pass
                start = None
    return out


def _research_with_ai(settings: Settings, max_systems: int | None = None,
                      max_tokens: int | None = None,
                      critique: bool = True, focus: str | None = None) -> tuple[list[dict] | None, str]:
    """Umfangreiche Live-Krypto-Recherche via Claude + echtem Web-Such-Tool.

    Nutzt das Anthropic ``web_search``-Tool: zieht validierte Quellen heran UND
    sucht aktiv nach neuen (Startsuche: „recent crypto trading strategy content").
    ``max_systems``/``max_tokens`` überschreiben die Defaults (für „Max-Power"-Läufe).
    Faellt bei Fehlern (z. B. Web-Suche nicht freigeschaltet, leeres Ergebnis) auf
    ``(None, "ai_failed")`` zurueck — der Aufrufer überschreibt dann KEINEN bestehenden Katalog.
    """
    try:
        import anthropic

        cfg = get_research_config()
        ms = int(max_systems or cfg.get("max_systems", 8))
        # 28000 statt 16000: das Eröffnungs-Kapitel (opening_focus) verlängert Prompt+Antwort —
        # mit 16000 wurde die JSON-Antwort abgeschnitten (stop_reason=max_tokens, nur Teil gerettet).
        mt = int(max_tokens or 28000)
        sources = get_research_sources()
        src_lines = "\n".join(
            f"- {s['name']}: {s.get('url','')}" for s in sources["defaults"] + sources["custom"]
        )
        futures_line = (
            "Futures-Strategien (mit Hebel) sind ein SCHWERPUNKT — priorisiere sie und liefere "
            "MEHRHEITLICH Futures-Systeme (market_type='futures' inkl. sinnvollem 'leverage'). "
            "Einige gute Spot-Systeme duerfen ergaenzend dabei sein."
            if cfg.get("allow_futures") else
            "NUR Spot-Strategien (market_type='spot'). KEINE Futures/Hebel-Strategien."
        )
        # Sonder-Kapitel „Börseneröffnungen" (eigener Recherche-Schwerpunkt, opt-out).
        opening_block = (
            "\nSONDER-KAPITEL BÖRSENERÖFFNUNGEN (WICHTIGER ZUSATZ-SCHWERPUNKT):\n"
            "- Recherchiere GEZIELT Trade-Systeme, die an MARKT-/SESSION-ERÖFFNUNGEN haengen "
            "(nicht primaer indikator-, sondern ZEIT-getriggert). Liefere davon MINDESTENS 4 Systeme.\n"
            "- Decke ab: (a) Opening-Range-Breakout (ORB), (b) Gap-and-Go / Opening-Drive, "
            "(c) CME-Gap-Fill (Krypto-Wochenend-Gap; beachte: CME 24/7 ab Ende Mai 2026 → Edge laeuft aus), "
            "(d) Session-Open-Momentum / ICT-Killzone, (e) Monday-Asia-Open-Effekt, (f) Opening-Fade / Failed-Breakout.\n"
            "- Session-Opens in UTC angeben/zuordnen: Asia/Tokio ~00:00, London/EU ~07:00, US/NY ~13:00, "
            "EU↔US-Overlap ~13:00–16:00 (Vola-Peak). Empirie: EU-/US-Stunden ueberdurchschnittlich, "
            "Asien meist darunter (Ausnahme Monday-Asia-Open).\n"
            "- Markiere diese Systeme mit trigger_type='session_open', setze opening_session "
            "('asia'|'london'|'us'|'eu_us_overlap') und opening_range_min (Min der Eröffnungs-Range). "
            "Nimm Session-Parameter ('session'/'opening_range_min'/Handelsfenster) in params auf (category='session').\n"
            if cfg.get("opening_focus", True) else ""
        )
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system = (
            "Du bist ein gruendlicher Trading-Strategie-Researcher fuer Kryptowaehrungen. "
            "Du recherchierst im Web, bevorzugst validierte Quellen, suchst aber auch neue. "
            "Du kennst dich besonders mit BÖRSEN-/SESSION-ERÖFFNUNGEN aus (Asia/London/US-Open, "
            "Opening-Range-Breakout, Gap-and-Go, CME-Gap, Killzones, Monday-Asia-Open). "
            "Du lieferst NUR klar definierte, regelbasierte Strategien, die ein Bot befolgen kann."
        )
        prompt = (
            "Recherchiere GRUENDLICH die aktuell besten, KLAR DEFINIERTEN KRYPTO-Trading-Strategien "
            "und liefere eine MOEGLICHST GROSSE, vielfaeltige Auswahl.\n\n"
            "QUELLEN-VORGEHEN (mehrere Suchen nutzen):\n"
            "1) Durchforste ZUERST und GRUENDLICH die beiden Nutzer-YouTube-Kanaele 'Trading Strategie "
            "Analyse' und 'Trading Strategy Testing': suche gezielt deren AKTUELLE Videos, in denen "
            "Strategien GEBACKTESTET werden. Verstehe pro Video das getestete System samt konkreten "
            "Parametern UND den Backtest-Ergebnissen (Anzahl Backtests/Trades, Zeitraum, Win-Rate, "
            "Profit/Drawdown). Leite daraus jeweils ein konkretes, regelbasiertes System ab.\n"
            "2) Pruefe danach die weiteren validierten Quellen sowie gute neue Quellen:\n" + src_lines + "\n\n"
            "MENGE & SCHWERPUNKT (wichtig):\n"
            f"- Liefere INSGESAMT mindestens 15, moeglichst bis zu {ms} Systeme (lieber mehr als weniger).\n"
            "- SCHWERPUNKT SCALPING: mindestens ~10 Scalping-Systeme (horizon='scalp', niedrige Timeframes 1m/3m/5m).\n"
            "- Aus JEDER Kategorie (regime: trend / range / volatil) MINDESTENS ~4 Systeme, fuer breite Abdeckung.\n"
            "- ABDECKUNG DER TRADING-ARCHETYPEN (so vollstaendig wie krypto-sinnvoll): Trendfolge, Mean-Reversion, "
            "Momentum, Breakout, Grid/DCA, Carry/Funding-Basis, Boerseneroeffnungen (Session-Open) UND — sofern "
            "krypto-tauglich klar umsetzbar — MARKET-MAKING (Liquiditaet/Spread stellen, marktneutral, Maker-Orders/"
            "Inventory) sowie PAIRS-/STATISTICAL-ARBITRAGE (kointegrierte Paare, Spread-Mean-Reversion, marktneutral). "
            "Lass keinen dieser Archetypen grundlos aus.\n"
            "- Vermeide Duplikate; variiere Timeframe, Markt und Logik.\n\n"
            "QUALITAET (hart — wichtiger als bloße Menge):\n"
            "- Uebernimm NUR qualitativ hochwertige, KLAR STRUKTURIERTE Systeme: eindeutige Indikatoren "
            "mit exakten Schwellen, konkrete Ein-/Ausstiegsregeln (inkl. Stop/Take-Profit), eindeutige "
            "Parameter mit Spannen — so, dass ein Bot sie 1:1 umsetzen kann. Vage/schwammige oder nur "
            "narrativ beschriebene Systeme WEGLASSEN.\n"
            "- Aus den YouTube-Backtest-Videos: extrahiere die TATSAECHLICH getesteten Parameter und Regeln "
            "(keine Erfindung). Wenn ein Video keine klar umsetzbaren Regeln liefert, nicht aufnehmen.\n\n"
            "REAKTIVITAET (Loop-Tempo des Bots): setze 'reactivity' je System — 'hoch' fuer Scalping/"
            "sehr niedrige Timeframes (1m/3m; schnelle Ein-/Ausstiege), 'standard' fuer 5m/15m, "
            "'ruhig' fuer 30m+/1h. Bei Scalping ist zu traeges Reagieren gefaehrlich → dann 'hoch'.\n\n"
            "GELTUNGSBEREICH (strikt):\n"
            f"- Zeit-Horizont nur bis max '{cfg.get('horizon_scope')}' (Scalping/Intraday/kurzer Swing <= 1 Tag). "
            "ALLES ueber 1 Tag (Investment/Position-Trading) WEGLASSEN.\n"
            f"- {futures_line}\n"
            "- Nur krypto-taugliche Systeme (crypto_applicable=true). Sonst weglassen.\n"
            "- Zwei Gruppen: group='krypto' (krypto-spezifisch) und group='allgemein' (klassisch, krypto-tauglich).\n"
            + opening_block + "\n"
            "SICHERHEITS-/VERTRAUENS-EINSCHAETZUNG (zentral, EHRLICH bleiben — NICHT halluzinieren):\n"
            "- 'certainty': 'hoch' NUR fuer Systeme mit BELEGTER, METHODISCH SAUBERER Validierung — d. h. "
            "OUT-OF-SAMPLE bzw. WALK-FORWARD getestet (NICHT nur in-sample/kurvenangepasst), ueber MEHRERE "
            "Marktphasen/Regime (Trend UND Range) sowie mehrere Coins/Zeitraeume, konsistent positiv. "
            "'mittel' = plausibel belegt, aber nur einfach/in-sample getestet oder schmal abgedeckt; "
            "'niedrig' = Ideen/Anekdoten ohne solide Belege; 'unbekannt' = keine Beleglage auffindbar. "
            "Achte AKTIV auf Verzerrungen (Look-Ahead-, Survivorship-, Data-Snooping-Bias) und Overfitting "
            "(viele frei tunbare Parameter + nur in-sample) → bei Verdacht certainty SENKEN.\n"
            "- 'backtest_evidence': KURZER Beleg-Text mit (a) METHODE explizit (walk-forward / out-of-sample "
            "/ nur in-sample), (b) Anzahl Backtests/Trades, (c) Zeitraum + Maerkte/Coins, (d) Kernergebnis "
            "(Profit/Drawdown/Win-Rate). Methode IMMER benennen; leer lassen, wenn nichts belegbar.\n"
            "- 'backtest_count': geschaetzte Anzahl belegter Backtests als Zahl, sonst null.\n"
            "- SELEKTIONS-BIAS beachten: wenn eine Kennzahl als 'bestes' aus VIELEN getesteten Varianten/"
            "Parametern herausgepickt wurde (Optimierung ueber viele Kombinationen), ist sie nach oben "
            "verzerrt (vgl. Deflated Sharpe Ratio) → certainty NICHT 'hoch'.\n\n"
            "EFFIZIENZ (zweiter Kern-Score, EHRLICH): 'efficiency' = wie effizient die Strategie Gewinn je "
            "Risiko/Trade erwirtschaftet — bewerte nach Profit-Faktor (>=1,5 viabel, >=2 stark; >3 ist "
            "Overfit-VERDACHT → NICHT 'hoch'), Erwartungswert/Trade, Win-Rate×CRV und Drawdown, sowie "
            "Overtrading (zu viele Trades fressen Edge über Gebühren). 'hoch'|'mittel'|'niedrig'|'unbekannt'. "
            "Hohe Win-Rate ALLEIN ist keine Effizienz (CRV beachten).\n"
            "SYSTEM-KONTEXT (dieses System hat bereits): (a) HMM-REGIME-Erkennung (trend_up/range/trend_down "
            "+ Vola-Regime) → ordne 'regime' sauber zu; (b) FUNDAMENTAL-/EVENT-RISIKO (FOMC/CPI/NFP) → setze "
            "'event_sensitivity' ('hoch' für breakout-/momentum-/news-getriebene Systeme, 'niedrig' für "
            "markt-neutrale/mean-reverting); (c) MARKT-NEUTRALEN SOCKEL → 'market_neutral'=true nur für "
            "richtungs-neutrale Archetypen; (d) OOS-/Deflated-Sharpe-Härtung → 'schöner' In-sample-Backtest "
            "ist ein WARNsignal, kein Gütesiegel; (e) GESTREUTES COIN-UNIVERSUM: jeder Bot handelt NICHT nur "
            "BTC/ETH/SOL, sondern ein breit gestreutes, nach Liquidität gestaffeltes Universum liquider "
            f"Bitget-USDT-Perps ({', '.join(universe.FULL)}), aus dem die volumenstärksten Coins je Horizont "
            "DYNAMISCH ausgewählt werden. Bevorzuge daher Systeme, die auf MEHREREN liquiden Coins funktionieren "
            "(robust/coin-agnostisch); ein System, das nur auf EINEM Coin überfittet ist, bekommt niedrigere "
            "certainty.\n\n"
            "Gib am ENDE NUR ein JSON-Array zurueck (kein weiterer Text danach). Jedes Objekt:\n"
            "id, group, name, category, context (Idee/Marktlogik, 2-3 Saetze), entry_rules (konkret), "
            "exit_rules (konkret inkl. Stop/Take-Profit), "
            "params (Array aus {name, role, category, min, max, default, optional}), timeframe, "
            "horizon ('scalp'|'intraday'|'short_swing'), market_type ('spot'|'futures'), leverage, "
            "session ('asia'|'eu'|'us'|'eu_us_overlap'|'beliebig'), regime ('trend'|'range'|'volatil'), "
            "risk, crypto_applicable (bool), validated (bool), sources (Array aus URLs), "
            "certainty ('hoch'|'mittel'|'niedrig'|'unbekannt'), backtest_evidence (string), backtest_count (int|null), "
            "efficiency ('hoch'|'mittel'|'niedrig'|'unbekannt'), event_sensitivity ('hoch'|'mittel'|'niedrig'), "
            "reactivity ('hoch'|'standard'|'ruhig'), "
            "trigger_type ('signal'|'session_open'; 'session_open' NUR fuer an einer Börseneröffnung "
            "verankerte Systeme), opening_session ('asia'|'london'|'us'|'eu_us_overlap'|'none'; bei "
            "session_open die relevante Eröffnung, sonst 'none'), opening_range_min (int Minuten der "
            "Eröffnungs-Range bei session_open, sonst null), market_neutral (bool; true NUR fuer "
            "richtungs-neutrale Archetypen: Market-Making, Pairs-/Statistical-Arbitrage, sonst false), "
            "direction ('long'|'short'|'both'|'neutral'; KLAR DEKLARIEREN: 'long' nur Long, 'short' "
            "short-SPEZIALISIERT (gerichteter Short, z. B. Downside-Momentum/Breakdown oder "
            "funding-bewusster Short im Abwaerts-Regime), 'both' beide Richtungen (Futures), 'neutral' "
            "fuer market_neutral. EHRLICH: Krypto hat Aufwaerts-Drift -> reine Short-Systeme sind "
            "schwerer; gegen den Drift dauer-zu-shorten verdient niedrige certainty).\n"
            "WICHTIG zu params: 'category' ist eine von "
            "'indikator'|'volumen'|'risiko'|'session'|'krypto'. Liste NUR Parameter, die fuer die "
            "Strategie WIRKLICH relevant sind (irrelevante Kategorien WEGLASSEN). 'optional'=true fuer "
            "Feintuning-Parameter (z. B. Trailing-Stop, Session-Zeiten), 'optional'=false fuer Kern-Parameter."
        )
        # B4: optionaler Nutzer-Schwerpunkt (Freitext) mit hoher Prioritaet voranstellen.
        if focus:
            prompt = (f"NUTZER-SCHWERPUNKT (HOHE PRIORITAET): {focus.strip()}\n"
                      "Richte die Auswahl der Strategien vorrangig hieran aus, ohne die Qualitaetskriterien zu verletzen.\n\n") + prompt
        # Streaming: hebt das 10-Minuten-Limit für nicht-gestreamte Requests auf
        # (sonst lehnt das SDK große max_tokens sofort ab) → erlaubt „Max-Power"-Output.
        # Ein Retry fängt transiente Stream-/Verbindungsabbrüche bei langen Läufen ab.
        TRANSIENT = ("RemoteProtocolError", "APIConnectionError", "APITimeoutError",
                     "InternalServerError", "OverloadedError", "ReadError", "ChunkedEncodingError")
        msg, last_err = None, None
        for attempt in range(2):
            try:
                with client.messages.stream(
                    model=settings.ai_model, max_tokens=mt, system=system,
                    messages=[{"role": "user", "content": prompt}],
                    tools=[{"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": WEB_SEARCH_MAX_USES}],
                ) as stream:
                    msg = stream.get_final_message()
                break
            except Exception as e:
                last_err = e
                if type(e).__name__ in TRANSIENT and attempt == 0:
                    audit.record("catalog_ai_retry", attempt=attempt + 1,
                                 error=f"{type(e).__name__}: {str(e)[:120]}")
                    continue
                raise
        if msg is None:
            raise last_err
        stop_reason = getattr(msg, "stop_reason", None)
        # Nur den FINALEN Text-Block nehmen (frueheren Begruendungstext mit '[' meiden)
        # und mit raw_decode robust gegen nachfolgenden Text parsen.
        blocks = [b.text for b in msg.content if getattr(b, "type", "") == "text" and b.text.strip()]
        text = (blocks[-1] if blocks else "").replace("```json", "").replace("```", "")
        start = text.find("[")
        if start < 0:
            raise ValueError("Kein JSON-Array in der KI-Antwort gefunden")
        try:
            systems, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            # Antwort vermutlich durch max_tokens abgeschnitten -> vollständige Objekte retten.
            systems = _salvage_objects(text)
            if not systems:
                raise
            audit.record("catalog_ai_salvaged", count=len(systems), stop_reason=stop_reason)
        out = []
        for s in systems:
            s["pinned"] = False
            s["source"] = "ai"
            out.append(_normalize_system(s))
        audit.record("catalog_ai_ok", count=len(out))
        if critique and out:
            out = _self_critique(client, settings.ai_model, out)
        return out, "ai"
    except Exception as exc:  # pragma: no cover
        audit.record("catalog_ai_failed", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return None, "ai_failed"


_CERTAINTY_RANK = {"hoch": 3, "mittel": 2, "niedrig": 1, "unbekannt": 0}


def _self_critique(client, model: str, systems: list[dict]) -> list[dict]:
    """2-Pass Self-Critique (QuantEvolve/FactorMAD-Stil): ein zweiter, GUENSTIGER Claude-Call
    (ohne Web-Suche) prueft jede generierte Strategie gegen eine Rubrik und sortiert/wertet ab.

    Rubrik je System: (1) klar bot-umsetzbar? (2) Bias-Verdacht (Look-Ahead/Survivorship/
    Data-Snooping)? (3) Overfit-Verdacht (viele Tunables + nur in-sample)? (4) Beleg-Methode
    benannt? → verdict 'keep'/'drop' + (nur senkbare) certainty + kurze Begruendung.

    **Fail-safe & Anti-Halluzination:** schlaegt der Call fehl oder ist unparsebar, bleiben die
    Systeme UNVERAENDERT (kein Daten-Downgrade). Certainty wird nur GESENKT, nie angehoben.
    """
    try:
        compact = [{
            "id": s.get("id"), "name": s.get("name"), "certainty": s.get("certainty"),
            "market_type": s.get("market_type"), "timeframe": s.get("timeframe"),
            "n_params": len(s.get("params", []) or []),
            "entry_rules": str(s.get("entry_rules", ""))[:240],
            "exit_rules": str(s.get("exit_rules", ""))[:240],
            "backtest_evidence": str(s.get("backtest_evidence", ""))[:240],
        } for s in systems]
        system = (
            "Du bist ein strenger, skeptischer Pruefer (Evaluator) fuer Krypto-Handelsstrategien. "
            "Du bewertest NUR die vorgelegten Systeme anhand der Rubrik — du erfindest nichts dazu."
        )
        prompt = (
            "Pruefe jede der folgenden, bereits recherchierten Strategien gegen diese Rubrik.\n"
            "WICHTIG: 'drop' ist die AUSNAHME — verwirf NUR, wenn eine Strategie wirklich UNBRAUCHBAR ist:\n"
            "  - NICHT vollstaendig/eindeutig bot-umsetzbar (es fehlen Entry- ODER Exit-Regeln ODER Kern-Parameter), ODER\n"
            "  - in sich widerspruechlich, ODER ein offensichtliches DUPLIKAT einer anderen Strategie der Liste.\n"
            "Fehlende/schwache Backtest-Belege, Bias-Verdacht (Look-Ahead/Survivorship/Data-Snooping) oder\n"
            "Overfit-Verdacht sind KEIN Drop-Grund — dafuer NUR die 'certainty' SENKEN (System bleibt 'keep').\n"
            "REGELN: certainty NUR senken, nie anheben. Die MEISTEN Systeme bleiben 'keep' (ggf. mit niedrigerer\n"
            "certainty); nur klar unbrauchbare 'drop'. Begruendung kurz (<=140 Zeichen).\n\n"
            "Eingabe (JSON):\n" + json.dumps(compact, ensure_ascii=False) + "\n\n"
            "Gib NUR ein JSON-Array zurueck (kein weiterer Text). Jedes Objekt: "
            "{id, verdict ('keep'|'drop'), certainty ('hoch'|'mittel'|'niedrig'|'unbekannt'), reason (string)}."
        )
        msg = client.messages.create(
            model=model, max_tokens=4000, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        text = text.replace("```json", "").replace("```", "")
        start = text.find("[")
        if start < 0:
            raise ValueError("kein JSON-Array im Critique-Ergebnis")
        verdicts, _ = json.JSONDecoder().raw_decode(text[start:])
        by_id = {v.get("id"): v for v in verdicts if isinstance(v, dict)}

        # Sicherheits-Cap: ein zu aggressiver Pass (Drop > 50 % der Systeme) wuerde den Katalog
        # kollabieren lassen -> dann Drops VERWERFEN und NUR die Certainty-Downgrades anwenden.
        drop_ids = {s.get("id") for s in systems
                    if str((by_id.get(s.get("id")) or {}).get("verdict", "keep")).lower() == "drop"}
        capped = len(drop_ids) > len(systems) // 2
        if capped:
            drop_ids = set()

        kept, dropped, downgraded = [], 0, 0
        for s in systems:
            v = by_id.get(s.get("id"))
            if s.get("id") in drop_ids:
                dropped += 1
                continue
            if v:
                cj = str(v.get("certainty", "")).lower()
                cur = str(s.get("certainty", "unbekannt")).lower()
                if cj in _CERTAINTY_RANK and _CERTAINTY_RANK[cj] < _CERTAINTY_RANK.get(cur, 0):
                    s["certainty"] = cj  # NUR senken
                    downgraded += 1
                s["critique"] = str(v.get("reason", ""))[:200]
            kept.append(s)  # ohne Urteil: unveraendert behalten (defensiv)

        # Kein Total-Wipe: liefert die Critique (faelschlich) NICHTS zurueck, Original behalten.
        if not kept:
            audit.record("catalog_critique_empty", original=len(systems))
            return systems
        audit.record("catalog_critique_ok", kept=len(kept), dropped=dropped,
                     downgraded=downgraded, capped=capped)
        return kept
    except Exception as exc:
        audit.record("catalog_critique_skipped", error=f"{type(exc).__name__}: {str(exc)[:140]}")
        return systems  # fail-safe: kein Daten-Downgrade


def activate_system(system_id: str, engine_template: str) -> dict:
    """Aktiviert eine Recherche-Strategie, indem ihr eine (geprüfte) Engine-Vorlage
    zugeordnet wird. Danach ist sie als Bot waehlbar (`runnable`). Bewusst KEIN
    Code-Generieren — die Ausfuehrung uebernimmt die zugeordnete Engine-Vorlage;
    die recherchierten Parameter sind „empfohlen" (Anzeige). Vor Echtgeld: Backtest.
    """
    doc = get_catalog()
    for s in doc["systems"]:
        if s["id"] == system_id:
            s["freqtrade_template"] = engine_template
            s["activated"] = True
            _save_catalog(doc["systems"], source=doc.get("source", "seed"))
            audit.record("strategy_activated", system_id=system_id, engine_template=engine_template)
            return {"ok": True, "system_id": system_id, "engine_template": engine_template}
    return {"ok": False, "error": f"System nicht gefunden: {system_id}"}


def set_validation(system_id: str, validated: bool, metrics: dict | None = None) -> dict:
    """Speichert das Ergebnis des Validierungs-Backtests am Katalog-System."""
    doc = get_catalog()
    for s in doc["systems"]:
        if s["id"] == system_id:
            s["validated"] = bool(validated)
            s["validation"] = {"ts": _now(), "metrics": metrics or {}}
            _save_catalog(doc["systems"], source=doc.get("source", "seed"))
            audit.record("strategy_validated", system_id=system_id, validated=bool(validated))
            return {"ok": True, "system_id": system_id, "validated": bool(validated)}
    return {"ok": False, "error": f"System nicht gefunden: {system_id}"}


def set_pin(system_id: str, pinned: bool) -> dict:
    doc = get_catalog()
    found = False
    for s in doc["systems"]:
        if s["id"] == system_id:
            s["pinned"] = pinned
            found = True
    if not found:
        return {"ok": False, "error": f"System nicht gefunden: {system_id}"}
    _save_catalog(doc["systems"], source=doc.get("source", "seed"))
    audit.record("catalog_pin", system_id=system_id, pinned=pinned)
    return {"ok": True, "system_id": system_id, "pinned": pinned}


# ---------------------------------------------------------------- Analyse
def analyze_performance(settings: Settings, bot_id: str) -> dict:
    """Leitet aus der Statistik-DB Verbesserungsvorschlaege ab (regelbasiert; KI optional)."""
    bot = get_bot(bot_id)
    if bot is None:
        return {"ok": False, "error": "Bot nicht gefunden"}
    latest = stats.get_latest(bot_id)
    if not latest:
        return {"ok": False, "error": "Keine Statistik vorhanden — erst Backtest laufen lassen."}

    s = []
    pf = latest.get("profit_factor")
    dd = latest.get("max_drawdown_pct") or 0.0
    wr = latest.get("winrate_pct") or 0.0
    sharpe = latest.get("sharpe") or 0.0
    prof = latest.get("profit_total_pct") or 0.0
    market = latest.get("market_change_pct")

    if pf is not None and pf < 1.0:
        s.append("Profit-Faktor < 1: Strategie/Exit ueberarbeiten oder Bot pausieren.")
    if dd >= bot.risk.max_drawdown_pct * 0.75:
        s.append(f"Drawdown {dd:.1f}% naehert sich Limit ({bot.risk.max_drawdown_pct:.0f}%): Positionsgroesse senken.")
    if wr < 40:
        s.append(f"Trefferquote {wr:.0f}% niedrig: Entry-Filter verschaerfen.")
    if sharpe < 0:
        s.append("Negatives Sharpe-Ratio: Risiko/Ertrag unguenstig — Parameter-Tuning noetig.")
    if market is not None and prof > market:
        s.append(f"Positiv: schlaegt den Markt ({prof:.1f}% vs {market:.1f}%).")
    if not s:
        s.append("Keine kritischen Auffaelligkeiten. Weiter im Paper-Modus beobachten.")

    return {"ok": True, "bot_id": bot_id, "based_on": latest, "suggestions": s,
            "ai_used": False,
            "note": "Regelbasiert. Mit ANTHROPIC_API_KEY zusaetzlich KI-Narrative moeglich."}


def chat(settings: Settings, message: str, context: str = "") -> dict:
    """Freier KI-Assistent fuer Fragen rund um die Bots/Strategien (key-aware)."""
    if not settings.anthropic_api_key:
        return {"ok": True, "ai_used": False,
                "reply": "KI-Chat braucht einen ANTHROPIC_API_KEY in der .env. "
                         "Tipp: Mit '/' am Anfang kannst du Befehle ausfuehren, z. B. '/bots' oder '/help'."}
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system = (
            "Du bist der Assistent eines privaten KRYPTO-Trading-Bot-Systems (Demo/Paper). "
            "Antworte kurz, klar und auf Deutsch. Du gibst Hilfestellung zu Strategien, "
            "Parametern und der Bedienung. Du kennst das Sonder-Thema BÖRSENERÖFFNUNGEN "
            "(Session-Opens Asia/London/US in UTC, Opening-Range-Breakout, Gap-and-Go, "
            "CME-Gap, Killzones, Monday-Asia-Open) und beziehst Session-Timing in Tipps ein. "
            "Keine Anlageberatung/keine Garantien."
        )
        msg = client.messages.create(
            model=settings.ai_model, max_tokens=700, system=system,
            messages=[{"role": "user", "content": f"{context}\n\nFrage des Nutzers: {message}"}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return {"ok": True, "ai_used": True, "reply": text.strip()}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "ai_used": False, "reply": f"Fehler beim KI-Aufruf: {type(exc).__name__}: {exc}"}
