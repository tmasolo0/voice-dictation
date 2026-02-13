"""HotkeyManager — глобальные горячие клавиши."""

import threading
import keyboard
import win32gui


class HotkeyManager:
    """Слушатель горячих клавиш, управляет записью через EventBus."""

    def __init__(self, event_bus, config):
        self._bus = event_bus
        self._config = config
        self._recording = False
        self._enabled = True
        self._hotkey = config.get('recognition', 'hotkey', default='f9')

    def start(self):
        """Запустить слушатель клавиатуры в фоновом потоке."""
        def listener():
            keyboard.hook(self._on_key_event)
            keyboard.wait()

        threading.Thread(target=listener, daemon=True).start()

    def stop(self):
        """Остановить слушатель."""
        keyboard.unhook_all()

    def set_enabled(self, enabled: bool):
        """Включить/выключить обработку горячих клавиш."""
        self._enabled = enabled

    def _on_key_event(self, event):
        """Обработка нажатий/отпусканий горячей клавиши."""
        if event.name != self._hotkey:
            return

        if not self._enabled:
            return

        if event.event_type == 'down' and not self._recording:
            self._recording = True
            hwnd = win32gui.GetForegroundWindow()
            self._bus.recording_start.emit(hwnd)
            print("Запись...")

        elif event.event_type == 'up' and self._recording:
            self._recording = False
            self._bus.recording_stop.emit()
