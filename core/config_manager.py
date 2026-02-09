"""
ConfigManager — централизованное управление конфигурацией.
Singleton-класс для чтения/записи настроек из config.json.
"""

from pathlib import Path
import json
import copy
from typing import Any

# Путь к config.json — в корне проекта (parent от core/)
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.json"
CONFIG_VERSION = 2

DEFAULT_CONFIG = {
    "version": CONFIG_VERSION,
    "widget": {
        "position": {"x": None, "y": None},
        "size": 150,
        "hide_in_fullscreen": True
    },
    "recognition": {
        "hotkey": "f9",
        "model": "large-v3-turbo",
        "device": "cuda",
        "compute_type": "float16",
        "language": "auto",
        "beam_size": 5,
        "custom_terms": [
            "Claude Code", "VS Code", "Visual Studio Code", "file manager",
            "Git", "GitHub", "Python", "JavaScript", "TypeScript",
            "terminal", "commit", "push", "pull", "merge", "branch",
            "npm", "pip", "Docker", "API", "JSON", "SQL", "README", "config",
            "Whisper", "PyQt", "widget", "hotkey", "Ctrl", "Shift", "Alt"
        ]
    },
    "system": {
        "autostart": False,
        "start_minimized": False
    }
}


class ConfigManager:
    """Singleton менеджер конфигурации."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = None
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._load()
            self._initialized = True

    def _load(self):
        """Загрузка конфигурации из файла."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                self._migrate()
            except (json.JSONDecodeError, IOError) as e:
                print(f"Ошибка чтения конфига: {e}")
                self._config = copy.deepcopy(DEFAULT_CONFIG)
                self.save()
        else:
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            self.save()

    def _migrate(self):
        """Миграция старого формата конфига."""
        if "version" not in self._config:
            # Старый формат: window_x, window_y
            old_x = self._config.pop("window_x", None)
            old_y = self._config.pop("window_y", None)

            # Создаём новый конфиг с дефолтами
            new_config = copy.deepcopy(DEFAULT_CONFIG)

            # Переносим позицию
            if old_x is not None and old_y is not None:
                new_config["widget"]["position"]["x"] = old_x
                new_config["widget"]["position"]["y"] = old_y

            self._config = new_config
            self.save()
            print(f"Конфиг мигрирован на версию {CONFIG_VERSION}")

    def get(self, *keys, default=None) -> Any:
        """
        Получение значения по пути ключей.

        Пример:
            config.get('recognition', 'hotkey', default='f9')
            config.get('widget', 'position', 'x')
        """
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, *keys_and_value):
        """
        Установка значения по пути ключей.
        Последний аргумент — значение, остальные — путь.

        Пример:
            config.set('widget', 'position', 'x', 100)
        """
        if len(keys_and_value) < 2:
            raise ValueError("Нужен хотя бы ключ и значение")

        *keys, value = keys_and_value
        target = self._config

        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        target[keys[-1]] = value

    def save(self):
        """Сохранение конфигурации в файл."""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Ошибка сохранения конфига: {e}")

    def get_initial_prompt(self) -> str:
        """Собирает custom_terms в строку для initial_prompt."""
        terms = self.get('recognition', 'custom_terms', default=[])
        return ", ".join(terms)

    def reload(self):
        """Перезагрузка конфигурации из файла."""
        self._load()


# Глобальный экземпляр для импорта
config = ConfigManager()
