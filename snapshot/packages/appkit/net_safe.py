"""net_safe — geteiltes SSRF-Gate fürs ganze Netz (appkit Single-Source).

Jede Stelle, die Inhalte von einer **vom Nutzer/Feed/Webhook gelieferten URL**
holt, ist eine potenzielle **SSRF-Falle** (Server Side Request Forgery): ohne
Prüfung könnte ein Angreifer den Server interne Dienste (``127.0.0.1``,
``169.254.169.254``-Metadaten, Intranet-IPs) anzapfen lassen.

Dieses Modul ist der **eine kanonische Wächter** dafür (vorher app-lokal in
``news/extract.py``; promoted nach docs/33 §W-1, damit die Ingestion-Sicherheits-
Norm NR-1 + G4 + HE-1 EINE Heimat hat — News-Feeds, künftige Wearable-/Webhook-
Quellen, jede user-URL-Ingestion teilen genau diese Prüfung statt sie zu forken).

Prinzip (defense-in-depth):
  * nur ``http``/``https``;
  * der Host wird **aufgelöst** und **JEDE** Auflösung (alle A/AAAA-Records) muss
    eine **öffentliche** IP sein — private/loopback/link-local/reserved/multicast/
    unspecified Bereiche (inkl. IPv4-mapped IPv6) werden hart abgewiesen;
  * der Aufrufer prüft Redirects **Hop für Hop** neu (keine Umleitung ins interne
    Netz), siehe ``news/extract.py`` / ``news/main.py`` als Referenz-Aufrufer.
  * gegen **DNS-Rebinding** (TOCTOU) pinnen ``aufloesen_geprueft`` / ``pin_ziel`` die
    Verbindung auf die GEPRÜFTE IP (Host-Header + TLS-SNI bleiben der echte Name),
    sodass zwischen Prüfung und Abruf kein zweiter Lookup mehr auf ein internes Ziel
    umschwenken kann. ``ist_oeffentliche_url`` (nur bool) bleibt für Rückwärts-Kompat.

Fail-closed: alles, was nicht eindeutig öffentlich auflöst, ⇒ ``False`` bzw. ``None``.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

_ERLAUBTE_SCHEMATA = {"http", "https"}


def _ist_unsichere_ip(ip: ipaddress._BaseAddress) -> bool:
    """True, wenn die IP NICHT öffentlich erreichbar sein soll (SSRF-Schutz)."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:           # ::ffff:10.0.0.1 etc. auf den v4-Kern prüfen
        ip = mapped
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _aufloesen(host: str) -> list[ipaddress._BaseAddress]:
    """Host → IP-Liste. Literale IP ohne DNS; sonst getaddrinfo (alle Records)."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    ips: list[ipaddress._BaseAddress] = []
    for *_rest, sockaddr in socket.getaddrinfo(host, None):
        try:
            ips.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue
    return ips


def ist_oeffentliche_url(url: str) -> bool:
    """SSRF-Gate: nur http/https zu AUSSCHLIESSLICH öffentlichen IPs. Jede
    interne/private Auflösung (auch nur eine von mehreren) ⇒ False."""
    try:
        u = urlsplit(url)
    except Exception:
        return False
    if u.scheme not in _ERLAUBTE_SCHEMATA:
        return False
    host = u.hostname
    if not host:
        return False
    try:
        ips = _aufloesen(host)
    except Exception:
        return False
    if not ips:
        return False
    return all(not _ist_unsichere_ip(ip) for ip in ips)


def aufloesen_geprueft(url: str) -> tuple[str, str] | None:
    """SSRF-Pin gegen DNS-Rebinding (TOCTOU-Schließung): löst den Host EINMAL auf,
    prüft ALLE A/AAAA-Records und gibt EINE geprüfte, öffentliche IP + den Original-
    Host zurück. Der Aufrufer PINNT die Verbindung auf diese IP, statt den Host beim
    eigentlichen Abruf ein ZWEITES Mal aufzulösen — genau dieses zweite (evtl. vom
    Angreifer-DNS umgebogene) Lookup ist die Lücke, die ``ist_oeffentliche_url`` allein
    offen lässt. Rückgabe ``(ip, host)`` NUR wenn Schema http/https UND alle Auflösungen
    öffentlich; sonst ``None`` (fail-closed — dieselbe Semantik wie ``ist_oeffentliche_url``,
    nur mit gemerkter IP)."""
    try:
        u = urlsplit(url)
    except Exception:
        return None
    if u.scheme not in _ERLAUBTE_SCHEMATA:
        return None
    host = u.hostname
    if not host:
        return None
    try:
        ips = _aufloesen(host)
    except Exception:
        return None
    if not ips or any(_ist_unsichere_ip(ip) for ip in ips):
        return None
    return str(ips[0]), host


def pin_ziel(url: str) -> tuple[str, dict[str, str], dict[str, str]] | None:
    """Baut die httpx-Pin-Parameter für EINEN Hop ODER ``None`` (nicht öffentlich).
    Liefert ``(pin_url, headers, extensions)``:
      * ``pin_url`` zeigt auf die GEPRÜFTE IP ⇒ httpx verbindet garantiert dorthin,
        ohne den Host ein zweites Mal aufzulösen (schließt das DNS-Rebinding-Fenster);
      * ``headers`` trägt den Original-``Host`` (Name-based-Vhosts + Redirect-Semantik);
      * ``extensions`` setzt ``sni_hostname`` = Original-Host ⇒ TLS-SNI und die
        Zertifikatsprüfung laufen weiter gegen den echten Namen (kein Cert-Bruch bei HTTPS;
        httpcore nutzt ``server_hostname = sni_hostname or origin.host``).
    Nutzung: ``client.stream("GET", pin_url, headers=headers, extensions=extensions)``
    mit ``follow_redirects=False``; jeden Redirect-Hop gegen die ORIGINAL-Host-URL
    ``urljoin``en und neu ``pin_ziel``en."""
    ergebnis = aufloesen_geprueft(url)
    if ergebnis is None:
        return None
    ip, host = ergebnis
    if not host.isascii():
        # IDN (z. B. münchen.de): Header + SNI brauchen das A-Label — ein roher
        # Unicode-Host wäre ein ungültiger HTTP-Header (httpx wirft). Vor dem Pin
        # erledigte httpx diese Kodierung selbst; hier fail-closed bei Nicht-Kodierbarem.
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return None
    u = urlsplit(url)
    ip_host = f"[{ip}]" if ":" in ip else ip           # IPv6 in der Netloc klammern
    port = f":{u.port}" if u.port else ""
    pin_url = urlunsplit((u.scheme, ip_host + port, u.path, u.query, u.fragment))
    return pin_url, {"Host": host + port}, {"sni_hostname": host}
