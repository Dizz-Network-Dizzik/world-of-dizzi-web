"""ELSTER-Transport — Persistenz + CRUD (M1-1, docs/65 §3/§12). DB-Schicht UNTER
dem Vertrag (``test_elster_vertrag.py`` bleibt der Design-Zaun). Schwerpunkt:

  * Zugänge-CRUD (POST/GET/DELETE) über den HTTP-Pfad,
  * **Geheimnis-Freiheit der Responses** (I-2): kein ``pin_vault_key``, keine
    volle Steuernummer, NIE das Steuer-XML/Roh-Protokoll — die harte M1-1-Linie,
  * die Filing-Lauf-Historie + das Quittungs-Archiv als **read-only** Sicht,
  * der Doppel-Übermittlungs-Schutz (I-6) über die PERSISTIERTE Historie
    (``laeufe_paare`` → ``vertrag.pruefe_doppel``),
  * die generische DSGVO-Lösch-Kaskade greift auf die drei neuen Tabellen + die
    Hersteller-ID (``app_settings``) OHNE Per-App-Code.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from moneyapp import main as mm
from moneyapp.elster import persistenz as ep, vertrag as v

USER = mm.DEFAULT_USER_ID


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _stack(tmp_path):
    """App (HTTP) + eine an DIESELBE DB gebundene Speicher-Schicht — für die
    Motor-Nähte (Läufe/Quittungen), die es in M1-1 noch nicht per HTTP gibt."""
    app = mm.build_app(data_dir=tmp_path)
    db = mm.Database(mm.default_db_path(mm.APP_ID, data_root=tmp_path))
    return app, db, ep.ElsterSpeicher(db)


_FALL = v.SteuerFall(formular=v.FormularArt.EUER, jahr=2026)


def _datensatz(xml="<Nutzdaten>GEHEIM-XML-4711</Nutzdaten>"):
    return v.ElsterDatensatz(fall=_FALL, xml=xml,
                             quell_stand_hash=v.berechne_quell_stand("q-2026"),
                             formular_version="EUER-2026")


def _quittung(ticket="TT-9"):
    return v.Quittung(transferticket=ticket, uebermittelt_am="2026-07-05T10:00:00",
                      protokoll_roh=b"GEHEIM-PROTOKOLL-BYTES")


# ------------------------------------------------------------------ Zugänge-CRUD

def test_zugang_crud(tmp_path):
    with _client(tmp_path) as c:
        z = c.post("/api/elster/zugaenge", json={
            "zertifikat_pfad": r"elster\zert\test.pfx",
            "zertifikat_typ": "persoenlich",
            "steuernummer": "123/456/78901"}).json()
        zid = z["id"]
        assert z["zertifikat_typ"] == "persoenlich"
        assert z["scharf"] is False and z["angelegt"] is True   # §8: Schlüssel 1 gesetzt, 2 fehlt
        assert z["zertifikat_importiert"] is False and z["pin_gesetzt"] is False
        # Liste + Holen
        assert any(x["id"] == zid for x in c.get("/api/elster/zugaenge").json())
        assert c.get(f"/api/elster/zugaenge/{zid}").json()["id"] == zid
        # Soft-Delete
        assert c.delete(f"/api/elster/zugaenge/{zid}").json()["ok"]
        assert not any(x["id"] == zid for x in c.get("/api/elster/zugaenge").json())
        assert c.get(f"/api/elster/zugaenge/{zid}").status_code == 404
        assert c.delete(f"/api/elster/zugaenge/{zid}").status_code == 404


def test_zugang_validierung(tmp_path):
    with _client(tmp_path) as c:
        # leerer Zertifikat-Pfad ⇒ KonfigFehler ⇒ 400 (Vertrag erzwingt Datei-REF)
        assert c.post("/api/elster/zugaenge", json={"zertifikat_pfad": "  "}).status_code == 400
        # unbekannter Zertifikatstyp ⇒ 400
        assert c.post("/api/elster/zugaenge", json={
            "zertifikat_pfad": "z.pfx", "zertifikat_typ": "quantum"}).status_code == 400
        # organisation ist gültig
        assert c.post("/api/elster/zugaenge", json={
            "zertifikat_pfad": "z.pfx", "zertifikat_typ": "organisation"
        }).json()["zertifikat_typ"] == "organisation"


# --------------------------------------------------- HÄRTUNG: geheimnisfreie Responses

def test_zugang_response_traegt_nie_pin_oder_volle_steuernummer(tmp_path):
    """I-2: eine Zugangs-Response enthält NIE den Vault-Schlüssel-Namen, NIE die
    volle Steuernummer — die Steuernummer erscheint ausschließlich maskiert."""
    with _client(tmp_path) as c:
        r = c.post("/api/elster/zugaenge", json={
            "zertifikat_pfad": "z.pfx", "steuernummer": "123/456/78901"})
        body = r.json()
        roh = r.text
        # kein Vault-Bezug in der Response (weder Feldname noch Key-Konvention):
        assert "pin_vault_key" not in body and "pin_vault_key" not in roh
        assert "elster_pin_" not in roh
        # Steuernummer nur maskiert, nie im Klartext:
        assert "123/456/78901" not in roh
        assert body["steuernummer_maskiert"] == "12…01"
        # auch die Liste/Einzel-Sicht bleibt geheimnisfrei:
        assert "123/456/78901" not in c.get("/api/elster/zugaenge").text
        assert "elster_pin_" not in c.get(f"/api/elster/zugaenge/{body['id']}").text


def test_zugang_row_traegt_vault_key_nur_intern(tmp_path):
    """Der ``pin_vault_key`` wird server-seitig aus der zugang_id abgeleitet (I-2/
    VREV-R-2) und existiert intern — verlässt die Schicht aber nur über die
    Vertrags-Naht (``zugang()``), NIE über die Response."""
    app, db, speicher = _stack(tmp_path)
    zid = speicher.zugang_anlegen(USER, zertifikat_pfad="z.pfx")
    row = speicher.zugang_row(USER, zid)
    assert row["pin_vault_key"] == f"{v.PIN_VAULT_PREFIX}{zid}"
    # Vertrags-Rekonstruktion trägt den Key-NAMEN (kein Geheimnis) …
    zugang = speicher.zugang(USER, zid)
    assert isinstance(zugang, v.ElsterZugang)
    assert zugang.pin_vault_key == f"{v.PIN_VAULT_PREFIX}{zid}"
    # … die Response-Serialisierung aber NICHT:
    assert "pin_vault_key" not in ep.zugang_public(row)


# ------------------------------------------------------- Hersteller-ID (Settings)

def test_hersteller_id_settings_und_purge_warnung(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/api/elster/einstellungen").json()
        assert r["hersteller_id"] == "" and r["hersteller_id_gesetzt"] is False
        assert "Quittungs-Archiv" in r["purge_warnung"]      # DSGVO-Warnung ehrlich ausgewiesen
        assert c.put("/api/elster/einstellungen",
                     json={"hersteller_id": "  KENNUNG-42  "}).json()["hersteller_id_gesetzt"]
        r2 = c.get("/api/elster/einstellungen").json()
        assert r2["hersteller_id"] == "KENNUNG-42"           # getrimmt gespeichert
        assert r2["hersteller_id_gesetzt"] is True


def test_hersteller_id_naht_fuettert_wachter(tmp_path):
    """Der Settings-Slot ist die Quelle für ``pruefe_hersteller_id`` (I-3)."""
    app, db, speicher = _stack(tmp_path)
    with pytest.raises(v.NichtScharf):
        v.pruefe_hersteller_id(speicher.hersteller_id(USER))   # leer ⇒ NichtScharf
    speicher.hersteller_id_setzen(USER, "KENNUNG-1")
    v.pruefe_hersteller_id(speicher.hersteller_id(USER))       # gesetzt ⇒ ok


# ------------------------------------------------ Läufe/Quittungen (read-only + I-2)

def test_laeufe_historie_read_only(tmp_path):
    app, db, speicher = _stack(tmp_path)
    speicher.lauf_speichern(USER, fall=_FALL, zustand=v.FilingZustand.FEHLGESCHLAGEN,
                            fehler="ELSTER-Server nicht erreichbar",
                            fehler_art="VerbindungsFehler")
    with TestClient(app) as c:
        laeufe = c.get("/api/elster/laeufe").json()
        assert len(laeufe) == 1
        assert laeufe[0]["fall_schluessel"] == "euer|2026|"
        assert laeufe[0]["zustand"] == "fehlgeschlagen"
        assert laeufe[0]["fehler_art"] == "VerbindungsFehler"
        # gefiltert auf den Fall-Schlüssel
        assert len(c.get("/api/elster/laeufe?fall_schluessel=euer|2026|").json()) == 1
        assert c.get("/api/elster/laeufe?fall_schluessel=ustva|2026|2026-06").json() == []
        # read-only: es gibt KEIN POST auf die Historie (Motor = M1-5)
        assert c.post("/api/elster/laeufe", json={}).status_code == 405


def test_quittung_archiv_zeigt_nie_xml_oder_protokoll(tmp_path):
    """I-2: das Quittungs-Archiv gibt NUR den Nachweis (Transferticket + Zeit)
    preis — nie die gesendete Erklärung (XML) und nie das Roh-Protokoll."""
    app, db, speicher = _stack(tmp_path)
    lid = speicher.lauf_speichern(USER, fall=_FALL, zustand=v.FilingZustand.FESTGESCHRIEBEN,
                                  transferticket="TT-9")
    speicher.quittung_speichern(USER, quittung=_quittung("TT-9"),
                                datensatz=_datensatz(), lauf_id=lid)
    with TestClient(app) as c:
        r = c.get("/api/elster/quittungen")
        roh = r.text
        q = r.json()[0]
        assert q["transferticket"] == "TT-9"           # Nachweis zeigbar
        assert q["protokoll_bytes"] > 0                 # DASS archiviert, nicht WAS
        assert "GEHEIM-XML-4711" not in roh             # die Erklärung selbst NIE (I-2)
        assert "GEHEIM-PROTOKOLL-BYTES" not in roh      # das Roh-Protokoll NIE (I-2)
        assert "datensatz_xml" not in q and "protokoll_roh" not in q


# --------------------------------------------- Doppel-Schutz über die Persistenz (I-6)

def test_pruefe_doppel_ueber_persistierte_historie(tmp_path):
    """Der Idempotenz-Schutz baut auf der DB-Historie auf: ``laeufe_paare`` →
    ``pruefe_doppel``. FESTGESCHRIEBEN blockt den Erstlauf, lässt aber die bewusste
    Korrektur zu (I-6)."""
    app, db, speicher = _stack(tmp_path)
    speicher.lauf_speichern(USER, fall=_FALL, zustand=v.FilingZustand.FESTGESCHRIEBEN,
                            transferticket="TT-1")
    paare = speicher.laeufe_paare(USER)
    with pytest.raises(v.DoppelFilingFehler):
        v.pruefe_doppel(paare, _FALL)                  # Erstlauf blockiert
    korrektur = v.SteuerFall(formular=v.FormularArt.EUER, jahr=2026, korrektur_nr=1)
    v.pruefe_doppel(paare, korrektur)                  # bewusste Korrektur darf


def test_pruefe_doppel_sendet_leiche_blockt_auch_korrektur(tmp_path):
    """Eine ``SENDET``-Leiche (Crash im Senden) blockiert JEDEN neuen Lauf — auch
    eine Korrektur — bis zur manuellen Klärung (I-6, fail-closed)."""
    app, db, speicher = _stack(tmp_path)
    speicher.lauf_speichern(USER, fall=_FALL, zustand=v.FilingZustand.SENDET)
    paare = speicher.laeufe_paare(USER)
    korrektur = v.SteuerFall(formular=v.FormularArt.EUER, jahr=2026, korrektur_nr=1)
    with pytest.raises(v.DoppelFilingFehler):
        v.pruefe_doppel(paare, _FALL)
    with pytest.raises(v.DoppelFilingFehler):
        v.pruefe_doppel(paare, korrektur)


def test_lauf_zustand_setzen_persistiert_uebergang(tmp_path):
    """Die Persistenz-Seite eines Motor-Übergangs (M1-5): Zustand + Nachweis
    fortschreiben. Die Legalität prüft der Motor (``pruefe_uebergang``), nicht die DB."""
    app, db, speicher = _stack(tmp_path)
    lid = speicher.lauf_speichern(USER, fall=_FALL, zustand=v.FilingZustand.SENDET)
    assert speicher.lauf_zustand_setzen(
        USER, lid, v.FilingZustand.QUITTUNG_ERHALTEN, transferticket="TT-7")
    rows = speicher.laeufe_rows(USER)
    assert rows[0]["zustand"] == "quittung_erhalten" and rows[0]["transferticket"] == "TT-7"
    assert speicher.lauf_zustand_setzen(USER, "gibtsnicht", v.FilingZustand.FESTGESCHRIEBEN) is False


# ---------------------------------------------------------- DSGVO-Lösch-Kaskade

def test_dsgvo_kaskade_erfasst_alle_elster_daten(tmp_path):
    """Alle drei Tabellen tragen user_id+deleted_at, die Hersteller-ID liegt im
    generischen ``app_settings`` ⇒ ``soft_delete_user`` räumt ALLES ohne Per-App-Code."""
    app, db, speicher = _stack(tmp_path)
    zid = speicher.zugang_anlegen(USER, zertifikat_pfad="z.pfx", steuernummer="123/456/78901")
    lid = speicher.lauf_speichern(USER, fall=_FALL, zustand=v.FilingZustand.FESTGESCHRIEBEN,
                                  transferticket="TT-1")
    speicher.quittung_speichern(USER, quittung=_quittung("TT-1"), datensatz=_datensatz(), lauf_id=lid)
    speicher.hersteller_id_setzen(USER, "KENNUNG-1")

    # Vor der Löschung: DSGVO-Export sieht alle drei Tabellen …
    exp = db.export_user(USER)
    assert exp["elster_zugaenge"] and exp["filing_laeufe"] and exp["filing_quittungen"]

    # Lösch-Kaskade (generisch) …
    zaehler = db.soft_delete_user(USER)
    assert zaehler.get("elster_zugaenge") and zaehler.get("filing_laeufe")
    assert zaehler.get("filing_quittungen")

    # … danach ist über den Lese-Pfad nichts mehr da (auch die Hersteller-ID fällt):
    with TestClient(app) as c:
        assert c.get("/api/elster/zugaenge").json() == []
        assert c.get("/api/elster/laeufe").json() == []
        assert c.get("/api/elster/quittungen").json() == []
        assert c.get("/api/elster/einstellungen").json()["hersteller_id"] == ""
