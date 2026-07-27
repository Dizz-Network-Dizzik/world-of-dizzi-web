"""Tests für das geteilte SSRF-Gate ``appkit.net_safe`` (docs/33 §W-1).

Hermetisch: literale IPs lösen ohne DNS auf; für Hostnamen wird ``_aufloesen``
gemonkeypatcht (kein Netzzugriff im Test).
"""

from __future__ import annotations

import ipaddress

import pytest

from appkit import net_safe


# ----- literale IPs: keine DNS nötig -----------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x",          # loopback
    "http://10.0.0.5/x",           # privat
    "http://192.168.1.10/x",       # privat
    "http://169.254.169.254/meta", # link-local (Cloud-Metadaten!)
    "http://[::1]/x",              # IPv6 loopback
    "http://[::ffff:10.0.0.1]/x",  # IPv4-mapped IPv6 → v4-Kern privat
    "http://0.0.0.0/x",            # unspecified
])
def test_interne_ip_wird_geblockt(url):
    assert net_safe.ist_oeffentliche_url(url) is False


@pytest.mark.parametrize("url", [
    "http://8.8.8.8/feed",
    "https://1.1.1.1/feed",
])
def test_oeffentliche_ip_erlaubt(url):
    assert net_safe.ist_oeffentliche_url(url) is True


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",   # kein http/https
    "ftp://8.8.8.8/x",      # kein http/https
    "gopher://8.8.8.8/x",
    "http://",              # kein Host
    "not a url",            # kein Schema/Host
    "",
])
def test_nicht_http_oder_hostlos_wird_geblockt(url):
    assert net_safe.ist_oeffentliche_url(url) is False


# ----- Hostname-Auflösung (gemonkeypatcht, kein Netz) ------------------------

def test_hostname_mit_privater_aufloesung_blockt(monkeypatch):
    """Auch wenn EINE von mehreren Auflösungen privat ist ⇒ False (kein Rebind)."""
    monkeypatch.setattr(net_safe, "_aufloesen", lambda host: [
        ipaddress.ip_address("8.8.8.8"),
        ipaddress.ip_address("127.0.0.1"),
    ])
    assert net_safe.ist_oeffentliche_url("http://evil.example/x") is False


def test_hostname_rein_oeffentlich_erlaubt(monkeypatch):
    monkeypatch.setattr(net_safe, "_aufloesen", lambda host: [
        ipaddress.ip_address("93.184.216.34"),  # example.com
    ])
    assert net_safe.ist_oeffentliche_url("http://example.com/x") is True


def test_aufloesung_leer_blockt(monkeypatch):
    monkeypatch.setattr(net_safe, "_aufloesen", lambda host: [])
    assert net_safe.ist_oeffentliche_url("http://nx.example/x") is False


def test_aufloesung_fehler_failclosed(monkeypatch):
    def boom(host):
        raise OSError("DNS down")
    monkeypatch.setattr(net_safe, "_aufloesen", boom)
    assert net_safe.ist_oeffentliche_url("http://x.example/x") is False


# ----- _ist_unsichere_ip direkt ----------------------------------------------

@pytest.mark.parametrize("ip,unsicher", [
    ("127.0.0.1", True),
    ("10.1.2.3", True),
    ("169.254.1.1", True),
    ("224.0.0.1", True),       # multicast
    ("8.8.8.8", False),
    ("93.184.216.34", False),
])
def test_ist_unsichere_ip(ip, unsicher):
    assert net_safe._ist_unsichere_ip(ipaddress.ip_address(ip)) is unsicher


# ----- aufloesen_geprueft / pin_ziel: DNS-Rebinding-Pin ----------------------

def test_aufloesen_geprueft_rein_oeffentlich(monkeypatch):
    monkeypatch.setattr(net_safe, "_aufloesen",
                        lambda host: [ipaddress.ip_address("93.184.216.34")])
    assert net_safe.aufloesen_geprueft("https://example.com/x") == ("93.184.216.34", "example.com")


def test_aufloesen_geprueft_mixed_failclosed(monkeypatch):
    """EINE interne Auflösung reicht ⇒ None (wie ist_oeffentliche_url)."""
    monkeypatch.setattr(net_safe, "_aufloesen", lambda host: [
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("127.0.0.1"),
    ])
    assert net_safe.aufloesen_geprueft("https://example.com/x") is None


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://", ""])
def test_aufloesen_geprueft_schema_oder_hostlos(url):
    assert net_safe.aufloesen_geprueft(url) is None


def test_pin_ziel_struktur(monkeypatch):
    monkeypatch.setattr(net_safe, "_aufloesen",
                        lambda host: [ipaddress.ip_address("93.184.216.34")])
    pin_url, headers, ext = net_safe.pin_ziel("https://example.com/feed?a=1")
    assert pin_url == "https://93.184.216.34/feed?a=1"      # verbindet zur IP, nicht zum Namen
    assert headers == {"Host": "example.com"}               # Vhost-/Redirect-Semantik
    assert ext == {"sni_hostname": "example.com"}           # TLS-SNI + Cert gegen den Namen


def test_pin_ziel_ipv6_und_port(monkeypatch):
    monkeypatch.setattr(net_safe, "_aufloesen",
                        lambda host: [ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946")])
    pin_url, headers, _ = net_safe.pin_ziel("https://example.com:8443/x")
    assert pin_url == "https://[2606:2800:220:1:248:1893:25c8:1946]:8443/x"
    assert headers == {"Host": "example.com:8443"}


def test_pin_ziel_idn_host_als_a_label(monkeypatch):
    """IDN-Hosts: Host-Header + SNI müssen das A-Label tragen (roher Unicode wäre
    ein ungültiger HTTP-Header — httpx wirft UnicodeEncodeError)."""
    monkeypatch.setattr(net_safe, "_aufloesen",
                        lambda host: [ipaddress.ip_address("93.184.216.34")])
    pin_url, headers, ext = net_safe.pin_ziel("https://münchen.de/feed")
    assert pin_url == "https://93.184.216.34/feed"
    assert headers == {"Host": "xn--mnchen-3ya.de"}
    assert ext == {"sni_hostname": "xn--mnchen-3ya.de"}


def test_pin_ziel_intern_none(monkeypatch):
    monkeypatch.setattr(net_safe, "_aufloesen",
                        lambda host: [ipaddress.ip_address("127.0.0.1")])
    assert net_safe.pin_ziel("http://rebind.test/x") is None


def test_pin_ziel_schliesst_rebinding_fenster(monkeypatch):
    """1. Auflösung (Prüfung) öffentlich, danach intern: der Pin fixiert die
    öffentliche IP als URL-Literal ⇒ httpx verbindet garantiert dorthin und kann
    beim Abruf nicht mehr auf die interne IP umschwenken (kein zweiter Lookup)."""
    calls = {"n": 0}

    def stateful(host):
        calls["n"] += 1
        return [ipaddress.ip_address("93.184.216.34" if calls["n"] == 1 else "127.0.0.1")]

    monkeypatch.setattr(net_safe, "_aufloesen", stateful)
    pin_url, _, _ = net_safe.pin_ziel("http://rebind.test/feed")
    assert pin_url == "http://93.184.216.34/feed"   # gepinnt auf die geprüfte (öffentliche) IP


# (Den Re-Export ``news.extract.ist_oeffentliche_url``/``pin_ziel`` → ``net_safe``
#  deckt die News-Suite ab: ``apps/news/tests/test_news_feed_ssrf.py``.)
