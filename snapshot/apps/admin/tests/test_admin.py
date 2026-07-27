"""Tests Dizz Admin [AD] — Geschäfts-/Studien-Kern (Basis-Repo leading, id→admin):
Vertrags-Konformität + Domäne (Kunden/Produkte/Rechnungen GoBD-append-only/Fristen/
Support/Studium) + KPIs/EÜR/Frist-Wächter + Aggregator (Schwestern read-only über den
Core, gemockt) + Mini-Dizzi-KI-Smoke + MCP-Namensraum. (Tresor/Projekte/Bereiche folgen.)

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from appkit import conformance
from adminapp import main as lm


def _client(tmp_path, *, http_post=None, http_get=None) -> TestClient:
    kw = {}
    if http_post is not None:
        kw["http_post"] = http_post
    if http_get is not None:
        kw["http_get"] = http_get
    return TestClient(lm.build_app(data_dir=tmp_path, **kw))


class _LeerResp:
    """Generische 200-Antwort mit leerer Liste (z. B. Core-Panels im EÜR-Test)."""
    status_code = 200

    def json(self):
        return []


class _MoneyEuerResp:
    """Simuliert die Core-Relay-Antwort GET /api/querverbindung/finanzen/euer
    (V16) = Moneys EÜR-Auswertung mit einer steuer-relevanten Ausgabe- UND einer
    steuer-relevanten Einnahme-Kategorie (letztere informativ, V16/(b))."""
    status_code = 200

    def json(self):
        return {"ok": True, "ziel": "finanzen", "euer": {
            "jahr": date.today().year, "einnahmen": 3000, "ausgaben": 10000,
            "ueberschuss": -7000, "nur_steuer": True, "je_kategorie": [
                {"kategorie_id": "k1", "kategorie_name": "Bürobedarf",
                 "steuer_relevant": True, "steuer_art": "Betriebsausgabe",
                 "einnahmen": 0, "ausgaben": 10000, "ueberschuss": -10000},
                {"kategorie_id": "k2", "kategorie_name": "Nebenerlös",
                 "steuer_relevant": True, "steuer_art": "Betriebseinnahme",
                 "einnahmen": 3000, "ausgaben": 0, "ueberschuss": 3000}]}}


def test_vertrag_konform(tmp_path):
    with _client(tmp_path) as c:
        conformance.check_contract(c, "admin")
        # Dizzi-ID installiert; ohne Login = Standalone-Stufe 'lokal'.
        assert c.get("/auth/me").json() == {"angemeldet": False, "level": "lokal"}


def test_kunde_crud(tmp_path):
    with _client(tmp_path) as c:
        kid = c.post("/api/kunden", json={"name": "Acme GmbH", "email": "a@b.de"}).json()["id"]
        assert len(c.get("/api/kunden").json()) == 1
        c.put(f"/api/kunden/{kid}", json={"firma": "Acme"})
        assert c.get("/api/kunden").json()[0]["firma"] == "Acme"
        assert c.delete(f"/api/kunden/{kid}").json()["ok"] is True
        assert c.get("/api/kunden").json() == []
        assert c.put("/api/kunden/gibtsnicht", json={"name": "x"}).status_code == 404
        assert c.post("/api/kunden", json={"name": "  "}).status_code == 400


def test_rechnung_lebenszyklus_und_gobd(tmp_path):
    # V16: die EÜR-Ausgabenseite zieht aus Dizz Money (Core-Relay) — hier injiziert,
    # damit der Test hermetisch bleibt und die Einnahmen-MINUS-Ausgaben-Faltung greift.
    def _euer_get(url):
        if "/euer" in url:
            return _MoneyEuerResp()
        return _LeerResp()
    with _client(tmp_path, http_get=_euer_get) as c:
        rid = c.post("/api/rechnungen", json={
            "titel": "Webdesign", "faellig_am": "2020-01-01",
            "positionen": [
                {"beschreibung": "Design", "menge": 2, "einzelpreis_cent": 10000, "ust_satz": 19},
                {"beschreibung": "Hosting", "menge": 1, "einzelpreis_cent": 5000, "ust_satz": 19}],
        }).json()["id"]
        det = c.get(f"/api/rechnungen/{rid}").json()
        assert det["status"] == "entwurf" and det["nummer"] == ""
        # Entwurf rechnet live: netto 25000, ust 4750, brutto 29750
        assert det["netto_cent"] == 25000 and det["ust_cent"] == 4750 and det["brutto_cent"] == 29750

        st = c.post(f"/api/rechnungen/{rid}/stellen").json()
        assert st["status"] == "offen" and st["nummer"].endswith("-0001") and st["brutto_cent"] == 29750

        # GoBD: eine gestellte Rechnung ist unveränderlich (kein PUT, kein DELETE)
        assert c.put(f"/api/rechnungen/{rid}", json={"titel": "x", "positionen": []}).status_code == 409
        assert c.delete(f"/api/rechnungen/{rid}").status_code == 409

        assert c.post(f"/api/rechnungen/{rid}/bezahlt").json()["status"] == "bezahlt"
        s = c.get("/api/stats").json()
        assert s["umsatz_bezahlt_cent"] == 29750 and s["offene_rechnungen"] == 0

        e = c.get(f"/api/euer?jahr={date.today().year}").json()
        assert e["anzahl"] == 1 and e["einnahmen_netto_cent"] == 25000
        # V16: Ausgabenseite aus Money gefaltet (10.000 Cent), Überschuss = 25000 − 10000.
        assert e["ausgaben_ok"] is True and e["ausgaben_cent"] == 10000
        assert e["ueberschuss_cent"] == 15000
        assert e["ausgaben_je_kategorie"][0]["kategorie"] == "Bürobedarf"
        # V16/(b): explizite Quellen + Money-Einnahmen INFORMATIV (nicht im Überschuss).
        assert e["quellen"]["einnahmen"].startswith("Dizz Admin")
        assert e["money_einnahmen_cent"] == 3000          # aus Money, steuer-relevant
        assert e["ueberschuss_cent"] == 15000             # NICHT um die 3000 erhöht (Doppelzählungs-Schutz)
        assert e["money_einnahmen_je_kategorie"][0]["kategorie"] == "Nebenerlös"
        csv = c.get("/api/euer/export").text
        assert "nummer;datum" in csv and "250.00" in csv
        assert "AUSGABEN" in csv and "Bürobedarf" in csv and "Ueberschuss_eur" in csv
        assert "MONEY-EINNAHMEN" in csv and "Nebenerlös" in csv   # informativ ausgewiesen


def test_rechnung_stellen_ohne_positionen_400(tmp_path):
    with _client(tmp_path) as c:
        rid = c.post("/api/rechnungen", json={"titel": "leer"}).json()["id"]
        assert c.post(f"/api/rechnungen/{rid}/stellen").status_code == 400


def test_nummern_luckenlos(tmp_path):
    with _client(tmp_path) as c:
        nums = []
        for _ in range(3):
            rid = c.post("/api/rechnungen", json={
                "positionen": [{"einzelpreis_cent": 100, "ust_satz": 0}]}).json()["id"]
            nums.append(c.post(f"/api/rechnungen/{rid}/stellen").json()["nummer"])
        jahr = date.today().year
        assert nums == [f"{jahr}-0001", f"{jahr}-0002", f"{jahr}-0003"]


def test_frist_waechter(tmp_path):
    with _client(tmp_path) as c:
        rid = c.post("/api/rechnungen", json={
            "faellig_am": "2020-01-01",
            "positionen": [{"einzelpreis_cent": 100, "ust_satz": 0}]}).json()["id"]
        c.post(f"/api/rechnungen/{rid}/stellen")
        c.post("/api/fristen", json={"titel": "UStVA", "kategorie": "steuer", "faellig_am": "2020-02-10"})
        w = c.get("/api/waechter").json()
        assert len(w["ueberfaellige_rechnungen"]) == 1 and len(w["faellige_fristen"]) == 1
        s = c.get("/api/stats").json()
        assert s["ueberfaellige_rechnungen"] == 1 and s["fristen_faellig"] == 1


def test_produkt_mrr(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/produkte", json={"name": "Dizz Money", "preis_cent": 1000, "abo_intervall": "monatlich"})
        c.post("/api/produkte", json={"name": "Dizz Trading", "preis_cent": 12000, "abo_intervall": "jaehrlich"})
        s = c.get("/api/stats").json()
        assert s["mrr_cent"] == 2000   # 1000 monatlich + 12000/12


def test_support_crud(tmp_path):
    with _client(tmp_path) as c:
        sid = c.post("/api/support", json={"betreff": "Login geht nicht", "prioritaet": "hoch"}).json()["id"]
        assert c.get("/api/stats").json()["support_offen"] == 1
        c.put(f"/api/support/{sid}", json={"status": "geschlossen"})
        assert c.get("/api/stats").json()["support_offen"] == 0


def test_aggregator_netzwerk(tmp_path):
    class _R:
        status_code = 200

        def json(self):
            return [
                {"id": "memory", "brand": "Dizz Memory", "status": "aktiv"},
                {"id": "admin", "brand": "Dizz Admin", "status": "aktiv"},
                {"id": "systeminfo", "status": "aktiv"}]

    with _client(tmp_path, http_get=lambda url: _R()) as c:
        n = c.get("/api/netzwerk").json()
        # eigene App + reine System-Kachel ausgeblendet
        assert n["ok"] is True and {a["id"] for a in n["apps"]} == {"memory"}
        assert n["online"] == 1


def test_aggregator_core_offline(tmp_path):
    def boom(url):
        raise RuntimeError("kein Core")

    with _client(tmp_path, http_get=boom) as c:
        n = c.get("/api/netzwerk").json()
        assert n["ok"] is False and n["apps"] == []


def test_euer_ausgaben_offline_nur_einnahmen(tmp_path):
    """V16 best-effort: ist Money/Core offline, bleibt die EÜR nutzbar und zeigt
    EHRLICH nur die Einnahmen (ausgaben_ok=False, ausgaben_cent=0)."""
    def boom(url):
        raise RuntimeError("kein Core")

    with _client(tmp_path, http_get=boom) as c:
        e = c.get(f"/api/euer?jahr={date.today().year}").json()
        assert e["ausgaben_ok"] is False and e["ausgaben_cent"] == 0
        assert e["ueberschuss_cent"] == e["einnahmen_netto_cent"]
        assert "nicht abrufbar" in e["hinweis"]


def test_geschaeft_ausgaben_parst_money_euer():
    """V16: die Aggregator-Funktion liest Moneys EÜR (Core-Relay) und liefert nur die
    Kategorien mit Ausgaben > 0, absteigend sortiert."""
    from adminapp.aggregat import geschaeft_ausgaben

    class _R:
        status_code = 200

        def json(self):
            return {"ok": True, "euer": {"ausgaben": 30000, "einnahmen": 5000, "je_kategorie": [
                {"kategorie_name": "Miete", "steuer_art": "Betriebsausgabe",
                 "einnahmen": 0, "ausgaben": 20000},
                {"kategorie_name": "Nebenerlös", "ausgaben": 0, "einnahmen": 5000},
                {"kategorie_name": "Software", "steuer_art": "", "ausgaben": 10000}]}}

    out = geschaeft_ausgaben(2026, core_url="http://core", http_get=lambda url: _R())
    assert out["ok"] is True and out["ausgaben_cent"] == 30000
    # nur Ausgabe-Kategorien, absteigend (Miete vor Software), Einnahme-Kategorie raus
    assert [k["kategorie"] for k in out["je_kategorie"]] == ["Miete", "Software"]
    # V16/(b): steuer-relevante Einnahmen separat erfasst (informativ)
    assert out["einnahmen_cent"] == 5000
    assert [k["kategorie"] for k in out["einnahmen_je_kategorie"]] == ["Nebenerlös"]


def test_geschaeft_ausgaben_offline_leer():
    from adminapp.aggregat import geschaeft_ausgaben

    def boom(url):
        raise RuntimeError("kein Core")

    out = geschaeft_ausgaben(2026, core_url="http://core", http_get=boom)
    assert out["ok"] is False and out["ausgaben_cent"] == 0 and out["je_kategorie"] == []


def test_mini_dizzi_ki_smoke(tmp_path):
    class _R:
        status_code = 200

        def json(self):
            return {"message": {"content": json.dumps({"antwort": "Aktuell 0 Kunden."})}}

    with _client(tmp_path, http_post=lambda url, json: _R()) as c:
        out = c.post("/api/ki/frage", json={"frage": "Wie viele Kunden?"}).json()
        assert "antwort" in out


def test_summary_und_mcp_namensraum(tmp_path):
    with _client(tmp_path) as c:
        assert "Umsatz" in c.get("/api/summary").text     # KPI-Kachel
    # MCP-Tools tragen den admin_-Namensraum
    from adminapp.manifest import MANIFEST
    assert "admin_geschaefts_kpis" in MANIFEST.mcp.tools


# ===== UI/UX P1: KPI-Verlauf (Trend + MRR-Zerlegung) + Executive-Cockpit =====

def test_kpi_verlauf_struktur_und_aufbauend(tmp_path):
    """P1c: /api/kpi/verlauf liefert Ist + Trend + Sparkline-Reihe + MRR-Zerlegung.
    Am ersten Tag (nur heutiger Snapshot) ist der Trend ehrlich „aufbauend" (delta
    None) und die Zerlegung im Status 'aufbauend' — kein Heute-gegen-heute-Vergleich."""
    with _client(tmp_path) as c:
        d = c.get("/api/kpi/verlauf").json()
        assert set(d) >= {"ist", "trend", "verlauf", "mrr_zerlegung", "punkte"}
        assert d["punkte"] == 1                       # genau der heutige Snapshot
        assert d["trend"]["umsatz_cent"]["delta"] is None
        assert d["mrr_zerlegung"]["status"] == "aufbauend"
        # zweiter Abruf schreibt KEINEN zusätzlichen Tagespunkt (idempotent je Tag)
        assert c.get("/api/kpi/verlauf").json()["punkte"] == 1


def test_kpi_verlauf_trend_mit_historie(tmp_path):
    """Mit einem zurückdatierten Snapshot wird der Trend echt berechnet (delta +,
    Richtung up bei steigendem Umsatz)."""
    from appkit.db import new_id, now_iso
    with _client(tmp_path) as c:
        dom = c.app.state.domain
        # Basis-Snapshot vor 40 Tagen mit Umsatz 0 einspielen
        alt = (date.today() - timedelta(days=40)).isoformat()
        dom.db.get_conn().execute(
            "INSERT INTO kpi_snapshot (id,user_id,datum,umsatz_cent,mrr_cent,offen_cent,"
            "offen_n,ueberfaellig_n,kunden_n,mrr_posten,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_id(), "dizzi", alt, 0, 0, 0, 0, 0, 0, "{}", now_iso(), now_iso()))
        dom.db.get_conn().commit()
        # Umsatz erzeugen: Rechnung stellen + bezahlen
        rid = c.post("/api/rechnungen", json={
            "positionen": [{"einzelpreis_cent": 10000, "ust_satz": 0}]}).json()["id"]
        c.post(f"/api/rechnungen/{rid}/stellen")
        c.post(f"/api/rechnungen/{rid}/bezahlt")
        t = c.get("/api/kpi/verlauf?tage=30").json()["trend"]["umsatz_cent"]
        assert t["delta"] == 10000 and t["richtung"] == "up" and t["basis_datum"] == alt


def test_mrr_zerlegung_komponenten(tmp_path):
    """MRR-Zerlegung deterministisch: Expansion (Preis rauf), Churn (Produkt weg),
    Netto = neu + Expansion − Contraction − Churn."""
    import json as _json
    with _client(tmp_path) as c:
        pid = c.post("/api/produkte", json={
            "name": "Abo A", "preis_cent": 1000, "abo_intervall": "monatlich"}).json()["id"]
        dom = c.app.state.domain
        assert dom.mrr_zerlegung("dizzi", None)["status"] == "aufbauend"
        basis = {"datum": "2020-01-01",
                 "mrr_posten": _json.dumps({pid: 600, "ghost": 300})}
        z = dom.mrr_zerlegung("dizzi", basis)
        assert z["expansion_cent"] == 400      # 1000 − 600
        assert z["churn_cent"] == 300          # ghost weg
        assert z["neu_cent"] == 0 and z["contraction_cent"] == 0
        assert z["netto_cent"] == 100          # 0 + 400 − 0 − 300


def _cockpit_get(url):
    """Mockt Core /api/panels/{id}/stats je Domäne (Vertrags-Stats-Form)."""
    import re
    m = re.search(r"/panels/([^/]+)/stats", url)
    pid = m.group(1) if m else ""
    data = {
        "finanzen": {"status": "ok", "online": True, "url": "http://127.0.0.1:8210",
                     "kpis": [{"id": "konten", "label": "Konten", "value": 3},
                              {"id": "netto", "label": "Nettovermögen", "value": "12.000 €"}]},
        "kommunikation": {"status": "platzhalter", "panel": "kommunikation"},
        "management": {"status": "ok", "online": False, "url": "http://127.0.0.1:8213"},
    }.get(pid)

    class _R:
        status_code = 200 if data is not None else 404

        def json(self):
            return data or {}
    return _R()


def test_cockpit_waehlt_kpi_und_deeplink(tmp_path):
    """P1a: das Cockpit wählt je Domäne die führungsrelevante KPI (netto vor konten),
    setzt den Deep-Link und markiert Platzhalter/Offline-Apps als offline."""
    with _client(tmp_path, http_get=_cockpit_get) as c:
        co = c.get("/api/cockpit").json()
        kac = {k["id"]: k for k in co["kacheln"]}
        assert kac["finanzen"]["online"] is True
        assert kac["finanzen"]["kpi"]["id"] == "netto"          # bevorzugt vor 'konten'
        assert kac["finanzen"]["url"] == "http://127.0.0.1:8210"
        assert "plans" not in kac          # Plans in Admin verschmolzen ⇒ keine Schwester-Kachel mehr
        assert kac["kommunikation"]["online"] is False          # Platzhalter
        assert kac["management"]["online"] is False             # online=False


def test_cockpit_core_offline(tmp_path):
    def boom(url):
        raise RuntimeError("kein Core")

    with _client(tmp_path, http_get=boom) as c:
        co = c.get("/api/cockpit").json()
        assert co["ok"] is False
        assert all(k["online"] is False and k["kpi"] is None for k in co["kacheln"])


# ===== Studienverwaltung (P-Stud-1) =========================================

def _bildungsweg(c, **kw):
    body = {"institution": "Universität Bayreuth", "studiengang": "Informatik",
            "abschluss": "bachelor", "ects_gesamt": 180, "start_semester": "WS2024",
            "regelstudienzeit": 6, "max_versuche": 3}
    body.update(kw)
    return c.post("/api/studien", json=body).json()["id"]


def test_bildungsweg_crud_und_validierung(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/studien", json={"institution": "", "studiengang": ""}).status_code == 400
        bw = _bildungsweg(c)
        assert len(c.get("/api/studien").json()) == 1
        assert c.get(f"/api/studien/{bw}").json()["abschluss"] == "bachelor"
        # Enum-Coercion: unbekannte Art ⇒ Default
        c.put(f"/api/studien/{bw}", json={"art": "quatsch", "hauptfach": "Theoretische Informatik"})
        d = c.get(f"/api/studien/{bw}").json()
        assert d["art"] == "universitaet" and d["hauptfach"] == "Theoretische Informatik"
        # Lösch-Kaskade: Modul + Frist mitlöschen
        c.post(f"/api/studien/{bw}/module", json={"name": "M", "ects": 5})
        c.post(f"/api/studien/{bw}/fristen", json={"titel": "F", "faellig_am": "2026-01-01"})
        assert c.delete(f"/api/studien/{bw}").json()["ok"] is True
        assert c.get("/api/studien").json() == []
        assert c.get(f"/api/studien/{bw}/module").json() == []


def test_modul_ergebnis_versuch_logik(tmp_path):
    with _client(tmp_path) as c:
        bw = _bildungsweg(c)
        mid = c.post(f"/api/studien/{bw}/module",
                     json={"name": "Analysis I", "ects": 9, "bereich": "hauptfach"}).json()["id"]
        # Bestehen: Status + ECTS + Note
        r = c.post(f"/api/module/{mid}/ergebnis", json={"bestanden": True, "note": 1.7}).json()
        assert r["status"] == "bestanden" and r["versuch_nr"] == 1
        m = c.get(f"/api/studien/{bw}/module").json()[0]
        assert m["ects_erreicht"] == 9 and m["note"] == 1.7
        # Durchfallen bis zum endgültigen Nichtbestehen (Default 3 Versuche)
        mid2 = c.post(f"/api/studien/{bw}/module", json={"name": "Analysis II", "ects": 9}).json()["id"]
        assert c.post(f"/api/module/{mid2}/ergebnis", json={"bestanden": False}).json()["status"] == "nicht_bestanden"
        assert c.post(f"/api/module/{mid2}/ergebnis", json={"bestanden": False}).json()["status"] == "nicht_bestanden"
        r3 = c.post(f"/api/module/{mid2}/ergebnis", json={"bestanden": False}).json()
        assert r3["status"] == "endgueltig" and r3["endgueltig"] is True and r3["versuch_nr"] == 3


def test_studien_cockpit_aggregation(tmp_path):
    with _client(tmp_path) as c:
        bw = _bildungsweg(c)
        a = c.post(f"/api/studien/{bw}/module", json={"name": "A", "ects": 6, "bereich": "hauptfach"}).json()["id"]
        b = c.post(f"/api/studien/{bw}/module", json={"name": "B", "ects": 12, "bereich": "nebenfach"}).json()["id"]
        c.post(f"/api/module/{a}/ergebnis", json={"bestanden": True, "note": 2.0})
        c.post(f"/api/module/{b}/ergebnis", json={"bestanden": True, "note": 1.0})
        co = c.get(f"/api/studien/{bw}/cockpit").json()
        assert co["ects"]["erreicht"] == 18 and co["ects"]["prozent"] == 10
        # ECTS-gewichteter Schnitt: (2.0*6 + 1.0*12)/18 = 1.33
        assert co["note_schnitt"] == 1.33
        assert co["fachsemester"] >= 1  # aus WS2024 berechnet
        bereiche = {x["bereich"]: x["erreicht"] for x in co["ects"]["je_bereich"]}
        assert bereiche == {"hauptfach": 6, "nebenfach": 12}


def test_studienfristen_waechter_und_warnungen(tmp_path):
    with _client(tmp_path) as c:
        bw = _bildungsweg(c)
        c.post(f"/api/studien/{bw}/fristen",
               json={"titel": "Klausuranmeldung", "art": "anmeldung", "faellig_am": "2020-01-01"})
        # endgültig nicht bestandenes Modul ⇒ Warnung
        mid = c.post(f"/api/studien/{bw}/module", json={"name": "Pflicht X", "ects": 5, "max_versuche": 1}).json()["id"]
        c.post(f"/api/module/{mid}/ergebnis", json={"bestanden": False})  # 1 Versuch, max 1 ⇒ endgueltig
        w = c.get("/api/waechter").json()
        assert len(w["faellige_studienfristen"]) == 1
        assert any(x["stufe"] == "endgueltig" for x in w["studien_risiko"])
        assert w["gesamt"] >= 2
        # MCP-/Übersichts-Endpunkte (Literal-Routen vor {bw})
        assert "studien" in c.get("/api/studien/uebersicht").json()
        assert c.get("/api/studien/warnungen").json()["warnungen"]
        assert len(c.get("/api/studienfristen").json()) == 1
