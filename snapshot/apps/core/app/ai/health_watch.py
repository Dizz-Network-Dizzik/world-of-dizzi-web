"""Core-Health-Watch (R-4/R-5) — Betriebs-Wächter über die Gesundheit des Netzwerks.

Pingt periodisch die Vertrags-Apps (:82xx) und **Ollama** (der geteilte Single-
Point ALLER App-KIs + Triage + Mini-Dizzi). Meldet **Zustands-WECHSEL** (auf↔ab)
an die Glocke und versucht Ollama bei Ausfall — geguarded gegen Endlos-Schleifen —
einmal je Abkühlzeit zu reanimieren (`ollama serve`).

Bewusst defensiv (wie der L4-Beobachter): jeder Fehler bleibt lokal, der Wächter
darf den Core nie beeinträchtigen. Die SYNC-Pings laufen im Thread (Aufrufer nutzt
``asyncio.to_thread``). Zustand = Prozess-Gedächtnis (nach Neustart neu, fail-safe).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Callable

from .. import db
from . import providers

WATCH_INTERVAL_S = 60
REANIMATE_COOLDOWN_S = 180   # Ollama höchstens alle 3 min neu anstoßen (kein Loop)
OLLAMA_CMD = os.environ.get("DIZZI_OLLAMA_CMD", "ollama")

# Prozess-Gedächtnis: zuletzt bekannter Zustand je Ziel (True=erreichbar) +
# Zeit des letzten Reanimations-Versuchs.
_state: dict[str, bool] = {}
_last_reanimate: float = 0.0


def _notice(user_id: str, severity: str, title: str, detail: dict) -> None:
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO notices (id, user_id, source, severity, title, detail, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (db.new_id(), user_id, "health-watch", severity, title,
         json.dumps(detail, ensure_ascii=False), db.now_iso()))
    conn.commit()


def _ping_app(base_url: str, path: str = "/api/health") -> bool:
    """App erreichbar? ``path`` < 500 (401/403 = läuft, nur auth-gegated)."""
    import httpx
    try:
        return httpx.get(f"{base_url}{path}", timeout=3.0).status_code < 500
    except Exception:
        return False


def _ollama_alive() -> bool:
    """Ollama erreichbar? Über die LocalRuntime-Selbstauskunft (docs/62 runtime-
    Konsistenz) statt direktem ``/api/tags``: ``health()`` (= ``/api/version``, 3 s,
    wirft nie) spiegelt für ein laufendes Ollama denselben Zustand wie der frühere
    ``/api/tags``==200-Check — dieselbe Äquivalenz, die ``providers.status()`` in M5
    übernahm (``ollama_ok = health().ok``). Die core-URL-gepinnte Runtime bleibt
    erhalten (``providers.OLLAMA_URL`` / ``DIZZI_OLLAMA_URL``); den Adapter wählt der
    Setting-Pfad (``runtime``, fail-safe Ollama). Das ``try`` bleibt defensiv für den
    Runtime-/DB-Zugriff — der Wächter darf nie werfen (health() selbst wirft nie)."""
    try:
        return providers.runtime().health().ok
    except Exception:
        return False


def _reanimate_ollama(now: float) -> bool:
    """Stößt `ollama serve` detached an, höchstens alle REANIMATE_COOLDOWN_S
    (Loop-Schutz). Liefert True, wenn ein Versuch gestartet wurde."""
    global _last_reanimate
    if now - _last_reanimate < REANIMATE_COOLDOWN_S:
        return False
    _last_reanimate = now
    try:
        kw: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        subprocess.Popen([OLLAMA_CMD, "serve"], **kw)
        return True
    except Exception:
        return False


def _default_checks() -> dict[str, Callable[[], bool]]:
    from .. import panels
    checks: dict[str, Callable[[], bool]] = {
        f"app:{aid}": (lambda u=url: _ping_app(u))
        for aid, url in panels.contract_apps().items()
    }
    # Trading Bot (Legacy-Kachel, KEIN Contract-App) jetzt ebenfalls zentral überwacht (F3):
    # eigener /health-Endpunkt (TB hat kein /api/health). So wird ein TB-Ausfall an der Glocke
    # gemeldet, nicht nur an der Kachel sichtbar.
    checks["app:tradingbot"] = lambda u=panels.TRADINGBOT_URL: _ping_app(u, "/health")
    checks["ollama"] = _ollama_alive
    return checks


def tick(user_id: str,
         checks: dict[str, Callable[[], bool]] | None = None,
         reanimate: Callable[[float], bool] | None = None,
         now: float | None = None) -> dict[str, bool]:
    """Ein Wächter-Durchlauf: prüft alle Ziele, meldet echte Zustands-WECHSEL an
    die Glocke + Audit, und reanimiert Ollama bei Ausfall (geguarded). Gibt den
    aktuellen Zustand je Ziel zurück. ``checks``/``reanimate``/``now`` sind für
    Tests injizierbar (Default = Live-Pings)."""
    now = time.time() if now is None else now
    reanimate = _reanimate_ollama if reanimate is None else reanimate
    checks = _default_checks() if checks is None else checks

    aktuell: dict[str, bool] = {}
    for ziel, pruef in checks.items():
        try:
            alive = bool(pruef())
        except Exception:
            alive = False
        aktuell[ziel] = alive
        vorher = _state.get(ziel)
        _state[ziel] = alive
        if vorher is None or vorher == alive:
            continue  # Grundzustand (erster Lauf) meldet nichts — nur echte Wechsel
        if not alive:
            _notice(user_id, "warn", f"Ausfall: {ziel}", {"ziel": ziel, "zustand": "offline"})
            db.audit(user_id, "system", "health_ausfall", {"ziel": ziel})
        else:
            _notice(user_id, "info", f"Wieder erreichbar: {ziel}", {"ziel": ziel, "zustand": "online"})
            db.audit(user_id, "system", "health_erholt", {"ziel": ziel})

    # Ollama ist der kritische Single-Point: bei Ausfall reanimieren (unabhängig vom
    # Wechsel — auch ein schon beim Start toter Dienst soll hochkommen; Cooldown schützt).
    if "ollama" in aktuell and not aktuell["ollama"]:
        # KA-N3: einmaliger Einrichtungs-Hinweis (auch OHNE Zustands-Wechsel — ein schon
        # beim Start toter Ollama soll den Nutzer erreichen; add_notice-Dedupe deckelt 12 h).
        from . import analyst
        analyst.add_notice(
            user_id, "health-watch", "info",
            "Lokale KI (Ollama) nicht erreichbar",
            "Ollama ist nicht gestartet/installiert — die lokale KI (Chat, Triage, "
            "App-Assistenten) bleibt bis dahin aus. `ollama serve` starten bzw. Ollama "
            "installieren; danach kommt sie automatisch hoch.")
        if reanimate(now):
            _notice(user_id, "warn", "Ollama neu gestartet",
                    {"ziel": "ollama", "aktion": "ollama serve"})
            db.audit(user_id, "system", "ollama_reanimiert", {})
    return aktuell


def status() -> dict[str, bool]:
    """Aktueller bekannter Zustand je Ziel (für GET /api/health/watch)."""
    return dict(_state)
