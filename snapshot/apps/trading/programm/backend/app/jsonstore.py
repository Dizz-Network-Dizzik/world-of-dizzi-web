"""jsonstore.py — robustes, atomares Lesen/Schreiben kleiner JSON-Zustandsdateien.

Warum: Die Zustandsdateien (``bots.json``, ``runners.json``, ``autopilot.json``) liegen im
OneDrive-gespiegelten Projektordner und werden aus mehreren Threads geschrieben (HTTP-Threadpool +
Autopilot-Hintergrund-Thread). Ein nacktes ``write_text`` truncatet die Datei und schreibt neu — bricht
das mitten drin ab (Absturz, OneDrive-Sync-Konflikt), bleibt eine **halbe, kaputte** Datei zurück.

Lösung:
- **write_atomic**: schreibt in eine ``.tmp`` und ersetzt das Ziel per ``os.replace`` (atomar, auch auf
  Windows) → das Ziel ist immer entweder komplett alt oder komplett neu, nie halb. Zusätzlich wird eine
  ``.bak`` (letzter guter Stand) gepflegt.
- **read_json**: liest das Ziel; ist es defekt, wird die ``.bak`` versucht. Existiert eine Datei, ist aber
  weder Ziel noch Backup lesbar, wird **laut abgebrochen** (RuntimeError) statt still ``default`` zu liefern
  — denn ein stilles ``default`` würde beim nächsten Speichern den (evtl. rettbaren) Inhalt überschreiben.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# Transiente Windows-Dateisperren, die unter OneDrive/Virenscanner GENAU während des atomaren Tauschs
# auftreten können: WinError 5 (Zugriff verweigert) + WinError 32 (Datei von anderem Prozess benutzt).
# Beim flottenweiten Re-Streuen (50 schnelle bots.json-Writes) trat WinError 5 reproduzierbar auf.
_RETRY_WINERR = {5, 32}
_RETRY_ATTEMPTS = 6      # ~ 6 Versuche
_RETRY_BACKOFF_S = 0.08  # × Versuch (0.08, 0.16, … ≈ max ~1.7 s gesamt) — klein, blockiert kaum


def _retry_io(fn, *args):
    """Führt eine Datei-Operation aus und wiederholt sie bei transienten Windows-Sperren (WinError 5/32)
    mit kurzem, wachsendem Backoff. Andere Fehler (und der letzte Fehlversuch) werden durchgereicht."""
    last: Exception | None = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            return fn(*args)
        except OSError as exc:
            if getattr(exc, "winerror", None) not in _RETRY_WINERR or attempt == _RETRY_ATTEMPTS:
                raise
            last = exc
            time.sleep(_RETRY_BACKOFF_S * attempt)
    if last is not None:  # theoretisch unerreichbar (letzter Versuch wirft) — Sicherheitsnetz
        raise last


def write_atomic(path: Path, data: Any) -> None:
    """Schreibt ``data`` als JSON atomar nach ``path`` (+ ``.bak``-Kopie des letzten guten Stands).

    Der tmp-Write und der ``os.replace`` werden gegen transiente OneDrive/Virenscanner-Dateisperren
    (WinError 5/32) mit kurzem Backoff wiederholt — sonst geht unter Last (z. B. flottenweites Schreiben)
    sporadisch ein Save verloren (Lost-Update-Risiko)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_name(path.name + ".tmp")
    _retry_io(tmp.write_text, text, "utf-8")
    _retry_io(os.replace, tmp, path)  # atomarer Tausch (überschreibt bestehendes Ziel), sperr-robust
    try:  # .bak ist reine Recovery-Versicherung — Fehler hier dürfen den Save nicht brechen
        path.with_name(path.name + ".bak").write_text(text, encoding="utf-8")
    except Exception:
        pass


def read_json(path: Path, default: Any) -> Any:
    """Liest JSON resilient: Ziel → ``.bak`` → (nur wenn gar keine Datei existiert) ``default``.

    Existiert eine Datei, ist aber weder Ziel noch Backup parsebar, wird RuntimeError geworfen
    (verhindert stillen Datenverlust durch ein nachfolgendes Überschreiben mit ``default``).
    """
    bak = path.with_name(path.name + ".bak")
    existed = False
    for p in (path, bak):
        if p.exists():
            existed = True
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    if existed:
        raise RuntimeError(f"{path.name}: Ziel und .bak unlesbar (Korruption) — Abbruch statt Datenverlust.")
    return default
