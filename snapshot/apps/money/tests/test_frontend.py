"""Teil C: GET / liefert die tokenbasierte Oberfläche (News-Muster). Geprüft
werden die verbindlichen Bausteine — Token-Achsen, die 5 Fenster-Gotchas
(docs/19 §2b), Spin v4.3, Float-Treiber, Mini-Dizzi — damit das Muster nicht
still wegbricht."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def test_startseite_liefert_html(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "dizz money" in r.text.lower()


def test_frontend_tokenbasiert_zwei_achsen(tmp_path):
    with _client(tmp_path) as c:
        html = c.get("/").text
        # Zwei Achsen als <html>-Attribute (K2.2) + Tokens als verlinkte Single-Source
        assert 'data-design="metall"' in html and 'data-farbe="cyan-magenta"' in html
        assert "/ui-kit/tokens.css" in html               # Achsen-Tokens (ausgelagert, 18.06.)
        # App-CSS nutzt NUR Tokens (keine hartkodierte Hauptfarbe)
        assert "var(--cy)" in html and "var(--panel)" in html


def test_frontend_fenster_gotchas(tmp_path):
    """Die 5 Pflicht-Gotchas des Fenster-Norm (docs/19 §2b)."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert ".kmwrap[hidden]{display:none!important}" in html      # 1 [hidden]!important
        assert "left:50%;top:50%;transform:translate(-50%,-50%)" in html  # 2 exakte Mitte
        assert "/ui-kit/floats.js" in html                           # 3 Klick-Fallback: initFloat im verlinkten Float-Treiber
        assert 'id="kontoModal"' in html                             # 4 Overlay auf BODY-Ebene
        assert "var(--panel-solid)" in html                          # 5 SOLID-Hintergrund (Pfeil)


def test_frontend_bereich_panel(tmp_path):
    """Bereich-Achse im Frontend: Panel + Cockpit + Filter + Zuordnung, data-dz-act-konform."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert 'id="card-bereiche"' in html and 'id="bereichliste"' in html
        assert 'id="bereich-cockpit"' in html                          # Cockpit-Renderbereich
        assert 'data-dz-act="bereichAnlegen"' in html                  # CSP-konform (keine inline-Handler)
        assert "function ladeBereiche(" in html and "function bereichCockpit(" in html
        assert 'id="k-bereich"' in html                                # Konto-Form: Bereich-Default
        # Register-Bereich-Filter = geteilte ui-kit-Leiste DzBereichBar (W4, ersetzt das tx-bereich-Dropdown)
        assert 'id="bereich-bar"' in html and "/ui-kit/bereichbar.js" in html
        assert "function renderBereichBar(" in html
        assert 'data-dz-act="bulkBereich"' in html                     # Bulk: Bereich zuweisen
        assert "/api/bereiche" in html
        # Admin→Money-Deep-Link (per money_kontext) + expliziter Kontext-Schlüssel
        assert 'id="ber-kontext"' in html                              # Kontext = Admins money_kontext
        assert "function oeffneBereichDeepLink(" in html               # ?kontext=/?bereich= → Cockpit
        assert "URLSearchParams" in html


def test_frontend_spin_floats_minidizzi(tmp_path):
    with _client(tmp_path) as c:
        html = c.get("/").text
        # Spin/Floats konvergiert aufs geteilte UI-Kit (18.06.): DizzSpin/DizzFloats
        assert "/ui-kit/spinfling.js" in html and "/ui-kit/floats.js" in html
        assert "DizzSpin" in html and "DizzFloats" in html and "mountKit" in html
        assert "/api/ki/frage" in html                               # Mini-Dizzi-Sprechblase
        # Domänen-Panels vorhanden (Transaktionen sind jetzt der Register-View)
        for marker in ("card-konten", "card-import", "card-cashflow",
                       "card-budget", "card-wiederkehr", "card-kat"):
            assert marker in html
        # P1: Register als Kern-Arbeitsfläche + Ansicht-Umschalter
        assert 'id="view-register"' in html and 'id="view-dashboard"' in html
        assert "function setView(" in html and 'id="view-switch"' in html
        assert "ladeWiederkehr" in html                              # Wiederkehr-Panel verdrahtet
        assert "ladeKurse" in html and "/api/wechselkurse" in html   # FX: Kurs-Editor + Buchen
        assert "buchungStornieren" in html and "kontoEntfernen" in html  # Korrektur/Pflege
        assert "buchungenExport" in html                             # Transaktions-Export
        assert "wkVerbuchen" in html                                 # Serie → Buchung verbuchen
        assert "ladeKennzahlen" in html and "kpi-strip" in html      # Kennzahlen-Leiste


def test_ui_kit_bundle_served(tmp_path):
    """K2.4: das app-neutrale ui-kit-Bundle wird ausgeliefert (Single-Source)."""
    with _client(tmp_path) as c:
        css = c.get("/ui-kit/controls.css")
        assert css.status_code == 200 and "text/css" in css.headers["content-type"]
        assert ".dz-check" in css.text and ".dz-panel-kopf" in css.text
        js = c.get("/ui-kit/collapse.js")
        assert js.status_code == 200
        assert "initCollapse" in js.text and "initStepper" in js.text


def test_frontend_k24_controls_und_collapse(tmp_path):
    """K2.4-(b): native Controls durch die dz-Familie ersetzt + große Panels
    einklappbar; Komponenten-Tokens kommen aus dem verlinkten tokens.css."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        # Bundle eingehängt
        assert '/ui-kit/controls.css' in html and '/ui-kit/collapse.js' in html
        # Komponenten-Tokens (--control-*/--panel-kurz) liegen im verlinkten tokens.css
        assert "/ui-kit/tokens.css" in html
        # Control-Familie im Markup
        assert 'class="dz-check' in html                             # Checkbox/Radio
        assert 'class="dz-field"' in html and 'class="dz-select"' in html  # Select
        assert 'class="dz-stepper"' in html and 'data-dz-step="-1"' in html  # Stepper
        # einklappbare große Panels mit Kurzanzeige
        assert html.count("data-dz-collapsible") >= 6
        assert 'class="dz-panel-kopf"' in html and 'dz-panel-kurz' in html
        for kurz in ("kurz-konten", "kurz-cashflow", "kurz-budget"):
            assert kurz in html
        # Einstellungs-Fenster nutzt die dz-Familie (Theme-Switcher = dz-select)
        assert 'id="designSel" class="dz-select"' in html
        # dynamische Stepper im Settings-Fenster werden verdrahtet
        assert "DzControls.initStepper" in html


def test_frontend_register_und_querverbindungen(tmp_path):
    """P1: Transaktions-Register als Kern-Arbeitsfläche (Startseite) + Ansicht-
    Umschalter + sichtbarer Querverbindungs-Chip-Cluster (📎 V15 · 🏷 V16 · ⇲ V9)."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        # Register + Umschalter (zerstörungsfrei: Dashboard bleibt)
        assert 'id="view-register"' in html and 'id="view-dashboard"' in html
        assert 'id="view-switch"' in html and 'data-dz-act="setView" data-dz-arg="register"' in html
        assert 'id="buchungsliste" class="register"' in html        # dichte Register-Liste
        assert "localStorage.setItem('moneyView'" in html           # Register = Startseite, gemerkt
        # Querverbindungs-Chips an der Zeile, echt verdrahtet an bestehende Backends
        assert "vchip" in html
        assert "belegDialog(" in html and "belegEntfernen(" in html  # 📎 V15
        assert "steuerHinweis(" in html and "EÜR (V16)" in html      # 🏷 V16
        assert "belegArchivieren(" in html and "(V9" in html         # ⇲ V9
        # die alte Transaktions-Dashboard-Karte ist in den Register gewandert
        assert 'id="card-tx"' not in html


def test_frontend_register_bulk_und_tastatur(tmp_path):
    """P1(a)-Tiefe: Mehrfachauswahl + Bulk-Aktionen + Tastatur-Flow im Register."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert 'id="reg-bulk"' in html and 'class="txsel"' in html   # Auswahl + Bulk-Leiste
        assert "function bulkKategorie(" in html and "function bulkStorno(" in html
        assert "function txSelAll(" in html and "function regSetActive(" in html  # Tastatur-Flow
        assert "ArrowDown" in html and "txrow.active" in html


def test_frontend_buchung_editor(tmp_path):
    """P1(a): Neue-Buchung-Editor (Split + Transfer im selben Editor), Fenster-Norm."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert 'id="buchModal"' in html and "function openBuch(" in html
        assert 'data-dz-act="openBuch"' in html              # + Buchung im Register (CSP-strikt)
        assert 'data-dz-act="buchModus" data-dz-arg="ausgabe"' in html \
            and 'data-dz-arg="transfer"' in html
        assert "function bmAddZeile(" in html                # Split-Zeilen
        assert "/api/buchungen/split" in html                # Split-Backend verdrahtet
        assert "function buchSpeichern(" in html


def test_frontend_abo_kalender(tmp_path):
    """P3: Abo-Kalender (12 Monate) + „kündigen?"-Flag im Wiederkehr-Panel."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert "function ladeAboKalender(" in html and 'id="wk-kalender"' in html
        assert "kündigen?" in html and "jahres_kosten" in html


def test_frontend_insights(tmp_path):
    """P3: Spending-Insights-Streifen (App-Wächter-KI sichtbar)."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert "function ladeInsights(" in html and "/api/auswertung/insights" in html
        assert 'id="insights-strip"' in html


def test_frontend_projektion(tmp_path):
    """P3: 30/60/90-Liquiditäts-Projektion im Wiederkehr-Panel."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert "function ladeProjektion(" in html and "/api/auswertung/projektion" in html
        assert 'id="wk-projektion"' in html


def test_frontend_reconciliation(tmp_path):
    """P2: Reconciliation-Flow im Konten-Panel (Auszug ↔ Ledger, „abgeglichen bis")."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert "Kontoabgleich" in html and 'id="rec-konto"' in html
        assert "function abgleichPruefen(" in html and "function abgleichMarkieren(" in html
        assert "/abgleich" in html


def test_frontend_import_assistent(tmp_path):
    """P2: Import-Assistent — Vorschau (Dry-Run) vor dem Schreiben."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert "function importVorschau(" in html and "/api/import/vorschau" in html
        assert 'id="imp-vorschau"' in html and "importVorschau()" in html


def test_frontend_envelope_budget(tmp_path):
    """P1(b): Envelope-/Zero-Based-Budget-Rendering (Zuzuweisen-Kopf + dz-progress)."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert 'id="bud-envelope"' in html                  # Zero-Based-Kopf
        assert "zuzuweisen" in html.lower()                 # „jeder Euro hat einen Job"
        assert "dz-progress" in html                         # Umschlag-Fortschritt (Kit)
        assert "verfügbar" in html                           # zugewiesen/ausgegeben/verfügbar
