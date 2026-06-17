import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.drone import router as drone_router
from routers.auth  import router as auth_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("uav_drone.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("UAV_drone_ICN API Gateway starting...")
    logger.info(f"  WhisperLive  -> {os.getenv('WHISPERLIVE_URL')}")
    logger.info(f"  Agent        -> {os.getenv('AGENT_URL')}")
    yield
    logger.info("UAV_drone_ICN Gateway shutting down.")


app = FastAPI(
    title="UAV_drone_ICN API Gateway",
    description="UAV Voice Control System — Edge AI, 100% offline",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,   prefix="/auth",  tags=["Authentication"])
app.include_router(drone_router,  tags=["Drone UAV"])


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "uav-drone-icn-gateway",
        "version": "2.0.0",
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8056,
        ws="websockets",
        log_level="info",
    )
