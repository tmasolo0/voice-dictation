"""Application — координатор компонентов Voice Dictation."""

from PyQt6.QtWidgets import QApplication

from core.config_manager import config
from core.event_bus import EventBus
from core.app_state import AppState, AppStateMachine
from core.audio_capture import AudioCapture
from core.model_manager import ModelManager
from core.recognizer import Recognizer
from core.output_pipeline import OutputPipeline
from core.text_inserter import TextInserter
from core.hotkeys import HotkeyManager
from ui.widget import DictationWidget
from ui.tray import TrayManager


MODEL_TURBO = 'large-v3-turbo'
MODEL_QUALITY = 'large-v3'
MODEL_RUSSIAN = 'whisper-podlodka-turbo'
MODEL_TRANSLATE = 'medium'

# Цикл переключения качества: turbo → quality → russian → turbo
MODEL_CYCLE = [MODEL_TURBO, MODEL_QUALITY, MODEL_RUSSIAN]


class Application:
    """Создаёт все компоненты и связывает их через EventBus."""

    def __init__(self):
        self.bus = EventBus()
        self.state_machine = AppStateMachine(self.bus)

        # Core-сервисы
        self.model_manager = ModelManager(self.bus, config)
        self.audio = AudioCapture(self.bus, config)
        self.recognizer = Recognizer(self.bus, self.model_manager, config)
        self.pipeline = OutputPipeline(self.bus)
        self.inserter = TextInserter(self.bus, config)
        self.hotkeys = HotkeyManager(self.bus, config)

        # UI
        self.widget = DictationWidget(self.bus, config)
        self.tray = TrayManager(self.bus, config, self.widget)

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
        # Загрузка модели
        translate_mode = config.get('dictation', 'translate_to_english', default=False)
        model_name = MODEL_TRANSLATE if translate_mode else config.get('recognition', 'model', default=MODEL_TURBO)
        self.model_manager.load_model(model_name)

        # Запуск сервисов
        self.audio.open_stream()
        self.hotkeys.start()
        self.widget.show()

        # Startup info
        hotkey = config.get('recognition', 'hotkey', default='f9')
        translate_hotkey = config.get('recognition', 'translate_hotkey', default='f10')
        dictation_model = config.get('recognition', 'model', default=MODEL_TURBO)
        print("=" * 40)
        print("Voice Dictation")
        print("=" * 40)
        print(f"Запись: {hotkey.upper()}")
        print(f"Перевод: {translate_hotkey.upper()}")
        print(f"Модель: {dictation_model}")
        print(f"Режим: {'EN (перевод)' if translate_mode else 'RU/EN (авто)'}")
        print("ПКМ → модель / перевод")
        print("=" * 40)

    def _on_text_recognized(self, text, metadata):
        """Обработка пустого результата — вернуть в READY."""
        if not text.strip():
            self.state_machine.transition(AppState.READY)

    def _on_state_changed(self, state_name: str):
        """Включить hotkey только в состоянии READY."""
        self.hotkeys.set_enabled(state_name == "ready")

    def _on_mode_changed(self, key, value):
        """Централизованная обработка переключения режимов."""
        if key == "open_model_manager":
            self._open_model_manager()
            return

        if key == "select_model":
            # Загрузка модели из диалога (пока диалог открыт)
            print(f"Переключение модели → {value}")
            translate_mode = config.get('dictation', 'translate_to_english', default=False)
            if not translate_mode:
                self.model_manager.load_model(value)
            self.widget.dictation_model = value
            self.widget.update()
            self.tray._sync_quality_from_config()
            return

        if key == "hotkey_changed":
            self.hotkeys.update_hotkey(value)
            config.set('recognition', 'hotkey', value)
            config.save()
            return

        if key == "translate_hotkey_changed":
            self.hotkeys.update_translate_hotkey(value)
            config.set('recognition', 'translate_hotkey', value)
            config.save()
            return

        if key == "quality_toggle":
            current = config.get('recognition', 'model', default=MODEL_TURBO)
            try:
                idx = MODEL_CYCLE.index(current)
            except ValueError:
                idx = 0
            new_model = MODEL_CYCLE[(idx + 1) % len(MODEL_CYCLE)]
            config.set('recognition', 'model', new_model)
            config.save()

            # Переключаем модель, если не в режиме перевода
            translate_mode = config.get('dictation', 'translate_to_english', default=False)
            if not translate_mode:
                self.model_manager.load_model(new_model)

        elif key == "translate_toggle":
            current = config.get('dictation', 'translate_to_english', default=False)
            new_value = not current
            config.set('dictation', 'translate_to_english', new_value)
            config.save()

            dictation_model = config.get('recognition', 'model', default=MODEL_TURBO)
            new_model = MODEL_TRANSLATE if new_value else dictation_model
            self.model_manager.load_model(new_model)

    def _open_model_manager(self):
        """Открыть диалог управления моделями."""
        from ui.model_dialog import ModelManagerDialog
        dialog = ModelManagerDialog(config, event_bus=self.bus, parent=self.widget)
        dialog.exec()

    def _shutdown(self):
        """Корректное завершение."""
        self.widget._save_position()
        self.recognizer.shutdown()
        self.audio.close_stream()
        self.hotkeys.stop()
        QApplication.quit()
