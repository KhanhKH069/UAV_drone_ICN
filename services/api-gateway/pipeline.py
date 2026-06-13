import asyncio
import logging
import os
import time

import httpx
from fastapi import WebSocket

logger = logging.getLogger("paraline.pipeline")

WHISPERLIVE_URL = os.getenv("WHISPERLIVE_URL", "http://whisperlive:8001")
TRANSLATION_URL = os.getenv("TRANSLATION_URL", "http://translation-service:8002")
COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://transcription-collector:8006")

_client = httpx.AsyncClient(timeout=300.0, limits=httpx.Limits(max_connections=50))

class AudioPipeline:

    def __init__(self):
        self._last_listening_text = {}

    async def process(
        self,
        frame: dict,
        session_id: str,
        direction: str,
        ws: WebSocket,
        is_final: bool = True,
    ):
        t0 = time.perf_counter()
        try:
            audio_b64 = frame.get("data", "")
            src_lang = frame.get("src_lang", "eng_Latn")
            tgt_lang = frame.get("tgt_lang", "vie_Latn")

            if not audio_b64:
                return

            asr = await _client.post(
                f"{WHISPERLIVE_URL}/transcribe",
                json={
                    "audio_b64": audio_b64,
                    "language": src_lang,
                    "vad_filter": True,
                },
            )
            asr.raise_for_status()
            original_text = asr.json().get("text", "").strip()

            if not is_final:
                last_text = self._last_listening_text.get(session_id, "")
                if original_text == last_text:
                    return

                self._last_listening_text[session_id] = original_text

                await ws.send_json({"type": "listening", "text": f"{original_text}"})
                return

            self._last_listening_text.pop(session_id, None)
            await ws.send_json(
                {
                    "type": "listening",
                    "text": f"[{src_lang[:2].upper()}] {original_text}",
                }
            )

            nllb = await _client.post(
                f"{TRANSLATION_URL}/translate",
                json={
                    "text": original_text,
                    "src_lang": src_lang,
                    "tgt_lang": tgt_lang,
                },
            )
            nllb.raise_for_status()
            translated_text = nllb.json().get("translated_text", "")

            latency_ms = (time.perf_counter() - t0) * 1000

            if direction == "inbound":
                await ws.send_json(
                    {
                        "type": "inbound_result",
                        "original_text": original_text,
                        "translated_text": translated_text,
                        "audio_b64": None,
                        "sample_rate": 22050,
                        "latency_ms": round(latency_ms, 1),
                    }
                )
                await ws.send_json(
                    {
                        "type": "subtitle",
                        "text": translated_text,
                        "latency_ms": round(latency_ms, 1),
                    }
                )

            elif direction == "outbound":
                await ws.send_json(
                    {
                        "type": "outbound_result",
                        "original_text": original_text,
                        "translated_text": translated_text,
                        "tgt_lang": tgt_lang,
                        "latency_ms": round(latency_ms, 1),
                    }
                )

            logger.info(
                f"[{session_id[:8]}] {direction} {latency_ms:.0f}ms "
                f"| {original_text[:40]} → {translated_text[:40]}"
            )

            asyncio.create_task(
                self._store_segment(
                    session_id,
                    direction,
                    original_text,
                    translated_text,
                    src_lang,
                    tgt_lang,
                    latency_ms,
                )
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Pipeline HTTP {e.response.status_code}: {e}")
            await ws.send_json(
                {"type": "error", "message": f"Service error: {e.response.status_code}"}
            )
        except Exception as e:
            logger.error(f"Pipeline error [{session_id[:8]}]: {e}", exc_info=True)
            await ws.send_json({"type": "error", "message": str(e)})

    async def _store_segment(
        self,
        session_id: str,
        direction: str,
        original: str,
        translated: str,
        src_lang: str,
        tgt_lang: str,
        latency_ms: float,
    ):
        try:
            await _client.post(
                f"{COLLECTOR_URL}/segments",
                json={
                    "session_id": session_id,
                    "direction": direction,
                    "original_text": original,
                    "translated_text": translated,
                    "src_lang": src_lang,
                    "tgt_lang": tgt_lang,
                    "latency_ms": latency_ms,
                },
            )
        except Exception:
            pass
