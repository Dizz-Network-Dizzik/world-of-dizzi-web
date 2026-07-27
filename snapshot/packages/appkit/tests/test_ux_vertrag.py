"""UX-Konsolidierungs-Vertrag (docs/70) — Tests der Bausteine F-1…F-8 + MG-1.

Pinnt: das kanonische App-Verzeichnis (T-NETZ) · die 404-Content-Negotiation
(T-404, Wertgleichheit für API-Clients) · die G-UX-AUTH-Editions-Matrix + den
Gesperrt-Zustand (T-LOCK) · Sprachregister + Datums-Norm (T-WORT) · den
Kit-Vertrag der neuen ui-kit-Dateien (T-TOKEN: token-only, Opt-in-Marker).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from appkit import fehlerseite, netz, sichtbarkeit, sprachregister, ui_kit_path
from appkit.app import create_app
from appkit.db import Database
from appkit.manifest import AppManifest
from appkit.summary import Kpi, Summary

MANIFEST = AppManifest(id="probe", name="Probefunktion", brand="Dizz Probe",
                       version="0.0.1", port=8299)


# ── T-NETZ · Kanonisches App-Verzeichnis (F-1, docs/70 §3.1) ─────────────────

#: Die verifizierten Manifest-Wahrheiten (04.07.2026) — ändert eine App
#: Port/ID, muss BEWUSST hier UND in netz.py nachgezogen werden (Gesetz 9).
_ERWARTET = {"core": 8200, "news": 8216, "finanzen": 8210, "kommunikation": 8218,
             "creator": 8214, "memory": 8212, "management": 8213, "health": 8217,
             "admin": 8222, "tradingbot": 8137}


class TestNetzVerzeichnis:
    def test_zehn_apps_kanonische_ids_und_ports(self):
        assert {a.id: a.port for a in netz.NETZ_APPS} == _ERWARTET

    def test_ids_und_ports_eindeutig(self):
        ids = [a.id for a in netz.NETZ_APPS]
        ports = [a.port for a in netz.NETZ_APPS]
        assert len(set(ids)) == len(ids) and len(set(ports)) == len(ports)

    def test_marken_vollstaendig(self):
        for a in netz.NETZ_APPS:
            assert a.brand and a.name, f"{a.id}: Marke/Funktion fehlt (K2.3)"

    def test_url_und_zugriff(self):
        assert netz.netz_app("finanzen").url == "http://127.0.0.1:8210"
        assert netz.netz_app("gibtsnicht") is None
        assert netz.CORE_URL == "http://127.0.0.1:8200"

    def test_hoechst_traegt_schild(self):
        hoechst = {a.id for a in netz.NETZ_APPS if a.sensitivity == "hoechst"}
        assert hoechst == {"kommunikation", "health", "tradingbot"}

    def test_router_liefert_verzeichnis(self):
        app = FastAPI()
        app.include_router(netz.netz_router())
        r = TestClient(app).get("/api/netz/apps")
        assert r.status_code == 200
        daten = r.json()
        assert daten["core_url"] == netz.CORE_URL
        assert len(daten["apps"]) == 10
        assert all("url" in a for a in daten["apps"])


# ── T-404 · Fehlerseite mit strikter Content-Negotiation (F-4, docs/70 §3.4) ─

def _mini_client(mit_fehlerseite: bool = True) -> TestClient:
    app = FastAPI()

    @app.get("/api/echt")
    def api_echt():
        return {"ok": True}

    @app.get("/seite")
    def seite():
        return {"ok": True}

    if mit_fehlerseite:
        fehlerseite.install_fehlerseiten(app, MANIFEST)
    return TestClient(app)


class TestFehlerseite:
    def test_browser_404_bekommt_html_mit_beiden_wegen(self):
        r = _mini_client().get("/gibtsnicht", headers={"Accept": "text/html,*/*;q=0.8"})
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("text/html")
        assert "Dizz Probe" in r.text and "Probefunktion" in r.text     # K2.3-Lockup
        assert 'href="/"' in r.text and netz.CORE_URL in r.text          # zwei Ausgänge
        assert "Diese Seite gibt es hier nicht." in r.text

    def test_api_pfad_bleibt_json_auch_fuer_browser(self):
        r = _mini_client().get("/api/gibtsnicht", headers={"Accept": "text/html"})
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}

    def test_fetch_und_tests_bleiben_json(self):
        r = _mini_client().get("/gibtsnicht", headers={"Accept": "*/*"})
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}

    def test_405_bekommt_eigenen_satz(self):
        r = _mini_client().post("/seite", headers={"Accept": "text/html"})
        assert r.status_code == 405 and "405" in r.text
        assert "Diese Aktion ist hier so nicht möglich." in r.text

    def test_bestehende_routen_unberuehrt(self):
        c = _mini_client()
        assert c.get("/api/echt").json() == {"ok": True}
        assert c.get("/seite", headers={"Accept": "text/html"}).json() == {"ok": True}

    def test_opt_out_bleibt_fastapi_default(self):
        r = _mini_client(mit_fehlerseite=False).get(
            "/gibtsnicht", headers={"Accept": "text/html"})
        assert r.json() == {"detail": "Not Found"}

    def test_seite_ist_csp_strikt_tauglich(self):
        html = fehlerseite.fehlerseite_html(MANIFEST, 404)
        assert "<script" not in html and "style=" not in html            # docs/37
        assert "/ui-kit/tokens.css" in html and "/ui-kit/ux-kit.css" in html


class TestCreateAppIntegration:
    @pytest.fixture()
    def client(self, tmp_path):
        db = Database(tmp_path / "probe.sqlite")
        # Triage stumm: Test-Sperren sollen keine echten Ollama-Aufrufe feuern.
        db.setting_put("dizzi", "defense_triage_aktiv", False)
        app = create_app(MANIFEST, db,
                         summary_fn=lambda: [Kpi(id="n", label="N", value=1)])
        return TestClient(app)

    def test_traegt_netz_verzeichnis(self, client):
        daten = client.get("/api/netz/apps").json()
        assert len(daten["apps"]) == 10

    def test_traegt_fehlerseite_nur_fuer_browser(self, client):
        html = client.get("/gibtsnicht", headers={"Accept": "text/html"})
        assert html.status_code == 404 and "Dizz Probe" in html.text
        js = client.get("/gibtsnicht")                       # Accept */* wie fetch
        assert js.json() == {"detail": "Not Found"}          # Wertgleichheit (Stufe-0)


# ── T-LOCK · Editions-Matrix + Gesperrt-Zustand (F-2, G-UX-AUTH ✅ 03.07.) ───

class TestSichtbarkeit:
    @pytest.mark.parametrize("edition,level,klasse,erwartet", [
        # vollserver: ohne Anmeldung Login-Wand, angemeldet frei
        ("vollserver", "lokal", "lesen", "wand"),
        ("vollserver", "lokal", "server", "wand"),
        ("vollserver", "verifiziert", "lesen", "frei"),
        ("vollserver", "hochsicher", "server", "frei"),
        # hybrid: lokal frei, Server-Funktionen erst angemeldet
        ("hybrid", "lokal", "lesen", "frei"),
        ("hybrid", "lokal", "schreiben", "frei"),
        ("hybrid", "lokal", "server", "anmelden"),
        ("hybrid", "verifiziert", "server", "frei"),
        # lokal-pur: nutzbar ohne Login — das Gerät IST die Grenze (David 03.07.)
        ("lokal-pur", "lokal", "lesen", "frei"),
        ("lokal-pur", "lokal", "schreiben", "frei"),
        # hochsicher-Klasse: IMMER frischer Step-up (docs/19 §2 reauth_sensibel)
        ("lokal-pur", "lokal", "hochsicher", "reauth"),
        ("lokal-pur", "hochsicher", "hochsicher", "reauth"),
        ("hybrid", "verifiziert", "hochsicher", "reauth"),
        ("vollserver", "hochsicher", "hochsicher", "reauth"),
    ])
    def test_editions_matrix(self, edition, level, klasse, erwartet):
        assert sichtbarkeit.zugriff(edition, level, klasse=klasse) == erwartet

    def test_lokal_pur_zeigt_auch_hoechst_ansicht(self):
        # Kern der David-Antwort: in Lokal-pur ist die ANSICHT frei — Money-
        # Vollmaskierung war die Abweichung, nicht Healthys Offenheit.
        assert sichtbarkeit.zugriff("lokal-pur", "lokal",
                                    klasse="lesen", sensitivity="hoechst") == "frei"

    def test_fail_closed(self):
        assert sichtbarkeit.zugriff("gibtsnicht", "hochsicher") == "wand"
        assert sichtbarkeit.zugriff("lokal-pur", "lokal", klasse="gibtsnicht") == "reauth"
        assert sichtbarkeit.zugriff("lokal-pur", "lokal", sensitivity="gibtsnicht") == "reauth"
        assert sichtbarkeit.zugriff("vollserver", "gibtsnicht") == "wand"

    def test_summary_akzeptiert_gesperrt(self):
        s = Summary(app="probe", name="Probe", ts="2026-07-04T12:00:00",
                    status="gesperrt")
        assert s.status == "gesperrt"

    def test_gesperrt_summary_maskiert_alles(self):
        s = sichtbarkeit.gesperrt_summary(
            MANIFEST, "Mit Dizzi-ID anmelden, um deine Finanzen zu sehen",
            kpi_labels=("Nettovermögen", "Konten"))
        assert s.status == "gesperrt" and s.ok is True
        assert [k.value for k in s.kpis] == [sichtbarkeit.MASKE] * 2      # nie Pseudo-Nullen
        assert "anmelden" in (s.note or "").lower()                       # der Weg steht dabei

    def test_gesperrt_braucht_grund(self):
        with pytest.raises(ValueError):
            sichtbarkeit.gesperrt_summary(MANIFEST, "  ")
        with pytest.raises(ValueError):
            sichtbarkeit.gesperrt_payload("")

    def test_gesperrt_payload_form(self):
        p = sichtbarkeit.gesperrt_payload("Anmeldung nötig")
        assert p == {"gesperrt": True, "grund": "Anmeldung nötig",
                     "login_url": sichtbarkeit.LOGIN_URL}


# ── T-WORT · Sprachregister + Datums-Norm (F-6/F-8, docs/70 §3.6+§3.8) ───────

class TestSprachregister:
    def test_kunden_labels(self):
        assert sprachregister.kunden_label("HITL") == "mit Freigabe"
        assert sprachregister.kunden_label("Senden (HITL)") == "Senden (mit Freigabe)"
        assert sprachregister.kunden_label("L2") == "Einsatz-Dämpfung"    # T5-Panel, docs/70 §5.4
        assert sprachregister.kunden_label("unbekannt") == "unbekannt"    # Identität

    def test_pruefe_text_findet_interna(self):
        funde = sprachregister.pruefe_text(
            "Senden (HITL) — v1 DORMANT (Gesetz 5), stake_scale via POST /api/x")
        assert {"HITL", "DORMANT", "(Gesetz", "stake_scale", "POST /api"} <= set(funde)

    def test_pruefe_text_sauber(self):
        assert sprachregister.pruefe_text(
            "Senden (mit Freigabe) — vorbereitet, bewusst noch aus.") == []

    def test_kunden_labels_selbst_sauber(self):
        for label in sprachregister.KUNDEN_LEXIKON.values():
            assert sprachregister.pruefe_text(label) == [], label

    def test_normen(self):
        assert sprachregister.ANREDE == "du"                              # G-UX-ANREDE-Default
        assert sprachregister.ANMELDE_PILL_ABGEMELDET == "Anmelden (Dizzi-ID)"
        assert "{stufe}" in sprachregister.ANMELDE_PILL_ANGEMELDET


class TestDatumsNorm:
    JETZT = datetime(2026, 7, 4, 15, 0, tzinfo=timezone(timedelta(hours=2)))

    def _d(self, wert, **kw):
        return sprachregister.datum_de(wert, jetzt=self.JETZT, **kw)

    def test_heute_iso(self):
        assert self._d("2026-07-04T14:33:00+02:00") == "heute 14:33"

    def test_gestern_rfc822(self):                       # das reale News-Feed-Format (NE-3)
        assert self._d("Fri, 03 Jul 2026 14:33:44 +0200") == "gestern 14:33"

    def test_letzte_woche_wochentag(self):
        assert self._d("2026-06-30T09:00:00+02:00") == "Di 30.06."

    def test_selbes_jahr_ohne_jahr(self):
        assert self._d("2026-02-01") == "01.02."

    def test_anderes_jahr_mit_jahr(self):
        assert self._d("2025-12-31") == "31.12.2025"

    def test_ohne_zeit(self):
        assert self._d("2026-07-04T14:33:00+02:00", mit_zeit=False) == "heute"

    def test_unparsebares_bleibt_roh(self):              # ehrlich: nie "Invalid Date"
        assert self._d("sofort") == "sofort"


# ── T-TOKEN · Kit-Vertrag der neuen ui-kit-Dateien (docs/70 §8) ──────────────

_KIT = ui_kit_path()

#: Der Token-Vertrag aus tokens.css (Datei-Kopf): beide Achsen müssen liefern.
_VERTRAGS_TOKENS = ("--cy", "--mg", "--cy-rgb", "--mg-rgb", "--ok", "--warn",
                    "--bad", "--bg", "--bg-deep", "--fg", "--mut", "--txt",
                    "--line", "--panel", "--panel-solid", "--brush", "--satin",
                    "--edge-t", "--edge-b", "--r", "--r-win", "--r-chip",
                    "--sh", "--blur")


class TestKitVertrag:
    def test_neue_kit_dateien_existieren(self):
        assert (_KIT / "ux-kit.css").is_file() and (_KIT / "ux-kit.js").is_file()

    def test_ux_kit_css_ist_token_only(self):
        css = (_KIT / "ux-kit.css").read_text(encoding="utf-8")
        hex_farben = [h for h in re.findall(r"#([0-9a-fA-F]{3,8})\b", css)
                      if len(h) in (3, 4, 6, 8)]
        assert hex_farben == [], f"Hartkodierte Farben verboten (docs/70 §2.1): {hex_farben}"

    def test_tokens_vertrag_weiter_vollstaendig(self):
        tokens = (_KIT / "tokens.css").read_text(encoding="utf-8")
        fehlend = [t for t in _VERTRAGS_TOKENS if f"{t}:" not in tokens]
        assert fehlend == [], f"Token-Vertrag verletzt: {fehlend}"

    def test_collapse_traegt_optin_marker(self):
        js = (_KIT / "collapse.js").read_text(encoding="utf-8")
        assert "data-dz-offen" in js and "data-dz-kopf-klick" in js       # F-3 Norm v2

    def test_controls_traegt_kopfklick_anhang(self):
        css = (_KIT / "controls.css").read_text(encoding="utf-8")
        assert "data-dz-kopf-klick" in css

    def test_ux_kit_js_api_vollstaendig(self):
        js = (_KIT / "ux-kit.js").read_text(encoding="utf-8")
        for marker in ("window.DzUx", "netzleiste", "gesperrt", "gesperrtKpis",
                       "leer", "toast", "bestaetigen", "agentchip", "oeffnePanel",
                       "pruefeTooltips", "Anmelden (Dizzi-ID)", "/api/netz/apps"):
            assert marker in js, f"ux-kit.js-Vertrag verletzt: {marker!r} fehlt"


# ── T-HALTER · DzHalter Float-Andock-Schale (Spin-Physik docs/14 v4.4) ───────

class TestDzHalterVertrag:
    def test_kit_dateien_existieren(self):
        assert (_KIT / "float_dock.js").is_file() and (_KIT / "float_dock.css").is_file()

    def test_css_ist_token_only(self):
        css = (_KIT / "float_dock.css").read_text(encoding="utf-8")
        hex_farben = [h for h in re.findall(r"#([0-9a-fA-F]{3,8})\b", css)
                      if len(h) in (3, 4, 6, 8)]
        assert hex_farben == [], f"Hartkodierte Farben verboten (docs/70 §2.1): {hex_farben}"

    def test_css_traegt_schale_und_uebersteuerbare_lage(self):
        css = (_KIT / "float_dock.css").read_text(encoding="utf-8")
        for marker in (".dz-halter", ".dzh-slot", ".dzh-schalter",
                       "--dzh-top", "--dzh-right", "prefers-reduced-motion"):
            assert marker in css, f"float_dock.css-Vertrag verletzt: {marker!r} fehlt"

    def test_js_api_und_desktop_default_angedockt(self):
        js = (_KIT / "float_dock.js").read_text(encoding="utf-8")
        for marker in ("DzHalter", "anmelden", "dz_floats_modus",
                       "STANDARD = 'angedockt'",          # Desktop-Default (Davids Wort 12.07.)
                       "dizzi:floatsmodus", "'switch'", "prefers-reduced-motion"):
            assert marker in js, f"float_dock.js-Vertrag verletzt: {marker!r} fehlt"

    def test_floats_js_traegt_die_modus_weiche(self):
        js = (_KIT / "floats.js").read_text(encoding="utf-8")
        for marker in ("DzHalter", "K_HOME", "FR_HOME", "SNAP",
                       "dizzi:floatsmodus", "homing", "frei: () => dockung"):
            assert marker in js, f"floats.js ohne v4.4-Dock-Weiche: {marker!r} fehlt"
        # Abprall läuft NUR über freie Floats (alte Registry-Einträge bleiben kompatibel).
        assert "(!f.frei || f.frei())" in js

    def test_react_fassung_synchron(self):
        tsx = (_KIT / "FloatingSettings.tsx").read_text(encoding="utf-8")
        for marker in ("DzHalter", "K_HOME", "dizzi:floatsmodus", "homing", "belegt"):
            assert marker in tsx, f"FloatingSettings.tsx nicht v4.4-synchron: {marker!r} fehlt"

    def test_refapp_kopien_byte_identisch(self):
        # Drift-Wächter: das refapp-Template vendort die Kit-Dateien; nach jedem
        # Kit-Edit müssen die Kopien nachgezogen sein. Im Einzel-App-Export gibt
        # es kein templates/ ⇒ skip (Test bleibt export-fähig).
        ref = _KIT.parent.parent / "templates" / "refapp" / "ui-kit"
        if not ref.is_dir():
            pytest.skip("kein Monorepo-Checkout (Einzel-App-Export)")
        for name in ("floats.js", "float_dock.js", "float_dock.css"):
            assert (ref / name).read_bytes() == (_KIT / name).read_bytes(), \
                f"refapp-Kopie driftet: {name}"

    # ── Icon-Fix netzweit (docs/14 v4.5) — Stacking-/Klick-Vertrag ────────────
    # T-HALTER pinnte bisher Existenz/Token/Default, NICHT die z-Ordnung im
    # Fixiert-Zustand — genau Davids Bug-Fläche (Icon hinter der Schale). Diese
    # Verträge sichern die Korrektheits-Bedingungen des Fixes statisch ab; den
    # Live-Klick-Beweis (elementFromPoint) trägt die isolierte Preview-Abnahme.

    def _floatlayer_block(self, css: str) -> str:
        m = re.search(r"\.dzh-floatlayer\s*\{([^}]*)\}", css)
        assert m, ".dzh-floatlayer-Regel fehlt (Icon-Fix-Schicht)"
        return m.group(1)

    def test_z_leiter_floats_ueber_schale(self):
        css = (_KIT / "float_dock.css").read_text(encoding="utf-8")
        schale = re.search(r"--dzh-z-schale:\s*(\d+)", css)
        floats = re.search(r"--dzh-z-floats:\s*(\d+)", css)
        assert schale and floats, "z-Leiter-Vars --dzh-z-schale/--dzh-z-floats fehlen"
        assert int(floats.group(1)) > int(schale.group(1)), \
            "Float-Schicht MUSS über der Schale liegen (--dzh-z-floats > --dzh-z-schale)"
        assert "var(--dzh-z-schale" in css, "Die Schale zieht die z-Leiter-Var nicht"

    def test_floatlayer_ist_sauber(self):
        # DIE Korrektheits-Bedingung: eine Float-Schicht mit transform/filter/…
        # würde selbst zum Containing-Block und die position:fixed-Floats
        # verrutschten — der Bug, den sie heilt. Also hart verbieten.
        block = self._floatlayer_block(
            (_KIT / "float_dock.css").read_text(encoding="utf-8")).lower()
        assert "position: fixed" in block or "position:fixed" in block
        assert "inset:" in block
        assert "pointer-events: none" in block or "pointer-events:none" in block
        for verboten in ("transform", "filter", "backdrop-filter", "will-change",
                         "contain", "perspective", "background"):
            assert verboten not in block, \
                f".dzh-floatlayer darf kein {verboten!r} tragen (Containing-Block-Falle)"

    def test_pointer_vertrag_schicht_und_mulde(self):
        css = (_KIT / "float_dock.css").read_text(encoding="utf-8")
        # Nur die Floats selbst sind klickbar; die bildschirmfüllende Schicht
        # lässt Klicks der App darunter durch (kein Voll-Bild-Blocker).
        assert re.search(r"\.dzh-floatlayer\s*>\s*\*\s*\{[^}]*pointer-events:\s*auto", css), \
            ".dzh-floatlayer > * muss pointer-events:auto setzen (Floats klickbar)"
        assert re.search(r"\.dzh-slot\s*\{[^}]*pointer-events:\s*none", css), \
            ".dzh-slot muss pointer-events:none sein (Mulde fängt keinen Klick ab)"

    def test_js_hebt_float_auf_body_ebene(self):
        js = (_KIT / "float_dock.js").read_text(encoding="utf-8")
        for marker in ("dzh-floatlayer", "function schicht", "function heben",
                       "dzhHoist", "appendChild", "schicht: schicht"):
            assert marker in js, f"Icon-Fix-Hebe-Pfad unvollständig: {marker!r} fehlt"
        # anmelden MUSS heben() aufrufen (sonst greift die Garantie nie).
        assert re.search(r"if \(!wrap\) return null;\s*heben\(el\);", js), \
            "anmelden() hebt das Float nicht (heben(el) fehlt)"

    def test_react_float_opt_out(self):
        # Der React-Float (Shell) darf NICHT gehoben werden (Reconciliation) —
        # er trägt data-dzh-hoist="off" und sitzt schon auf z 60 über der Schale.
        tsx = (_KIT / "FloatingSettings.tsx").read_text(encoding="utf-8")
        assert 'data-dzh-hoist="off"' in tsx, \
            'FloatingSettings.tsx muss sich per data-dzh-hoist="off" vom Heben abmelden'
