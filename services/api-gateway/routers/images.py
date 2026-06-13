import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
_http = httpx.AsyncClient(timeout=20.0)
VISION_URL = os.getenv("VISION_URL", "http://vision-service:8004")


class ImageTranslateReq(BaseModel):
    session_id: str
    image_b64: str
    src_lang: str = "jpn_Jpan"
    tgt_lang: str = "vie_Latn"
    font_auto_resize: bool = True


@router.post("/image")
async def translate_image(req: ImageTranslateReq):

    try:
        resp = await _http.post(f"{VISION_URL}/translate/image", json=req.model_dump())
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
