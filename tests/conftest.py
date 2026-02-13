"""Shared fixtures for tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_bus():
    """Mock EventBus with all signals."""
    bus = MagicMock()
    bus.recording_start = MagicMock()
    bus.recording_stop = MagicMock()
    bus.audio_ready = MagicMock()
    bus.text_recognized = MagicMock()
    bus.text_processed = MagicMock()
    bus.text_inserted = MagicMock()
    bus.state_changed = MagicMock()
    bus.model_load_started = MagicMock()
    bus.model_load_finished = MagicMock()
    bus.model_load_failed = MagicMock()
    bus.mode_changed = MagicMock()
    bus.quit_requested = MagicMock()
    bus.error_occurred = MagicMock()
    return bus


@pytest.fixture
def mock_config():
    """Mock ConfigManager."""
    cfg = MagicMock()
    cfg.get.return_value = None
    cfg.get_initial_prompt.return_value = ""
    cfg.get_hotwords.return_value = ""
    return cfg
