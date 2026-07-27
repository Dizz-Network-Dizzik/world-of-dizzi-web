"""appkit.vision + OllamaRuntime.strukturiert(bilder=) — die VLM-Naht (KA-M7 C3).

Ollama-frei: der ``http_post``/``http_get``-Seam ist gefakt (Muster test_ollama_runtime).
Beweist (a) dass ``bilder=`` base64 ins ``images``-Feld hängt UND ohne ``bilder`` die
Payload byte-gleich zum Vor-C3-Verhalten bleibt (Regression), (b) die vision-Helfer +
den verfuegbar-Ping mit ihren Fehler-Verträgen (nie werfen, ehrlich None/False).
"""

from __future__ import annotations

import base64
import json

from pydantic import BaseModel

from appkit import runtime as rt
from appkit import vision


class _Text(BaseModel):
    text: str


def _resp(payload, status=200):
    class _R:
        status_code = status

        def json(self):
            return {"message": {"content": json.dumps(payload)
                                if not isinstance(payload, str) else payload}}
    return _R()


# --- OllamaRuntime.strukturiert(bilder=) -------------------------------------

def test_bilder_haengt_base64_images_an():
    gesehen = {}

    def fake(url, daten):
        gesehen["daten"] = daten
        return _resp({"text": "erkannt"})

    r = rt.OllamaRuntime().strukturiert(
        "sys", "usr", schema=_Text, modell="qwen2.5vl:7b",
        bilder=[b"\x89PNGdata"], http_post=fake)
    assert r is not None and r.text == "erkannt"
    user = gesehen["daten"]["messages"][-1]
    assert user["role"] == "user" and user["content"] == "usr"
    assert user["images"] == [base64.b64encode(b"\x89PNGdata").decode("ascii")]


def test_ohne_bilder_kein_images_key_bytegleich():
    gesehen = {}

    def fake(url, daten):
        gesehen["daten"] = daten
        return _resp({"text": "x"})

    rt.OllamaRuntime().strukturiert("sys", "usr", schema=_Text, modell="m", http_post=fake)
    # byte-gleich zum Vor-C3-Verhalten: exakt {role,content}, KEIN images-Key
    assert gesehen["daten"]["messages"][-1] == {"role": "user", "content": "usr"}


def test_leere_bilderliste_kein_images_key():
    gesehen = {}

    def fake(url, daten):
        gesehen["daten"] = daten
        return _resp({"text": "x"})

    rt.OllamaRuntime().strukturiert("sys", "usr", schema=_Text, modell="m",
                                    bilder=[], http_post=fake)
    assert "images" not in gesehen["daten"]["messages"][-1]


# --- vision.ocr_bild / beschreibe_bild ---------------------------------------

def test_ocr_bild_liefert_text():
    def fake(url, daten):
        assert "images" in daten["messages"][-1]     # Bild wurde wirklich mitgeschickt
        return _resp({"text": "Rechnung Quartalsende"})
    assert vision.ocr_bild(b"bilddaten", http_post=fake) == "Rechnung Quartalsende"


def test_ocr_bild_http_fehler_none():
    assert vision.ocr_bild(b"x", http_post=lambda u, d: _resp({}, status=500)) is None


def test_ocr_bild_leerer_text_none():
    assert vision.ocr_bild(b"x", http_post=lambda u, d: _resp({"text": "   "})) is None


def test_beschreibe_bild_liefert_text():
    def fake(url, daten):
        return _resp({"beschreibung": "Ein Balkendiagramm mit vier Säulen."})
    assert vision.beschreibe_bild(b"x", http_post=fake) == "Ein Balkendiagramm mit vier Säulen."


# --- vision.verfuegbar (Ollama /api/tags-Ping) -------------------------------

def _tags(namen, status=200):
    def fake_get(url):
        class _R:
            status_code = status

            def json(self):
                return {"models": [{"name": n} for n in namen]}
        return _R()
    return fake_get


def test_verfuegbar_modell_vorhanden():
    assert vision.verfuegbar(http_get=_tags(["qwen2.5vl:7b", "bge-m3"])) is True


def test_verfuegbar_modell_stamm_variante():
    assert vision.verfuegbar(http_get=_tags(["qwen2.5vl:latest"])) is True


def test_verfuegbar_modell_fehlt():
    assert vision.verfuegbar(http_get=_tags(["llama3", "bge-m3"])) is False


def test_verfuegbar_ollama_weg():
    def boom(url):
        raise ConnectionError("refused")
    assert vision.verfuegbar(http_get=boom) is False
