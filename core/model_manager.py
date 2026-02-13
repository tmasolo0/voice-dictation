"""ModelManager — управление моделью Whisper."""

import gc
import threading
from pathlib import Path
from faster_whisper import WhisperModel


MODELS_DIR = Path(__file__).parent.parent / "models"


class ModelManager:
    """Загрузка, переключение и потокобезопасный доступ к модели Whisper."""

    def __init__(self, event_bus, config):
        self._bus = event_bus
        self._config = config
        self._model = None
        self._model_name = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str | None:
        return self._model_name

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def get_model(self):
        """Получить модель под блокировкой. Возвращает None если не загружена."""
        with self._lock:
            return self._model

    def load_model(self, model_name: str):
        """Загрузить модель в фоновом потоке."""
        if self._model_name == model_name and self._model is not None:
            return
        self._bus.model_load_started.emit(model_name)
        threading.Thread(target=self._do_load, args=(model_name,), daemon=True).start()

    def _do_load(self, model_name: str):
        """Фоновая загрузка: создать новую, подменить под блокировкой, удалить старую."""
        try:
            print(f"Загрузка модели {model_name}...")

            device = self._config.get('recognition', 'device', default='cuda')
            compute_type = self._config.get('recognition', 'compute_type', default='float16')

            local_path = MODELS_DIR / model_name
            model_path = str(local_path) if local_path.exists() else model_name

            new_model = WhisperModel(model_path, device=device, compute_type=compute_type)

            with self._lock:
                old_model = self._model
                self._model = new_model
                self._model_name = model_name

            # Удаляем старую модель ВНЕ блокировки
            if old_model is not None:
                del old_model
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass

            print(f"Модель {model_name} загружена ({device})")
            self._bus.model_load_finished.emit(model_name)

        except Exception as e:
            print(f"Ошибка загрузки модели: {e}")
            self._bus.model_load_failed.emit(str(e))
