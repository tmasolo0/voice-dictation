"""Application — координатор компонентов Voice Dictation."""

import logging
import sys
from pathlib import Path

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
from core.history_manager import HistoryManager
from ui.widget import DictationWidget
from ui.tray import TrayManager
from ui.preview_popup import PreviewPopup


MODEL_TURBO = 'large-v3-turbo'


class Application:
    """Создаёт все компоненты и связывает их через EventBus."""

    def __init__(self):
        self.bus = EventBus()
        self.state_machine = AppStateMachine(self.bus)

        # Core-сервисы
        self.model_manager = ModelManager(self.bus, config)
        self.audio = AudioCapture(self.bus, config)
        self.recognizer = Recognizer(self.bus, self.model_manager, config)
        self.pipeline = OutputPipeline(self.bus, config)
        self.inserter = TextInserter(self.bus, config)
        self.hotkeys = HotkeyManager(self.bus, config)
        self.history = HistoryManager(self.bus, self.model_manager)

        # UI
        self.widget = DictationWidget(self.bus, config)
        self.tray = TrayManager(self.bus, config, self.widget)

        # Preview popup — перехватываем text_processed до TextInserter
        self.bus.text_processed.disconnect(self.inserter._on_text_ready)
        self.bus.text_processed.connect(self._on_text_processed)

        self.preview_popup = PreviewPopup(self.widget)
        self.preview_popup.insert_requested.connect(self._on_preview_insert)
        self.preview_popup.cancel_requested.connect(self._on_preview_cancel)
        self.preview_popup.redictate_requested.connect(self._on_redictate)
        self._redictate_mode = False

        # State machine wiring
        self.bus.recording_start.connect(lambda _: self.state_machine.transition(AppState.RECORDING))
        self.bus.recording_stop.connect(lambda: self.state_machine.transition(AppState.PROCESSING))
        self.bus.text_inserted.connect(lambda: self.state_machine.transition(AppState.READY))
        self.bus.text_recognized.connect(self._on_text_recognized)
        self.bus.model_load_started.connect(lambda _: self.state_machine.transition(AppState.MODEL_SWITCHING))
        self.bus.model_load_finished.connect(lambda _: self.state_machine.transition(AppState.READY))
        self.bus.model_load_failed.connect(lambda _: self.state_machine.transition(AppState.ERROR))
        self.bus.error_occurred.connect(lambda *a: self.state_machine.transition(AppState.READY))

        # State-aware hotkey guard
        self.bus.state_changed.connect(self._on_state_changed)

        # Mode changes
        self.bus.mode_changed.connect(self._on_mode_changed)

        # Quit
        self.bus.quit_requested.connect(self._shutdown)

    def start(self):
        """Запуск приложения."""
        # Проверка наличия моделей
        from core.model_catalog import get_local_models
        if not get_local_models():
            self._prompt_download_models()

        # Загрузка модели
        model_name = config.get('recognition', 'model', default=MODEL_TURBO)
        self.model_manager.load_model(model_name)

        # Запуск сервисов
        self.audio.open_stream()
        self.hotkeys.start()
        self.widget.show()

        # Startup info
        import ctypes
        version = get_version()
        hotkey = config.get('recognition', 'hotkey', default='f9')
        history_hotkey = config.get('recognition', 'history_hotkey', default='ctrl+h')
        dictation_model = config.get('recognition', 'model', default=MODEL_TURBO)
        preview_enabled = config.get('preview', 'enabled', default=False)
        auto_delay = config.get('preview', 'auto_insert_delay', default=5)
        try:
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            is_admin = False
        banner = (
            f"Voice Dictation v{version} | "
            f"Запись: {hotkey.upper()} | "
            f"История: {history_hotkey.upper()} | "
            f"Модель: {dictation_model} | "
            f"Preview: {preview_enabled} (delay={auto_delay}s) | "
            f"Admin: {is_admin}"
        )
        log.info(banner)

    def _on_text_processed(self, text: str):
        """Координация preview popup: показать или вставить мгновенно."""
        log.info("on_text_processed: text_len=%d redictate=%s", len(text), self._redictate_mode)

        if self._redictate_mode:
            self._redictate_mode = False
            auto_delay = config.get('preview', 'auto_insert_delay', default=5)
            self.preview_popup.update_text(text)
            if auto_delay > 0:
                self.preview_popup.restart_timer(auto_delay)
            log.info("on_text_processed: redictate mode, updating preview")
            return

        preview_enabled = config.get('preview', 'enabled', default=False)
        auto_delay = config.get('preview', 'auto_insert_delay', default=5)

        if not preview_enabled or auto_delay == 0:
            log.info("on_text_processed: direct insert (preview=%s delay=%d)",
                     preview_enabled, auto_delay)
            self.inserter._on_text_ready(text)
            return

        log.info("on_text_processed: showing preview (delay=%d)", auto_delay)
        self.preview_popup.show_preview(text, auto_delay)

    def _on_preview_insert(self, text: str):
        """Вставка текста из preview popup (возможно отредактированного)."""
        log.info("on_preview_insert: text_len=%d", len(text))
        self._redictate_mode = False
        self.inserter._on_text_ready(text)

    def _on_preview_cancel(self):
        """Отмена вставки из preview popup."""
        self._redictate_mode = False
        self.state_machine.transition(AppState.READY)

    def _on_redictate(self):
        """Re-dictate: остановить таймер, перейти в режим ожидания записи."""
        self._redictate_mode = True
        self.preview_popup.stop_timer()
        self.preview_popup.set_waiting_state()
        self.state_machine.transition(AppState.READY)

    def _on_text_recognized(self, text, metadata):
        """Обработка пустого результата — вернуть в READY."""
        if not text.strip():
            self.state_machine.transition(AppState.READY)

    def _on_state_changed(self, state_name: str):
        """Включить hotkey только в состоянии READY."""
        enabled = state_name == "ready"
        log.debug("state_changed: %s -> hotkeys_enabled=%s", state_name, enabled)
        self.hotkeys.set_enabled(enabled)

    def _on_mode_changed(self, key, value):
        """Централизованная обработка переключения режимов."""
        if key == "open_history":
            self._open_history()
            return

        if key == "open_settings":
            self._open_settings()
            return

        if key == "hotkey_changed":
            self.hotkeys.update_hotkey(value)
            config.set('recognition', 'hotkey', value)
            config.save()
            return

    def _open_history(self):
        """Открыть диалог истории диктовок."""
        import win32gui
        from ui.history_dialog import HistoryDialog

        self.hotkeys.set_enabled(False)
        target_hwnd = win32gui.GetForegroundWindow()
        dialog = HistoryDialog(self.history, target_hwnd=target_hwnd, parent=self.widget)
        dialog.exec()
        self.hotkeys.set_enabled(True)

    def _open_settings(self):
        """Открыть диалог настроек с hot-apply логикой."""
        from ui.settings_dialog import SettingsDialog

        # Отключить hotkeys на время модального диалога
        self.hotkeys.set_enabled(False)

        # Снапшот для сравнения
        old_hotkey = config.get('recognition', 'hotkey', default='f9')
        old_history_hotkey = config.get('recognition', 'history_hotkey', default='ctrl+h')
        old_size = config.get('widget', 'size', default=100)
        old_model = config.get('recognition', 'model', default=MODEL_TURBO)

        dialog = SettingsDialog(config, parent=self.widget)
        result = dialog.exec()

        # Вернуть hotkeys
        self.hotkeys.set_enabled(True)

        if result == dialog.DialogCode.Accepted:
            # Hot-apply: горячие клавиши
            new_hotkey = config.get('recognition', 'hotkey', default='f9')
            new_history_hotkey = config.get('recognition', 'history_hotkey', default='ctrl+h')
            if new_hotkey != old_hotkey:
                log.info("settings: hotkey changed '%s' -> '%s'", old_hotkey, new_hotkey)
                self.hotkeys.update_hotkey(new_hotkey)
            if new_history_hotkey != old_history_hotkey:
                log.info("settings: history_hotkey changed '%s' -> '%s'",
                         old_history_hotkey, new_history_hotkey)
                self.hotkeys.update_history_hotkey(new_history_hotkey)

            # Hot-apply: размер виджета
            new_size = config.get('widget', 'size', default=100)
            if new_size != old_size:
                self.widget.setFixedSize(new_size, new_size)
                self.widget.update()

            # Hot-apply: смена модели (горячая перезагрузка)
            new_model = config.get('recognition', 'model', default=MODEL_TURBO)
            if new_model != old_model:
                log.info("settings: model changed '%s' -> '%s'", old_model, new_model)
                self.model_manager.load_model(new_model)

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
        self.audio.close_stream()
        self.hotkeys.stop()
        self.history.close()
        QApplication.quit()
