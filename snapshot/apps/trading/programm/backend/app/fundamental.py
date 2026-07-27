"""fundamental.py — Oberkategorie „Fundamental": Wirtschaftskalender + Event-Risiko + Makro-Stance.

Vorausschauende Risiko-Schicht NEBEN der (rein preisbasierten) Regime-Erkennung: bekannte
**Wirtschafts-Großereignisse** (FOMC, CPI, NFP, Zinsentscheide) sind im Voraus terminiert. Best Practice
ist ein **Event-Risiko-Overlay** — vor/um High-Impact-Termine defensiver werden (Profi-Regel: „ein
bullishes Chartmuster wird von einem hawkischen FOMC invalidiert"). 0 Risiko, proposal-only.

Datenquelle **key-frei**: faireconomy-Wochen-JSON (Forex-Factory-Community), gecacht (Rate-Limit 2/5 min),
mit **Seed-Fallback** (regelbasierte wiederkehrende High-Impact-Events) → funktioniert auch offline.
Reines Python, dependency-leicht (stdlib urllib), testbar. Siehe docs/RESEARCH_FUNDAMENTAL_2026-06-08.md.
"""
from __future__ import annotations

import json
import statistics
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from . import mn_base

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CG_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"   # key-frei (rate-limited)
DAY_MS = 24 * 60 * 60 * 1000

FUND_DEFAULTS = {
    "pre_window_h": 12.0,        # Stunden VOR einem High-Impact-Event → „high" Risiko
    "post_window_h": 6.0,        # Stunden NACH einem Event → Risiko klingt ab
    "elevated_window_h": 36.0,   # weiteres Vorfeld → „elevated"
    "include_medium": 0,         # 1 = Medium-Impact mitzählen (sonst nur High)
    "cache_hours": 6.0,          # Kalender-Cache (schont das Rate-Limit der Quelle)
    "dampen": 0.5,               # Dämpfungsfaktor des gerichteten Sleeves bei „high" (0..1; F6)
}

# Ungefähre FOMC-Entscheidungstage 2026 (2. Sitzungstag, ~18–19 UTC ≈ 14:00 ET) — nur Seed-Fallback.
_FOMC_2026_UTC = [
    "2026-01-28T19:00:00+00:00", "2026-03-18T18:00:00+00:00", "2026-04-29T18:00:00+00:00",
    "2026-06-17T18:00:00+00:00", "2026-07-29T18:00:00+00:00", "2026-09-16T18:00:00+00:00",
    "2026-10-28T18:00:00+00:00", "2026-12-09T19:00:00+00:00",
]


def get_config() -> dict:
    return mn_base.config_get(FUND_DEFAULTS, "fundamental_config")


def set_config(patch: dict) -> dict:
    return mn_base.config_set(FUND_DEFAULTS, "fundamental_config", patch)


# ---------- Normalisierung ----------
def _to_utc_ms(iso: str) -> int | None:
    """ISO-Zeitstempel (mit Offset, z.B. '2026-06-07T05:15:00-04:00') → UTC-Epoch in ms."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)
    except Exception:
        return None


def parse_faireconomy(raw: list) -> list[dict]:
    """faireconomy-Rohliste → normalisierte, zeitlich sortierte Event-Liste (rein, testbar)."""
    out = []
    for e in raw or []:
        ts = _to_utc_ms(str(e.get("date") or ""))
        if ts is None:
            continue
        out.append({
            "title": str(e.get("title") or ""),
            "country": str(e.get("country") or "").upper(),
            "impact": str(e.get("impact") or "").capitalize(),   # High/Medium/Low/Holiday
            "ts": ts,
            "forecast": str(e.get("forecast") or ""),
            "previous": str(e.get("previous") or ""),
            "actual": str(e.get("actual") or ""),               # nach Release gefüllt (echter Wert)
        })
    out.sort(key=lambda x: x["ts"])
    return out


def is_high_impact(ev: dict, include_medium: bool = False) -> bool:
    """High-Impact-Filter; Medium optional. Holiday/Low zählen nie als Risiko-Event."""
    imp = (ev.get("impact") or "").capitalize()
    return imp == "High" or (include_medium and imp == "Medium")


# ---------- Seed-Fallback (regelbasiert, offline) ----------
def _first_friday(year: int, month: int) -> datetime:
    d = datetime(year, month, 1, 12, 30, tzinfo=timezone.utc)   # NFP ~12:30 UTC (08:30 ET)
    return d + timedelta(days=(4 - d.weekday()) % 7)            # Freitag = weekday 4


def _seed_events(now_ms: int, horizon_days: int = 45) -> list[dict]:
    """Regelbasierte wiederkehrende High-Impact-Events (USD) als Offline-Fallback: NFP (1. Freitag),
    CPI (~12. des Monats), FOMC (hardcodierte 2026-Termine). Bewusst APPROXIMATIV — nur Fallback."""
    now = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    end = now + timedelta(days=horizon_days)
    evs: list[dict] = []
    for iso in _FOMC_2026_UTC:
        ts = _to_utc_ms(iso)
        if ts is not None:
            evs.append({"title": "FOMC Statement & Rate Decision", "country": "USD",
                        "impact": "High", "ts": ts, "forecast": "", "previous": "", "approx": True})
    # NFP + CPI für den aktuellen und nächsten Monat
    for delta in (0, 1, 2):
        y, m = now.year + (now.month - 1 + delta) // 12, (now.month - 1 + delta) % 12 + 1
        nfp = _first_friday(y, m)
        evs.append({"title": "Non-Farm Employment Change (NFP)", "country": "USD", "impact": "High",
                    "ts": int(nfp.timestamp() * 1000), "forecast": "", "previous": "", "approx": True})
        cpi = datetime(y, m, 12, 12, 30, tzinfo=timezone.utc)
        evs.append({"title": "CPI (approx.)", "country": "USD", "impact": "High",
                    "ts": int(cpi.timestamp() * 1000), "forecast": "", "previous": "", "approx": True})
    evs = [e for e in evs if now_ms <= e["ts"] <= int(end.timestamp() * 1000)]
    evs.sort(key=lambda x: x["ts"])
    return evs


# ---------- Ingestion (live, gecacht, defensiv) ----------
def fetch_calendar(force: bool = False) -> tuple[list[dict], str]:
    """Wirtschaftskalender holen → (Events, Quelle). Reihenfolge: frischer Cache → live → alter Cache →
    Seed. Key-frei; bei Netzfehler nie ein Fehler nach außen (defensiv)."""
    cfg = get_config()
    now_ms = int(time.time() * 1000)
    raw = mn_base.meta_get("fundamental_calendar")
    ts = mn_base.meta_get("fundamental_calendar_ts")
    age_h = ((now_ms - float(ts)) / 3.6e6) if ts else 1e9
    if raw and not force and age_h < float(cfg["cache_hours"]):
        try:
            return parse_faireconomy(json.loads(raw)), "cache"
        except Exception:
            pass
    try:
        req = urllib.request.Request(FEED_URL, headers={"User-Agent": "trading-bot-eins/research (read-only)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read().decode("utf-8")
        events = parse_faireconomy(json.loads(data))
        if events:
            mn_base.meta_set("fundamental_calendar", data)
            mn_base.meta_set("fundamental_calendar_ts", str(now_ms))
            return events, "live"
    except Exception:
        pass
    if raw:   # Netz fehlgeschlagen → alter Cache besser als nichts
        try:
            return parse_faireconomy(json.loads(raw)), "cache-stale"
        except Exception:
            pass
    return _seed_events(now_ms), "seed"


# ---------- Event-Risiko (vorausschauend) ----------
def event_risk(now_ms: int | None = None, events: list[dict] | None = None,
               cfg: dict | None = None) -> dict:
    """Vorausschauendes Event-Risiko aus dem Kalender. Stufen:
    **high** = innerhalb [Event − pre_window, Event + post_window] eines High-Impact-Events,
    **elevated** = nächstes High-Impact-Event liegt innerhalb elevated_window voraus, sonst **none**.
    Liefert nächstes Event + Stunden bis dahin + die nächsten High-Impact-Termine. Defensiv (kein Netz
    nötig, wenn ``events`` übergeben wird)."""
    cfg = cfg or get_config()
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    if events is None:
        events, source = fetch_calendar()
    else:
        source = "given"
    inc_med = bool(int(cfg["include_medium"]))
    hi = [e for e in events if is_high_impact(e, inc_med)]
    pre = float(cfg["pre_window_h"]) * 3.6e6
    post = float(cfg["post_window_h"]) * 3.6e6
    elev = float(cfg["elevated_window_h"]) * 3.6e6

    level, active = "none", None
    for e in hi:
        d = e["ts"] - now_ms            # >0: Event liegt voraus, <0: Event ist vorbei
        if -post <= d <= pre:
            level, active = "high", e
            break
    upcoming = [e for e in hi if e["ts"] >= now_ms]
    nxt = upcoming[0] if upcoming else None
    if level != "high" and nxt is not None and (nxt["ts"] - now_ms) <= elev:
        level, active = "elevated", nxt

    # Event-typ- + proximitäts-gewichtete Dämpfung (stetig): FOMC > CPI > NFP > generisch; näher = stärker.
    dscale = dir_scale(level, cfg)
    if level != "none" and active is not None:
        floor = max(0.0, min(1.0, float(cfg["dampen"])))   # dir_scale-Boden bei voller Dämpfung
        d = active["ts"] - now_ms
        if level == "high":
            window = pre if d >= 0 else post
            prox = (1.0 - min(1.0, abs(d) / window)) if window > 0 else 1.0
        else:                                              # elevated: nur schwaches Vorfeld-Tilt
            span = elev - pre
            prox = 0.4 * (1.0 - min(1.0, max(0.0, d - pre) / span)) if span > 0 else 0.2
        reduction = (1.0 - floor) * _event_weight(active.get("title")) * prox
        dscale = round(1.0 - reduction, 4)

    def _slim(e):
        return {"title": e["title"], "country": e["country"], "impact": e["impact"], "ts": e["ts"],
                "hours_until": round((e["ts"] - now_ms) / 3.6e6, 1), "approx": e.get("approx", False)}

    return {
        "event_risk": level, "source": source,
        "next_event": _slim(nxt) if nxt else None,
        "active_event": ({"title": active["title"], "ts": active["ts"],
                          "weight": _event_weight(active.get("title"))} if active else None),
        "high_impact_upcoming": [_slim(e) for e in upcoming[:6]],
        "dir_scale": dscale,
        "windows_h": {"pre": pre / 3.6e6, "post": post / 3.6e6, "elevated": elev / 3.6e6},
    }


def _event_weight(title: str | None) -> float:
    """Relatives Impact-Gewicht nach Event-Typ (Empirie: FOMC > CPI > NFP > generisch)."""
    t = (title or "").lower()
    if "fomc" in t or "rate decision" in t or "interest rate" in t or "rate statement" in t:
        return 1.0
    if "cpi" in t or "inflation" in t or "ppi" in t:
        return 0.85
    if "non-farm" in t or "nfp" in t or "payroll" in t or "employment" in t:
        return 0.7
    return 0.5


def dir_scale(level: str, cfg: dict | None = None) -> float:
    """Skalierungsfaktor für das GERICHTETE Sleeve nach Event-Risiko (1.0 = voll, <1 = gedämpft).
    high → ``dampen``; elevated → halbe Dämpfung; none → 1.0. Defensiv: senkt nur Risiko."""
    cfg = cfg or get_config()
    d = max(0.0, min(1.0, float(cfg["dampen"])))
    if level == "high":
        return round(d, 4)
    if level == "elevated":
        return round(1.0 - (1.0 - d) * 0.5, 4)
    return 1.0


# ---------- Makro-Überraschung (echte Werte: actual vs forecast, key-frei aus dem Kalender) ----------
def _parse_num(s: str) -> float | None:
    """'3.2%','150K','-0.3','1.2M' → float; None wenn nicht numerisch."""
    if not s:
        return None
    t = str(s).strip().replace("%", "").replace(",", "")
    mult = 1.0
    if t and t[-1] in "KkMmBb":
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[t[-1].lower()]
        t = t[:-1]
    try:
        return float(t) * mult
    except Exception:
        return None


def _surprise_direction(title: str, actual: float, forecast: float) -> str:
    """Übersetzt eine Daten-Überraschung in einen Markt-Tilt. Inflation/Jobs heißer als erwartet =
    hawkish (risk_off), Arbeitslosenquote höher = dovish (risk_on). Sonst neutral."""
    t = (title or "").lower()
    hotter = actual > forecast
    if "unemployment" in t:                                   # höhere Arbeitslosigkeit = dovish
        return "dovish" if hotter else "hawkish"
    if any(w in t for w in ("cpi", "inflation", "ppi", "payroll", "non-farm", "nfp", "employment change")):
        return "hawkish" if hotter else "dovish"             # heißer = hawkish (Zinsdruck)
    return "neutral"


def macro_surprise(events: list[dict] | None = None, now_ms: int | None = None,
                   lookback_h: float = 24.0) -> dict | None:
    """Jüngste High-Impact-Daten-Überraschung (actual vs forecast) der letzten ``lookback_h`` Stunden —
    echte Makro-Werte aus dem Kalender (key-frei). None, wenn nichts Belegbares vorliegt."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    if events is None:
        events, _src = fetch_calendar()
    win_start = now_ms - lookback_h * 3.6e6
    cand = None
    for e in events:
        if not is_high_impact(e):
            continue
        if not (win_start <= e["ts"] <= now_ms):
            continue
        a, f = _parse_num(e.get("actual", "")), _parse_num(e.get("forecast", ""))
        if a is None or f is None:
            continue
        if cand is None or e["ts"] > cand["ts"]:
            cand = {"title": e["title"], "ts": e["ts"], "actual": a, "forecast": f}
    if cand is None:
        return None
    cand["surprise"] = round(cand["actual"] - cand["forecast"], 4)
    cand["direction"] = _surprise_direction(cand["title"], cand["actual"], cand["forecast"])
    cand["hours_ago"] = round((now_ms - cand["ts"]) / 3.6e6, 1)
    return cand


# ---------- Krypto-Fundamentals (CoinGecko, key-frei) ----------
def _parse_global(data: dict) -> dict:
    """CoinGecko-/global-Daten → schlanke Krypto-Markt-Fundamentals (rein, testbar)."""
    g = (data or {}).get("data") or data or {}
    dom = float((g.get("market_cap_percentage") or {}).get("btc") or 0.0)
    total = float((g.get("total_market_cap") or {}).get("usd") or 0.0)
    chg = float(g.get("market_cap_change_percentage_24h_usd") or 0.0)
    return {"btc_dominance": round(dom, 2), "total_mcap_usd": total,
            "mcap_change_24h_pct": round(chg, 2)}


def _crypto_risk(cf: dict) -> str:
    """Leichtgewichtiges Krypto-Risk-Proxy aus dem 24h-Marktkapital-Trend (key-frei, dokumentiert
    approximativ): stark negativ → risk_off, klar positiv → risk_on, sonst neutral."""
    if not cf.get("ok"):
        return "unknown"
    chg = cf.get("mcap_change_24h_pct") or 0.0
    if chg <= -2.0:
        return "risk_off"
    if chg >= 1.5:
        return "risk_on"
    return "neutral"


def crypto_fundamentals(force: bool = False) -> dict:
    """Krypto-Markt-Fundamentals via CoinGecko /global (key-frei, gecacht, defensiv). Liefert
    BTC-Dominanz, Total-MarketCap, 24h-Änderung + (über gecachte Vorwerte) Dominanz-Trend."""
    cfg = get_config()
    now = int(time.time() * 1000)
    raw = mn_base.meta_get("fundamental_cg")
    ts = mn_base.meta_get("fundamental_cg_ts")
    age_h = ((now - float(ts)) / 3.6e6) if ts else 1e9
    source = "cache"
    if not (raw and not force and age_h < float(cfg["cache_hours"])):
        try:
            req = urllib.request.Request(CG_GLOBAL_URL, headers={"User-Agent": "trading-bot-eins/research (read-only)"})
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read().decode("utf-8")
            json.loads(body)   # validieren
            mn_base.meta_set("fundamental_cg", body)
            mn_base.meta_set("fundamental_cg_ts", str(now))
            raw, source = body, "live"
        except Exception:
            source = "cache-stale" if raw else "none"
    if not raw:
        return {"ok": False, "source": "none"}
    try:
        cf = _parse_global(json.loads(raw))
    except Exception:
        return {"ok": False, "source": source}
    prev = mn_base.meta_get("fundamental_dom_prev")
    cf["dominance_change"] = round(cf["btc_dominance"] - float(prev), 3) if prev else None
    if source == "live":
        mn_base.meta_set("fundamental_dom_prev", str(cf["btc_dominance"]))
    cf.update({"ok": True, "source": source})
    return cf


# ---------- Echte On-Chain-Tiefe (blockchain.com Charts, key-frei) ----------
def _bc_chart(name: str) -> list[float] | None:
    """Holt eine blockchain.com-Chart-Zeitreihe (30 Tage) → Liste der y-Werte (jüngster zuletzt)."""
    try:
        url = f"https://api.blockchain.info/charts/{name}?timespan=30days&format=json&cors=true"
        req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-eins/research (read-only)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        vals = [float(p["y"]) for p in (data.get("values") or []) if p.get("y") is not None]
        return vals or None
    except Exception:
        return None


def _onchain_signal(addr_trend_pct: float | None, nvt: float | None) -> str:
    """On-Chain-Bewertung (heuristisch): hohe NVT = überbewertet (stretched), fallende Adoption =
    stretched, steigende Adoption + moderate NVT = healthy, sonst neutral."""
    if nvt is not None and nvt > 120:
        return "stretched"
    if addr_trend_pct is not None and addr_trend_pct <= -10:
        return "stretched"
    if addr_trend_pct is not None and addr_trend_pct >= 5 and (nvt is None or nvt < 90):
        return "healthy"
    return "neutral"


def onchain(force: bool = False) -> dict:
    """Echte BTC-On-Chain-Metriken (key-frei, gecacht): Active Addresses + 30T-Trend, NVT
    (MarketCap/Tx-Volumen), Hash-Rate. Defensiv (Netzfehler → alter Cache/none)."""
    cfg = get_config()
    now = int(time.time() * 1000)
    raw = mn_base.meta_get("fundamental_oc")
    ts = mn_base.meta_get("fundamental_oc_ts")
    age_h = ((now - float(ts)) / 3.6e6) if ts else 1e9
    if raw and not force and age_h < float(cfg["cache_hours"]):
        try:
            return json.loads(raw)
        except Exception:
            pass
    try:
        aa = _bc_chart("n-unique-addresses")
        vol = _bc_chart("estimated-transaction-volume-usd")
        mc = _bc_chart("market-cap")
        hr = _bc_chart("hash-rate")
        if not aa:
            raise ValueError("keine On-Chain-Daten")
        trend = round((aa[-1] / aa[0] - 1.0) * 100, 2) if aa[0] else None
        nvt = round(mc[-1] / vol[-1], 1) if (mc and vol and vol[-1] > 0) else None
        res = {"ok": True, "active_addresses": int(aa[-1]), "addr_trend_30d_pct": trend, "nvt": nvt,
               "hash_rate": round(hr[-1], 1) if hr else None,
               "signal": _onchain_signal(trend, nvt), "source": "live"}
        mn_base.meta_set("fundamental_oc", json.dumps(res))
        mn_base.meta_set("fundamental_oc_ts", str(now))
        return res
    except Exception:
        if raw:
            try:
                r = json.loads(raw)
                r["source"] = "cache-stale"
                return r
            except Exception:
                pass
        return {"ok": False, "source": "none", "signal": "neutral"}


# ---------- Forward-Volatilität (Deribit DVOL, key-frei) ----------
DVOL_URL = ("https://www.deribit.com/api/v2/public/get_volatility_index_data"
            "?currency=BTC&resolution=3600&start_timestamp={a}&end_timestamp={b}")


def _iv_signal(cur: float | None, base: float | None) -> str:
    """Forward-IV-Bewertung relativ zur eigenen Baseline: deutlich erhöht = elevated (Markt preist
    Turbulenz ein → defensiv), deutlich niedriger = calm, sonst normal."""
    if not cur or not base or base <= 0:
        return "normal"
    ratio = cur / base
    if ratio >= 1.25:
        return "elevated"
    if ratio <= 0.8:
        return "calm"
    return "normal"


def _dvol_from_rows(rows: list) -> tuple[float, float] | None:
    """DVOL-OHLC-Rohzeilen ([ts,o,h,l,c]) → (aktueller DVOL, Baseline=Median). None bei leer (rein/testbar)."""
    closes = [float(r[4]) for r in (rows or []) if r and len(r) >= 5 and r[4] is not None]
    if not closes:
        return None
    return round(closes[-1], 2), round(statistics.median(closes), 2)


def forward_vol(force: bool = False) -> dict:
    """Vorausschauende (implizite) Volatilität via Deribit **DVOL-Index** (30-Tage-Forward-IV, key-frei,
    gecacht, defensiv). Liefert aktuellen DVOL, Baseline (Median der letzten ~30 T) + IV-Signal."""
    cfg = get_config()
    now = int(time.time() * 1000)
    raw = mn_base.meta_get("fundamental_dvol")
    ts = mn_base.meta_get("fundamental_dvol_ts")
    age_h = ((now - float(ts)) / 3.6e6) if ts else 1e9
    if raw and not force and age_h < float(cfg["cache_hours"]):
        try:
            return json.loads(raw)
        except Exception:
            pass
    try:
        url = DVOL_URL.format(a=now - 30 * DAY_MS, b=now)
        req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-eins/research (read-only)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows = (data.get("result") or {}).get("data") or []
        parsed = _dvol_from_rows(rows)
        if not parsed:
            raise ValueError("keine DVOL-Daten")
        cur, base = parsed
        res = {"ok": True, "dvol": cur, "dvol_baseline": base,
               "signal": _iv_signal(cur, base), "source": "live"}
        mn_base.meta_set("fundamental_dvol", json.dumps(res))
        mn_base.meta_set("fundamental_dvol_ts", str(now))
        return res
    except Exception:
        if raw:
            try:
                r = json.loads(raw)
                r["source"] = "cache-stale"
                return r
            except Exception:
                pass
        return {"ok": False, "source": "none", "signal": "normal"}


# ---------- Echte Makro-Werte via FRED (St. Louis Fed, API-Key) ----------
FRED_URL = ("https://api.stlouisfed.org/fred/series/observations?series_id={sid}"
            "&api_key={key}&file_type=json&sort_order=desc&limit={n}")


def fred_series(series_id: str, n: int, key: str) -> list[float] | None:
    """Jüngste FRED-Beobachtungen einer Serie (neueste zuerst), Fehlwerte '.' übersprungen. None bei Fehler."""
    try:
        url = FRED_URL.format(sid=series_id, key=key, n=n)
        req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-eins/research (read-only)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        vals = [float(o["value"]) for o in (data.get("observations") or [])
                if o.get("value") not in (".", "", None)]
        return vals or None
    except Exception:
        return None


def _fred_regime(nfci: float | None, nfci_trend: float | None, ff_trend: float | None) -> str:
    """Echtes Makro-Regime aus Financial-Conditions (NFCI) + Fed-Funds-Trend: straffend (risk_off-Tendenz),
    lockernd (risk_on-Tendenz), sonst neutral. NFCI>0 = straffer als Schnitt."""
    if nfci is None:
        return "unbekannt"
    if nfci > 0.0 or (nfci_trend or 0) > 0.02 or (ff_trend or 0) > 0.05:
        return "tightening"
    if nfci < -0.1 and (nfci_trend or 0) <= 0 and (ff_trend or 0) <= 0:
        return "easing"
    return "neutral"


def macro_real(force: bool = False) -> dict:
    """ECHTE Makro-Werte von FRED (NFCI = Financial Conditions, FEDFUNDS = Leitzins) → Makro-Regime.
    Nur mit gesetztem FRED-Key; sonst {available: False} (Proxy bleibt aktiv). Gecacht, defensiv."""
    from .config import get_settings
    key = (get_settings().fred_api_key or "").strip()
    if not key:
        return {"ok": False, "available": False, "regime": "unbekannt"}
    cfg = get_config()
    now = int(time.time() * 1000)
    raw = mn_base.meta_get("fundamental_fred")
    ts = mn_base.meta_get("fundamental_fred_ts")
    age_h = ((now - float(ts)) / 3.6e6) if ts else 1e9
    if raw and not force and age_h < float(cfg["cache_hours"]):
        try:
            return json.loads(raw)
        except Exception:
            pass
    try:
        nfci = fred_series("NFCI", 8, key)           # wöchentlich
        ff = fred_series("FEDFUNDS", 6, key)          # monatlich
        if not nfci:
            raise ValueError("keine FRED-Daten (NFCI)")
        nfci_now = round(nfci[0], 3)
        nfci_trend = round(nfci[0] - nfci[min(4, len(nfci) - 1)], 3)
        ff_now = round(ff[0], 2) if ff else None
        ff_trend = round(ff[0] - ff[min(3, len(ff) - 1)], 2) if (ff and len(ff) > 1) else 0.0
        res = {"ok": True, "available": True, "nfci": nfci_now, "nfci_trend": nfci_trend,
               "fed_funds": ff_now, "ff_trend": ff_trend,
               "regime": _fred_regime(nfci_now, nfci_trend, ff_trend), "source": "live"}
        mn_base.meta_set("fundamental_fred", json.dumps(res))
        mn_base.meta_set("fundamental_fred_ts", str(now))
        return res
    except Exception:
        if raw:
            try:
                r = json.loads(raw)
                r["source"] = "cache-stale"
                return r
            except Exception:
                pass
        return {"ok": False, "available": False, "regime": "unbekannt", "source": "error"}


# ---------- Makro-Stance (kombiniert Event-Druck + Krypto-Risk + On-Chain + Forward-Vola + FRED) ----------
def macro_stance(now_ms: int | None = None, er: dict | None = None, cf: dict | None = None,
                 sup: dict | None = None, oc: dict | None = None, fv: dict | None = None,
                 mr: dict | None = None) -> dict:
    """Kombiniert Event-Risiko + Krypto-Risk + **echte Daten-Überraschung** + **On-Chain** + **Forward-IV
    (DVOL)** + **echtes FRED-Makro-Regime** (Financial Conditions/Leitzins) zu einer groben Markt-Stance.
    Straffende Finanzbedingungen / hawkish / On-Chain-stretched / erhöhte IV lehnen risk_off, lockernde
    Bedingungen stützen risk_on. ``er``/``cf``/``sup``/``oc``/``fv``/``mr`` injizierbar (Tests/ohne Netz)."""
    injected = er is not None
    er = er if er is not None else event_risk(now_ms)
    cf = cf if cf is not None else crypto_fundamentals()
    if sup is None and not injected:                          # nur im Live-Pfad nachladen (hermetisch)
        sup = macro_surprise(now_ms=now_ms)
    if oc is None and not injected:
        oc = onchain()
    if fv is None and not injected:
        fv = forward_vol()
    if mr is None and not injected:
        mr = macro_real()
    hawkish = bool(sup and sup.get("direction") == "hawkish")
    oc_sig = (oc or {}).get("signal", "neutral")
    iv_sig = (fv or {}).get("signal", "normal")
    mr_regime = (mr or {}).get("regime", "unbekannt")
    mr_tight = mr_regime == "tightening"
    mr_easing = mr_regime == "easing"
    crisk = _crypto_risk(cf)
    pressure = len([e for e in er.get("high_impact_upcoming", []) if (e.get("hours_until") or 1e9) <= 48])
    if (crisk == "risk_off" or er.get("event_risk") == "high" or hawkish
            or oc_sig == "stretched" or iv_sig == "elevated" or mr_tight):
        stance = "risk_off"
    elif (crisk == "risk_on" and er.get("event_risk") == "none" and pressure == 0
          and not hawkish and oc_sig != "stretched" and iv_sig != "elevated" and not mr_tight):
        stance = "risk_on"
    elif mr_easing and crisk != "risk_off" and not hawkish and oc_sig != "stretched" and iv_sig != "elevated":
        stance = "risk_on"                                    # echte Lockerung stützt risk_on
    else:
        stance = "neutral"
    return {"stance": stance, "crypto_risk": crisk, "event_pressure_48h": pressure,
            "surprise": (sup.get("direction") if sup else None), "onchain_signal": oc_sig,
            "iv_signal": iv_sig, "dvol": (fv or {}).get("dvol"),
            "macro_regime": mr_regime, "nfci": (mr or {}).get("nfci"),
            "btc_dominance": cf.get("btc_dominance"), "mcap_change_24h_pct": cf.get("mcap_change_24h_pct"),
            "dominance_change": cf.get("dominance_change"),
            "source": {"calendar": er.get("source"), "coingecko": cf.get("source"),
                       "onchain": (oc or {}).get("source"), "dvol": (fv or {}).get("source"),
                       "fred": (mr or {}).get("source")}}


def report(now_ms: int | None = None) -> dict:
    """Komplettes Fundamental-Bild für Endpoint/Frontend: Event-Risiko + Makro-Stance + Krypto-
    Fundamentals + Kalender + Config."""
    er = event_risk(now_ms)
    cf = crypto_fundamentals()
    sup = macro_surprise(now_ms=now_ms)
    oc = onchain()
    fv = forward_vol()
    mr = macro_real()
    er["macro_stance"] = macro_stance(now_ms, er=er, cf=cf, sup=sup, oc=oc, fv=fv, mr=mr)
    er["macro_surprise"] = sup
    er["crypto_fundamentals"] = cf
    er["onchain"] = oc
    er["forward_vol"] = fv
    er["macro_real"] = mr
    er["config"] = get_config()
    er["explainer"] = (
        "Wirtschaftskalender als VORAUSSCHAUENDER Risiko-Filter: vor/um High-Impact-Termine (FOMC/CPI/NFP) "
        "dämpft das Ensemble das gerichtete Sleeve (lehnt stärker auf den markt-neutralen Sockel). "
        "Makro-Stance + Krypto-Risk (BTC-Dominanz/MarketCap) als zusätzlicher Tilt. Key-freie Quellen "
        "(faireconomy + CoinGecko) mit Seed-Fallback — proposal-only, 0 Risiko, keine Orders."
    )
    return er
