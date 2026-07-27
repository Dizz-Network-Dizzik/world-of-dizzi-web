"""App-Wächter-KI (Mini-Dizzi via set_app_ki): beantwortet die häufigsten
Finanz-Fragen DETERMINISTISCH aus den echten Zahlen — ohne Ollama, daher hier
voll testbar. Quelle der Antwort = 'app_ki' (nicht der Ollama-Fallback)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from moneyapp import main as mm

FIX = Path(__file__).resolve().parent / "fixtures"


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _setup(c):
    giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
    c.post("/api/import", json={"inhalt": (FIX / "sparkasse.csv").read_text(encoding="utf-8"),
                                "format": "csv", "zielkonto": giro})
    return giro


def _frage(c, text):
    return c.post("/api/ki/frage", json={"frage": text}).json()


def test_ki_registriert(tmp_path):
    # set_app_ki wurde verdrahtet ⇒ /api/ki/status meldet app_ki_registriert
    with _client(tmp_path) as c:
        assert c.get("/api/ki/status").json()["app_ki_registriert"] is True


def test_ki_nettovermoegen(tmp_path):
    with _client(tmp_path) as c:
        _setup(c)
        a = _frage(c, "Wie hoch ist mein Nettovermögen?")
        assert a["quelle"] == "app_ki"
        assert "2815.77" in a["antwort"]              # Giro-Saldo aus dem Import


def test_ki_cashflow(tmp_path):
    with _client(tmp_path) as c:
        _setup(c)
        a = _frage(c, "Wie sieht mein Cashflow aus, spare ich genug?")
        assert a["quelle"] == "app_ki"
        assert "Einnahmen" in a["antwort"] and "Saldo" in a["antwort"]


def test_ki_konten_und_abos(tmp_path):
    with _client(tmp_path) as c:
        _setup(c)
        assert _frage(c, "Zeig mir meine Konten")["quelle"] == "app_ki"
        a = _frage(c, "Was habe ich an Abos / Fixkosten?")
        assert a["quelle"] == "app_ki" and "Fixkost" in a["antwort"]


def test_ki_budget_im_rahmen(tmp_path):
    with _client(tmp_path) as c:
        a = _frage(c, "Sind meine Budgets überzogen?")
        assert a["quelle"] == "app_ki" and "Rahmen" in a["antwort"]


def test_ki_unbekannt_faellt_zurueck(tmp_path):
    with _client(tmp_path) as c:
        # Frage ohne Finanz-Bezug ⇒ App-KI schweigt ⇒ Fallback (ohne Ollama:
        # ehrlicher Hinweis, Quelle != app_ki)
        a = _frage(c, "Erzähl mir einen Witz über Astronauten")
        assert a["quelle"] != "app_ki"
        assert "antwort" in a
