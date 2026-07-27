"""concentration.py — Korrelations-/Konzentrations-Bewusstsein über die ganze Flotte (P2).

Problem: fast alle Futures-Bots handeln BTC/ETH/SOL. Einzeln betrachtet sieht das harmlos aus — auf
**Portfolio-Ebene** ist es ein versteckter Klumpen: stark korrelierte Assets bündeln das Gesamt-Risiko.
Fällt „der Kryptomarkt", trifft es praktisch alle Bots gleichzeitig.

Dieses Modul macht den Klumpen sichtbar und messbar:
- **Exposure je Basis-Asset** (BTC/ETH/SOL/…), gewichtet mit der Notional-Kapazität jedes Bots
  (``stake × max_open_trades × Hebel``), gleichmäßig auf die Basis-Assets des Bots verteilt.
- **HHI** (Herfindahl-Hirschman-Index) als Konzentrations-Maß (0–10 000; höher = konzentrierter).
- **Korrelations-Cluster**: korrelierte Assets werden zu Gruppen zusammengefasst (Default „Krypto-Majors"
  = BTC/ETH/SOL). Der **kombinierte** Cluster-Anteil ist das eigentliche Klumpenrisiko.
- **Deckel-Flags + Streuungs-Hinweise**, wenn ein Asset oder ein Cluster die Schwelle reißt.

Read-only/Analyse — es wird nichts gehandelt oder verändert. Der Governor (P1) zieht das Ergebnis als
zusätzliches **Frühwarn-Signal** heran (Konzentration ist strukturelles, kein akutes Risiko → Warnung +
Streuungs-Empfehlung, kein automatisches Pausieren). 0 Risiko (Demo).
"""
from __future__ import annotations

from . import jsonstore, registry, stats, universe
from .config import DATA_DIR

STATE_FILE = DATA_DIR / "concentration.json"

# Korrelierte Gruppen: Default fasst die hochkorrelierten Krypto-Majors zusammen. Tunbar via set_config.
_DEFAULT_CLUSTERS = {"Krypto-Majors": ["BTC", "ETH", "SOL"]}
_DEFAULTS = {
    "enabled": True,
    "max_asset_share_pct": 50.0,    # ein einzelnes Basis-Asset darf max. so viel Exposure stellen
    "max_cluster_share_pct": 85.0,  # eine korrelierte Gruppe darf max. so viel Exposure stellen
    "clusters": _DEFAULT_CLUSTERS,
}


def get_config() -> dict:
    cfg = {**_DEFAULTS, **(jsonstore.read_json(STATE_FILE, {}) or {})}
    if not isinstance(cfg.get("clusters"), dict) or not cfg["clusters"]:
        cfg["clusters"] = dict(_DEFAULT_CLUSTERS)
    return cfg


def set_config(patch: dict) -> dict:
    s = get_config()
    for k in ("max_asset_share_pct", "max_cluster_share_pct"):
        if k in patch:
            try:
                s[k] = float(patch[k])
            except (TypeError, ValueError):
                pass
    if "enabled" in patch:
        s["enabled"] = bool(patch["enabled"])
    if isinstance(patch.get("clusters"), dict) and patch["clusters"]:
        # nur saubere {Name: [ASSETS]}-Einträge übernehmen
        clean = {}
        for name, assets in patch["clusters"].items():
            if isinstance(assets, list):
                syms = [str(a).upper() for a in assets if str(a).strip()]
                if syms:
                    clean[str(name)] = syms
        if clean:
            s["clusters"] = clean
    jsonstore.write_atomic(STATE_FILE, s)
    return s


def _base_asset(pair: str) -> str | None:
    """Basis-Asset eines Pairs: 'BTC/USDT:USDT' → 'BTC', 'ETH/USDT' → 'ETH'."""
    if not pair or "/" not in pair:
        return None
    return pair.split("/", 1)[0].strip().upper() or None


# Hebel je Strategie mit Abweichung vom Modus-Default (Quelle der Wahrheit:
# main.IMPLEMENTED_STRATEGIES — hier bewusst ohne Import gespiegelt, um keinen Zyklus zu erzeugen;
# diese Werte sind stabil. Default Futures 3×; MasterMeta via opt_params). Die ehemaligen Spot-Strategien
# laufen auch nach der Futures-Migration real mit Hebel 1 (kein leverage()-Callback) → explizit 1.
_STRATEGY_LEVERAGE = {
    "SessionOpenBreakout": 2.0,
    "TrendFollowEma": 1.0, "MeanReversionRsi": 1.0, "MomentumMacd": 1.0,
    "GridRange": 1.0, "DcaDip": 1.0,
}


def _bot_leverage(bot) -> float:
    """Hebel-Schätzung je Bot (konsistent mit der App): MasterMeta via opt_params.base_leverage,
    sonst je Strategie (Sonderfälle in ``_STRATEGY_LEVERAGE``), sonst Modus-Default Futures 3× / Spot 1×.
    Exposure-Proxy — keine exakte Live-Hebelwirkung."""
    op = getattr(bot, "opt_params", None) or {}
    try:
        if op.get("base_leverage"):
            return max(1.0, float(op["base_leverage"]))
    except (TypeError, ValueError):
        pass
    strat = getattr(bot, "strategy", "")
    if strat in _STRATEGY_LEVERAGE:
        return _STRATEGY_LEVERAGE[strat]
    return 3.0 if getattr(bot, "trading_mode", "spot") == "futures" else 1.0


def _bot_notional(bot) -> float:
    """Notional-Kapazität eines Bots: stake × max_open_trades × Hebel (Exposure-Obergrenze)."""
    stake = float(getattr(bot, "stake_amount", 0.0) or 0.0)
    mot = int(getattr(bot, "max_open_trades", 1) or 1)
    return stake * max(1, mot) * _bot_leverage(bot)


def _live_exposure(bots: list) -> tuple[dict, dict, int]:
    """Exposure je Basis-Asset aus den TATSÄCHLICH offenen Positionen (Trade-DBs).
    Returns (exposure, bot_count, n_open_trades). Das ist das ehrliche Klumpenrisiko."""
    exposure: dict[str, float] = {}
    bot_count: dict[str, int] = {}
    seen_bot: dict[str, set] = {}
    n_open = 0
    for b in bots:
        try:
            pos = stats.open_positions(b.id)
        except Exception:
            pos = []
        for p in pos:
            a = _base_asset(p.get("pair", ""))
            notional = float(p.get("notional") or 0.0)
            if not a or notional <= 0:
                continue
            n_open += 1
            exposure[a] = exposure.get(a, 0.0) + notional
            if a not in seen_bot.setdefault(b.id, set()):
                seen_bot[b.id].add(a)
                bot_count[a] = bot_count.get(a, 0) + 1
    return exposure, bot_count, n_open


def _capacity_exposure(bots: list) -> tuple[dict, dict]:
    """Exposure-Schätzung aus der Notional-KAPAZITÄT je Bot (stake×max_trades×Hebel), verteilt auf
    die voraussichtlich gehandelten Assets. Fallback, solange (noch) keine Positionen offen sind —
    bei dynamischen Bots auf die ``number_assets`` volumenstärksten Kandidaten gedeckelt (ehrlicher
    als alle 14 Kandidaten, da Tier-1-Majors zuerst gewählt werden)."""
    exposure: dict[str, float] = {}
    bot_count: dict[str, int] = {}
    for b in bots:
        assets, seen = [], set()
        for p in (getattr(b, "pairs", None) or []):
            a = _base_asset(p)
            if a and a not in seen:
                seen.add(a)
                assets.append(a)
        if not assets:
            continue
        if getattr(b, "pair_mode", "static") == "dynamic":
            n = universe.number_assets_for(getattr(b, "horizon", None))
            if n > 0:
                assets = assets[:n]
        per = _bot_notional(b) / len(assets)
        for a in assets:
            exposure[a] = exposure.get(a, 0.0) + per
            bot_count[a] = bot_count.get(a, 0) + 1
    return exposure, bot_count


def analyze() -> dict:
    """Konzentrations-Analyse über alle Bots (read-only). Liefert Exposure je Asset, HHI,
    Cluster-Anteile, Deckel-Flags + Streuungs-Hinweise und eine Schwere (``ok``/``warn``).

    **Primär aus den ECHTEN offenen Positionen** (``mode='live'``) — misst das tatsächlich gehaltene
    Klumpenrisiko. Solange keine Position offen ist, fällt es auf die Kapazitäts-Schätzung
    (``mode='capacity'``, zulässiges Universum) zurück, damit das Panel nicht leer bleibt."""
    cfg = get_config()
    bots = list(registry.list_bots())

    exposure, bot_count, n_open = _live_exposure(bots)
    if n_open > 0:
        mode = "live"
    else:
        exposure, bot_count = _capacity_exposure(bots)
        mode = "capacity"

    total = sum(exposure.values())
    assets_out: list[dict] = []
    hhi = 0.0
    for a, exp in exposure.items():
        share = (exp / total * 100.0) if total else 0.0
        hhi += share * share
        assets_out.append({"asset": a, "exposure": round(exp, 2), "share_pct": round(share, 2),
                           "bots": bot_count.get(a, 0)})
    assets_out.sort(key=lambda r: r["share_pct"], reverse=True)

    # Korrelations-Cluster: kombinierter Anteil je Gruppe (das eigentliche Klumpenrisiko).
    share_by_asset = {r["asset"]: r["share_pct"] for r in assets_out}
    clusters_out: list[dict] = []
    cap_cluster = float(cfg["max_cluster_share_pct"])
    for name, members in (cfg.get("clusters") or {}).items():
        present = [m for m in members if m in share_by_asset]
        cshare = round(sum(share_by_asset[m] for m in present), 2)
        clusters_out.append({"name": name, "assets": list(members), "present": present,
                             "share_pct": cshare, "cap_pct": cap_cluster, "over": cshare > cap_cluster})
    clusters_out.sort(key=lambda c: c["share_pct"], reverse=True)

    top = assets_out[0] if assets_out else None
    cap_asset = float(cfg["max_asset_share_pct"])
    flags: list[str] = []
    suggestions: list[str] = []
    if top and top["share_pct"] > cap_asset:
        flags.append(f"{top['asset']} stellt {top['share_pct']:.0f}% des Exposure (Deckel {cap_asset:.0f}%)")
        suggestions.append(f"Exposure auf {top['asset']} senken oder auf weitere, schwächer korrelierte "
                           f"Assets streuen.")
    for c in clusters_out:
        if c["over"]:
            flags.append('Cluster „{}" {:.0f}% > Deckel {:.0f}%'.format(
                c["name"], c["share_pct"], c["cap_pct"]))
            suggestions.append('Korrelierter Klumpen „{}" zu groß — Pairs außerhalb der Gruppe ({}) '
                               'aufnehmen, um die Gesamt-Korrelation zu senken.'.format(
                                   c["name"], "/".join(c["assets"])))

    severity = "warn" if (cfg.get("enabled") and flags) else "ok"
    return {
        "severity": severity,
        "mode": mode,                 # 'live' = echte offene Positionen, 'capacity' = Universum-Schätzung
        "open_trades": n_open,
        "mode_note": ("Aus den tatsächlich offenen Positionen (echtes Klumpenrisiko)." if mode == "live"
                      else "Schätzung aus der Notional-Kapazität (zulässiges Universum) — noch keine "
                           "Position offen; wird live, sobald Trades laufen."),
        "total_exposure": round(total, 2),
        "hhi": round(hhi, 1),
        "n_assets": len(assets_out),
        "top_asset": ({"asset": top["asset"], "share_pct": top["share_pct"]} if top else None),
        "max_asset_share_pct": (top["share_pct"] if top else 0.0),
        "assets": assets_out,
        "clusters": clusters_out,
        "flags": flags,
        "suggestions": suggestions,
        "config": {"enabled": cfg["enabled"], "max_asset_share_pct": cap_asset,
                   "max_cluster_share_pct": cap_cluster, "clusters": cfg.get("clusters")},
    }
