"""Proaktiver Analyst (Phase 4 Teil C).

Zwei Stufen, bewusst getrennt:
1. REGELN (deterministisch, getestet): vergleichen L4-Schnappschüsse und
   erzeugen Meldungen (Regime-Wechsel, Governor-Eingriff, ROI-Rutsch).
   Kein LLM — Zuverlässigkeit vor Eloquenz.
2. VORSCHLÄGE (LLM, 1×/Tag): das lokale Modell liest die Beobachtungs-Serie
   und formuliert 0–2 Verbesserungsvorschläge (severity='vorschlag').

Vorschläge gehen AN DEN NUTZER (Glocke im UI). Die formale Einreichung in
die Proposal-Gates des Trading Bots braucht dort einen Annahme-Endpoint —
vorbereiteter Anschluss, wird in einer Trading-Bot-Session gebaut
(Systemübersicht §4). Bis dahin: beobachten + vorschlagen, nie eingreifen.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, RootModel

from .. import db
from . import observe, providers

ROI_DROP_WARN_PP = 0.5      # Prozentpunkte Verschlechterung binnen ~48 h
DEDUP_HOURS = 12            # gleiche Meldung nicht doppelt innerhalb dieses Fensters


# Vorschlags-Schema (docs/50 P2.1): EINE Quelle für format= (constrained decoding)
# UND Validierung — statt dict-Schema + json.loads + Hand-isinstance.
class _Vorschlag(BaseModel):
    titel: str = ""
    begruendung: str = ""


_Vorschlaege = RootModel[list[_Vorschlag]]


# --- Meldungen (CRUD) ---------------------------------------------------------

def add_notice(user_id: str, source: str, severity: str, title: str, detail: str) -> bool:
    conn = db.get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=DEDUP_HOURS)).isoformat(timespec="seconds")
    dup = conn.execute(
        "SELECT 1 FROM notices WHERE user_id=? AND title=? AND created_at>=? AND deleted_at IS NULL",
        (user_id, title, cutoff),
    ).fetchone()
    if dup:
        return False
    conn.execute(
        "INSERT INTO notices (id, user_id, source, severity, title, detail, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (db.new_id(), user_id, source, severity, title, detail, db.now_iso()),
    )
    conn.commit()
    db.audit(user_id, "ki", "notice_created", {"severity": severity, "title": title})
    return True


def notices(user_id: str, limit: int = 50, unread_only: bool = False) -> list[dict[str, Any]]:
    q = ("SELECT id, source, severity, title, detail, created_at, read_at FROM notices "
         "WHERE user_id=? AND deleted_at IS NULL")
    if unread_only:
        q += " AND read_at IS NULL"
    q += " ORDER BY created_at DESC LIMIT ?"
    rows = db.get_conn().execute(q, (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


def mark_read(user_id: str) -> int:
    conn = db.get_conn()
    cur = conn.execute(
        "UPDATE notices SET read_at=? WHERE user_id=? AND read_at IS NULL AND deleted_at IS NULL",
        (db.now_iso(), user_id),
    )
    conn.commit()
    return cur.rowcount


# --- Stufe 1: deterministische Regeln ------------------------------------------

def _g(d: dict, *path: str, default: Any = None) -> Any:
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p, default)
    return d


def analyze(user_id: str) -> int:
    """Vergleicht die letzten beiden Trading-Bot-Schnappschüsse. → Anzahl Meldungen."""
    obs = observe.recent(user_id, hours=48, source="tradingbot", limit=2)
    if len(obs) < 2:
        return 0
    latest, prev = obs[0]["daten"], obs[1]["daten"]
    created = 0

    r_new = _g(latest, "mastermeta", "regime")
    r_old = _g(prev, "mastermeta", "regime")
    if r_new and r_old and r_new != r_old:
        conf = _g(latest, "mastermeta", "regime_konfidenz")
        created += add_notice(
            user_id, "tradingbot", "info",
            f"Regime-Wechsel: {r_old} → {r_new}",
            f"MasterMeta meldet neues Markt-Regime '{r_new}' (Konfidenz {conf}). "
            f"Vorher: '{r_old}'.",
        )

    a_new = _g(latest, "governor", "aktionen_gesamt", default=0) or 0
    a_old = _g(prev, "governor", "aktionen_gesamt", default=0) or 0
    if a_new > a_old:
        created += add_notice(
            user_id, "tradingbot", "warn",
            f"Governor hat eingegriffen ({a_old} → {a_new} Aktionen)",
            f"Der Risiko-Governor hat seit dem letzten Schnappschuss {a_new - a_old} "
            f"neue Aktion(en) ausgeführt. Letzte: {_g(latest, 'governor', 'letzte_aktionen')}",
        )

    roi_new = _g(latest, "flotte", "roi_pct")
    roi_old = _g(prev, "flotte", "roi_pct")
    if isinstance(roi_new, (int, float)) and isinstance(roi_old, (int, float)):
        drop = roi_old - roi_new
        if drop >= ROI_DROP_WARN_PP:
            created += add_notice(
                user_id, "tradingbot", "warn",
                f"Flotten-ROI rutscht: {roi_old} % → {roi_new} %",
                f"Verschlechterung um {drop:.2f} Prozentpunkte zwischen den letzten "
                f"Schnappschüssen. Offene Trades: {_g(latest, 'flotte', 'offene_trades')}.",
            )
    return created


# --- Stufe 2: LLM-Vorschläge (1×/Tag, lokal) ------------------------------------

async def suggest(user_id: str) -> int:
    """Lässt das lokale Arbeitsmodell die 24h-Serie lesen → 0–2 Vorschläge."""
    series = observe.recent(user_id, hours=24, source="tradingbot", limit=12)
    if len(series) < 2:
        return 0
    prompt = (
        "Du bist Dizzi und berätst zum Trading-Bot-System (nur beobachten/vorschlagen, "
        "nie eingreifen). Hier die Beobachtungs-Serie der letzten 24h (neueste zuerst):\n"
        + json.dumps(series, ensure_ascii=False)[:6000]
        + "\n\nFormuliere 0 bis 2 konkrete, kurze VERBESSERUNGSVORSCHLÄGE auf Deutsch "
        "(nur wenn die Daten sie wirklich hergeben — sonst leere Liste). Antworte NUR "
        'als JSON-Liste: [{"titel": "...", "begruendung": "..."}]'
    )
    try:
        raw = await providers.quick_chat(
            [{"role": "user", "content": prompt}], model=providers.local_model(),
            format=_Vorschlaege.model_json_schema(),
        )
        # Defensiv: falls das Modell doch Prosa drumherum setzt, auf das Array kürzen.
        raw = raw[raw.find("[") : raw.rfind("]") + 1]
        items = _Vorschlaege.model_validate_json(raw).root
    except Exception:
        return 0
    created = 0
    for it in items[:2]:
        if it.titel:
            created += add_notice(user_id, "tradingbot", "vorschlag",
                                  it.titel[:120], it.begruendung[:1000])
    return created


# --- KA-M8: proaktiver Analyst NETZWEIT (app-agnostisch) ------------------------
# Die 30-min-KPI-Zeitreihe ALLER Vertrags-Apps (observe.observe_contract_apps →
# observations {kpis, status}) wird ausgewertet, nicht nur aufgezeichnet: eine
# deterministische Delta-Stufe (jeder Tick) + eine Tages-LLM-Stufe (constrained,
# IMMER lokales Modell). Datenschutz by construction: sensible KPIs kommen bereits
# maskiert („•••") an und fallen im Zahl-Parse automatisch heraus.

NETZ_FENSTER_H = 3            # Delta-Stufe: Fenster, aus dem die 2 jüngsten Ticks je App kommen
NETZ_MAX_PRO_APP = 3         # Deckel je App je Tick (kein Glocken-Spam)
NETZ_DEFAULT = {"delta_schwelle": 0.25, "llm": True}
# Optionale per-App-Overrides (nach contract-app-id; sonst gilt NETZ_DEFAULT):
NETZ_REGELN: dict[str, dict[str, Any]] = {
    "finanzen": {"delta_schwelle": 0.10},   # Money: Saldo/Ledger enger
    "news":     {"delta_schwelle": 0.50},   # News: Artikel-Zähler weiter
}


def _netz_regel(app_id: str) -> dict[str, Any]:
    return {**NETZ_DEFAULT, **NETZ_REGELN.get(app_id, {})}


def _als_zahl(val: Any) -> float | None:
    """Best-effort KPI-Wert → float. Maskiertes („•••") + Unparsebares ⇒ None
    (⇒ sensible KPIs fallen von selbst raus). Deutsches Format 1.234,56 wird erkannt."""
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s or "•" in s:
        return None
    s = (s.replace("€", "").replace("%", "").replace(" ", "")
          .replace(" ", "").strip())
    try:
        return float(s)                      # "23", "1.5", "-0.42"
    except ValueError:
        pass
    try:
        return float(s.replace(".", "").replace(",", "."))   # "1.234,56" → 1234.56
    except ValueError:
        return None


def _kpi_zahlen(kpis: Any) -> dict[str, float]:
    """KPI-Liste [{id,label,value}] → {label: zahl} (nur parsebare, un-maskierte)."""
    out: dict[str, float] = {}
    for k in kpis or []:
        if not isinstance(k, dict):
            continue
        label = str(k.get("label") or k.get("id") or "").strip()
        z = _als_zahl(k.get("value"))
        if label and z is not None:
            out[label] = z
    return out


def _fmt(v: float) -> str:
    return f"{v:g}"


def analyze_netz(user_id: str) -> int:
    """Delta-Stufe (deterministisch, KEIN LLM): je Vertrags-App die 2 jüngsten
    observations vergleichen — Status-Kippen (ok→warn/fehler) ⇒ ``warn``, numerischer
    KPI-Sprung |Δrel|≥Schwelle ⇒ ``info`` — je App max ``NETZ_MAX_PRO_APP`` Meldungen,
    alles über ``add_notice`` (12-h-Dedupe). ``tradingbot`` deckt das spezifische
    ``analyze()``. Liefert die Anzahl neuer Meldungen."""
    obs = observe.recent(user_id, hours=NETZ_FENSTER_H, limit=300)
    je_quelle: dict[str, list[dict[str, Any]]] = {}
    for o in obs:                            # recent liefert DESC (neueste zuerst)
        q = o.get("quelle")
        if not q or q == "tradingbot":
            continue
        je_quelle.setdefault(q, []).append(o)
    created = 0
    for app_id, serie in je_quelle.items():
        if len(serie) < 2:
            continue
        regel = _netz_regel(app_id)
        latest = serie[0]["daten"] if isinstance(serie[0]["daten"], dict) else {}
        prev = serie[1]["daten"] if isinstance(serie[1]["daten"], dict) else {}
        n_app = 0
        # Regel 1: Status-Kippen (Overlap mit health_watch ok — Dedupe + andere Semantik).
        s_new, s_old = latest.get("status"), prev.get("status")
        if (s_old in ("ok", None) and s_new in ("warn", "fehler")
                and s_new != s_old):
            if add_notice(user_id, app_id, "warn",
                          f"{app_id}: Status auf '{s_new}' gekippt",
                          f"Die App meldet fachlich Status '{s_new}' (vorher '{s_old}')."):
                created += 1
            n_app += 1
        # Regel 2: numerische KPI-Sprünge.
        z_new = _kpi_zahlen(latest.get("kpis"))
        z_old = _kpi_zahlen(prev.get("kpis"))
        for label, v_new in z_new.items():
            if n_app >= NETZ_MAX_PRO_APP:
                break
            v_old = z_old.get(label)
            if v_old is None:
                continue
            basis = abs(v_old) or abs(v_new) or 1.0
            if abs(v_new - v_old) / basis >= regel["delta_schwelle"]:
                if add_notice(
                        user_id, app_id, "info",
                        f"{app_id}: {label} {_fmt(v_old)} → {_fmt(v_new)}",
                        f"{label} hat sich um {v_new - v_old:+.2f} verändert "
                        f"(Schwelle {regel['delta_schwelle']:.0%})."):
                    created += 1
                n_app += 1
    return created


class _NetzVorschlag(BaseModel):
    app_id: str = ""
    titel: str = ""
    begruendung: str = ""


_NetzVorschlaege = RootModel[list[_NetzVorschlag]]


async def suggest_netz(user_id: str) -> int:
    """Tages-LLM-Stufe (app-agnostisch, IMMER lokal ⇒ strukturell cloud-unfähig): baut je
    App eine kompakte 24-h-KPI-Serie (nur Label + erst/letzt/min/max, NIE Freitext) und lässt
    EIN lokales Modell je auffälliger App höchstens einen Vorschlag formulieren. Der ``llm``-
    Flag je App (NETZ_REGELN, Default True) ist der Not-Aus. Liefert die Anzahl."""
    obs = observe.recent(user_id, hours=24, limit=400)
    je_quelle: dict[str, list[dict[str, Any]]] = {}
    for o in obs:
        q = o.get("quelle")
        if not q or q == "tradingbot" or not _netz_regel(q)["llm"]:
            continue
        je_quelle.setdefault(q, []).append(o)
    kompakt: dict[str, dict[str, dict[str, float]]] = {}
    for app_id, serie in je_quelle.items():
        if len(serie) < 2:
            continue
        werte: dict[str, list[float]] = {}
        for o in serie:                      # DESC: [0]=letzt, [-1]=erst
            d = o["daten"] if isinstance(o["daten"], dict) else {}
            for label, z in _kpi_zahlen(d.get("kpis")).items():
                werte.setdefault(label, []).append(z)
        eingedampft = {label: {"erst": vs[-1], "letzt": vs[0],
                               "min": min(vs), "max": max(vs)}
                       for label, vs in werte.items() if vs}
        if eingedampft:
            kompakt[app_id] = eingedampft
    if not kompakt:
        return 0
    prompt = (
        "Du bist Dizzi und überblickst die lokalen Apps des Nutzers (nur beobachten/"
        "vorschlagen, nie eingreifen). Hier je App die 24h-KPI-Serie (erst/letzt/min/max):\n"
        + json.dumps(kompakt, ensure_ascii=False)[:6000]
        + "\n\nFormuliere pro auffälliger App HÖCHSTENS EINEN kurzen, konkreten "
        "VERBESSERUNGSVORSCHLAG auf Deutsch (nur wenn die Zahlen ihn wirklich hergeben — "
        'sonst leere Liste). Antworte NUR als JSON-Liste: '
        '[{"app_id": "...", "titel": "...", "begruendung": "..."}]'
    )
    try:
        raw = await providers.quick_chat(
            [{"role": "user", "content": prompt}], model=providers.local_model(),
            format=_NetzVorschlaege.model_json_schema(),
        )
        raw = raw[raw.find("[") : raw.rfind("]") + 1]
        items = _NetzVorschlaege.model_validate_json(raw).root
    except Exception:
        return 0
    created = 0
    for it in items:
        if it.titel and it.app_id in kompakt:
            created += add_notice(user_id, it.app_id, "vorschlag",
                                  it.titel[:120], it.begruendung[:1000])
    return created
