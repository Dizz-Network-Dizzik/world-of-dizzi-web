"""UStVA-Datenschicht — Persistenz + CRUD (M4-1, docs/68 §3/§11). DB-Schicht UNTER
dem Vertrag (``test_ustva_vertrag.py`` bleibt der Design-Zaun, unangetastet).
Schwerpunkt:

  * Regel-CRUD (Kategorie-Default, Upsert je ``kategorie_id``) über den HTTP-Pfad,
  * Klassifikations-Override (Upsert je ``buchung_id``, ``quelle=MANUELL``),
  * **Vertrags-Validierung VOR der Persistenz** — ein strukturell ungültiger
    Entscheid (Satz-Widerspruch, §15-Pflichtfeld, TEILWEISE) erreicht die DB nie,
  * der **U-1-Arbeitsvorrat** „offene Buchungen des Zeitraums" = die Lese-Sicht des
    Vollständigkeits-Wächters (Override → Regel → sonst offen; ``netto==0`` geklärt),
  * Ledger-Sorgfaltskern **byte-gleich** (U-4) + generische DSGVO-Lösch-Kaskade.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm
from moneyapp.ustva import persistenz as up, vertrag as uv

USER = mm.DEFAULT_USER_ID


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _stack(tmp_path):
    """App (HTTP) + eine an DIESELBE DB gebundene Speicher-Schicht — für die
    Methoden-Nähte (offene_buchungen synthetisch, DSGVO), die den vollen
    Ledger-Seed nicht brauchen."""
    app = mm.build_app(data_dir=tmp_path)
    db = mm.Database(mm.default_db_path(mm.APP_ID, data_root=tmp_path))
    return app, db, up.UstSpeicher(db)


# --------------------------------------------------------------- ust_regeln (CRUD)

def test_regel_crud_und_upsert(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/ust/regeln", json={
            "kategorie_id": "kat-umsatz", "ust_kategorie": "umsatz_19",
            "satz_promille": 190}).json()
        assert r["kategorie_id"] == "kat-umsatz" and r["satz_promille"] == 190
        # Liste + Einzel-Holen
        assert any(x["kategorie_id"] == "kat-umsatz" for x in c.get("/api/ust/regeln").json())
        assert c.get("/api/ust/regeln/kat-umsatz").json()["ust_kategorie"] == "umsatz_19"
        # Upsert je kategorie_id: erneutes POST UPDATET, legt KEINE Dublette an
        c.post("/api/ust/regeln", json={
            "kategorie_id": "kat-umsatz", "ust_kategorie": "umsatz_7", "satz_promille": 70})
        liste = [x for x in c.get("/api/ust/regeln").json() if x["kategorie_id"] == "kat-umsatz"]
        assert len(liste) == 1 and liste[0]["ust_kategorie"] == "umsatz_7"
        # Soft-Delete + 404 danach
        assert c.delete("/api/ust/regeln/kat-umsatz").json()["ok"]
        assert c.get("/api/ust/regeln/kat-umsatz").status_code == 404
        assert c.delete("/api/ust/regeln/kat-umsatz").status_code == 404
        # Neu-Anlage nach Löschen ok (Partial-Unique-Index lässt Soft-Deletes fallen)
        assert c.post("/api/ust/regeln", json={
            "kategorie_id": "kat-umsatz", "ust_kategorie": "umsatz_19",
            "satz_promille": 190}).status_code == 200


def test_regel_validierung_faellt_am_vertrag(tmp_path):
    """Der Vertrag ist der Torwächter: jeder Widerspruch ⇒ KonfigFehler ⇒ 400,
    NICHTS Ungültiges wird persistiert (U-1/U-2-Geist)."""
    with _client(tmp_path) as c:
        # Satz widerspricht der Kategorie (umsatz_19 verlangt 190)
        assert c.post("/api/ust/regeln", json={
            "kategorie_id": "k1", "ust_kategorie": "umsatz_19", "satz_promille": 70}).status_code == 400
        # unbekannte UStKategorie
        assert c.post("/api/ust/regeln", json={
            "kategorie_id": "k2", "ust_kategorie": "quatsch"}).status_code == 400
        # NICHT_ABZIEHBAR ohne Verbots-Grund
        assert c.post("/api/ust/regeln", json={
            "kategorie_id": "k3", "ust_kategorie": "eingang_vst", "satz_promille": 190,
            "vorsteuer_status": "nicht_abziehbar"}).status_code == 400
        # TEILWEISE ist in v1 gesperrt (§15 Abs.4 = M4-3)
        assert c.post("/api/ust/regeln", json={
            "kategorie_id": "k4", "ust_kategorie": "eingang_vst", "satz_promille": 190,
            "vorsteuer_status": "teilweise"}).status_code == 400
        # Vorsteuer-Status an einer Nicht-§15-Kategorie
        assert c.post("/api/ust/regeln", json={
            "kategorie_id": "k5", "ust_kategorie": "umsatz_19", "satz_promille": 190,
            "vorsteuer_status": "abziehbar"}).status_code == 400
        # nach fünf Fehlversuchen ist die Regel-Tabelle leer
        assert c.get("/api/ust/regeln").json() == []


# ------------------------------------------------ ust_klassifikationen (Override)

def test_klassifikation_override_crud(tmp_path):
    with _client(tmp_path) as c:
        # MIT_SPLIT-Kategorie: brutto wird in netto/ust zerlegt (11900 @19% → 10000/1900)
        k = c.post("/api/ust/klassifikationen", json={
            "buchung_id": "b1", "ust_kategorie": "umsatz_19", "satz_promille": 190,
            "brutto_cent": 11900}).json()
        assert k["quelle"] == "manuell" and k["netto_cent"] == 10000 and k["ust_cent"] == 1900
        assert k["entschieden_am"]      # Audit-Zeitstempel gesetzt
        # Liste (gesamt + gefiltert je Buchung)
        assert len(c.get("/api/ust/klassifikationen").json()) == 1
        assert len(c.get("/api/ust/klassifikationen?buchung_id=b1").json()) == 1
        assert c.get("/api/ust/klassifikationen?buchung_id=fremd").json() == []
        # Upsert je buchung_id: erneutes POST UPDATET
        c.post("/api/ust/klassifikationen", json={
            "buchung_id": "b1", "ust_kategorie": "umsatz_7", "satz_promille": 70,
            "brutto_cent": 10700})
        rows = c.get("/api/ust/klassifikationen").json()
        assert len(rows) == 1 and rows[0]["ust_kategorie"] == "umsatz_7"
        # Soft-Delete (Override zurücknehmen) + 404 danach
        assert c.delete("/api/ust/klassifikationen/b1").json()["ok"]
        assert c.get("/api/ust/klassifikationen").json() == []
        assert c.delete("/api/ust/klassifikationen/b1").status_code == 404


def test_klassifikation_belegausweis_schlaegt_rechenweg(tmp_path):
    """§7: weist der Beleg die USt aus (``ust_cent``), gilt der Belegbetrag —
    nicht der rechnerische Split."""
    with _client(tmp_path) as c:
        k = c.post("/api/ust/klassifikationen", json={
            "buchung_id": "b-beleg", "ust_kategorie": "umsatz_19", "satz_promille": 190,
            "brutto_cent": 12000, "ust_cent": 2000}).json()
        assert k["netto_cent"] == 10000 and k["ust_cent"] == 2000   # Beleg, nicht 12000/1.19


def test_klassifikation_validierung_faellt_am_vertrag(tmp_path):
    with _client(tmp_path) as c:
        # MIT_SPLIT ohne brutto_cent ⇒ 400 (Rechnungs-Zerlegung ist Pflicht)
        assert c.post("/api/ust/klassifikationen", json={
            "buchung_id": "b1", "ust_kategorie": "umsatz_19", "satz_promille": 190}).status_code == 400
        # unbekannte Kategorie
        assert c.post("/api/ust/klassifikationen", json={
            "buchung_id": "b2", "ust_kategorie": "quatsch"}).status_code == 400
        # §15-Kategorie ohne Vorsteuer-Status
        assert c.post("/api/ust/klassifikationen", json={
            "buchung_id": "b3", "ust_kategorie": "eingang_vst", "satz_promille": 190,
            "brutto_cent": 11900}).status_code == 400
        # gültige §15-Klassifikation MIT Status
        assert c.post("/api/ust/klassifikationen", json={
            "buchung_id": "b3", "ust_kategorie": "eingang_vst", "satz_promille": 190,
            "brutto_cent": 11900, "vorsteuer_status": "abziehbar"}).status_code == 200


# ---------------------------------------------------------- U-1-Arbeitsvorrat

def test_offene_arbeitsvorrat_ist_lesesicht_des_wachters(tmp_path):
    """Der Arbeitsvorrat spiegelt exakt ``klassifiziere`` (Override → Regel →
    sonst offen; ``netto==0`` = interner Transfer ⇒ KEIN_UMSATZ = geklärt)."""
    app, db, sp = _stack(tmp_path)
    sp.regel_speichern(USER, uv.KlassifikationsRegel(
        kategorie_id="kat-food", ust_kategorie=uv.UStKategorie.EINGANG_OHNE_VST))
    sp.klassifikation_speichern(USER, uv.Klassifikation(
        buchung_id="b-override", ust_kategorie=uv.UStKategorie.UMSATZ_STFREI_OHNE_VST,
        quelle=uv.KlassifikationsQuelle.MANUELL))
    bewegungen = [
        {"id": "b-open", "netto": -5000, "kategorie_id": "kat-unbekannt"},     # offen
        {"id": "b-rule", "netto": -3000, "kategorie_id": "kat-food"},          # Regel greift
        {"id": "b-transfer", "netto": 0, "kategorie_id": "kat-unbekannt"},     # KEIN_UMSATZ
        {"id": "b-override", "netto": -2000, "kategorie_id": "kat-unbekannt"}, # Override greift
    ]
    z = uv.UStVAZeitraum(jahr=2026, typ=uv.ZeitraumTyp.QUARTAL, nummer=2)
    res = sp.offene_buchungen(USER, z, bewegungen)
    assert res["zeitraum"] == "2026-Q2" and res["von"] == "2026-04-01"
    assert res["offen_anzahl"] == 1 and res["klassifiziert_anzahl"] == 3
    assert res["gesamt"] == 4 and res["vollstaendig"] is False
    assert [o["id"] for o in res["offen"]] == ["b-open"]


def test_offene_http_ueber_echten_ledger(tmp_path):
    """Der HTTP-Pfad: eine echte Buchung im Zeitraum ist zuerst offen, ein
    Override klärt sie — der injizierte ``bewegungen_fn`` liest den echten Ledger."""
    with _client(tmp_path) as c:
        bank = c.post("/api/konten", json={"name": "Bank", "typ": "asset"}).json()["id"]
        lohn = c.post("/api/konten", json={"name": "Umsatz", "typ": "income"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": lohn, "nach_konto": bank,
                                       "betrag": "1000,00", "datum": "2026-05-15"})
        offen = c.get("/api/ust/offene?jahr=2026&typ=quartal&nummer=2").json()
        assert offen["offen_anzahl"] == 1 and offen["vollstaendig"] is False
        bid = offen["offen"][0]["id"]
        # Buchung außerhalb des Fensters taucht NICHT auf (Q1 leer)
        assert c.get("/api/ust/offene?jahr=2026&typ=quartal&nummer=1").json()["offen_anzahl"] == 0
        # Override klärt die Buchung ⇒ Zeitraum vollständig
        c.post("/api/ust/klassifikationen", json={
            "buchung_id": bid, "ust_kategorie": "umsatz_stfrei_ohne_vst"})
        klar = c.get("/api/ust/offene?jahr=2026&typ=quartal&nummer=2").json()
        assert klar["offen_anzahl"] == 0 and klar["vollstaendig"] is True


def test_offene_zeitraum_validierung(tmp_path):
    with _client(tmp_path) as c:
        # Quartal 9 gibt es nicht ⇒ 400 (U-8, konstruktive Zeitraum-Validierung)
        assert c.get("/api/ust/offene?jahr=2026&typ=quartal&nummer=9").status_code == 400
        # Monat 13 ⇒ 400
        assert c.get("/api/ust/offene?jahr=2026&typ=monat&nummer=13").status_code == 400
        # unbekannter Typ ⇒ 400
        assert c.get("/api/ust/offene?jahr=2026&typ=jahr_befreit&nummer=1").status_code == 400
        # gültig ⇒ 200
        assert c.get("/api/ust/offene?jahr=2026&typ=monat&nummer=6").status_code == 200


# ------------------------------------------------- Row → Vertrag (spricht Typen)

def test_persistenz_spricht_vertragstypen(tmp_path):
    """Rekonstruktion aus der Zeile ergibt EXAKT den Vertrags-Typ (der
    Klassifikator spricht Typen, nicht Rows) — inkl. konstruktivem Split."""
    app, db, sp = _stack(tmp_path)
    sp.regel_speichern(USER, uv.KlassifikationsRegel(
        kategorie_id="kat-vst", ust_kategorie=uv.UStKategorie.EINGANG_VST,
        satz_promille=190, vorsteuer_status=uv.VorsteuerStatus.ABZIEHBAR))
    regel = sp.regel(USER, "kat-vst")
    assert isinstance(regel, uv.KlassifikationsRegel)
    assert regel.ust_kategorie is uv.UStKategorie.EINGANG_VST
    assert regel.vorsteuer_status is uv.VorsteuerStatus.ABZIEHBAR

    sp.klassifikation_speichern(USER, up._klassifikation_bauen(up.KlassifikationIn(
        buchung_id="b-vst", ust_kategorie="eingang_vst", satz_promille=190,
        brutto_cent=11900, vorsteuer_status="abziehbar")))
    kmap = sp.klassifikationen_map(USER)
    k = kmap["b-vst"]
    assert isinstance(k, uv.Klassifikation) and k.split is not None
    assert k.split.brutto_cent == 11900 and k.split.netto_cent == 10000
    assert k.quelle is uv.KlassifikationsQuelle.MANUELL


# ---------------------------------------------------- U-4 + DSGVO-Lösch-Kaskade

def test_ledger_byte_gleich_und_tabellen_getrennt_u4(tmp_path):
    """U-4: die USt-Achse lebt in SEITEN-Tabellen; der Sorgfaltskern (buchungen/
    postings/konten/kategorien) trägt KEINE USt-Spalte, der Ledger bleibt funktional."""
    app, db, sp = _stack(tmp_path)
    hat_deleted = dict(db.user_tabellen())
    for t in ("ust_regeln", "ust_klassifikationen", "ust_zeitraeume", "ku_status"):
        assert hat_deleted.get(t) is True     # existiert + trägt deleted_at (DSGVO greift)
    conn = db.get_conn()
    for t in ("buchungen", "postings", "konten", "kategorien"):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
        assert not any(c.startswith("ust_") or c in ("satz_promille", "vorsteuer_status")
                       for c in cols)        # keine USt-Spalte bleedet in den Kern
    # der Ledger postet weiter balanciert (Balance-Invariante unberührt)
    with TestClient(app) as c:
        a = c.post("/api/konten", json={"name": "Bank", "typ": "asset"}).json()["id"]
        b = c.post("/api/konten", json={"name": "Lohn", "typ": "income"}).json()["id"]
        assert c.post("/api/buchungen", json={
            "von_konto": b, "nach_konto": a, "betrag": "500,00"}).status_code == 200


def test_dsgvo_kaskade_erfasst_ust_daten(tmp_path):
    """ust_regeln + ust_klassifikationen tragen user_id+deleted_at ⇒
    ``soft_delete_user``/``export_user`` greifen OHNE Per-App-Code."""
    app, db, sp = _stack(tmp_path)
    sp.regel_speichern(USER, uv.KlassifikationsRegel(
        kategorie_id="kat-x", ust_kategorie=uv.UStKategorie.UMSATZ_19, satz_promille=190))
    sp.klassifikation_speichern(USER, uv.Klassifikation(
        buchung_id="b-x", ust_kategorie=uv.UStKategorie.UMSATZ_STFREI_OHNE_VST,
        quelle=uv.KlassifikationsQuelle.MANUELL))

    exp = db.export_user(USER)
    assert exp["ust_regeln"] and exp["ust_klassifikationen"]

    zaehler = db.soft_delete_user(USER)
    assert zaehler.get("ust_regeln") and zaehler.get("ust_klassifikationen")

    with TestClient(app) as c:
        assert c.get("/api/ust/regeln").json() == []
        assert c.get("/api/ust/klassifikationen").json() == []
