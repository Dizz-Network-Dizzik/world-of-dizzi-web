"""KI-Endpunkte: Chat (SSE-Streaming, Agent-Loop mit Tools), Verlauf,
Gedächtnis, RAG-Index, Status."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .. import db
from ..config import DEFAULT_USER_ID
from . import agent, analyst, memory, providers, rag, tools, voice, wakeword

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

router = APIRouter(prefix="/api/ai", tags=["ki"])


class ChatIn(BaseModel):
    message: str
    sensitive: bool = False  # True ⇒ nichts verlässt den PC (keine Websuche/Boost-Tools)


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(body: ChatIn) -> StreamingResponse:
    user_id = DEFAULT_USER_ID
    msg = body.message.strip()
    if not msg:
        raise HTTPException(status_code=422, detail="Leere Nachricht")

    explicit = memory.explicit_fact_from(msg)
    if explicit:
        memory.add_fact(user_id, explicit, "explizit")

    rag_chunks: list = []
    if db.setting_get(user_id, "rag_enabled", True):
        try:  # RAG ist rein lokal → auch im Sensibel-Modus ok
            rag_chunks = await rag.search(user_id, msg, k=3)
        except Exception:
            pass

    msgs = memory.build_messages(user_id, msg, rag_chunks=rag_chunks)
    memory.save_message(user_id, "user", msg)
    toolset = await tools.registry(body.sensitive)

    async def gen() -> AsyncIterator[str]:
        parts: list[str] = []
        tools_used: list[str] = []
        if explicit:
            yield _sse({"memory_saved": explicit})
        try:
            async for kind, data in agent.stream_agent(msgs, toolset):
                if kind == "t":
                    parts.append(data)
                    yield _sse({"t": data})
                elif kind == "tool":
                    tools_used.append(data["name"])
                    yield _sse({"tool": data["name"], "args": data["args"]})
        except Exception as e:
            yield _sse({"error": f"KI nicht erreichbar: {e}"})
            return
        answer = "".join(parts)
        memory.save_message(user_id, "assistant", answer, provider="lokal")
        db.audit(user_id, "ki", "chat_answered",
                 {"provider": "lokal", "chars": len(answer),
                  "sensitive": body.sensitive, "tools": tools_used})
        yield _sse({"done": True, "provider": "lokal", "tools": tools_used})
        asyncio.get_event_loop().create_task(_post_exchange(user_id, msg, answer))

    return StreamingResponse(gen(), media_type="text/event-stream")


async def _post_exchange(user_id: str, user_msg: str, answer: str) -> None:
    await memory.auto_extract(user_id, user_msg, answer)
    await memory.maybe_summarize_episode(user_id)


@router.get("/history")
def get_history(limit: int = 50) -> list[dict[str, Any]]:
    return memory.history(DEFAULT_USER_ID, limit=min(limit, 200))


@router.get("/memory")
def get_memory() -> list[dict[str, Any]]:
    return memory.facts(DEFAULT_USER_ID)


@router.delete("/memory/{fact_id}")
def remove_fact(fact_id: str) -> dict[str, Any]:
    if not memory.delete_fact(DEFAULT_USER_ID, fact_id):
        raise HTTPException(status_code=404, detail="Fakt nicht gefunden")
    return {"ok": True}


class IndexIn(BaseModel):
    folder: str | None = None  # Default: Projektordner (docs etc.)


@router.post("/index")
async def index_folder(body: IndexIn) -> dict[str, Any]:
    folder = Path(body.folder) if body.folder else _PROJECT_ROOT
    if not folder.is_dir():
        raise HTTPException(status_code=422, detail=f"Kein Ordner: {folder}")
    return await rag.index_folder(DEFAULT_USER_ID, folder)


@router.get("/rag/status")
def rag_status() -> dict[str, Any]:
    return rag.status()


@router.get("/tools")
async def list_tools(sensitive: bool = False) -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description}
            for t in await tools.registry(sensitive)]


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile) -> dict[str, Any]:
    """Spracheingabe → Text (faster-whisper, rein lokal)."""
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=422, detail="Leere Audiodatei")
    try:
        text = await voice.transcribe(data)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"STT nicht verfügbar: {e}")
    db.audit(DEFAULT_USER_ID, "user", "voice_input", {"chars": len(text)})
    return {"text": text}


class SpeakIn(BaseModel):
    text: str


@router.post("/speak")
async def speak(body: SpeakIn) -> Response:
    """Text → Sprachausgabe als WAV (Piper, rein lokal)."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Leerer Text")
    try:
        wav = await voice.synthesize(text[:2000])
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"TTS nicht verfügbar: {e}")
    return Response(content=wav, media_type="audio/wav")


@router.get("/voice/status")
def voice_status() -> dict[str, Any]:
    return voice.status()


# --- Weckwort („immer lauschen", openWakeWord, lokal) ------------------------
def _on_wake(wort: str, wav: bytes) -> None:
    """Daemon-Callback (Mikro-Thread): Weckwort erkannt ⇒ Sprachfenster durch
    die STT-Pipeline schicken und das Transkript in die Glocke legen. Läuft
    synchron im Daemon-Thread; Fehler bleiben hier (der Daemon fängt sie)."""
    db.audit(DEFAULT_USER_ID, "user", "wake_erkannt", {"wort": wort})
    text = ""
    try:
        text = voice._transcribe_sync(wav)
    except Exception:
        text = ""
    titel = f"„{text}“" if text else "(kein Sprachbefehl erkannt)"
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO notices (id, user_id, source, severity, title, detail, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (db.new_id(), DEFAULT_USER_ID, "wakeword", "info",
         f"Weckwort erkannt: {titel}",
         json.dumps({"wort": wort, "transkript": text}, ensure_ascii=False),
         db.now_iso()))
    conn.commit()


def start_wake_from_settings() -> dict[str, Any]:
    """Startet den Daemon mit den gespeicherten Einstellungen (Lifespan + /start)."""
    wakeword.eingabe_geraete()   # Geräte-Cache füllen, BEVOR ein Stream offen ist
    wort = db.setting_get(DEFAULT_USER_ID, "voice_wake_wort") or wakeword.DEFAULT_WORT
    schwelle = float(db.setting_get(DEFAULT_USER_ID, "voice_wake_schwelle") or 0.5)
    geraet = db.setting_get(DEFAULT_USER_ID, "voice_wake_geraet")
    wakeword.daemon.on_wake = _on_wake
    # Geräte-Angabe robust auflösen (Name-Hinweis übersteht Index-Wandern).
    return wakeword.daemon.start(wort, schwelle, wakeword.geraet_aufloesen(geraet))


@router.get("/wake/status")
def wake_status() -> dict[str, Any]:
    return {
        **wakeword.daemon.status(),
        "aktiv_setting": bool(db.setting_get(DEFAULT_USER_ID, "voice_wake_aktiv")),
        "woerter": wakeword.verfuegbare_woerter(),
        "geraete": wakeword.eingabe_geraete(),
        "gewaehltes_wort": db.setting_get(DEFAULT_USER_ID, "voice_wake_wort")
                           or wakeword.DEFAULT_WORT,
    }


class WakeEinstellungIn(BaseModel):
    wort: str | None = None
    schwelle: float | None = None
    # int (fester Index) ODER str (Namens-Hinweis, z. B. "USB dongle" — übersteht
    # Index-Wandern); beim Start löst geraet_aufloesen() das robust auf.
    geraet: "int | str | None" = None


@router.post("/wake/einstellungen")
def wake_einstellungen(body: WakeEinstellungIn) -> dict[str, Any]:
    if body.wort is not None:
        if body.wort not in wakeword.verfuegbare_woerter():
            raise HTTPException(status_code=400, detail="Unbekanntes Weckwort")
        db.setting_put(DEFAULT_USER_ID, "voice_wake_wort", body.wort)
    if body.schwelle is not None:
        db.setting_put(DEFAULT_USER_ID, "voice_wake_schwelle",
                       max(0.0, min(1.0, body.schwelle)))
    if body.geraet is not None:
        db.setting_put(DEFAULT_USER_ID, "voice_wake_geraet", body.geraet)
    return {"ok": True}


@router.post("/wake/start")
def wake_start() -> dict[str, Any]:
    """Mikrofon-Lauschen einschalten (opt-in). Hält über Neustarts an
    (Setting), Daemon startet im Lifespan automatisch nach."""
    db.setting_put(DEFAULT_USER_ID, "voice_wake_aktiv", True)
    res = start_wake_from_settings()
    db.audit(DEFAULT_USER_ID, "user", "wake_gestartet", {})
    return {**res, **wakeword.daemon.status()}


@router.post("/wake/stop")
def wake_stop() -> dict[str, Any]:
    db.setting_put(DEFAULT_USER_ID, "voice_wake_aktiv", False)
    wakeword.daemon.stop()
    db.audit(DEFAULT_USER_ID, "user", "wake_gestoppt", {})
    return {"ok": True}


@router.get("/notices")
def get_notices(unread_only: bool = False) -> list[dict[str, Any]]:
    return analyst.notices(DEFAULT_USER_ID, unread_only=unread_only)


@router.post("/notices/read")
def read_notices() -> dict[str, Any]:
    return {"marked": analyst.mark_read(DEFAULT_USER_ID)}


@router.get("/status")
async def ai_status() -> dict[str, Any]:
    return await providers.status()
