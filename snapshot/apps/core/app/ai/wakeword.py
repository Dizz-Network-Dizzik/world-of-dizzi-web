"""Weckwort-Lauschen („immer hören") — openWakeWord, komplett lokal, 0 €.

Architektur (Nutzer-Entscheid 12.06.): ein **lokaler Lausch-Daemon** greift
direkt aufs Mikrofon zu (kein offener Browser-Tab nötig), lässt openWakeWord
über 80-ms-Audioblöcke laufen und löst bei einem Treffer ein kurzes
Sprachfenster aus, das durch die bestehende STT-Pipeline (``voice.transcribe``)
an Dizzi geht.

Ehrliche Grenze (Recherche 12.06., docs/03): openWakeWord-**Training** ist
Linux/CUDA-gebunden ⇒ das eigene Wort ``hey_dizzi`` wird per Colab trainiert
und als ``.onnx`` hier abgelegt; die **Inferenz** läuft lokal auf Windows
(onnxruntime). Bis das Dizzi-Modell vorliegt dient ein vortrainiertes Wort
(``hey_jarvis``) zur Verifikation — die Architektur ist identisch, nur die
Modell-Datei wechselt.

Fail-safe: ohne Mikrofon / ohne ``sounddevice`` ruht alles (kein Absturz);
Mikrofon-Zugriff ist **opt-in** über das Setting ``voice_wake_aktiv``.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..config import settings

SAMPLE_RATE = 16000          # openWakeWord-Pflicht
CHUNK = 1280                 # 80 ms @ 16 kHz
FOLGE_SEK = 4.0              # Länge des Sprachfensters nach dem Weckwort
EINGEBAUT = ("hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy")
DEFAULT_WORT = "hey_dizzi"   # eigenes Modell trainiert+live verifiziert (12.06., docs/21)


def pcm_to_wav(pcm_int16: bytes) -> bytes:
    """16-kHz-mono-int16-PCM ⇒ WAV-Bytes (für die STT-Pipeline)."""
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm_int16)
    return buf.getvalue()


def custom_model_dir() -> Path:
    """Ablage für selbst trainierte Modelle (z. B. hey_dizzi.onnx)."""
    d = settings.data_dir / "models" / "wakeword"
    return d


def verfuegbare_woerter() -> list[str]:
    """Eingebaute + selbst abgelegte (.onnx) Weckwörter."""
    eigene = []
    d = custom_model_dir()
    if d.is_dir():
        eigene = [p.stem for p in d.glob("*.onnx")]
    return list(EINGEBAUT) + sorted(set(eigene) - set(EINGEBAUT))


def _modell_pfad(wort: str) -> str:
    """Eigenes Modell (Datei) bevorzugt, sonst der eingebaute Name."""
    datei = custom_model_dir() / f"{wort}.onnx"
    return str(datei) if datei.is_file() else wort


class WakeListener:
    """Kapselt das openWakeWord-Modell + Trigger-Logik. Die Audio-Verarbeitung
    (``feed``) ist von der Mikrofon-Schleife getrennt ⇒ deterministisch testbar
    (man speist Audioblöcke ein, ohne echte Hardware)."""

    def __init__(self, wort: str = DEFAULT_WORT, schwelle: float = 0.5,
                 cooldown_s: float = 2.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.wort = wort
        self.schwelle = schwelle
        self.cooldown_s = cooldown_s
        self.clock = clock
        self._model: Any = None
        self._letzter_trigger = -1e9   # „lange her" ⇒ erster Treffer geht durch
        self.letzter_score = 0.0

    def _ensure_model(self) -> Any:
        if self._model is None:
            from openwakeword.model import Model
            self._model = Model(wakeword_models=[_modell_pfad(self.wort)],
                                inference_framework="onnx")
        return self._model

    def feed(self, chunk_int16) -> str | None:
        """Ein 80-ms-Block (1280 int16-Samples) ⇒ Weckwort-Name bei Treffer
        (außerhalb des Cooldowns), sonst None."""
        model = self._ensure_model()
        scores = model.predict(chunk_int16)
        # Modell-Schlüssel kann der Dateiname ODER der eingebaute Name sein.
        # float() ist Pflicht: openWakeWord liefert numpy.float32 (nicht
        # JSON-/pydantic-serialisierbar — Live-Vorfall 12.06.).
        self.letzter_score = float(max(scores.values())) if scores else 0.0
        if self.letzter_score < self.schwelle:
            return None
        now = self.clock()
        if now - self._letzter_trigger < self.cooldown_s:
            return None
        self._letzter_trigger = now
        return self.wort

    def reset(self) -> None:
        """Internen Audio-Zustand des Modells leeren (z. B. nach Pause)."""
        if self._model is not None:
            self._model.reset()


# --------------------------------------------------------------- Daemon
class WakeDaemon:
    """Mikrofon-Schleife in einem Daemon-Thread. Start/Stopp zur Laufzeit
    (ohne Core-Neustart). Hält sich aus dem Core heraus, solange das Setting
    ``voice_wake_aktiv`` falsch ist."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._listener: WakeListener | None = None
        # Callback bekommt (Weckwort, WAV-Bytes des Folge-Sprachfensters).
        self.on_wake: Callable[[str, bytes], None] | None = None
        self.fehler: str | None = None
        self.laeuft = False
        self.treffer_gesamt = 0

    def start(self, wort: str, schwelle: float, geraet: int | None) -> dict[str, Any]:
        if self.laeuft:
            return {"ok": True, "schon_aktiv": True}
        self.fehler = None
        self._stop.clear()
        self._listener = WakeListener(wort=wort, schwelle=schwelle)
        self._thread = threading.Thread(
            target=self._loop, args=(geraet,), daemon=True, name="wake-daemon")
        self._thread.start()
        return {"ok": True}

    def stop(self) -> None:
        self._stop.set()
        self.laeuft = False

    def _loop(self, geraet: int | None) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except Exception as e:                     # Bibliothek fehlt ⇒ ruht
            self.fehler = f"Audio-Bibliothek nicht verfügbar: {e}"
            return
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=CHUNK, device=geraet) as stream:
                self.laeuft = True
                while not self._stop.is_set():
                    data, _ = stream.read(CHUNK)
                    chunk = np.asarray(data, dtype="int16").reshape(-1)
                    treffer = self._listener.feed(chunk) if self._listener else None
                    if not treffer:
                        continue
                    self.treffer_gesamt += 1
                    # Sprachfenster aus DEMSELBEN Stream sammeln (kein zweiter
                    # Mikro-Zugriff); danach Wake-Detection wieder scharf.
                    folge = [chunk.tobytes()]
                    bloecke = int(FOLGE_SEK * SAMPLE_RATE / CHUNK)
                    for _ in range(bloecke):
                        if self._stop.is_set():
                            break
                        d2, _ = stream.read(CHUNK)
                        folge.append(np.asarray(d2, dtype="int16").tobytes())
                    if self._listener:
                        self._listener.reset()      # Trigger-Audio nicht nachklingen
                    if self.on_wake:
                        try:
                            self.on_wake(treffer, pcm_to_wav(b"".join(folge)))
                        except Exception:
                            pass                    # Callback-Fehler nie fatal
        except Exception as e:                      # Mikro belegt/weg ⇒ ehrlich
            self.fehler = f"Mikrofon-Fehler: {e}"
        finally:
            self.laeuft = False

    def status(self) -> dict[str, Any]:
        return {
            "laeuft": self.laeuft,
            "fehler": self.fehler,
            "wort": self._listener.wort if self._listener else None,
            "schwelle": self._listener.schwelle if self._listener else None,
            "letzter_score": round(self._listener.letzter_score, 3)
                             if self._listener else 0.0,
            "treffer_gesamt": self.treffer_gesamt,
        }


# Prozess-weiter Daemon (ein Mikrofon, ein Lauscher).
daemon = WakeDaemon()


_geraete_cache: list[dict[str, Any]] | None = None


def _oeffenbar(index: int) -> bool:
    """Lässt sich ein Aufnahme-Stream auf diesem Index öffnen? (filtert tote/
    ungültige Geräte wie verwaiste USB-Indizes raus — Live-Lehre 12.06.)."""
    try:
        import sounddevice as sd
        s = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                           blocksize=CHUNK, device=index)
        s.close()
        return True
    except Exception:
        return False


def geraet_aufloesen(geraet: "int | str | None") -> int | None:
    """Geräte-Angabe → funktionierender Eingang-Index (oder None = Default).

    Robust gegen **Index-Wandern** (Live-Vorfall 12.06.: das USB-Mikro lag mal
    auf Index 0, dann auf 1): ein **Name** (z. B. ``"USB dongle"``) ist stabil,
    eine Nummer nicht. Darum:
    - ``str``  → erster ÖFFENBARE Eingang, dessen Name den Hinweis enthält.
    - ``int``  → dieser Index, wenn öffenbar; sonst Suche über seinen Namen.
    - ``None`` → None (PortAudio-Default).
    Findet sich nichts Öffenbares, ``None`` (Daemon nimmt dann den Default)."""
    if geraet is None or geraet == "":
        return None
    geraete = eingabe_geraete()
    # numerisch (int oder Ziffern-String)
    if isinstance(geraet, int) or (isinstance(geraet, str) and geraet.lstrip("-").isdigit()):
        idx = int(geraet)
        if _oeffenbar(idx):
            return idx
        treffer = next((g for g in geraete if g["index"] == idx), None)
        geraet = treffer["name"] if treffer else None  # über den Namen weitersuchen
        if geraet is None:
            return None
    # Namens-Hinweis (case-insensitiv, erster öffenbarer Treffer)
    hinweis = str(geraet).lower()
    for g in geraete:
        if hinweis in g["name"].lower() and _oeffenbar(g["index"]):
            return g["index"]
    return None


def eingabe_geraete(neu_laden: bool = False) -> list[dict[str, Any]]:
    """Verfügbare Mikrofone (Index + Name). GECACHT: ``query_devices`` darf
    nicht live laufen, während der Daemon im selben Prozess einen Stream offen
    hält (PortAudio-Reentrancy ⇒ Fehler). Die Liste ändert sich praktisch nie."""
    global _geraete_cache
    if _geraete_cache is not None and not neu_laden:
        return _geraete_cache
    out: list[dict[str, Any]] = []
    try:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                out.append({"index": i, "name": d["name"],
                            "samplerate": int(d.get("default_samplerate", 0))})
    except Exception:
        out = _geraete_cache or []   # bei Fehler den letzten Stand behalten
    _geraete_cache = out
    return out
