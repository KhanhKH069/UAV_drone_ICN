"""
services/api-gateway/routers/drone.py
WebSocket endpoint dành riêng cho UAV Drone.

Pipeline:
  Raspberry Pi 5 → (audio bytes) → ws://.../drone/stream
    → Step 1: Whisper STT        → text lệnh (EN hoặc VI)
    → Step 2: NLLB Translation   → text lệnh tiếng Anh (nếu đầu vào là VI)
    → Step 3: Regex Intent Match → intent + entities (nhanh, <10ms)
    → Step 4: LLM Fallback       → nếu Regex không match (confidence < 0.7)
    → Response JSON              → {"intent": "move_forward", "entities": {...}}

Frame protocol (Drone → Server):
  bytes  : raw PCM int16 16kHz mono audio chunk
  text   : JSON command, e.g. {"event": "endpoint"}  ← chốt câu, yêu cầu kết quả cuối

Frame protocol (Server → Drone):
  {"type": "partial",  "text": "fly forw..."}                  ← STT đang nhận diện
  {"type": "command",  "intent": "move_forward",
                        "entities": {"distance_cm": 200},
                        "raw_text": "fly forward 2 meters",
                        "confidence": 0.95, "latency_ms": 210} ← Lệnh xác định
  {"type": "unknown",  "raw_text": "...", "latency_ms": 300}   ← Không nhận diện được
  {"type": "error",    "message": "..."}
"""
import asyncio
import json
import logging
import os
import re
import time
from typing import Optional, Tuple

import httpx
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = logging.getLogger("paraline.drone")

router = APIRouter()

WHISPERLIVE_URL = os.getenv("WHISPERLIVE_URL", "http://whisperlive:8001")
TRANSLATION_URL = os.getenv("TRANSLATION_URL", "http://translation-service:8002")
AGENT_URL       = os.getenv("AGENT_URL",       "http://agent-service:8005")

_http = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=20))

# ─────────────────────────────────────────────────────────────────────────────
# Bộ 28 intents + Regex Rule-based (Tầng 1 NLP)
# Học theo kiến trúc cascade 3 tầng từ đồ án UAV (Chương 2.3)
# ─────────────────────────────────────────────────────────────────────────────
# fmt: off
_INTENT_PATTERNS = [
    # --- Nhóm: Điều khiển bay cơ bản ---
    ("take_off",       r"\b(take\s?off|takeoff|launch|lift\s?off|fly\s?up)\b"),
    ("land",           r"\b(land|landing|come\s?down|touch\s?down)\b"),
    ("hover",          r"\b(hover|hold|stay|stop\s+moving|maintain\s+position)\b"),
    ("stop",           r"\b(stop|halt|freeze|abort)\b"),
    ("return_home",    r"\b(return|go\s+home|come\s+back|rtl)\b"),
    # --- Nhóm: Di chuyển ---
    ("move_forward",   r"\b(fly|move|go)\s+(forward|ahead|front)\b"),
    ("move_backward",  r"\b(fly|move|go)\s+(backward|back|rear|behind)\b"),
    ("move_left",      r"\b(fly|move|go|strafe)\s+left\b"),
    ("move_right",     r"\b(fly|move|go|strafe)\s+right\b"),
    ("ascend",         r"\b(go|fly|move|climb)\s+up\b|\bascend\b|\bincrease\s+altitude\b"),
    ("descend",        r"\b(go|fly|move)\s+down\b|\bdescend\b|\bdecrease\s+altitude\b"),
    # --- Nhóm: Quay hướng ---
    ("rotate_left",    r"\b(rotate|turn|yaw)\s+(left|counter.?clockwise|ccw)\b"),
    ("rotate_right",   r"\b(rotate|turn|yaw)\s+(right|clockwise|cw)\b"),
    ("rotate_degrees", r"\b(rotate|turn|yaw)\b.{0,20}\b(\d+)\s*(degree|deg|°)\b"),
    ("face_north",     r"\bface\s+north\b|\bhead\s+north\b"),
    ("face_south",     r"\bface\s+south\b|\bhead\s+south\b"),
    ("face_east",      r"\bface\s+east\b|\bhead\s+east\b"),
    ("face_west",      r"\bface\s+west\b|\bhead\s+west\b"),
    # --- Nhóm: Theo dõi mục tiêu ---
    ("follow_target",  r"\b(follow|track|chase|pursue)\b"),
    ("stop_tracking",  r"\b(stop\s+follow|stop\s+track|lose\s+target|cancel\s+follow)\b"),
    # --- Nhóm: Điều khiển Camera ---
    ("camera_up",      r"\b(camera|gimbal)\s+up\b|\blook\s+up\b"),
    ("camera_down",    r"\b(camera|gimbal)\s+down\b|\blook\s+down\b"),
    ("take_photo",     r"\b(take\s+photo|take\s+picture|capture|shoot|snapshot)\b"),
    ("start_video",    r"\b(start\s+(recording|video)|record|begin\s+record)\b"),
    ("stop_video",     r"\b(stop\s+(recording|video)|end\s+record)\b"),
    # --- Nhóm: Query ---
    ("get_altitude",   r"\b(what|how).{0,10}(altitude|height)\b|\b(altitude|height)\?"),
    ("get_battery",    r"\b(what|how).{0,10}battery\b|\bbattery\s+(level|status|percent)"),
    ("get_position",   r"\b(where|what).{0,10}(position|location|coordinate)\b"),
]
# fmt: on

def _regex_classify(text: str) -> Tuple[Optional[str], float]:
    """
    Phân loại intent bằng Regex.
    Trả về (intent_name, confidence) hoặc (None, 0.0) nếu không khớp.
    Confidence: 0.95 nếu match chính xác, thấp hơn nếu text dài/phức tạp.
    """
    text_lower = text.lower().strip()
    for intent_name, pattern in _INTENT_PATTERNS:
        if re.search(pattern, text_lower):
            # Confidence giảm nhẹ nếu câu quá dài (có thể là câu phức hợp)
            confidence = 0.95 if len(text_lower.split()) <= 8 else 0.85
            return intent_name, confidence
    return None, 0.0


def _extract_entities(text: str, intent: str) -> dict:
    """
    Trích xuất entity từ text lệnh theo intent.
    Ví dụ: "fly forward 2 meters" → {"distance_cm": 200}
    """
    entities = {}
    text_lower = text.lower()

    # Khoảng cách (distance)
    dist_m = re.search(r"(\d+(?:\.\d+)?)\s*(meter|metre|m)\b", text_lower)
    dist_cm = re.search(r"(\d+)\s*(centimeter|centimetre|cm)\b", text_lower)
    dist_ft = re.search(r"(\d+(?:\.\d+)?)\s*(?:foot|feet|ft)\b", text_lower)
    if dist_m:
        entities["distance_cm"] = int(float(dist_m.group(1)) * 100)
    elif dist_cm:
        entities["distance_cm"] = int(dist_cm.group(1))
    elif dist_ft:
        entities["distance_cm"] = int(float(dist_ft.group(1)) * 30.48)

    # Góc quay (angle)
    angle = re.search(r"(\d+)\s*(degree|deg|°)", text_lower)
    if angle:
        entities["angle_deg"] = int(angle.group(1))

    # Màu sắc mục tiêu (color)
    color = re.search(r"\b(red|blue|green|yellow|white|black|orange|purple)\b", text_lower)
    if color:
        entities["target_color"] = color.group(1)

    # Loại mục tiêu (class)
    obj_class = re.search(r"\b(person|people|man|woman|car|bike|bicycle)\b", text_lower)
    if obj_class:
        target_map = {"people": "person", "man": "person", "woman": "person"}
        entities["target_class"] = target_map.get(obj_class.group(1), obj_class.group(1))

    # Tốc độ (speed)
    speed = re.search(r"\b(slow|fast|quickly|slowly)\b", text_lower)
    if speed:
        speed_map = {"slow": "low", "slowly": "low", "fast": "high", "quickly": "high"}
        entities["speed"] = speed_map.get(speed.group(1), "normal")

    return entities


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/drone/stream")
async def drone_stream(
    websocket: WebSocket,
    api_key: str = Query(""),
    drone_id: str = Query("drone-01"),
    lang: str = Query("en", description="Ngôn ngữ lệnh: 'en' hoặc 'vi'"),
):
    """
    WebSocket endpoint để Raspberry Pi 5 stream audio lệnh bay.
    - drone_id : ID của drone (ghi log phân biệt nhiều drone)
    - lang     : 'en' = lệnh tiếng Anh (mặc định), 'vi' = tự động dịch sang EN qua NLLB
    """
    # Auth
    if api_key != os.getenv("CLIENT_API_KEY", "drone-secret"):
        await websocket.accept()
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    logger.info(f"🚁 [Drone] Connected: drone_id={drone_id}, lang={lang}")

    audio_buffer = bytearray()
    BYTES_PER_SEC = 16000 * 2  # 16kHz, int16
    CHUNK_SIZE = int(BYTES_PER_SEC * 0.5)  # Partial STT mỗi 0.5s
    last_processed_len = 0

    try:
        while True:
            data = await websocket.receive()

            # ── Nhận chunk audio thô từ Raspberry Pi ──────────────────────
            if "bytes" in data:
                audio_buffer.extend(data["bytes"])

                # Gửi partial STT sau mỗi 0.5s audio
                if len(audio_buffer) - last_processed_len >= CHUNK_SIZE:
                    last_processed_len = len(audio_buffer)
                    audio_np = (
                        np.frombuffer(bytes(audio_buffer), dtype=np.int16)
                        .astype(np.float32) / 32768.0
                    )
                    partial_text = await _asr(audio_np, lang)
                    if partial_text:
                        await websocket.send_json({
                            "type": "partial",
                            "text": partial_text,
                        })

            # ── Nhận lệnh điều khiển (chốt câu, reset,...) ─────────────────
            elif "text" in data:
                try:
                    cmd = json.loads(data["text"])
                except json.JSONDecodeError:
                    continue

                if cmd.get("event") == "endpoint":
                    # Raspberry Pi báo kết thúc câu lệnh → xử lý toàn bộ buffer
                    t0 = time.perf_counter()

                    if len(audio_buffer) == 0:
                        await websocket.send_json({"type": "unknown", "raw_text": "", "latency_ms": 0})
                        continue

                    audio_np = (
                        np.frombuffer(bytes(audio_buffer), dtype=np.int16)
                        .astype(np.float32) / 32768.0
                    )

                    # Reset buffer cho câu tiếp theo
                    audio_buffer.clear()
                    last_processed_len = 0

                    # Step 1: ASR
                    raw_text = await _asr(audio_np, lang)
                    if not raw_text:
                        await websocket.send_json({
                            "type": "unknown",
                            "raw_text": "",
                            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                        })
                        continue

                    logger.info(f"🎙️ [Drone/{drone_id}] ASR: '{raw_text}'")

                    # Step 2: Dịch VI → EN nếu cần
                    en_text = raw_text
                    if lang == "vi":
                        en_text = await _translate_to_en(raw_text)
                        logger.info(f"🌐 [Drone/{drone_id}] Translated: '{en_text}'")

                    # Step 3: Regex Intent Classification (Tầng 1 — nhanh <10ms)
                    intent, confidence = _regex_classify(en_text)
                    entities = _extract_entities(en_text, intent) if intent else {}

                    # Step 4: LLM Fallback nếu Regex không match
                    if intent is None or confidence < 0.7:
                        logger.info(f"🤖 [Drone/{drone_id}] Regex miss → LLM fallback for: '{en_text}'")
                        intent, entities, confidence = await _llm_classify(en_text)

                    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

                    if intent:
                        logger.info(
                            f"✅ [Drone/{drone_id}] COMMAND: intent={intent} "
                            f"entities={entities} conf={confidence:.2f} latency={latency_ms}ms"
                        )
                        await websocket.send_json({
                            "type":        "command",
                            "intent":      intent,
                            "entities":    entities,
                            "raw_text":    raw_text,
                            "en_text":     en_text,
                            "confidence":  round(confidence, 2),
                            "latency_ms":  latency_ms,
                        })
                    else:
                        logger.warning(f"❓ [Drone/{drone_id}] UNKNOWN: '{en_text}' ({latency_ms}ms)")
                        await websocket.send_json({
                            "type":       "unknown",
                            "raw_text":   raw_text,
                            "en_text":    en_text,
                            "latency_ms": latency_ms,
                        })

                elif cmd.get("event") == "reset":
                    audio_buffer.clear()
                    last_processed_len = 0
                    await websocket.send_json({"type": "reset_ok"})

    except WebSocketDisconnect:
        logger.info(f"🚁 [Drone/{drone_id}] Disconnected")
    except Exception as e:
        logger.error(f"Drone WS error [{drone_id}]: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

async def _asr(audio_np: np.ndarray, lang: str) -> str:
    """Gọi Whisper STT, trả về text thô."""
    import base64
    audio_b64 = base64.b64encode(audio_np.astype(np.float32).tobytes()).decode()
    # Map sang NLLB code để Whisper backend nhận diện ngôn ngữ đúng
    lang_map = {"en": "eng_Latn", "vi": "vie_Latn", "ja": "jpn_Jpan"}
    try:
        resp = await _http.post(f"{WHISPERLIVE_URL}/transcribe", json={
            "audio_b64":  audio_b64,
            "language":   lang_map.get(lang, "auto"),
            "vad_filter": True,
        })
        resp.raise_for_status()
        return resp.json().get("text", "").strip()
    except Exception as e:
        logger.error(f"ASR error: {e}")
        return ""


async def _translate_to_en(text: str) -> str:
    """Dịch văn bản từ tiếng Việt sang tiếng Anh qua NLLB."""
    if not text:
        return text
    try:
        resp = await _http.post(f"{TRANSLATION_URL}/translate", json={
            "text":     text,
            "src_lang": "vie_Latn",
            "tgt_lang": "eng_Latn",
        })
        resp.raise_for_status()
        return resp.json().get("translated_text", text)
    except Exception as e:
        logger.warning(f"Translation failed, using original: {e}")
        return text


async def _llm_classify(text: str) -> Tuple[Optional[str], dict, float]:
    """
    Gọi agent-service để phân loại intent bằng LLM (Ollama).
    Trả về (intent, entities, confidence).
    """
    try:
        resp = await _http.post(f"{AGENT_URL}/drone/classify", json={"text": text})
        resp.raise_for_status()
        data = resp.json()
        return data.get("intent"), data.get("entities", {}), data.get("confidence", 0.7)
    except Exception as e:
        logger.error(f"LLM classify error: {e}")
        return None, {}, 0.0
