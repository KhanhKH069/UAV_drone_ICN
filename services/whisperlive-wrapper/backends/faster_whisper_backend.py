"""
services/whisperlive-wrapper/backends/faster_whisper_backend.py
Backend dùng Faster Whisper (mặc định cũ).
"""
import logging
import os
import time
from typing import Optional

import numpy as np

from .base import BaseASRBackend, ASRResult

logger = logging.getLogger("paraline.asr.faster_whisper")

# Các ngôn ngữ cho phép (tránh hallucination)
_ALLOWED_LANGS = {"ja", "en", "vi"}

# Map NLLB code → Whisper code
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


class FasterWhisperBackend(BaseASRBackend):
    def __init__(self):
        from faster_whisper import WhisperModel

        model_size   = os.getenv("WHISPER_MODEL",        "large-v3")
        device       = os.getenv("WHISPER_DEVICE",       "cuda")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
        model_dir    = os.getenv("MODEL_CACHE_DIR",      "/models/whisper")

        print(f"⏳ [Faster Whisper] Đang tải model {model_size} trên {device}...", flush=True)
        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=model_dir,
        )
        print(f"✅ [Faster Whisper] Model {model_size} đã tải xong!", flush=True)

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

        # Chuyển NLLB code → Whisper code nếu cần
        whisper_lang = _NLLB_TO_WHISPER.get(language, language) if language else None
        if whisper_lang == "auto":
            whisper_lang = None

        duration_sec = len(audio_np) / sample_rate
        print(
            f"🎧 [Faster Whisper] {len(audio_np)} samples ({duration_sec:.2f}s) "
            f"| Lang: {whisper_lang or 'auto'}",
            flush=True,
        )

        segments_gen, info = self._model.transcribe(
            audio_np,
            language=whisper_lang,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 400},
            condition_on_previous_text=False,
            initial_prompt="This is a business meeting conversation. Please ignore background noise.",
        )

        segs = list(segments_gen)
        for s in segs:
            print(f"📊 [Faster Whisper DEBUG] '{s.text}' | no_speech_prob: {s.no_speech_prob:.2f}", flush=True)

        valid_segs = [s for s in segs if s.no_speech_prob < 0.8]
        text = " ".join(s.text.strip() for s in valid_segs).strip()

        # Lọc ngôn ngữ ngoài danh sách — CHỈ khi auto-detect
        # (nếu đã chỉ định lang cụ thể, Whisper đã ép rồi, không cần lọc thêm)
        if whisper_lang is None and info.language not in _ALLOWED_LANGS:
            logger.debug(f"Filtering unexpected language: {info.language}")
            text = ""

        # Lọc hallucination
        if any(kw in text.lower() for kw in ["subscribe", "đăng ký kênh"]):
            text = ""

        ms = (time.perf_counter() - t0) * 1000
        print(f"🟢 [Faster Whisper] Lang: {info.language} | {ms:.0f}ms | '{text}'", flush=True)

        return ASRResult(
            text=text,
            language=info.language,
            latency_ms=round(ms, 1),
            segments=[{"start": s.start, "end": s.end, "text": s.text} for s in segs],
        )
