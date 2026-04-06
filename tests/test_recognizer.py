"""Tests for Recognizer — single-worker, busy guard, system prompt."""

import threading
from unittest.mock import MagicMock, patch
from core.recognizer import Recognizer
from core.asr_backend import ASRResult


class TestBusyGuard:
    def test_reject_when_busy(self, mock_bus, mock_config):
        mock_config.get.return_value = 10
        model_mgr = MagicMock()
        rec = Recognizer(mock_bus, model_mgr, mock_config)

        # Simulate busy state
        rec._busy = True
        rec._on_audio_ready(b"audio")

        # executor.submit should NOT be called
        assert not rec._executor._shutdown

    def test_accept_when_idle(self, mock_bus, mock_config):
        mock_config.get.return_value = 10
        model_mgr = MagicMock()
        rec = Recognizer(mock_bus, model_mgr, mock_config)

        with patch.object(rec._executor, 'submit') as mock_submit:
            rec._on_audio_ready(b"audio")
            mock_submit.assert_called_once()
            assert rec._busy is True

    def test_busy_cleared_after_transcribe(self, mock_bus, mock_config):
        mock_config.get.return_value = 10
        model_mgr = MagicMock()
        model_mgr.get_model.return_value = None  # trigger early return
        rec = Recognizer(mock_bus, model_mgr, mock_config)

        rec._busy = True
        rec._transcribe(b"audio")

        assert rec._busy is False


class TestShutdown:
    def test_shutdown_completes(self, mock_bus, mock_config):
        mock_config.get.return_value = 10
        model_mgr = MagicMock()
        rec = Recognizer(mock_bus, model_mgr, mock_config)
        rec.shutdown()
        # No exception = success


class TestTranscriptionCount:
    def test_count_increments(self, mock_bus, mock_config):
        mock_config.get.side_effect = lambda *args, default=None: default
        mock_config.get_hotwords.return_value = ""
        mock_config.get_terms_list.return_value = []

        model_mgr = MagicMock()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ASRResult(
            text="hello", language="en", language_probability=0.99,
        )
        model_mgr.get_model.return_value = mock_model

        rec = Recognizer(mock_bus, model_mgr, mock_config)
        rec._busy = True
        rec._transcribe(b"audio")

        assert rec._transcription_count == 1
        assert rec._busy is False


class TestSystemPrompt:
    def test_build_with_terms(self, mock_bus, mock_config):
        mock_config.get.side_effect = lambda *args, default=None: default
        mock_config.get_hotwords.return_value = ""
        mock_config.get_terms_list.return_value = ["Claude Code", "Docker", "API"]

        model_mgr = MagicMock()
        rec = Recognizer(mock_bus, model_mgr, mock_config)

        prompt = rec._build_system_prompt(["Claude Code", "Docker", "API"])
        assert "Claude Code" in prompt
        assert "Docker" in prompt
        assert "API" in prompt

    def test_build_empty(self, mock_bus, mock_config):
        mock_config.get.side_effect = lambda *args, default=None: default
        model_mgr = MagicMock()
        rec = Recognizer(mock_bus, model_mgr, mock_config)

        prompt = rec._build_system_prompt([])
        assert prompt is None

    def test_build_with_user_prompt(self, mock_bus, mock_config):
        def get_side_effect(*args, default=None):
            if args == ('recognition', 'system_prompt'):
                return "Диктовка на русском языке"
            return default

        mock_config.get.side_effect = get_side_effect
        model_mgr = MagicMock()
        rec = Recognizer(mock_bus, model_mgr, mock_config)

        prompt = rec._build_system_prompt(["Docker"])
        assert "Диктовка на русском языке" in prompt
        assert "Docker" in prompt


class TestHallucination:
    def test_single_word(self, mock_bus, mock_config):
        mock_config.get.return_value = 10
        model_mgr = MagicMock()
        rec = Recognizer(mock_bus, model_mgr, mock_config)

        assert rec._is_hallucination("um") is True
        assert rec._is_hallucination("да") is True

    def test_repeated_phrase(self, mock_bus, mock_config):
        mock_config.get.return_value = 10
        model_mgr = MagicMock()
        rec = Recognizer(mock_bus, model_mgr, mock_config)

        assert rec._is_hallucination("hello worldhello worldhello world") is True

    def test_normal_text(self, mock_bus, mock_config):
        mock_config.get.return_value = 10
        model_mgr = MagicMock()
        rec = Recognizer(mock_bus, model_mgr, mock_config)

        assert rec._is_hallucination("Запусти Claude Code и проверь Docker") is False
