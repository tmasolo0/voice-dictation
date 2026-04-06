"""Standalone Silero VAD — детекция речи через ONNX Runtime."""

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# Silero VAD v6 работает на 16kHz, окно 576 сэмплов
SAMPLE_RATE = 16000
WINDOW_SIZE = 576


class SileroVAD:
    """Voice Activity Detection через Silero VAD v6 (ONNX)."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        threshold: float = 0.5,
        min_speech_ms: int = 250,
        min_silence_ms: int = 500,
    ):
        self.threshold = threshold
        self.min_speech_ms = min_speech_ms
        self.min_silence_ms = min_silence_ms
        self._session = None
        self._state = None
        self._sr = None

        if model_path:
            self.load(model_path)

    def load(self, model_path: str | Path) -> None:
        """Загрузить ONNX-модель Silero VAD."""
        import onnxruntime as ort

        model_path = str(model_path)
        self._session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],  # VAD всегда на CPU — быстрее
        )
        self._reset_state()
        log.info("Silero VAD загружена: %s", model_path)

    def _reset_state(self) -> None:
        """Сбросить LSTM hidden/cell state."""
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    def get_speech_segments(
        self,
        audio: np.ndarray,
    ) -> list[tuple[int, int]]:
        """Найти сегменты речи в аудио.

        Args:
            audio: float32 моно @ 16kHz

        Returns:
            Список (start_sample, end_sample) — сегменты с речью.
        """
        if not self.is_loaded:
            raise RuntimeError("VAD не загружена")

        self._reset_state()

        min_speech_samples = int(self.min_speech_ms * SAMPLE_RATE / 1000)
        min_silence_samples = int(self.min_silence_ms * SAMPLE_RATE / 1000)

        # Прогнать аудио через VAD по окнам
        probs = self._compute_probs(audio)

        # Найти сегменты речи
        segments = self._merge_segments(
            probs, min_speech_samples, min_silence_samples,
        )
        return segments

    def extract_speech(self, audio: np.ndarray) -> np.ndarray:
        """Извлечь только речевые фрагменты, склеить в один массив.

        Args:
            audio: float32 моно @ 16kHz

        Returns:
            Склеенные речевые фрагменты или оригинал если речь не найдена.
        """
        segments = self.get_speech_segments(audio)
        if not segments:
            log.debug("VAD: речь не обнаружена, возвращаю оригинал")
            return audio

        parts = [audio[start:end] for start, end in segments]
        result = np.concatenate(parts)
        total_speech = sum(end - start for start, end in segments)
        log.debug(
            "VAD: %d сегментов, речь %.1f сек из %.1f сек",
            len(segments),
            total_speech / SAMPLE_RATE,
            len(audio) / SAMPLE_RATE,
        )
        return result

    def _compute_probs(self, audio: np.ndarray) -> list[float]:
        """Вычислить вероятность речи для каждого окна."""
        probs = []
        n_samples = len(audio)

        for i in range(0, n_samples, WINDOW_SIZE):
            chunk = audio[i : i + WINDOW_SIZE]
            if len(chunk) < WINDOW_SIZE:
                chunk = np.pad(chunk, (0, WINDOW_SIZE - len(chunk)))

            input_data = chunk[np.newaxis, :]  # [1, 576]

            outputs = self._session.run(
                None,
                {
                    "input": input_data,
                    "h": self._h,
                    "c": self._c,
                },
            )
            prob = outputs[0].item()
            self._h = outputs[1]
            self._c = outputs[2]
            probs.append(prob)

        return probs

    def _merge_segments(
        self,
        probs: list[float],
        min_speech_samples: int,
        min_silence_samples: int,
    ) -> list[tuple[int, int]]:
        """Объединить оконные вероятности в сегменты речи."""
        segments = []
        speech_start = None
        silence_start = None

        for i, prob in enumerate(probs):
            sample_pos = i * WINDOW_SIZE

            if prob >= self.threshold:
                # Речь
                if speech_start is None:
                    speech_start = sample_pos
                silence_start = None
            else:
                # Тишина
                if speech_start is not None and silence_start is None:
                    silence_start = sample_pos

                if (
                    speech_start is not None
                    and silence_start is not None
                    and (sample_pos - silence_start) >= min_silence_samples
                ):
                    # Достаточно тишины — закрыть сегмент
                    speech_end = silence_start
                    if (speech_end - speech_start) >= min_speech_samples:
                        segments.append((speech_start, speech_end))
                    speech_start = None
                    silence_start = None

        # Закрыть последний сегмент если речь дошла до конца
        if speech_start is not None:
            speech_end = len(probs) * WINDOW_SIZE
            if silence_start is not None:
                speech_end = silence_start
            if (speech_end - speech_start) >= min_speech_samples:
                segments.append((speech_start, speech_end))

        return segments
