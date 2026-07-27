"""Sprachschicht (Phase 4 Teil B) — komplett lokal, 0 €.

- STT: faster-whisper (Modell ``small``, Deutsch stark; CPU int8 reicht für
  kurze Sprachbefehle; Modell-Cache unter C:\\Dizzik\\data\\models\\whisper)
- TTS: Piper mit deutscher Stimme (Thorsten medium, ONNX)

Beide Modelle werden lazy geladen und dann im Prozess gehalten.
openWakeWord („immer lauschen") ist LIVE (``wakeword.py::WakeDaemon``, Start/Stopp
zur Laufzeit; Mikrofon opt-in über das Setting ``voice_wake_aktiv``).
"""

from __future__ import annotations

import asyncio
import io
import threading
import wave
from pathlib import Path
from typing import Any

from ..config import settings

STT_MODEL = "small"          # ~460 MB, gutes Deutsch; per Setting später wechselbar
VOICE_ONNX = "de_DE-thorsten-medium.onnx"

_lock = threading.Lock()
_whisper: Any = None
_piper: Any = None


def _voice_dir() -> Path:
    return settings.data_dir / "models" / "voice"


def _whisper_model() -> Any:
    global _whisper
    if _whisper is None:
        with _lock:
            if _whisper is None:
                from faster_whisper import WhisperModel
                cache = settings.data_dir / "models" / "whisper"
                cache.mkdir(parents=True, exist_ok=True)
                _whisper = WhisperModel(STT_MODEL, device="cpu",
                                        compute_type="int8", download_root=str(cache))
    return _whisper


def _piper_voice() -> Any:
    global _piper
    if _piper is None:
        with _lock:
            if _piper is None:
                from piper import PiperVoice
                _piper = PiperVoice.load(str(_voice_dir() / VOICE_ONNX))
    return _piper


def _transcribe_sync(audio: bytes) -> str:
    segments, _info = _whisper_model().transcribe(
        io.BytesIO(audio), language="de", beam_size=2, vad_filter=True,
    )
    return " ".join(s.text.strip() for s in segments).strip()


def _synthesize_sync(text: str) -> bytes:
    buf = io.BytesIO()
    voice = _piper_voice()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    return buf.getvalue()


async def transcribe(audio: bytes) -> str:
    """Audio (webm/ogg/wav vom Browser-MediaRecorder) → deutscher Text."""
    return await asyncio.to_thread(_transcribe_sync, audio)


async def synthesize(text: str) -> bytes:
    """Text → WAV-Bytes (Piper, deutsche Stimme)."""
    return await asyncio.to_thread(_synthesize_sync, text)


def status() -> dict[str, Any]:
    return {
        "stt_model": STT_MODEL,
        "stt_loaded": _whisper is not None,
        "tts_voice": VOICE_ONNX,
        "tts_available": (_voice_dir() / VOICE_ONNX).is_file(),
        "wake_word": _wake_status(),
    }


def _wake_status() -> dict[str, Any]:
    """Weckwort-Daemon-Status (lazy import — vermeidet Zyklus voice↔wakeword)."""
    try:
        from . import wakeword
        return wakeword.daemon.status()
    except Exception:
        return {"laeuft": False, "fehler": "nicht initialisiert"}
