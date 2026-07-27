import json

import pytest

from appkit import modellprofil as mp
from appkit.runtime import (
    LocalRuntime,
    ModellInfo,
    OllamaRuntime,
    RuntimeEreignis,
    RuntimeHealth,
)

from app.ai import memory, providers


# --- Memory L1 --------------------------------------------------------------

def test_add_and_list_facts():
    assert memory.add_fact("dizzi", "Mag Cyan und Magenta", "explizit") is True
    fs = memory.facts("dizzi")
    assert len(fs) == 1
    assert fs[0]["fact"] == "Mag Cyan und Magenta"


def test_fact_dedup_case_insensitive():
    memory.add_fact("dizzi", "Trinkt gern Kaffee", "auto")
    assert memory.add_fact("dizzi", "trinkt gern kaffee", "auto") is False
    assert len(memory.facts("dizzi")) == 1


def test_fact_too_short_rejected():
    assert memory.add_fact("dizzi", "ab", "auto") is False


def test_delete_fact():
    memory.add_fact("dizzi", "Wird gleich gelöscht", "explizit")
    fid = memory.facts("dizzi")[0]["id"]
    assert memory.delete_fact("dizzi", fid) is True
    assert memory.facts("dizzi") == []
    assert memory.delete_fact("dizzi", fid) is False


def test_explicit_fact_detection():
    assert memory.explicit_fact_from("Merk dir: ich hasse Montage") == "ich hasse Montage"
    assert memory.explicit_fact_from("merke dir bitte was") == "bitte was"
    assert memory.explicit_fact_from("Wie ist das Wetter?") is None


def test_explicit_fact_stops_at_sentence_end():
    msg = "Merk dir: mein Lieblingsprojekt ist der Trading Bot. Stell dich vor."
    assert memory.explicit_fact_from(msg) == "mein Lieblingsprojekt ist der Trading Bot."


def test_facts_user_scoped():
    memory.add_fact("dizzi", "Fakt von dizzi", "explizit")
    memory.add_fact("gast", "Fakt von gast", "explizit")
    assert [f["fact"] for f in memory.facts("dizzi")] == ["Fakt von dizzi"]


# --- Verlauf + Prompt-Bau ----------------------------------------------------

def test_history_roundtrip():
    memory.save_message("dizzi", "user", "Hallo")
    memory.save_message("dizzi", "assistant", "Hi!", provider="lokal")
    h = memory.history("dizzi")
    assert [m["role"] for m in h] == ["user", "assistant"]
    assert h[1]["provider"] == "lokal"


def test_build_messages_injects_facts_and_history():
    memory.add_fact("dizzi", "Hat eine RTX 5070 Ti", "explizit")
    memory.save_message("dizzi", "user", "Erste Frage")
    msgs = memory.build_messages("dizzi", "Zweite Frage")
    assert msgs[0]["role"] == "system"
    assert "RTX 5070 Ti" in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "Zweite Frage"}
    assert any(m["content"] == "Erste Frage" for m in msgs)


# --- Provider-Kette ----------------------------------------------------------

def test_chain_sensitive_is_local_only():
    specs = providers.chain(sensitive=True)
    assert [s.kind for s in specs] == ["lokal"]


def test_chain_without_keys_is_local_only(monkeypatch):
    # Ohne DIZZI_*_KEY-Variablen ⇒ Boost-Provider fehlen (echte Keys aus der
    # .env des Entwickler-Rechners hier bewusst ausblenden)
    for var in ("DIZZI_NIM_KEY", "DIZZI_GROQ_KEY", "DIZZI_CEREBRAS_KEY"):
        monkeypatch.delenv(var, raising=False)
    specs = providers.chain(sensitive=False)
    assert specs[-1].kind == "lokal"
    assert all(s.kind == "lokal" for s in specs)


def test_chain_with_key(monkeypatch):
    for var in ("DIZZI_NIM_KEY", "DIZZI_CEREBRAS_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DIZZI_GROQ_KEY", "x")
    ids = [s.id for s in providers.chain(sensitive=False)]
    assert ids == ["groq", "lokal"]
    # sensibel bleibt trotz Key lokal
    assert [s.id for s in providers.chain(sensitive=True)] == ["lokal"]


def test_chain_boost_off_via_setting(monkeypatch):
    from app import db
    monkeypatch.setenv("DIZZI_NIM_KEY", "x")
    db.setting_put("dizzi", "ai_boost", False)
    assert [s.kind for s in providers.chain(sensitive=False)] == ["lokal"]


# --- Provider-Circuit-Breaker (P3.3b) ----------------------------------------

def test_circuit_breaker_oeffnet_und_schliesst(monkeypatch):
    providers._cb_state.clear()
    monkeypatch.setenv("DIZZI_GROQ_KEY", "x")
    for var in ("DIZZI_NIM_KEY", "DIZZI_CEREBRAS_KEY"):
        monkeypatch.delenv(var, raising=False)
    groq = next(p for p in providers.PROVIDERS if p.id == "groq")
    # Anfangs in der Kette
    assert "groq" in [s.id for s in providers.chain(sensitive=False)]
    # CB_SCHWELLE Fehler IN FOLGE ⇒ Breaker offen ⇒ aus der Kette, lokal bleibt
    for _ in range(providers.CB_SCHWELLE):
        providers.cb_fehler(groq)
    assert providers.circuit_offen(groq) is True
    ids = [s.id for s in providers.chain(sensitive=False)]
    assert "groq" not in ids and "lokal" in ids
    # ein Erfolg schließt sofort wieder
    providers.cb_erfolg(groq)
    assert providers.circuit_offen(groq) is False
    assert "groq" in [s.id for s in providers.chain(sensitive=False)]
    providers._cb_state.clear()


def test_circuit_breaker_lokal_nie_ausgesperrt():
    providers._cb_state.clear()
    lokal = next(p for p in providers.PROVIDERS if p.kind == "lokal")
    for _ in range(providers.CB_SCHWELLE * 3):
        providers.cb_fehler(lokal)              # no-op für lokal
    assert providers.circuit_offen(lokal) is False
    assert any(s.kind == "lokal" for s in providers.chain(sensitive=False))
    providers._cb_state.clear()


def test_circuit_breaker_cooldown_laeuft_ab(monkeypatch):
    providers._cb_state.clear()
    monkeypatch.setenv("DIZZI_GROQ_KEY", "x")
    groq = next(p for p in providers.PROVIDERS if p.id == "groq")
    for _ in range(providers.CB_SCHWELLE):
        providers.cb_fehler(groq)
    assert providers.circuit_offen(groq) is True
    providers._cb_state[groq.id]["bis"] = 0.0   # Cooldown abgelaufen simulieren
    assert providers.circuit_offen(groq) is False
    providers._cb_state.clear()


# --- Auto-Extraktion (Modell gemockt) -----------------------------------------

@pytest.mark.anyio
async def test_auto_extract_parses_json(monkeypatch):
    async def fake_quick(messages, model=None, *, format=None):
        return 'Hier: ["dizzi baut eine Kommandozentrale"] fertig.'
    monkeypatch.setattr(providers, "quick_chat", fake_quick)
    n = await memory.auto_extract("dizzi", "frage", "antwort")
    assert n == 1
    assert memory.facts("dizzi")[0]["source"] == "auto"


@pytest.mark.anyio
async def test_auto_extract_never_raises(monkeypatch):
    async def broken(messages, model=None, *, format=None):
        raise RuntimeError("Modell weg")
    monkeypatch.setattr(providers, "quick_chat", broken)
    assert await memory.auto_extract("dizzi", "a", "b") == 0


@pytest.mark.anyio
async def test_auto_extract_pydantic_single_source(monkeypatch):
    """P2.1: das Schema kommt aus EINEM Pydantic-Modell — quick_chat bekommt das
    constrained-decoding-``format`` UND die Antwort wird damit validiert. Liefert
    das Modell schema-ungültiges JSON, fällt die Extraktion ehrlich auf 0 zurück."""
    gesehen = {}

    async def fake_quick(messages, model=None, *, format=None):
        gesehen["format"] = format
        return '[123, "echte zahl ist kein fakt-string"]'   # erstes Element kein str
    monkeypatch.setattr(providers, "quick_chat", fake_quick)
    n = await memory.auto_extract("dizzi", "f", "a")
    # Schema = flaches String-Array (kein $ref) ⇒ grammatik-sicher live
    assert gesehen["format"]["type"] == "array"
    assert gesehen["format"]["items"] == {"type": "string"}
    assert n == 0   # 123 ist kein String ⇒ ValidationError ⇒ ehrlicher 0-Fallback


# --- Episoden (L2) ------------------------------------------------------------

@pytest.mark.anyio
async def test_episode_summarization(monkeypatch):
    async def fake_quick(messages, model=None):
        return "Nutzer und Dizzi besprachen das Dashboard."
    monkeypatch.setattr(providers, "quick_chat", fake_quick)
    for i in range(memory.EPISODE_AFTER_MSGS):
        memory.save_message("dizzi", "user" if i % 2 == 0 else "assistant", f"Msg {i}")
    assert await memory.maybe_summarize_episode("dizzi") is True
    eps = memory.episodes("dizzi")
    assert len(eps) == 1 and eps[0]["kind"] == "episode"
    # jüngste Nachrichten bleiben wörtlich erhalten
    assert len(memory.history("dizzi")) == memory.EPISODE_KEEP_RECENT
    # Episode fließt in den System-Prompt
    msgs = memory.build_messages("dizzi", "Weiter")
    assert "Dashboard" in msgs[0]["content"]


@pytest.mark.anyio
async def test_episode_not_triggered_below_threshold(monkeypatch):
    async def fake_quick(messages, model=None):
        raise AssertionError("darf nicht aufgerufen werden")
    monkeypatch.setattr(providers, "quick_chat", fake_quick)
    memory.save_message("dizzi", "user", "nur eine Nachricht")
    assert await memory.maybe_summarize_episode("dizzi") is False


@pytest.mark.anyio
async def test_episode_kept_on_model_failure(monkeypatch):
    async def broken(messages, model=None):
        raise RuntimeError("Modell weg")
    monkeypatch.setattr(providers, "quick_chat", broken)
    for i in range(memory.EPISODE_AFTER_MSGS):
        memory.save_message("dizzi", "user", f"Msg {i}")
    assert await memory.maybe_summarize_episode("dizzi") is False
    # NICHTS gelöscht, wenn keine Episode entstand
    assert len(memory.history("dizzi", limit=99)) == memory.EPISODE_AFTER_MSGS


@pytest.mark.anyio
async def test_consolidation_merges_old_episodes(monkeypatch):
    async def fake_quick(messages, model=None):
        return "Essenz aller alten Gespräche."
    monkeypatch.setattr(providers, "quick_chat", fake_quick)
    for i in range(14):
        memory._add_episode("dizzi", f"Episode {i}", "episode", f"2026-06-0{i % 9 + 1}", f"2026-06-0{i % 9 + 1}")
    res = await memory.consolidate("dizzi")
    assert res["episodes_merged"] == 8
    kinds = [e["kind"] for e in memory.episodes("dizzi", limit=99)]
    assert kinds.count("essenz") == 1
    assert kinds.count("episode") == 6
    from app import db
    assert db.setting_get("dizzi", "last_consolidation") is not None


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --- M5 (docs/62 C1d): providers-Nähte auf die LocalRuntime -------------------
# Paritäts-Fakes: stream_chat-Lokal-Bein · quick_chat (ohne Schema) · status.
# Signaturen unverändert (die Bestands-Monkeypatches oben bleiben intakt);
# hier wird die neue Naht ``providers.runtime`` durch eine Fake-Runtime ersetzt.

class _FakeRuntime(LocalRuntime):
    """Minimal-Runtime für die M5-Nähte: liefert konservierte Text-Chunks
    (optional Abbruch nach ``fail_after`` Chunks) + Selbstauskunft."""

    def __init__(self, *, text_chunks=(), health_ok=True, modelle_namen=(),
                 fail_after=None):
        self._chunks = list(text_chunks)
        self._health_ok = health_ok
        self._modelle = list(modelle_namen)
        self._fail_after = fail_after
        self.calls: list[dict] = []

    def strukturiert(self, *a, **k):
        return None

    def embed(self, *a, **k):
        return None

    def modelle(self):
        return [ModellInfo(name=n) for n in self._modelle]

    def health(self):
        return RuntimeHealth(ok=self._health_ok, laufzeit="fake")

    async def chat_stream(self, messages, *, modell, tools=None, optionen=None,
                          timeout=300.0):
        self.calls.append({"messages": messages, "modell": modell, "timeout": timeout})
        for i, c in enumerate(self._chunks):
            if self._fail_after is not None and i == self._fail_after:
                raise RuntimeError("transport weg")
            yield RuntimeEreignis("text", text=c)
        yield RuntimeEreignis("ende")


@pytest.mark.anyio
async def test_stream_chat_local_routes_through_runtime(monkeypatch):
    """Lokal-Bein läuft über runtime().chat_stream — gleiche (id, chunk)-Folge,
    Modell = local_model(), Timeout 180 s (Paritäts-Pins)."""
    fake = _FakeRuntime(text_chunks=["Hal", "lo"])
    monkeypatch.setattr(providers, "runtime", lambda: fake)
    out = [t async for t in providers.stream_chat(
        [{"role": "user", "content": "hi"}], sensitive=True)]
    assert out == [("lokal", "Hal"), ("lokal", "lo")]
    assert fake.calls[0]["modell"] == providers.local_model()
    assert fake.calls[0]["timeout"] == 180.0


@pytest.mark.anyio
async def test_stream_chat_local_emitted_then_raises(monkeypatch):
    """emitted-Regel: floss schon ein Token, wird ein Transportfehler NICHT
    stillschweigend verschluckt — stream_chat wirft (kein halber Provider-Wechsel)."""
    fake = _FakeRuntime(text_chunks=["A", "B"], fail_after=1)
    monkeypatch.setattr(providers, "runtime", lambda: fake)
    seen: list = []
    with pytest.raises(RuntimeError):
        async for t in providers.stream_chat(
                [{"role": "user", "content": "x"}], sensitive=True):
            seen.append(t)
    assert seen == [("lokal", "A")]      # ein Token floss, DANN Abbruch


@pytest.mark.anyio
async def test_stream_chat_local_fail_before_token_exhausts_chain(monkeypatch):
    """Fehler VOR dem ersten Token ⇒ kein Wurf mitten im Stream; die (hier nur
    lokale) Kette läuft leer und endet im ehrlichen 'Kein Provider erreichbar'."""
    fake = _FakeRuntime(text_chunks=["A"], fail_after=0)
    monkeypatch.setattr(providers, "runtime", lambda: fake)
    with pytest.raises(RuntimeError, match="Kein Provider"):
        async for _ in providers.stream_chat(
                [{"role": "user", "content": "x"}], sensitive=True):
            pass


@pytest.mark.anyio
async def test_quick_chat_no_format_via_runtime(monkeypatch):
    """quick_chat ohne Schema = a_chat (chat_stream eingesammelt); Modell-Default
    FAST_LOCAL_MODEL, Rückgabe = zusammengefügter Text."""
    fake = _FakeRuntime(text_chunks=["Zusammen", "fassung"])
    monkeypatch.setattr(providers, "runtime", lambda: fake)
    out = await providers.quick_chat([{"role": "user", "content": "fasse zusammen"}])
    assert out == "Zusammenfassung"
    assert fake.calls[0]["modell"] == providers.FAST_LOCAL_MODEL


@pytest.mark.anyio
async def test_quick_chat_no_format_raises_on_transport(monkeypatch):
    """strikt=True: quick_chat WIRFT bei Transportfehler wie zuvor (die Aufrufer
    fangen breit ab — memory-Verdichtung etc.)."""
    fake = _FakeRuntime(text_chunks=["x"], fail_after=0)
    monkeypatch.setattr(providers, "runtime", lambda: fake)
    with pytest.raises(RuntimeError):
        await providers.quick_chat([{"role": "user", "content": "x"}])


@pytest.mark.anyio
async def test_status_maps_runtime_health_and_modelle(monkeypatch):
    fake = _FakeRuntime(health_ok=True, modelle_namen=["qwen3:14b", "bge-m3"])
    monkeypatch.setattr(providers, "runtime", lambda: fake)
    s = await providers.status()
    assert s["ollama_ok"] is True
    assert s["models"] == ["qwen3:14b", "bge-m3"]
    assert s["active_model"] == providers.local_model()
    assert [p["id"] for p in s["providers"]] == ["nim", "groq", "cerebras", "lokal"]


@pytest.mark.anyio
async def test_status_ollama_down(monkeypatch):
    fake = _FakeRuntime(health_ok=False, modelle_namen=[])
    monkeypatch.setattr(providers, "runtime", lambda: fake)
    s = await providers.status()
    assert s["ollama_ok"] is False
    assert s["models"] == []


# --- M7 (docs/62 C2): runtime() Setting-getrieben über die appkit-Registry ----
# Default/unbekannt/leer ⇒ Ollama (fail-safe); der ENV-Split (core-URL) bleibt.

def test_runtime_default_ist_core_url_ollama():
    """Ohne Setting ⇒ Ollama-Adapter mit core-URL (ENV-Split docs/62 §0: core baut
    seine Instanz mit ``OLLAMA_URL`` = DIZZI_OLLAMA_URL, nicht dem appkit-Default).
    Und: eine gecachte Instanz (Registry) — dieselbe Singleton-Semantik wie zuvor."""
    rt = providers.runtime()
    assert isinstance(rt, OllamaRuntime)
    assert rt.url == providers.OLLAMA_URL
    assert providers.runtime() is rt          # gecacht wie der alte _runtime_cache


def test_runtime_setting_ollama_explizit():
    from app import db
    db.setting_put(providers.DEFAULT_USER_ID, "runtime", "ollama")
    assert isinstance(providers.runtime(), OllamaRuntime)


def test_runtime_setting_unbekannt_failsafe_ollama():
    """Kaputtes/unbekanntes Setting ⇒ Boden (Ollama) — nie ein Crash oder ein
    Verhaltenswechsel (runtime_holen fällt auf DEFAULT_RUNTIME zurück)."""
    from app import db
    db.setting_put(providers.DEFAULT_USER_ID, "runtime", "vllm-gibts-noch-nicht")
    rt = providers.runtime()
    assert isinstance(rt, OllamaRuntime)
    assert rt.url == providers.OLLAMA_URL


def test_runtime_setting_leer_failsafe():
    from app import db
    db.setting_put(providers.DEFAULT_USER_ID, "runtime", "")
    assert isinstance(providers.runtime(), OllamaRuntime)


# --- M8 (docs/62 C3): modellprofil verdrahtet — App-seitige Paritäts-Pins -----
# Der Cross-Check von der App-Import-Seite (appkit kann Apps nicht importieren):
# Stufe-0-Slots == die Live-Konstanten. + Präzedenz Setting > Profil > Konstante.

def test_profil_paritaet_mit_konstanten():
    from appkit.modellprofil import STUFE_0

    from app.ai import rag
    assert STUFE_0.modell_fuer("chat") == providers.DEFAULT_LOCAL_MODEL     # qwen3:14b
    assert STUFE_0.modell_fuer("schnell") == providers.FAST_LOCAL_MODEL     # qwen3:4b
    assert STUFE_0.modell_fuer("embed") == rag.EMBED_MODEL                  # bge-m3
    assert STUFE_0.slot("embed").faehigkeiten.dim == rag.EMBED_DIM          # 1024


def test_local_model_default_ist_profil_slot():
    """Ohne ai_model-Setting ⇒ Profil-Slot 'chat' (== Konstante, 0 Drift)."""
    from appkit.modellprofil import STUFE_0
    assert providers.local_model() == STUFE_0.modell_fuer("chat")
    assert providers.local_model() == providers.DEFAULT_LOCAL_MODEL


def test_local_model_setting_gewinnt():
    """Präzedenz: ein gesetztes ai_model schlägt Profil-Slot + Konstante."""
    from app import db
    db.setting_put(providers.DEFAULT_USER_ID, "ai_model", "custom:70b")
    assert providers.local_model() == "custom:70b"


def test_fast_model_ist_profil_schnell():
    from appkit.modellprofil import STUFE_0
    assert providers.fast_model() == STUFE_0.modell_fuer("schnell")
    assert providers.fast_model() == providers.FAST_LOCAL_MODEL


# --- M9 (docs/62 C4): Kanal-Auflösung in status() + Re-Index-Gate-Hinweis ------
# Hermetisch: die nvidia-smi-Probe wird gestubbt (fixture-Stufen), der providers-
# VRAM-Cache davor+danach geleert. Der Probe-Fail-safe selbst ist appkit-getestet.

@pytest.fixture
def stub_vram(monkeypatch):
    """Deterministische VRAM-Probe + geleerter providers-Cache (kein echtes
    nvidia-smi im Unit-Test)."""
    def _use(bytes_or_none):
        monkeypatch.setattr(mp, "vram_probe", lambda: bytes_or_none)
        providers._vram_reset()
    yield _use
    providers._vram_reset()


@pytest.mark.anyio
async def test_status_kanal_und_runtime_felder(monkeypatch, stub_vram):
    """status() trägt additiv ``runtime`` + ``kanal``; die M5-Bestandsfelder
    bleiben unangetastet (0 Verhaltenswechsel)."""
    stub_vram(None)                       # Probe „unbekannt" ⇒ Boden Stufe 0
    fake = _FakeRuntime(health_ok=True, modelle_namen=["qwen3:14b"])
    monkeypatch.setattr(providers, "runtime", lambda: fake)
    s = await providers.status()
    assert s["runtime"] == "ollama"
    assert s["kanal"]["stufe"] == 0
    assert s["kanal"]["name"] == "stufe-0"
    assert s["kanal"]["vram_bytes"] is None
    assert s["kanal"]["reindex_noetig"] is False
    assert s["kanal"]["reindex_hinweis"] == ""
    # Bestandsfelder unverändert:
    assert s["ollama_ok"] is True
    assert s["models"] == ["qwen3:14b"]
    assert s["active_model"] == providers.local_model()
    assert [p["id"] for p in s["providers"]] == ["nim", "groq", "cerebras", "lokal"]


@pytest.mark.anyio
async def test_status_kanal_mit_vram_bleibt_stufe0(monkeypatch, stub_vram):
    """Auch mit reichlich VRAM heute Stufe 0 (STUFEN hat nur den Boden) — der
    Kanal ist vorverdrahtet, wächst aber nur per Release, nicht per Hardware."""
    stub_vram(64 * 2**30)
    monkeypatch.setattr(providers, "runtime", lambda: _FakeRuntime(health_ok=True))
    s = await providers.status()
    assert s["kanal"]["stufe"] == 0
    assert s["kanal"]["vram_bytes"] == 64 * 2**30
    assert s["kanal"]["reindex_noetig"] is False


def test_kanal_pin_garbage_failsafe(stub_vram):
    """Ein kaputter modell_profil_stufe-Pin ⇒ auto-Auflösung (Boden), kein Crash."""
    from app import db
    stub_vram(None)
    db.setting_put(providers.DEFAULT_USER_ID, "modell_profil_stufe", "voelliger-quatsch")
    k = providers.kanal()
    assert k["stufe"] == 0 and k["reindex_noetig"] is False


def test_kanal_reindex_hinweis_bei_embed_wechsel(monkeypatch, stub_vram):
    """Re-Index-GATE-Hinweis: löst der Kanal eine Zielstufe mit ANDEREM embed-Slot
    auf, meldet kanal() ``reindex_noetig`` + Hinweis — aber NUR als Hinweis (kein
    Auto-Lauf; das gegatete Verwerfen bleibt bei rag._migriere_modellwechsel)."""
    stub_vram(None)
    ziel = mp.ModellProfil(
        stufe=1, name="stufe-1", freigegeben=True, vram_min_bytes=0,
        zuordnung={"embed": mp.ModellSlot("qwen3-embedding",
                                          mp.ModellFaehigkeiten(dim=1024))})
    monkeypatch.setattr(mp, "aufloese_stufe", lambda *a, **k: ziel)
    k = providers.kanal()
    assert k["stufe"] == 1
    assert k["reindex_noetig"] is True
    assert "Re-Index" in k["reindex_hinweis"]
