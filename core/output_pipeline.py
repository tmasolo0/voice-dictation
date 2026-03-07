"""OutputPipeline — цепочка обработки распознанного текста."""

import logging
import re
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class TextProcessor(ABC):
    """Базовый класс для обработчиков текста."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def process(self, text: str, metadata: dict) -> str:
        ...


class StripProcessor(TextProcessor):
    """Убирает пробелы по краям."""

    @property
    def name(self) -> str:
        return "strip"

    def process(self, text: str, metadata: dict) -> str:
        return text.strip()


class PunctuationProcessor(TextProcessor):
    """Нормализация пробелов вокруг знаков препинания."""

    @property
    def name(self) -> str:
        return "punctuation"

    def process(self, text: str, metadata: dict) -> str:
        # Убрать пробелы ПЕРЕД .,:;!?
        text = re.sub(r'\s+([.,:;!?])', r'\1', text)
        # Добавить пробел ПОСЛЕ .,:;!? если его нет (и если не конец строки)
        text = re.sub(r'([.,:;!?])([^\s.,:;!?\d)"\'])', r'\1 \2', text)
        # Схлопнуть множественные пробелы
        text = re.sub(r' {2,}', ' ', text)
        return text


class CapitalizationProcessor(TextProcessor):
    """Заглавная буква в начале текста и после .!?"""

    @property
    def name(self) -> str:
        return "capitalization"

    def process(self, text: str, metadata: dict) -> str:
        if not text:
            return text
        # Первая буква текста — заглавная
        text = text[0].upper() + text[1:]
        # После .!? + пробел — заглавная буква
        text = re.sub(r'([.!?])\s+([a-zа-яё])', lambda m: m.group(1) + ' ' + m.group(2).upper(), text)
        return text


class TrailingDotProcessor(TextProcessor):
    """Добавляет точку в конце, если нет завершающей пунктуации."""

    @property
    def name(self) -> str:
        return "trailing_dot"

    def process(self, text: str, metadata: dict) -> str:
        if text and text[-1] not in '.!?':
            text += '.'
        return text


class OutputPipeline:
    """Пропускает текст через цепочку TextProcessor и отправляет результат."""

    def __init__(self, event_bus, config):
        self._bus = event_bus
        self._config = config
        self._processors: list[TextProcessor] = [
            StripProcessor(),
            PunctuationProcessor(),
            CapitalizationProcessor(),
            TrailingDotProcessor(),
        ]

        self._bus.text_recognized.connect(self._on_text_recognized)

    def add_processor(self, processor: TextProcessor):
        """Добавить обработчик в конец цепочки."""
        self._processors.append(processor)

    def _on_text_recognized(self, text: str, metadata: dict):
        """Обработка распознанного текста через цепочку процессоров."""
        try:
            log.info("pipeline_start: input='%s' metadata=%s", text[:100], metadata)

            processors = [StripProcessor()]
            if self._config.get('postprocessing', 'punctuation', default=True):
                processors.append(PunctuationProcessor())
            if self._config.get('postprocessing', 'capitalization', default=True):
                processors.append(CapitalizationProcessor())
            if self._config.get('postprocessing', 'trailing_dot', default=True):
                processors.append(TrailingDotProcessor())

            for proc in processors:
                text = proc.process(text, metadata)
                log.debug("pipeline_step: %s -> '%s'", proc.name, text[:100])

            if text:
                log.info("pipeline_done: output='%s'", text[:100])
                self._bus.text_processed.emit(text)
            else:
                log.warning("pipeline_done: empty text, skipping emit")
        except Exception as e:
            log.exception("pipeline_error: %s", e)
            self._bus.error_occurred.emit("OutputPipeline", str(e))
