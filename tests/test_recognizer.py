"""Tests for Recognizer — single-worker, busy guard."""

import threading
from unittest.mock import MagicMock, patch
from core.recognizer import Recognizer


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
        mock_config.get_initial_prompt.return_value = ""

        model_mgr = MagicMock()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        model_mgr.get_model.return_value = mock_model

        rec = Recognizer(mock_bus, model_mgr, mock_config)
        rec._busy = True
        rec._transcribe(b"audio")

        assert rec._transcription_count == 1
        assert rec._busy is False
