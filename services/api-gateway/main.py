"""
services/api-gateway/main.py
Paraline MSAgent — API Gateway
Vexa pattern: api-gateway routes requests + manages WebSocket sessions.

REST  :  http://host:8056
WS    :  ws://host:8765/ws/audio/{session_id}?direction=inbound|outbound
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

from routers.sessions import router as sessions_router
from routers.images   import router as images_router
from routers.agent    import router as agent_router
from routers.mock     import router as mock_router
from pipeline import AudioPipeline
from connection_manager import ConnectionManager

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("paraline.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🟠 Paraline MSAgent API Gateway starting...")
    logger.info(f"  WhisperLive  → {os.getenv('WHISPERLIVE_URL')}")
    logger.info(f"  Translation  → {os.getenv('TRANSLATION_URL')}")
    logger.info(f"  TTS          → {os.getenv('TTS_URL')}")
    logger.info(f"  Vision       → {os.getenv('VISION_URL')}")
    logger.info(f"  Agent        → {os.getenv('AGENT_URL')}")
    yield
    logger.info("Paraline MSAgent shutting down.")


app = FastAPI(
    title="Paraline MSAgent API",
    description="VMG Internal AI Translation Server — 100% offline on VMG_STAFF",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict to VMG_STAFF subnet in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers
app.include_router(sessions_router, prefix="/sessions", tags=["Sessions"])
app.include_router(images_router,   prefix="/translate", tags=["Image Translation"])
app.include_router(agent_router,    prefix="/agent",     tags=["Meeting Agent"])
app.include_router(mock_router,     prefix="/mock",      tags=["Mock Testing"])

# Singletons
connection_manager = ConnectionManager()
pipeline = AudioPipeline()


# ─────────────────────────────────────────────
# WebSocket — Audio Stream
# Vexa pattern: WhisperLive WebSocket endpoint
# ─────────────────────────────────────────────

@app.websocket("/ws/audio/{session_id}")
async def ws_audio_endpoint(
    websocket: WebSocket,
    session_id: str,
    direction: str = Query("inbound", regex="^(inbound|outbound)$"),
    api_key: str = Query(""),
):
    """
    WebSocket audio stream endpoint.

    Frame protocol:
      Client → Server:
        { "type": "audio_chunk", "data": "<b64 pcm>",
          "src_lang": "jpn_Jpan", "tgt_lang": "vie_Latn" }

      Server → Client (inbound):
        { "type": "subtitle",       "text": "...", "latency_ms": 850 }
        { "type": "inbound_result", "translated_text": "...",
          "audio_b64": "<b64 wav>", "latency_ms": 900 }

      Server → Client (outbound):
        { "type": "outbound_result", "original_text": "...",
          "translated_text": "...", "push_to_teams": true }
    """
    # Auth check
    if api_key != os.getenv("CLIENT_API_KEY", ""):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await connection_manager.connect(websocket, session_id, direction)
    logger.info(f"WS connected: session={session_id[:8]} direction={direction}")

    queue = asyncio.Queue()

    async def _worker():
        while True:
            frame = await queue.get()
            if frame is None:
                break
            try:
                # Await sequentially to avoid out-of-order execution and overwhelming the backend
                is_final = frame.get("is_final", True)
                await pipeline.process(frame, session_id, direction, websocket, is_final=is_final)
            except Exception as e:
                logger.error(f"Pipeline error in worker: {e}")
            finally:
                queue.task_done()

    worker_task = asyncio.create_task(_worker())

    try:
        while True:
            frame = await websocket.receive_json()
            await queue.put(frame)
    except WebSocketDisconnect:
        logger.info(f"WS disconnected: session={session_id[:8]}")
    except Exception as e:
        logger.error(f"WS error [{session_id[:8]}]: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        await queue.put(None) # Signal worker to stop
        # Optionally await worker_task completion, or just let it die.
        # await worker_task
        connection_manager.disconnect(websocket, session_id)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "paraline-api-gateway",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8056,
        ws="websockets",
        log_level="info",
    )
