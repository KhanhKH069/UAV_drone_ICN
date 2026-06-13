from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

@dataclass
class ASRResult:
    text: str
    language: str
    latency_ms: float
    segments: list = field(default_factory=list)

class BaseASRBackend(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio_np: np.ndarray,
        language: Optional[str],
        sample_rate: int = 16000,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> ASRResult: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
