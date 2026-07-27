"""Event-Push App → Dizzi (Kernpaket K4).

Apps melden Ereignisse (Warnungen, Auffälligkeiten, Vorschlags-Hinweise) an
den Dizzi-Core (``POST /api/events``); dort landen sie in der Meldungs-Glocke
(notices) und im L4-Gedächtnis (observations). Best-effort by design: ein
nicht erreichbarer Core darf die App NIE stören (False statt Exception).

Gate: das K2-Setting ``event_push`` (Kategorie Vernetzung, Default aus) —
die App entscheidet selbst, ob sie meldet; Dizzi kann nichts erzwingen.
"""

from __future__ import annotations

from typing import Any

import httpx

CORE_URL = "http://127.0.0.1:8200"
SEVERITIES = ("info", "warn", "vorschlag")


def push_event(app_id: str, severity: str, title: str,
               detail: dict[str, Any] | None = None,
               core_url: str = CORE_URL,
               http_post=None) -> bool:
    """Sendet ein Ereignis an Dizzi. True = angekommen (best-effort)."""
    if severity not in SEVERITIES:
        raise ValueError(f"severity muss aus {SEVERITIES} sein")
    poster = http_post or (lambda url, json: httpx.post(url, json=json, timeout=3.0))
    try:
        r = poster(f"{core_url}/api/events",
                   json={"app": app_id, "severity": severity,
                         "title": title, "detail": detail or {}})
        return bool(getattr(r, "status_code", 0) == 200)
    except Exception:
        return False
