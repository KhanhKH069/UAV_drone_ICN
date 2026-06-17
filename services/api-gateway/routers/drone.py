import asyncio
import base64
import io
import json
import logging
import os
import time
import jwt
from typing import Optional, Tuple

import httpx
import numpy as np
import soundfile as sf
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from connection_manager import ConnectionManager
from nlp import spell_correct, regex_classify, extract_entities, split_compound_commands

logger = logging.getLogger("uav_drone.drone")

router = APIRouter()
drone_conns = ConnectionManager()

WHISPERLIVE_URL = os.getenv("WHISPERLIVE_URL", "http://whisperlive:8001")
AGENT_URL = os.getenv("AGENT_URL", "http://agent-service:8005")

_http = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=20))

CRITICAL_INTENTS = {"land", "stop", "return_home"}
MAX_BUFFER_BYTES = 16000 * 2 * 30  # 30 seconds of 16kHz mono int16 audio



@router.websocket("/drone/stream")
async def drone_stream(
    websocket: WebSocket,
    drone_id: str = Query("drone-01"),
    lang: str = Query("en"),
):
    await websocket.accept()

    try:
        first_msg = await asyncio.wait_for(websocket.receive(), timeout=5.0)
        cmd = json.loads(first_msg.get("text", "{}"))
        if cmd.get("event") != "auth":
            await websocket.close(code=4001, reason="Unauthorized")
            return
        token = cmd.get("token", "")
        jwt_secret = os.getenv("JWT_SECRET", "super-secret-jwt-key")
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        if payload.get("role") != "drone_client":
            raise ValueError("Invalid role")
    except Exception as e:
        logger.warning(f"WS Auth failed: {e}")
        try:
            await websocket.close(code=4001, reason="Unauthorized")
        except Exception:
            pass
        return

    drone_conns.register(websocket, drone_id, direction="drone")
    logger.info(f"[Drone] Connected: drone_id={drone_id}, lang={lang}")

    audio_buffer = bytearray()
    BYTES_PER_SEC = 16000 * 2
    CHUNK_SIZE = int(BYTES_PER_SEC * 0.5)
    last_processed_len = 0

    try:
        while True:
            data = await websocket.receive()

            if "bytes" in data:
                payload = data["bytes"]
                if payload.startswith(b"OggS"):
                    pcm_data, _ = sf.read(io.BytesIO(payload), dtype="int16")
                    audio_buffer.extend(pcm_data.tobytes())
                else:
                    audio_buffer.extend(payload)

                if len(audio_buffer) > MAX_BUFFER_BYTES:
                    audio_buffer = audio_buffer[-MAX_BUFFER_BYTES:]
                    last_processed_len = min(last_processed_len, len(audio_buffer))

                if len(audio_buffer) - last_processed_len >= CHUNK_SIZE:
                    last_processed_len = len(audio_buffer)
                    audio_np = (
                        np.frombuffer(bytes(audio_buffer), dtype=np.int16).astype(
                            np.float32
                        )
                        / 32768.0
                    )
                    partial_text = await _asr(audio_np, lang)
                    if partial_text:
                        await drone_conns.broadcast(
                            drone_id,
                            {
                                "type": "partial",
                                "text": partial_text,
                            },
                        )

            elif "text" in data:
                try:
                    cmd = json.loads(data["text"])
                except json.JSONDecodeError:
                    continue

                if cmd.get("event") == "telemetry":
                    await drone_conns.broadcast(
                        drone_id,
                        {
                            "type": "telemetry",
                            "data": cmd.get("data", {})
                        }
                    )
                elif cmd.get("event") == "endpoint":
                    t0 = time.perf_counter()

                    if len(audio_buffer) == 0:
                        await drone_conns.broadcast(
                            drone_id,
                            {"type": "unknown", "raw_text": "", "latency_ms": 0},
                        )
                        continue

                    audio_np = (
                        np.frombuffer(bytes(audio_buffer), dtype=np.int16).astype(
                            np.float32
                        )
                        / 32768.0
                    )

                    audio_buffer.clear()
                    last_processed_len = 0

                    raw_text = await _asr(audio_np, lang)
                    if not raw_text:
                        await drone_conns.broadcast(
                            drone_id,
                            {
                                "type": "unknown",
                                "raw_text": "",
                                "latency_ms": round(
                                    (time.perf_counter() - t0) * 1000, 1
                                ),
                            },
                        )
                        continue

                    logger.info(f"[Drone/{drone_id}] ASR: '{raw_text}'")

                    en_text = spell_correct(raw_text)

                    sub_commands = split_compound_commands(en_text)
                    command_list = []

                    for sub_text in sub_commands:
                        intent, confidence = regex_classify(sub_text)
                        entities = extract_entities(sub_text, intent) if intent else {}

                        require_confirmation = False

                        if intent is None or confidence < 0.7:
                            logger.info(
                                f"[Drone/{drone_id}] Regex miss -> LLM fallback for: '{sub_text}'"
                            )
                            intent, entities, confidence = await _llm_classify(sub_text)

                            if intent in CRITICAL_INTENTS:
                                require_confirmation = True
                                logger.warning(
                                    f"[Drone/{drone_id}] LLM generated CRITICAL intent: {intent}. Requiring confirmation."
                                )

                        if intent:
                            command_list.append(
                                {
                                    "intent": intent,
                                    "entities": entities,
                                    "confidence": round(confidence, 2),
                                    "require_confirmation": require_confirmation,
                                }
                            )

                    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

                    if command_list:
                        logger.info(
                            f"[Drone/{drone_id}] COMMANDS ({len(command_list)}): {command_list} latency={latency_ms}ms"
                        )
                        await drone_conns.broadcast(
                            drone_id,
                            {
                                "type": "command_list",
                                "commands": command_list,
                                "raw_text": raw_text,
                                "en_text": en_text,
                                "latency_ms": latency_ms,
                            },
                        )
                    else:
                        logger.warning(
                            f"[Drone/{drone_id}] UNKNOWN: '{en_text}' ({latency_ms}ms)"
                        )
                        await drone_conns.broadcast(
                            drone_id,
                            {
                                "type": "unknown",
                                "raw_text": raw_text,
                                "en_text": en_text,
                                "latency_ms": latency_ms,
                            },
                        )

                elif cmd.get("event") == "reset":
                    audio_buffer.clear()
                    last_processed_len = 0
                    await drone_conns.broadcast(drone_id, {"type": "reset_ok"})

    except WebSocketDisconnect:
        logger.info(f"[Drone/{drone_id}] Disconnected")
        drone_conns.disconnect(websocket, drone_id)
    except Exception as e:
        logger.error(f"Drone WS error [{drone_id}]: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        finally:
            drone_conns.disconnect(websocket, drone_id)


async def _asr(audio_np: np.ndarray, lang: str) -> str:
    audio_b64 = base64.b64encode(audio_np.astype(np.float32).tobytes()).decode()
    lang_map = {"en": "eng_Latn", "vi": "vie_Latn", "ja": "jpn_Jpan"}
    try:
        resp = await _http.post(
            f"{WHISPERLIVE_URL}/transcribe",
            json={
                "audio_b64": audio_b64,
                "language": lang_map.get(lang, "auto"),
                "vad_filter": True,
            },
        )
        resp.raise_for_status()
        return resp.json().get("text", "").strip()
    except Exception as e:
        logger.error(f"ASR error: {e}")
        return ""


async def _llm_classify(text: str) -> Tuple[Optional[str], dict, float]:
    try:
        resp = await _http.post(f"{AGENT_URL}/drone/classify", json={"text": text})
        resp.raise_for_status()
        data = resp.json()
        return data.get("intent"), data.get("entities", {}), data.get("confidence", 0.7)
    except Exception as e:
        logger.error(f"LLM classify error: {e}")
        return None, {}, 0.0
