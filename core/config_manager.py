"""
ConfigManager — централизованное управление конфигурацией.
Singleton-класс для чтения/записи настроек из config.json.
"""

import sys
from pathlib import Path
import json
import copy
from typing import Any

# Frozen (PyInstaller): .exe рядом с writable-файлами, _MEIPASS — read-only bundle
# Dev: всё в корне проекта
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent       # рядом с .exe (writable)
    BUNDLE_DIR = Path(sys._MEIPASS)             # _internal/ (read-only)
else:
    APP_DIR = Path(__file__).parent.parent
    BUNDLE_DIR = APP_DIR

CONFIG_FILE = APP_DIR / "config.json"
DICTIONARY_FILE = BUNDLE_DIR / "dictionary.txt"
DICTIONARIES_DIR = BUNDLE_DIR / "dictionaries"
REPLACEMENTS_FILE = APP_DIR / "replacements.json"
CONFIG_VERSION = 14

DEFAULT_CONFIG = {
    "version": CONFIG_VERSION,
    "widget": {
        "position": {"x": None, "y": None},
        "auto_position": True,
        "bar_width": 200,
        "bar_height": 36,
        "size": 150,
        "sound_effects": True,
        "audio_ducking": True,
        "duck_level": 0.15
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
        "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],  # Temperature fallback (начинает с greedy, повышает при плохих метриках)
        "condition_on_previous_text": False,     # Контекст предыдущего сегмента (False для push-to-talk)
        "compression_ratio_threshold": 2.4,     # Порог сжатия — фильтр повторяющегося текста
        "log_prob_threshold": -1.0,             # Порог логарифма вероятности — фильтр низкой уверенности
        "no_speech_threshold": 0.6,             # Порог «нет речи» — пропуск тихих сегментов
        "repetition_penalty": 1.2,              # Штраф за повторение токенов (>1.0 = штраф)
        "no_repeat_ngram_size": 3,              # Запрет повтора N-грамм подряд
        "suppress_tokens": [-1],                # Подавление не-речевых токенов (-1 = дефолтный набор)
        "hallucination_silence_threshold": 2.0, # Фильтр галлюцинаций на тишине (секунды)
        "vram_cleanup_interval": 10,
        "audio_gain": 1.0
    },
    "vad": {
        "threshold": 0.5,
        "min_speech_ms": 250,
        "min_silence_ms": 500
    },
    "dictionaries": {
        "active": ["it"]
    },
    "postprocessing": {
        "punctuation": True,
        "capitalization": True,
        "trailing_dot": True
    },
    "system": {
        "autostart": False,
        "start_minimized": False,
        "run_as_admin": False
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
            old_version = self._config["version"]
            user_overrides = self._config
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            self._deep_update(self._config, user_overrides)
            # v11 → v12: temperature скаляр → список, невалидный hotkey → f9
            if old_version < 12:
                temp = self._config.get("recognition", {}).get("temperature")
                if isinstance(temp, (int, float)):
                    self._config["recognition"]["temperature"] = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
                _STANDALONE_MODS = {"ctrl", "shift", "alt", "win"}
                for hk_key in ("hotkey",):
                    val = self._config.get("recognition", {}).get(hk_key, "")
                    if val in _STANDALONE_MODS:
                        default_val = DEFAULT_CONFIG["recognition"].get(hk_key, "f9")
                        self._config["recognition"][hk_key] = default_val
                        print(f"Миграция: hotkey '{hk_key}' сброшен с '{val}' на '{default_val}'")
            # v12 → v13: удалены translate, history, preview, hide_in_fullscreen; компактный виджет
            if old_version < 13:
                rec = self._config.get("recognition", {})
                for k in ("translate_hotkey", "history_hotkey"):
                    rec.pop(k, None)
                self._config.pop("dictation", None)
                self._config.pop("preview", None)
                self._config.pop("history", None)
                self._config.get("widget", {}).pop("hide_in_fullscreen", None)
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
