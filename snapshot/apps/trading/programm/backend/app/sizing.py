"""sizing.py — Vola-skaliertes Positions-Sizing pro Bot (P3).

Heute hat jeder Bot einen **festen** Stake. Folge: ein ruhiger und ein hochvolatiler Bot mit gleichem
Stake tragen sehr **unterschiedliches** Risiko zum Portfolio bei. „Vol-Targeting" ist laut Recherche eine
der konsistentesten Verbesserungen: die Positionsgröße wird **invers zur realisierten Volatilität**
skaliert, sodass jeder Bot ein ähnliches Risiko-Budget belegt.

Modell (absolut, driftfrei): aus den Tages-Snapshots wird die realisierte Tagesvolatilität der Equity
geschätzt (Stdev der Tagesrenditen, via ``meta.consistency``). Empfohlener Stake:

    empfohlen = clip( referenz_stake × ziel_vol / realisierte_vol , min_stake , max_stake )

Bei ``realisierte_vol == ziel_vol`` ergibt sich genau ``referenz_stake`` (neutral). Weil die Empfehlung
**absolut** aus der Vola folgt (nicht aus dem aktuellen Stake), driftet sie bei wiederholter Anwendung
nicht. Bots mit zu wenig Historie bekommen neutral den Referenz-Stake (kein blindes Skalieren).

Reine **Empfehlung** (proposal-only) — analog zu den gelernten Upgrades. Das Anwenden (Stake setzen +
Bot-Neustart) passiert nur auf ausdrückliche Aktion über die API. 0 Risiko (Demo).

**FP-2 (T4, docs/KELLY_SIZING_SPEC.md):** darüber liegt die Portfolio-Klemmkette ``portfolio_plan``
(K4 Budget → K5 Konzentration → K6 Governor, Reihenfolge normativ) und die opt-in **Brücke zur Hand**
``suggested_sizing.json`` (Muster ``hmm_regime.json``): Backend schreibt atomar, die MasterMeta-Engine
liest in ``custom_stake_amount`` — nur bei Opt-in, nur dry_run, nur ``mode=='apply'``. Alle neuen
Hebel haben INERTE Defaults (Budget aus, Brücke aus, Shrink aus) ⇒ ohne Opt-in byte-identisch."""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import jsonstore, meta, registry, stats
from .config import DATA_DIR

STATE_FILE = DATA_DIR / "sizing.json"

# Sizing-Bridge: das Backend exportiert den geklemmten Portfolio-Plan in eine Datei, die die
# Engine-Strategie (anderes venv/Prozess) lesen kann (master_meta.custom_stake_amount). Pfad via
# Env TBT_SIZING_FILE überschreibbar — der runner reicht ihn IMMER an Bot-Subprozesse durch
# (analog tracker.REGIME_BRIDGE_FILE = single source of truth, kein Drift).
SIZING_BRIDGE_FILE = Path(os.environ.get("TBT_SIZING_FILE") or (DATA_DIR / "suggested_sizing.json"))

_DEFAULTS = {
    "enabled": True,
    "reference_stake": 100.0,   # Stake bei realisierter Vol == Ziel-Vol (neutraler Anker)
    "target_vol_pct": 2.0,      # angepeilte Tagesvolatilität der Bot-Equity (%)
    "min_stake": 25.0,          # harte Unterkante (nie ganz auf 0 skalieren)
    "max_stake": 250.0,         # harte Oberkante (ruhige Bots nicht unbegrenzt hebeln)
    "min_returns": 3,           # so viele Tagesrenditen müssen vorliegen, sonst neutral
    "min_change_pct": 10.0,     # Empfehlung erst ab dieser relativen Abweichung als „Änderung" zählen
    # --- Erwartungswert-/Kelly-Tilt (opt-in, Default AUS → Sizing exakt wie heute; gegated) ---
    # Vol-Targeting setzt das RISIKO-Budget; dieser Tilt verschiebt es nach dem belegten EDGE
    # (Erwartungswert/Kelly), NICHT nach Winrate. Positiver Erwartungswert → moderat hoch
    # (fraktionaler Kelly, hart gedeckelt); NEGATIVER Erwartungswert → runter (nie hoch). Proposal-only.
    "expectancy_enabled": False,  # Hauptschalter (Default AUS = laufende Empfehlungen unverändert)
    "kelly_fraction": 0.25,       # fraktionaler Kelly (Viertel-Kelly = Standard gegen Ruin/Schätzfehler)
    "kelly_cap": 1.5,             # HARTE Obergrenze des Erwartungswert-Multiplikators (nie hochhebeln)
    "kelly_floor": 0.5,           # HARTE Untergrenze (negative-Edge-Bots werden gekappt, nicht über-geschrumpft)
    "min_trades_kelly": 20,       # so viele entschiedene Trades nötig, sonst neutral (Multiplikator 1.0)
    # --- FP-2 Edge-Quelle + Konfidenz-Abschlag (K0/K1, SPEC §1 — Defaults inert) ---
    "edge_source": "bot",         # "bot" (heutiger Pfad) | "strategy" (Pool aller Bots der Strategie) | "auto"
    "min_trades_strategy": 60,    # Mindest-Stichprobe für den Strategie-Pool (mehr Bots ⇒ mehr Anspruch)
    "shrink_trades": 0,           # Konfidenz-Shrinkage kelly×n/(n+k) gegen Schätzfehler (0 = aus; Empfehlung 40)
    "sim_discount": 1.0,          # dry-run-Edge-Discount (Fills ohne Slippage sind optimistisch; 1.0 = aus,
                                  # Empfehlung 0.85 — Analogie: master_config.sim_discount für Sim-Engines)
    # --- FP-2 Portfolio-Klemmkette (K4–K6, SPEC §3 — wirkt NUR in portfolio_plan, nie in recommend) ---
    "portfolio_budget_pct": 0.0,  # Margin-Deckel Σ stake×max_open_trades ≤ pct% × Σ dry_run_wallet (0 = aus)
    "concentration_clamp": True,  # K5: Konzentrations-warn ⇒ kein Upsizing betroffener Assets
    "governor_clamp": True,       # K6: Governor warn/breach ⇒ flottenweit kein Upsizing (letztes Wort)
    # --- FP-2 Brücke zur Hand (SPEC §4 — Default AUS ⇒ Datei wird nicht geschrieben, 0 Verhaltensänderung) ---
    "bridge_enabled": False,      # Hauptschalter: Autopilot schreibt suggested_sizing.json
    "bridge_mode": "proposal",    # "proposal" (Engine wendet NIE an) | "apply" (nur dry_run-Bots mit Opt-in)
    "bridge_max_age_s": 900,      # Engine-Frische-Gate (veraltete Datei wird ignoriert)
}


def get_config() -> dict:
    return {**_DEFAULTS, **(jsonstore.read_json(STATE_FILE, {}) or {})}


def set_config(patch: dict) -> dict:
    s = get_config()
    for k in ("reference_stake", "target_vol_pct", "min_stake", "max_stake", "min_change_pct",
              "kelly_fraction", "kelly_cap", "kelly_floor", "sim_discount", "portfolio_budget_pct"):
        if k in patch:
            try:
                s[k] = float(patch[k])
            except (TypeError, ValueError):
                pass
    for k in ("min_returns", "min_trades_kelly", "min_trades_strategy"):
        if k in patch:
            try:
                s[k] = max(2, int(patch[k]))
            except (TypeError, ValueError):
                pass
    for k in ("enabled", "expectancy_enabled", "concentration_clamp", "governor_clamp",
              "bridge_enabled"):
        if k in patch:
            s[k] = bool(patch[k])
    if "shrink_trades" in patch:
        try:
            s["shrink_trades"] = max(0, int(patch["shrink_trades"]))   # 0 = aus
        except (TypeError, ValueError):
            pass
    if patch.get("edge_source") in ("bot", "strategy", "auto"):
        s["edge_source"] = patch["edge_source"]
    if patch.get("bridge_mode") in ("proposal", "apply"):
        s["bridge_mode"] = patch["bridge_mode"]
    if "bridge_max_age_s" in patch:
        try:
            s["bridge_max_age_s"] = max(60, int(patch["bridge_max_age_s"]))
        except (TypeError, ValueError):
            pass
    # min/max konsistent halten.
    if s["min_stake"] > s["max_stake"]:
        s["min_stake"], s["max_stake"] = s["max_stake"], s["min_stake"]
    # Kelly-Caps konsistent halten (Floor ≤ Cap); λ und Discounts hart in sichere Bereiche klemmen.
    if s["kelly_floor"] > s["kelly_cap"]:
        s["kelly_floor"], s["kelly_cap"] = s["kelly_cap"], s["kelly_floor"]
    s["kelly_fraction"] = _clip(float(s["kelly_fraction"]), 0.0, 1.0)      # nie über Voll-Kelly
    s["sim_discount"] = _clip(float(s["sim_discount"]), 0.0, 1.0)          # Discount, nie Aufschlag
    s["portfolio_budget_pct"] = max(0.0, float(s["portfolio_budget_pct"]))
    jsonstore.write_atomic(STATE_FILE, s)
    return s


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _edge_for(bot, cfg: dict) -> tuple[dict, str, int]:
    """K0 — Edge-Quelle für EINEN Bot (SPEC §1): ``(expectancy, quelle, n_effektiv)``.

    ``edge_source``: "bot" = eigene Live-Trade-DB (Mindest-Stichprobe ``min_trades_kelly``) ·
    "strategy" = gepoolte Trades ALLER Bots derselben Strategie (``min_trades_strategy``) ·
    "auto" = Bot wenn genug eigene Trades, sonst Strategie-Pool, sonst neutral.
    Unter der Mindest-Stichprobe wird ``kelly`` auf None gesetzt (⇒ neutraler Tilt) — der Aufrufer
    braucht keine eigene Gate-Logik."""
    source = str(cfg.get("edge_source") or "bot")
    min_bot = int(cfg["min_trades_kelly"])
    min_strat = int(cfg.get("min_trades_strategy") or 60)

    def _gated(ex: dict, min_n: int) -> tuple[dict, int]:
        n = int(ex.get("n_decided") or 0)
        if n < min_n:
            ex = {**ex, "kelly": None}
        return ex, n

    if source in ("bot", "auto"):
        ex, n = _gated(stats.trade_expectancy(getattr(bot, "id", "")), min_bot)
        if ex.get("kelly") is not None or source == "bot":
            return ex, "bot", n
    # Strategie-Pool: gleiche Strategie = gleicher Signalgeber ⇒ gemeinsame Edge-Hypothese.
    strat = getattr(bot, "strategy", None)
    ids = [b.id for b in registry.list_bots() if getattr(b, "strategy", None) == strat]
    ex, n = _gated(stats.pooled_expectancy(ids), min_strat)
    return ex, "strategy", n


def expectancy_factor(bot, cfg: dict) -> dict:
    """Erwartungswert-/Kelly-Multiplikator für EINEN Bot (read-only, opt-in via ``expectancy_enabled``).

    Skaliert die vol-basierte Empfehlung nach dem belegten EDGE (klassischer Kelly aus der Live-Trade-
    DB bzw. dem Strategie-Pool, K0), NICHT nach Winrate. Vor dem Tilt der **Konfidenz-Abschlag** (K1,
    SPEC §1, Defaults inert): ``kelly_eff = kelly × n/(n+shrink_trades) × sim_discount`` — Shrinkage
    gegen Schätzfehler kleiner Stichproben + Discount für optimistische dry-run-Fills. Multiplikator =
    clip(1 + ``kelly_fraction``·kelly_eff, ``kelly_floor``, ``kelly_cap``): positiver Kelly → >1
    (gedeckelt), negativer → <1 (ein Verlierer wird NIE hochgehebelt). Zu wenig Trades / undefinierter
    Payoff → neutral (1.0). Reine Empfehlung — kein echtes Geld."""
    if not cfg.get("expectancy_enabled"):
        return {"mult": 1.0, "applied": False, "reason": "Erwartungswert-Tilt aus", "expectancy": None}
    ex, source, n = _edge_for(bot, cfg)
    kelly = ex.get("kelly")
    if kelly is None:
        return {"mult": 1.0, "applied": False, "expectancy": ex, "source": source,
                "reason": f"zu wenig entschiedene Trades ({n}, Quelle {source}) → neutral"}
    # K1 — Konfidenz-Abschlag (beide Faktoren Default-inert: shrink 0 ⇒ ×1, discount 1.0 ⇒ ×1).
    shrink = int(cfg.get("shrink_trades") or 0)
    kelly_eff = float(kelly) * (n / (n + shrink) if shrink > 0 else 1.0) * float(cfg.get("sim_discount", 1.0))
    mult = _clip(1.0 + float(cfg["kelly_fraction"]) * kelly_eff,
                 float(cfg["kelly_floor"]), float(cfg["kelly_cap"]))
    src_txt = "" if source == "bot" else f", Quelle {source}-Pool n={n}"
    if kelly > 0:
        reason = f"positiver Erwartungswert (Kelly {kelly:+.2f}{src_txt}) → ×{mult:.2f} (fraktionaler Kelly, gedeckelt)"
    elif kelly < 0:
        reason = f"negativer Erwartungswert (Kelly {kelly:+.2f}{src_txt}) → ×{mult:.2f} (verkleinern, nie hochhebeln)"
    else:
        reason = "Erwartungswert neutral → ×1.00"
    return {"mult": round(mult, 3), "applied": True, "expectancy": ex, "source": source,
            "kelly_eff": round(kelly_eff, 4), "reason": reason}


def recommend_for(bot, cfg: dict) -> dict:
    """Sizing-Empfehlung für EINEN Bot (read-only). Nutzt die realisierte Vola aus ``meta.consistency``."""
    cons = meta.consistency(bot.id)
    # BUGFIX: meta.consistency liefert die realisierte Tagesvola unter dem Key ``volatility_pct``
    # (nicht ``volatility``) — vorher las das Sizing den falschen Key und fiel für JEDEN Bot in den
    # neutralen Zweig (Vol-Targeting wirkte nie; der Expectancy-Tilt baut darauf auf und blieb tot).
    vol = cons.get("volatility_pct")
    days = cons.get("days_tracked", 0)
    current = float(getattr(bot, "stake_amount", 0.0) or 0.0)
    ref = float(cfg["reference_stake"])
    target = float(cfg["target_vol_pct"])

    enough = vol is not None and vol > 0 and days >= cfg["min_returns"]
    if not enough:
        return {"bot_id": bot.id, "tag": getattr(bot, "tag", None), "name": bot.name,
                "strategy": bot.strategy, "realized_vol_pct": vol, "days_tracked": days,
                "current_stake": round(current, 2), "recommended_stake": round(ref, 2),
                "factor": 1.0, "delta": round(ref - current, 2), "change": False,
                "reason": f"zu wenig Historie ({days} Tage) → neutraler Referenz-Stake"}

    factor_raw = target / vol
    # Erwartungswert-/Kelly-Tilt (opt-in): verschiebt das vol-Budget nach belegtem Edge. Default aus
    # → ex_mult = 1.0 → Empfehlung exakt wie bisher (kein Regress an laufenden Bots).
    ef = expectancy_factor(bot, cfg)
    ex_mult = float(ef["mult"])
    recommended = _clip(ref * factor_raw * ex_mult, float(cfg["min_stake"]), float(cfg["max_stake"]))
    factor = recommended / ref if ref else 1.0
    delta = recommended - current
    change = current > 0 and abs(delta) / current * 100.0 >= float(cfg["min_change_pct"])
    if vol > target:
        reason = f"volatil (Vol {vol}% > Ziel {target}%) → Stake verkleinern"
    elif vol < target:
        reason = f"ruhig (Vol {vol}% < Ziel {target}%) → Stake vergrößern"
    else:
        reason = "Vol auf Ziel → neutral"
    if ef.get("applied"):
        reason += " · " + ef["reason"]
    return {"bot_id": bot.id, "tag": getattr(bot, "tag", None), "name": bot.name,
            "strategy": bot.strategy, "realized_vol_pct": vol, "days_tracked": days,
            "current_stake": round(current, 2), "recommended_stake": round(recommended, 2),
            "factor": round(factor, 3), "vol_factor": round(_clip(factor_raw, 0, 1e9), 3),
            "expectancy_mult": round(ex_mult, 3), "expectancy": ef.get("expectancy"),
            "delta": round(delta, 2), "change": change, "reason": reason}


def recommend() -> dict:
    """Sizing-Empfehlungen für alle Bots (read-only) + Konfiguration + Zusammenfassung."""
    cfg = get_config()
    rows = [recommend_for(b, cfg) for b in registry.list_bots()]
    changes = [r for r in rows if r["change"]]
    sized = [r for r in rows if r["realized_vol_pct"] is not None]
    return {"enabled": bool(cfg["enabled"]), "config": {k: cfg[k] for k in _DEFAULTS},
            "recommendations": rows, "n_bots": len(rows), "n_with_vol": len(sized),
            "n_changes": len(changes), "changes": changes}


# ------------------------------------------------------- FP-2: Portfolio-Klemmkette K4–K6 (SPEC §3)
def _water_fill(stakes: dict[str, float], weights: dict[str, float], floor: float,
                cap: float) -> tuple[dict[str, float], float, bool]:
    """K4-Kern: proportionales Herunterskalieren mit hartem Floor je Stake (Water-Filling).

    EIN Faktor s ≤ 1 für alle, bis Σ stake×weight ≤ cap; Stakes, die dabei unter ``floor`` fielen,
    werden gefloort und scheiden aus der Skalierung aus, der Rest wird neu skaliert (Fixpunkt nach
    ≤ n Runden) — die RELATIVEN Kelly-Gewichte der Übrigen bleiben erhalten. Degeneriert
    (selbst alle-auf-Floor über dem Deckel) ⇒ ``(alle floor, 0.0, True)``: ehrlich melden statt
    still verletzen. Rein + deterministisch (Property-Tests in test_kelly_clamps.py)."""
    total = sum(stakes[b] * weights[b] for b in stakes)
    if cap <= 0 or total <= cap:
        return dict(stakes), 1.0, False
    if sum(floor * weights[b] for b in stakes) > cap:
        return {b: floor for b in stakes}, 0.0, True
    floored: set[str] = set()
    s = 1.0
    for _ in range(len(stakes) + 1):
        rest = cap - sum(floor * weights[b] for b in floored)
        denom = sum(stakes[b] * weights[b] for b in stakes if b not in floored)
        s = min(1.0, rest / denom) if denom > 0 else 0.0
        newly = {b for b in stakes if b not in floored and s * stakes[b] < floor}
        if not newly:
            break
        floored |= newly
    return ({b: (floor if b in floored else s * stakes[b]) for b in stakes}, round(s, 6), False)


def _overexposed_assets(conc: dict) -> set[str]:
    """K5-Input: Assets, in die bei Konzentrations-warn NICHT aufgesizet werden darf — das
    über-gedeckelte Top-Asset plus alle präsenten Mitglieder über-gedeckelter Cluster."""
    out: set[str] = set()
    if (conc or {}).get("severity") != "warn":
        return out
    cap = float(((conc.get("config") or {}).get("max_asset_share_pct")) or 100.0)
    for a in (conc.get("assets") or []):
        if float(a.get("share_pct") or 0.0) > cap and a.get("asset"):
            out.add(str(a["asset"]))
    for c in (conc.get("clusters") or []):
        if c.get("over"):
            out.update(str(x) for x in (c.get("present") or c.get("assets") or []))
    return out


def _apply_portfolio_clamps(rows: list[dict], *, mots: dict[str, int], assets: dict[str, set],
                            wallet_total: float, overexposed: set[str],
                            governor_severity: str, cfg: dict) -> dict:
    """Reine Klemmkette K4→K5→K6 auf fertigen per-Bot-Empfehlungen (Reihenfolge NORMATIV, SPEC §3).

    K4 Portfolio-Budget (Margin Σ stake×max_open_trades ≤ pct% × Σ Wallet, Water-Filling) →
    K5 Konzentration (warn ⇒ kein Upsizing betroffener Assets) → K6 Governor (warn/breach ⇒
    flottenweit kein Upsizing; letztes Wort). Freeze heißt ``min(stake, aktuell)`` und hebt NIE
    zurück auf ``min_stake`` an (Invariante: final ≥ min(min_stake, aktuell)). Alle Stufen sind
    monoton nicht-erhöhend; jede Klemme wird je Bot protokolliert (``clamps``) + im ``trace``
    zusammengefasst. Seiteneffektfrei/deterministisch — Property-Tests prüfen P1–P6."""
    trace: list[str] = []
    floor = float(cfg["min_stake"])
    stakes = {r["bot_id"]: float(r["recommended_stake"]) for r in rows}
    clamps: dict[str, list[str]] = {b: [] for b in stakes}

    # K4 — Portfolio-Budget (Default 0 = aus).
    pct = float(cfg.get("portfolio_budget_pct") or 0.0)
    weights = {b: float(mots.get(b) or 1) for b in stakes}
    budget: dict = {"pct": pct, "cap": None, "scale": 1.0, "infeasible": False,
                    "wallet_total": round(wallet_total, 2)}
    if pct > 0 and wallet_total > 0 and stakes:
        cap = pct / 100.0 * wallet_total
        scaled, s, infeasible = _water_fill(stakes, weights, floor, cap)
        for b, r in ((r["bot_id"], r) for r in rows):
            if scaled[b] < stakes[b] - 1e-9:
                clamps[b].append("K4 Budget → min_stake" if scaled[b] <= floor + 1e-9
                                 else f"K4 Budget ×{s:g}")
        stakes = scaled
        budget.update(cap=round(cap, 2), scale=s, infeasible=infeasible)
        if s < 1.0 or infeasible:
            trace.append(f"K4: Budget {pct:g}% × Wallet {wallet_total:.0f} = Deckel {cap:.0f} → "
                         f"Skalierung ×{s:g}" + (" · INFEASIBLE (alle auf min_stake)" if infeasible else ""))

    # K5 — Konzentrations-Klemme (strukturell: kein Upsizing in den Klumpen, kein Zwangs-Downsizing).
    if bool(cfg.get("concentration_clamp", True)) and overexposed:
        hit = 0
        for r in rows:
            b = r["bot_id"]
            cur = float(r.get("current_stake") or 0.0)
            touched = (assets.get(b) or set()) & overexposed
            if cur > 0 and touched and stakes[b] > cur:
                stakes[b] = cur
                clamps[b].append("K5 Konzentration: kein Upsizing (" + "/".join(sorted(touched)) + ")")
                hit += 1
        if hit:
            trace.append(f"K5: Konzentrations-warn ({'/'.join(sorted(overexposed))}) → "
                         f"{hit} Bot(s) eingefroren")

    # K6 — Governor-Klemme (akut, LETZTES WORT: warn/breach ⇒ flottenweit kein Upsizing).
    if bool(cfg.get("governor_clamp", True)) and governor_severity in ("warn", "breach"):
        hit = 0
        for r in rows:
            b = r["bot_id"]
            cur = float(r.get("current_stake") or 0.0)
            if cur > 0 and stakes[b] > cur:
                stakes[b] = cur
                clamps[b].append(f"K6 Governor {governor_severity}: kein Upsizing")
                hit += 1
        trace.append(f"K6: Governor {governor_severity} → kein Upsizing flottenweit ({hit} geklemmt)")

    out_rows: list[dict] = []
    min_change = float(cfg["min_change_pct"])
    for r in rows:
        b = r["bot_id"]
        cur = float(r.get("current_stake") or 0.0)
        planned = round(stakes[b], 2)
        delta = round(planned - cur, 2)
        out_rows.append({**r, "planned_stake": planned, "clamps": clamps[b], "delta": delta,
                         "change": cur > 0 and abs(delta) / cur * 100.0 >= min_change})
    budget["margin_total"] = round(sum(stakes[b] * weights[b] for b in stakes), 2)
    return {"rows": out_rows, "budget": budget, "trace": trace,
            "governor_severity": governor_severity, "overexposed_assets": sorted(overexposed)}


def portfolio_plan(use_cache: bool = True) -> dict:
    """Portfolio-Sizing-Plan (read-only): per-Bot-Empfehlungen (K0–K3) + Klemmkette (K4–K6).

    Liest Governor-Schwere und Konzentrations-Analyse defensiv (Fehler ⇒ ok/keine Klemme statt
    Abbruch — der Plan ist Empfehlung, nicht Wächter; der echte Wächter bleibt der Governor selbst).
    **Echtgeld-Bots (dry_run=False) werden NIE geplant** — nur informativ unter ``skipped``
    gelistet (Doppel-Schutz zusätzlich zum dry_run-Gate der Engine, SPEC §4)."""
    from . import concentration, governor   # lazy: Modul-Load leicht halten, kein Zyklus-Risiko
    cfg = get_config()
    bots = list(registry.list_bots())
    dry = [b for b in bots if bool(getattr(b, "dry_run", True))]
    rows = [recommend_for(b, cfg) for b in dry]
    try:
        conc = concentration.analyze()
    except Exception:
        conc = {"severity": "ok"}
    try:
        sev = str((governor.evaluate(use_cache=use_cache) or {}).get("severity") or "ok")
    except Exception:
        sev = "ok"
    mots = {b.id: int(getattr(b, "max_open_trades", 1) or 1) for b in dry}
    assets = {b.id: {a for a in (concentration._base_asset(p) for p in (getattr(b, "pairs", None) or []))
                     if a} for b in dry}
    wallet_total = sum(float(getattr(b, "dry_run_wallet", 0.0) or 0.0) for b in dry)
    res = _apply_portfolio_clamps(rows, mots=mots, assets=assets, wallet_total=wallet_total,
                                  overexposed=_overexposed_assets(conc),
                                  governor_severity=sev, cfg=cfg)
    skipped = [{"bot_id": b.id, "name": b.name, "reason": "Echtgeld — nicht geplant"}
               for b in bots if not bool(getattr(b, "dry_run", True))]
    return {"enabled": bool(cfg["enabled"]), "config": {k: cfg[k] for k in _DEFAULTS},
            "n_bots": len(rows), "skipped": skipped, **res}


# ------------------------------------------------------- FP-2: Brücke zur Hand (SPEC §4)
def write_bridge_auto() -> dict:
    """Schreibt die Sizing-Bridge ``suggested_sizing.json`` (Autopilot-Tick, nach dem Governor).

    Opt-in-Kette Backend-seitig: ``bridge_enabled`` False (Default) ⇒ es wird NICHTS geschrieben.
    ``bridge_mode='apply'`` degradiert bei Governor-**breach** automatisch auf ``proposal`` (in einer
    Breach-Lage wendet die Hand nichts Neues an, P5). Payload nur dry_run-Bots; atomar via
    ``jsonstore.write_atomic``. Die Engine hat ihre eigenen Gates (Opt-in-Param + dry_run + Frische)."""
    cfg = get_config()
    if not cfg.get("bridge_enabled"):
        return {"written": False, "reason": "bridge_enabled=false (Default) — Brücke aus"}
    plan = portfolio_plan()
    sev = str(plan.get("governor_severity") or "ok")
    mode = "apply" if (str(cfg.get("bridge_mode")) == "apply" and sev != "breach") else "proposal"
    stakes = {r["bot_id"]: {"stake": float(r["planned_stake"]),
                            "current": float(r.get("current_stake") or 0.0)}
              for r in plan.get("rows") or []}
    payload = {"ts": int(time.time() * 1000), "mode": mode, "governor_severity": sev,
               "stakes": stakes, "budget": plan.get("budget")}
    jsonstore.write_atomic(SIZING_BRIDGE_FILE, payload)
    degraded = (str(cfg.get("bridge_mode")) == "apply" and mode == "proposal")
    return {"written": True, "mode": mode, "governor_severity": sev, "n": len(stakes),
            "degraded": degraded, "file": str(SIZING_BRIDGE_FILE)}
