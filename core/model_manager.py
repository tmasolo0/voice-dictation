"""ModelManager — управление ASR-моделью (Qwen3-ASR ONNX)."""

import logging
import threading

from core.qwen3_asr import Qwen3ASRBackend

log = logging.getLogger(__name__)

from core.config_manager import APP_DIR

MODELS_DIR = APP_DIR / "models"


class ModelManager:
    """Загрузка и потокобезопасный доступ к ASR-модели."""

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

    def get_model(self) -> Qwen3ASRBackend | None:
        """Получить модель под блокировкой. Возвращает None если не загружена."""
        with self._lock:
            return self._model

    def load_model(self, model_name: str):
        """Загрузить модель в фоновом потоке."""
        if self._model_name == model_name and self._model is not None:
            return
        self._bus.model_load_started.emit(model_name)
        threading.Thread(target=self._do_load, args=(model_name,), daemon=True).start()

    @staticmethod
    def _get_free_vram() -> int | None:
        """Свободная VRAM в байтах (None если CUDA недоступна)."""
        try:
            import onnxruntime as ort
            if 'CUDAExecutionProvider' in ort.get_available_providers():
                # Пробуем через torch если доступен
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

            local_path = MODELS_DIR / model_name
            model_path = str(local_path) if local_path.exists() else model_name
            log.debug("model_path=%s exists=%s", model_path, local_path.exists())

            free_before = self._get_free_vram() if device == 'cuda' else None

            # Выгрузить предыдущую модель
            with self._lock:
                if self._model is not None:
                    self._model.unload()
                    self._model = None

            backend = Qwen3ASRBackend()
            backend.load(model_path, device=device)

            with self._lock:
                self._model = backend
                self._model_name = model_name

            # Замер VRAM
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
