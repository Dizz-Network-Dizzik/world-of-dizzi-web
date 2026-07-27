"""Volltext-Extraktion (Readability-artig) für Dizz News — Backlog docs/33 §news.

Feeds liefern oft nur eine kurze ``summary`` (≤600 Z.). Für (a) bessere KI-Eingabe
(Sektor-Briefings/Fragen) und (b) einen ablenkungsfreien **Lesemodus** holen wir
zum Artikel-Link den HTML-Haupttext und destillieren ihn deterministisch.

SICHERHEIT (Gesetz 4 — der Extraktor holt Inhalte von BELIEBIGEN, vom Feed
gelieferten URLs; das ist die klassische SSRF-Falle):
  * **SSRF-Gate** ``ist_oeffentliche_url`` (geteilt in ``appkit.net_safe``, hier
    re-exportiert): nur http/https; der Host wird aufgelöst
    und JEDE Auflösung muss eine ÖFFENTLICHE IP sein — private/loopback/link-local/
    reserved/multicast/unspecified Bereiche (inkl. IPv4-mapped IPv6) werden hart
    abgewiesen. Redirects werden Hop für Hop neu geprüft (keine Umleitung ins
    interne Netz). Damit kann der Extraktor keine internen Dienste anzapfen.
  * **Größen-Limit** (gestreamt, harte Byte-Obergrenze) ⇒ kein Speicher-DoS.
  * **Content-Type-Filter** (nur HTML/XML) ⇒ keine Binär-/Riesendateien.
  * **Sicherer Parser**: stdlib ``html.parser`` (keine externen Entities, kein
    DTD-Resolving, kein lxml/XXE). ``convert_charrefs`` macht nur Standard-
    Zeichenreferenzen.
Alles **best-effort**: jeder Fehler ⇒ leerer String, nie eine Exception nach außen
(damit der Feed-Abruf je Artikel isoliert bleibt und nie crasht).

Hinweis (Gesetz 6): Dies ist eine **leichtgewichtige Absatz-Dichte-Heuristik**
(stdlib, 0 Abhängigkeiten), keine volle Readability-Engine. Eine spätere Upgrade-
Stufe (trafilatura/readability-lxml) ist als „FÜR WORLD-CHAT"-Notiz vermerkt.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin

# SSRF-Gate lebt jetzt geteilt in appkit (docs/33 §W-1, ``appkit.net_safe``) — hier
# re-exportiert, damit ``extract.ist_oeffentliche_url`` (News-interne + ``main.py``-
# Aufrufer + Tests) unverändert gültig bleibt. EINE Quelle netzweit (NR-1/G4/HE-1).
from appkit.net_safe import (  # noqa: F401  (Re-Export für Rückwärts-Kompatibilität)
    _aufloesen,
    _ist_unsichere_ip,
    aufloesen_geprueft,
    ist_oeffentliche_url,
    pin_ziel,
)

_UA = "DizzNews/1.0 (+localhost; Lesemodus-Extraktor)"

# Standard-Grenzen (am Aufruf überschreibbar).
MAX_BYTES = 1_500_000        # ~1.5 MiB HTML reichen für jeden Artikel
MAX_ZEICHEN = 20_000         # destillierter Text wird hierauf gedeckelt
MIN_ABSATZ = 40              # kürzere <p> = meist Navi/Teaser ⇒ verworfen


# SSRF-Gate (``_ist_unsichere_ip`` / ``_aufloesen`` / ``ist_oeffentliche_url``)
# wurde nach ``appkit.net_safe`` promoted (oben re-importiert) — EINE Quelle netzweit.


# --------------------------- Haupttext-Parser -------------------------------

# Container, deren Text Navigation/Beiwerk ist (NUR zuverlässig PAARIGE, NICHT-void
# Tags — void-Elemente wie <input> würden den Skip-Zähler dauerhaft hochhalten und
# den Rest der Seite verschlucken; das große Rauschen [script/style/svg/Kommentare]
# wird ohnehin vorab per Regex entfernt).
_SKIP_CONTAINER = {"nav", "header", "footer", "aside", "figure", "figcaption"}

# Vorab-Strip: entfernt Blöcke, die Parser stören (riesige Inline-SVG) oder reines
# Rauschen sind. DOTALL + IGNORECASE; nicht-gierig.
_VORAB = re.compile(
    r"<!--.*?-->"
    r"|<script\b[^>]*>.*?</script>"
    r"|<style\b[^>]*>.*?</style>"
    r"|<svg\b[^>]*>.*?</svg>"
    r"|<noscript\b[^>]*>.*?</noscript>"
    r"|<head\b[^>]*>.*?</head>",
    re.DOTALL | re.IGNORECASE)


class _HaupttextParser(HTMLParser):
    """Sammelt Text aus Inhalts-Blöcken; ignoriert Navigations-Container.

    ``skip_container=False`` ⇒ Fallback-Modus ohne Container-Skip (greift, falls der
    Container-Skip nichts liefert, z. B. bei kaputtem Markup) — der Längen-Filter in
    ``haupttext`` hält dann Navi-Schnipsel draußen."""

    _BLOCK = {"p", "h1", "h2", "h3", "h4", "li", "blockquote"}

    def __init__(self, skip_container: bool = True) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_container = skip_container
        self._skip = 0
        self._aktiv: str | None = None
        self._buf: list[str] = []
        self.bloecke: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if self._skip_container and tag in _SKIP_CONTAINER:
            self._skip += 1
            return
        if tag in self._BLOCK:
            self._abschluss()
            self._aktiv = tag
            self._buf = []

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        if tag == "br" and self._aktiv is not None and self._skip == 0:
            self._buf.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_container and tag in _SKIP_CONTAINER:
            if self._skip > 0:
                self._skip -= 1
            return
        if tag == self._aktiv:
            self._abschluss()

    def handle_data(self, data: str) -> None:
        if self._skip == 0 and self._aktiv is not None:
            self._buf.append(data)

    def _abschluss(self) -> None:
        if self._aktiv is not None:
            txt = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if txt:
                self.bloecke.append((self._aktiv, txt))
        self._aktiv = None
        self._buf = []


def _bloecke(html: str, skip_container: bool) -> list[tuple[str, str]]:
    p = _HaupttextParser(skip_container=skip_container)
    try:
        p.feed(html)
    except Exception:
        pass
    finally:
        p._abschluss()
    return p.bloecke


def _verdichte(bloecke: list[tuple[str, str]], min_absatz: int) -> list[str]:
    absaetze: list[str] = []
    for tag, txt in bloecke:
        if tag in ("h1", "h2", "h3", "h4"):
            if len(txt) >= 20:               # Mini-/Navi-Überschriften verwerfen
                absaetze.append(txt)
        elif tag == "li":
            if len(txt) >= min_absatz:
                absaetze.append("• " + txt)
        else:                                # p / blockquote
            if len(txt) >= min_absatz:
                absaetze.append(txt)
    return absaetze


def haupttext(html: str, *, max_zeichen: int = MAX_ZEICHEN,
              min_absatz: int = MIN_ABSATZ) -> str:
    """Destilliert den lesbaren Haupttext aus HTML (deterministisch).

    Heuristik: Rauschen (script/style/svg/Kommentare) vorab strippen; dann nur
    Inhalts-Blöcke (Absätze/Überschriften/Listen/Zitate) ausserhalb der Navi-
    Container; kurze <p> (< ``min_absatz`` Z.) gelten als Navi/Teaser (Dichte-
    Filter). Liefert der Container-Skip NICHTS (kaputtes Markup), greift ein
    zweiter Pass OHNE Container-Skip — dann hält allein der Längen-Filter Navi
    draußen, statt am Ende leer auszugehen."""
    rein = _VORAB.sub(" ", html or "")
    absaetze = _verdichte(_bloecke(rein, skip_container=True), min_absatz)
    if not absaetze:                          # Fallback: ohne Container-Skip
        absaetze = _verdichte(_bloecke(rein, skip_container=False), min_absatz)
    return "\n\n".join(absaetze).strip()[:max_zeichen]


# ------------------------------ Netz-Abruf ----------------------------------

def _hole_html(url: str, *, timeout: float, max_bytes: int) -> str | None:
    """Realer Abruf (httpx): SSRF-revalidiert JE Redirect-Hop UND auf die geprüfte IP
    GEPINNT (kein zweiter DNS-Lookup zwischen Prüfung und Abruf ⇒ DNS-Rebinding
    geschlossen), gestreamt + hart gedeckelt, nur HTML/XML. Liefert HTML-Text oder None."""
    import httpx
    ziel = url
    with httpx.Client(follow_redirects=False,
                      headers={"User-Agent": _UA},
                      timeout=httpx.Timeout(timeout, connect=min(5.0, timeout))) as client:
        for _hop in range(4):                 # bis zu 3 Redirects, jeder neu geprüft + gepinnt
            pin = pin_ziel(ziel)              # SSRF-Gate + IP-Pin gegen DNS-Rebinding
            if pin is None:
                return None
            pin_url, pin_headers, pin_ext = pin
            with client.stream("GET", pin_url, headers=pin_headers, extensions=pin_ext) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location")
                    if not loc:
                        return None
                    ziel = urljoin(ziel, loc)
                    continue
                if r.status_code != 200:
                    return None
                ct = (r.headers.get("content-type") or "").lower()
                if "html" not in ct and "xml" not in ct:
                    return None
                total, buf = 0, []
                for chunk in r.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        break
                    buf.append(chunk)
                raw = b"".join(buf)
                enc = r.encoding or "utf-8"
                try:
                    return raw.decode(enc, "replace")
                except LookupError:
                    return raw.decode("utf-8", "replace")
    return None


def extrahiere_volltext(url: str, *,
                        http_get: Callable[[str], Any] | None = None,
                        max_bytes: int = MAX_BYTES, timeout: float = 8.0,
                        max_zeichen: int = MAX_ZEICHEN) -> str:
    """Best-effort Haupttext zu einem Artikel-Link. Wirft NIE — Fehler ⇒ ''.

    ``http_get`` ist ein Test-/Injektions-Seam (wie ``http_post`` in ki.py): wird
    es gesetzt, liefert es direkt den HTML-Text (oder ein Objekt mit ``.text``) und
    der Netz-/SSRF-Pfad wird übersprungen. Im Echtbetrieb (``None``) greift der
    volle SSRF-geschützte httpx-Abruf."""
    try:
        if not isinstance(url, str) or not url.strip():
            return ""
        if http_get is not None:
            res = http_get(url)
            html = res if isinstance(res, str) else (getattr(res, "text", "") or "")
        else:
            if not ist_oeffentliche_url(url):
                return ""
            html = _hole_html(url, timeout=timeout, max_bytes=max_bytes) or ""
        return haupttext(html, max_zeichen=max_zeichen)
    except Exception:
        return ""
