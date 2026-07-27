r"""Demo-Seed für den Bereichs-Cockpit-Feel-Check (docs/34/35, D2 Punkt 3).

Legt einen Demo-**Bereich** mit gesetzten Querverbindungs-Schlüsseln
(``money_kontext`` / ``management_kontext`` / ``memory_ref``) an und füllt ihn mit
einer **admin-seitigen Demo-Finanzspur** (Kunde + Rechnungen Entwurf/offen-überfällig/
bezahlt + Mahnung) sowie Projekt/Aufgabe/Frist und zwei dormanten **Konnektoren** —
damit die 👤-Abnahme des Cockpits etwas Echtes zum Anschauen hat.

WICHTIG zur Cockpit-**Finanzspur-Box**: die zieht ihre Zahlen read-only aus **Dizz
Money** über den Core-Relay (V17, ``money_kontext``). Damit sie im Live-Verbund
gefüllt ist, müssen ein paar Money-Buchungen denselben ``kontext`` tragen — das ist
die **Money-Seite** (FÜR WORLD-CHAT / Money-Chat, s. ``CROSS_APP_HINWEIS`` unten).
Dieses Skript bereitet die **Admin-Seite** vor (Bereich + Schlüssel + lokale Daten).

Idempotent: existiert der Demo-Bereich (per Name) schon, wird er wiederverwendet und
NICHT neu befüllt. Lauf gegen die Scratch-Instanz (Live :8222 NICHT anfassen):

    <venv>\python tools\seed_demo_cockpit.py            # default http://127.0.0.1:8319
    <venv>\python tools\seed_demo_cockpit.py http://127.0.0.1:8319
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from typing import Any

DEMO_NAME = "Demo · Studio Nord"
MONEY_KONTEXT = "studio-nord"
MGMT_KONTEXT = "studio-nord"
MEMORY_REF = "Studio Nord"

CROSS_APP_HINWEIS = (
    "FÜR WORLD-CHAT / Schwester-Apps — damit ALLE drei Cockpit-Spuren im Live-Verbund "
    "Zahlen zeigen, je Quelle mit dem Bereichs-Schlüssel taggen:\n"
    f"  • Dizz Money: ein paar Buchungen mit kontext='{MONEY_KONTEXT}' "
    "(Endpoint /api/bereich/finanzspur?kontext=… aggregiert sie → V17).\n"
    f"  • Dizz Management: ein paar Posts/Social-Bot mit kontext='{MGMT_KONTEXT}' (V18).\n"
    f"  • Dizz Memory: ein Ordner '{MEMORY_REF}' mit Notizen (V19).\n"
    "Die Admin-Seite (Bereich + Schlüssel + lokale Finanzspur) ist mit diesem Seed gesetzt."
)


def _json(resp) -> Any:
    return resp.json()


def _find_bereich(client, name: str) -> dict[str, Any] | None:
    for b in _json(client.get("/api/bereiche")):
        if b.get("name") == name:
            return b
    return None


def seed(client, *, name: str = DEMO_NAME) -> dict[str, Any]:
    """Seedet den Demo-Bereich gegen ``client`` (httpx.Client ODER TestClient — beide
    bieten get/post/put mit ``json=`` und ``.json()``/``.status_code``). Idempotent."""
    vorhanden = _find_bereich(client, name)
    if vorhanden is not None:
        return {"status": "vorhanden", "bereich_id": vorhanden["id"], "name": name,
                "cross_app_hinweis": CROSS_APP_HINWEIS}

    b = _json(client.post("/api/bereiche", json={
        "name": name, "art": "mandant",
        "beschreibung": "Demo-Mandant für den Bereichs-Cockpit-Feel-Check.",
        "money_kontext": MONEY_KONTEXT, "management_kontext": MGMT_KONTEXT,
        "memory_ref": MEMORY_REF}))
    bid = b["id"]

    def zuordnen(tabelle: str, rid: str) -> None:
        client.put("/api/bereiche/zuordnung",
                   json={"tabelle": tabelle, "id": rid, "bereich_id": bid})

    heute = date.today()
    vor20 = (heute - timedelta(days=20)).isoformat()

    # Kunde
    kunde = _json(client.post("/api/kunden", json={
        "name": "Nordlicht GmbH", "firma": "Nordlicht GmbH", "email": "buchhaltung@nordlicht.example"}))
    zuordnen("kunden", kunde["id"])

    rechnungen: list[str] = []

    def rechnung(titel: str, cent: int, *, faellig: str = "") -> str:
        r = _json(client.post("/api/rechnungen", json={
            "kunde_id": kunde["id"], "titel": titel, "faellig_am": faellig,
            "positionen": [{"beschreibung": titel, "menge": 1,
                            "einzelpreis_cent": cent, "ust_satz": 19}]}))
        zuordnen("rechnungen", r["id"]); rechnungen.append(r["id"]); return r["id"]

    # 1) Entwurf  2) gestellt + überfällig (→ Mahnung)  3) gestellt + bezahlt
    rechnung("Setup-Paket", 120000)
    r_offen = rechnung("Monatsbetreuung Mai", 50000, faellig=vor20)
    client.post(f"/api/rechnungen/{r_offen}/stellen")
    r_bez = rechnung("Workshop März", 80000, faellig=vor20)
    client.post(f"/api/rechnungen/{r_bez}/stellen")
    client.post(f"/api/rechnungen/{r_bez}/bezahlt")

    # Mahnung zur überfälligen offenen Rechnung (A8)
    mahn = _json(client.post("/api/mahnungen", json={"rechnung_id": r_offen}))

    # Geschäfts-Frist + Projekt/Aufgabe im Bereich
    frist = _json(client.post("/api/fristen", json={
        "titel": "USt-Voranmeldung Q2", "kategorie": "steuer",
        "faellig_am": (heute + timedelta(days=5)).isoformat()}))
    zuordnen("fristen", frist["id"])
    proj = _json(client.post("/api/projekte", json={"name": "Relaunch Website"}))
    zuordnen("projekte", proj["id"])
    auf = _json(client.post("/api/aufgaben", json={
        "titel": "Angebot finalisieren",
        "faellig": (heute + timedelta(days=3)).isoformat()}))
    zuordnen("aufgaben", auf["id"])

    # Zwei dormante Konnektoren am Bereich (Externe-Tool-Slot, docs/35 §3)
    for typ, nm in (("caldav", "Studio-Kalender"), ("notion", "Mandant-Wiki")):
        client.post("/api/konnektoren", json={"typ": typ, "name": nm, "bereich_id": bid})

    return {"status": "angelegt", "bereich_id": bid, "name": name,
            "money_kontext": MONEY_KONTEXT, "management_kontext": MGMT_KONTEXT,
            "memory_ref": MEMORY_REF, "rechnungen": len(rechnungen),
            "mahnung_id": mahn.get("id"), "frist_id": frist["id"],
            "projekt_id": proj["id"], "aufgabe_id": auf["id"],
            "konnektoren": 2, "cross_app_hinweis": CROSS_APP_HINWEIS}


def main() -> int:
    try:                                    # Windows-Konsole (cp1252) → UTF-8 für Umlaute/Pfeile
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8319"
    try:
        import httpx
    except ImportError:
        print("httpx fehlt im venv.", file=sys.stderr); return 2
    with httpx.Client(base_url=base, timeout=15.0) as client:
        try:
            erg = seed(client)
        except Exception as e:  # noqa: BLE001 — Diagnose für den Bediener
            print(f"Seed fehlgeschlagen gegen {base}: {e}", file=sys.stderr); return 1
    print(f"[{erg['status']}] Demo-Bereich '{erg['name']}' (id={erg['bereich_id']}) gegen {base}")
    for k in ("money_kontext", "management_kontext", "memory_ref", "rechnungen",
              "mahnung_id", "konnektoren"):
        if k in erg:
            print(f"  {k}: {erg[k]}")
    print("\n" + erg["cross_app_hinweis"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
