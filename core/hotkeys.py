"""
HotkeyManager — управление глобальными горячими клавишами.
Обёртка над библиотекой keyboard для упрощения работы с хоткеями.
"""

import threading
from typing import Callable, Dict, Optional

import keyboard


class HotkeyManager:
    """Менеджер глобальных горячих клавиш."""

    def __init__(self):
        """Инициализация менеджера."""
        self._callbacks: Dict[str, dict] = {}
        self._hook = None
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False

    def register(
        self,
        key: str,
        on_press: Optional[Callable] = None,
        on_release: Optional[Callable] = None,
    ):
        """
        Зарегистрировать хоткей.

        Args:
            key: Клавиша (например 'f9', 'shift+f9')
            on_press: Callback при нажатии
            on_release: Callback при отпускании (опционально)
        """
        key_lower = key.lower()
        self._callbacks[key_lower] = {
            'on_press': on_press,
            'on_release': on_release,
            'pressed': False,
        }

    def unregister(self, key: str):
        """Снять регистрацию хоткея."""
        key_lower = key.lower()
        if key_lower in self._callbacks:
            del self._callbacks[key_lower]

    def unregister_all(self):
        """Снять все хоткеи."""
        self._callbacks.clear()

    def start(self):
        """Запустить слушатель клавиатуры."""
        if self._running:
            return

        self._running = True
        self._listener_thread = threading.Thread(
            target=self._listener_loop,
            daemon=True
        )
        self._listener_thread.start()

    def stop(self):
        """Остановить слушатель клавиатуры."""
        self._running = False
        if self._hook:
            keyboard.unhook(self._hook)
            self._hook = None

    def _listener_loop(self):
        """Основной цикл слушателя (запускается в отдельном потоке)."""
        self._hook = keyboard.hook(self._on_key_event)
        keyboard.wait()

    def _on_key_event(self, event):
        """
        Обработчик событий клавиатуры.

        Args:
            event: Событие от библиотеки keyboard
        """
        key_name = event.name.lower()

        # Проверяем прямое совпадение
        if key_name in self._callbacks:
            callback_data = self._callbacks[key_name]

            if event.event_type == 'down' and not callback_data['pressed']:
                callback_data['pressed'] = True
                if callback_data['on_press']:
                    callback_data['on_press']()

            elif event.event_type == 'up' and callback_data['pressed']:
                callback_data['pressed'] = False
                if callback_data['on_release']:
                    callback_data['on_release']()

    def is_pressed(self, key: str) -> bool:
        """
        Проверить, нажата ли клавиша.

        Args:
            key: Название клавиши (например 'shift', 'ctrl')

        Returns:
            True если клавиша нажата
        """
        return keyboard.is_pressed(key)

    def is_modifier_pressed(self, modifier: str) -> bool:
        """
        Проверить, нажата ли клавиша-модификатор.

        Args:
            modifier: 'shift', 'ctrl', 'alt', 'win'

        Returns:
            True если модификатор нажат
        """
        return keyboard.is_pressed(modifier)


# Глобальный экземпляр для удобства
_default_manager: Optional[HotkeyManager] = None


def get_hotkey_manager() -> HotkeyManager:
    """Получить глобальный менеджер хоткеев."""
    global _default_manager
    if _default_manager is None:
        _default_manager = HotkeyManager()
    return _default_manager
