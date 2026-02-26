"""HotkeyManager — глобальные горячие клавиши."""

import logging
import threading
import keyboard
import win32gui

log = logging.getLogger(__name__)


class HotkeyManager:
    """Слушатель горячих клавиш, управляет записью через EventBus."""

    def __init__(self, event_bus, config):
        self._bus = event_bus
        self._config = config
        self._recording = False
        self._enabled = True
        self._hotkey = config.get('recognition', 'hotkey', default='f9')
        self._translate_hotkey = config.get('recognition', 'translate_hotkey', default='f10')
        self._history_hotkey = config.get('recognition', 'history_hotkey', default='ctrl+h')

    def start(self):
        """Запустить слушатель клавиатуры в фоновом потоке."""
        def listener():
            log.info("keyboard hook started, hotkey=%s", self._hotkey)
            keyboard.hook(self._on_key_event)
            keyboard.wait()

        threading.Thread(target=listener, daemon=True).start()

    def stop(self):
        """Остановить слушатель."""
        keyboard.unhook_all()

    def set_enabled(self, enabled: bool):
        """Включить/выключить обработку горячих клавиш записи."""
        self._enabled = enabled

    def update_hotkey(self, hotkey: str):
        """Обновить горячую клавишу записи без перезапуска."""
        self._hotkey = hotkey

    def update_translate_hotkey(self, hotkey: str):
        """Обновить горячую клавишу перевода без перезапуска."""
        self._translate_hotkey = hotkey

    def update_history_hotkey(self, hotkey: str):
        """Обновить горячую клавишу истории без перезапуска."""
        self._history_hotkey = hotkey

    def _on_key_event(self, event):
        """Обработка нажатий/отпусканий горячих клавиш."""
        # Переключение перевода — одиночное нажатие, работает всегда
        if event.name == self._translate_hotkey and event.event_type == 'down':
            self._bus.mode_changed.emit("translate_toggle", None)
            return

        # History dialog — combo hotkey (e.g. "ctrl+h")
        if self._history_hotkey and event.event_type == 'down':
            parts = self._history_hotkey.split('+')
            base_key = parts[-1].strip()
            modifiers = [m.strip() for m in parts[:-1]]
            if event.name == base_key and all(keyboard.is_pressed(mod) for mod in modifiers):
                self._bus.mode_changed.emit("open_history", None)
                return

        # Push-to-talk
        if event.name != self._hotkey:
            return

        # Отпускание ВСЕГДА останавливает запись (даже если enabled=False из-за смены состояния)
        if event.event_type == 'up' and self._recording:
            self._recording = False
            log.info("recording_stop")
            self._bus.recording_stop.emit()
            return

        if not self._enabled:
            return

        if event.event_type == 'down' and not self._recording:
            self._recording = True
            hwnd = win32gui.GetForegroundWindow()
            log.info("recording_start hwnd=%s", hwnd)
            self._bus.recording_start.emit(hwnd)
