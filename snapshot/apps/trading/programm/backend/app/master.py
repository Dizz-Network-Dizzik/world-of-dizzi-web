"""master.py — selbst-verfeinernder Master-Algorithmus (U7, erste Iteration).

Verdichtet die **validierten** Erkenntnisse ALLER Strategien zu einer eigenen, **versionierten**
Regime→Strategie/Parameter-Allokationspolitik, **bewertet sich selbst** (Fitness aus den bekannten
OOS-Kennzahlen der gewählten Allokationen) und behält nur die **bessere** Version (Fitness-Verlauf).
So verfeinert er „seinen eigenen Algorithmus", während die Evidenzbasis (Validierungen/Gewinner) wächst.

Ehrlich: solange keine Strategie PF>1 hat, weist der Master das als „keine profitable Allokation" aus
und bleibt defensiv. Er handelt NICHT selbst — Anwendung/Echtgeld bleibt ausdrückliche Freigabe.
Ein selbst-trainierender RL-Agent über Live-Märkte ist der spätere große Ausbau (Blueprint §6).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import math

from . import cache, csm, fundamental, marketmaking, mn_base, pairs, stats
from .meta import STRAT_REGIME

REGIMES = ["trend_up", "trend_down", "range"]
_REG_MAP = {"trend_up": "trend", "trend_down": "trend", "range": "range"}

# Markt-neutrale Edge-Quellen (regime-UNabhängiger, OOS-getunter Sockel): (Anzeigename, status-fn).
MN_ENGINES: list[tuple[str, object]] = [
    ("csm", csm.status), ("pairs", pairs.status),
    ("statarb", pairs.statarb_status), ("marketmaking", marketmaking.status),
]

# Rein SYNTHETISCHE Microstruktur-Engines: Market-Making läuft auf einem stochastischen Monte-Carlo-
# Mid-Preispfad mit un-kalibrierten Fill-/Adverse-Selection-Params, OHNE Slippage/Latenz/Queue-Position/
# Teil-Fills. Ihr simulierter Edge ist NICHT gegen echte Microstruktur validierbar ⇒ struktureller
# Discount (`sim_discount`). CSM/Pairs/StatArb backtesten auf ECHTEN Kursen und sind NICHT betroffen.
SIM_ENGINES = {"marketmaking"}

# Tunbarer Meta-Learner (Sockel-Gewichtung + OOS-Härtung). Persistiert via mn_base (Schritt-1-Helfer).
SH_TO_PF = 3.0   # Default-Sharpe→Pseudo-PF-Skala (Sharpe 3 ≈ PF 2, Sharpe 6 ≈ PF 3)
MASTER_DEFAULTS = {
    "sharpe_to_pf": SH_TO_PF,   # Sharpe→Pseudo-PF-Skala (gemeinsame Währung mit gerichteten PFs)
    "sharpe_haircut": 0.5,      # OOS-Härtung: flacher Abzug je annualisierter Sharpe (Schätzfehler/Deflation)
    "conf_shrink": 1.0,         # OOS-Härtung: Score ∝ Sharpe·Konfidenz^conf_shrink (0=Konfidenz egal, 1=voll)
    "max_weight": 0.6,          # Diversifikation: Kappung des Einzelgewichts im Sockel (Überschuss umverteilt)
    "weight_temp": 0.0,         # Soft-Voting: 0=lineare Gewichte, >0=Softmax-Temperatur (kleiner=schärfer)
    "deflate_factor": 0.4,      # Deflated-Sharpe (Multiple-Testing): extra Haircut ∝ √(2·ln N_engines).
                                # Default AKTIV (0.4): die Engine-Sharpes entstehen teils auf Daten,
                                # auf denen auch ihre Parameter getunt wurden — ohne Deflation wäre
                                # die Sockel-Gewichtung systematisch zu optimistisch. 0=aus.
    "meta_temp": 0.0,           # Meta-Split dir↔Sockel: 0=linear edge-proportional, >0=Softmax (Soft-Voting)
    "meta_floor": 0.0,          # Mindest-Anteil je Sleeve, wenn BEIDE Edge>0 (Meta-Diversifikation; 0=aus)
    "psr_weight": 1.0,          # PSR-Härtung: 0=aus … 1=volle Gewichtung mit Probabilistic-Sharpe-Faktor
    "sim_discount": 1.0,        # Struktureller Simulations-Discount für SYNTHETISCHE Microstruktur-Engines
                                # (SIM_ENGINES, derzeit nur Market-Making): deren simulierte Sharpe zählt nur
                                # zu diesem Faktor (1.0=aus/voll · 0.5=halb · <~0.15 ⇒ MM fällt unter die
                                # Härtungs-Schwelle und trägt 0). Ehrlichkeit: ein Monte-Carlo-MM-Edge ohne
                                # reale Microstruktur ist NICHT 1:1 mit real-data-Edges vergleichbar.
    "vol_target_pct": 0.0,      # Vol-Targeting (Ziel-1h-Return-Stdev %): >0 aktiv → Gesamt-Exposure-Skalierer; 0=aus
}


def _meta_split(dir_edge: float, mn_edge: float, sleeve_active: bool, cfg: dict) -> float:
    """Dynamischer Meta-Gewicht-Split (Stacking) → Anteil des markt-neutralen Sockels (mn_share).
    Linear edge-proportional (Default) oder Softmax (``meta_temp``); ``meta_floor`` sichert beiden
    Sleeves mit positiver Edge einen Mindestanteil (Diversifikation gegen 0/100-Extreme)."""
    temp = float(cfg.get("meta_temp", 0.0))
    floor = float(cfg.get("meta_floor", 0.0))
    if dir_edge <= 0 and mn_edge <= 0:
        return 1.0 if sleeve_active else 0.0
    if temp > 0:
        mx = max(dir_edge, mn_edge)
        wd = math.exp((dir_edge - mx) / temp)
        wm = math.exp((mn_edge - mx) / temp)
        share = wm / (wd + wm)
    elif dir_edge <= 0:
        share = 1.0          # nur der markt-neutrale Sockel hat Edge → voll auf den Sockel
    elif mn_edge <= 0:
        share = 0.0          # nur das gerichtete Sleeve hat Edge → kein Sockel
    else:
        share = mn_edge / (dir_edge + mn_edge)   # beide positiv: edge-proportional (Summe>0, 0<share<1)
    if floor > 0 and dir_edge > 0 and mn_edge > 0:
        share = min(1.0 - floor, max(floor, share))
    return round(max(0.0, min(1.0, share)), 4)   # Sicherheitsnetz: Anteil immer in [0,1]


def get_config() -> dict:
    return mn_base.config_get(MASTER_DEFAULTS, "master_config")


def set_config(patch: dict) -> dict:
    return mn_base.config_set(MASTER_DEFAULTS, "master_config", patch)


def _ensure(conn) -> None:
    conn.executescript(
        """CREATE TABLE IF NOT EXISTS master_policy(
            version INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, fitness REAL,
            parent_version INTEGER, policy TEXT, note TEXT);"""
    )


# Konfidenz-Dämpfung für Strategien, die ihr Walk-Forward-Validierungs-Gate NICHT bestanden haben.
UNVALIDATED_CONF_PENALTY = 0.25


def _confidence(val: dict | None) -> float:
    """Vertrauen in eine Strategie-Erkenntnis: mehr OOS-Fenster + höherer PF → höher.

    **Ehrlichkeit:** Hat die Strategie ihr Validierungs-Gate explizit NICHT bestanden
    (``validated`` = False, z. B. nur 1/3 Walk-Forward-Fenster), wird die Konfidenz stark
    gedämpft (``UNVALIDATED_CONF_PENALTY``). Sonst würde ein knapp-über-1-Aggregat-PF aus
    wenigen zufällig bestandenen Fenstern die gerichtete Politik tragen, obwohl der Edge
    out-of-sample nicht hielt. Fehlt das Flag (reiner Optimierungs-Record), bleibt es neutral."""
    if not val:
        return 0.0
    w = int(val.get("windows") or 1)
    pf = val.get("profit_factor")
    base = 0.2 + 0.2 * min(2, max(0, w - 1))
    if pf is not None:
        base += 0.1 * min(3.0, float(pf))
    conf = min(1.0, base)
    if val.get("validated") is not None and not val.get("validated"):
        conf *= UNVALIDATED_CONF_PENALTY
    return round(conf, 3)


def _sharpe_pf(sharpe: float | None, scale: float = SH_TO_PF) -> float:
    """Annualisierte Sharpe → Pseudo-Profit-Factor (≥1), gemeinsame Währung mit den gerichteten PFs."""
    return 1.0 + max(0.0, float(sharpe or 0.0)) / (scale if scale else SH_TO_PF)


def _haircut_sharpe(sharpe: float | None, haircut: float) -> float:
    """OOS-gehärtete Sharpe: flacher Abzug für Schätzfehler (Deflation), bei 0 gekappt."""
    return max(0.0, float(sharpe or 0.0) - max(0.0, haircut))


def _cap_weights(weights: dict, cap: float) -> dict:
    """Kappt Einzelgewichte auf ``cap`` und verteilt den Überschuss iterativ auf die ungekappten
    (Diversifikation gegen Einzel-Engine-Dominanz). Lässt die Summe < 1, falls cap·N < 1."""
    if cap >= 1.0 or not weights:
        return weights
    w = dict(weights)
    for _ in range(20):
        over = {k: v for k, v in w.items() if v > cap + 1e-9}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        for k in over:
            w[k] = cap
        free = {k: v for k, v in w.items() if v < cap - 1e-9}
        fsum = sum(free.values())
        if fsum <= 0:
            break  # alle am Cap → nicht weiter verteilbar
        for k in free:
            w[k] += excess * (free[k] / fsum)
    return w


def _mn_confidence(stat: dict) -> float:
    """Vertrauen in eine MN-Engine: wächst mit der OOS-Länge (Tage). ~+0.2 je ~6 Monate, Deckel 1.0."""
    days = int((stat or {}).get("days") or 0)
    return round(min(1.0, 0.2 + 0.2 * min(3, days // 180)), 3)


def _collect_mn_raw() -> list[dict]:
    """Liest die Status aller MN-Engines (je ein voller Sim-Lauf) — Producer für den TTL-Memo."""
    out = []
    for name, fn in MN_ENGINES:
        try:
            full = fn() or {}
        except Exception:
            full = {}
        ready = bool(full.get("ready"))      # `ready` steht auf oberster Ebene der status()-Antwort
        st = full.get("stats") or {}
        out.append({"name": name, "ready": ready, "stats": st,
                    "sharpe": st.get("sharpe") if ready else None})
    return out


def mn_sleeve(cfg: dict | None = None) -> dict:
    """Liest die markt-neutralen Engines (csm/pairs/statarb/marketmaking) als gewichteten Sockel.

    Meta-Learner-Gewichtung (tunbar via Master-Config):
    1. **OOS-Härtung** — gehärtete Sharpe = ``max(0, sharpe − sharpe_haircut)`` (Schätzfehler-Abzug),
       Score = gehärtete Sharpe · Konfidenz^``conf_shrink`` (wenig OOS-Belege → stärker gedämpft).
    2. **Soft-Voting** — lineare Normierung (``weight_temp``=0) oder Softmax (Soft-Voting, kleinere
       Temperatur = schärfer auf den Spitzenreiter).
    3. **Diversifikation** — Kappung des Einzelgewichts auf ``max_weight`` (Überschuss umverteilt),
       gegen Dominanz einer einzelnen (evtl. modell-optimistischen) Engine.
    Nur positive (gehärtete) Sharpe trägt bei; Verlierer bleiben sichtbar mit Gewicht 0. Reine
    Lese-/Sim-Operation (kein Netz, keine Orders).
    """
    cfg = cfg or get_config()
    haircut = float(cfg["sharpe_haircut"]); shrink = float(cfg["conf_shrink"])
    cap = float(cfg["max_weight"]); temp = float(cfg["weight_temp"]); scale = float(cfg["sharpe_to_pf"])
    deflate = float(cfg.get("deflate_factor", 0.0))
    psr_weight = max(0.0, min(1.0, float(cfg.get("psr_weight", 1.0))))
    sim_discount = max(0.0, float(cfg.get("sim_discount", 1.0)))
    # 1. Pass: Rohdaten je Engine sammeln (für N_eval / Deflated-Sharpe). Die 4 status()-Aufrufe
    # rechnen jeweils die volle Engine-Simulation — kurzer TTL-Memo kollabiert die Mehrfach-Aufrufe
    # eines UI-/Politik-Bursts (Tagesdaten ändern sich nicht im Sekundentakt; config-unabhängig).
    raw_members = cache.ttl_get("master_mn_raw_members", 30.0, _collect_mn_raw)
    # Deflated-Sharpe: Multiple-Testing-Abzug ∝ √(2·ln N_eval) über die Anzahl bewerteter Engines.
    n_eval = sum(1 for m in raw_members if m["ready"])
    deflation = round(deflate * math.sqrt(2.0 * math.log(max(2, n_eval))), 4) if deflate > 0 else 0.0
    members = []
    for m in raw_members:
        ready, st, sharpe = m["ready"], m["stats"], m["sharpe"]
        conf = _mn_confidence(st) if ready else 0.0
        # Struktureller Simulations-Discount: die Sharpe synthetischer Microstruktur-Engines (SIM_ENGINES)
        # wird VOR der Härtung skaliert — der Edge ist nicht gegen echte Friktionen validierbar. Wirkt auf
        # Score (Gewicht) UND über `hs` auf sleeve_pf/edge/fitness (sonst bei N=1 wirkungslos). Real-Preis-
        # Engines (CSM/Pairs/StatArb) bleiben unberührt.
        synthetic = m["name"] in SIM_ENGINES
        eff_sharpe = (float(sharpe) * sim_discount) if (ready and sharpe is not None and synthetic) else sharpe
        hs = _haircut_sharpe(eff_sharpe, haircut + deflation) if ready else 0.0
        # PSR (statistische Signifikanz der Sharpe, nicht-normal-korrigiert) als zusätzlicher Faktor:
        # nicht signifikante Edges (kurze/fat-tailed Tracks) werden runtergewichtet. psr_weight blendet.
        psr_v = float(st.get("psr", 1.0)) if ready else 0.0
        psr_factor = (1.0 - psr_weight) + psr_weight * psr_v
        score = hs * (conf ** shrink) * psr_factor if hs > 0 else 0.0
        members.append({"engine": m["name"], "ready": ready, "sharpe": sharpe, "confidence": conf,
                        "synthetic": synthetic, "haircut_sharpe": round(hs, 3),
                        "psr": round(psr_v, 3) if ready else None,
                        "ann_pct": st.get("ann_pct"), "maxdd_pct": st.get("maxdd_pct"),
                        "score": round(score, 4), "weight": 0.0})
    active = [m for m in members if m["score"] > 0]
    if active:
        if temp > 0:   # Soft-Voting (Softmax über die Scores, numerisch stabil)
            mx = max(m["score"] for m in active)
            raw = {m["engine"]: math.exp((m["score"] - mx) / temp) for m in active}
        else:          # lineare Normierung (proportional zum Score)
            raw = {m["engine"]: m["score"] for m in active}
        tot = sum(raw.values())
        w = {k: (v / tot if tot > 0 else 0.0) for k, v in raw.items()}
        w = _cap_weights(w, cap)
        for m in active:
            m["weight"] = round(w.get(m["engine"], 0.0), 4)
    # Sockel-Kennzahlen in gemeinsamer PF-Währung — auf der GEHÄRTETEN Sharpe (konsistent OOS-hart).
    sleeve_pf = round(sum(m["weight"] * _sharpe_pf(m["haircut_sharpe"], scale) for m in active), 4) if active else 0.0
    sleeve_conf = round(sum(m["confidence"] for m in active) / len(active), 3) if active else 0.0
    edge = round(sum(max(0.0, _sharpe_pf(m["haircut_sharpe"], scale) - 1.0) * m["confidence"] for m in active), 4)
    # 1/N-Benchmark (DeMiguel et al. 2009): bei kurzen Tracks frisst Schätzfehler den Optimierungs-
    # gewinn — die Gleichgewichtung über dieselben aktiven Engines macht sichtbar, ob die Score-
    # Gewichtung überhaupt Mehrwert liefert (Ehrlichkeits-Referenz, keine eigene Allokation).
    bench_pf = round(sum(_sharpe_pf(m["haircut_sharpe"], scale) for m in active) / len(active), 4) if active else 0.0
    benchmark_1n = {"sleeve_pf": bench_pf, "fitness": round(bench_pf * sleeve_conf, 4),
                    "weight_each": round(1.0 / len(active), 4) if active else 0.0}
    return {"members": members, "active": len(active), "sleeve_pf": sleeve_pf,
            "sleeve_confidence": sleeve_conf, "edge": edge,
            "fitness": round(sleeve_pf * sleeve_conf, 4),
            "benchmark_1n": benchmark_1n,
            "weighting": {"sharpe_haircut": haircut, "conf_shrink": shrink, "max_weight": cap,
                          "weight_temp": temp, "sharpe_to_pf": scale, "deflate_factor": deflate,
                          "deflation": deflation, "psr_weight": psr_weight, "sim_discount": sim_discount}}


def _fundamental_overlay() -> dict:
    """Taktischer Fundamental-Risiko-Overlay (defensiv, ZEITVARIABEL): Event-Risiko (Kalender) +
    Makro-Stance → Skalierungsfaktor fürs gerichtete Sleeve. Defensiv gewrappt (nie train brechen).
    Fließt NICHT in die persistierte Fitness (sonst Versions-Churn) — nur in die effektive Allokation."""
    try:
        er = fundamental.event_risk()
        ms = fundamental.macro_stance(er=er)
        ev_scale = float(er.get("dir_scale", 1.0))
        macro_factor = 0.85 if ms.get("stance") == "risk_off" else 1.0
        return {"available": True, "event_risk": er.get("event_risk"), "dir_scale_event": ev_scale,
                "macro_stance": ms.get("stance"), "total_scale": round(ev_scale * macro_factor, 4),
                "next_event": er.get("next_event"), "source": er.get("source")}
    except Exception as exc:
        return {"available": False, "total_scale": 1.0, "event_risk": "none",
                "macro_stance": "unknown", "note": f"{type(exc).__name__}"}


def _vol_target_factor(cfg: dict) -> float:
    """Vol-Targeting (B3): skaliert das GESAMT-Exposure = clamp(Ziel-Vola / realisierte Vola, 0.3, 1).
    Nur defensiv (≤1, kein Hebeln). Realisierte Vola = jüngste 1h-Return-Stdev aus dem Snapshot.
    0 = aus (Faktor 1.0). Bereitet echtes Sizing für M6 vor (proposal-only)."""
    target = float(cfg.get("vol_target_pct", 0.0))
    if target <= 0:
        return 1.0
    snaps = stats.get_market_snapshots(limit=1)
    vol = (snaps[-1].get("volatility") if snaps else None)
    if not vol or float(vol) <= 0:
        return 1.0
    return round(max(0.3, min(1.0, target / float(vol))), 4)


def exposure_scale() -> float:
    """Öffentlicher Vol-Targeting-Exposure-Skalierer (0.3..1.0, defensiv) — der EINE Wert, den die Hand
    (MasterMeta-Engine) live über die Regime-Bridge konsumiert (D1). Single-Source: delegiert an
    ``_vol_target_factor`` auf der aktuellen Config. Default ``vol_target_pct=0`` ⇒ 1.0 (kein Eingriff)."""
    return _vol_target_factor(get_config())


def _current_regime() -> tuple[str | None, float, str | None, float | None]:
    """Aktuelles Regime + HMM-Konfidenz + ANTIZIPIERTES nächstes Regime + Halte-Wahrscheinlichkeit
    aus dem jüngsten Snapshot. (None,0,None,None) wenn keins; Legacy ohne HMM-Konfidenz → 0.5."""
    snaps = stats.get_market_snapshots(limit=1)
    if not snaps:
        return None, 0.0, None, None
    last = snaps[-1]
    reg = last.get("regime")
    if reg not in REGIMES:
        return None, 0.0, None, None
    conf = last.get("regime_conf")
    nxt = last.get("next_regime")
    stay = last.get("regime_stay_prob")
    return (reg, (float(conf) if conf is not None else 0.5),
            (nxt if nxt in REGIMES else None), (float(stay) if stay is not None else None))


def derive_policy(high_vol: bool = False, regime: str | None = None,
                  regime_conf: float | None = None, next_regime: str | None = None,
                  stay_prob: float | None = None) -> dict:
    """Leitet aus der aktuellen Evidenz die Ensemble-Politik ab: regime-gerichtete Strategien
    (Freqtrade) + markt-neutraler Sockel (csm/pairs/statarb/mm), dynamisch nach Edge gewichtet.

    **Regime-bedingt:** der gerichtete Sleeve wird auf das AKTUELLE Markt-Regime (HMM) konditioniert —
    seine Strategie dominiert, nach HMM-Konfidenz geblendet mit der regime-gemittelten Sicht (so fällt
    er bei unsicherem Regime sanft auf das bisherige Mittel zurück). ``regime``/``regime_conf`` explizit
    übergeben oder (Default) aus dem jüngsten Markt-Snapshot lesen."""
    vals = {s: (stats.get_strategy_validation(s) or {}) for s in STRAT_REGIME}
    opts = {o["strategy"]: o for o in stats.get_all_optimizations()}
    alloc: dict = {}
    for reg in REGIMES:
        want = _REG_MAP.get(reg, reg)
        best = None
        for strat in STRAT_REGIME:
            val = vals.get(strat) or {}
            pf = val.get("profit_factor")
            validated = bool(val.get("validated"))
            # Ehrlichkeits-Gate: eine Strategie OHNE bestandene OOS-Validierung hat keinen belegten
            # gerichteten Edge → ihr effektiver PF wird auf ≤1 gekappt (kein positiver Beitrag),
            # egal wie hoch der Aggregat-PF aussieht. Sonst trägt ein Overfit-PF>3 bei NEGATIVER
            # Gesamtrendite (z.B. DcaDip PF 3.49 / −5.9 %, validated=False) die gerichtete Allokation.
            eff_pf = float(pf) if pf is not None else None
            if eff_pf is not None and not validated:
                eff_pf = min(eff_pf, 1.0)
            tag = STRAT_REGIME.get(strat)
            fit = 1.0 if tag == want else (0.7 if (high_vol and tag == "volatil") else 0.4)
            score = (eff_pf if eff_pf is not None else 0.0) * fit
            cand = {"strategy": strat, "score": round(score, 4), "expected_pf": eff_pf,
                    "profit_factor": pf, "validated": validated,
                    "regime_fit": fit, "confidence": _confidence(val),
                    "params": (opts.get(strat) or {}).get("params"),
                    "profitable": bool(validated and pf and float(pf) > 1.0)}
            if best is None or cand["score"] > best["score"]:
                best = cand
        alloc[reg] = best
    # --- Gerichteter Sleeve: regime-bedingt (aktuelles HMM-Regime dominiert, nach Konfidenz geblendet) ---
    mean_fit = round(sum((a["expected_pf"] or 0.0) * a["confidence"] for a in alloc.values())
                     / max(1, len(alloc)), 4)
    mean_edge = round(sum(max(0.0, (a["expected_pf"] or 0.0) - 1.0) * a["confidence"]
                          for a in alloc.values()), 4)
    if regime is not None:
        cur_reg, reg_conf = regime, (regime_conf if regime_conf is not None else 0.5)
        nxt_reg, stay = next_regime, stay_prob
    else:
        cur_reg, reg_conf, nxt_reg, stay = _current_regime()

    def _fit_edge(a):
        pf = a["expected_pf"] or 0.0
        return pf * a["confidence"], max(0.0, pf - 1.0) * a["confidence"]

    active_alloc = alloc.get(cur_reg) if cur_reg else None
    anticipated = False
    if active_alloc:
        a_fit, a_edge = _fit_edge(active_alloc)
        # A3: Regime-Übergang antizipieren — mit Halte-Wahrscheinlichkeit das nächste Regime einmischen.
        if nxt_reg and nxt_reg != cur_reg and stay is not None and 0.0 < stay < 1.0:
            na = alloc.get(nxt_reg)
            if na:
                nf, ne = _fit_edge(na)
                a_fit = stay * a_fit + (1.0 - stay) * nf
                a_edge = stay * a_edge + (1.0 - stay) * ne
                anticipated = True
        blend = max(0.0, min(1.0, reg_conf))
        dir_fitness = round(blend * a_fit + (1.0 - blend) * mean_fit, 4)
        dir_edge = round(blend * a_edge + (1.0 - blend) * mean_edge, 4)
    else:
        dir_fitness, dir_edge = mean_fit, mean_edge
    profitable_any = any(a["profitable"] for a in alloc.values())

    # --- Markt-neutraler Sockel-Sleeve ---
    mcfg = get_config()
    sleeve = mn_sleeve(mcfg)
    mn_edge = sleeve["edge"]

    # --- Dynamischer Meta-Split (Stacking) dir↔Sockel (gerichtet schwach → Sockel trägt mehr) ---
    mn_share = _meta_split(dir_edge, mn_edge, sleeve["active"] > 0, mcfg)
    dir_share = round(1.0 - mn_share, 4)
    ensemble_fitness = round(dir_share * dir_fitness + mn_share * sleeve["fitness"], 4)

    # --- Taktischer Fundamental-Overlay: dämpft die EFFEKTIVE gerichtete Quote (Fitness bleibt Basis) ---
    overlay = _fundamental_overlay()
    eff_dir_edge = dir_edge * float(overlay.get("total_scale", 1.0))
    eff_mn_share = _meta_split(eff_dir_edge, mn_edge, sleeve["active"] > 0, mcfg)
    overlay["effective_mn_share"] = eff_mn_share
    overlay["effective_dir_share"] = round(1.0 - eff_mn_share, 4)
    overlay["base_mn_share"] = mn_share
    # B3: Vol-Targeting → Gesamt-Exposure-Empfehlung (0..1, defensiv; proposal-only, M6-Sizing-Vorbereitung).
    vt = _vol_target_factor(mcfg)
    overlay["vol_target_factor"] = vt
    overlay["suggested_exposure"] = vt

    _RLBL = {"trend_up": "Aufwärtstrend", "trend_down": "Abwärtstrend", "range": "Seitwärts"}
    reg_txt = ""
    if active_alloc:
        reg_txt = (f"Aktuelles Regime: {_RLBL.get(cur_reg, cur_reg)} (HMM-Konfidenz "
                   f"{int(reg_conf * 100)} %) → gerichtet bevorzugt {active_alloc['strategy']}. ")
    if profitable_any and sleeve["active"]:
        note = reg_txt + "Ensemble: profitable gerichtete Allokation(en) + markt-neutraler Sockel."
    elif sleeve["active"]:
        note = (reg_txt + f"Gerichtete Strategien unprofitabel (PF<1) — Ensemble stützt sich auf den "
                f"markt-neutralen Sockel ({sleeve['active']} aktive Engine(s), Anteil {int(mn_share * 100)} %).")
    else:
        note = (reg_txt + "Keine Allokation profitabel und kein aktiver MN-Sockel — Master bleibt "
                "defensiv; verbessert sich mit besseren Belegen.")
    if overlay.get("total_scale", 1.0) < 0.999:
        nxt = overlay.get("next_event") or {}
        note += (f" ⚠ Fundamental-Overlay aktiv (Event-Risiko {overlay.get('event_risk')}, "
                 f"Makro {overlay.get('macro_stance')}): gerichtet defensiv gedämpft → Sockel-Anteil "
                 f"{int(eff_mn_share * 100)} %"
                 + (f", nächstes Event {nxt.get('title')} in {nxt.get('hours_until')} h" if nxt else "") + ".")

    return {"ts": datetime.now(timezone.utc).isoformat(), "allocations": alloc,
            "active_regime": {"regime": cur_reg, "confidence": round(reg_conf, 3) if cur_reg else None,
                              "allocation": active_alloc, "next_regime": nxt_reg,
                              "stay_prob": stay, "anticipated": anticipated},
            "mn_sleeve": sleeve, "ensemble": {"mn_share": mn_share, "dir_share": dir_share,
                                              "dir_fitness": dir_fitness, "mn_fitness": sleeve["fitness"],
                                              "dir_edge": dir_edge, "mn_edge": mn_edge},
            "fundamental": overlay,
            "fitness": ensemble_fitness, "profitable_any": profitable_any, "note": note}


def get_current() -> dict | None:
    with stats._conn() as c:
        _ensure(c)
        row = c.execute("SELECT version, ts, fitness, parent_version, policy, note "
                        "FROM master_policy ORDER BY version DESC LIMIT 1").fetchone()
    if not row:
        return None
    pol = json.loads(row[4])
    return {"version": row[0], "ts": row[1], "fitness": row[2], "parent_version": row[3],
            "note": row[5], **pol}


def fitness_history(limit: int = 30) -> list[dict]:
    with stats._conn() as c:
        _ensure(c)
        rows = c.execute("SELECT version, ts, fitness FROM master_policy ORDER BY version ASC").fetchall()
    return [{"version": r[0], "ts": r[1], "fitness": r[2]} for r in rows][-limit:]


def _evidence_fp(cand: dict) -> str:
    """Fingerprint der EVIDENZ, auf der eine Politik fußt (Strategie-PFs je Regime + MN-Engine-Sharpes +
    Gewichtungs-Methodik). Ändert er sich, ist die alte (auf anderer Evidenz berechnete) Fitness nicht
    mit der neuen vergleichbar → Re-Baseline. Reine Lesefunktion über das schon abgeleitete ``cand``."""
    import hashlib
    parts = []
    for reg, a in sorted((cand.get("allocations") or {}).items()):
        a = a or {}
        parts.append(f"{reg}:{a.get('strategy')}:{a.get('expected_pf')}:{a.get('confidence')}")
    for m in (cand.get("mn_sleeve") or {}).get("members", []):
        parts.append(f"{m.get('engine')}:{m.get('ready')}:{m.get('sharpe')}:{m.get('confidence')}")
    parts.append(json.dumps((cand.get("mn_sleeve") or {}).get("weighting"), sort_keys=True))
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]


def train_step(high_vol: bool = False) -> dict:
    """Ein Trainingsschritt: neue Politik ableiten → bewerten → nur behalten, wenn besser (versioniert).

    Ratchet (kein Churn bei gleicher Evidenz): innerhalb DERSELBEN Evidenz wird nur eine höhere Fitness
    übernommen. **Ändert sich die zugrundeliegende Evidenz** (Strategie-PFs, MN-Sharpes oder die
    Gewichtungs-Methodik — erkannt am ``_evidence_fp``), sind alte und neue Fitness NICHT vergleichbar →
    Re-Baseline (Politik wird einmalig persistiert, auch wenn die neue, ehrliche Fitness niedriger ausfällt).
    So bleibt die gespeicherte Politik immer konsistent zur aktuellen Beleglage — sie kann nicht mehr auf
    einer veralteten, optimistischeren Evidenz „festhängen"."""
    cand = derive_policy(high_vol)
    cur = get_current()
    cand_fp = _evidence_fp(cand)
    cur_fp = (cur or {}).get("evidence_fp")
    # Evidenz-Wechsel (auch Legacy-Politik ohne gespeicherten Fingerprint → einmalige Neu-Kalibrierung).
    evidence_changed = cur is not None and cur_fp != cand_fp
    improved = (cur is None) or evidence_changed or (cand["fitness"] > (cur.get("fitness") or -1e9) + 1e-9)
    version = cur["version"] if cur else 0
    if improved:
        with stats._conn() as c:
            _ensure(c)
            c.execute("INSERT INTO master_policy(ts,fitness,parent_version,policy,note) VALUES(?,?,?,?,?)",
                      (cand["ts"], cand["fitness"], (cur["version"] if cur else None),
                       json.dumps({"allocations": cand["allocations"], "mn_sleeve": cand["mn_sleeve"],
                                   "ensemble": cand["ensemble"], "active_regime": cand["active_regime"],
                                   "fundamental": cand.get("fundamental"), "fitness": cand["fitness"],
                                   "profitable_any": cand["profitable_any"], "evidence_fp": cand_fp}),
                       cand["note"]))
            version = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"improved": improved, "rebaselined": evidence_changed, "version": version,
            "candidate_fitness": cand["fitness"], "current_fitness": (cur.get("fitness") if cur else None),
            "evidence_changed": evidence_changed, "policy": cand, "note": cand["note"]}


def status() -> dict:
    validated = sum(1 for s in STRAT_REGIME
                    if (stats.get_strategy_validation(s) or {}).get("profit_factor") is not None)
    mm = stats.get_strategy_validation("MasterMeta") or {}
    executable = {"strategy": "MasterMeta", "profit_factor": mm.get("profit_factor"),
                  "profit_total_pct": mm.get("profit_total_pct"), "windows": mm.get("windows"),
                  "note": "Ausführbare Regime-Switching-Engine (U7-Stufe 2) — setzt die Politik real um; "
                          "über den Lern-Loop tunbar."} if mm.get("profit_factor") is not None else None
    pol = get_current()
    fl = _fundamental_overlay()       # frischer, zeitvariabler Overlay (gegen die aktuelle Politik)
    if pol and pol.get("ensemble"):
        de = pol["ensemble"].get("dir_edge", 0.0) * float(fl.get("total_scale", 1.0))
        me = pol["ensemble"].get("mn_edge", 0.0)
        fl["effective_mn_share"] = _meta_split(de, me, me > 0, get_config())
        fl["base_mn_share"] = pol["ensemble"].get("mn_share")
    vt = _vol_target_factor(get_config())
    fl["vol_target_factor"] = vt
    fl["suggested_exposure"] = vt
    return {"policy": pol, "fitness_history": fitness_history(),
            "executable_meta": executable, "mn_sleeve_live": mn_sleeve(), "config": get_config(),
            "fundamental_live": fl,
            "evidence": {"strategies": len(STRAT_REGIME), "validated": validated,
                         "mn_engines": len(MN_ENGINES)},
            "explainer": "Der Master ist ein Ensemble über ALLE Edge-Quellen: regime-gerichtete "
                         "Strategien (Freqtrade) PLUS ein markt-neutraler Sockel (CSM/Pairs/StatArb/"
                         "Market-Making), dynamisch nach OOS-Edge gewichtet (gerichtet schwach → Sockel "
                         "trägt mehr). Behält nur die bessere Version (Fitness-Verlauf). Er handelt nicht "
                         "selbst; Anwendung/Echtgeld bleibt deine Freigabe."}
