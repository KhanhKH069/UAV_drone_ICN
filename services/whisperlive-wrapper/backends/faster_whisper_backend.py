import logging
import os
import time
from typing import Optional

import numpy as np

from .base import BaseASRBackend, ASRResult

logger = logging.getLogger("paraline.asr.faster_whisper")

_ALLOWED_LANGS = {"ja", "en", "vi"}

_NLLB_TO_WHISPER = {
    "jpn_Jpan": "ja",
    "eng_Latn": "en",
    "vie_Latn": "vi",
    "kor_Hang": "ko",
    "zho_Hans": "zh",
    "fra_Latn": "fr",
    "deu_Latn": "de",
    "spa_Latn": "es",
}

_HALLUCINATION_KW = [
    "subscribe", "đăng ký kênh", "cảm ơn bạn đã xem",
    "like và subscribe", "xin chào các bạn",
]


class FasterWhisperBackend(BaseASRBackend):
    def __init__(self):
        from faster_whisper import WhisperModel

        model_size = os.getenv("WHISPER_MODEL", "large-v3-turbo")
        device = os.getenv("WHISPER_DEVICE", "cuda")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
        model_dir = os.getenv("MODEL_CACHE_DIR", "/models/whisper")

        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=model_dir,
        )
        logger.info(f"Faster Whisper model {model_size} loaded on {device}.")

    @property
    def name(self) -> str:
        return "Faster Whisper"

    def transcribe(
        self,
        audio_np: np.ndarray,
        language: Optional[str],
        sample_rate: int = 16000,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> ASRResult:
        t0 = time.perf_counter()

        whisper_lang = _NLLB_TO_WHISPER.get(language, language) if language else None
        if whisper_lang == "auto":
            whisper_lang = None

        duration_sec = len(audio_np) / sample_rate

        segments_gen, info = self._model.transcribe(
            audio_np,
            language=whisper_lang,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200},
            condition_on_previous_text=False,
            initial_prompt="Lệnh điều khiển máy bay không người lái: cất cánh, hạ cánh, tiến lên, lùi lại, bay lên, hạ xuống, xoay trái, xoay phải, dừng khẩn cấp, quay về nhà.",
        )

        segs = list(segments_gen)

        valid_segs = [s for s in segs if s.no_speech_prob < 0.8]
        text = " ".join(s.text.strip() for s in valid_segs).strip()

        if whisper_lang is None and info.language not in _ALLOWED_LANGS:
            logger.debug(f"Filtering unexpected language: {info.language}")
            text = ""

        if any(kw in text.lower() for kw in _HALLUCINATION_KW):
            text = ""

        ms = (time.perf_counter() - t0) * 1000
        logger.info(f"Faster Whisper | lang={info.language} | {ms:.0f}ms | '{text[:50]}'")

        return ASRResult(
            text=text,
            language=info.language,
            latency_ms=round(ms, 1),
            segments=[{"start": s.start, "end": s.end, "text": s.text} for s in segs],
        )
