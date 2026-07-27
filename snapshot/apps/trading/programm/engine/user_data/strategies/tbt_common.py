"""tbt_common.py — geteilte, verhaltens-erhaltende Helfer für die TB-freqtrade-Engines (DRY).

Dieses Modul enthält BEWUSST KEINE ``IStrategy``-Klasse → der freqtrade-Strategy-Resolver
importiert es zwar beim Verzeichnis-Scan, findet keine Strategie und überspringt es (kein Fehler).
Die Engines importieren die Helfer per ``from tbt_common import ...`` (freqtrade legt das
strategies-Verzeichnis auf den ``sys.path``, daher greift der Geschwister-Import).

Alle Funktionen sind 1:1 die bisher in JEDER Engine duplizierten Bodies — die kausale,
lookahead-freie Eigenschaft der Engines bleibt unverändert (reine Env-/Spalten-Helfer, keine
neue Signal-Logik). ``apply_cooldown`` trägt ein explizites ``sides``, damit Long-only- und
Long+Short-Engines exakt ihr bisheriges Verhalten behalten.

GELTUNGSBEREICH (bewusst, Gesetz 2): Dieses Modul ist der kanonische Helfer-Pfad für NEUE Engines
und wird von den 6 jüngsten Engines (TtmSqueeze · EmaAdxTrend · UtBotEma · AsianRangeScalp ·
RsiDivergence · GaussianScalp) genutzt. Die 12 ÄLTEREN Engines behalten vorerst BEWUSST ihre
lokalen Helfer: ihre Formen sind heterogen (drei verschiedene ``_apply_cooldown``-Signaturen;
``_opt`` vs. ``_opt_params``; engine-eigene Multi-TF-Helfer wie ``_informative_tfs``/``_tf_minutes``,
die sich ``json/os/re`` teilen; MasterMeta beidseitig; IntParameter). Eine uniforme Extraktion dort
ist NICHT risikoarm (battle-tested Live-Geld-Engines) — sie werden bei Bedarf opportunistisch
migriert (wenn ohnehin angefasst), nicht in einem Big-Bang.
"""

from __future__ import annotations

import json
import os

from pandas import DataFrame

# Session-Open-Stunden (UTC) — 0=Asia 00:00, 1=London 07:00, 2=US 13:00 (vgl. sessions.SESSION_OPENS).
OPEN_HOURS = {0: 0, 1: 7, 2: 13}


def opt_params() -> dict:
    """Lern-/Optimierungs-Parameter aus der Umgebung (``TBT_OPT_PARAMS``). Leer/defekt = ``{}``."""
    try:
        return json.loads(os.environ.get("TBT_OPT_PARAMS", "") or "{}")
    except Exception:
        return {}


def opt_int(p: dict, key: str, default: int) -> int:
    try:
        return int(p.get(key, default))
    except Exception:
        return default


def opt_float(p: dict, key: str, default: float) -> float:
    try:
        return float(p.get(key, default))
    except Exception:
        return default


def env_leverage(max_leverage, base_default: float) -> float:
    """Per-Bot-Hebel aus ``TBT_LEVERAGE`` (sonst ``base_default``), hart gedeckelt auf 5 und ``max_leverage``."""
    try:
        u = float(os.environ.get("TBT_LEVERAGE", "") or 0)
    except Exception:
        u = 0.0
    base = u if u > 0 else base_default
    return min(base, 5.0, float(max_leverage) or base)


def apply_cooldown(dataframe: DataFrame, gap: int, sides=("enter_long",)) -> DataFrame:
    """Overtrading-Bremse: unterdrückt Entries, die < ``gap`` Kerzen nach dem letzten ZUGELASSENEN
    Entry derselben Seite kommen (eigener Zähler je Seite). ``gap<=0`` = aus.

    ``sides`` = die zu bremsenden Entry-Spalten: Long-only-Engines ``("enter_long",)``,
    Long+Short-Engines ``("enter_long","enter_short")``. ``enter_tag`` wird gelöscht, wo KEINE
    der gebremsten Seiten einen Entry trägt — exakt das bisherige Verhalten je Engine.
    """
    if gap <= 0:
        return dataframe
    present = [c for c in sides if c in dataframe.columns]
    for col in present:
        vals = dataframe[col].fillna(0).astype(int).tolist()
        last = -10 ** 9
        for i, v in enumerate(vals):
            if v == 1:
                if i - last < gap:
                    vals[i] = 0
                else:
                    last = i
        dataframe[col] = vals
    if present and "enter_tag" in dataframe.columns:
        no_entry = None
        for col in present:
            cond = dataframe[col].fillna(0).astype(int) != 1
            no_entry = cond if no_entry is None else (no_entry & cond)
        dataframe.loc[no_entry, "enter_tag"] = None
    return dataframe


def opening_range_bounds(d: DataFrame, open_hour: int, range_min: int):
    """Session-Opening-Range (lookahead-frei): Minuten seit Session-Open (UTC), plus High/Low der
    ersten ``range_min`` Minuten je Session-Tag, auf alle Tageskerzen gebroadcastet.

    Rückgabe: ``(min_since_open, or_high, or_low)`` (pandas-Series). Nur abgeschlossene Range-
    Kerzen fließen ein (``where(in_range).groupby(tag).transform``) — kein Zukunftsblick.
    """
    min_since_open = (d["date"].dt.hour - open_hour) * 60 + d["date"].dt.minute
    sess_day = d["date"].dt.floor("D")
    in_range = (min_since_open >= 0) & (min_since_open < range_min)
    or_high = d["high"].where(in_range).groupby(sess_day).transform("max")
    or_low = d["low"].where(in_range).groupby(sess_day).transform("min")
    return min_since_open, or_high, or_low
