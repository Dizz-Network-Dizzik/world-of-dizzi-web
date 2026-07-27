"""Querverbindung App → Core → Ziel-App (Phase 2, docs/11 §5c / docs/26).

Eine App reicht ein Element (Notiz, Report, Asset-Metadaten, Mail-Auszug …) an
eine andere Netzwerk-App weiter. **Der Core ist die Drehscheibe**: er kennt die
Ziel-URLs (Apps kennen nur den Core) und auditiert JEDEN Querfluss zentral —
die Grundlage für Leading-Aggregation + autonome Dizzi-Orchestrierung.

Erstes Ziel = **Dizz Memory als zentrales Archiv** (``ziel="memory"`` →
Memorys ``POST /api/querverbindung/archivieren``, idempotent/auditiert).

Auth: localhost-Guard + Single-User-Fallback (``current_user`` ohne Token = der
Single-User ``dizzi``) — wie ``events.push_event``/Mini-Dizzi/Defense-Hub. Kein
Token nötig, der Core-Guard ist die Vertrauensgrenze.

Best-effort by design: ein nicht erreichbarer Core/Ziel darf die sendende App
NIE stören — die Funktion wirft nie, sondern liefert ``{"ok": False, …}``.

HITL/Sicherheit: ``sensibel=True`` markiert das Element beim Ziel als sensibel
(Memory ⇒ KI nur lokal). WANN gesendet wird (z. B. erst nach Freigabe bei
Geld-/Gesundheits-Daten) entscheidet die sendende App über ihre K4-Aktionsstufe.
"""

from __future__ import annotations

from typing import Any

import httpx

CORE_URL = "http://127.0.0.1:8200"


# --- Relay-Kern (DRY, docs/50 P2.3) -------------------------------------------
# Alle 9 Querverbindungen sind derselbe best-effort-Relay: baue Umschlag/Params,
# rufe den Core, gib bei 200 die Ziel-Antwort 1:1 zurück, sonst einen ehrlichen
# Fehler MIT typisiert-leerem Rückgabe-Feld (``leer``) — damit die fragende App nie
# auf ``None`` läuft. Die zwei Helfer kapseln genau diese Schleife; die öffentlichen
# Funktionen bleiben dünne, je Vertrag dokumentierte Wrapper (Signaturen 1:1).

def _relay_post(path: str, umschlag: dict, *, leer: dict | None = None,
                fehler_prefix: str = "Core nicht erreichbar", timeout: float = 5.0,
                core_url: str = CORE_URL, http_post=None) -> dict[str, Any]:
    """POST ``umschlag`` an ``{core_url}{path}``. Bei 200 die Ziel-Antwort, sonst
    ``{"ok": False, **leer, "fehler": …}``. Wirft NIE (best-effort)."""
    leer = leer or {}
    poster = http_post or (lambda url, json: httpx.post(url, json=json, timeout=timeout))
    try:
        r = poster(f"{core_url}{path}", json=umschlag)
        if getattr(r, "status_code", 0) == 200:
            return r.json()
        return {"ok": False, **leer, "fehler": f"Relay HTTP {getattr(r, 'status_code', '?')}"}
    except Exception as e:  # noqa: BLE001 — best-effort, darf die App nie stören
        return {"ok": False, **leer, "fehler": f"{fehler_prefix}: {e}"}


def _relay_get(path: str, params: dict, *, leer: dict | None = None,
               fehler_prefix: str = "Core nicht erreichbar", timeout: float = 5.0,
               core_url: str = CORE_URL, http_get=None) -> dict[str, Any]:
    """GET ``{core_url}{path}`` mit ``params``. Bei 200 die Ziel-Antwort, sonst
    ``{"ok": False, **leer, "fehler": …}``. Wirft NIE (best-effort)."""
    leer = leer or {}
    getter = http_get or (lambda url, params: httpx.get(url, params=params, timeout=timeout))
    try:
        r = getter(f"{core_url}{path}", params=params)
        if getattr(r, "status_code", 0) == 200:
            return r.json()
        return {"ok": False, **leer, "fehler": f"Relay HTTP {getattr(r, 'status_code', '?')}"}
    except Exception as e:  # noqa: BLE001 — best-effort, darf die App nie stören
        return {"ok": False, **leer, "fehler": f"{fehler_prefix}: {e}"}


def archiviere(app_id: str, titel: str, inhalt: str, *,
               quelle: str = "", tags: list[str] | None = None,
               ordner: str = "", ref: str | None = None,
               sensibel: bool = False, strom: str = "", explizit: bool = False,
               ziel: str = "memory", timeout: float = 5.0,
               core_url: str = CORE_URL, http_post=None) -> dict[str, Any]:
    """Archiviert ein Element der App ``app_id`` in der Ziel-Archiv-App (Default
    Memory) — über den Core-Relay ``POST /api/querverbindung/{ziel}``.

    Liefert die Ziel-Antwort ``{"ok": True, "status": "archiviert"|"vorhanden"|
    "uebersprungen", "id": …}`` oder bei Fehler ``{"ok": False, "fehler": …}``.
    Wirft NIE.

    ``ref`` = stabiler externer Idempotenz-Schlüssel (z. B. ``"news:artikel:42"``)
    ⇒ mehrfaches Senden legt nur EINE Notiz an.

    ``strom`` = Strom-/Inhalts-Typ der Quelle (z. B. ``"wochenbericht"`` vs.
    ``"artikel"``) — die Archiv-Regel in Memory entscheidet je (app, strom)
    automatisch/auf Zuruf/aus (docs/26 §8). ``explizit=True`` (Nutzer-Klick
    „archivieren") schlägt JEDE Regel und archiviert immer.
    """
    umschlag = {
        "titel": titel, "inhalt": inhalt, "quelle": quelle, "app": app_id,
        "tags": list(tags or []), "ordner": ordner, "ref": ref,
        "sensibel": bool(sensibel), "strom": strom, "explizit": bool(explizit),
    }
    return _relay_post(f"/api/querverbindung/{ziel}", umschlag,
                       timeout=timeout, core_url=core_url, http_post=http_post)


def sende_termin(app_id: str, titel: str, beginn: str, *,
                 ende: str = "", ganztags: bool = False, ort: str = "",
                 beschreibung: str = "", quelle: str = "", ref: str | None = None,
                 ziel: str = "admin", timeout: float = 5.0,
                 core_url: str = CORE_URL, http_post=None) -> dict[str, Any]:
    """Trägt ein Kalender-Event der App ``app_id`` in die Ziel-Kalender-App ein
    (Default **Dizz Admin** — seit dem Plans+Admin+Leading-Merge, docs/28/29, hält
    Admin den Kalender-Empfänger; ``"plans"`` war tot) — über den Core-Relay
    ``POST /api/querverbindung/{ziel}/kalender`` (ZWEITER Vertragstyp neben
    ``archiviere``, V5 docs/26).

    Liefert die Ziel-Antwort ``{"ok": True, "status": "eingetragen"|"vorhanden",
    "id": …}`` oder bei Fehler ``{"ok": False, "fehler": …}``. Wirft NIE.

    ``ref`` = stabiler Idempotenz-Schlüssel (z. B. ``"komm:termin:42"``) ⇒
    mehrfaches Senden trägt nur EINEN Termin ein.
    """
    umschlag = {
        "titel": titel, "beginn": beginn, "ende": ende, "ganztags": bool(ganztags),
        "ort": ort, "beschreibung": beschreibung, "app": app_id,
        "quelle": quelle, "ref": ref,
    }
    return _relay_post(f"/api/querverbindung/{ziel}/kalender", umschlag,
                       timeout=timeout, core_url=core_url, http_post=http_post)


def memory_suche(q: str, *, semantisch: bool = False, limit: int = 8,
                 ziel: str = "memory", timeout: float = 5.0,
                 core_url: str = CORE_URL, http_get=None) -> dict[str, Any]:
    """RÜCK-LESE-Richtung (das „↔" der Querverbindungen V5–V11, docs/26 §10.1):
    fragt das zentrale Archiv (Default Dizz Memory) ab — über den Core-Relay
    ``GET /api/querverbindung/{ziel}/suche``. Gegenstück zu ``archiviere`` (eine
    App liest, was sie/andere abgelegt haben).

    ``semantisch=False`` ⇒ Wortsuche (FTS5, Memorys ``/api/suche``);
    ``semantisch=True`` ⇒ Bedeutungssuche (RAG/Vektor, ``/api/suche/semantisch``).
    ``limit`` = max. Treffer. ``timeout`` = HTTP-Timeout (s) für den Default-Getter;
    der mini_dizzi-Rück-Lese-Pfad ruft mit einem kürzeren Wert (2,5 s), damit ein
    träger Core die KI-Antwort nicht spürbar verzögert (H-Scan 17.06.).

    Liefert ``{"ok": True, "treffer": [...], "anzahl": n}`` (je Treffer: Notiz-
    Metadaten + ``auszug``) oder bei Fehler ``{"ok": False, "treffer": [],
    "fehler": …}``. Best-effort: wirft NIE, ein nicht erreichbarer Core/Ziel
    liefert leere Treffer (die fragende App läuft ungestört weiter).
    """
    params = {"q": q, "semantisch": "1" if semantisch else "0", "limit": int(limit)}
    return _relay_get(f"/api/querverbindung/{ziel}/suche", params, leer={"treffer": []},
                      timeout=timeout, core_url=core_url, http_get=http_get)


def verknuepfe(von_app: str, von_ref: str, von_titel: str, ziel_ref: str, *,
               notiz: str = "", ziel: str = "admin", timeout: float = 5.0,
               core_url: str = CORE_URL, http_post=None) -> dict[str, Any]:
    """V15 (docs/26 §12): legt beim ZIEL eine **Rück-Referenz** an — der bidirektionale
    Beleg-Link. Die treibende App (z. B. Money) hält ihre Vorwärts-Referenz selbst und
    teilt dem Ziel (z. B. Admin) mit, dass ``von_ref`` (z. B. ``finanzen:buchung:42``)
    auf dessen ``ziel_ref`` (z. B. ``admin:dokument:7``) zeigt — über den Core-Relay
    ``POST /api/querverbindung/{ziel}/verknuepfung``. **Idempotent** beim Ziel
    (``von_ref × ziel_ref``). Nur Daten, kein Aktions-Auslöser. **Wirft NIE.**

    Liefert ``{"ok": True, "status": "verknuepft"|"vorhanden", "id": …}`` bzw.
    ``{"ok": False, "fehler": …}``."""
    umschlag = {"von_app": von_app, "von_ref": von_ref, "von_titel": von_titel,
                "ziel_ref": ziel_ref, "notiz": notiz, "aktion": "anlegen"}
    return _relay_post(f"/api/querverbindung/{ziel}/verknuepfung", umschlag,
                       timeout=timeout, core_url=core_url, http_post=http_post)


def loese_verknuepfung(von_app: str, von_ref: str, ziel_ref: str, *,
                       ziel: str = "admin", timeout: float = 5.0,
                       core_url: str = CORE_URL, http_post=None) -> dict[str, Any]:
    """V15-Gegenstück zu :func:`verknuepfe` (docs/26 §12): meldet dem ZIEL, dass die
    Verknüpfung ``von_ref`` ↔ ``ziel_ref`` aufgelöst ist (z. B. weil die Quell-Buchung
    storniert oder der Beleg entfernt wurde) ⇒ das Ziel räumt seine Rück-Referenz, sodass
    kein **verwaister** „verwendet in N"-Hinweis stehen bleibt. Gleicher Umschlag mit
    ``aktion="loesen"`` (``von_titel`` irrelevant). Best-effort, **wirft NIE**."""
    umschlag = {"von_app": von_app, "von_ref": von_ref, "von_titel": "",
                "ziel_ref": ziel_ref, "notiz": "", "aktion": "loesen"}
    return _relay_post(f"/api/querverbindung/{ziel}/verknuepfung", umschlag,
                       timeout=timeout, core_url=core_url, http_post=http_post)


def belege_holen(ziel: str = "admin", *, q: str = "", limit: int = 50,
                 timeout: float = 5.0, core_url: str = CORE_URL,
                 http_get=None) -> dict[str, Any]:
    """V15-LOOKUP (docs/26 §12): holt die verknüpfbaren Belege/Dokumente vom Ziel
    (Default Dizz Admin) über den Core-Relay ``GET /api/querverbindung/{ziel}/belege``
    → ``{ziel}/api/belege``. Damit füllt die treibende App (Money) ihre Beleg-Auswahl.
    Best-effort: **wirft NIE**, ``[]`` bei Fehler.

    Liefert ``{"ok": True, "belege": [ {ref, titel, typ, datum}, … ]}`` bzw.
    ``{"ok": False, "belege": [], "fehler": …}``."""
    params = {"q": q, "limit": int(limit)}
    return _relay_get(f"/api/querverbindung/{ziel}/belege", params, leer={"belege": []},
                      fehler_prefix="Ziel nicht erreichbar",
                      timeout=timeout, core_url=core_url, http_get=http_get)


def finanzspur_holen(kontext: str, *, jahr: int = 0, kanon: str = "", ziel: str = "finanzen",
                     timeout: float = 5.0, core_url: str = CORE_URL,
                     http_get=None) -> dict[str, Any]:
    """A5/V17 (docs/34): holt die per-Bereich-Finanzspur (Einnahmen/Ausgaben/Saldo je
    ``kontext`` = ``bereich.money_kontext``) von der Finanz-App (Default Dizz Money) über
    den Core-Relay ``GET /api/querverbindung/{ziel}/finanzspur``. Read-only, **wirft NIE**.

    ``kanon`` = kanonische Bereichs-ID (= Admin-``bereiche.id``, docs/67 BER-1): wird
    **zusätzlich** zu ``kontext`` durchgereicht, damit die Ziel-App bevorzugt über die
    stabile ID auflöst (``DzBereichRegister.aufloesen`` ①→②). Additiv/rückwärtskompatibel:
    leer ⇒ der Param entfällt und der Aufruf ist byte-gleich zum kontext-only-Verhalten.

    Liefert ``{"ok": True, "finanzspur": {…}}`` bzw. ``{"ok": False, "finanzspur": {},
    "fehler": …}`` (Core/Ziel offline ⇒ leer; die fragende App läuft ungestört weiter)."""
    params: dict[str, Any] = {"kontext": kontext, "jahr": int(jahr)}
    if kanon:
        params["kanon"] = kanon
    return _relay_get(f"/api/querverbindung/{ziel}/finanzspur", params,
                      leer={"finanzspur": {}},
                      timeout=timeout, core_url=core_url, http_get=http_get)


def bereich_social_holen(kontext: str, *, kanon: str = "", ziel: str = "management",
                         timeout: float = 5.0, core_url: str = CORE_URL,
                         http_get=None) -> dict[str, Any]:
    """A5/V18 (docs/34): holt die per-Bereich-Social-Aktivität (geplante/veröffentlichte
    Posts, aktive Bots je ``kontext``) von Dizz Management über den Core-Relay
    ``GET /api/querverbindung/{ziel}/bereich-social``. Read-only (Veröffentlichen bleibt
    Management-HITL), **wirft NIE**.

    ``kanon`` = kanonische Bereichs-ID (docs/67 BER-1): zusätzlich zu ``kontext``
    durchgereicht (leer ⇒ Param entfällt, kontext-only-verhalten unverändert).

    Liefert ``{"ok": True, "social": {…}}`` bzw. ``{"ok": False, "social": {}, "fehler": …}``."""
    params: dict[str, Any] = {"kontext": kontext}
    if kanon:
        params["kanon"] = kanon
    return _relay_get(f"/api/querverbindung/{ziel}/bereich-social", params,
                      leer={"social": {}},
                      timeout=timeout, core_url=core_url, http_get=http_get)


def kategorie_holen(ordner: str, *, limit: int = 12, kanon: str = "", ziel: str = "memory",
                    timeout: float = 5.0, core_url: str = CORE_URL,
                    http_get=None) -> dict[str, Any]:
    """A5/V19 (docs/34): holt die Notizen einer Memory-Kategorie/eines Ordners
    (= ``bereich.memory_ref``) aus dem zentralen Archiv (Default Dizz Memory) über den
    Core-Relay ``GET /api/querverbindung/{ziel}/kategorie``. Sensibel — read-only, **wirft NIE**.

    ``kanon`` = kanonische Bereichs-ID (docs/67 BER-1/ME-1): zusätzlich durchgereicht,
    damit Memory künftig kanon-primär auf seine Bereichs-Achse auflöst (``ordner`` bleibt
    Alt-Fallback ③). Leer ⇒ Param entfällt (ordner-only-Verhalten unverändert).

    Liefert ``{"ok": True, "notizen": [...], "anzahl": n}`` bzw. ``{"ok": False,
    "notizen": [], "fehler": …}``."""
    params: dict[str, Any] = {"ordner": ordner, "limit": int(limit)}
    if kanon:
        params["kanon"] = kanon
    return _relay_get(f"/api/querverbindung/{ziel}/kategorie", params,
                      leer={"notizen": []},
                      timeout=timeout, core_url=core_url, http_get=http_get)


def kanon_status_holen(ziel: str, *, timeout: float = 5.0, core_url: str = CORE_URL,
                       http_get=None) -> dict[str, Any]:
    """BER-1 (docs/67 §3.3/§3.4): holt den **kanon-status-Feed** einer Konsumenten-App
    (Bereiche mit ``kanon_id``/``kontext`` + ``anker_extra`` = app-spezifische Alt-Namen)
    über den Core-Relay ``GET /api/querverbindung/{ziel}/kanon-status``. Er speist den
    **Broken-Link-Wächter** (``aggregat.bereich_waechter`` → ``waechter_report``).

    Read-only, best-effort — **wirft NIE**: Core/Ziel offline ODER Relay noch nicht
    registriert ⇒ ``{"ok": False, "bereiche": [], "fehler": …}`` ⇒ der Wächter meldet die
    Kante ``unbekannt`` statt zu raten (Invariante I-6). Der Ziel-Endpunkt liefert bei
    Erfolg ``{"ok": True, "bereiche": [...], "anker_extra": {…}}``."""
    return _relay_get(f"/api/querverbindung/{ziel}/kanon-status", {}, leer={"bereiche": []},
                      timeout=timeout, core_url=core_url, http_get=http_get)
