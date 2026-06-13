import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import json
import logging
import os
import re
import time
from collections import OrderedDict, deque
from typing import List, Optional

import httpx
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from prompts import SUMMARY_PROMPT, ACTION_ITEMS_PROMPT
from drone_prompts import DRONE_CLASSIFY_PROMPT, DRONE_MULTI_CLASSIFY_PROMPT

logger = logging.getLogger("paraline.agent")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3:8b")
COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://transcription-collector:8006")

_http = httpx.AsyncClient(timeout=120.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def prewarm_task():
        await asyncio.sleep(5)
        await _prewarm_cache()
    asyncio.create_task(prewarm_task())
    yield


app = FastAPI(title="Paraline Agent Service", version="2.0.0", lifespan=lifespan)

_PREWARM_COMMANDS = [
    "dừng khẩn cấp",
    "dừng lại ngay",
    "dừng ngay lập tức",
    "cất cánh",
    "bay lên",
    "hạ cánh",
    "hạ xuống",
    "tiến lên 2 mét",
    "lùi lại 2 mét",
    "sang trái 2 mét",
    "sang phải 2 mét",
    "bay lên 3 mét",
    "xoay phải 90 độ",
    "quay về nhà",
    "kiểm tra pin",
]

_classify_cache: OrderedDict = OrderedDict()
_CACHE_MAX_SIZE = 100
_LATENCY_WINDOW = 200
_classify_latencies: deque = deque(maxlen=_LATENCY_WINDOW)


class ActionItem(BaseModel):
    task: str
    assignee: Optional[str] = None
    deadline: Optional[str] = None
    priority: str = "medium"


class MeetingMinutesResp(BaseModel):
    session_id: str
    summary: str
    key_points: List[str] = []
    action_items: List[ActionItem] = []
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    total_latency_ms: float = 0.0


@app.post("/agent/summarize/{session_id}", response_model=MeetingMinutesResp)
async def summarize(session_id: str):
    t0 = time.perf_counter()
    try:
        resp = await _http.get(f"{COLLECTOR_URL}/sessions/{session_id}/export")
        resp.raise_for_status()
        transcript = resp.json().get("transcript", "")

        if not transcript.strip():
            raise HTTPException(404, "No transcript found for this session")

        summary_raw, actions_raw = await _run_parallel(transcript)

        summary, key_points = _parse_summary(summary_raw)
        action_items = _parse_actions(actions_raw)

        ms = (time.perf_counter() - t0) * 1000
        logger.info(f"Meeting minutes generated in {ms:.0f}ms for {session_id[:8]}")

        return MeetingMinutesResp(
            session_id=session_id,
            summary=summary,
            key_points=key_points,
            action_items=action_items,
            total_latency_ms=round(ms, 1),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        raise HTTPException(500, str(e))


async def _run_parallel(transcript: str):
    summary_task = _call_llm(SUMMARY_PROMPT.format(transcript=transcript))
    actions_task = _call_llm(ACTION_ITEMS_PROMPT.format(transcript=transcript))
    return await asyncio.gather(summary_task, actions_task)


async def _call_llm(prompt: str) -> str:
    resp = await _http.post(
        f"{OLLAMA_HOST}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 1024,
            },
        },
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


async def _call_llm_json(prompt: str) -> str:
    resp = await _http.post(
        f"{OLLAMA_HOST}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 128,
            },
        },
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def _parse_summary(raw: str):
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    summary = lines[0] if lines else raw.strip()
    key_points = [
        line.lstrip("-•* ").strip()
        for line in lines[1:]
        if line.startswith(("-", "•", "*", "–"))
    ]
    return summary, key_points[:10]


def _parse_actions(raw: str) -> List[ActionItem]:
    try:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            items = json.loads(m.group())
            return [ActionItem(**item) for item in items if "task" in item]
    except Exception:
        pass
    return []


@app.get("/health")
async def health():
    return {"status": "ok", "llm": LLM_MODEL, "version": "2.0.0"}


async def _prewarm_cache():
    logger.info(f"Pre-warm: starting with {len(_PREWARM_COMMANDS)} commands...")
    success = 0
    for cmd in _PREWARM_COMMANDS:
        try:
            text_key = cmd.strip().lower()
            if _cache_get(text_key):
                continue

            prompt = DRONE_CLASSIFY_PROMPT.format(command=cmd)
            raw = await _call_llm_json(prompt)

            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                confidence = float(data.get("confidence", 0.0))
                if confidence >= 0.85:
                    _cache_set(text_key, {
                        "intent": data.get("intent"),
                        "entities": data.get("entities", {}),
                        "confidence": confidence,
                        "raw_text": cmd,
                        "require_confirmation": bool(data.get("require_confirmation", False)),
                    })
                    success += 1
                    logger.debug(f"  Pre-warm: '{cmd}' -> {data.get('intent')} ({confidence:.2f})")
        except Exception as e:
            logger.warning(f"  Pre-warm failed for '{cmd}': {e}")

    logger.info(f"Pre-warm done: {success}/{len(_PREWARM_COMMANDS)} commands cached.")



DRONE_INTENTS = [
    {"intent": "take_off",       "vi": "Cất cánh",                "requires_entity": "distance_cm (tùy chọn)"},
    {"intent": "land",           "vi": "Hạ cánh",                 "requires_entity": None},
    {"intent": "hover",          "vi": "Giữ vị trí",              "requires_entity": None},
    {"intent": "stop",           "vi": "Dừng lại",                "requires_entity": None},
    {"intent": "emergency_stop", "vi": "Dừng khẩn cấp",          "requires_entity": None},
    {"intent": "return_home",    "vi": "Trở về điểm xuất phát",  "requires_entity": None},
    {"intent": "move_forward",   "vi": "Tiến lên",                "requires_entity": "distance_cm"},
    {"intent": "move_backward",  "vi": "Lùi lại",                 "requires_entity": "distance_cm"},
    {"intent": "move_left",      "vi": "Sang trái",               "requires_entity": "distance_cm"},
    {"intent": "move_right",     "vi": "Sang phải",               "requires_entity": "distance_cm"},
    {"intent": "ascend",         "vi": "Bay lên cao",             "requires_entity": "distance_cm"},
    {"intent": "descend",        "vi": "Hạ xuống",                "requires_entity": "distance_cm"},
    {"intent": "rotate_left",    "vi": "Xoay trái",               "requires_entity": "angle_deg"},
    {"intent": "rotate_right",   "vi": "Xoay phải",               "requires_entity": "angle_deg"},
    {"intent": "follow_target",  "vi": "Bám đuổi mục tiêu",      "requires_entity": "class, color (tùy chọn)"},
    {"intent": "get_battery",    "vi": "Kiểm tra pin",            "requires_entity": None},
    {"intent": "get_altitude",   "vi": "Kiểm tra độ cao",         "requires_entity": None},
]


@app.get("/drone/intents")
async def get_drone_intents():
    return {
        "intents": DRONE_INTENTS,
        "count": len(DRONE_INTENTS),
        "model": LLM_MODEL,
    }


@app.get("/metrics")
async def get_metrics():
    if not _classify_latencies:
        return {"message": "Chưa có dữ liệu. Hãy gọi /drone/classify trước."}
    arr = list(_classify_latencies)
    return {
        "classify_latency_ms": {
            "mean":  round(float(np.mean(arr)), 1),
            "p50":   round(float(np.percentile(arr, 50)), 1),
            "p95":   round(float(np.percentile(arr, 95)), 1),
            "p99":   round(float(np.percentile(arr, 99)), 1),
            "max":   round(float(max(arr)), 1),
            "count": len(arr),
        },
        "cache_size": len(_classify_cache),
        "model": LLM_MODEL,
    }


@app.post("/metrics/reset")
async def reset_metrics():
    _classify_latencies.clear()
    _classify_cache.clear()
    logger.info("Classify latencies metrics and cache have been reset.")
    return {"message": "Metrics and cache reset successful"}


class DroneClassifyReq(BaseModel):
    text: str


class DroneClassifyResp(BaseModel):
    intent: Optional[str] = None
    entities: dict = Field(default_factory=dict)
    confidence: float = 0.0
    raw_text: str = ""
    latency_ms: float = 0.0
    require_confirmation: bool = False
    cached: bool = False


def _cache_get(key: str) -> Optional[dict]:
    if key in _classify_cache:
        _classify_cache.move_to_end(key)
        return _classify_cache[key]
    return None


def _cache_set(key: str, value: dict):
    _classify_cache[key] = value
    _classify_cache.move_to_end(key)
    if len(_classify_cache) > _CACHE_MAX_SIZE:
        _classify_cache.popitem(last=False)


@app.post("/drone/classify", response_model=DroneClassifyResp)
async def drone_classify(req: DroneClassifyReq):
    t0 = time.perf_counter()
    if not req.text.strip():
        raise HTTPException(400, "text is required")

    text_key = req.text.strip().lower()

    cached = _cache_get(text_key)
    if cached:
        ms = (time.perf_counter() - t0) * 1000
        logger.info(f"[Drone Classify CACHE HIT] '{req.text[:40]}' → {cached.get('intent')} ({ms:.0f}ms)")
        return DroneClassifyResp(**cached, cached=True, latency_ms=round(ms, 1))

    try:
        prompt = DRONE_CLASSIFY_PROMPT.format(command=req.text.strip())
        raw_response = await _call_llm_json(prompt)

        json_lines = [line for line in raw_response.splitlines() if not line.strip().startswith("//")]
        json_text = "\n".join(json_lines)

        intent = None
        entities = {}
        confidence = 0.0
        require_confirmation = False

        m = re.search(r"\{.*\}", json_text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            intent = data.get("intent") or None
            entities = data.get("entities", {})
            confidence = float(data.get("confidence", 0.7))
            require_confirmation = bool(data.get("require_confirmation", False))

        ms = (time.perf_counter() - t0) * 1000
        _classify_latencies.append(ms)

        logger.info(
            f"[Drone Classify] '{req.text[:50]}' → intent={intent} "
            f"conf={confidence:.2f} req_confirm={require_confirmation} {ms:.0f}ms"
        )

        result = {
            "intent": intent,
            "entities": entities,
            "confidence": confidence,
            "raw_text": req.text,
            "require_confirmation": require_confirmation,
        }

        if confidence >= 0.85:
            _cache_set(text_key, result)

        return DroneClassifyResp(**result, latency_ms=round(ms, 1))

    except json.JSONDecodeError as e:
        logger.warning(f"LLM returned invalid JSON: {e}\nResponse: {raw_response[:200]}")
        return DroneClassifyResp(
            raw_text=req.text, latency_ms=round((time.perf_counter() - t0) * 1000, 1)
        )
    except Exception as e:
        logger.error(f"Drone classify error: {e}", exc_info=True)
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)
