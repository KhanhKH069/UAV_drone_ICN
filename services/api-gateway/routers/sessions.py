import os
import uuid
from typing import Optional
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
_http = httpx.AsyncClient(timeout=10.0)
COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://transcription-collector:8006")

class SessionCreateReq(BaseModel):
    teams_meeting_id: Optional[str] = None
    teams_chat_id: Optional[str] = None
    inbound_src_lang: str = "jpn_Jpan"
    outbound_tgt_lang: str = "jpn_Jpan"

@router.post("/")
async def create_session(req: SessionCreateReq):
    session_id = str(uuid.uuid4())
    await _http.post(
        f"{COLLECTOR_URL}/sessions",
        json={
            "session_id": session_id,
            "teams_chat_id": req.teams_chat_id,
            "inbound_src_lang": req.inbound_src_lang,
            "outbound_tgt_lang": req.outbound_tgt_lang,
        },
    )
    return {"session_id": session_id, "status": "created"}

@router.get("/{session_id}")
async def get_session(session_id: str):
    resp = await _http.get(f"{COLLECTOR_URL}/sessions/{session_id}")
    if resp.status_code == 404:
        raise HTTPException(404, "Session not found")
    return resp.json()

@router.delete("/{session_id}")
async def end_session(session_id: str):
    await _http.patch(
        f"{COLLECTOR_URL}/sessions/{session_id}", json={"status": "finished"}
    )
    return {"session_id": session_id, "status": "finished"}
