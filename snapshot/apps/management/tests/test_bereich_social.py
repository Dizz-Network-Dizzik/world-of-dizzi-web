"""A5/V18 (docs/34) — per-Bereich-Social-Spur-Endpoint für Dizz Admins Bereichs-
Cockpit. ``kontext`` = ``bereich.management_kontext`` → Social-Bot-Name (der Bot ist
die Marken-/Themen-Achse, die Kanäle + Posts verbindet). READ-ONLY."""

from __future__ import annotations

from fastapi.testclient import TestClient

from managementapp import main as mm


def _client(tmp_path) -> TestClient:
    return TestClient(mm.build_app(data_dir=tmp_path))


def test_bereich_social_aggregiert_je_bot(tmp_path):
    with _client(tmp_path) as c:
        bx = c.post("/api/bots", json={"name": "Agentur X", "thema": "B2B"}).json()["id"]
        bp = c.post("/api/bots", json={"name": "Privat"}).json()["id"]
        # Kanäle: 2 an Agentur X, 1 an Privat (darf NICHT auftauchen)
        c.post("/api/kanaele", json={"plattform": "instagram", "handle": "@ag", "bot_id": bx})
        c.post("/api/kanaele", json={"plattform": "tiktok", "handle": "@agtt", "bot_id": bx})
        c.post("/api/kanaele", json={"plattform": "x", "handle": "@priv", "bot_id": bp})
        # Posts an Agentur X: 2 zukünftig geplant, 1 Entwurf, 1 vergangen geplant
        c.post("/api/posts", json={"titel": "A", "plattform": "instagram",
                                   "bot_id": bx, "geplant_fuer": "2030-08-01T10:00"})
        c.post("/api/posts", json={"titel": "B", "plattform": "instagram", "bot_id": bx})
        c.post("/api/posts", json={"titel": "C", "plattform": "tiktok",
                                   "bot_id": bx, "geplant_fuer": "2030-09-01T09:00"})
        c.post("/api/posts", json={"titel": "D", "plattform": "linkedin",
                                   "bot_id": bx, "geplant_fuer": "2020-01-01T10:00"})
        # Post an Privat (anderer Bot, darf NICHT auftauchen)
        c.post("/api/posts", json={"titel": "Z", "plattform": "x", "bot_id": bp})

        r = c.get("/api/bereich/social?kontext=agentur x").json()   # case-insensitiv
        assert r["kontext"] == "agentur x"
        assert [b["name"] for b in r["bots"]] == ["Agentur X"]
        assert r["anzahl_kanaele"] == 2
        assert {k["plattform"] for k in r["kanaele"]} == {"instagram", "tiktok"}
        assert r["posts"]["gesamt"] == 4
        assert r["posts"]["je_status"]["geplant"] == 3 and r["posts"]["je_status"]["entwurf"] == 1
        je_pl = {x["plattform"]: x["anzahl"] for x in r["posts"]["je_plattform"]}
        assert je_pl == {"instagram": 2, "tiktok": 1, "linkedin": 1}
        # nächste Posts: nur ZUKÜNFTIG geplante (vergangener linkedin-Post fliegt raus)
        titel = [p["titel"] for p in r["naechste_posts"]]
        assert titel == ["A", "C"]                       # aufsteigend nach geplant_fuer


def test_bereich_social_unbekannter_und_leerer_kontext(tmp_path):
    with _client(tmp_path) as c:
        leer = c.get("/api/bereich/social?kontext=gibtsnicht").json()
        assert leer["bots"] == [] and leer["anzahl_posts"] == 0
        r = c.get("/api/bereich/social").json()
        assert r["kontext"] == "" and r["kanaele"] == [] and r["posts"]["gesamt"] == 0


def test_bereich_social_via_bereich_kontext(tmp_path):
    """Umbau: hat ein lokaler Bereich einen ``kontext``, aggregiert V18 über dessen
    ``bereich_id`` (Kanäle/Bots/Posts im Bereich) — NICHT über den Bot-Namen."""
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "LHN", "art": "kunde",
                                          "kontext": "lhn"}).json()["id"]
        # Im Bereich: 1 Bot, 2 Kanäle, 2 Posts (1 zukünftig geplant) — Bot-Name ≠ kontext.
        bot = c.post("/api/bots", json={"name": "LHN-Redaktion", "bereich_id": b}).json()["id"]
        c.post("/api/kanaele", json={"plattform": "instagram", "handle": "@lhn", "bereich_id": b})
        c.post("/api/kanaele", json={"plattform": "linkedin", "handle": "lhn", "bereich_id": b})
        c.post("/api/posts", json={"titel": "Im Bereich", "plattform": "instagram",
                                   "bereich_id": b, "geplant_fuer": "2030-08-01T10:00"})
        c.post("/api/posts", json={"titel": "Entwurf", "plattform": "linkedin", "bereich_id": b})
        # Außerhalb des Bereichs (darf NICHT auftauchen)
        c.post("/api/posts", json={"titel": "Fremd", "plattform": "x"})

        r = c.get("/api/bereich/social?kontext=LHN").json()   # case-insensitiv über bereiche.kontext
        assert [bb["name"] for bb in r["bots"]] == ["LHN-Redaktion"]
        assert r["anzahl_kanaele"] == 2
        assert r["posts"]["gesamt"] == 2                       # Fremd-Post bleibt draußen
        assert r["posts"]["je_status"]["geplant"] == 1 and r["posts"]["je_status"]["entwurf"] == 1
        assert [p["titel"] for p in r["naechste_posts"]] == ["Im Bereich"]
        _ = bot


def test_bereich_social_kanon_vor_kontext(tmp_path):
    """V18-Kantenvertrag (docs/67 §10): kanon → quelle='kanon'; kontext → 'kontext';
    Bot-Namen-Fallback (Bestand) → 'bot'."""
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "LHN", "art": "kunde",
                                          "kontext": "lhn"}).json()["id"]
        c.post("/api/bots", json={"name": "LHN-Redaktion", "bereich_id": b})
        c.post("/api/kanaele", json={"plattform": "instagram", "handle": "@lhn", "bereich_id": b})
        c.post("/api/posts", json={"titel": "Im Bereich", "plattform": "instagram", "bereich_id": b})
        assert c.put(f"/api/bereiche/{b}/kanon", json={"kanon_id": "A-9"}).json()["ok"]
        # ① kanon (ohne kontext) aggregiert über den Bereich
        r = c.get("/api/bereich/social?kanon=A-9").json()
        assert r["quelle"] == "kanon" and [bb["name"] for bb in r["bots"]] == ["LHN-Redaktion"]
        # ② kontext (ohne kanon)
        assert c.get("/api/bereich/social?kontext=LHN").json()["quelle"] == "kontext"
        # ③ Bot-Namen-Fallback (Bestand): kontext matcht keinen Bereich, aber einen Bot-Namen
        c.post("/api/bots", json={"name": "Solo"})
        assert c.get("/api/bereich/social?kontext=Solo").json()["quelle"] == "bot"
