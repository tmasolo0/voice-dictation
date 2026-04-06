"""Tests for standalone Silero VAD."""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from core.vad import SileroVAD, SAMPLE_RATE, WINDOW_SIZE


class TestSileroVAD:
    def test_init_without_model(self):
        vad = SileroVAD()
        assert not vad.is_loaded

    def test_get_speech_segments_not_loaded(self):
        vad = SileroVAD()
        with pytest.raises(RuntimeError, match="VAD не загружена"):
            vad.get_speech_segments(np.zeros(16000, dtype=np.float32))

    def test_extract_speech_returns_original_if_no_speech(self):
        """Если VAD не нашла речь — вернуть оригинал."""
        vad = SileroVAD(threshold=0.5)
        vad._session = MagicMock()

        # Все окна возвращают prob=0.0 (тишина)
        vad._session.run.return_value = [
            np.array(0.0, dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
        ]

        audio = np.zeros(16000, dtype=np.float32)
        result = vad.extract_speech(audio)
        np.testing.assert_array_equal(result, audio)

    def test_merge_segments_basic(self):
        """Тест объединения вероятностей в сегменты."""
        vad = SileroVAD(threshold=0.5, min_speech_ms=100, min_silence_ms=200)

        # 10 окон: 5 речь, 5 тишина
        probs = [0.9, 0.8, 0.9, 0.7, 0.8, 0.1, 0.0, 0.1, 0.0, 0.0]

        min_speech = int(0.1 * SAMPLE_RATE)
        min_silence = int(0.2 * SAMPLE_RATE)

        segments = vad._merge_segments(probs, min_speech, min_silence)
        assert len(segments) == 1
        start, end = segments[0]
        assert start == 0
        assert end == 5 * WINDOW_SIZE  # тишина начинается с 5-го окна

    def test_compute_probs_shape(self):
        """Проверка что _compute_probs возвращает правильное число окон."""
        vad = SileroVAD()
        vad._session = MagicMock()
        vad._h = np.zeros((1, 1, 128), dtype=np.float32)
        vad._c = np.zeros((1, 1, 128), dtype=np.float32)

        vad._session.run.return_value = [
            np.array(0.5, dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
        ]

        audio = np.zeros(WINDOW_SIZE * 10, dtype=np.float32)
        probs = vad._compute_probs(audio)
        assert len(probs) == 10
