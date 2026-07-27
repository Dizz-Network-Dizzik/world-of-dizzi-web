"""universe.py — kuratiertes, gestreutes Coin-Universum (Single Source of Truth für „Pairs streuen").

**Problem (bis 2026-06-10):** praktisch alle Bots handelten dieselben drei Majors (BTC/ETH/SOL) → ein
versteckter Korrelations-Klumpen auf Portfolio-Ebene (siehe ``concentration.py``). Fällt „der
Kryptomarkt", trifft es alle Bots gleichzeitig.

**Lösung („Pairs streuen"):** ein kuratiertes, nach Liquidität gestaffeltes Universum liquider
**Bitget-USDT-Perpetuals**, aus dem Freqtrade je Bot die nach Handelsvolumen liquidesten Pairs
**dynamisch** auswählt (``VolumePairList``) — begrenzt auf eine **horizont-passende Anzahl**. So wird
breit gestreut, aber **kontrolliert und erklärbar** (kein wahlloses Top-N über alle Märkte): Scalping
braucht die liquidesten Coins (enge Spreads), Swing verträgt mehr Breite.

Dieses Modul ist die EINE Wahrheit: ``registry`` (Config-Erzeugung), ``concentration`` (Analyse), die
KI-/Recherche-Schicht (``ai``) und das UI beziehen Kandidaten + Anzahl + Anzeige-Label von hier. Keine
Imports aus app-Modulen → zyklenfrei.
"""
from __future__ import annotations

# --- Kuratiertes Kandidaten-Universum (Basis-Symbole, ohne Quote/Suffix) ----------------------------
# Gestaffelt nach Liquidität/Marktkapitalisierung. Alle sind etablierte, liquide Bitget-USDT-Perps
# (Symbole gegen das reale CSM-Volumen-Universum geprüft). Tunbar — eine Erweiterung wirkt überall.
TIER1 = ["BTC", "ETH", "SOL", "XRP", "DOGE"]     # höchste Liquidität → auch fürs Scalping sauber
TIER2 = ["ADA", "AVAX", "LINK", "LTC", "BCH"]    # große Caps
TIER3 = ["DOT", "POL", "NEAR", "ATOM"]           # mid-caps, breitere Streuung
FULL = TIER1 + TIER2 + TIER3                     # 14 Coins

# Horizont → {Kandidaten-Symbole, number_assets}. ``number_assets`` ist die Obergrenze, die
# ``VolumePairList`` aus den Kandidaten nach Volumen tatsächlich auswählt (< Kandidaten ⇒ echte
# dynamische Auswahl). Scalping bleibt liquide (kleiner, T1+T2-Pool); Swing nutzt die volle Breite.
_HORIZON: dict[str, dict] = {
    "scalping": {"symbols": TIER1 + TIER2, "number_assets": 5},
    "intraday": {"symbols": FULL,          "number_assets": 8},
    "swing":    {"symbols": FULL,          "number_assets": 10},
}
_DEFAULT_HORIZON = "intraday"


def base_asset(pair: str) -> str:
    """'BTC/USDT:USDT' → 'BTC', 'ETH/USDT' → 'ETH'."""
    return (pair or "").split("/", 1)[0].strip().upper()


def to_pairs(symbols: list[str], trading_mode: str = "futures") -> list[str]:
    """Basis-Symbole ins Exchange-Pair-Format bringen (Futures: ':USDT'-Suffix; idempotent für Pairs)."""
    out: list[str] = []
    for s in symbols or []:
        s = (s or "").strip().upper()
        if not s:
            continue
        if "/" in s:                       # bereits ein Pair → durchreichen (ggf. Futures-Suffix)
            out.append(s if (trading_mode != "futures" or ":" in s) else f"{s}:{s.split('/', 1)[1]}")
            continue
        out.append(f"{s}/USDT:USDT" if trading_mode == "futures" else f"{s}/USDT")
    return out


def _spec(horizon: str | None) -> dict:
    return _HORIZON.get(horizon or "", _HORIZON[_DEFAULT_HORIZON])


def candidates_for(horizon: str | None, trading_mode: str = "futures") -> list[str]:
    """Kandidaten-Pairs (Whitelist) für einen Horizont — das gestreute Universum, aus dem dynamisch
    ausgewählt wird. Wird als ``bot.pairs`` gespeichert, damit die Konzentrations-Analyse die volle
    Streuung sieht."""
    return to_pairs(_spec(horizon)["symbols"], trading_mode)


def number_assets_for(horizon: str | None) -> int:
    """Wie viele der Kandidaten Freqtrade nach Volumen tatsächlich gleichzeitig hält (dynamischer Deckel)."""
    return int(_spec(horizon)["number_assets"])


# Liquiditäts-Guard: ein Pair fliegt raus, wenn der relative Bid/Ask-Spread diese Schwelle reißt.
# Bewusst locker (0,5 %): für die kuratierten, liquiden Majors/Large-Caps praktisch nie bindend — greift
# nur bei akuter Illiquidität/Marktstress (Schutz v. a. fürs spread-empfindliche Scalping). Nutzt die
# ohnehin für VolumePairList geholten Ticker → kaum zusätzliche API-Last.
_MAX_SPREAD_RATIO = 0.005


def pairlists_for(horizon: str | None) -> list[dict]:
    """Freqtrade-``pairlists``-Kette für den dynamischen, volumengerankten Modus:
    ``StaticPairList`` lädt das kuratierte Kandidaten-Universum (aus ``pair_whitelist``), ``VolumePairList``
    rankt es nach 24h-Quote-Volumen und behält die liquidesten ``number_assets`` Coins, ``SpreadFilter``
    wirft illiquide Pairs mit zu weitem Spread raus (Ausführungs-/Slippage-Schutz). Refresh alle 30 min.
    """
    return [
        {"method": "StaticPairList"},
        {"method": "VolumePairList", "number_assets": number_assets_for(horizon),
         "sort_key": "quoteVolume", "min_value": 0, "refresh_period": 1800},
        {"method": "SpreadFilter", "max_spread_ratio": _MAX_SPREAD_RATIO},
    ]


def label(horizon: str | None, trading_mode: str = "futures") -> dict:
    """Kompaktes Anzeige-/Erklär-Objekt für UI + KI: Anzahl, Kandidaten, Basis-Symbole, Klartext."""
    cands = candidates_for(horizon, trading_mode)
    n = number_assets_for(horizon)
    bases = [base_asset(p) for p in cands]
    return {
        "horizon": horizon or _DEFAULT_HORIZON,
        "mode": "dynamic",
        "number_assets": n,
        "candidate_count": len(cands),
        "candidates": cands,
        "bases": bases,
        "text": f"Dynamisch: Top-{n} nach Volumen aus {len(cands)} Coins",
    }


def model() -> dict:
    """Gesamtmodell des Universums — für ``GET /api/universe`` (UI + Recherchetool)."""
    return {
        "method": "dynamic_volume",
        "description": "Kuratiertes, liquiditäts-gestaffeltes Bitget-USDT-Perp-Universum; Freqtrade "
                       "wählt je Bot die volumenstärksten Coins dynamisch aus (horizont-gedeckelt).",
        "tiers": {"tier1_majors": TIER1, "tier2_large": TIER2, "tier3_mid": TIER3},
        "candidate_count": len(FULL),
        "horizons": {h: label(h) for h in ("scalping", "intraday", "swing")},
    }
