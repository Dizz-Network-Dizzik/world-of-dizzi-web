"""introspect.py — Selbst-Analyse / Selbst-Audit.

Das System erfasst seine **eigene Struktur** in Unterkategorien, bewertet sich anhand **realer
Signale** (Health + konkrete Verbesserungs-Hebel je Kategorie + nächstes Lern-Ziel) und **sammelt**
die Schlüsse ins Learning-Ledger ein. Rein lesend / leichtgewichtig (keine Backtests), proposal-only.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from . import maintenance, master, stats
from .config import PROJECT_ROOT
from .meta import STRAT_REGIME


def _cat(name, label, modules, health, findings, improvements):
    return {"name": name, "label": label, "modules": modules, "health": health,
            "findings": findings, "improvements": improvements}


def _bots():
    from .registry import list_bots
    try:
        return list_bots()
    except Exception:
        return []


def assess() -> dict:
    """Strukturierte Selbst-Bewertung über alle Unterkategorien (aus echtem Systemzustand)."""
    vals = {s: (stats.get_strategy_validation(s) or {}) for s in STRAT_REGIME}
    pfs = [v.get("profit_factor") for v in vals.values() if v.get("profit_factor") is not None]
    ready = sum(1 for p in pfs if p and p > 1)
    best_pf = max(pfs) if pfs else None
    opts = {o["strategy"]: o for o in stats.get_all_optimizations()}
    cooldowners = [s for s, o in opts.items() if (o.get("params") or {}).get("min_bars_between")]
    mp = master.get_current()
    rep = maintenance.storage_report()
    n_bots = len(_bots())
    try:
        from . import ai
        cat = ai.get_catalog()["systems"]
        n_sys = len(cat)
        cert_hoch = sum(1 for s in cat if s.get("certainty") == "hoch")
    except Exception:
        n_sys, cert_hoch = None, None
    tests_dir = PROJECT_ROOT / "tests"
    has_tests = tests_dir.exists() and any(tests_dir.glob("test_*.py"))
    has_git = (PROJECT_ROOT.parent / ".git").exists() or (PROJECT_ROOT / ".git").exists()

    cats = []
    cats.append(_cat("lernen", "🧠 Lernen & Master", ["meta.py", "master.py"],
                     "ok" if mp else "warn",
                     [f"Master: {'v'+str(mp['version'])+' · Fitness '+str(mp['fitness']) if mp else 'noch nicht trainiert'}",
                      f"{ready}/{len(vals)} Strategien echtgeldreif"],
                     ([] if mp else ["Master-Politik per Trainingsschritt initialisieren."])
                     + ["Master-Stufe 2: Regime-Switching-Ausführung (echte Meta-Strategie) bauen.",
                        "Empirische Regime-Performance stärker gewichten (mehr Bot-Historie sammeln)."]))
    cats.append(_cat("strategien", "📊 Strategien & Gates", ["STRATEGY_PARAMS", "strategy_validations"],
                     "warn" if ready == 0 else "ok",
                     [f"Bester Profit-Faktor: {best_pf if best_pf is not None else '–'} (PF>1 = profitabel)",
                      f"Trade-Bremse aktiv in gelernten Gewinnern: {', '.join(cooldowners) or 'keine'}"],
                     ["Keine Strategie profitabel → strukturelle Overtrader-Fixes (Signal-Filter) + breitere Strategie-Recherche.",
                      "Evolution mit mehr Generationen/Mutationsbreite für hartnäckige Fälle."]))
    cats.append(_cat("daten", "💾 Daten & Gedächtnis", ["stats.py", "tracker.py", "maintenance.py"],
                     "warn" if (rep.get("audit_lines", 0) > 2000 or rep.get("orphan_backtest_bots")) else "ok",
                     [f"DB {rep.get('db_kb')} KB · Snapshots {rep.get('tables', {}).get('snapshots')} · "
                      f"Audit {rep.get('audit_lines')} Zeilen · Karteileichen {len(rep.get('orphan_backtest_bots', []))}",
                      f"Schlüsse kompakt (UPSERT 1/Strategie) · Ledger {rep.get('tables', {}).get('learning_ledger')}"],
                     ["Lifecycle regelmäßig laufen lassen (Verdichtung/Pruning/Audit-Rotation).",
                      "Später: zentrale DB (Postgres/Timescale) + tenant_id (Seams 08b)."]))
    cats.append(_cat("ausfuehrung", "⚙ Ausführung", ["runner.py", "engine.py"], "ok",
                     [f"{n_bots} Bots registriert · lokale Freqtrade-Prozesse · Backtest-Cache aus (--cache none)"],
                     ["Skalierung: Bot-Ausführungsmodell entscheiden (Container-je-Tenant vs. geteilter Pool)."]))
    cats.append(_cat("risiko", "🛡 Risiko & Gates", ["risk.py", "_live_ready"], "ok",
                     ["Echtgeld-Gate: validiert + ≥2 Fenster + Profit-Faktor>1 · globale Caps/DD gesetzt · Demo-Modus"],
                     ["Vor M6: Kill-Switch + globaler DD-Stop scharf testen (Sicherheitskonzept 07)."]))
    cats.append(_cat("recherche", "🔬 Recherche", ["ai.py"],
                     "warn" if (cert_hoch == 0) else "ok",
                     [f"Katalog {n_sys} Systeme · {cert_hoch} mit Certainty 'hoch'" if n_sys is not None else "Katalog n/v"],
                     ["YouTube-Transkript-Ingest + Self-Critique-Tiefe für validiertere Systeme.",
                      "Nur belegt-gute (Gate) Systeme für Demo/Echtgeld vorschlagen."]))
    cats.append(_cat("schnittstelle", "🔌 Schnittstelle & Integration", ["main.py", "integration.py"], "ok",
                     ["API-Versionierung /api/v1 · CORS-Schalter · Owner-Token (default aus) · OpenAPI /docs"],
                     ["Für Multi-User: echte Auth (JWT/OAuth) + Mandanten (tenant_id).",
                      "Komponenten-Schnittstelle für übergeordnetes Verwaltungssystem nutzen (descriptor/state/command)."]))
    cats.append(_cat("betrieb", "🧪 Betrieb & Qualität", ["tests/", "git"],
                     "ok" if (has_tests and has_git) else "warn",
                     [f"Test-Suite: {'vorhanden' if has_tests else 'fehlt'} · Versionskontrolle: {'Git' if has_git else 'keine'}"],
                     ["CI (GitHub Actions) für Tests einrichten."]))

    # Top-Verbesserungen (priorisiert) + nächstes Lern-Ziel
    top = [
        "Strategien profitabel machen: strukturelle Overtrader-Fixes + breitere/validiertere Recherche.",
        "Master-Algorithmus Stufe 2: echte Regime-Switching-Ausführung.",
        "Mehr Bot-Laufzeit → empirisches Regime-Lernen wird belastbar.",
    ]
    learning_target = ("Kern-Engpass: keine Strategie hat PF>1. Hebel mit größtem Effekt = (1) strukturelle "
                       "Entschärfung der Overtrader (Logik, nicht nur Parameter) und (2) bessere Strategie-Quellen "
                       "(Recherche-Tiefe). Der Master verdichtet das automatisch, sobald die Einzelbelege besser werden.")
    health_counts = {"ok": 0, "warn": 0, "gap": 0}
    for c in cats:
        health_counts[c["health"]] = health_counts.get(c["health"], 0) + 1
    return {"ts": datetime.now(timezone.utc).isoformat(), "categories": cats,
            "health_summary": health_counts, "top_improvements": top,
            "learning_target": learning_target,
            "note": "Selbst-Audit aus realem Systemzustand (regelbasiert, proposal-only). "
                    "Wird mit jedem Aufruf neu erhoben; Schlüsse via /api/introspect/collect ins Gedächtnis."}


def self_collect() -> dict:
    """Sammelt die wichtigsten Selbst-Audit-Schlüsse kompakt ins Learning-Ledger ein."""
    a = assess()
    maintenance.record_ledger("self_assessment", "Selbst-Audit",
                              a["learning_target"], {"health": a["health_summary"]})
    for imp in a["top_improvements"][:2]:
        maintenance.record_ledger("self_improvement", "Hebel", imp, {})
    return {"ok": True, "recorded": 3, "health_summary": a["health_summary"]}
