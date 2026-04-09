"""
services/whisperlive-wrapper/backends/base.py
Abstract base class cho tất cả ASR backends.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class ASRResult:
    text: str
    language: str          # Whisper-style code: "ja", "en", "vi"...
    latency_ms: float
    segments: list = field(default_factory=list)


class BaseASRBackend(ABC):
    """Interface chung — mỗi backend phải implement transcribe()."""

    @abstractmethod
    def transcribe(
        self,
        audio_np: np.ndarray,
        language: Optional[str],   # None = auto-detect, hoặc tên đầy đủ/mã ngôn ngữ
        sample_rate: int = 16000,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> ASRResult:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Tên backend để hiển thị trong log."""
        ...
