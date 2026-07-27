"""Konto-Löschung (KA-H1 / DSGVO Art. 17) für Dizzi-Core.

Der Core baut FastAPI direkt (kein appkit ``create_app``) und hatte daher gar KEINEN
Lösch-Pfad — Identität/Sessions/Chat/Memory/Observations/RAG/agent_laeufe überlebten
eine Konto-Löschung (der „größere" KA-H1-Befund). Dieses Modul liefert die vollständige,
GPU-frei testbare Lösch-ENGINE:

  1. Kaskade (``db.soft_delete_user``): setzt ``deleted_at`` auf allen user_id-Tabellen
     mit ``deleted_at`` — außer ``audit_log`` (Löschbeleg) und ``id_clients`` (Netz-App-
     Registrierungen, kein Nutzerdatum; ein Soft-Delete bräche das SSO).
  2. Harte Räumung (``_raeume_core_artefakte``): die user_id-Tabellen OHNE ``deleted_at``
     (Identität/Auth: id_identity/id_sessions/id_refresh/id_codes/id_lockout/
     id_webauthn_chal + agent_laeufe) in der Haupt-DB + der RAG-Index (separate rag.sqlite).
  3. Abschluss-Audit ``daten_geloescht`` (in der bewusst behaltenen audit_log).

Reihenfolge/Semantik spiegeln ``appkit/app.py:256-279``.

Der HTTP-Endpoint ``POST /api/account/loeschen`` (in ``app/main.py``) ruft diese Engine
HINTER einem Re-Auth-Gate auf — KA-H1/A2, **Option A** (Architektur-KI-Entscheid 10.07.): er verlangt
das lokale Passwort ODER einen frischen TOTP-Code IM REQUEST. Der Core IST der IdP und prüft
den Credential-Beweis damit an der Quelle (auth_time = jetzt), statt eine neue current_user-/
auth_time-Schicht auf ``/api/`` einzuziehen; fail-closed, H4-Lockout auf beiden Pfaden. Die
Gate-Tests liegen in ``tests/test_loesch_endpoint.py`` — diese Engine bleibt HTTP-/Auth-frei
und damit GPU-frei testbar (``tests/test_loesch_invariante.py``).
"""
from __future__ import annotations

import sqlite3
from typing import Any

from . import db
from .ai import rag

# user_id-Tabellen OHNE deleted_at, die die Soft-Delete-Kaskade überspringt und die
# der Hook daher HART löschen muss (Identität/Auth + Agenten-Läufe). ``id_webauthn``
# hat deleted_at ⇒ deckt die Kaskade (Public-Key ist kein Geheimnis; retention purged).
HART_TABELLEN: tuple[str, ...] = (
    "id_codes", "id_sessions", "id_refresh", "id_identity",
    "id_lockout", "id_webauthn_chal", "agent_laeufe",
)


def _raeume_core_artefakte(user_id: str) -> dict[str, int]:
    """Harte Räumung dessen, was die deleted_at-Kaskade nicht deckt: die
    ``HART_TABELLEN`` in der Haupt-DB + der RAG-Index (rag.sqlite, eigene Verbindung).
    Best-effort je Tabelle (eine nie benutzte, daher nie angelegte Tabelle — z. B.
    ``agent_laeufe`` ohne je gelaufenen Agenten — wird übersprungen). Ein fehlschlagender
    RAG-Purge blockiert die Löschung nie, wird aber als ``rag_purge_fehlgeschlagen``
    auditiert (kein stiller Verlust — abgeleitete Embeddings könnten sonst unsichtbar
    überleben)."""
    conn = db.get_conn()
    zaehler: dict[str, int] = {}
    for t in HART_TABELLEN:
        try:
            zaehler[t] = conn.execute(
                f"DELETE FROM {t} WHERE user_id=?", (user_id,)).rowcount
        except sqlite3.OperationalError:
            pass                              # Tabelle (noch) nicht angelegt
    conn.commit()
    try:
        zaehler.update(rag.remove_user(user_id))     # separate rag.sqlite
    except Exception as e:                     # noqa: BLE001 — RAG best-effort, nie lauf-kritisch
        # „Fehler = gemeldeter, kein stiller Zustand": der Purge darf die Primärlöschung
        # nicht blockieren, aber ein Marker im (behaltenen) audit_log macht sichtbar, dass
        # abgeleitete RAG-Embeddings überlebt haben könnten — statt still zu verschwinden.
        db.audit(user_id, "user", "rag_purge_fehlgeschlagen", {"fehler": str(e)})
    return zaehler


def loesche_konto(user_id: str) -> dict[str, Any]:
    """DSGVO-Art.-17-Konto-Löschung (Engine, ohne HTTP/Auth-Gate — s. Modul-Docstring):
    Kaskade → harte Räumung → Abschluss-Audit. Das Audit-Log selbst bleibt (Beleg)."""
    kaskade = db.soft_delete_user(user_id)     # behalten-Default: audit_log + id_clients
    artefakte = _raeume_core_artefakte(user_id)
    db.audit(user_id, "user", "daten_geloescht",
             {"kaskade": kaskade, "artefakte": artefakte})
    return {"ok": True, "kaskade": kaskade, "artefakte": artefakte}
