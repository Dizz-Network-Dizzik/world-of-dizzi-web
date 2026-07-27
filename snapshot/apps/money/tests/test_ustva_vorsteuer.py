"""Vorsteuer-Rechner — §15-Abzug + §15-Abs.-4-Aufteilung (M4-3, docs/68 §7). Die
Rechen-/Erfassungs-Schicht UNTER dem Vertrag (``vorsteuer.py`` + die ``persistenz``-
Naht); ``vertrag.py`` bleibt der Design-Zaun (unangetastet — ``TEILWEISE`` wirft dort
weiter, die Aufteilung lebt als EIGENER dokumentierter Datensatz). Akzeptanz (docs/68
§11 M4-3): **Bewirtungs-Regel e2e** (VoSt 100 % ≠ EÜR 70 %) · **kein Abzug ohne
expliziten Status** · **Aufteilung nur mit erfasster Begründung**.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from moneyapp import main as mm
from moneyapp.ustva import persistenz as up, vertrag as uv, vorsteuer as vo

USER = mm.DEFAULT_USER_ID


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _stack(tmp_path):
    """App (HTTP) + an DIESELBE DB gebundene Speicher-Schicht — für die Methoden-
    Nähte (``vorsteuer_warnungen`` synthetisch), die keinen Ledger-Seed brauchen."""
    app = mm.build_app(data_dir=tmp_path)
    db = mm.Database(mm.default_db_path(mm.APP_ID, data_root=tmp_path))
    return app, db, up.UstSpeicher(db)


# ============================================================ reine vorsteuer.py-Logik

def test_aufteilen_konservativ_abgerundet():
    """Der abziehbare Anteil wird ABGERUNDET (nie mehr Vorsteuer als der Schlüssel
    exakt hergibt — fail-closed-Richtung wie das §19-Maß)."""
    assert vo.aufteilen(1900, 600) == 1140          # 60 % von 1900 = 1140,0
    assert vo.aufteilen(1901, 600) == 1140          # 1140,6 → abgerundet 1140 (nie 1141)
    assert vo.aufteilen(1900, 0) == 0
    assert vo.aufteilen(1900, 1000) == 1900
    for bad in (-1, 1001):
        with pytest.raises(uv.KonfigFehler):
            vo.aufteilen(1900, bad)
    with pytest.raises(uv.KonfigFehler):
        vo.aufteilen(-1, 600)                        # ust betragsmäßig


def test_aufteilung_pflicht_doku_erzwungen():
    """★ Akzeptanz: Aufteilung NUR mit erfasster Begründung — leere Doku ist
    konstruktiv unmöglich (§15 Abs. 4: nie ein stiller Prozentsatz)."""
    with pytest.raises(uv.KonfigFehler):
        vo.VorsteuerAufteilung(buchung_id="b", ust_cent=1900, abziehbar_promille=600,
                               abziehbar_cent=1140, schluessel="individuell", begruendung="")
    with pytest.raises(uv.KonfigFehler):
        vo.VorsteuerAufteilung(buchung_id="b", ust_cent=1900, abziehbar_promille=600,
                               abziehbar_cent=1140, schluessel="individuell", begruendung="   ")
    a = vo.VorsteuerAufteilung(buchung_id="b", ust_cent=1900, abziehbar_promille=600,
                               abziehbar_cent=1140, schluessel="flaechenschluessel",
                               begruendung="Büro 60 % betrieblich / 40 % privat")
    assert a.nicht_abziehbar_cent == 760 and a.anteil_prozent == 60.0
    assert a.schluessel is vo.AufteilungsSchluessel.FLAECHENSCHLUESSEL


def test_aufteilung_strikt_partiell():
    """100 % ist ABZIEHBAR, 0 % ist NICHT_ABZIEHBAR — beides gehört in die normale
    Klassifikation, nie in eine Aufteilung (die ist per Definition partiell)."""
    for promille in (0, 1000):
        with pytest.raises(uv.KonfigFehler):
            vo.VorsteuerAufteilung(buchung_id="b", ust_cent=1900, abziehbar_promille=promille,
                                   abziehbar_cent=vo.aufteilen(1900, promille),
                                   schluessel="individuell", begruendung="x")


def test_aufteilung_betrag_folgt_dem_schluessel():
    """``abziehbar_cent`` ist aus dem dokumentierten Anteil ABGELEITET — ein frei
    daneben gesetzter Betrag ist konstruktiv unmöglich (wie ``UstSplit``)."""
    with pytest.raises(uv.KonfigFehler):
        vo.VorsteuerAufteilung(buchung_id="b", ust_cent=1900, abziehbar_promille=600,
                               abziehbar_cent=1200,   # != aufteilen(1900,600)=1140
                               schluessel="individuell", begruendung="x")


def test_aufteilung_grund_nur_echte_15abs4_faelle():
    """Der NICHT-abziehbare Teil dient steuerfreier Verwendung (§15 Abs. 2) ODER
    der privaten Sphäre — die Voll-Verbots-Gründe (keine Rechnung, §15 Abs. 1a)
    sind KEINE Aufteilungs-Gründe."""
    for grund in ("steuerfreie_verwendung", "privat"):
        vo.VorsteuerAufteilung(buchung_id="b", ust_cent=1900, abziehbar_promille=600,
                               abziehbar_cent=1140, schluessel="individuell",
                               begruendung="x", grund_nicht_abziehbar=grund)
    for grund in ("keine_ordnungsgemaesse_rechnung", "paragraf_15_1a", "kleinunternehmer_status"):
        with pytest.raises(uv.KonfigFehler):
            vo.VorsteuerAufteilung(buchung_id="b", ust_cent=1900, abziehbar_promille=600,
                                   abziehbar_cent=1140, schluessel="individuell",
                                   begruendung="x", grund_nicht_abziehbar=grund)


def test_aufteilung_aus_brutto_belegausweis_schlaegt_rechenweg():
    """§7: weist der Beleg die USt aus, gilt der Belegbetrag — nicht der rechnerische
    Split. Satz 0 / kein USt-Betrag ⇒ gegenstandslos (wirft)."""
    _, a = vo.aufteilung_aus_brutto("b", 11900, 190, 500, "individuell", "hälftig")
    assert a.ust_cent == 1900 and a.abziehbar_cent == 950
    _, a2 = vo.aufteilung_aus_brutto("b", 12000, 190, 500, "individuell", "x", ust_cent=2000)
    assert a2.ust_cent == 2000 and a2.abziehbar_cent == 1000       # Beleg 2000, nicht 12000/1,19
    with pytest.raises(uv.KonfigFehler):
        vo.aufteilung_aus_brutto("b", 10000, 0, 500, "individuell", "x")   # Satz 0 ⇒ keine USt


def test_abziehbare_vorsteuer_kein_abzug_ohne_status():
    """★ Akzeptanz: kein Abzug ohne expliziten Status — nur ABZIEHBAR zieht die
    volle Beleg-USt; NICHT_ABZIEHBAR (mit Grund) zieht 0. Kein stilles Default."""
    split = uv.split_aus_brutto(11900, 190)
    abz = uv.Klassifikation(buchung_id="b", ust_kategorie=uv.UStKategorie.EINGANG_VST,
                            quelle=uv.KlassifikationsQuelle.MANUELL, satz_promille=190,
                            split=split, vorsteuer_status=uv.VorsteuerStatus.ABZIEHBAR)
    assert vo.abziehbare_vorsteuer(abz) == 1900
    verbot = uv.Klassifikation(
        buchung_id="b", ust_kategorie=uv.UStKategorie.EINGANG_VST,
        quelle=uv.KlassifikationsQuelle.MANUELL, satz_promille=190, split=split,
        vorsteuer_status=uv.VorsteuerStatus.NICHT_ABZIEHBAR,
        vorsteuer_verbot_grund=uv.VorsteuerVerbotsGrund.PRIVAT)
    assert vo.abziehbare_vorsteuer(verbot) == 0
    # Der Vertrag selbst sperrt ein EINGANG_VST OHNE Status (kein Default) — Re-Anker:
    with pytest.raises(uv.KonfigFehler):
        uv.Klassifikation(buchung_id="b", ust_kategorie=uv.UStKategorie.EINGANG_VST,
                          quelle=uv.KlassifikationsQuelle.MANUELL, satz_promille=190, split=split)


def test_bewirtung_vorsteuer_100_prozent_nicht_70():
    """★ Akzeptanz (Bewirtungs-Falle): Vorsteuer zu 100 % abziehbar, obwohl
    ertragsteuerlich nur 70 % Betriebsausgabe (§15 Abs. 1a S. 2 vs. §4 Abs. 5 EStG)."""
    assert vo.bewirtung_vorsteuer(1900) == 1900          # volle VoSt, NIE 0,7·1900=1330
    v = vo.bewirtung_vergleich(10000, 1900)
    assert v["vorsteuer_abziehbar_cent"] == 1900         # USt-Achse: 100 %
    assert v["euer_betriebsausgabe_cent"] == 7000        # EÜR-Achse: 70 % (getrennte Welt)


def test_beleg_pflicht_verletzt_nur_bei_abziehbar():
    """Warnregel „ABZIEHBAR ohne Beleg-Ref": nur ein Abzug braucht den Nachweis."""
    A = uv.VorsteuerStatus.ABZIEHBAR
    assert vo.beleg_pflicht_verletzt(A, "") is True
    assert vo.beleg_pflicht_verletzt(A, "admin:dokument:x7") is False
    assert vo.beleg_pflicht_verletzt(A, "irgendwas") is True          # falsches Präfix zählt nicht
    assert vo.beleg_pflicht_verletzt(uv.VorsteuerStatus.NICHT_ABZIEHBAR, "") is False
    assert vo.beleg_pflicht_verletzt(None, "") is False


def test_felder_anker_eingefroren():
    """Feld-Fläche der Aufteilung eingefroren (Erweiterung = bewusste Änderung)."""
    assert vo.AUFTEILUNG_FELDER == frozenset({
        "buchung_id", "ust_cent", "abziehbar_promille", "abziehbar_cent",
        "schluessel", "begruendung", "grund_nicht_abziehbar"})


# ============================================================ Persistenz + HTTP-Naht

def test_aufteilung_crud_und_upsert(tmp_path):
    with _client(tmp_path) as c:
        a = c.post("/api/ust/vorsteuer/aufteilung", json={
            "buchung_id": "b1", "satz_promille": 190, "brutto_cent": 11900,
            "abziehbar_promille": 600, "schluessel": "flaechenschluessel",
            "begruendung": "Büro 60 %", "grund_nicht_abziehbar": "privat"}).json()
        assert a["ust_cent"] == 1900 and a["abziehbar_cent"] == 1140
        assert a["nicht_abziehbar_cent"] == 760 and a["anteil_prozent"] == 60.0
        assert a["entschieden_am"]
        assert len(c.get("/api/ust/vorsteuer/aufteilung").json()) == 1
        # Upsert je buchung_id: erneutes POST UPDATET, legt keine Dublette an
        c.post("/api/ust/vorsteuer/aufteilung", json={
            "buchung_id": "b1", "satz_promille": 190, "brutto_cent": 11900,
            "abziehbar_promille": 300, "schluessel": "zeitschluessel", "begruendung": "neu 30 %"})
        rows = c.get("/api/ust/vorsteuer/aufteilung").json()
        assert len(rows) == 1 and rows[0]["abziehbar_cent"] == 570
        # Soft-Delete + 404 danach; Neu-Anlage nach Löschen ok (Partial-Unique-Index)
        assert c.delete("/api/ust/vorsteuer/aufteilung/b1").json()["ok"]
        assert c.delete("/api/ust/vorsteuer/aufteilung/b1").status_code == 404
        assert c.post("/api/ust/vorsteuer/aufteilung", json={
            "buchung_id": "b1", "satz_promille": 190, "brutto_cent": 11900,
            "abziehbar_promille": 600, "schluessel": "individuell",
            "begruendung": "wieder da"}).status_code == 200


def test_aufteilung_validierung_faellt_am_vertrag(tmp_path):
    """Der Torwächter: fehlende Doku / nicht-partiell / kein Brutto / Satz 0 ⇒ 400,
    NICHTS Ungültiges wird persistiert."""
    with _client(tmp_path) as c:
        basis = {"buchung_id": "b", "satz_promille": 190, "brutto_cent": 11900,
                 "abziehbar_promille": 600, "schluessel": "individuell"}
        assert c.post("/api/ust/vorsteuer/aufteilung", json={**basis, "begruendung": ""}).status_code == 400
        assert c.post("/api/ust/vorsteuer/aufteilung",
                      json={**basis, "abziehbar_promille": 1000, "begruendung": "x"}).status_code == 400
        assert c.post("/api/ust/vorsteuer/aufteilung",
                      json={**basis, "abziehbar_promille": 0, "begruendung": "x"}).status_code == 400
        assert c.post("/api/ust/vorsteuer/aufteilung", json={
            "buchung_id": "b", "satz_promille": 190, "abziehbar_promille": 600,
            "schluessel": "individuell", "begruendung": "x"}).status_code == 400   # kein brutto
        assert c.post("/api/ust/vorsteuer/aufteilung", json={
            "buchung_id": "b", "satz_promille": 0, "brutto_cent": 10000,
            "abziehbar_promille": 600, "schluessel": "individuell",
            "begruendung": "x"}).status_code == 400                                # keine USt
        assert c.get("/api/ust/vorsteuer/aufteilung").json() == []


def test_bewirtung_endpoint_e2e_100_vs_70(tmp_path):
    """★ Akzeptanz e2e über die HTTP-Naht: die Bewirtungs-Falle sichtbar —
    119,00 € brutto @19 % ⇒ VoSt 19,00 € (100 %) vs. EÜR-Betriebsausgabe 70,00 € (70 %)."""
    with _client(tmp_path) as c:
        b = c.get("/api/ust/vorsteuer/bewirtung?brutto_cent=11900&satz_promille=190").json()
        assert b["netto_cent"] == 10000 and b["ust_cent"] == 1900
        assert b["vorsteuer_abziehbar_cent"] == 1900        # 100 % — NICHT auf 70 % gekürzt
        assert b["euer_betriebsausgabe_cent"] == 7000       # 70 % lebt allein auf der EÜR-Achse
        assert c.get("/api/ust/vorsteuer/bewirtung?brutto_cent=10000&satz_promille=999").status_code == 400


def test_beleg_warnung_e2e_ueber_ledger(tmp_path):
    """★ Beleg-Ref-Kopplung e2e: eine ABZIEHBAR klassifizierte Eingangs-Buchung OHNE
    ``beleg_ref`` erzeugt eine Warnung; ist der Beleg verknüpft, ist sie sauber."""
    with _client(tmp_path) as c:
        bank = c.post("/api/konten", json={"name": "Bank", "typ": "asset"}).json()["id"]
        aufwand = c.post("/api/konten", json={"name": "Wareneinkauf", "typ": "expense"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": bank, "nach_konto": aufwand,
                                       "betrag": "119,00", "datum": "2026-05-15"})
        bid = c.get("/api/ust/offene?jahr=2026&typ=quartal&nummer=2").json()["offen"][0]["id"]
        # ABZIEHBAR klassifizieren (Beleg noch nicht verknüpft)
        c.post("/api/ust/klassifikationen", json={
            "buchung_id": bid, "ust_kategorie": "eingang_vst", "satz_promille": 190,
            "brutto_cent": 11900, "vorsteuer_status": "abziehbar"})
        w = c.get("/api/ust/vorsteuer/warnungen?jahr=2026&typ=quartal&nummer=2").json()
        assert w["warn_anzahl"] == 1 and w["geprueft_anzahl"] == 1 and w["sauber"] is False
        assert w["warnungen"][0]["id"] == bid and w["warnungen"][0]["abziehbar_cent"] == 1900
        assert w["warnungen"][0]["art"] == "klassifikation"
        # Beleg verknüpfen ⇒ Warnung verschwindet (Quartal Q1 hat ohnehin nichts)
        c.post("/api/buchungen/" + bid + "/beleg",
               json={"ref": "admin:dokument:beleg-7", "titel": "Rechnung"})
        w2 = c.get("/api/ust/vorsteuer/warnungen?jahr=2026&typ=quartal&nummer=2").json()
        assert w2["warn_anzahl"] == 0 and w2["geprueft_anzahl"] == 1 and w2["sauber"] is True
        assert c.get("/api/ust/vorsteuer/warnungen?jahr=2026&typ=quartal&nummer=9").status_code == 400


def test_warnung_deckt_aufteilung_ab(tmp_path):
    """Auch der abziehbare Teil einer §15-Abs.-4-Aufteilung ohne Beleg wird gewarnt
    (Lese-Sicht ``vorsteuer_warnungen`` über synthetische Bewegungen)."""
    app, db, sp = _stack(tmp_path)
    _, auf = vo.aufteilung_aus_brutto("b-teil", 11900, 190, 600, "individuell", "60 %")
    split = uv.split_aus_brutto(11900, 190)
    sp.aufteilung_speichern(USER, split, auf)
    z = uv.UStVAZeitraum(jahr=2026, typ=uv.ZeitraumTyp.QUARTAL, nummer=2)
    bew_ohne = [{"id": "b-teil", "datum": "2026-05-01", "netto": -11900, "beleg_ref": ""}]
    r = sp.vorsteuer_warnungen(USER, z, bew_ohne)
    assert r["warn_anzahl"] == 1 and r["warnungen"][0]["art"] == "aufteilung"
    assert r["warnungen"][0]["abziehbar_cent"] == 1140
    bew_mit = [{"id": "b-teil", "datum": "2026-05-01", "netto": -11900,
                "beleg_ref": "admin:dokument:x"}]
    assert sp.vorsteuer_warnungen(USER, z, bew_mit)["warn_anzahl"] == 0


def test_aufteilung_klaert_arbeitsvorrat(tmp_path):
    """Eine dokumentierte Aufteilung gilt im U-1-Arbeitsvorrat als GEKLÄRT — sonst
    bliebe die (vom Vertrag als TEILWEISE gesperrte) Buchung ewig offen."""
    app, db, sp = _stack(tmp_path)
    _, auf = vo.aufteilung_aus_brutto("b-teil", 11900, 190, 600, "individuell", "60 %")
    split = uv.split_aus_brutto(11900, 190)
    sp.aufteilung_speichern(USER, split, auf)
    z = uv.UStVAZeitraum(jahr=2026, typ=uv.ZeitraumTyp.QUARTAL, nummer=2)
    bew = [{"id": "b-teil", "datum": "2026-05-01", "netto": -11900, "kategorie_id": "x"},
           {"id": "b-offen", "datum": "2026-05-02", "netto": -5000, "kategorie_id": "x"}]
    res = sp.offene_buchungen(USER, z, bew)
    assert res["klassifiziert_anzahl"] == 1 and res["offen_anzahl"] == 1
    assert [o["id"] for o in res["offen"]] == ["b-offen"]


def test_aufteilung_dsgvo_und_ledger_u4(tmp_path):
    """Die Aufteilungs-Tabelle trägt user_id + deleted_at ⇒ generische DSGVO-Kaskade;
    der Ledger-Sorgfaltskern bleibt ohne USt-/Aufteilungs-Spalte (U-4)."""
    app, db, sp = _stack(tmp_path)
    assert dict(db.user_tabellen()).get("ust_vorsteuer_aufteilung") is True
    conn = db.get_conn()
    for t in ("buchungen", "postings", "konten"):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
        assert not any(c.startswith(("abziehbar", "aufteilung")) for c in cols)
    _, auf = vo.aufteilung_aus_brutto("b-x", 11900, 190, 600, "individuell", "60 %")
    sp.aufteilung_speichern(USER, uv.split_aus_brutto(11900, 190), auf)
    assert db.export_user(USER)["ust_vorsteuer_aufteilung"]
    assert db.soft_delete_user(USER).get("ust_vorsteuer_aufteilung")
    with TestClient(app) as c:
        assert c.get("/api/ust/vorsteuer/aufteilung").json() == []
