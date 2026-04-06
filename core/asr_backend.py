"""ASR Backend — абстракция движка распознавания речи."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ASRResult:
    """Результат распознавания речи."""
    text: str
    language: str = ""
    language_probability: float = 0.0
    elapsed: float = 0.0
    metadata: dict = field(default_factory=dict)


class ASRBackend(ABC):
    """Абстрактный ASR-движок."""

    @abstractmethod
    def load(self, model_path: str, device: str = "cuda") -> None:
        """Загрузить модель."""

    @abstractmethod
    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        system_prompt: str | None = None,
    ) -> ASRResult:
        """Распознать аудио. audio: float32 @ 16kHz mono."""

    @abstractmethod
    def unload(self) -> None:
        """Выгрузить модель, освободить ресурсы."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Модель загружена и готова к работе."""
