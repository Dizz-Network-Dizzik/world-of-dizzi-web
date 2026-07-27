"""Vertrags-Tests C1-0 (docs/66 §11): pure Regelwerke vollständig, Bau-Stubs werfen NichtGebaut."""
from pathlib import Path

import pytest

from appexport import NichtGebaut, carving, editionen, lizenz, manifest, nullzustand

# ---------------------------------------------------------------- Editionen (I-7)


class TestEditionen:
    def test_konstanten(self):
        assert editionen.EDITIONEN == ("lokal", "hybrid", "server")
        assert editionen.PAKET_TYPEN == ("einzel", "bundle", "gesamt")
        assert editionen.KERN_APPS == ("core",)

    def test_trading_nie_auslieferbar(self):
        assert all(not editionen.ist_auslieferbar("trading", e) for e in editionen.EDITIONEN)

    def test_hoch_hoechst_nie_server(self):
        for app in ("management", "admin", "healthy"):
            assert not editionen.ist_auslieferbar(app, "server")
            assert not editionen.ist_auslieferbar(app, "hybrid")

    def test_healthy_und_creating_heute_gesperrt(self):
        # healthy: SQLITE-SEE-Gate (§12.4) · creating: G-FLUX-LIZENZ (§12.3)
        assert editionen.erlaubte_editionen("healthy") == frozenset()
        assert editionen.erlaubte_editionen("creating") == frozenset()

    def test_pilot_kandidaten_lokal_frei(self):
        for app in ("news", "memory", "communication", "money", "management", "admin"):
            assert editionen.ist_auslieferbar(app, "lokal")

    def test_fail_closed_unbekannt(self):
        assert editionen.erlaubte_editionen("gibtsnicht") == frozenset()
        assert not editionen.ist_auslieferbar("news", "cloud")   # unbekannte Edition
        assert not editionen.ist_auslieferbar("core", "lokal")   # nie einzeln

    def test_freigaben_nur_bekannte_editionen(self):
        for app, frei in editionen.APP_FREIGABEN.items():
            assert frei <= set(editionen.EDITIONEN), app


# ---------------------------------------------------------------- Manifeste (§4)

def gueltiges_export_manifest() -> dict:
    return {
        "schema": 1, "app_id": "news", "paket": "newsapp", "port": 8216,
        "appkit_direkt": ["app", "auth", "csp", "db"],
        "pip_eigen": ["feedparser"], "statisch": ["static/"],
        "editionen": ["lokal"], "sensitivitaet": "normal",
        "nachgeladen": [{"name": "ollama-modell", "zweck": "lokale KI (optional)", "gate": None}],
    }


def gueltiges_bundle_manifest() -> dict:
    return {
        "schema": 1, "bundle_id": "dizzi-news", "bundle_version": "2026-07-04+e794a51",
        "erzeugt_am": "2026-07-04T12:00:00", "quelle_commit": "e794a51",
        "edition": "lokal", "paket_typ": "einzel", "apps": ["core", "news"],
        "appkit_module": ["app", "auth"], "lizenz_manifest_sha256": "0" * 64,
        "daten_anker_default": "%LOCALAPPDATA%\\dizzi-world\\daten",
    }


class TestExportManifest:
    def test_gueltig(self):
        assert manifest.validiere_export_manifest(gueltiges_export_manifest()) == []

    @pytest.mark.parametrize("feld", manifest.EXPORT_PFLICHTFELDER)
    def test_pflichtfeld_fehlt(self, feld):
        m = gueltiges_export_manifest()
        del m[feld]
        assert any(feld in f for f in manifest.validiere_export_manifest(m))

    def test_unsortierte_module_abgelehnt(self):
        m = gueltiges_export_manifest()
        m["appkit_direkt"] = ["db", "app"]
        assert any("sortiert" in f for f in manifest.validiere_export_manifest(m))

    def test_duplikate_abgelehnt(self):
        m = gueltiges_export_manifest()
        m["appkit_direkt"] = ["app", "app"]
        assert any("Duplikate" in f for f in manifest.validiere_export_manifest(m))

    def test_unbekannte_edition_abgelehnt(self):
        m = gueltiges_export_manifest()
        m["editionen"] = ["cloud"]
        assert manifest.validiere_export_manifest(m)

    def test_falsche_sensitivitaet_und_schema(self):
        m = gueltiges_export_manifest()
        m["sensitivitaet"], m["schema"] = "geheim", 99
        fehler = manifest.validiere_export_manifest(m)
        assert len(fehler) == 2

    def test_nachgeladen_braucht_name_und_zweck(self):
        m = gueltiges_export_manifest()
        m["nachgeladen"] = [{"name": "ERiC"}]
        assert any("zweck" in f for f in manifest.validiere_export_manifest(m))


class TestBundleManifest:
    def test_gueltig(self):
        assert manifest.validiere_bundle_manifest(gueltiges_bundle_manifest()) == []

    def test_core_immer_dabei(self):
        m = gueltiges_bundle_manifest()
        m["apps"] = ["news"]
        assert any("IMMER" in f for f in manifest.validiere_bundle_manifest(m))

    @pytest.mark.parametrize("version", ["1.0.0", "2026-07-04", "e794a51", "2026-7-4+e794a51"])
    def test_versionsmuster_abgelehnt(self, version):
        m = gueltiges_bundle_manifest()
        m["bundle_version"] = version
        assert any("bundle_version" in f for f in manifest.validiere_bundle_manifest(m))

    def test_paket_typ_und_edition_validiert(self):
        m = gueltiges_bundle_manifest()
        m["paket_typ"], m["edition"] = "mega", "cloud"
        assert len(manifest.validiere_bundle_manifest(m)) == 2


# ---------------------------------------------------------------- Carving (§3, I-6)


class TestCarving:
    KANTEN = {"app": {"csp", "headers"}, "csp": {"headers"}, "auth": {"db"}, "agenten": {"db"}}

    def test_huelle_transitiv_und_sortiert(self):
        assert carving.huelle_aus_kanten(["app"], self.KANTEN) == ("app", "csp", "headers")

    def test_huelle_zyklenfest(self):
        kanten = {"a": {"b"}, "b": {"a"}}
        assert carving.huelle_aus_kanten(["a"], kanten) == ("a", "b")

    def test_huelle_deterministisch(self):
        eins = carving.huelle_aus_kanten(["auth", "app"], self.KANTEN)
        zwei = carving.huelle_aus_kanten(["app", "auth"], self.KANTEN)
        assert eins == zwei == ("app", "auth", "csp", "db", "headers")

    def test_abschluss_fehlend_ist_fehler(self):
        befund = carving.pruefe_abschluss(deklariert=["app"], beobachtet=["app", "ollama"])
        assert not befund.ok and befund.fehlend == ("ollama",)

    def test_abschluss_ueberzaehlig_nur_warnung(self):
        befund = carving.pruefe_abschluss(deklariert=["app", "mcp"], beobachtet=["app"])
        assert befund.ok and befund.ueberzaehlig == ("mcp",)

    def test_schwer_nur_transitiv(self):
        huelle = carving.huelle_aus_kanten(["agenten"], self.KANTEN)
        assert carving.schwer_nur_transitiv(["app"], huelle + ("app",)) == ("agenten",)
        assert carving.schwer_nur_transitiv(["agenten"], huelle) == ()

    def test_modul_pip_deps_bewusst_leer(self):
        # docs/66 §3.5: maschinelle Erhebung in C1-2 — der Vertrag rät nichts.
        assert carving.MODUL_PIP_DEPS == {}

    def test_beobachter_nicht_gebaut(self):
        with pytest.raises(NichtGebaut):
            carving.ermittle_direkte_nutzung(Path("."))
        with pytest.raises(NichtGebaut):
            carving.ermittle_appkit_kanten(Path("."))


# ---------------------------------------------------------------- Lizenz-Ampel (§5, I-4/I-5)


class TestLizenzAmpel:
    def k(self, **kw) -> lizenz.Komponente:
        basis = dict(name="x", lizenz="MIT", klasse="pip")
        basis.update(kw)
        return lizenz.Komponente(**basis)

    @pytest.mark.parametrize("spdx", sorted(lizenz.PERMISSIV))
    def test_permissiv_gruen(self, spdx):
        assert lizenz.ampel_fuer(self.k(lizenz=spdx), "lokal") == lizenz.AMPEL_GRUEN

    def test_lgpl_nur_mit_isolation(self):
        mit_iso = self.k(lizenz="LGPL-3.0-or-later", isolation=lizenz.ISOLATION_LGPL)
        ohne_iso = self.k(lizenz="LGPL-3.0-or-later")
        assert lizenz.ampel_fuer(mit_iso, "lokal") == lizenz.AMPEL_AUFLAGE
        assert lizenz.ampel_fuer(ohne_iso, "lokal") == lizenz.AMPEL_ROT

    @pytest.mark.parametrize("spdx", sorted(lizenz.COPYLEFT_HART))
    def test_gpl_agpl_rot(self, spdx):
        assert lizenz.ampel_fuer(self.k(lizenz=spdx), "lokal") == lizenz.AMPEL_ROT

    def test_gate_vor_allem(self):
        k = self.k(lizenz="MIT", gate="G-M1-LIZENZ")
        assert lizenz.ampel_fuer(k, "lokal") == lizenz.AMPEL_GATE

    def test_unbekannt_fail_closed_rot(self):
        assert lizenz.ampel_fuer(self.k(lizenz="TotalObskur-1.0"), "lokal") == lizenz.AMPEL_ROT

    def test_mpl_auflage(self):
        assert lizenz.ampel_fuer(self.k(lizenz="MPL-2.0"), "lokal") == lizenz.AMPEL_AUFLAGE

    def test_v1_konservativ_in_jeder_edition(self):
        k = self.k(lizenz="proprietaer", gate="G-FLUX-LIZENZ")
        assert all(lizenz.ampel_fuer(k, e) == lizenz.AMPEL_GATE for e in editionen.EDITIONEN)

    def test_unbekannte_edition_wirft(self):
        with pytest.raises(ValueError):
            lizenz.ampel_fuer(self.k(), "cloud")


class TestBekannteKomponenten:
    def test_fints_traegt_m6_isolation(self):
        fints = lizenz.BEKANNTE_KOMPONENTEN["fints"]
        assert fints.lizenz == "LGPL-3.0-or-later"
        assert fints.isolation == lizenz.ISOLATION_LGPL
        assert "docs/64" in fints.quelle
        assert lizenz.ampel_fuer(fints, "lokal") == lizenz.AMPEL_AUFLAGE

    def test_eric_und_flux_gegated_und_nachgeladen(self):
        for name in ("ERiC", "FLUX.1"):
            k = lizenz.BEKANNTE_KOMPONENTEN[name]
            assert k.klasse == "nachgeladen" and k.gate            # I-9 + Gate
            assert lizenz.ampel_fuer(k, "lokal") == lizenz.AMPEL_GATE

    def test_startbestand_klassen_und_belege(self):
        for k in lizenz.BEKANNTE_KOMPONENTEN.values():
            assert k.klasse in lizenz.KLASSEN
            assert k.quelle, f"{k.name}: Beleg (quelle) ist Pflicht — Warranty-of-Title-Spur"

    def test_generator_nicht_gebaut(self):
        with pytest.raises(NichtGebaut):
            lizenz.erzeuge_lizenz_manifest("dizzi-news", "lokal", [])


# ---------------------------------------------------------------- Nullzustand (§7, I-2/I-3/I-6)


class TestNullzustand:
    @pytest.mark.parametrize("text,muster", [
        ("-----BEGIN RSA PRIVATE KEY-----", "private-key"),
        ('api_key = "sk-abcdef123456789"', "zuweisungs-secret"),
        ("PIN: 123456", "pin"),
        (r"pfad = C:\Dizzik\data", "absoluter-dizzik-pfad"),
        (r"db in data\apps\news\x.db", "daten-wurzel"),
        (r"aus _backups\mirrors kopiert", "backup-pfad"),
    ])
    def test_muster_fangen(self, text, muster):
        assert muster in nullzustand.verstoesse_in_text(text)

    def test_harmloser_text_sauber(self):
        text = "Dizz News liest Feeds. api_key wird in der Config-UI gesetzt (Vault)."
        assert nullzustand.verstoesse_in_text(text) == []

    @pytest.mark.parametrize("name", ["news.db", "x.sqlite3", "a.db-wal", ".env", "key.pem", "id.pfx"])
    def test_verbotene_dateien(self, name):
        assert nullzustand.ist_verbotene_datei(name)

    @pytest.mark.parametrize("name", ["main.py", "tokens.css", "LIESMICH.md", "requirements.txt"])
    def test_erlaubte_dateien(self, name):
        assert not nullzustand.ist_verbotene_datei(name)

    @pytest.mark.parametrize("pfad", [
        "apps/news/tests/test_news.py", "apps/news/_workfiles/GESETZE.md",
        "apps/news/docs/x.md", "apps/news/CLAUDE.md", "apps/news/conftest.py",
        "packages/appkit/__pycache__/app.cpython-312.pyc",
    ])
    def test_entwicklungs_artefakte_ausgeschlossen(self, pfad):
        assert nullzustand.ist_ausgeschlossen(pfad)

    def test_nutzcode_nicht_ausgeschlossen(self):
        for pfad in ("apps/news/newsapp/main.py", "packages/ui-kit/tokens.css", "apps/news/static/app.js"):
            assert not nullzustand.ist_ausgeschlossen(pfad)

    def test_scanner_nicht_gebaut(self):
        with pytest.raises(NichtGebaut):
            nullzustand.scanne_baum(Path("."))


# ---------------------------------------------------------------- I-11: kein appkit-Import


class TestWerkzeugEntkopplung:
    def test_appexport_importiert_kein_appkit(self):
        paket = Path(carving.__file__).parent
        for datei in paket.glob("*.py"):
            quelle = datei.read_text(encoding="utf-8")
            assert "import appkit" not in quelle, f"{datei.name} verletzt I-11 (docs/66 §1)"
