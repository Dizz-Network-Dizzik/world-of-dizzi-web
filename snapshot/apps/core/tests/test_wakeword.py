"""Tests Weckwort-Schicht (openWakeWord). Echtes Mikrofon gibt es im Test nicht
⇒ die HARDWARE-freie Logik (Trigger/Schwelle/Cooldown/WAV/Modell-Auflösung)
wird mit einem gefälschten Modell deterministisch geprüft; das echte
Mikro-Lauschen verifiziert der Nutzer live."""

from __future__ import annotations

import wave
import io

import numpy as np

from app.ai import wakeword


class FakeModel:
    """Liefert vorgegebene Scores je predict-Aufruf (FIFO)."""

    def __init__(self, scores):
        self._scores = list(scores)
        self.reset_aufrufe = 0

    def predict(self, chunk):
        s = self._scores.pop(0) if self._scores else 0.0
        return {"hey_jarvis": s}

    def reset(self):
        self.reset_aufrufe += 1


def _listener(scores, **kw):
    L = wakeword.WakeListener(wort="hey_jarvis", **kw)
    L._model = FakeModel(scores)          # Modell injizieren (kein Download)
    return L


def test_trigger_ab_schwelle():
    L = _listener([0.1, 0.6, 0.2], schwelle=0.5)
    chunk = np.zeros(1280, dtype=np.int16)
    assert L.feed(chunk) is None           # 0.1 < 0.5
    assert L.feed(chunk) == "hey_jarvis"   # 0.6 >= 0.5
    assert L.letzter_score == 0.6


def test_cooldown_unterdrueckt_mehrfach():
    t = {"v": 0.0}
    L = _listener([0.9, 0.9, 0.9], schwelle=0.5, cooldown_s=2.0,
                  clock=lambda: t["v"])
    c = np.zeros(1280, dtype=np.int16)
    assert L.feed(c) == "hey_jarvis"       # erster Treffer bei t=0
    t["v"] = 1.0
    assert L.feed(c) is None               # innerhalb Cooldown (1s < 2s)
    t["v"] = 2.5
    assert L.feed(c) == "hey_jarvis"       # Cooldown vorbei


def test_pcm_to_wav_ist_16k_mono():
    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()   # 1 s Stille
    wav = wakeword.pcm_to_wav(pcm)
    with wave.open(io.BytesIO(wav), "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getnframes() == 16000


def test_verfuegbare_woerter_enthaelt_eingebaute(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    woerter = wakeword.verfuegbare_woerter()
    assert "hey_jarvis" in woerter and "alexa" in woerter
    # Eigenes Modell ablegen ⇒ taucht auf (Datei-Stem)
    d = wakeword.custom_model_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "hey_dizzi.onnx").write_bytes(b"x")
    assert "hey_dizzi" in wakeword.verfuegbare_woerter()


def test_modellpfad_bevorzugt_eigene_datei(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # Ohne Datei: eingebauter Name
    assert wakeword._modell_pfad("hey_jarvis") == "hey_jarvis"
    d = wakeword.custom_model_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "hey_dizzi.onnx").write_bytes(b"x")
    assert wakeword._modell_pfad("hey_dizzi").endswith("hey_dizzi.onnx")


def test_daemon_status_ohne_start():
    d = wakeword.WakeDaemon()
    s = d.status()
    assert s["laeuft"] is False and s["treffer_gesamt"] == 0


def test_geraet_aufloesen_per_name(monkeypatch):
    """Namens-Hinweis übersteht Index-Wandern: das USB-Mikro liegt auf Index 1,
    wird aber über seinen Namen gefunden (tote Indizes werden übersprungen)."""
    geraete = [{"index": 0, "name": "Microsoft Soundmapper - Input"},
               {"index": 1, "name": "Mikrofon (USB dongle)"},
               {"index": 2, "name": "Mikrofon (USB dongle)"}]  # tot
    monkeypatch.setattr(wakeword, "eingabe_geraete", lambda neu_laden=False: geraete)
    # nur Index 1 ist „öffenbar"
    monkeypatch.setattr(wakeword, "_oeffenbar", lambda i: i == 1)
    assert wakeword.geraet_aufloesen("USB dongle") == 1   # über den Namen
    assert wakeword.geraet_aufloesen("usb DONGLE") == 1   # case-insensitiv
    assert wakeword.geraet_aufloesen(1) == 1              # int direkt (öffenbar)
    assert wakeword.geraet_aufloesen(2) == 1              # int tot ⇒ Name ⇒ 1
    assert wakeword.geraet_aufloesen(None) is None        # Default
    assert wakeword.geraet_aufloesen("Realtek") is None   # nichts Passendes
