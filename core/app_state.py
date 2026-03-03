"""AppState — состояния приложения и машина переходов."""

import logging
from enum import Enum, auto

log = logging.getLogger(__name__)


class AppState(Enum):
    """Возможные состояния приложения."""
    INITIALIZING = auto()
    READY = auto()
    RECORDING = auto()
    PROCESSING = auto()
    MODEL_SWITCHING = auto()
    ERROR = auto()


VALID_TRANSITIONS = {
    AppState.INITIALIZING: {AppState.READY, AppState.MODEL_SWITCHING, AppState.ERROR},
    AppState.READY: {AppState.RECORDING, AppState.MODEL_SWITCHING},
    AppState.RECORDING: {AppState.PROCESSING, AppState.READY},
    AppState.PROCESSING: {AppState.READY, AppState.ERROR},
    AppState.MODEL_SWITCHING: {AppState.READY, AppState.ERROR},
    AppState.ERROR: {AppState.READY, AppState.MODEL_SWITCHING},
}


class AppStateMachine:
    """Конечный автомат с валидацией переходов."""

    def __init__(self, event_bus):
        self._state = AppState.INITIALIZING
        self._bus = event_bus

    @property
    def state(self) -> AppState:
        return self._state

    def transition(self, new_state: AppState) -> bool:
        """Переход в новое состояние. Возвращает True при успехе."""
        old = self._state
        if new_state in VALID_TRANSITIONS.get(old, set()):
            self._state = new_state
            log.info("STATE: %s -> %s", old.name, new_state.name)
            self._bus.state_changed.emit(new_state.name.lower())
            return True
        log.warning("INVALID transition: %s -> %s (allowed: %s)",
                     old.name, new_state.name,
                     [s.name for s in VALID_TRANSITIONS.get(old, set())])
        return False
