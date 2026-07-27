"""Vertrags-Tests für appkit/runtime.py (FP-3-Stub — docs/62 §1).

Pinnt den VERTRAG (Fehler-Verträge, Default-Zwillinge, Registry-fail-safe),
nicht einen Adapter: ``FakeRuntime`` steht für jeden künftigen Adapter (C1
OllamaRuntime muss exakt diese Semantik erfüllen). Komplett Ollama-frei;
async über ``asyncio.run`` (keine pytest-asyncio-Annahme)."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from appkit import runtime as rt


class Antwort(BaseModel):
    wert: int


class FakeRuntime(rt.LocalRuntime):
    """Minimaler Vertrags-Erfüller: liefert Konserven, zeichnet Aufrufe auf."""
    name = "fake"

    def __init__(self, events=None, stream_fehler: Exception | None = None):
        self.events = list(events or [])
        self.stream_fehler = stream_fehler
        self.aufrufe: list[tuple] = []

    def strukturiert(self, system, nutzer, *, schema, modell, temperature=0.0,
                     timeout=rt.TIMEOUT_STRUKTURIERT_S, strikt=False):
        self.aufrufe.append(("strukturiert", modell))
        return schema(wert=7)

    def chat_stream(self, messages, *, modell, tools=None, optionen=None,
                    timeout=rt.TIMEOUT_STREAM_S):
        async def _gen():
            if self.stream_fehler is not None:
                raise self.stream_fehler
            for ev in self.events:
                yield ev
        return _gen()

    def embed(self, texts, *, modell, timeout=rt.TIMEOUT_EMBED_S):
        return [] if not texts else [[0.1, 0.2] for _ in texts]

    def modelle(self):
        return [rt.ModellInfo("fake-1b", groesse_bytes=1)]

    def health(self):
        return rt.RuntimeHealth(ok=True, laufzeit=self.name)


@pytest.fixture()
def registry_sauber():
    """Registry-Globalzustand je Test isolieren (kein Leck zwischen Tests)."""
    fab, inst = dict(rt._FABRIKEN), dict(rt._INSTANZEN)
    rt._FABRIKEN.clear(), rt._INSTANZEN.clear()
    yield
    rt._FABRIKEN.clear(), rt._INSTANZEN.clear()
    rt._FABRIKEN.update(fab), rt._INSTANZEN.update(inst)


def test_abc_nicht_instanzierbar():
    with pytest.raises(TypeError):
        rt.LocalRuntime()  # 5 Pflicht-Methoden = abstrakt


def test_async_zwillinge_delegieren_an_sync():
    f = FakeRuntime()
    erg = asyncio.run(f.a_strukturiert("s", "n", schema=Antwort, modell="m"))
    assert erg == Antwort(wert=7) and ("strukturiert", "m") in f.aufrufe
    assert asyncio.run(f.a_embed(["x"], modell="m")) == [[0.1, 0.2]]
    assert asyncio.run(f.a_modelle())[0].name == "fake-1b"
    assert asyncio.run(f.a_health()).ok is True


def test_a_chat_sammelt_nur_text_ereignisse():
    f = FakeRuntime(events=[
        rt.RuntimeEreignis("text", text="Hal"),
        rt.RuntimeEreignis("tool_aufrufe", tool_aufrufe=(rt.ToolAufruf("t"),)),
        rt.RuntimeEreignis("text", text="lo"),
        rt.RuntimeEreignis("ende", nutzung={"eval_count": 2}),
    ])
    assert asyncio.run(f.a_chat([{"role": "user", "content": "?"}], modell="m")) == "Hallo"


def test_a_chat_fehler_vertrag_none_und_strikt():
    f = FakeRuntime(stream_fehler=ConnectionError("engine weg"))
    assert asyncio.run(f.a_chat([], modell="m")) is None          # fail-safe
    with pytest.raises(ConnectionError):                           # Opt-in: Parität
        asyncio.run(f.a_chat([], modell="m", strikt=True))         # zu quick_chat


def test_toolaufruf_ollama_rueckform_und_defaults():
    ta = rt.ToolAufruf("suche", {"q": "x"})
    assert ta.als_ollama() == {"function": {"name": "suche", "arguments": {"q": "x"}}}
    ev = rt.RuntimeEreignis("ende")
    assert ev.text == "" and ev.tool_aufrufe == () and ev.nutzung is None
    with pytest.raises(Exception):                                 # frozen
        ev.art = "text"  # type: ignore[misc]


def test_registry_failsafe_und_cache(registry_sauber):
    with pytest.raises(LookupError):                               # Stub-Phase ehrlich
        rt.runtime_holen()
    rt.registriere_runtime("ollama", FakeRuntime)
    a = rt.runtime_holen(None)
    assert rt.runtime_holen("") is a                               # leer ⇒ Default
    assert rt.runtime_holen("gibts-nicht") is a                    # unbekannt ⇒ Default
    assert rt.runtime_holen("ollama") is a                         # eine Instanz je Name
    rt.registriere_runtime("ollama", FakeRuntime)                  # Re-Registrierung …
    assert rt.runtime_holen() is not a                             # … verwirft Cache
