"""Application — координатор компонентов Voice Dictation."""

import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.config_manager import config

log = logging.getLogger(__name__)


def get_version() -> str:
    """Прочитать версию из файла VERSION."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    version_file = base / 'VERSION'
    if version_file.exists():
        return version_file.read_text(encoding='utf-8').strip()
    return 'dev'


from core.event_bus import EventBus
from core.app_state import AppState, AppStateMachine
from core.audio_capture import AudioCapture
from core.model_manager import ModelManager
from core.recognizer import Recognizer
from core.output_pipeline import OutputPipeline
from core.text_inserter import TextInserter
from core.hotkeys import HotkeyManager
from core.llm_manager import LLMManager
from ui.widget import DictationWidget
from core.audio_ducking import AudioDucker
from ui.tray import TrayManager


MODEL_DEFAULT = 'large-v3'


class Application:
    """Создаёт все компоненты и связывает их через EventBus."""

    def __init__(self):
        self.bus = EventBus()
        self.state_machine = AppStateMachine(self.bus)

        # Core-сервисы
        self.model_manager = ModelManager(self.bus, config)
        self.audio = AudioCapture(self.bus, config)
        self.llm_manager = LLMManager(config, event_bus=self.bus)
        self.recognizer = Recognizer(self.bus, self.model_manager, config, llm_manager=self.llm_manager)
        self.pipeline = OutputPipeline(self.bus, config)
        self.inserter = TextInserter(self.bus, config)
        self.hotkeys = HotkeyManager(self.bus, config)
        self.ducker = AudioDucker(self.bus, config)

        # UI
        self.widget = DictationWidget(self.bus, config, self.audio)
        self.tray = TrayManager(self.bus, config, self.widget)

        # Safety timeout — восстановление из зависшего PROCESSING
        self._safety_timer = QTimer()
        self._safety_timer.setSingleShot(True)
        self._safety_timer.setInterval(30000)
        self._safety_timer.timeout.connect(self._on_safety_timeout)

        # Отдельный таймер для RECORDING — защита от «забытой» кнопки (2 минуты)
        self._recording_timeout = QTimer()
        self._recording_timeout.setSingleShot(True)
        self._recording_timeout.setInterval(120000)
        self._recording_timeout.timeout.connect(self._on_recording_timeout)

        # State machine wiring
        self.bus.recording_start.connect(lambda _: self.state_machine.transition(AppState.RECORDING))
        self.bus.recording_stop.connect(lambda: self.state_machine.transition(AppState.PROCESSING))
        self.bus.text_inserted.connect(lambda: self.state_machine.transition(AppState.READY))
        self.bus.text_recognized.connect(self._on_text_recognized)
        self.bus.model_load_started.connect(lambda _: self.state_machine.transition(AppState.MODEL_SWITCHING))
        self.bus.model_load_finished.connect(lambda _: self.state_machine.transition(AppState.READY))
        self.bus.model_load_failed.connect(lambda _: self.state_machine.transition(AppState.ERROR))
        self.bus.error_occurred.connect(self._on_error)

        # State-aware hotkey guard
        self.bus.state_changed.connect(self._on_state_changed)

        # Mode changes
        self.bus.mode_changed.connect(self._on_mode_changed)

        # Quit
        self.bus.quit_requested.connect(self._shutdown)

    def start(self):
        """Запуск приложения."""
        from core.model_catalog import get_local_models
        if not get_local_models():
            self._prompt_download_models()

        model_name = config.get('recognition', 'model', default=MODEL_DEFAULT)
        self.model_manager.load_model(model_name)

        if config.get('llm', 'enabled', default=False):
            self.llm_manager.load_model_async()

        self.audio.open_stream()
        self.hotkeys.start()
        self.widget.show()

        import ctypes
        version = get_version()
        hotkey = config.get('recognition', 'hotkey', default='f9')
        dictation_model = config.get('recognition', 'model', default=MODEL_DEFAULT)
        try:
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            is_admin = False
        banner = (
            f"Voice Dictation v{version} | "
            f"Запись: {hotkey.upper()} | "
            f"Модель: {dictation_model} | "
            f"Admin: {is_admin}"
        )
        log.info(banner)

    def _on_error(self, component, message):
        """Обработка ошибок — логирование и восстановление в READY."""
        log.error("ERROR from %s: %s (state=%s)", component, message, self.state_machine.state.name)
        self.state_machine.transition(AppState.READY)

    def _on_text_recognized(self, text, metadata):
        """Обработка пустого результата — вернуть в READY."""
        if not text.strip():
            self.state_machine.transition(AppState.READY)

    def _on_state_changed(self, state_name: str):
        """Включить hotkey только в состоянии READY. Управление safety timer."""
        enabled = state_name == "ready"
        log.debug("state_changed: %s -> hotkeys_enabled=%s", state_name, enabled)
        self.hotkeys.set_enabled(enabled)

        if state_name == "ready":
            self._safety_timer.stop()
            self._recording_timeout.stop()
        elif state_name == "recording":
            self._safety_timer.stop()
            self._recording_timeout.start()
        elif state_name == "processing":
            self._recording_timeout.stop()
            self._safety_timer.start()

    def _on_safety_timeout(self):
        """Восстановление из зависшего PROCESSING (> 30с)."""
        current = self.state_machine.state
        if current == AppState.PROCESSING:
            log.error("SAFETY TIMEOUT: stuck in PROCESSING for 30s — forcing READY")
            with self.recognizer._busy_lock:
                if self.recognizer._busy:
                    log.warning("SAFETY TIMEOUT: resetting recognizer._busy")
                    self.recognizer._busy = False
            self.state_machine.transition(AppState.READY)

    def _on_recording_timeout(self):
        """Защита от забытой записи (> 120с)."""
        current = self.state_machine.state
        if current == AppState.RECORDING:
            log.error("RECORDING TIMEOUT: recording for 120s — stopping")
            self.audio.stop_recording()
            self.state_machine.transition(AppState.READY)

    def _on_mode_changed(self, key, value):
        """Централизованная обработка переключения режимов."""
        if key == "open_settings":
            self._open_settings()
            return

        if key == "hotkey_changed":
            self.hotkeys.update_hotkey(value)
            config.set('recognition', 'hotkey', value)
            config.save()
            return

    def _open_settings(self):
        """Открыть диалог настроек с hot-apply логикой."""
        from ui.settings_dialog import SettingsDialog

        self.hotkeys.set_enabled(False)

        old_hotkey = config.get('recognition', 'hotkey', default='f9')
        old_model = config.get('recognition', 'model', default=MODEL_DEFAULT)
        old_llm_enabled = config.get('llm', 'enabled', default=False)

        dialog = SettingsDialog(config, parent=self.widget)
        result = dialog.exec()

        self.hotkeys.set_enabled(True)

        if result == dialog.DialogCode.Accepted:
            new_hotkey = config.get('recognition', 'hotkey', default='f9')
            if new_hotkey != old_hotkey:
                log.info("settings: hotkey changed '%s' -> '%s'", old_hotkey, new_hotkey)
                self.hotkeys.update_hotkey(new_hotkey)

            self.widget.dictation_model = config.get('recognition', 'model', default=MODEL_DEFAULT)
            self.widget.update()

            new_model = config.get('recognition', 'model', default=MODEL_DEFAULT)
            if new_model != old_model:
                log.info("settings: model changed '%s' -> '%s'", old_model, new_model)
                self.model_manager.load_model(new_model)

            # LLM toggle
            new_llm_enabled = config.get('llm', 'enabled', default=False)
            if new_llm_enabled and not old_llm_enabled:
                log.info("settings: LLM enabled, loading model")
                self.llm_manager.load_model_async()
            elif not new_llm_enabled and old_llm_enabled:
                log.info("settings: LLM disabled, unloading model")
                self.llm_manager.unload_model()
                self.bus.llm_load_failed.emit("")  # сброс индикатора на виджете

    def _prompt_download_models(self):
        """Первый запуск без моделей — предложить скачать."""
        reply = QMessageBox.information(
            None,
            "Voice Dictation",
            "Модели распознавания не найдены.\n"
            "Откройте менеджер моделей и скачайте хотя бы одну.",
            QMessageBox.StandardButton.Ok,
        )
        from ui.model_dialog import ModelManagerDialog
        dialog = ModelManagerDialog(config, event_bus=self.bus)
        dialog.exec()
        if dialog.model_selected:
            config.set('recognition', 'model', dialog.model_selected)
            config.save()

    def _shutdown(self):
        """Корректное завершение."""
        self.widget._save_position()
        self.recognizer.shutdown()
        self.llm_manager.unload_model()
        self.audio.close_stream()
        self.hotkeys.stop()
        self.tray._tray_icon.hide()
        self.widget.force_quit()
        QApplication.quit()
