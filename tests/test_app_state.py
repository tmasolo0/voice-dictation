"""Tests for AppStateMachine — valid/invalid transitions."""

from unittest.mock import MagicMock
from core.app_state import AppState, AppStateMachine


class TestValidTransitions:
    def test_init_to_ready(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        assert sm.transition(AppState.READY) is True
        assert sm.state == AppState.READY

    def test_ready_to_recording(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        sm.transition(AppState.READY)
        assert sm.transition(AppState.RECORDING) is True

    def test_recording_to_processing(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        sm.transition(AppState.READY)
        sm.transition(AppState.RECORDING)
        assert sm.transition(AppState.PROCESSING) is True

    def test_processing_to_ready(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        sm.transition(AppState.READY)
        sm.transition(AppState.RECORDING)
        sm.transition(AppState.PROCESSING)
        assert sm.transition(AppState.READY) is True

    def test_full_cycle(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        sm.transition(AppState.READY)
        sm.transition(AppState.RECORDING)
        sm.transition(AppState.PROCESSING)
        sm.transition(AppState.READY)
        assert sm.state == AppState.READY


class TestInvalidTransitions:
    def test_ready_to_processing_invalid(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        sm.transition(AppState.READY)
        assert sm.transition(AppState.PROCESSING) is False
        assert sm.state == AppState.READY

    def test_recording_to_model_switching_invalid(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        sm.transition(AppState.READY)
        sm.transition(AppState.RECORDING)
        assert sm.transition(AppState.MODEL_SWITCHING) is False

    def test_init_to_recording_invalid(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        assert sm.transition(AppState.RECORDING) is False


class TestSignalEmission:
    def test_emits_state_changed(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        sm.transition(AppState.READY)
        bus.state_changed.emit.assert_called_with("ready")

    def test_no_emit_on_invalid(self):
        bus = MagicMock()
        sm = AppStateMachine(bus)
        sm.transition(AppState.RECORDING)  # invalid from INIT
        bus.state_changed.emit.assert_not_called()
