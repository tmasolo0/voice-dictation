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
DICTIONARY_FILE = PROJECT_ROOT / "dictionary.txt"
DICTIONARIES_DIR = PROJECT_ROOT / "dictionaries"
REPLACEMENTS_FILE = PROJECT_ROOT / "replacements.json"
CONFIG_VERSION = 9

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
        "initial_prompt": "",                    # Контекст для декодера (короткая фраза, НЕ список терминов)
        "use_hotwords": True,                    # Использовать hotwords из словарей (может вызывать галлюцинации)
        # --- Параметры качества транскрипции ---
        "beam_size": 5,                         # Ширина beam search (больше = точнее, медленнее)
        "temperature": 0.3,                     # Температура сэмплирования (0 = жадный декодинг)
        "condition_on_previous_text": False,     # Контекст предыдущего сегмента (False для push-to-talk)
        "compression_ratio_threshold": 2.4,     # Порог сжатия — фильтр повторяющегося текста
        "log_prob_threshold": -1.0,             # Порог логарифма вероятности — фильтр низкой уверенности
        "no_speech_threshold": 0.6,             # Порог «нет речи» — пропуск тихих сегментов
        "repetition_penalty": 1.2,              # Штраф за повторение токенов (>1.0 = штраф)
        "no_repeat_ngram_size": 3,              # Запрет повтора N-грамм подряд
        "suppress_tokens": [-1],                # Подавление не-речевых токенов (-1 = дефолтный набор)
        "hallucination_silence_threshold": 2.0, # Фильтр галлюцинаций на тишине (секунды)
        "translate_hotkey": "f10",
        "history_hotkey": "ctrl+h",
        "vram_cleanup_interval": 10,
        "audio_gain": 1.0
    },
    "dictation": {
        "translate_to_english": False
    },
    "vad": {
        "threshold": 0.5,
        "min_speech_ms": 250,
        "min_silence_ms": 500
    },
    "dictionaries": {
        "active": ["it"]
    },
    "preview": {
        "enabled": False,
        "auto_insert_delay": 5
    },
    "postprocessing": {
        "punctuation": True,
        "capitalization": True,
        "trailing_dot": True
    },
    "history": {
        "history_retention_days": 30
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
            # v0: старый формат с window_x, window_y
            old_x = self._config.pop("window_x", None)
            old_y = self._config.pop("window_y", None)

            new_config = copy.deepcopy(DEFAULT_CONFIG)

            if old_x is not None and old_y is not None:
                new_config["widget"]["position"]["x"] = old_x
                new_config["widget"]["position"]["y"] = old_y

            self._config = new_config
            self.save()
            print(f"Конфиг мигрирован на версию {CONFIG_VERSION}")
        elif self._config["version"] < CONFIG_VERSION:
            # v1/v2 -> v3: deep merge — добавляет недостающие ключи
            user_overrides = self._config
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            self._deep_update(self._config, user_overrides)
            self._config["version"] = CONFIG_VERSION
            self.save()
            print(f"Конфиг мигрирован на версию {CONFIG_VERSION}")

    @staticmethod
    def _deep_update(base: dict, override: dict):
        """Рекурсивное слияние override в base."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigManager._deep_update(base[key], value)
            else:
                base[key] = value

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

    def _load_dictionary_file(self, path: Path) -> set:
        """Загрузка терминов из файла словаря."""
        if not path.exists():
            return set()
        try:
            text = path.read_text(encoding='utf-8')
            return {
                line.strip().lower()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith('#')
            }
        except IOError as e:
            print(f"Ошибка чтения словаря {path}: {e}")
            return set()

    def get_hotwords(self) -> str:
        """Собирает термины из base dictionary.txt + активных доменных словарей."""
        terms = set()

        # Базовый словарь
        terms.update(self._load_dictionary_file(DICTIONARY_FILE))

        # Доменные словари
        active = self.get('dictionaries', 'active', default=[])
        for domain in active:
            domain_file = DICTIONARIES_DIR / f"{domain}.txt"
            if domain_file.exists():
                terms.update(self._load_dictionary_file(domain_file))
            else:
                print(f"Доменный словарь не найден: {domain_file}")

        return " ".join(sorted(terms)) if terms else ""

    def get_replacements(self) -> dict:
        """Загрузка словаря замен из replacements.json."""
        if not REPLACEMENTS_FILE.exists():
            return {}
        try:
            with open(REPLACEMENTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Ошибка чтения replacements.json: {e}")
            return {}

    def reload(self):
        """Перезагрузка конфигурации из файла."""
        self._load()


# Глобальный экземпляр для импорта
config = ConfigManager()
