"""mn_learn.py — generischer **anchored** Walk-Forward-Optimierer für die markt-neutralen
Engines (CSM / Pairs / StatArb). Proposal-only (wendet nichts automatisch an).

Anchored-Prinzip: die Preis-Historie wird in ``windows`` aufeinanderfolgende Zeitfenster geteilt;
die Kandidaten-**Selektion** läuft ausschließlich auf den älteren Fenstern (bester Ø-Sharpe,
Tie-break robusterer Worst-Case), das **jüngste Fenster bleibt ungesehen** und prüft EINMAL nur
den Gewinner (``oos_sharpe``/``oos_validated``). Würden alle Fenster zugleich selektieren und
validieren, wäre der Gewinner ein best-of-N auf den Validierungsdaten (Selektions-Bias).
Reines Python, dependency-leicht, testbar.
"""

from __future__ import annotations

from itertools import product


def equal_folds(T: int, windows: int) -> list[tuple[int, int]]:
    """Teilt [0, T) in ``windows`` etwa gleich große, aufeinanderfolgende Fenster.
    Reduziert ``windows``, falls die Fenster sonst zu klein würden."""
    windows = max(1, int(windows))
    while windows > 1 and T // windows < 90:   # je Fenster mind. ~90 Tage
        windows -= 1
    step = T // windows
    folds = []
    for k in range(windows):
        a = k * step
        b = (k + 1) * step if k < windows - 1 else T
        folds.append((a, b))
    return folds


def grid(options: dict) -> list[dict]:
    """Karthesisches Produkt eines Parameter-Rasters ``{name: [werte...]}`` -> Liste von cfgs."""
    keys = list(options.keys())
    out = []
    for combo in product(*[options[k] for k in keys]):
        out.append({k: v for k, v in zip(keys, combo)})
    return out


def walk_forward(eval_fn, T: int, candidates: list[dict], windows: int = 3,
                 baseline: dict | None = None) -> dict:
    """``eval_fn(cfg, a, b) -> float | None`` bewertet einen Kandidaten auf dem Zeit-Slice [a,b)
    (Sharpe; None bei zu wenig Daten).

    **Anchored:** Selektion (bester Ø-Sharpe, Tie-break Worst-Case) NUR auf den älteren Folds;
    der jüngste Fold bleibt ungesehen und testet einmalig den Gewinner → ``oos_sharpe`` +
    ``oos_validated`` (Sharpe > 0). Bei nur einem Fold (zu wenig Historie) entfällt der
    OOS-Test (``oos_validated`` = None, kein Validierungs-Anspruch).

    **Ehrlichkeits-Gate gegen Regressionen:** Wird ``baseline`` (= aktuelle Engine-Config)
    übergeben, wird sie auf DEMSELBEN ungesehenen OOS-Fold bewertet (``baseline_oos_sharpe``).
    Nur wenn der Gewinner die laufende Config dort schlägt, ist ``improved_vs_current`` True und
    ``apply_recommended`` (OOS-validiert UND echte Verbesserung) gesetzt. So labelt der
    Optimierer keinen ökonomisch schlechteren Parametersatz als anwendbaren „Gewinner" —
    ein auf älteren Folds bester Kandidat kann auf den jüngsten Daten schwächer als der
    Status quo sein (empirisch beobachtet: CSM-Winner OOS-positiv, aber Voll-Historie schwächer)."""
    folds = equal_folds(T, windows)
    sel_folds = folds[:-1] if len(folds) > 1 else folds
    test_fold = folds[-1] if len(folds) > 1 else None
    results = []
    for cfg in candidates:
        scores = []
        for a, b in sel_folds:
            try:
                s = eval_fn(cfg, a, b)
            except Exception:
                s = None
            if s is not None:
                scores.append(float(s))
        avg = round(sum(scores) / len(scores), 3) if scores else None
        worst = round(min(scores), 3) if scores else None
        results.append({"params": cfg, "avg_sharpe": avg, "worst_sharpe": worst, "windows": len(scores)})
    valid = [r for r in results if r["avg_sharpe"] is not None]
    winner = max(valid, key=lambda r: (r["avg_sharpe"], r["worst_sharpe"])) if valid else None
    if winner is not None:
        winner = dict(winner)
        if test_fold is not None:
            try:
                oos = eval_fn(winner["params"], *test_fold)
            except Exception:
                oos = None
            winner["oos_sharpe"] = round(float(oos), 3) if oos is not None else None
            winner["oos_validated"] = bool(oos is not None and float(oos) > 0)
            # Ehrlichkeits-Gate: schlägt der Gewinner die laufende Config auf dem OOS-Fold?
            if baseline is not None:
                try:
                    base_oos = eval_fn(baseline, *test_fold)
                except Exception:
                    base_oos = None
                winner["baseline_oos_sharpe"] = round(float(base_oos), 3) if base_oos is not None else None
                improved = bool(oos is not None and base_oos is not None and float(oos) > float(base_oos))
                winner["improved_vs_current"] = improved
                winner["apply_recommended"] = bool(winner["oos_validated"] and improved)
        else:
            winner["oos_sharpe"] = None
            winner["oos_validated"] = None
            if baseline is not None:
                winner["baseline_oos_sharpe"] = None
                winner["improved_vs_current"] = None
                winner["apply_recommended"] = False
    results.sort(key=lambda r: (r["avg_sharpe"] is not None, r["avg_sharpe"] or -1e9), reverse=True)
    return {"folds": len(folds), "selection_folds": len(sel_folds),
            "candidates": len(candidates), "results": results, "winner": winner,
            "note": "Proposal-only, anchored: Selektion nach Ø-Sharpe auf den älteren Folds; der "
                    "jüngste Fold testet ungesehen nur den Gewinner (oos_sharpe/oos_validated). "
                    "apply_recommended verlangt zusätzlich, dass der Gewinner die laufende Config "
                    "auf dem OOS-Fold schlägt (keine Regressions-Vorschläge). Anwenden = Engine-Config setzen."}
