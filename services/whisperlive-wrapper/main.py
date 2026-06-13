import base64
import json
import logging
import os

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("paraline.whisperlive")

ASR_BACKEND = os.getenv("ASR_BACKEND", "faster_whisper")

_MOCK_PHRASES = [
    "Hello everyone, today we will discuss the project timeline.",
    "The development team has finished the first phase.",
    "We need to review the requirements before the next sprint.",
    "Please share your feedback on the current design proposal.",
    "The meeting will wrap up with a summary of action items.",
]
_mock_idx = 0

_backend = None

logger.info(f"Starting ASR backend: '{ASR_BACKEND}'...")

try:
    if ASR_BACKEND == "faster_whisper":
        from backends.faster_whisper_backend import FasterWhisperBackend

        _backend = FasterWhisperBackend()

    elif ASR_BACKEND == "qwen3_asr":
        from backends.qwen3_asr_backend import Qwen3ASRBackend

        _backend = Qwen3ASRBackend()

    elif ASR_BACKEND == "sensevoice":
        from backends.sensevoice_backend import SenseVoiceBackend

        _backend = SenseVoiceBackend()

    else:
        raise ValueError(
            f"Invalid ASR_BACKEND: '{ASR_BACKEND}'. "
            "Choose 'faster_whisper', 'qwen3_asr', or 'sensevoice'."
        )

    logger.info(f"ASR backend '{_backend.name}' ready.")

except Exception as e:
    _backend = None
    logger.error(f"Backend load error '{ASR_BACKEND}': {e}", exc_info=True)


app = FastAPI(title=f"Paraline ASR [{ASR_BACKEND}]")


class TranscribeReq(BaseModel):
    audio_b64: str
    language: str = "auto"
    sample_rate: int = 16000
    beam_size: int = 5
    vad_filter: bool = True


class TranscribeResp(BaseModel):
    text: str
    language: str
    latency_ms: float
    segments: list = []


@app.post("/transcribe", response_model=TranscribeResp)
async def transcribe(req: TranscribeReq):
    global _mock_idx

    mock_text = os.getenv("MOCK_TRANSCRIPTION_TEXT", "")
    if mock_text == "__cycle__":
        text = _MOCK_PHRASES[_mock_idx % len(_MOCK_PHRASES)]
        _mock_idx += 1
        logger.info(f"[mock] returning preset phrase: {text[:60]}")
        return TranscribeResp(text=text, language="en", latency_ms=0.0, segments=[])
    elif mock_text:
        logger.info(f"[mock] returning fixed text: {mock_text[:60]}")
        return TranscribeResp(
            text=mock_text, language="en", latency_ms=0.0, segments=[]
        )

    if _backend is None:
        raise HTTPException(
            503, f"ASR backend '{ASR_BACKEND}' is not ready. Check server logs."
        )

    try:
        audio_np = np.frombuffer(base64.b64decode(req.audio_b64), dtype=np.float32)

        result = _backend.transcribe(
            audio_np=audio_np,
            language=req.language,
            sample_rate=req.sample_rate,
            beam_size=req.beam_size,
            vad_filter=req.vad_filter,
        )

        logger.info(f"[{_backend.name}] TEXT: '{result.text[:60]}'")

        return TranscribeResp(
            text=result.text,
            language=result.language,
            latency_ms=result.latency_ms,
            segments=result.segments,
        )

    except Exception as e:
        logger.error(f"ASR error: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@app.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    if _backend is None:
        await websocket.accept()
        await websocket.close(code=1011, reason="Backend not loaded")
        return

    await websocket.accept()
    audio_buffer = bytearray()

    BYTES_PER_SEC = 16000 * 2
    CHUNK_SIZE = int(BYTES_PER_SEC * 0.5)

    last_processed_len = 0

    try:
        while True:
            data = await websocket.receive()

            if "bytes" in data:
                audio_buffer.extend(data["bytes"])

                if len(audio_buffer) - last_processed_len >= CHUNK_SIZE:
                    last_processed_len = len(audio_buffer)

                    audio_np = (
                        np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32)
                        / 32768.0
                    )
                    try:
                        result = _backend.transcribe(
                            audio_np, language="auto", vad_filter=False
                        )
                        await websocket.send_json(
                            {
                                "type": "partial",
                                "text": result.text,
                                "latency_ms": result.latency_ms,
                            }
                        )
                    except Exception as e:
                        logger.error(f"[WS Partial Error]: {e}")

            elif "text" in data:
                try:
                    cmd = json.loads(data["text"])
                    if cmd.get("event") == "endpoint":
                        if len(audio_buffer) > 0:
                            audio_np = (
                                np.frombuffer(audio_buffer, dtype=np.int16).astype(
                                    np.float32
                                )
                                / 32768.0
                            )
                            result = _backend.transcribe(
                                audio_np, language="auto", vad_filter=False
                            )
                            await websocket.send_json(
                                {"type": "final", "text": result.text}
                            )
                        else:
                            await websocket.send_json({"type": "final", "text": ""})

                        audio_buffer.clear()
                        last_processed_len = 0
                except json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")


@app.get("/health")
async def health():
    return {
        "status": "ok" if _backend is not None else "backend_not_loaded",
        "backend": ASR_BACKEND,
        "model": _backend.name if _backend else None,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
