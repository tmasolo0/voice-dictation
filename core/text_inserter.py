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
        try:
            title = win32gui.GetWindowText(hwnd) if hwnd else "<None>"
            cls = win32gui.GetClassName(hwnd) if hwnd else "<None>"
        except Exception:
            title, cls = "<error>", "<error>"
        log.info("capture_window: hwnd=%s title='%s' class='%s'", hwnd, title, cls)

    def _on_text_ready(self, text: str):
        """Вставить текст в целевое окно, сохранив clipboard пользователя."""
        log.info("insert_start: text_len=%d target_hwnd=%s", len(text), self._target_window)

        # Диагностика: проверяем, что целевое окно ещё существует
        if self._target_window:
            try:
                is_valid = win32gui.IsWindow(self._target_window)
                title = win32gui.GetWindowText(self._target_window) if is_valid else "<destroyed>"
                log.info("insert_target: valid=%s title='%s'", is_valid, title)
            except Exception as e:
                log.warning("insert_target: check failed: %s", e)

        old_clipboard = None
        try:
            # Шаг 1: Сохраняем текущий clipboard
            try:
                old_clipboard = pyperclip.paste()
                log.debug("insert_step1: clipboard saved, len=%d",
                          len(old_clipboard) if old_clipboard else 0)
            except Exception as e:
                old_clipboard = None
                log.warning("insert_step1: clipboard save failed: %s", e)

            # Шаг 2: Активируем целевое окно
            if self._target_window:
                try:
                    win32gui.SetForegroundWindow(self._target_window)
                    log.debug("insert_step2: SetForegroundWindow OK hwnd=%s", self._target_window)
                except Exception as e:
                    log.error("insert_step2: SetForegroundWindow FAILED hwnd=%s: %s",
                              self._target_window, e)
                time.sleep(0.05)
            else:
                log.warning("insert_step2: no target window, skipping SetForegroundWindow")

            # Шаг 3: Копируем текст в clipboard
            try:
                pyperclip.copy(text)
                log.debug("insert_step3: pyperclip.copy OK, len=%d", len(text))
            except Exception as e:
                log.error("insert_step3: pyperclip.copy FAILED: %s", e)
                raise
            time.sleep(0.05)

            # Шаг 4: Отправляем Ctrl+V
            try:
                # Проверяем текущее активное окно перед вставкой
                fg = win32gui.GetForegroundWindow()
                fg_title = win32gui.GetWindowText(fg) if fg else "<None>"
                log.debug("insert_step4: foreground before paste: hwnd=%s title='%s'", fg, fg_title)

                pyautogui.hotkey('ctrl', 'v')
                log.debug("insert_step4: pyautogui.hotkey('ctrl', 'v') OK")
            except Exception as e:
                log.error("insert_step4: pyautogui Ctrl+V FAILED: %s", e)
                raise

            self._bus.text_inserted.emit()
            log.info("insert_done: success, text_len=%d", len(text))

        except Exception as e:
            log.exception("insert_error: %s", e)
            self._bus.error_occurred.emit("TextInserter", str(e))
        finally:
            # Шаг 5: Восстанавливаем clipboard после вставки
            time.sleep(0.1)
            try:
                if old_clipboard is not None:
                    pyperclip.copy(old_clipboard)
                    log.debug("insert_step5: clipboard restored")
            except Exception as e:
                log.warning("insert_step5: clipboard restore failed: %s", e)
