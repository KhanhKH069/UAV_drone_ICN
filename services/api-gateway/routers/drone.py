import asyncio
import base64
import io
import json
import logging
import os
import re
import time
import jwt
from typing import Optional, Tuple

import httpx
import numpy as np
import soundfile as sf
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from connection_manager import ConnectionManager

logger = logging.getLogger("paraline.drone")

router = APIRouter()
drone_conns = ConnectionManager()

WHISPERLIVE_URL = os.getenv("WHISPERLIVE_URL", "http://whisperlive:8001")
AGENT_URL = os.getenv("AGENT_URL", "http://agent-service:8005")

_http = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=20))

CRITICAL_INTENTS = {"land", "stop", "return_home"}
MAX_BUFFER_BYTES = 16000 * 2 * 30

_INTENT_PATTERNS = [
    ("take_off", r"\b(cất cánh|bay lên|take off|takeoff|lift off|launch|take flight|depart)\b"),
    ("land", r"\b(hạ cánh|đáp xuống|land|landing|touch down|set down|descend and land)\b"),
    ("hover", r"\b(dừng lại|đứng yên|giữ vị trí|giữ nguyên|hover|hold position|hold altitude|stay in place|maintain (position|altitude)|wait here)\b"),
    ("stop", r"\b(dừng|ngừng|stop|halt|pause|freeze|cut engines)\b"),
    ("return_home", r"\b(quay về|về nhà|về điểm xuất phát|return (to )?home|go home|come back|rtl|return to base|fly back)\b"),
    ("move_forward", r"\b(tiến|tới|bay tới|tiến tới trước|đi thẳng|bay thẳng|head|go|fly|move|proceed|continue|straight|forward)\b"),
    ("move_backward", r"\b(lùi|bay lùi|lùi lại|backward|back)\b"),
    ("rotate_left", r"\b(xoay trái|quay trái|rotate left|turn left|spin left|yaw left)\b"),
    ("rotate_right", r"\b(xoay phải|quay phải|rotate right|turn right|spin right|yaw right)\b"),
    ("move_left", r"\b(sang trái|bay sang trái|trái|left)\b"),
    ("move_right", r"\b(sang phải|bay sang phải|phải|right)\b"),
    ("ascend", r"\b(bay cao|nâng cao|lên cao|ascend|climb|rise|go up|fly up|move up|increase altitude|higher)\b"),
    ("descend", r"\b(bay thấp|hạ thấp|xuống thấp|descend|lower|go down|fly down|decrease altitude|fly lower)\b"),
    ("follow_target", r"\b(bám theo|theo dõi|đuổi theo|follow|track|chase|pursue|trail|keep up with|stay with)\b"),
    ("get_battery", r"\b(hỏi pin|kiểm tra pin|xem pin|pin|battery|how much battery)\b"),
    ("get_altitude", r"\b(hỏi độ cao|kiểm tra độ cao|độ cao|altitude|how high)\b"),
    ("ask_direction", r"\b(which direction|what direction|where should i go|how to go|where.*go now)\b"),
    ("ask_destination_appearance", r"\b(what.*destination look|how does.*destination|destination.*color|destination.*shape)\b"),
    ("ask_proximity", r"\b(am i (near|close|at)|how far|am i (almost|nearly)|near the destination)\b"),
    ("ask_visibility", r"\b(can i see|is.*in (my )?view|in.*field of view|is.*visible|do i see)\b"),
    ("ask_current_position", r"\b(i am (on|at|in|near)|i('m| am) (on top|on the|at the)|i (move|moved|pass|passed|turn))\b"),
    ("orbit", r"\b(circle|orbit|fly around|loop around|go around|revolve)\b"),
    ("map_area", r"\b(map|scan|survey|cover the area|grid)\b"),
    ("spray_zone", r"\b(spray|sprinkle|dispense|fertiliz)\b"),
]


def _regex_classify(text: str) -> Tuple[Optional[str], float]:
    text_lower = text.lower().strip()
    for intent_name, pattern in _INTENT_PATTERNS:
        if re.search(pattern, text_lower):
            confidence = 0.95 if len(text_lower.split()) <= 8 else 0.85
            return intent_name, confidence
    return None, 0.0


def _extract_entities(text: str, intent: str) -> dict:
    entities = {}
    text_lower = text.lower()

    dist_m = re.search(r"(\d+(?:\.\d+)?)\s*(mét|met|meter|metre|m)s?\b", text_lower)
    dist_cm = re.search(r"(\d+)\s*(centimet|phân|centimeter|centimetre|cm)s?\b", text_lower)
    dist_ft = re.search(r"(\d+(?:\.\d+)?)\s*(?:foot|feet|ft)s?\b", text_lower)
    if dist_m:
        entities["distance_cm"] = int(float(dist_m.group(1)) * 100)
    elif dist_cm:
        entities["distance_cm"] = int(dist_cm.group(1))
    elif dist_ft:
        entities["distance_cm"] = int(float(dist_ft.group(1)) * 30.48)

    angle = re.search(r"(\d+)\s*(độ|degree|deg|°)", text_lower)
    if angle:
        entities["angle_deg"] = int(angle.group(1))

    compass = re.search(
        r"\b(north|south|east|west|northeast|northwest|southeast|southwest)\b",
        text_lower,
    )
    if compass:
        entities["compass"] = compass.group(1)

    clock = re.search(r"\b(\d+)\s*['\u2019]?\s*o['\u2019]?\s*clock\b", text_lower)
    if clock:
        entities["clock"] = int(clock.group(1))

    color_map = {"đỏ": "red", "xanh dương": "blue", "xanh lá": "green", "vàng": "yellow", "trắng": "white", "đen": "black"}
    color = re.search(
        r"\b(red|blue|green|yellow|white|black|orange|purple|brown|grey|gray|đỏ|xanh dương|xanh lá|vàng|trắng|đen)\b",
        text_lower,
    )
    if color:
        c_val = color.group(1)
        entities["target_color"] = color_map.get(c_val, c_val)

    target_map = {"người": "person", "xe hơi": "car", "ô tô": "car", "xe máy": "bike", "people": "person", "man": "person", "woman": "person"}
    obj_class = re.search(
        r"\b(person|people|man|woman|car|bike|bicycle|building|road|bridge|field|area|người|xe hơi|ô tô|xe máy)\b",
        text_lower,
    )
    if obj_class:
        cls_val = obj_class.group(1)
        entities["target_class"] = target_map.get(cls_val, cls_val)

    speed_map = {"chậm": "low", "từ từ": "low", "nhanh": "high", "slow": "low", "slowly": "low", "fast": "high", "quickly": "high"}
    speed = re.search(r"\b(chậm|từ từ|nhanh|slow|fast|quickly|slowly)\b", text_lower)
    if speed:
        entities["speed"] = speed_map.get(speed.group(1), "normal")

    return entities


def _split_compound_commands(text: str) -> list[str]:
    parts = re.split(
        r"\b(and then|then|and|sau đó|rồi|và)\b", text, flags=re.IGNORECASE
    )
    commands = []
    for p in parts:
        p = p.strip()
        if p and p.lower() not in ["and then", "then", "and", "sau đó", "rồi", "và"]:
            commands.append(p)
    return commands

_STT_CORRECTIONS = {
    r"\btek of\b": "take off",
    r"\btake of\b": "take off",
    r"\btack off\b": "take off",
    r"\blaning\b": "landing",
    r"\blen\b": "land",
    r"\bflay\b": "fly",
    r"\bflye\b": "fly",
    r"\bgo foward\b": "go forward",
    r"\bforwad\b": "forward",
    r"\bstraigh\b": "straight",
    r"\brighte\b": "right",
    r"\brotat\b": "rotate",
    r"\bterm left\b": "turn left",
    r"\bterm right\b": "turn right",
    r"\bhove\b": "hover",
    r"\bhaver\b": "hover",
}


def _spell_correct_stt(text: str) -> str:
    text_lower = text.lower()
    for wrong, right in _STT_CORRECTIONS.items():
        text_lower = re.sub(wrong, right, text_lower)
    return text_lower


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

                    en_text = raw_text

                    en_text = _spell_correct_stt(en_text)

                    sub_commands = _split_compound_commands(en_text)
                    command_list = []

                    for sub_text in sub_commands:
                        intent, confidence = _regex_classify(sub_text)
                        entities = _extract_entities(sub_text, intent) if intent else {}

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
