import logging
import os
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("paraline.mock")

TRANSLATION_URL = os.getenv("TRANSLATION_URL", "http://translation-service:8002")

_http = httpx.AsyncClient(timeout=15.0)

MOCK_EN_TEXTS = [
    "Hello everyone, today we will discuss the project timeline.",
    "The development team has finished the first phase of implementation.",
    "We need to review the requirements before the next sprint.",
    "Please share your feedback on the current design proposal.",
    "The meeting will wrap up with a summary of action items.",
]

MOCK_JA_TEXTS = [
    "皆さん、こんにちは。本日はプロジェクトの進捗についてお話しします。",
    "開発チームは最初のフェーズを完了しました。",
    "次のスプリントの前に要件を確認する必要があります。",
    "現在の設計提案に関するフィードバックを共有してください。",
    "会議はアクションアイテムのまとめで終わります。",
]

class MockInjectReq(BaseModel):
    session_id: str
    src_lang: str = "eng_Latn"
    tgt_lang: str = "vie_Latn"

class MockInjectResp(BaseModel):
    results: list
    latency_ms: float

@router.post("/inject", response_model=MockInjectResp)
async def mock_inject(req: MockInjectReq):
    texts = MOCK_EN_TEXTS if "eng" in req.src_lang else MOCK_JA_TEXTS
    results = []
    t0 = time.perf_counter()

    for text in texts:
        try:
            r = await _http.post(
                f"{TRANSLATION_URL}/translate",
                json={
                    "text": text,
                    "src_lang": req.src_lang,
                    "tgt_lang": req.tgt_lang,
                },
            )
            r.raise_for_status()
            translated = r.json().get("translated_text", "")
            results.append({"original": text, "translated": translated})
            logger.info(f"[mock] {text[:40]} → {translated[:40]}")
        except Exception as e:
            logger.error(f"[mock] translate error: {e}")
            results.append({"original": text, "translated": f"[Error: {e}]"})

    ms = (time.perf_counter() - t0) * 1000
    return MockInjectResp(results=results, latency_ms=round(ms, 1))
