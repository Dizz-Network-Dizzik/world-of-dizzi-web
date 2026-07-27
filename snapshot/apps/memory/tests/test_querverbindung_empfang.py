"""Querverbindungs-Empfang: andere Netzwerk-Apps archivieren ein Element als Notiz.
Empfangs-Slot — idempotent (ref/Inhalt), auditiert, Ziel-Ordner, Tags→Labels."""

from __future__ import annotations

from fastapi.testclient import TestClient

from archivapp import main as am


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def test_archivieren_legt_notiz_an(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/querverbindung/archivieren", json={
            "titel": "EZB hält Zinsen", "inhalt": "Die Notenbank pausiert. Findwort: leitzins.",
            "quelle": "https://news/ezb", "app": "news",
            "tags": ["finanzen", "wichtig"], "ordner": "News/Finanzen",
            "explizit": True}).json()
        assert r["ok"] and r["status"] == "archiviert" and r["id"]
        det = c.get("/api/notizen/" + r["id"]).json()
        assert det["titel"] == "EZB hält Zinsen"
        assert det["quelle"] == "https://news/ezb" and det["import_quelle"] == "news"
        # Tag-Labels (normal) + das garantierte Herkunftslabel „News" (docs/26 §9.1)
        assert {l["name"] for l in det["labels"]} == {"finanzen", "wichtig", "News"}
        assert {l["name"] for l in det["labels"] if l.get("herkunft")} == {"News"}
        # Ziel-Ordner-Hierarchie angelegt
        assert {"News", "Finanzen"} <= {o["name"] for o in c.get("/api/ordner").json()}
        # archiviert ⇒ durchsuchbar
        assert c.get("/api/suche?q=leitzins").json()[0]["id"] == r["id"]


def test_idempotent_per_ref(tmp_path):
    with _client(tmp_path) as c:
        body = {"titel": "Asset 42", "inhalt": "Render-Metadaten.", "app": "creator",
                "ref": "creator:asset:42", "explizit": True}
        a = c.post("/api/querverbindung/archivieren", json=body).json()
        b = c.post("/api/querverbindung/archivieren", json=body).json()
        assert a["status"] == "archiviert" and b["status"] == "vorhanden"
        assert a["id"] == b["id"]
        assert len(c.get("/api/notizen").json()) == 1


def test_re_archiviert_nach_loeschung_ist_frische_notiz(tmp_path):
    """2.-Tiefe (Funktions-Forscher): löscht der Nutzer ein quer-archiviertes Element
    und die Quell-App re-synct denselben ``ref``, MUSS eine frische Notiz entstehen —
    NICHT stilles „vorhanden" (das die Re-Sync verschluckte) und KEIN UNIQUE-Crash.
    Deckt den dokumentierten ON-CONFLICT-Zweig (main.py ~1567, ``deleted_at=NULL``,
    Re-Archivieren nach Löschung) ab — den die 3 bestehenden Idempotenz-Tests nie traf."""
    with _client(tmp_path) as c:
        body = {"titel": "Asset 7", "inhalt": "Erste Fassung.", "app": "creator",
                "ref": "creator:asset:7", "explizit": True}
        a = c.post("/api/querverbindung/archivieren", json=body).json()
        assert a["status"] == "archiviert"
        # Nutzer löscht das Querverbindungs-Archiv wieder.
        assert c.delete("/api/notizen/" + a["id"]).json()["ok"]
        assert c.get("/api/notizen/" + a["id"]).status_code == 404
        # Quelle re-synct denselben ref ⇒ FRISCHE Notiz (neue id), nicht „vorhanden".
        b = c.post("/api/querverbindung/archivieren", json=body).json()
        assert b["status"] == "archiviert" and b["id"] != a["id"]
        # Genau EINE aktive Notiz; der Idempotenz-Beleg zeigt jetzt auf die neue (re-synct
        # ⇒ „vorhanden" mit der NEUEN id, nicht der alten gelöschten).
        assert len(c.get("/api/notizen").json()) == 1
        dritt = c.post("/api/querverbindung/archivieren", json=body).json()
        assert dritt["status"] == "vorhanden" and dritt["id"] == b["id"]


def test_idempotent_per_inhalt_und_default_ordner(tmp_path):
    with _client(tmp_path) as c:
        body = {"titel": "Brief", "inhalt": "Gleicher Inhalt.", "app": "creator",
                "explizit": True}  # kein ref
        c.post("/api/querverbindung/archivieren", json=body)
        zwei = c.post("/api/querverbindung/archivieren", json=body).json()
        assert zwei["status"] == "vorhanden"
        # Default-Ordner = App-Name, wenn kein ordner angegeben
        assert "creator" in {o["name"] for o in c.get("/api/ordner").json()}
        # auditiert
        assert any(e["action"] == "querverbindung_empfangen" for e in c.get("/api/audit").json())


def test_herkunftslabel_immer_vergeben(tmp_path):
    """docs/26 §9.1: jedes Querverbindungs-Archiv trägt GARANTIERT genau ein
    erkennbares Quell-App-Herkunftslabel — auch ganz ohne Tags."""
    with _client(tmp_path) as c:
        r = c.post("/api/querverbindung/archivieren", json={
            "titel": "Briefing", "inhalt": "Körper.", "app": "news",
            "explizit": True}).json()           # bewusst KEINE tags
        labels = c.get("/api/notizen/" + r["id"]).json()["labels"]
        herk = [l for l in labels if l["art"] == "herkunft"]
        assert [l["name"] for l in herk] == ["News"]   # genau eines, abgeleitet aus app
        assert herk[0]["herkunft"] is True             # abgeleitetes Bequemlichkeitsfeld
        # Es taucht als Herkunftslabel (System-Art) in der Label-Liste auf.
        liste = {l["name"]: l for l in c.get("/api/labels").json()}
        assert liste["News"]["art"] == "herkunft"


def test_herkunftslabel_unbekannte_app_titlecase_und_neben_tags(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/querverbindung/archivieren", json={
            "titel": "X", "inhalt": "Y", "app": "wetter",
            "tags": ["regen"], "explizit": True}).json()
        labels = {l["name"]: l for l in c.get("/api/notizen/" + r["id"]).json()["labels"]}
        # Unbekannte id ⇒ Titlecase; das normale Tag-Label bleibt normal.
        assert labels["Wetter"]["art"] == "herkunft"
        assert labels["regen"]["art"] == "normal"


def test_v11_tradingbot_herkunft_trading_und_sensibel(tmp_path):
    """V11 (docs/26 §10.1): Dizz Trading sendet mit der Manifest-id ``tradingbot``
    und IMMER ``sensibel=True`` (sensitivity hoechst). Empfang ⇒ Herkunftslabel
    „Trading" (NICHT „Tradingbot") + Notiz als sensibel markiert."""
    with _client(tmp_path) as c:
        r = c.post("/api/querverbindung/archivieren", json={
            "titel": "Flotten-Report", "inhalt": "Master-Fitness 1.16. Findwort: flottenreport.",
            "app": "tradingbot", "strom": "report", "ref": "trading:report:1",
            "sensibel": True, "explizit": True}).json()
        assert r["ok"] and r["status"] == "archiviert"
        det = c.get("/api/notizen/" + r["id"]).json()
        assert [l["name"] for l in det["labels"] if l["art"] == "herkunft"] == ["Trading"]
        assert det["sensibel"] is True   # hoechst ⇒ Memory-KI lokal_only


def test_labels_kpi_zaehlt_nur_nutzer_labels(tmp_path):
    """H-10(a): die Dashboard-„Labels"-KPI zählt NUR kuratierte Nutzer-Labels
    (art='normal'), nicht die System-Herkunfts-Labels — sonst stiege sie mit jeder
    neuen Querverbindung künstlich (+1 je Quell-App)."""
    with _client(tmp_path) as c:
        # Archiv mit Tag ⇒ 1 Nutzer-Label ("finanzen") + 1 Herkunfts-Label ("News").
        c.post("/api/querverbindung/archivieren", json={
            "titel": "EZB", "inhalt": "x", "app": "news",
            "tags": ["finanzen"], "explizit": True})
        assert {l["name"] for l in c.get("/api/labels").json()} == {"finanzen", "News"}
        kpi = {k["id"]: k["value"] for k in c.get("/api/summary").json()["kpis"]}
        assert kpi["labels"] == 1   # nur „finanzen", NICHT das Herkunfts-Label „News"


def test_herkunft_und_nutzerlabel_koexistieren(tmp_path):
    """docs/26 §9.5: Herkunfts-Labels sind eine EIGENE System-Art mit eigenem
    Namensraum — ein gleichnamiges Nutzer-Label wird weder befördert noch
    verschluckt; beide existieren getrennt nebeneinander."""
    with _client(tmp_path) as c:
        # Der Nutzer legt selbst ein normales Label „Money" an.
        mlid = c.post("/api/labels", json={"name": "Money"}).json()["id"]
        # finanzen archiviert ⇒ eigenes Herkunfts-„Money" (Map finanzen→Money).
        r = c.post("/api/querverbindung/archivieren", json={
            "titel": "Beleg", "inhalt": "x", "app": "finanzen", "explizit": True}).json()
        nach = {(l["name"], l["art"]): l for l in c.get("/api/labels").json()}
        # BEIDE existieren — keine Beförderung, keine Kollision.
        assert ("Money", "normal") in nach and ("Money", "herkunft") in nach
        assert nach[("Money", "normal")]["id"] == mlid          # Nutzer-Label unangetastet
        # Die Notiz trägt das HERKUNFTS-Money, nicht das Nutzer-Money.
        herk = [l for l in c.get("/api/notizen/" + r["id"]).json()["labels"]
                if l["art"] == "herkunft"]
        assert [l["name"] for l in herk] == ["Money"] and herk[0]["id"] != mlid
