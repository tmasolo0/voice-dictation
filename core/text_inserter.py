"""TextInserter — вставка текста в активное окно."""

import logging
import time
import win32gui
import pyperclip
import pyautogui

log = logging.getLogger(__name__)


class TextInserter:
    """Захват целевого окна и вставка текста через Ctrl+V."""

    def __init__(self, event_bus, config):
        self._bus = event_bus
        self._config = config
        self._target_window = None

        self._bus.recording_start.connect(self._capture_window)
        self._bus.text_processed.connect(self._on_text_ready)

    def _capture_window(self, hwnd):
        """Запомнить активное окно (захвачено в keyboard hook thread)."""
        self._target_window = hwnd

    def _on_text_ready(self, text: str):
        """Вставить текст в целевое окно, сохранив clipboard пользователя."""
        old_clipboard = None
        try:
            # Сохраняем текущий clipboard
            try:
                old_clipboard = pyperclip.paste()
            except Exception:
                old_clipboard = None

            if self._target_window:
                win32gui.SetForegroundWindow(self._target_window)
                time.sleep(0.05)

            pyperclip.copy(text)
            time.sleep(0.05)
            pyautogui.hotkey('ctrl', 'v')

            self._bus.text_inserted.emit()

        except Exception as e:
            log.exception("Ошибка вставки: %s", e)
            self._bus.error_occurred.emit("TextInserter", str(e))
        finally:
            # Восстанавливаем clipboard после вставки
            time.sleep(0.1)
            try:
                if old_clipboard is not None:
                    pyperclip.copy(old_clipboard)
            except Exception:
                pass
