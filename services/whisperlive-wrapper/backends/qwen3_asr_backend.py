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

logger = logging.getLogger("uav_drone.asr.qwen3")

_NLLB_TO_QWEN_LANG = {
    "jpn_Jpan": "Japanese",
    "eng_Latn": "English",
    "vie_Latn": "Vietnamese",
    "kor_Hang": "Korean",
    "zho_Hans": "Chinese",
    "fra_Latn": "French",
    "deu_Latn": "German",
    "spa_Latn": "Spanish",
    "ja": "Japanese",
    "en": "English",
    "vi": "Vietnamese",
    "ko": "Korean",
    "zh": "Chinese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
}

_QWEN_LANG_TO_CODE = {
    "japanese": "ja",
    "english": "en",
    "vietnamese": "vi",
    "korean": "ko",
    "chinese": "zh",
    "mandarin": "zh",
    "cantonese": "zh",
    "french": "fr",
    "german": "de",
    "spanish": "es",
}

_ALLOWED_LANGS_AUTO = {"en"}

_HALLUCINATION_KEYWORDS = ["Không nghe thấy gì !!!!"]


class Qwen3ASRBackend(BaseASRBackend):
    def __init__(self):
        model_name = os.getenv("QWEN_ASR_MODEL", "Qwen/Qwen3-ASR-0.6B")
        device = os.getenv("WHISPER_DEVICE", "cuda")
        model_dir = os.getenv("MODEL_CACHE_DIR", "/models/qwen_asr")
        dtype = torch.float16 if device == "cuda" else torch.float32
        self._model = Qwen3ASRModel.from_pretrained(
            model_name,
            dtype=dtype,
            device_map=device,
            max_inference_batch_size=4,
            max_new_tokens=512,
            cache_dir=model_dir,
        )
        logger.info(f"Qwen3-ASR model {model_name} loaded on {device} (dtype={dtype}).")

    @property
    def name(self) -> str:
        return "Qwen3-ASR"

    def transcribe(
        self,
        audio_np: np.ndarray,
        language: Optional[str],
        sample_rate: int = 16000,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> ASRResult:
        t0 = time.perf_counter()

        if language is None or language == "auto":
            qwen_language = None
        else:
            qwen_language = _NLLB_TO_QWEN_LANG.get(language)
            if qwen_language is None:
                qwen_language = language if language[0].isupper() else None

        duration_sec = len(audio_np) / sample_rate

        results = self._model.transcribe(
            audio=(audio_np, sample_rate),
            language=qwen_language,
        )

        result = results[0]
        text = result.text.strip() if result.text else ""

        detected_lang_full = (result.language or "").lower()
        if not detected_lang_full:
            detected_lang_code = _NLLB_TO_QWEN_LANG.get(language or "", {})
            detected_lang_code = {
                "Japanese": "ja",
                "English": "en",
                "Vietnamese": "vi",
            }.get(
                detected_lang_code,
                "und",
            )
        else:
            detected_lang_code = _QWEN_LANG_TO_CODE.get(
                detected_lang_full, detected_lang_full[:2] or "und"
            )

        is_auto = language is None or language == "auto"
        if is_auto and detected_lang_code not in _ALLOWED_LANGS_AUTO:
            logger.debug(f"Filtering lang '{detected_lang_full}' (not in {_ALLOWED_LANGS_AUTO})")
            text = ""

        if any(kw in text.lower() for kw in _HALLUCINATION_KEYWORDS):
            logger.warning(f"Hallucination detected (keyword): '{text}'")
            text = ""

        if text and len(text) < 2 and duration_sec > 1.5:
            logger.warning(f"Hallucination detected (too short): '{text}'")
            text = ""

        ms = (time.perf_counter() - t0) * 1000
        logger.info(f"Qwen3-ASR | lang={detected_lang_full} | {ms:.0f}ms | '{text[:50]}'")

        return ASRResult(
            text=text,
            language=detected_lang_code,
            latency_ms=round(ms, 1),
            segments=[],
        )
