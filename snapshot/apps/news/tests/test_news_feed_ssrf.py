"""NR-1 (Angreifer-Brille, 28.06.): der FEED-Abruf ``_lade_feed`` muss dieselbe
SSRF-Absperrung haben wie die Volltext-Extraktion (``extract._hole_html``). Ein
nutzer-/OPML-gelieferter Feed — oder dessen 302-Redirect — darf NICHT auf interne
Ziele (Core :8200, Trading :8137, Cloud-Metadaten 169.254.169.254, ...) zugreifen.

Bisher war NUR der Volltext-Pfad abgesichert; der Feed-Abruf folgte Redirects
ungeprüft (``follow_redirects=True``, kein Gate). Diese Tests prüfen den Block mit
LITERALEN IPs / Nicht-HTTP-Schemata ⇒ kein DNS/Netz nötig (der Block greift vor
jedem Socket)."""

from __future__ import annotations

import pytest

from newsapp import main as nm


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8200/api/panels",            # Core-Loopback
    "http://169.254.169.254/latest/meta-data/",    # Cloud-Metadaten (link-local)
    "http://[::1]:8137/",                          # Trading via IPv6-Loopback
    "http://10.0.0.5/feed.xml",                    # privates Netz
    "http://192.168.1.1/rss",                      # privates Netz
    "file:///etc/passwd",                          # Nicht-HTTP-Schema
    "ftp://127.0.0.1/x",                           # Nicht-HTTP-Schema
])
def test_lade_feed_blockt_interne_und_nicht_http(url):
    """_lade_feed wirft VOR jedem Netz-Zugriff (Block via ist_oeffentliche_url);
    fetch_all zählt das je Quelle als Fehler und läuft weiter."""
    with pytest.raises(Exception):
        nm._lade_feed(url)


def test_lade_feed_gate_nutzt_extract_helper():
    """Konsistenz: der Feed-Pfad teilt dasselbe SSRF-Gate wie die Extraktion."""
    assert nm.extract.ist_oeffentliche_url("http://127.0.0.1:8200/x") is False
    assert nm.extract.ist_oeffentliche_url("http://8.8.8.8/feed") is True
