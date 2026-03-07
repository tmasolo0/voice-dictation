"""EventBus — центральная шина сигналов приложения."""

from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    """Единая точка коммуникации между компонентами через PyQt signals."""

    # Жизненный цикл записи
    recording_start = pyqtSignal(object)     # hwnd целевого окна
    recording_stop = pyqtSignal()

    # Поток данных
    audio_ready = pyqtSignal(object)          # np.ndarray через object (PyQt6 не знает numpy типы)
    text_recognized = pyqtSignal(str, dict)   # текст, метаданные
    text_processed = pyqtSignal(str)          # финальный текст после пайплайна
    text_inserted = pyqtSignal()

    # Состояние
    state_changed = pyqtSignal(str)           # AppState.name.lower()

    # Управление моделью (Whisper)
    model_load_started = pyqtSignal(str)      # имя модели
    model_load_finished = pyqtSignal(str)     # имя модели
    model_load_failed = pyqtSignal(str)       # сообщение об ошибке

    # Управление LLM
    llm_load_started = pyqtSignal()
    llm_load_finished = pyqtSignal()
    llm_load_failed = pyqtSignal(str)         # сообщение об ошибке

    # VRAM
    vram_updated = pyqtSignal(int)            # MB видеопамяти модели

    # Режимы
    mode_changed = pyqtSignal(str, object)    # ключ, значение

    # Жизненный цикл приложения
    quit_requested = pyqtSignal()
    error_occurred = pyqtSignal(str, str)     # компонент, сообщение
