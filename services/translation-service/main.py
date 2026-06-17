import os
import re
import time
import logging
from typing import List

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uav_drone.nllb")

MODEL_NAME = os.getenv("NLLB_MODEL", "facebook/nllb-200-distilled-600M")
CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "/models/nllb")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

logger.info(f"Loading NLLB model: {MODEL_NAME} on {DEVICE}")

_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir=CACHE_DIR)

_model = AutoModelForSeq2SeqLM.from_pretrained(
    MODEL_NAME,
    cache_dir=CACHE_DIR,
    torch_dtype=torch.float16,
).to(DEVICE)

app = FastAPI(title="UAV_drone_ICN Translation")

class TransReq(BaseModel):
    text: str
    src_lang: str = "jpn_Jpan"
    tgt_lang: str = "vie_Latn"


class BatchReq(BaseModel):
    texts: List[str]
    src_lang: str = "jpn_Jpan"
    tgt_lang: str = "vie_Latn"


def _core_translate(texts: List[str], src: str, tgt: str) -> List[str]:
    if not texts:
        return []

    _tokenizer.src_lang = src
    forced_bos_id = _tokenizer.lang_code_to_id[tgt]

    inputs = _tokenizer(
        texts, return_tensors="pt", padding=True, truncation=True, max_length=512
    ).to(DEVICE)

    with torch.inference_mode():
        outputs = _model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_id,
            max_new_tokens=128,
            num_beams=1,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
            early_stopping=True,
        )

    decoded = _tokenizer.batch_decode(outputs, skip_special_tokens=True)
    return [_postprocess(t) for t in decoded]


def _postprocess(text: str) -> str:
    text = text.replace("▁", " ")
    text = re.sub(r"__[a-z]{3}_[A-Za-z]{4}__", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@app.post("/translate")
async def translate(req: TransReq):
    t0 = time.perf_counter()
    try:
        results = _core_translate([req.text], req.src_lang, req.tgt_lang)
        ms = (time.perf_counter() - t0) * 1000
        return {"translated_text": results[0], "latency_ms": round(ms, 1)}
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(500, str(e))


@app.post("/translate/batch")
async def translate_batch(req: BatchReq):
    t0 = time.perf_counter()
    try:
        valid_texts = [t if t.strip() else " " for t in req.texts]
        results = _core_translate(valid_texts, req.src_lang, req.tgt_lang)

        ms = (time.perf_counter() - t0) * 1000
        return {"translations": results, "latency_ms": round(ms, 1)}
    except Exception as e:
        logger.error(f"Batch Error: {e}")
        raise HTTPException(500, str(e))


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "vram_allocated": f"{torch.cuda.memory_allocated() / 1024**2:.1f}MB" if DEVICE == "cuda" else "N/A",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
