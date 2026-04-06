"""Tests for Qwen3-ASR ONNX Backend."""

import numpy as np
import pytest
from core.qwen3_asr import (
    build_prompt_ids,
    compute_mel_spectrogram,
    get_audio_token_count,
    Qwen3ASRBackend,
    AUDIO_PAD_ID,
    IM_START_ID,
    IM_END_ID,
    AUDIO_START_ID,
    AUDIO_END_ID,
)


class TestAudioTokenCount:
    def test_100_frames(self):
        """100 mel-фреймов = 1 окно = 13 токенов + residual."""
        count = get_audio_token_count(100)
        assert count > 0

    def test_200_frames(self):
        """200 фреймов = 2 окна."""
        count_200 = get_audio_token_count(200)
        count_100 = get_audio_token_count(100)
        assert count_200 > count_100

    def test_short_audio(self):
        """Очень короткое аудио."""
        count = get_audio_token_count(10)
        assert count >= 0


class TestBuildPromptIds:
    def test_basic_structure(self):
        """Промпт содержит все маркеры в правильном порядке."""
        ids = build_prompt_ids(10)
        assert IM_START_ID in ids
        assert AUDIO_START_ID in ids
        assert AUDIO_END_ID in ids
        assert ids.count(AUDIO_PAD_ID) == 10

    def test_audio_pad_count(self):
        ids = build_prompt_ids(50)
        assert ids.count(AUDIO_PAD_ID) == 50

    def test_with_system_prompt(self):
        """System prompt увеличивает длину промпта."""
        mock_tokenizer = type('T', (), {
            'encode': lambda self, text: type('R', (), {'ids': [1, 2, 3]})()
        })()

        ids_no_prompt = build_prompt_ids(10)
        ids_with_prompt = build_prompt_ids(10, system_prompt="test", tokenizer=mock_tokenizer)
        assert len(ids_with_prompt) > len(ids_no_prompt)

    def test_without_tokenizer(self):
        """Без tokenizer system prompt игнорируется."""
        ids = build_prompt_ids(10, system_prompt="test", tokenizer=None)
        ids_no_prompt = build_prompt_ids(10)
        assert len(ids) == len(ids_no_prompt)


class TestParseOutput:
    def test_standard_format(self):
        text, lang = Qwen3ASRBackend._parse_output(
            "language ru<asr_text>Привет мир<|im_end|>"
        )
        assert text == "Привет мир"
        assert lang == "ru"

    def test_english(self):
        text, lang = Qwen3ASRBackend._parse_output(
            "language english<asr_text>Hello world<|im_end|>"
        )
        assert text == "Hello world"
        assert lang == "english"

    def test_no_language(self):
        text, lang = Qwen3ASRBackend._parse_output(
            "<asr_text>Some text<|im_end|>"
        )
        assert text == "Some text"
        assert lang == ""

    def test_empty(self):
        text, lang = Qwen3ASRBackend._parse_output("")
        assert text == ""
        assert lang == ""

    def test_eos_cleanup(self):
        text, lang = Qwen3ASRBackend._parse_output(
            "language ru<asr_text>Текст<|im_end|><|endoftext|>"
        )
        assert "<|im_end|>" not in text
        assert "<|endoftext|>" not in text


class TestBackendInit:
    def test_not_loaded_initially(self):
        backend = Qwen3ASRBackend()
        assert not backend.is_loaded

    def test_unload(self):
        backend = Qwen3ASRBackend()
        backend.unload()
        assert not backend.is_loaded

    def test_transcribe_without_load(self):
        backend = Qwen3ASRBackend()
        audio = np.zeros(16000, dtype=np.float32)
        with pytest.raises(RuntimeError, match="Модель не загружена"):
            backend.transcribe(audio)
