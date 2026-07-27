"""Tests Volltext-Extraktion (Backlog docs/33 §news).

Zwei Ebenen: (1) der reine Extraktor ``newsapp.extract`` — Haupttext-Heuristik +
SSRF-Gate (mit literalen IPs, kein DNS/Netz im Test); (2) die Verdrahtung in der
App — Bulk-Extraktion beim Abruf (gated/isoliert), On-Demand-Lesemodus-Endpoint,
Rückfall ohne Extraktor."""

from __future__ import annotations

from fastapi.testclient import TestClient

from newsapp import extract
from newsapp import main as nm


# ----------------------------- Extraktor pur --------------------------------

_HTML = """<html><head><title>T</title><style>.x{color:red}</style></head>
<body>
  <nav><a>Home</a><a>Menü</a></nav>
  <header>Seiten Kopf Navigation Leiste hier oben</header>
  <article>
    <h1>Eine wichtige Schlagzeile über das Thema</h1>
    <p>Dies ist der erste substantielle Absatz mit genuegend Inhalt, um den
       Dichtefilter sicher zu passieren und im Ergebnis zu landen.</p>
    <p>kurz</p>
    <script>var x = "geheimer skript inhalt nicht anzeigen";</script>
    <p>Ein zweiter ausfuehrlicher Absatz, der ebenfalls lang genug ist und
       echten Fliesstext enthaelt fuer die Extraktion.</p>
  </article>
  <footer>Fusszeile Impressum Datenschutz Kontakt Ueber uns alle Rechte</footer>
</body></html>"""


def test_haupttext_extrahiert_und_filtert():
    t = extract.haupttext(_HTML)
    assert "erste substantielle Absatz" in t
    assert "zweiter ausfuehrlicher Absatz" in t
    assert "wichtige Schlagzeile" in t          # h1 (>=20 Z.)
    assert "geheimer skript" not in t           # <script> ignoriert
    assert "kurz" not in t                       # Dichtefilter (zu kurz)
    assert "Home" not in t and "Menü" not in t   # <nav>
    assert "Impressum" not in t                   # <footer>


def test_haupttext_leer_bei_muell():
    assert extract.haupttext("") == ""
    assert extract.haupttext("<html><body><div>nur divs</div></body></html>") == ""


def test_haupttext_robust_gegen_void_input_und_svg():
    # Regression 20.06.: ein Such-<form> mit void-<input> (kein </input>) durfte
    # NICHT den Skip-Zähler dauerhaft hochhalten und den Artikel danach schlucken;
    # riesige Inline-SVG (z. B. tagesschau-Logo) wird vorab gestrippt.
    html = ("<html><body>"
            "<form role='search'><input type='text' name='q'></form>"
            "<svg viewBox='0 0 9 9'><path d='M0 0 L9 9 Z'/></svg>"
            "<article><p>Dies ist der eigentliche Artikeltext, der trotz Suchformular "
            "und Inline-SVG zuverlaessig extrahiert werden muss.</p></article>"
            "</body></html>")
    t = extract.haupttext(html)
    assert "eigentliche Artikeltext" in t
    assert "path" not in t and "viewBox" not in t


def test_haupttext_fallback_ohne_container():
    # Kaputtes Markup: ungeschlossenes <nav> würde mit Container-Skip ALLES
    # verschlucken — der Fallback-Pass (ohne Skip) rettet den langen Absatz.
    html = ("<html><body><nav>Menü Punkt Eins"
            "<p>Ein hinreichend langer Inhaltsabsatz mit echtem Fliesstext, der "
            "auch ohne sauberen Container erkannt werden soll.</p>"
            "</body></html>")
    assert "hinreichend langer Inhaltsabsatz" in extract.haupttext(html)


def test_ssrf_gate_blockt_internes():
    blocken = [
        "http://127.0.0.1/x", "http://10.0.0.5/x", "http://192.168.1.1/",
        "http://169.254.1.1/", "http://[::1]/", "http://0.0.0.0/",
        "ftp://example.com/x", "file:///etc/passwd", "http:///kein-host",
        "kein-url", "http://[::ffff:127.0.0.1]/",
    ]
    for u in blocken:
        assert extract.ist_oeffentliche_url(u) is False, u


def test_ssrf_gate_erlaubt_oeffentliche_ip():
    assert extract.ist_oeffentliche_url("http://8.8.8.8/x") is True
    assert extract.ist_oeffentliche_url("https://1.1.1.1/") is True
    assert extract.ist_oeffentliche_url("http://[2001:4860:4860::8888]/") is True


def test_extrahiere_volltext_injektion():
    # http_get-Seam liefert direkt HTML ⇒ kein Netz, SSRF übersprungen.
    out = extract.extrahiere_volltext("https://egal/x", http_get=lambda u: _HTML)
    assert "erste substantielle Absatz" in out


def test_extrahiere_volltext_wirft_nie():
    def boom(_u):
        raise RuntimeError("kaputt")
    assert extract.extrahiere_volltext("https://egal/x", http_get=boom) == ""
    assert extract.extrahiere_volltext("") == ""
    # realer Pfad gegen interne URL ⇒ SSRF-Block ⇒ "" (kein Netz)
    assert extract.extrahiere_volltext("http://127.0.0.1/x") == ""


# ----------------------------- App-Verdrahtung ------------------------------

def _client(tmp_path, monkeypatch, feeds=None, volltext=None):
    if feeds is not None:
        monkeypatch.setattr(nm, "_lade_feed", lambda url: feeds.get(url, []))
    vfn = (lambda url: (volltext or {}).get(url, "")) if volltext is not None else None
    app = nm.build_app(data_dir=tmp_path, start_timer=False, volltext_fn=vfn)
    return TestClient(app)


def test_abruf_extrahiert_und_lesemodus(tmp_path, monkeypatch):
    link = "https://x/story-eins"
    feeds = {nm.SEED_QUELLEN[0][1]: [
        {"titel": "Story Eins", "link": link, "zusammenfassung": "kurz", "published": None}]}
    volltext = {link: "Dies ist der ausfuehrliche extrahierte Haupttext des Artikels."}
    with _client(tmp_path, monkeypatch, feeds=feeds, volltext=volltext) as c:
        r = c.post("/api/abrufen").json()
        assert r["neu"] >= 1 and r["volltext"] == 1
        a = next(x for x in c.get("/api/artikel").json() if x["link"] == link)
        assert a["volltext_status"] == "ok"
        v = c.get("/api/artikel/" + a["id"] + "/volltext").json()
        assert "extrahierte Haupttext" in v["volltext"]
        assert v["status"] == "ok" and v["rueckfall"] is False


def test_setting_aus_stoppt_bulk_nicht_ondemand(tmp_path, monkeypatch):
    link = "https://x/story-zwei"
    feeds = {nm.SEED_QUELLEN[0][1]: [
        {"titel": "Story Zwei", "link": link, "zusammenfassung": "s", "published": None}]}
    volltext = {link: "Langer Haupttext zum Testen, ausreichend Inhalt vorhanden hier."}
    with _client(tmp_path, monkeypatch, feeds=feeds, volltext=volltext) as c:
        assert c.put("/api/settings", json={"key": "volltext_extraktion",
                                            "value": False}).status_code == 200
        assert c.post("/api/abrufen").json()["volltext"] == 0   # Bulk aus
        a = next(x for x in c.get("/api/artikel").json() if x["link"] == link)
        assert a["volltext_status"] in (None, "")
        # Lesemodus (Nutzer-Aktion) extrahiert trotzdem on-demand + cached
        v = c.get("/api/artikel/" + a["id"] + "/volltext").json()
        assert "Langer Haupttext" in v["volltext"] and v["status"] == "ok"
        a2 = next(x for x in c.get("/api/artikel").json() if x["link"] == link)
        assert a2["volltext_status"] == "ok"                    # jetzt gecached


def test_ohne_extraktor_rueckfall_auf_summary(tmp_path, monkeypatch):
    link = "https://x/story-drei"
    feeds = {nm.SEED_QUELLEN[0][1]: [
        {"titel": "Story Drei", "link": link,
         "zusammenfassung": "<p>Zusammenfassung Text</p>", "published": None}]}
    monkeypatch.setattr(nm, "_lade_feed", lambda url: feeds.get(url, []))
    app = nm.build_app(data_dir=tmp_path, start_timer=False)   # volltext_fn=None
    with TestClient(app) as c:
        assert c.post("/api/abrufen").json()["volltext"] == 0
        a = next(x for x in c.get("/api/artikel").json() if x["link"] == link)
        v = c.get("/api/artikel/" + a["id"] + "/volltext").json()
        assert v["rueckfall"] is True
        assert "Zusammenfassung Text" in v["volltext"]          # HTML-frei
        assert "<p>" not in v["volltext"]


def test_volltext_fehler_isoliert_kein_crash(tmp_path, monkeypatch):
    link = "https://x/boom"
    feeds = {nm.SEED_QUELLEN[0][1]: [
        {"titel": "Boom", "link": link, "zusammenfassung": "s", "published": None}]}

    def boom(_url):
        raise RuntimeError("kaputt")
    monkeypatch.setattr(nm, "_lade_feed", lambda url: feeds.get(url, []))
    app = nm.build_app(data_dir=tmp_path, start_timer=False, volltext_fn=boom)
    with TestClient(app) as c:
        r = c.post("/api/abrufen").json()
        assert r["neu"] >= 1 and r["volltext"] == 0             # versucht, isoliert
        a = next(x for x in c.get("/api/artikel").json() if x["link"] == link)
        assert a["volltext_status"] == "fehler"


def test_cluster_endpoint_fuehrt_zusammen(tmp_path, monkeypatch):
    s1, s2 = nm.SEED_QUELLEN[0][1], nm.SEED_QUELLEN[2][1]
    feeds = {
        s1: [{"titel": "EZB hebt den Leitzins erneut an",
              "link": "https://a/ezb-leitzins", "zusammenfassung": "", "published": None}],
        s2: [{"titel": "EZB hebt Leitzins erneut an, Märkte reagieren",
              "link": "https://b/ecb-rates", "zusammenfassung": "", "published": None},
             {"titel": "Vulkan auf Island bricht erneut aus",
              "link": "https://b/island-vulkan", "zusammenfassung": "", "published": None}],
    }
    with _client(tmp_path, monkeypatch, feeds=feeds) as c:
        c.post("/api/abrufen")
        cl = c.get("/api/artikel/cluster").json()
        ezb = [x for x in cl if "EZB" in x["titel"]]
        assert len(ezb) == 1 and ezb[0]["anzahl"] == 2 and len(ezb[0]["quellen"]) == 2
        assert any("Vulkan" in x["titel"] for x in cl)
