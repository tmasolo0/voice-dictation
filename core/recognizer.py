"""
SpeechRecognizer — распознавание речи на базе faster-whisper.
Инкапсулирует загрузку модели и транскрипцию аудио.
"""

from pathlib import Path
from typing import Optional, Tuple
import numpy as np

from .config_manager import config, PROJECT_ROOT


class SpeechRecognizer:
    """Распознаватель речи на базе faster-whisper."""

    # Частота дискретизации для Whisper
    SAMPLE_RATE = 16000

    def __init__(self):
        """Инициализация (без загрузки модели)."""
        self._model = None
        self._model_loaded = False

        # Настройки из конфига
        self._model_size = config.get('recognition', 'model', default='large-v3-turbo')
        self._device = config.get('recognition', 'device', default='cuda')
        self._compute_type = config.get('recognition', 'compute_type', default='float16')
        self._beam_size = config.get('recognition', 'beam_size', default=5)
        self._language = config.get('recognition', 'language', default='auto')

        # Параметры качества транскрипции
        self._temperature = config.get('recognition', 'temperature', default=0.3)
        self._compression_ratio_threshold = config.get('recognition', 'compression_ratio_threshold', default=2.4)
        self._log_prob_threshold = config.get('recognition', 'log_prob_threshold', default=-1.0)
        self._no_speech_threshold = config.get('recognition', 'no_speech_threshold', default=0.6)

        # Путь к модели
        self._model_path = PROJECT_ROOT / "models" / self._model_size

    def load_model(self) -> bool:
        """
        Загрузка модели Whisper.

        Returns:
            True при успешной загрузке, False при ошибке.
        """
        if self._model_loaded:
            return True

        try:
            from faster_whisper import WhisperModel

            print(f"Загрузка модели Whisper из {self._model_path}...")

            self._model = WhisperModel(
                str(self._model_path),
                device=self._device,
                compute_type=self._compute_type
            )

            self._model_loaded = True
            print(f"Модель {self._model_path.name} загружена!")
            return True

        except Exception as e:
            print(f"Ошибка загрузки модели Whisper: {e}")
            return False

    def is_model_loaded(self) -> bool:
        """Проверка готовности модели."""
        return self._model_loaded

    def recognize(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
        vad_filter: bool = True,
    ) -> str:
        """
        Распознать аудио.

        Args:
            audio: numpy float32 array, 16kHz mono
            language: Язык распознавания (None = из конфига, 'auto' = автоопределение)
            vad_filter: Применять VAD фильтр для удаления тишины

        Returns:
            Распознанный текст
        """
        if not self._model_loaded:
            raise RuntimeError("Модель не загружена. Вызовите load_model() сначала.")

        # Определяем язык
        lang = language or self._language
        lang_param = None if lang == 'auto' else lang

        # Транскрипция
        segments, info = self._model.transcribe(
            audio,
            language=lang_param,
            vad_filter=vad_filter,
            initial_prompt=config.get_initial_prompt(),
            condition_on_previous_text=False,
            beam_size=self._beam_size,
            temperature=self._temperature,
            compression_ratio_threshold=self._compression_ratio_threshold,
            log_prob_threshold=self._log_prob_threshold,
            no_speech_threshold=self._no_speech_threshold,
        )

        # Собираем текст из сегментов
        text = "".join([segment.text for segment in segments])
        return text.strip()

    def recognize_with_info(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
        vad_filter: bool = True,
    ) -> Tuple[str, dict]:
        """
        Распознать аудио с дополнительной информацией.

        Args:
            audio: numpy float32 array, 16kHz mono
            language: Язык распознавания
            vad_filter: Применять VAD фильтр

        Returns:
            Кортеж (текст, info_dict) где info_dict содержит:
            - language: определённый язык
            - language_probability: вероятность языка
        """
        if not self._model_loaded:
            raise RuntimeError("Модель не загружена. Вызовите load_model() сначала.")

        lang = language or self._language
        lang_param = None if lang == 'auto' else lang

        segments, info = self._model.transcribe(
            audio,
            language=lang_param,
            vad_filter=vad_filter,
            initial_prompt=config.get_initial_prompt(),
            condition_on_previous_text=False,
            beam_size=self._beam_size,
            temperature=self._temperature,
            compression_ratio_threshold=self._compression_ratio_threshold,
            log_prob_threshold=self._log_prob_threshold,
            no_speech_threshold=self._no_speech_threshold,
        )

        text = "".join([segment.text for segment in segments])

        info_dict = {
            'language': info.language,
            'language_probability': info.language_probability,
        }

        return text.strip(), info_dict

    @property
    def model_name(self) -> str:
        """Имя загруженной модели."""
        return self._model_size

    @property
    def model_path(self) -> Path:
        """Путь к модели."""
        return self._model_path

    def reload_settings(self):
        """Перезагрузить настройки из конфига (требует перезагрузки модели)."""
        self._model_size = config.get('recognition', 'model', default='large-v3-turbo')
        self._device = config.get('recognition', 'device', default='cuda')
        self._compute_type = config.get('recognition', 'compute_type', default='float16')
        self._beam_size = config.get('recognition', 'beam_size', default=5)
        self._language = config.get('recognition', 'language', default='auto')
        self._model_path = PROJECT_ROOT / "models" / self._model_size

        # Параметры качества транскрипции
        self._temperature = config.get('recognition', 'temperature', default=0.3)
        self._compression_ratio_threshold = config.get('recognition', 'compression_ratio_threshold', default=2.4)
        self._log_prob_threshold = config.get('recognition', 'log_prob_threshold', default=-1.0)
        self._no_speech_threshold = config.get('recognition', 'no_speech_threshold', default=0.6)
