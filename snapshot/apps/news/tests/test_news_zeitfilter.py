"""Tests Phase 2 — Artikel-Zeitfilter.

Zwei Ebenen: (1) die reinen Datum-Helfer (`_parse_dt`/`_zeit_cutoff`/`_eff_datum`)
und (2) der server-seitige `zeit`-Param am Cluster-Endpoint (gegen das effektive
Artikel-Datum = Veröffentlichung, Fallback Abrufzeit)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from newsapp import main as nm


def _client(tmp_path, monkeypatch, feeds=None):
    if feeds is not None:
        monkeypatch.setattr(nm, "_lade_feed", lambda url: feeds.get(url, []))
    app = nm.build_app(data_dir=tmp_path, start_timer=False)
    return TestClient(app)


# ----------------------------- reine Helfer ---------------------------------

def test_parse_dt_iso_rfc822_und_muell():
    assert nm._parse_dt("2026-06-20T10:00:00+00:00") is not None
    assert nm._parse_dt("2026-06-20T10:00:00Z") is not None          # Z-Suffix
    assert nm._parse_dt("Mon, 12 Jun 2026 10:00:00 GMT") is not None  # RFC-822 (Feeds)
    assert nm._parse_dt("") is None and nm._parse_dt(None) is None
    assert nm._parse_dt("kein datum") is None
    # naive ⇒ als UTC gedeutet (tzinfo gesetzt)
    assert nm._parse_dt("2026-06-20T10:00:00").tzinfo is not None


def test_zeit_cutoff():
    assert nm._zeit_cutoff("all") is None
    assert nm._zeit_cutoff("unbekannt") is None
    jetzt = datetime.now(timezone.utc)
    c7 = nm._zeit_cutoff("7d")
    assert 6.9 < (jetzt - c7).total_seconds() / 86400 < 7.1
    heute = nm._zeit_cutoff("today")
    assert heute.hour == 0 and heute.minute == 0          # Tagesbeginn UTC


def test_eff_datum_bevorzugt_published():
    pub = "2020-01-01T00:00:00+00:00"
    cre = "2026-06-26T00:00:00+00:00"
    assert nm._eff_datum({"published_at": pub, "created_at": cre}).year == 2020
    # ohne published ⇒ Fallback created
    assert nm._eff_datum({"published_at": None, "created_at": cre}).year == 2026


# --------------------------- Endpoint-Integration ---------------------------

def _iso(tage_alt: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=tage_alt)).isoformat()


def test_cluster_zeitfilter_endpoint(tmp_path, monkeypatch):
    feeds = {nm.SEED_QUELLEN[0][1]: [
        {"titel": "Frisch heute", "link": "https://x/frisch",
         "zusammenfassung": "", "published": _iso(0)},
        {"titel": "Hundert Tage alt", "link": "https://x/alt",
         "zusammenfassung": "", "published": _iso(100)},
        {"titel": "Ohne Datum", "link": "https://x/ohne",
         "zusammenfassung": "", "published": None},
    ]}
    with _client(tmp_path, monkeypatch, feeds) as c:
        c.post("/api/abrufen")

        def titel(zeit):
            r = c.get("/api/artikel/cluster?zeit=" + zeit).json()
            return {x["titel"] for x in r}

        # all: alle drei
        assert {"Frisch heute", "Hundert Tage alt", "Ohne Datum"} <= titel("all")
        # 7d: 100-Tage-Artikel raus; published=None fällt auf created_at (jetzt) ⇒ drin
        t7 = titel("7d")
        assert "Frisch heute" in t7 and "Ohne Datum" in t7
        assert "Hundert Tage alt" not in t7
        # 6m (183 T): 100-Tage-Artikel wieder dabei
        assert "Hundert Tage alt" in titel("6m")
        # created_at trägt das Zeitfeld jetzt im Cluster-Eintrag
        assert all("created_at" in x for x in c.get("/api/artikel/cluster").json())


def test_cluster_default_all(tmp_path, monkeypatch):
    feeds = {nm.SEED_QUELLEN[0][1]: [
        {"titel": "Uralt", "link": "https://x/uralt", "zusammenfassung": "",
         "published": _iso(900)}]}
    with _client(tmp_path, monkeypatch, feeds) as c:
        c.post("/api/abrufen")
        # ohne zeit-Param = all ⇒ auch ein 900-Tage-Artikel ist dabei
        assert any(x["titel"] == "Uralt" for x in c.get("/api/artikel/cluster").json())
        # 1y schließt ihn aus
        assert not any(x["titel"] == "Uralt"
                       for x in c.get("/api/artikel/cluster?zeit=1y").json())
