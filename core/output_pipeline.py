"""OutputPipeline — цепочка обработки распознанного текста."""

from abc import ABC, abstractmethod


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


class OutputPipeline:
    """Пропускает текст через цепочку TextProcessor и отправляет результат."""

    def __init__(self, event_bus):
        self._bus = event_bus
        self._processors: list[TextProcessor] = [StripProcessor()]

        self._bus.text_recognized.connect(self._on_text_recognized)

    def add_processor(self, processor: TextProcessor):
        """Добавить обработчик в конец цепочки."""
        self._processors.append(processor)

    def _on_text_recognized(self, text: str, metadata: dict):
        """Обработка распознанного текста через цепочку процессоров."""
        for proc in self._processors:
            text = proc.process(text, metadata)

        if text:
            self._bus.text_processed.emit(text)
