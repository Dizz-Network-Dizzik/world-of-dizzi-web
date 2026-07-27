"""Vertrags-Konformität — maschinell prüfbar statt nur dokumentiert.

Jede App ruft ``check_contract(client, app_id)`` in ihrer Test-Suite auf
(siehe templates/refapp/tests). Damit kann der Vertrag nicht stillschweigend
brechen: eine App, die ihn verletzt, wird rot — egal wer sie wann baut.
"""

from __future__ import annotations

from datetime import datetime

from . import CONTRACT_VERSION
from .manifest import AppManifest
from .summary import Summary


def check_contract(client, app_id: str) -> None:
    """Prüft alle Pflicht-Endpoints des App-Vertrags gegen einen TestClient.

    ``client`` ist ein ``fastapi.testclient.TestClient`` (oder kompatibel)
    der vertragskonformen App.
    """
    # 1) /api/health — Lebenszeichen + Vertrags-Version
    r = client.get("/api/health")
    assert r.status_code == 200, f"/api/health: HTTP {r.status_code}"
    h = r.json()
    assert h["ok"] is True
    assert h["app"] == app_id
    assert h["contract"] == CONTRACT_VERSION, (
        f"Vertrags-Version {h['contract']!r} != Bibliothek {CONTRACT_VERSION!r}")
    datetime.fromisoformat(h["ts"])  # ISO-8601 oder ValueError

    # 2) /api/manifest — validiert strikt gegen das Schema
    r = client.get("/api/manifest")
    assert r.status_code == 200, f"/api/manifest: HTTP {r.status_code}"
    m = AppManifest(**r.json())
    assert m.id == app_id
    assert m.url.startswith("http"), "Deep-Link fehlt im Manifest"

    # 3) /api/summary — IMMER HTTP 200, Schema-konform, display-fertige KPIs
    r = client.get("/api/summary")
    assert r.status_code == 200, f"/api/summary: HTTP {r.status_code} (muss immer 200 sein)"
    s = Summary(**r.json())
    assert s.app == app_id
    if s.status == "ok":
        assert s.kpis, "status 'ok' verlangt mindestens eine KPI"

    # 4) /api/settings — typisiert (K2, Vertrag 1.1): Schema mit 6 Kategorien,
    #    Roundtrip im freien x_-Namensraum, unbekannte Schlüssel ⇒ 400.
    r = client.get("/api/settings/schema")
    assert r.status_code == 200
    kategorien = r.json()["kategorien"]
    assert set(kategorien) == {"konto", "sicherheit", "ki", "vernetzung",
                               "darstellung", "daten"}
    r = client.put("/api/settings", json={"key": "x_konformitaet", "value": 42})
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.get("/api/settings")
    assert r.status_code == 200 and r.json().get("x_konformitaet") == 42
    assert client.put("/api/settings",
                      json={"key": "tippfehler_key", "value": 1}).status_code == 400

    # 4b) /api/account — Konto-Übersicht vorhanden (K2)
    r = client.get("/api/account")
    assert r.status_code == 200
    acc = r.json()
    assert "profil" in acc and "identitaet" in acc and "sso" in acc

    # 4c) /api/actions — K4-Mechanik vorhanden (Katalog + Liste; ggf. leer)
    r = client.get("/api/actions")
    assert r.status_code == 200
    acts = r.json()
    assert "katalog" in acts and "liste" in acts

    # 5) /api/audit — Protokoll vorhanden; der Settings-Write von eben ist drin
    r = client.get("/api/audit")
    assert r.status_code == 200
    entries = r.json()
    assert isinstance(entries, list)
    assert any(e["action"] == "setting_changed" for e in entries), (
        "setting_changed fehlt im Audit-Log")

    # 6) Datenrechte (Vertrag 1.3) — vorhanden UND fail-closed: ohne frische
    #    Verifikation (standalone) MÜSSEN Export/Löschen 403 liefern.
    assert client.post("/api/account/export").status_code == 403, (
        "Export ohne Re-Auth muss 403 sein (fail-closed)")
    assert client.post("/api/account/loeschen").status_code == 403, (
        "Löschen ohne Re-Auth muss 403 sein (fail-closed)")

    # 7) Dizz Defense (Vertrag 1.4) — Pflicht für create_app-Apps; Bestands-
    #    Apps (contract_router-Einbettung, z. B. TB vor O-DEF) dürfen den
    #    Endpoint noch nicht haben ⇒ nur prüfen, wenn vorhanden.
    r = client.get("/api/defense")
    if r.status_code == 200:
        d = r.json()
        assert d.get("name") == "Dizz Defense"
        for key in ("stufenwerk", "massnahmen", "vorfaelle", "lockdown"):
            assert key in d, f"/api/defense ohne Feld {key!r}"

    # 8) Mini-Dizzi (Vertrag 1.5) — KI-Stimme/Brücke; nur prüfen, wenn vorhanden.
    r = client.get("/api/ki/status")
    if r.status_code == 200:
        s = r.json()
        for key in ("app", "app_ki_registriert", "lauscht_lokal", "modus", "wort"):
            assert key in s, f"/api/ki/status ohne Feld {key!r}"
        # Frage muss IMMER 200 + eine Antwort liefern (Fallback fängt alles).
        a = client.post("/api/ki/frage", json={"frage": "Status?"})
        assert a.status_code == 200 and "antwort" in a.json()
