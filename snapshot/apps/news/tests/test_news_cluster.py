"""Tests Cross-Source-Dedup / Story-Clustering (Backlog docs/33 §news).

Deterministisch + lokal: gleiche Story aus mehreren Feeds wird zusammengeführt,
verschiedene Stories bleiben getrennt (konservativ)."""

from __future__ import annotations

from newsapp import cluster


def test_titel_tokens_ohne_stoppwoerter():
    t = cluster.titel_tokens("Die EZB hebt den Leitzins an und die Märkte reagieren")
    assert "ezb" in t and "leitzins" in t and "märkte" in t
    assert "die" not in t and "den" not in t and "und" not in t and "an" not in t


def test_url_slug_tokens():
    s = cluster.url_slug_tokens("https://www.tagesschau.de/wirtschaft/ezb-leitzins-100.html")
    assert "ezb" in s and "leitzins" in s
    assert "100" not in s            # reine Zahl (ID/Datum) fällt weg


def test_clustere_fuehrt_gleiche_story_zusammen():
    artikel = [
        {"id": "1", "titel": "EZB hebt den Leitzins erneut an",
         "link": "https://a/ezb-leitzins", "quelle": "tagesschau", "sektor": "wirtschaft"},
        {"id": "2", "titel": "EZB hebt Leitzins erneut an, Märkte reagieren",
         "link": "https://b/ecb-rates", "quelle": "Guardian", "sektor": "wirtschaft"},
        {"id": "3", "titel": "Vulkan auf Island bricht erneut aus",
         "link": "https://c/island-vulkan", "quelle": "heise", "sektor": "allgemein"},
    ]
    cl = cluster.clustere(artikel)
    assert len(cl) == 2                          # EZB (2 Quellen) + Vulkan
    ezb = next(c for c in cl if "EZB" in c["titel"])
    assert ezb["anzahl"] == 2
    assert set(ezb["quellen"]) == {"tagesschau", "Guardian"}
    assert len(ezb["dubletten"]) == 1
    assert any("Vulkan" in c["titel"] and c["anzahl"] == 1 for c in cl)


def test_clustere_konservativ_trennt_verschiedene():
    artikel = [
        {"id": "1", "titel": "Bundestag beschließt Klimagesetz",
         "link": "https://a/klima", "quelle": "Q1", "sektor": "deutschland"},
        {"id": "2", "titel": "Apple stellt neuen Chip vor",
         "link": "https://b/apple-chip", "quelle": "Q2", "sektor": "tech"},
    ]
    cl = cluster.clustere(artikel)
    assert len(cl) == 2 and all(c["anzahl"] == 1 for c in cl)


def test_clustere_per_url_slug():
    # Titel unterschiedlich formuliert, aber identischer Slug ⇒ gleiche Story.
    artikel = [
        {"id": "1", "titel": "Marktbericht zum Wochenstart",
         "link": "https://a.de/news/tesla-rueckruf-batterie", "quelle": "A", "sektor": "x"},
        {"id": "2", "titel": "Was heute wichtig war",
         "link": "https://b.com/2026/tesla-rueckruf-batterie", "quelle": "B", "sektor": "x"},
    ]
    cl = cluster.clustere(artikel)
    assert len(cl) == 1 and cl[0]["anzahl"] == 2


def test_dedupe_liefert_einen_repraesentanten():
    artikel = [
        {"id": "1", "titel": "EZB hebt den Leitzins erneut an", "link": "https://a/ezb",
         "quelle": "Q1", "zusammenfassung": "voller Text A"},
        {"id": "2", "titel": "EZB hebt Leitzins erneut an heute", "link": "https://b/ezb",
         "quelle": "Q2", "zusammenfassung": "voller Text B"},
    ]
    dd = cluster.dedupe(artikel)
    assert len(dd) == 1
    assert dd[0]["id"] == "1"                       # erster = Repräsentant
    assert dd[0]["zusammenfassung"] == "voller Text A"   # voller Datensatz erhalten


def test_generischer_slug_video_mergt_nicht():
    # Regression 20.06.: alle „…/video-12345.html" reduzieren sich auf den Slug
    # {'video'} — verschiedene Beiträge derselben Quelle dürfen NICHT verschmelzen.
    artikel = [
        {"id": "1", "titel": "Europa erwärmt sich doppelt so schnell",
         "link": "https://t.de/multimedia/video/video-100.html", "quelle": "T", "sektor": "x"},
        {"id": "2", "titel": "Google startet KI-Suche in Deutschland",
         "link": "https://t.de/multimedia/video/video-200.html", "quelle": "T", "sektor": "x"},
        {"id": "3", "titel": "Tausende Stahlarbeiter protestieren",
         "link": "https://t.de/multimedia/video/video-300.html", "quelle": "T", "sektor": "x"},
    ]
    cl = cluster.clustere(artikel)
    assert len(cl) == 3 and all(c["anzahl"] == 1 for c in cl)


def test_leere_titel_mergen_nicht_ueber_kreuz():
    artikel = [
        {"id": "1", "titel": "", "link": "https://a/x", "quelle": "Q1"},
        {"id": "2", "titel": "", "link": "https://b/y", "quelle": "Q2"},
    ]
    cl = cluster.clustere(artikel)
    assert len(cl) == 2                             # keine Falsch-Verschmelzung
