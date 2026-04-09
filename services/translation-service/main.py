# """
# services/translation-service/main.py
# NLLB-200 Machine Translation.

# POST /translate        → single text
# POST /translate/batch  → list of texts (dùng cho vision pipeline)
# """
# import logging
# import os
# import re
# import time
# from typing import List

# import uvicorn
# from fastapi import FastAPI, HTTPException
# from pydantic import BaseModel
# from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
# import torch

# logger = logging.getLogger("paraline.nllb")

# MODEL_NAME = os.getenv("NLLB_MODEL", "facebook/nllb-200-distilled-1.3B")
# CACHE_DIR  = os.getenv("MODEL_CACHE_DIR", "/models/nllb")

# logger.info(f"Loading NLLB: {MODEL_NAME}")
# _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir=CACHE_DIR)

# # Ép vào Cuda bằng load_in_8bit để nén dung lượng 50%, giúp GPU 4GB VRAM chứa vừa cả ASR và Translate
# _model = AutoModelForSeq2SeqLM.from_pretrained(
#     MODEL_NAME,
#     cache_dir=CACHE_DIR,
#     load_in_8bit=True,
#     device_map="cuda"
# )

# _device = "cuda" if torch.cuda.is_available() else "cpu"
# logger.info(f"✅ NLLB loaded with INT8 on {_device}")

# app = FastAPI(title="Paraline Translation Service")


# class TransReq(BaseModel):
#     text: str
#     src_lang: str = "jpn_Jpan"
#     tgt_lang: str = "vie_Latn"


# class TransResp(BaseModel):
#     translated_text: str
#     src_lang: str
#     tgt_lang: str
#     latency_ms: float


# class BatchReq(BaseModel):
#     texts: List[str]
#     src_lang: str = "jpn_Jpan"
#     tgt_lang: str = "vie_Latn"


# class BatchResp(BaseModel):
#     translations: List[str]
#     latency_ms: float


# @app.post("/translate", response_model=TransResp)
# async def translate(req: TransReq):
#     t0 = time.perf_counter()
#     try:
#         result = _translate(req.text, req.src_lang, req.tgt_lang)
#         ms = (time.perf_counter() - t0) * 1000
#         return TransResp(
#             translated_text=result,
#             src_lang=req.src_lang,
#             tgt_lang=req.tgt_lang,
#             latency_ms=round(ms, 1)
#         )
#     except Exception as e:
#         logger.error(f"Translation error: {e}")
#         raise HTTPException(500, str(e))


# @app.post("/translate/batch", response_model=BatchResp)
# async def translate_batch(req: BatchReq):
#     """Batch translation — critical for vision pipeline (many OCR blocks)."""
#     t0 = time.perf_counter()
#     try:
#         results = [_translate(t, req.src_lang, req.tgt_lang) for t in req.texts]
#         ms = (time.perf_counter() - t0) * 1000
#         return BatchResp(translations=results, latency_ms=round(ms, 1))
#     except Exception as e:
#         raise HTTPException(500, str(e))


# def _translate(text: str, src: str, tgt: str) -> str:
#     """Dịch đoạn văn bản. Dùng generation config nâng cao để kết quả tự nhiên."""
#     if not text.strip():
#         return text

#     _tokenizer.src_lang = src
#     inputs = _tokenizer(
#         text,
#         return_tensors="pt",
#         padding=True,
#         truncation=True,
#         max_length=512,
#     ).to(_device)

#     # Tính độ dài động phòng trường hợp bị cụt câu (Nhật -> Việt dài hơn nhiều)
#     input_len = inputs["input_ids"].shape[1]
#     max_new   = min(int(input_len * 2.5) + 64, 1024)

#     forced_bos = _tokenizer.lang_code_to_id[tgt]

#     with torch.no_grad():
#         outputs = _model.generate(
#             **inputs,
#             forced_bos_token_id=forced_bos,
#             max_new_tokens=max_new,
#             num_beams=1,             # Dò 5 nhánh lấy nhánh tốt nhất (Mượt hơn)
#             # Tắt repetition_penalty & length_penalty vì chúng khiến model không ra được token </s>(EOS)
#             # từ đó dẫn đến liên tục sinh ra các chữ như 't' để cho đủ độ dài.
#             early_stopping=True,
#         )

#     raw = _tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]
#     return _postprocess(raw)


# def _postprocess(text: str) -> str:
#     """Xóa ký tự rác do tokenizer NLLB ném ra."""
#     text = text.replace("▁", " ")
#     text = re.sub(r"__[a-z]{3}_[A-Za-z]{4}__", "", text)
#     # Cắt bỏ các ký tự rác lặp lại ở cuối, ví dụ "t t t t t"
#     text = re.sub(r"(\s*t){4,}.*$", "", text)
#     text = re.sub(r" {2,}", " ", text).strip()
#     return text


# @app.get("/health")
# async def health():
#     return {"status": "ok", "model": MODEL_NAME, "device": _device}


# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8002)



import os
import re
import time
import logging
from typing import List, Union

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# Cấu hình Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("paraline.nllb")

# Cấu hình Model
MODEL_NAME = os.getenv("NLLB_MODEL", "facebook/nllb-200-distilled-600M")
CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "/models/nllb")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

logger.info(f"🚀 Đang tải NLLB: {MODEL_NAME} trên {DEVICE}")

_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir=CACHE_DIR)

# Tối ưu cho GTX 1650: Dùng thẳng FLOAT16.
# Vì 2 model (Qwen 600M + NLLB 600M) cộng lại mới có 2.4GB, dùng FLOAT16 dư sức nằm gọn trong 4GB VRAM
# Tuyệt đối không dùng load_in_8bit vì card đời cũ không có Tensor Core giải mã INT8, khiến tốc độ dịch giật lag từ 3-7s/câu!
_model = AutoModelForSeq2SeqLM.from_pretrained(
    MODEL_NAME,
    cache_dir=CACHE_DIR,
    torch_dtype=torch.float16,
).to(DEVICE)

app = FastAPI(title="Paraline Translation Optimized")

# --- Models Pydantic ---
class TransReq(BaseModel):
    text: str
    src_lang: str = "jpn_Jpan"
    tgt_lang: str = "vie_Latn"

class BatchReq(BaseModel):
    texts: List[str]
    src_lang: str = "jpn_Jpan"
    tgt_lang: str = "vie_Latn"

# --- Logic Dịch Thuật Tối Ưu ---

def _core_translate(texts: List[str], src: str, tgt: str) -> List[str]:
    """Hàm lõi xử lý dịch theo Batch thật sự trên GPU"""
    if not texts:
        return []

    # 1. Setup ngôn ngữ
    _tokenizer.src_lang = src
    forced_bos_id = _tokenizer.lang_code_to_id[tgt]

    # 2. Tokenize (Padding giúp xử lý Batch song song)
    inputs = _tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512
    ).to(DEVICE)

    # 3. Sinh văn bản với cấu hình chống lặp
    with torch.inference_mode(): # Nhanh hơn no_grad
        outputs = _model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_id,
            max_new_tokens=128,    # Giảm mức token vì bản chất câu cũng ko dài quá vậy
            num_beams=1,           # Dùng Greedy Search (nhanh gấp 3 lần beam search)
            repetition_penalty=1.2, # CHỐT chặn hiện tượng lặp "t t t"
            no_repeat_ngram_size=3, # Ngăn lặp lại cụm 3 từ
            early_stopping=True
        )

    # 4. Decode kết quả
    decoded = _tokenizer.batch_decode(outputs, skip_special_tokens=True)
    return [_postprocess(t) for t in decoded]

def _postprocess(text: str) -> str:
    """Làm sạch rác sau khi dịch"""
    text = text.replace("▁", " ")
    # Xóa các code ngôn ngữ thừa nếu có
    text = re.sub(r"__[a-z]{3}_[A-Za-z]{4}__", "", text)
    # Xử lý khoảng trắng thừa
    text = re.sub(r"\s+", " ", text).strip()
    return text

# --- Endpoints ---

@app.post("/translate")
async def translate(req: TransReq):
    t0 = time.perf_counter()
    try:
        # Xử lý như một batch có 1 phần tử để dùng chung logic
        results = _core_translate([req.text], req.src_lang, req.tgt_lang)
        ms = (time.perf_counter() - t0) * 1000
        return {
            "translated_text": results[0],
            "latency_ms": round(ms, 1)
        }
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(500, str(e))

@app.post("/translate/batch")
async def translate_batch(req: BatchReq):
    """Dịch batch cực nhanh cho Vision Pipeline"""
    t0 = time.perf_counter()
    try:
        # Lọc bỏ text trống để tránh lỗi model
        valid_texts = [t if t.strip() else " " for t in req.texts]
        results = _core_translate(valid_texts, req.src_lang, req.tgt_lang)
        
        ms = (time.perf_counter() - t0) * 1000
        return {
            "translations": results,
            "latency_ms": round(ms, 1)
        }
    except Exception as e:
        logger.error(f"Batch Error: {e}")
        raise HTTPException(500, str(e))

@app.get("/health")
async def health():
    return {"status": "ok", "device": DEVICE, "vram_allocated": f"{torch.cuda.memory_allocated() / 1024**2:.1f}MB"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)