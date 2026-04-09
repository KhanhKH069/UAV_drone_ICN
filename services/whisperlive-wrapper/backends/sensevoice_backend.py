"""
services/whisperlive-wrapper/backends/sensevoice_backend.py
Backend dùng SenseVoice-Small của Alibaba FunASR.
"""
import logging
import os
import time
from typing import Optional
import re

import numpy as np

from .base import BaseASRBackend, ASRResult

# Ép ModelScope tiết kiệm bộ nhớ, lưu vào Volume vĩnh viễn của Docker
os.environ["MODELSCOPE_CACHE"] = os.getenv("MODELSCOPE_CACHE", "/models")

logger = logging.getLogger("paraline.asr.sensevoice")
 
# NLLB code -> SenseVoice code
_NLLB_TO_SV = {
    "jpn_Jpan": "ja",
    "eng_Latn": "en",
    "kor_Hang": "ko",
    "zho_Hans": "zh",
    "vie_Latn": "auto",  # SenseVoice ko train explicitly Tiếng Việt nên phải để auto
}

class SenseVoiceBackend(BaseASRBackend):
    def __init__(self):
        try:
            from funasr import AutoModel
        except ImportError:
            raise ImportError("Không tìm thấy thư viện 'funasr'. Lệnh cài: pip install funasr modelscope torchaudio")

        device = os.getenv("WHISPER_DEVICE", "cuda:0") # Tái sử dụng env của Whisper
        model_id = os.getenv("SENSEVOICE_MODEL", "iic/SenseVoiceSmall")
        
        print(f"⏳ [SenseVoice] Đang tải {model_id} trên {device}...", flush=True)
        self._model = AutoModel(
            model=model_id,
            trust_remote_code=True,
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device=device,
        )
        print(f"✅ [SenseVoice] Model {model_id} đã tải xong!", flush=True)

    @property
    def name(self) -> str:
        return "SenseVoice-Small"

    def transcribe(
        self,
        audio_np: np.ndarray,
        language: Optional[str],
        sample_rate: int = 16000,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> ASRResult:
        t0 = time.perf_counter()

        # Map language cho SenseVoice, mặc định là auto
        sv_lang = _NLLB_TO_SV.get(language, language) if language else "auto"
        if sv_lang not in ["ja", "en", "ko", "zh", "yue", "auto"]:
            sv_lang = "auto"

        duration_sec = len(audio_np) / sample_rate
        print(
            f"🎧 [SenseVoice] {len(audio_np)} samples ({duration_sec:.2f}s) "
            f"| Lang (in): {sv_lang}",
            flush=True,
        )

        try:
            # SenseVoice expect input shape or path, NumPy array is supported directly in funasr AutoModel if shape is correct
            # Usually input expects 16kHz float32
            res = self._model.generate(
                input=audio_np,
                cache={},
                language=sv_lang,
                use_itn=True,
                batch_size_s=60
            )
            
            raw_text = res[0]["text"] if len(res) > 0 and "text" in res[0] else ""
            
            # Format của SenseVoice sẽ có dạng: <|zh|><|NEUTRAL|><|Speech|> Xin chào mọi người
            # Cần Regex để bóc tác language và clean text
            clean_text = re.sub(r"<\|.*?\|>", "", raw_text).strip()
            
            detected_lang = sv_lang
            lang_match = re.search(r"<\|([^|]+)\|>", raw_text)
            if lang_match:
                detected_lang = lang_match.group(1)

            text = clean_text

        except Exception as e:
            logger.error(f"[SenseVoice Error]: {e}")
            text = ""
            detected_lang = "auto"
            import traceback
            traceback.print_exc()

        ms = (time.perf_counter() - t0) * 1000
        print(f"🟢 [SenseVoice] Lang: {detected_lang} | {ms:.0f}ms | '{text}'", flush=True)

        return ASRResult(
            text=text,
            language=detected_lang,
            latency_ms=round(ms, 1),
            segments=[{"start": 0.0, "end": duration_sec, "text": text}],
        )
