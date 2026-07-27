"""Sprachschicht-Endpoints (Modelle gemockt — echte STT/TTS testet der
Roundtrip-Beweis Piper→Whisper manuell/E2E, nicht die Unit-Suite)."""

from fastapi.testclient import TestClient

from app.ai import voice
from app.main import app

client = TestClient(app)


def test_transcribe_endpoint(monkeypatch):
    async def fake(audio: bytes) -> str:
        assert audio == b"AUDIO"
        return "Hallo Dizzi"
    monkeypatch.setattr(voice, "transcribe", fake)
    r = client.post("/api/ai/transcribe", files={"audio": ("a.webm", b"AUDIO", "audio/webm")})
    assert r.status_code == 200
    assert r.json()["text"] == "Hallo Dizzi"


def test_transcribe_empty_audio():
    r = client.post("/api/ai/transcribe", files={"audio": ("a.webm", b"", "audio/webm")})
    assert r.status_code == 422


def test_speak_endpoint(monkeypatch):
    async def fake(text: str) -> bytes:
        return b"RIFFWAV" + text.encode()
    monkeypatch.setattr(voice, "synthesize", fake)
    r = client.post("/api/ai/speak", json={"text": "Hallo"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert r.content.startswith(b"RIFFWAV")


def test_speak_empty_text():
    assert client.post("/api/ai/speak", json={"text": "  "}).status_code == 422


def test_voice_status_shape():
    s = voice.status()
    assert s["stt_model"] == voice.STT_MODEL
    assert "tts_available" in s and "wake_word" in s