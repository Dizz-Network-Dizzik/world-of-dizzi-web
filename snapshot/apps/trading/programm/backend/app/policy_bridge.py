"""policy_bridge.py — FP-T5: Politik→Hand-Brücke (Gate G-T5; docs/POLICY_HAND_SPEC.md).

Die Master-Politik (``master.derive_policy``: Regime→beste Strategie/Parameter) erreicht die
tatsächlich handelnde MasterMeta-Engine heute nur partiell: Regime + HMM-Konfidenz + Hebel-/
Exposure-Scale (``hmm_regime.json``, D1) und Stakes (``suggested_sizing.json``, FP-2). Die
per-Regime-**Bestauswahl** selbst — „in range bevorzuge Mean-Reversion" — blieb beratend
(MASTERMETA_TIEFENPRUEFUNG Befund 2 / Empfehlung 2).

Dieses Modul schließt die Lücke nach exakt dem FP-2-Muster: das Backend destilliert die Politik
zu einem kleinen, GEKLEMMTEN Payload und schreibt ihn atomar in ``suggested_policy.json``; die
Engine (anderes venv/Prozess, ``master_meta.py``) liest ihn mehrfach gegated (Engine-Opt-in ·
nur dry_run · Frische · ``mode=='apply'``) und setzt ihn in der Sub-Logik-Wahl bzw. in
``custom_stake_amount`` um. Jeder Fehlweg ist fail-safe = heutiges Verhalten.

Klemmkette (normativ, SPEC §2): **T0 Politik → T1 Governor → T2 Konzentration → T3 Sizing.**
Die Politik schlägt vor; Governor/Konzentration können nur VERSCHÄRFEN (Logik-Freeze bei warn,
Degradation auf proposal bei breach), nie lockern; die Stake-Seite kann das Sizing nur DÄMPFEN
(Faktor ≤ 1) — nie über die K4–K6-Klemmen von FP-2 hinaus. Alle Defaults inert ⇒ ohne Opt-in
byte-identisches Verhalten (Suite-Beleg ``tests/test_policy_bridge.py``).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import audit, concentration, governor, jsonstore, master, registry, sizing
from .config import DATA_DIR
from .meta import STRAT_REGIME

STATE_FILE = DATA_DIR / "policy_bridge.json"

# Politik-Bridge: das Backend exportiert die geklemmte Regime→Logik/Stake-Politik in eine Datei,
# die die Engine-Strategie (anderes venv/Prozess) lesen kann (master_meta._policy_levers). Pfad via
# Env TBT_POLICY_FILE überschreibbar — der runner reicht ihn IMMER an Bot-Subprozesse durch
# (analog tracker.REGIME_BRIDGE_FILE / sizing.SIZING_BRIDGE_FILE = single source of truth).
POLICY_BRIDGE_FILE = Path(os.environ.get("TBT_POLICY_FILE") or (DATA_DIR / "suggested_policy.json"))

# Was die Hand real ausführen KANN: die MasterMeta-Engine besitzt je Richtung feste Sub-Logiken
# (Long: Trendfolge-MACD + Mean-Reversion-BB · Short: nur Trendfolge-MACD). Die Politik wählt
# FLOTTEN-Strategien (STRAT_REGIME-Tags trend/range/volatil) — der Tag entscheidet, WELCHE
# Hand-Logik der Bestauswahl entspricht. „volatil" (Breakout) hat KEIN Pendant in der Hand ⇒
# Default bleibt (ehrlich ausgewiesen statt erzwungen); Shorts haben keine MR-Alternative.
DEFAULT_LOGIC = {"trend_up": "trend_macd", "range": "range_bb", "trend_down": "trend_macd_short"}
_TAG_LOGIC_LONG = {"trend": "trend_macd", "range": "range_bb"}   # volatil → None (Default behalten)

_DEFAULTS = {
    # --- Brücke (SPEC §4 — Default AUS ⇒ Datei wird nicht geschrieben, 0 Verhaltensänderung) ---
    "bridge_enabled": False,      # Hauptschalter: Autopilot schreibt suggested_policy.json
    "bridge_mode": "proposal",    # "apply" = Engine DARF anwenden (nur dry_run; G-T5 beantwortet 03.07.)
    "bridge_max_age_s": 25200,    # Engine-Frische-Gate = Autopilot-Takt 6 h + 1 h Puffer (G-T5-Takt-
                                  # Entscheid, SPEC §4: deckt genau EIN Tick-Fenster; schützt weiter
                                  # gegen totes Backend, ohne apply zwischen den Ticks leerlaufen zu lassen)
    # --- Hebel L1–L3 (SPEC §3 — wirken NUR bei mode=='apply' + Engine-Opt-in; alle Default AUS) ---
    "apply_logic": False,         # L1: Sub-Logik-Umschaltung je Regime nach Politik-Bestauswahl
    "apply_stake": False,         # L2: Stake-Dämpfung nach Edge-Konfidenz (Faktor ≤ 1, nie hebeln)
    "gate_unprofitable": False,   # L3: Regime ohne belegten Edge (profitable=False) aussetzen
    "scale_floor": 0.5,           # harte Unterkante der L2-Dämpfung (0.1..1.0; 1.0 = Dämpfung neutral)
}


def get_config() -> dict:
    return {**_DEFAULTS, **(jsonstore.read_json(STATE_FILE, {}) or {})}


def set_config(patch: dict) -> dict:
    s = get_config()
    was_enabled = bool(s.get("bridge_enabled"))
    for k in ("bridge_enabled", "apply_logic", "apply_stake", "gate_unprofitable"):
        if k in patch:
            s[k] = bool(patch[k])
    if patch.get("bridge_mode") in ("proposal", "apply"):
        s["bridge_mode"] = patch["bridge_mode"]
    if "scale_floor" in patch:
        try:
            s["scale_floor"] = float(patch["scale_floor"])
        except (TypeError, ValueError):
            pass
    # Harte Grenzen: die Dämpfung ist ein Faktor in [0.1, 1.0] — die Politik kann die Hand nie
    # hochhebeln (Obergrenze 1.0 ist die G-T5-Vorgabe „nur dämpfen") und nie unter 10 % drücken.
    s["scale_floor"] = min(1.0, max(0.1, float(s["scale_floor"])))
    if "bridge_max_age_s" in patch:
        try:
            s["bridge_max_age_s"] = max(60, int(patch["bridge_max_age_s"]))
        except (TypeError, ValueError):
            pass
    jsonstore.write_atomic(STATE_FILE, s)
    audit.record("policy_bridge_config", **{k: s[k] for k in _DEFAULTS})
    if was_enabled and not s["bridge_enabled"]:
        # Abschalten wirkt SOFORT: sonst läse die Engine die alte apply-Datei bis zum
        # Frische-Gate (≤7 h) weiter (Entwaffnungs-Latenz, FP-T5-Härtung).
        _disarm_bridge()
    return s


def _stake_scale(profitable: bool, confidence: float, floor: float) -> float:
    """T0-Stake-Seite: Dämpfungsfaktor je Regime aus der Politik-Evidenz — IMMER in [floor, 1.0].

    Belegter Edge (validated + PF>1) mit Konfidenz c ⇒ ``floor + (1−floor)·c`` (mehr Beleg → näher
    an 1.0 = konfigurierter Stake). OHNE belegten Edge ⇒ ``floor`` (defensiv halbieren, Default 0.5).
    Monoton in der Konfidenz; kann nie > 1 (nie hochhebeln) und nie < floor (nie aushungern)."""
    edge_conf = max(0.0, min(1.0, confidence)) if profitable else 0.0
    return round(floor + (1.0 - floor) * edge_conf, 4)


def derive_payload(policy: dict, *, governor_severity: str = "ok",
                   concentration_hit: bool = False, cfg: dict | None = None) -> dict:
    """Destilliert die Master-Politik zum Brücken-Payload — REIN/deterministisch (Property-Tests).

    Klemmen in dieser Funktion (Reihenfolge normativ, SPEC §2):
    - **T0 Politik:** je Regime Bestauswahl → Hand-Logik via Tag-Map (unbekannt/volatil ⇒ Default,
      ``switched=False``), ``stake_scale`` hart in [scale_floor, 1.0], ``enabled`` nur relevant
      wenn Hebel L3 gesetzt.
    - **T1 Governor:** ``breach`` ⇒ ``mode='proposal'`` (Hand wendet NICHTS an, analog FP-2 P5).
      ``warn`` ⇒ **Logik-Freeze** (alle Logiken = Default): eine Warn-Lage ist kein Moment für
      Verhaltens-Churn; die rein defensive Stake-Dämpfung (≤1) bleibt anwendbar.
    - **T2 Konzentration:** warn UND MasterMeta-Assets betroffen ⇒ ebenfalls Logik-Freeze
      (strukturelle Klumpen-Lage — umschalten nein, dämpfen ja).
    - **T3 Sizing:** findet ENGINE-seitig statt (Faktor multipliziert den Sizing-Grundwert und
      wird zuletzt von freqtrades [min, max] geklemmt) — hier nur dokumentiert.
    """
    cfg = cfg or get_config()
    floor = min(1.0, max(0.1, float(cfg.get("scale_floor", 0.5))))
    gate_unprof = bool(cfg.get("gate_unprofitable"))
    freeze = governor_severity in ("warn", "breach") or concentration_hit
    allocs = (policy or {}).get("allocations") or {}

    regimes: dict[str, dict] = {}
    for reg, default_logic in DEFAULT_LOGIC.items():
        a = allocs.get(reg) or {}
        strat = a.get("strategy")
        tag = STRAT_REGIME.get(strat)
        note = None
        if reg == "trend_down":
            # Die Hand hat genau EINE Short-Logik (MACD-Trendfolge) — eine range/volatil-getaggte
            # Bestauswahl ist short-seitig nicht umsetzbar. Ehrlich ausweisen statt so tun als ob.
            logic = default_logic
            if tag and _TAG_LOGIC_LONG.get(tag) not in (None, "trend_macd"):
                note = f"kein Short-Pendant für Tag „{tag}“ — Default-Logik bleibt"
        else:
            logic = _TAG_LOGIC_LONG.get(tag) or default_logic
            if tag == "volatil":
                note = "Tag „volatil“ (Breakout) hat kein Hand-Pendant — Default-Logik bleibt"
        if freeze:
            logic = default_logic
        profitable = bool(a.get("profitable"))
        try:
            conf = float(a.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        regimes[reg] = {
            "strategy": strat, "tag": tag, "logic": logic, "default_logic": default_logic,
            "switched": logic != default_logic,
            "enabled": (True if not gate_unprof else profitable),
            "profitable": profitable, "expected_pf": a.get("expected_pf"),
            "confidence": round(conf, 3),
            "stake_scale": _stake_scale(profitable, conf, floor),
            "params": a.get("params"),
            **({"note": note} if note else {}),
        }

    mode = "apply" if (str(cfg.get("bridge_mode")) == "apply"
                       and governor_severity != "breach") else "proposal"

    active_reg = ((policy or {}).get("active_regime") or {}).get("regime")
    active = None
    if active_reg in regimes:
        ar = regimes[active_reg]
        conf = ((policy or {}).get("active_regime") or {}).get("confidence")
        active = {"regime": active_reg, "confidence": conf, "strategy": ar["strategy"],
                  "logic": ar["logic"], "stake_scale": ar["stake_scale"],
                  "enabled": ar["enabled"]}

    ens = (policy or {}).get("ensemble") or {}
    return {
        "ts": int(time.time() * 1000),
        "mode": mode,
        "governor_severity": governor_severity,
        "concentration_hit": bool(concentration_hit),
        "logic_frozen": bool(freeze),
        "levers": {"apply_logic": bool(cfg.get("apply_logic")),
                   "apply_stake": bool(cfg.get("apply_stake")),
                   "gate_unprofitable": gate_unprof},
        "scale_floor": floor,
        "active": active,
        "regimes": regimes,
        "ensemble": {"dir_share": ens.get("dir_share"), "mn_share": ens.get("mn_share")},
        "suggested_exposure": ((policy or {}).get("fundamental") or {}).get("suggested_exposure"),
    }


def _master_assets() -> set[str]:
    """Basis-Assets des MasterMeta-Bots (für die T2-Konzentrations-Klemme). Defensiv: die
    bekannten Majors, falls Registry/Bot nicht lesbar (MasterMeta handelt BTC/ETH/SOL)."""
    try:
        b = registry.get_bot(registry.MASTER_BOT_ID)
        assets = {a for a in (concentration._base_asset(p)
                              for p in (getattr(b, "pairs", None) or [])) if a}
        return assets or {"BTC", "ETH", "SOL"}
    except Exception:
        return {"BTC", "ETH", "SOL"}


def _concentration_hit(conc: dict) -> bool:
    """T2-Input: Konzentrations-warn, die die Assets der Hand berührt (Klumpen ⇒ Logik-Freeze)."""
    if (conc or {}).get("severity") != "warn":
        return False
    return bool(sizing._overexposed_assets(conc) & _master_assets())


def _risk_context() -> tuple[str, bool]:
    """Governor-Schwere + Konzentrations-Treffer, beide defensiv gelesen (Fehler ⇒ ok/kein Hit —
    die Brücke ist Empfehlung, nicht Wächter; der echte Wächter bleibt der Governor selbst)."""
    try:
        sev = str((governor.evaluate(use_cache=True) or {}).get("severity") or "ok")
    except Exception:
        sev = "ok"
    try:
        hit = _concentration_hit(concentration.analyze())
    except Exception:
        hit = False
    return sev, hit


def _disarm_bridge() -> None:
    """Schreibt eine neutrale Disarm-Payload (``mode='proposal'``) atomar in
    POLICY_BRIDGE_FILE. Die Engine (``master_meta._policy_levers``) wendet NUR
    ``mode=='apply'`` an ⇒ das entwaffnet sie sofort; ohne diesen Schritt läse sie
    eine alte apply-Datei bis zum Frische-Gate (Default 25200 s ≈ 7 h) weiter."""
    jsonstore.write_atomic(POLICY_BRIDGE_FILE, {
        "ts": int(time.time() * 1000),
        "mode": "proposal",
        "disabled": True,
        "reason": "bridge_enabled=false — Politik-Brücke deaktiviert (sofort entwaffnet)",
    })


def write_bridge_auto(policy: dict | None = None) -> dict:
    """Schreibt die Politik-Bridge ``suggested_policy.json`` (Autopilot-Tick, nach dem Governor).

    Opt-in-Kette Backend-seitig: ``bridge_enabled`` False (Default) ⇒ es wird KEINE aktive
    Politik geschrieben; eine noch scharfe (mode='apply') Altdatei wird jedoch neutralisiert
    (Entwaffnungs-Latenz-Härtung — deckt den Fall ab, dass beim Abschalten kein set_config-
    Disarm lief, z. B. Prozess-Neustart). ``bridge_mode='apply'`` degradiert bei Governor-
    **breach** automatisch auf ``proposal``; Governor-**warn**/Konzentrations-Treffer frieren
    die Logik-Umschaltung ein (T1/T2, SPEC §2). Atomar via ``jsonstore.write_atomic``. Die
    Engine hat ihre eigenen Gates (Opt-in-Param + dry_run + Frische + Hard-Klemme ≤1, SPEC §4)."""
    cfg = get_config()
    if not cfg.get("bridge_enabled"):
        try:  # idempotent: nur eine WIRKLICH scharfe Altdatei entwaffnen, sonst nichts tun
            if POLICY_BRIDGE_FILE.exists() and \
                    (jsonstore.read_json(POLICY_BRIDGE_FILE, {}) or {}).get("mode") == "apply":
                _disarm_bridge()
                return {"written": False, "disarmed": True,
                        "reason": "bridge_enabled=false — alte apply-Politik entwaffnet"}
        except Exception:
            pass
        return {"written": False, "reason": "bridge_enabled=false (Default) — Politik-Brücke aus"}
    if policy is None:
        policy = master.derive_policy()
    sev, hit = _risk_context()
    payload = derive_payload(policy, governor_severity=sev, concentration_hit=hit, cfg=cfg)
    jsonstore.write_atomic(POLICY_BRIDGE_FILE, payload)
    degraded = (str(cfg.get("bridge_mode")) == "apply" and payload["mode"] == "proposal")
    return {"written": True, "mode": payload["mode"], "governor_severity": sev,
            "concentration_hit": hit, "logic_frozen": payload["logic_frozen"],
            "degraded": degraded, "active": payload.get("active"),
            "file": str(POLICY_BRIDGE_FILE)}


def status() -> dict:
    """Konfiguration + Live-Vorschau des Payloads (ohne zu schreiben) — für UI/Transparenz."""
    cfg = get_config()
    try:
        sev, hit = _risk_context()
        preview = derive_payload(master.derive_policy(), governor_severity=sev,
                                 concentration_hit=hit, cfg=cfg)
    except Exception as exc:
        preview = {"error": f"{type(exc).__name__}: {exc}"}
    return {"config": {k: cfg[k] for k in _DEFAULTS},
            "file": str(POLICY_BRIDGE_FILE), "written": POLICY_BRIDGE_FILE.exists(),
            "preview": preview,
            "gate": "G-T5 beantwortet 03.07.2026 (SPEC §8): Stufe 1+2 GO, L3 an — scharf erst mit "
                    "beiden Schlüsseln (Backend-Config + Engine-Opt-in nach gegateten Neustarts)",
            "explainer": "Politik→Hand-Brücke (FP-T5): destilliert die Master-Bestauswahl je Regime "
                         "zu Logik-Wahl + Stake-Dämpfung für die MasterMeta-Engine. Klemmkette "
                         "Politik→Governor→Konzentration→Sizing; alle Hebel opt-in, nur dry_run, "
                         "Faktor ≤ 1 — Details docs/POLICY_HAND_SPEC.md."}
