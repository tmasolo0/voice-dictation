"""ModelManager — управление моделью Whisper."""

import logging
import threading
from faster_whisper import WhisperModel

log = logging.getLogger(__name__)

from core.config_manager import APP_DIR

MODELS_DIR = APP_DIR / "models"


class ModelManager:
    """Загрузка и потокобезопасный доступ к модели Whisper."""

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
        """Загрузить модель в фоновом потоке (только при старте)."""
        if self._model_name == model_name and self._model is not None:
            return
        self._bus.model_load_started.emit(model_name)
        threading.Thread(target=self._do_load, args=(model_name,), daemon=True).start()

    @staticmethod
    def _get_free_vram() -> int | None:
        """Свободная VRAM в байтах (None если CUDA недоступна)."""
        try:
            import torch
            if torch.cuda.is_available():
                free, _total = torch.cuda.mem_get_info()
                return free
        except ImportError:
            pass
        return None

    def _do_load(self, model_name: str):
        """Фоновая загрузка модели."""
        try:
            log.info("Загрузка модели %s...", model_name)

            device = self._config.get('recognition', 'device', default='cuda')
            compute_type = self._config.get('recognition', 'compute_type', default='float16')

            local_path = MODELS_DIR / model_name
            model_path = str(local_path) if local_path.exists() else model_name
            log.info("model_path=%s exists=%s", model_path, local_path.exists())

            free_before = self._get_free_vram() if device == 'cuda' else None

            new_model = WhisperModel(model_path, device=device, compute_type=compute_type)

            with self._lock:
                self._model = new_model
                self._model_name = model_name

            # Замер VRAM, потреблённой моделью
            if free_before is not None:
                free_after = self._get_free_vram()
                if free_after is not None:
                    vram_mb = max(0, (free_before - free_after)) // (1024 * 1024)
                    self._bus.vram_updated.emit(int(vram_mb))

            log.info("Модель %s загружена (%s)", model_name, device)
            self._bus.model_load_finished.emit(model_name)

        except Exception as e:
            log.exception("Ошибка загрузки модели: %s", e)
            self._bus.model_load_failed.emit(str(e))
