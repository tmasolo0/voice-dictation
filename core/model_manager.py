"""ModelManager — управление моделью Whisper."""

import gc
import sys
import time
import traceback
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
        self._loading = False

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
        if self._loading:
            print(f"Загрузка уже идёт, пропуск запроса на {model_name}")
            return
        self._loading = True
        self._bus.model_load_started.emit(model_name)
        threading.Thread(target=self._do_load, args=(model_name,), daemon=True).start()

    def _do_load(self, model_name: str):
        """Фоновая загрузка: выгрузить старую, загрузить новую (safe swap для VRAM)."""
        try:
            print(f"Загрузка модели {model_name}...")
            sys.stdout.flush()

            device = self._config.get('recognition', 'device', default='cuda')
            compute_type = self._config.get('recognition', 'compute_type', default='float16')

            # Выгрузить старую модель ДО загрузки новой (предотвращает OOM)
            print("[1] Захват lock, извлечение старой модели...")
            sys.stdout.flush()
            with self._lock:
                old_model = self._model
                self._model = None

            if old_model is not None:
                print(f"[2] del old_model (refs: {sys.getrefcount(old_model) - 1})...")
                sys.stdout.flush()
                del old_model
                print("[3] gc.collect()...")
                sys.stdout.flush()
                gc.collect()
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        print("[4] torch.cuda.empty_cache() done")
                except ImportError:
                    print("[4] torch not available, skip")
                sys.stdout.flush()
                time.sleep(1)
                print("[5] Старая модель выгружена из VRAM")
                sys.stdout.flush()
            else:
                print("[2-5] Старая модель отсутствует, пропуск очистки")
                sys.stdout.flush()

            local_path = MODELS_DIR / model_name
            model_path = str(local_path) if local_path.exists() else model_name
            print(f"[6] Создание WhisperModel({model_path}, {device}, {compute_type})...")
            sys.stdout.flush()

            new_model = WhisperModel(model_path, device=device, compute_type=compute_type)

            print("[7] Модель создана, сохранение...")
            sys.stdout.flush()
            with self._lock:
                self._model = new_model
                self._model_name = model_name

            print(f"Модель {model_name} загружена ({device})")
            sys.stdout.flush()
            self._loading = False
            self._bus.model_load_finished.emit(model_name)

        except Exception as e:
            print(f"Ошибка загрузки модели: {e}")
            traceback.print_exc()
            sys.stdout.flush()
            self._loading = False
            self._bus.model_load_failed.emit(str(e))
