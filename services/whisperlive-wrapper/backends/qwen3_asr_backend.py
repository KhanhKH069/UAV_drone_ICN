"""
services/whisperlive-wrapper/backends/qwen3_asr_backend.py
Backend dùng Qwen3-ASR-0.6B (hoặc 1.7B).
"""
import logging
import os
import time
from typing import Optional

import numpy as np
import dotenv
import torch
from qwen_asr import Qwen3ASRModel
from .base import BaseASRBackend, ASRResult

dotenv.load_dotenv()

logger = logging.getLogger("paraline.asr.qwen3")

# Map NLLB code và Whisper-style code → tên ngôn ngữ Qwen3-ASR hiểu
_NLLB_TO_QWEN_LANG = {
    # NLLB codes (mới, do pipeline gửi lên)
    "jpn_Jpan": "Japanese",
    "eng_Latn": "English",
    "vie_Latn": "Vietnamese",
    "kor_Hang": "Korean",
    "zho_Hans": "Chinese",
    "fra_Latn": "French",
    "deu_Latn": "German",
    "spa_Latn": "Spanish",
    # Whisper-style codes (cũ, do pipeline cũ trong api-gateway container gửi lên)
    "ja": "Japanese",
    "en": "English",
    "vi": "Vietnamese",
    "ko": "Korean",
    "zh": "Chinese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
}

# Map tên ngôn ngữ Qwen trả về → Whisper-style code
_QWEN_LANG_TO_CODE = {
    "japanese": "ja", "english": "en", "vietnamese": "vi",
    "korean": "ko", "chinese": "zh", "mandarin": "zh", "cantonese": "zh",
    "french": "fr", "german": "de", "spanish": "es",
}

# Chỉ giữ kết quả có ngôn ngữ trong danh sách này (lọc hallucination tiếng khác)
# Nếu language được chỉ định cụ thể (không phải auto), luôn giữ kết quả.
_ALLOWED_LANGS_AUTO = {"en"}  # Cho phép Anh, Nhật, Việt

# Các câu rác (hallucination) thường gặp khi trời im lặng
_HALLUCINATION_KEYWORDS = [
    "Không nghe thấy gì !!!!"
]


class Qwen3ASRBackend(BaseASRBackend):
    def __init__(self):

        model_name = os.getenv("QWEN_ASR_MODEL",  "Qwen/Qwen3-ASR-0.6B")
        device     = os.getenv("WHISPER_DEVICE",  "cuda")
        model_dir  = os.getenv("MODEL_CACHE_DIR", "/models/qwen_asr")

        # Sửa thành float16 vì GTX 1650 (Turing) KHÔNG HỖ TRỢ bfloat16, gây lỗi hoặc chậm rì
        dtype = torch.float16 if device == "cuda" else torch.float32
        print(f"⏳ [Qwen3-ASR] Đang tải model {model_name} trên {device} (dtype={dtype})...", flush=True)

        self._model = Qwen3ASRModel.from_pretrained(
            model_name,
            dtype=dtype,
            device_map=device,
            max_inference_batch_size=4,
            max_new_tokens=512,
            cache_dir=model_dir,
        )
        print(f'device: {device}, dtype: {dtype}', flush=True)
        print(f"✅ [Qwen3-ASR] Model {model_name} đã tải xong!", flush=True)

    @property
    def name(self) -> str:
        return "Qwen3-ASR"

    def transcribe(
        self,
        audio_np: np.ndarray,
        language: Optional[str],
        sample_rate: int = 16000,
        beam_size: int = 5,       # Không dùng nhưng giữ tương thích interface
        vad_filter: bool = True,  # Không dùng nhưng giữ tương thích interface
    ) -> ASRResult:
        t0 = time.perf_counter()

        # Chuyển NLLB code → tên ngôn ngữ Qwen3-ASR
        if language is None or language == "auto":
            qwen_language = None  # Auto-detect
        else:
            qwen_language = _NLLB_TO_QWEN_LANG.get(language)
            if qwen_language is None:
                # Thử dùng trực tiếp nếu đã là tên đầy đủ (VD: "Japanese")
                qwen_language = language if language[0].isupper() else None

        duration_sec = len(audio_np) / sample_rate
        print(
            f"🎧 [Qwen3-ASR] {len(audio_np)} samples ({duration_sec:.2f}s) "
            f"| Lang: {qwen_language or 'auto'}",
            flush=True,
        )

        results = self._model.transcribe(
            audio=(audio_np, sample_rate),
            language=qwen_language,
        )

        result = results[0]
        text = result.text.strip() if result.text else ""

        detected_lang_full = (result.language or "").lower()
        # Fallback về ngôn ngữ được yêu cầu nếu model không detect được
        if not detected_lang_full:
            detected_lang_code = _NLLB_TO_QWEN_LANG.get(language or "", {})
            detected_lang_code = {"Japanese": "ja", "English": "en", "Vietnamese": "vi"}.get(
                detected_lang_code, "und"  # "und" = undetermined
            )
        else:
            detected_lang_code = _QWEN_LANG_TO_CODE.get(detected_lang_full, detected_lang_full[:2] or "und")

        # Lọc ngôn ngữ không trong danh sách — CHỆ khi auto-detect
        # Nếu đã chỉ định cụ thể (VD: jpn_Jpan), giữ kết quả dù Qwen detect ra gì
        is_auto = language is None or language == "auto"
        if is_auto and detected_lang_code not in _ALLOWED_LANGS_AUTO:
            print(
                f"⚠️ [Qwen3-ASR] Lọc tiếng '{detected_lang_full}' (không nằm trong allowed: {_ALLOWED_LANGS_AUTO})",
                flush=True
            )
            text = ""

        # Lọc hallucination
        # 1. Theo từ khóa
        if any(kw in text.lower() for kw in _HALLUCINATION_KEYWORDS):
            print(f"🚫 [Qwen3-ASR] Hallucination detected (keyword): '{text}'", flush=True)
            text = ""
        
        # 2. Theo độ dài (nếu audio > 1s mà text < 2 ký tự thì thường là junk/hallucination)
        if text and len(text) < 2 and duration_sec > 1.5:
            # Ngoại lệ cho các từ xác nhận ngắn như "Ah", "Oh" (nếu cần)
            # Nhưng đa phần 1 ký tự mà audio dài là ảo.
            print(f"🚫 [Qwen3-ASR] Hallucination detected (too short): '{text}'", flush=True)
            text = ""

        ms = (time.perf_counter() - t0) * 1000
        print(f"🟢 [Qwen3-ASR] Lang: {detected_lang_full} | {ms:.0f}ms | '{text}'", flush=True)

        return ASRResult(
            text=text,
            language=detected_lang_code,
            latency_ms=round(ms, 1),
            segments=[],
        )
