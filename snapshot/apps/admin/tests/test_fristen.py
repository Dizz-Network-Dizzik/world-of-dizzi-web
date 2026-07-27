"""Tests Dizz Admin — Fristen-Cockpit (docs/28 §3, Phase 3): der netzwerkweite,
kategorie-gefilterte Frist-Aggregator über alle Module. Lauf: pytest tests/ -q
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from adminapp import main as lm
from adminapp.fristen import _ics_escape


def _client(tmp_path) -> TestClient:
    return TestClient(lm.build_app(data_dir=tmp_path))


def test_ics_escape_neutralisiert_zeilen_injection():
    """RFC-5545-Injection-Schutz: ein Frist-/Aufgaben-Titel mit CRLF/LF/lone-CR darf
    KEINE neuen iCal-Content-Lines (gefälschte VEVENTs/Properties) einschleusen — alle
    Zeilentrenner werden zu literalem ``\\n`` escaped (lone CR = G3-Härtung 28.06.)."""
    boese = "Meet\r\nBEGIN:VEVENT\nSUMMARY:FAKE\rEND"
    esc = _ics_escape(boese)
    assert "\r" not in esc and "\n" not in esc          # kein echter Zeilenumbruch übrig
    assert esc == "Meet\\nBEGIN:VEVENT\\nSUMMARY:FAKE\\nEND"
    # RFC-5545-Sonderzeichen ebenfalls escaped, sichtbarer Text bleibt
    assert _ics_escape("a,b;c\\d") == "a\\,b\\;c\\\\d"


def _alle(co):
    return [it for g in co["gruppen"].values() for it in g]


def test_fristen_cockpit_aggregiert_alle_quellen(tmp_path):
    with _client(tmp_path) as c:
        heute = date.today()
        gestern = (heute - timedelta(days=1)).isoformat()
        bald = (heute + timedelta(days=5)).isoformat()
        fern = (heute + timedelta(days=200)).isoformat()
        c.post("/api/aufgaben", json={"titel": "Steuer abgeben", "faellig": gestern})  # überfällig
        c.post("/api/aufgaben", json={"titel": "Review", "faellig": bald})             # Woche
        rid = c.post("/api/rechnungen", json={
            "faellig_am": gestern,
            "positionen": [{"einzelpreis_cent": 100, "ust_satz": 0}]}).json()["id"]
        c.post(f"/api/rechnungen/{rid}/stellen")                                        # überfällig
        c.post("/api/fristen", json={"titel": "Jahresabschluss", "faellig_am": fern})   # > Horizont
        bw = c.post("/api/studien", json={"institution": "Uni", "studiengang": "Info"}).json()["id"]
        c.post(f"/api/studien/{bw}/fristen",
               json={"titel": "Klausuranmeldung", "art": "anmeldung", "faellig_am": bald})  # Woche

        co = c.get("/api/fristen-cockpit").json()
        assert co["zaehler"]["ueberfaellig"] == 2          # Aufgabe + Rechnung
        assert co["zaehler"]["woche"] == 2                 # Aufgabe Review + Studienfrist
        assert co["gesamt"] == 4                           # ferne Geschäfts-Frist (200 T) raus
        assert all(it["titel"] != "Jahresabschluss" for it in _alle(co))
        # Quellen-Vielfalt über die Module
        assert {"projekte", "geschaeft", "studium"} <= {it["quelle"] for it in _alle(co)}


def test_fristen_cockpit_bereich_filter(tmp_path):
    with _client(tmp_path) as c:
        gestern = (date.today() - timedelta(days=1)).isoformat()
        b = c.post("/api/bereiche", json={"name": "Studium Info", "art": "studium"}).json()["id"]
        aid = c.post("/api/aufgaben", json={"titel": "A", "faellig": gestern}).json()["id"]
        c.post("/api/aufgaben", json={"titel": "B", "faellig": gestern})        # bereich '' (Allgemein)
        # per-Entity-bereich_id-CRUD ist noch nicht verdrahtet ⇒ Zuordnung direkt in der DB
        conn = c.app.state.bereiche.db.get_conn()
        conn.execute("UPDATE aufgaben SET bereich_id=? WHERE id=?", (b, aid)); conn.commit()

        assert c.get("/api/fristen-cockpit").json()["gesamt"] == 2
        co_b = c.get(f"/api/fristen-cockpit?bereich_id={b}").json()
        assert co_b["gesamt"] == 1 and co_b["gruppen"]["ueberfaellig"][0]["titel"] == "A"
        assert c.get("/api/fristen-cockpit?bereich_id=").json()["gesamt"] == 1   # nur Allgemein
        je = c.get("/api/fristen-cockpit").json()["je_bereich"]
        assert je.get(b) == 1 and je.get("") == 1


def test_fristen_cockpit_ics_feed(tmp_path):
    """iCalendar-Feed (RFC 5545): gültiges VCALENDAR, je Frist ein ganztägiges VEVENT
    mit stabiler UID, korrekter Content-Type + Bereich-Filter; Re-Sync idempotent (UID)."""
    with _client(tmp_path) as c:
        heute = date.today()
        bald = (heute + timedelta(days=5)).isoformat()
        b = c.post("/api/bereiche", json={"name": "Geschäft, GmbH; Co", "art": "geschaeft"}).json()["id"]
        aid = c.post("/api/aufgaben", json={"titel": "Angebot, dringend; raus", "faellig": bald}).json()["id"]
        c.post("/api/aufgaben", json={"titel": "Privat-Task", "faellig": bald})   # Allgemein
        conn = c.app.state.bereiche.db.get_conn()
        conn.execute("UPDATE aufgaben SET bereich_id=? WHERE id=?", (b, aid)); conn.commit()

        r = c.get("/api/fristen-cockpit.ics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/calendar")
        txt = r.text
        # Grundgerüst + CRLF-Zeilenenden (RFC 5545)
        assert txt.startswith("BEGIN:VCALENDAR\r\n") and txt.rstrip().endswith("END:VCALENDAR")
        assert "VERSION:2.0" in txt and "PRODID:" in txt
        assert txt.count("BEGIN:VEVENT") == 2 and txt.count("END:VEVENT") == 2
        assert ("UID:admin:aufgabe:" + aid + "@dizz-admin") in txt
        assert "DTSTART;VALUE=DATE:" + bald.replace("-", "") in txt
        # Escaping von , und ; im SUMMARY/CATEGORIES (RFC 5545 §3.3.11)
        assert "SUMMARY:⏰ Angebot\\, dringend\\; raus" in txt
        assert "BEGIN:VALARM" in txt and "TRIGGER:-P1D" in txt
        # Re-Sync: identische UID ⇒ Kalender-App dedupliziert
        assert c.get("/api/fristen-cockpit.ics").text.count("UID:admin:aufgabe:" + aid) == 1
        # Bereich-Filter zieht auch im Feed
        nur_b = c.get(f"/api/fristen-cockpit.ics?bereich_id={b}").text
        assert nur_b.count("BEGIN:VEVENT") == 1 and "Privat-Task" not in nur_b


def test_fristen_cockpit_aufbewahrung_optin(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/dokumente/upload",
               files={"datei": ("r.pdf", b"%PDF rechnung", "application/pdf")},
               data={"typ": "Rechnung"})                    # Aufbewahrung 10 Jahre
        assert all(it["art"] != "aufbewahrung" for it in _alle(c.get("/api/fristen-cockpit").json()))
        co = c.get("/api/fristen-cockpit?aufbewahrung=1").json()
        assert any(it["art"] == "aufbewahrung" for it in co["gruppen"]["spaeter"])
