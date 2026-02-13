"""Tests for AudioCapture — threading.Event, data collection."""

import numpy as np
from unittest.mock import MagicMock, patch
from core.audio_capture import AudioCapture


class TestRecordingEvent:
    def test_event_set_on_start(self, mock_bus, mock_config):
        ac = AudioCapture(mock_bus, mock_config)
        ac._on_start(hwnd=12345)
        assert ac._recording_event.is_set()

    def test_event_cleared_on_stop(self, mock_bus, mock_config):
        ac = AudioCapture(mock_bus, mock_config)
        ac._on_start(hwnd=12345)
        ac._on_stop()
        assert not ac._recording_event.is_set()

    def test_audio_data_cleared_on_start(self, mock_bus, mock_config):
        ac = AudioCapture(mock_bus, mock_config)
        ac._audio_data = [np.zeros(100)]
        ac._on_start(hwnd=12345)
        assert ac._audio_data == []


class TestAudioCallback:
    def test_callback_appends_when_recording(self, mock_bus, mock_config):
        ac = AudioCapture(mock_bus, mock_config)
        ac._recording_event.set()

        data = np.ones((160, 1), dtype=np.float32)
        ac._audio_callback(data, 160, None, None)

        assert len(ac._audio_data) == 1

    def test_callback_ignores_when_not_recording(self, mock_bus, mock_config):
        ac = AudioCapture(mock_bus, mock_config)
        # Event not set

        data = np.ones((160, 1), dtype=np.float32)
        ac._audio_callback(data, 160, None, None)

        assert len(ac._audio_data) == 0


class TestDataEmit:
    def test_emits_audio_ready_on_stop(self, mock_bus, mock_config):
        ac = AudioCapture(mock_bus, mock_config)
        ac._recording_event.set()

        # Simulate recording
        chunk = np.ones((160, 1), dtype=np.float32)
        ac._audio_callback(chunk, 160, None, None)
        ac._audio_callback(chunk, 160, None, None)

        ac._on_stop()
        mock_bus.audio_ready.emit.assert_called_once()

        # Verify concatenated data
        emitted = mock_bus.audio_ready.emit.call_args[0][0]
        assert isinstance(emitted, np.ndarray)
        assert len(emitted) == 320

    def test_no_emit_on_empty_recording(self, mock_bus, mock_config):
        ac = AudioCapture(mock_bus, mock_config)
        ac._on_start(hwnd=12345)
        ac._on_stop()
        mock_bus.audio_ready.emit.assert_not_called()
