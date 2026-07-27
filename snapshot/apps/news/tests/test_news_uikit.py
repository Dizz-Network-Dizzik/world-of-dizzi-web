"""K2.4: das ui-kit-Bundle muss same-origin serviert werden, damit das Frontend
die kanonische Komponenten-Schicht referenzieren kann (statt sie zu kopieren).
Verankert den /ui-kit-Mount aus newsapp.main (docs/06 §6)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from newsapp import main as nm


def _client(tmp_path):
    return TestClient(nm.build_app(data_dir=tmp_path, start_timer=False))


def test_uikit_controls_css_serviert(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/ui-kit/controls.css")
        assert r.status_code == 200
        assert "dz-check" in r.text and "dz-panel" in r.text


def test_uikit_collapse_js_serviert(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/ui-kit/collapse.js")
        assert r.status_code == 200
        assert "initControls" in r.text


def test_startseite_haengt_bundle_ein(tmp_path):
    """Das Frontend referenziert controls.css + collapse.js (K2.4-Einhängung)."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert "/ui-kit/controls.css" in html
        assert "/ui-kit/collapse.js" in html
        assert "data-dz-collapsible" in html      # Artikel-Panel einklappbar


# --- P1 UI/UX (docs/27 §10): Reading-Kit + Verknüpfungs-Chip + Digest-Hero ---

def test_reading_css_serviert(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/ui-kit/reading.css")
        assert r.status_code == 200
        # Lese-Typografie + Magazin + Vollbild-Lesemodus
        assert ".dz-read" in r.text and "dz-magazine" in r.text and "dz-readview" in r.text


def test_verknuepfungs_chip_im_kit(tmp_path):
    """Der zentrale Verknüpfungs-Chip (docs/27 #1) liegt im Controls-Kit."""
    with _client(tmp_path) as c:
        assert ".dz-chip" in c.get("/ui-kit/controls.css").text


def test_startseite_digest_hero(tmp_path):
    """Digest-Hero + Reading-View + reading.css sind eingehängt (P1)."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert "/ui-kit/reading.css" in html
        assert "Sektor-Digest" in html            # Hero-Panel-Titel
        assert 'id="lesemodus"' in html           # Vollbild-Lesemodus-Overlay
        assert "openLesemodus" in html            # Lesemodus-Knopf verdrahtet
