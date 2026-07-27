"""Aggregator — eine Kern-Idee von Dizz Admin (Geschäfts-Teil): die Schwester-Apps
READ-ONLY konsumieren statt zu doppeln (docs/00_VISION §Interne Vernetzung).

Bezugsquelle = der **Core** (`/api/panels`): er hält bereits den Live-Status +
die KPI-Kacheln ALLER Vertrags-Apps. Admin zieht das einmal und kuratiert eine
geschäftliche Netzwerk-Übersicht (online?, Kachel-Kennzahlen je App). So braucht
Admin KEINE Einzel-URLs der Schwestern und doppelt keine Logik.

Best-effort: ein nicht erreichbarer Core liefert eine leere, ehrliche Übersicht —
die App bleibt nutzbar. ``http_get`` ist der Test-Injektionspunkt.
"""

from __future__ import annotations

from typing import Any

CORE_URL = "http://127.0.0.1:8200"

# Diese App selbst + reine System-Kacheln blendet die Geschäfts-Übersicht aus.
_AUSBLENDEN = frozenset({"admin", "systeminfo"})

# Executive-Cockpit (UI/UX P1a): je Geschäfts-Domäne EINE Schwester-App + die für
# die Führung relevanteste Kennzahl. ``bevorzugt`` = KPI-IDs in Wunsch-Reihenfolge
# (gegrundet auf die echten /api/summary-KPIs der Schwestern); Fallback = erste KPI.
COCKPIT_DOMAINS = (
    {"id": "finanzen", "brand": "Dizz Money", "titel": "Liquidität",
     "bevorzugt": ("netto", "cashflow_30t", "saldo", "konten")},
    {"id": "kommunikation", "brand": "Dizz Communication", "titel": "Support",
     "bevorzugt": ("ungelesen", "offen", "konversationen")},
    {"id": "management", "brand": "Dizz Management", "titel": "Social",
     "bevorzugt": ("geplant", "bots", "naechster_slot")},
    # „Fristen" ist KEINE Schwester-Kachel mehr: Dizz Plans ist in Dizz Admin
    # verschmolzen (docs/28) — die Fristen liegen jetzt im eigenen Fristen-Cockpit.
)


def _pick_kpi(kpis: list, bevorzugt: tuple[str, ...]) -> dict[str, Any] | None:
    """Wählt die führungsrelevante KPI: erste Treffer-ID aus ``bevorzugt``,
    sonst die erste gelieferte KPI (App ordnet selbst nach Wichtigkeit)."""
    by_id = {k.get("id"): k for k in kpis if isinstance(k, dict)}
    for kid in bevorzugt:
        if kid in by_id:
            return by_id[kid]
    return kpis[0] if kpis else None


def cockpit_uebersicht(core_url: str = CORE_URL, http_get: Any | None = None) -> dict[str, Any]:
    """Executive-Cockpit-Daten (P1a): je Domäne Online-Status + führungsrelevante
    Kennzahl + Deep-Link in die Quell-App. Quelle = der Core (``/api/panels/{id}/
    stats`` liefert je Vertrags-App ``online``/``kpis``/``url``). Best-effort: eine
    nicht erreichbare/ungebaute App erscheint als Kachel ``online=false`` statt zu
    fehlen — das Cockpit bleibt ehrlich nutzbar."""
    import httpx
    getter = http_get or (lambda url: httpx.get(url, timeout=5.0))

    def _stats(pid: str) -> dict[str, Any] | None:
        try:
            r = getter(f"{core_url}/api/panels/{pid}/stats")
            if getattr(r, "status_code", 0) != 200:
                return None
            return r.json()
        except Exception:  # noqa: BLE001 — best-effort, darf das Cockpit nie stören
            return None

    # Z-1 (28.06.): die je-Domäne-Calls sind unabhängig ⇒ PARALLEL statt seriell
    # (sonst O(Domänen) Round-Trips = die Cockpit-Latenz). ThreadPoolExecutor je sync
    # getter (thread-safe, separate httpx-Calls), Reihenfolge via zip erhalten. Scratch-
    # Beweis: 3 Domänen 797→218 ms (~3,7×); skaliert linear mit Domänen-Zahl.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, len(COCKPIT_DOMAINS))) as _ex:
        _stats_je_dom = list(_ex.map(lambda d: _stats(d["id"]), COCKPIT_DOMAINS))

    kacheln = []
    core_ok = True
    for dom, st in zip(COCKPIT_DOMAINS, _stats_je_dom):
        if st is None:
            core_ok = False
            kacheln.append({"id": dom["id"], "brand": dom["brand"], "titel": dom["titel"],
                            "online": False, "kpi": None, "alle": [], "url": None})
            continue
        # Platzhalter-Panel (App noch nicht gebaut/angebunden) ⇒ kein online-Feld.
        online = bool(st.get("online")) and st.get("status") != "platzhalter"
        kpis = st.get("kpis") or []
        kacheln.append({"id": dom["id"], "brand": dom["brand"], "titel": dom["titel"],
                        "online": online, "kpi": _pick_kpi(kpis, dom["bevorzugt"]),
                        "alle": kpis, "url": st.get("url")})
    return {"ok": core_ok, "kacheln": kacheln}


def netzwerk_uebersicht(core_url: str = CORE_URL, http_get: Any | None = None) -> dict[str, Any]:
    """Kuratierte Netzwerk-Übersicht aus den Core-Panels. Liefert je App
    ``id``/``brand``/``status`` + (falls vorhanden) die Stats-Kachel."""
    import httpx
    getter = http_get or (lambda url: httpx.get(url, timeout=5.0))
    try:
        r = getter(f"{core_url}/api/panels")
        if getattr(r, "status_code", 0) != 200:
            return {"ok": False, "fehler": f"Core HTTP {getattr(r, 'status_code', '?')}", "apps": []}
        panels = r.json()
    except Exception as e:  # noqa: BLE001 — best-effort, darf die App nie stören
        return {"ok": False, "fehler": f"Core nicht erreichbar: {e}", "apps": []}

    apps = []
    for p in panels:
        pid = p.get("id", "")
        if pid in _AUSBLENDEN:
            continue
        apps.append({
            "id": pid,
            "brand": p.get("brand") or p.get("name") or pid,
            "status": p.get("status", "unbekannt"),
        })
    online = sum(1 for a in apps if a["status"] == "aktiv")
    return {"ok": True, "apps": apps, "anzahl": len(apps), "online": online}


def geschaeft_ausgaben(jahr: int, *, ziel: str = "finanzen",
                       core_url: str = CORE_URL,
                       http_get: Any | None = None) -> dict[str, Any]:
    """V16-Vertiefung (docs/11 §5c): die geschäftlichen (steuer-relevanten) AUSGABEN
    eines Jahres aus Dizz Money — über den Core-Relay ``GET /api/querverbindung/{ziel}/
    euer`` (proxyt Moneys EÜR-Auswertung mit ``nur_steuer=1``). Sie füllen die
    EÜR-Ausgabenseite von Dizz Leading (Aggregation statt Doppeln).

    Best-effort: ist Money/Core offline, liefert die Funktion ehrlich **leere**
    Ausgaben (``ok=False``) — Leadings EÜR zeigt dann nur die Einnahmen statt zu
    raten. Liefert ``{ok, ausgaben_cent, je_kategorie, einnahmen_cent,
    einnahmen_je_kategorie, quelle}`` (je nur Kategorien mit Betrag > 0, absteigend).

    Die ``einnahmen_*``-Felder sind die steuer-relevanten Einnahmen, die der Nutzer
    in Money gebucht hat — **informativ** (sie werden in Leading NICHT zur EÜR-
    Einnahmenseite addiert, weil dieselben Erlöse i. d. R. schon als Leading-Rechnung
    erfasst sind ⇒ Doppelzählungs-Schutz; die Abgleich-Darstellung ist UI/UX-Phase)."""
    import httpx
    getter = http_get or (lambda url: httpx.get(url, timeout=5.0))
    leer = {"ok": False, "ausgaben_cent": 0, "je_kategorie": [],
            "einnahmen_cent": 0, "einnahmen_je_kategorie": [], "quelle": ziel}
    try:
        r = getter(f"{core_url}/api/querverbindung/{ziel}/euer?jahr={int(jahr)}")
        if getattr(r, "status_code", 0) != 200:
            return leer
        euer = ((r.json() or {}).get("euer")) or {}
    except Exception:  # noqa: BLE001 — best-effort, darf Leading nie stören
        return leer

    def _posten(feld: str) -> list[dict[str, Any]]:
        out = []
        for k in euer.get("je_kategorie", []):
            betrag = int(k.get(feld, 0) or 0)
            if betrag > 0:
                out.append({"kategorie": k.get("kategorie_name") or "Nicht zugeordnet",
                            "steuer_art": k.get("steuer_art") or "",
                            f"{feld}_cent": betrag})
        out.sort(key=lambda e: -e[f"{feld}_cent"])
        return out

    return {"ok": True,
            "ausgaben_cent": int(euer.get("ausgaben", 0) or 0),
            "je_kategorie": _posten("ausgaben"),
            "einnahmen_cent": int(euer.get("einnahmen", 0) or 0),
            "einnahmen_je_kategorie": _posten("einnahmen"),
            "quelle": ziel}


def bereich_spuren(bereich: dict[str, Any], *, jahr: int = 0,
                   core_url: str = CORE_URL, http_get: Any | None = None) -> dict[str, Any]:
    """A5 (d, docs/34) — Bereichs-Cockpit-Daten: bündelt die DREI Querverbindungs-Spuren
    EINES Bereichs über die appkit-Helfer (jede über ihren Core-Relay, read-only):
    **Finanzspur** (Dizz Money, via ``bereich.money_kontext``) · **Social** (Dizz
    Management, via ``management_kontext``) · **Wissen** (Dizz Memory, via ``memory_ref``).
    BER-1 (docs/67 §3.3): zusätzlich wird die kanonische Bereichs-ID (``kanon`` =
    ``bereich.id``) durchgereicht; die drei kontext-Slots bleiben Anzeige/Fallback.

    Best-effort: jede Helfer-Funktion wirft NIE (Core/Ziel offline ⇒ leere Spur mit
    ``ok=False``); ein leerer Kontext-Schlüssel ⇒ Spur wird übersprungen (``ok=False``,
    ``fehler="kein …"``). So bleibt das Cockpit auch ohne laufenden Core/Schwester-App
    nutzbar. ``http_get`` (Signatur ``(url, params)`` wie in ``appkit.querverbindung``)
    ist der Test-Injektionspunkt und wird an alle drei Helfer durchgereicht."""
    from appkit.querverbindung import (bereich_social_holen, finanzspur_holen,
                                       kategorie_holen)
    money_k = (bereich.get("money_kontext") or "").strip()
    mgmt_k = (bereich.get("management_kontext") or "").strip()
    mem_k = (bereich.get("memory_ref") or "").strip()
    # BER-1 (docs/67 §3.3): die kanonische Bereichs-ID (= Admin-``bereiche.id``) wird
    # ZUSÄTZLICH zum kontext-Slot mitgeschickt, damit die Ziel-App bevorzugt darüber auflöst
    # (``DzBereichRegister.aufloesen`` ①kanon→②kontext). Additiv/rückwärtskompatibel: der
    # Slot-leer-Skip bleibt bestehen (kein Slot ⇒ keine Spur, KEIN Core-Call — 0 Verhaltens-
    # wechsel); ist der Slot gesetzt, trägt derselbe Relay-Call die kanon-ID zusätzlich.
    kanon = (bereich.get("id") or "").strip()
    finanz = (finanzspur_holen(money_k, jahr=jahr, kanon=kanon, core_url=core_url, http_get=http_get)
              if money_k else {"ok": False, "finanzspur": {}, "fehler": "kein money_kontext"})
    social = (bereich_social_holen(mgmt_k, kanon=kanon, core_url=core_url, http_get=http_get)
              if mgmt_k else {"ok": False, "social": {}, "fehler": "kein management_kontext"})
    wissen = (kategorie_holen(mem_k, kanon=kanon, core_url=core_url, http_get=http_get)
              if mem_k else {"ok": False, "notizen": [], "fehler": "kein memory_ref"})
    return {
        "bereich_id": bereich.get("id"), "name": bereich.get("name"),
        "art": bereich.get("art"), "kanon": kanon,
        "kontexte": {"money_kontext": money_k, "management_kontext": mgmt_k,
                     "memory_ref": mem_k},
        "finanzspur": finanz, "social": social, "wissen": wissen}


def bereich_waechter(admin_bereiche: list[dict[str, Any]], *, core_url: str = CORE_URL,
                     http_get: Any | None = None) -> dict[str, Any]:
    """A5/BER-1 Broken-Link-Wächter (docs/67 §3.4): bündelt die ``kanon-status``-Feeds der
    drei Konsumenten (Money V17 · Management V18 · Memory V19) über die Core-Relays und
    klassifiziert je Admin-Bereich × Kante über ``bereich_register.waechter_report``:
    ``ok`` (kanon-Bindung trifft) · ``alt`` (nur kontext-/Namens-Treffer — fragil, B-1) ·
    ``dangling`` (Slot zeigt ins Leere) · ``mehrdeutig`` (B-2) · ``ungenutzt`` (Slot leer) ·
    ``unbekannt`` (Feed offline). So wird eine verwaiste Referenz SICHTBAR statt still.

    Die Klassifikation ist pure appkit-Logik; hier läuft nur der Feed-Einzug. Read-only +
    best-effort: ein nicht erreichbarer ODER (noch) nicht registrierter Feed ⇒ die Kante
    bleibt ``unbekannt`` (Invariante I-6) — wirft nie. ``http_get`` (Signatur ``(url,
    params)`` wie in ``appkit.querverbindung``) ist der Test-Injektionspunkt."""
    from appkit.bereich_register import anker_index, waechter_report
    from appkit.querverbindung import kanon_status_holen
    # Kante → Querverbindungs-Ziel (= App-Netz-id im Relay-Pfad, wie in den A5-Helfern).
    ziel_je_kante = (("V17", "finanzen"), ("V18", "management"), ("V19", "memory"))
    anker: dict[str, Any] = {}
    for kante, ziel in ziel_je_kante:
        feed = kanon_status_holen(ziel, core_url=core_url, http_get=http_get)
        if not feed.get("ok"):
            continue                       # Feed offline/unregistriert ⇒ Kante 'unbekannt'
        extra = feed.get("anker_extra") or {}
        namen = [n for liste in extra.values() if isinstance(liste, list) for n in liste]
        anker[kante] = anker_index(feed.get("bereiche") or [], extra_namen=namen)
    return waechter_report(admin_bereiche, anker)
