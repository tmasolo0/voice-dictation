"""SettingsDialog -- tabbed QDialog for all application settings."""

import copy
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config_manager import ConfigManager, DEFAULT_CONFIG, DICTIONARIES_DIR
from core.model_catalog import (
    MODEL_CATALOG, MODEL_LABELS, MODELS_DIR, ALLOW_PATTERNS,
    get_local_models, is_model_downloaded,
)
from ui.model_dialog import ModelDownloadThread


# ---------------------------------------------------------------------------
# Qt key code -> keyboard library string mapping
# ---------------------------------------------------------------------------

_QT_KEY_MAP = {
    Qt.Key.Key_F1: "f1", Qt.Key.Key_F2: "f2", Qt.Key.Key_F3: "f3",
    Qt.Key.Key_F4: "f4", Qt.Key.Key_F5: "f5", Qt.Key.Key_F6: "f6",
    Qt.Key.Key_F7: "f7", Qt.Key.Key_F8: "f8", Qt.Key.Key_F9: "f9",
    Qt.Key.Key_F10: "f10", Qt.Key.Key_F11: "f11", Qt.Key.Key_F12: "f12",
    Qt.Key.Key_A: "a", Qt.Key.Key_B: "b", Qt.Key.Key_C: "c",
    Qt.Key.Key_D: "d", Qt.Key.Key_E: "e", Qt.Key.Key_F: "f",
    Qt.Key.Key_G: "g", Qt.Key.Key_H: "h", Qt.Key.Key_I: "i",
    Qt.Key.Key_J: "j", Qt.Key.Key_K: "k", Qt.Key.Key_L: "l",
    Qt.Key.Key_M: "m", Qt.Key.Key_N: "n", Qt.Key.Key_O: "o",
    Qt.Key.Key_P: "p", Qt.Key.Key_Q: "q", Qt.Key.Key_R: "r",
    Qt.Key.Key_S: "s", Qt.Key.Key_T: "t", Qt.Key.Key_U: "u",
    Qt.Key.Key_V: "v", Qt.Key.Key_W: "w", Qt.Key.Key_X: "x",
    Qt.Key.Key_Y: "y", Qt.Key.Key_Z: "z",
    Qt.Key.Key_0: "0", Qt.Key.Key_1: "1", Qt.Key.Key_2: "2",
    Qt.Key.Key_3: "3", Qt.Key.Key_4: "4", Qt.Key.Key_5: "5",
    Qt.Key.Key_6: "6", Qt.Key.Key_7: "7", Qt.Key.Key_8: "8",
    Qt.Key.Key_9: "9",
    Qt.Key.Key_Space: "space", Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter", Qt.Key.Key_Escape: "escape",
    Qt.Key.Key_Tab: "tab", Qt.Key.Key_Backspace: "backspace",
    Qt.Key.Key_Delete: "delete", Qt.Key.Key_Insert: "insert",
    Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "pageup", Qt.Key.Key_PageDown: "pagedown",
    Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down",
    Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right",
    Qt.Key.Key_CapsLock: "capslock", Qt.Key.Key_NumLock: "numlock",
    Qt.Key.Key_ScrollLock: "scrolllock",
    Qt.Key.Key_Print: "printscreen", Qt.Key.Key_Pause: "pause",
    Qt.Key.Key_Menu: "menu",
}

# Modifier keys — теперь поддерживаются как самостоятельные (Left/Right через scan code)
_MODIFIER_KEYS = {
    Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
}

# Native scan code -> modifier-only hotkey string
_SCAN_TO_MODIFIER = {
    0x1D: "left ctrl",   0x11D: "right ctrl",
    0x2A: "left shift",  0x36: "right shift",
    0x38: "left alt",    0x138: "right alt",
}


class HotkeyEdit(QLineEdit):
    """Custom widget that captures a hotkey (single key or combo) on click."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self._hotkey = ""
        self._recording = False

    def hotkey(self) -> str:
        return self._hotkey

    def setHotkey(self, value: str):
        self._hotkey = value
        self.setText(value if value else "")

    # -- events ---------------------------------------------------------------

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._recording = True
        self.setText("Нажмите клавишу...")

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._recording = False
        self.setText(self._hotkey if self._hotkey else "")

    def keyPressEvent(self, event):
        if not self._recording:
            return

        key = event.key()

        # Modifier-only: определить Left/Right через native scan code
        if key in _MODIFIER_KEYS:
            scan = event.nativeScanCode()
            mod_name = _SCAN_TO_MODIFIER.get(scan)
            if mod_name is None:
                return
            self._hotkey = mod_name
            self._recording = False
            self.setText(mod_name)
            self.clearFocus()
            return

        key_str = _QT_KEY_MAP.get(Qt.Key(key))
        if key_str is None:
            return

        parts = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        parts.append(key_str)

        combo = "+".join(parts)
        self._hotkey = combo
        self._recording = False
        self.setText(combo)
        self.clearFocus()



# ---------------------------------------------------------------------------
# Languages for recognition
# ---------------------------------------------------------------------------

_LANGUAGES = [
    ("auto", "Авто"),
    ("ru", "Русский"),
    ("en", "English"),
    ("de", "Deutsch"),
    ("fr", "Francais"),
    ("es", "Espanol"),
    ("zh", "Chinese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
]


class LLMConvertThread(QThread):
    """Скачивание и конвертация LLM модели в фоне."""

    progress_msg = pyqtSignal(str)
    finished_ok = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            from scripts.convert_llm import convert
            self.progress_msg.emit("Скачивание и конвертация модели...")
            convert()
            self.finished_ok.emit()
        except Exception as e:
            self.error.emit(str(e))


class SettingsDialog(QDialog):
    """Tabbed settings dialog with 5 tabs and OK/Cancel/Reset to Defaults."""

    RESTART_KEYS = {"recognition.device", "recognition.compute_type"}

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._changed_settings: dict = {}
        self._download_thread = None

        self.setWindowTitle("Настройки")
        self.setMinimumSize(550, 500)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
        )

        self._build_ui()
        self._load_values()
        self._initial_values = self._collect_all_values()

    # ======================================================================
    # UI Construction
    # ======================================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._build_tab_general()
        self._build_tab_recognition()
        self._build_tab_postprocessing()
        self._build_tab_dictionary()
        self._build_tab_models()

        # Button box
        self._btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._btn_reset = self._btn_box.addButton(
            "Сброс к умолчаниям", QDialogButtonBox.ButtonRole.ResetRole
        )
        self._btn_box.accepted.connect(self._on_ok)
        self._btn_box.rejected.connect(self._on_cancel)
        self._btn_reset.clicked.connect(self._on_reset_defaults)
        layout.addWidget(self._btn_box)

    # -- Tab 1: General ---------------------------------------------------

    def _build_tab_general(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self._hotkey_edit = HotkeyEdit()
        form.addRow("Горячая клавиша записи:", self._hotkey_edit)

        self._language_combo = QComboBox()
        for code, label in _LANGUAGES:
            self._language_combo.addItem(label, code)
        form.addRow("Язык распознавания:", self._language_combo)

        self._autostart_check = QCheckBox("Запускать при старте Windows")
        form.addRow(self._autostart_check)

        self._start_minimized_check = QCheckBox("Запуск в свёрнутом виде")
        form.addRow(self._start_minimized_check)

        self._audio_gain_spin = QDoubleSpinBox()
        self._audio_gain_spin.setRange(0.1, 5.0)
        self._audio_gain_spin.setSingleStep(0.1)
        self._audio_gain_spin.setDecimals(1)
        gain_layout = QHBoxLayout()
        gain_layout.addWidget(self._audio_gain_spin)
        gain_hint = QLabel("1.0 = без усиления")
        gain_hint.setStyleSheet("color: gray;")
        gain_layout.addWidget(gain_hint)
        gain_layout.addStretch()
        form.addRow("Усиление микрофона:", gain_layout)

        self._sound_effects_check = QCheckBox("Звуковые эффекты при записи")
        form.addRow(self._sound_effects_check)

        self._audio_ducking_check = QCheckBox("Приглушать звук при записи")
        form.addRow(self._audio_ducking_check)

        self._tabs.addTab(tab, "Основные")

    # -- Tab 2: Recognition -----------------------------------------------

    def _build_tab_recognition(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)

        # --- Model group ---
        model_group = QGroupBox("Модель")
        model_form = QFormLayout(model_group)

        self._model_combo = QComboBox()
        local_models = get_local_models()
        for m in local_models:
            label = MODEL_LABELS.get(m, m)
            self._model_combo.addItem(f"{label} ({m})", m)
        if not local_models:
            self._model_combo.addItem("(нет моделей)", "")
        model_form.addRow("Модель \u2605:", self._model_combo)

        self._device_combo = QComboBox()
        self._device_combo.addItem("CUDA (GPU)", "cuda")
        self._device_combo.addItem("CPU", "cpu")
        model_form.addRow("Устройство \u2605:", self._device_combo)

        self._compute_combo = QComboBox()
        for val in ("float16", "int8_float16", "int8"):
            self._compute_combo.addItem(val, val)
        model_form.addRow("Точность \u2605:", self._compute_combo)

        restart_label = QLabel("\u2605 = требует перезапуск")
        restart_label.setStyleSheet("color: gray; font-style: italic;")
        model_form.addRow(restart_label)

        outer.addWidget(model_group)

        # --- Quality group ---
        quality_group = QGroupBox("Параметры качества")
        qf = QFormLayout(quality_group)

        self._beam_size_spin = QSpinBox()
        self._beam_size_spin.setRange(1, 10)
        qf.addRow("Ширина поиска (beam):", self._beam_size_spin)
        qf.addRow("", QLabel("Ширина beam search (больше = точнее, медленнее)"))

        self._condition_prev_check = QCheckBox("Использовать предыдущий сегмент как контекст")
        qf.addRow("", self._condition_prev_check)

        self._compression_spin = QDoubleSpinBox()
        self._compression_spin.setRange(1.0, 5.0)
        self._compression_spin.setSingleStep(0.1)
        self._compression_spin.setDecimals(1)
        qf.addRow("Порог сжатия:", self._compression_spin)
        qf.addRow("", QLabel("Порог сжатия — фильтр повторяющегося текста"))

        self._log_prob_spin = QDoubleSpinBox()
        self._log_prob_spin.setRange(-5.0, 0.0)
        self._log_prob_spin.setSingleStep(0.1)
        self._log_prob_spin.setDecimals(1)
        qf.addRow("Порог вероятности:", self._log_prob_spin)
        qf.addRow("", QLabel("Порог вероятности — фильтр низкой уверенности"))

        self._no_speech_spin = QDoubleSpinBox()
        self._no_speech_spin.setRange(0.0, 1.0)
        self._no_speech_spin.setSingleStep(0.1)
        self._no_speech_spin.setDecimals(1)
        qf.addRow("Порог тишины:", self._no_speech_spin)
        qf.addRow("", QLabel("Порог тишины — пропуск тихих сегментов"))

        self._repetition_spin = QDoubleSpinBox()
        self._repetition_spin.setRange(1.0, 3.0)
        self._repetition_spin.setSingleStep(0.1)
        self._repetition_spin.setDecimals(1)
        qf.addRow("Штраф повтора:", self._repetition_spin)
        qf.addRow("", QLabel("Штраф за повторение (>1.0 = штраф)"))

        self._no_repeat_ngram_spin = QSpinBox()
        self._no_repeat_ngram_spin.setRange(0, 10)
        qf.addRow("Размер N-грамм:", self._no_repeat_ngram_spin)
        qf.addRow("", QLabel("Запрет повтора N-грамм подряд"))

        self._hallucination_spin = QDoubleSpinBox()
        self._hallucination_spin.setRange(0.0, 10.0)
        self._hallucination_spin.setSingleStep(0.5)
        self._hallucination_spin.setDecimals(1)
        qf.addRow("Фильтр галлюцинаций:", self._hallucination_spin)
        qf.addRow("", QLabel("Фильтр галлюцинаций на тишине (секунды)"))

        outer.addWidget(quality_group)

        # --- VAD group ---
        vad_group = QGroupBox("VAD (детектор речи)")
        vf = QFormLayout(vad_group)

        self._vad_threshold_spin = QDoubleSpinBox()
        self._vad_threshold_spin.setRange(0.0, 1.0)
        self._vad_threshold_spin.setSingleStep(0.05)
        self._vad_threshold_spin.setDecimals(2)
        vf.addRow("Чувствительность:", self._vad_threshold_spin)

        self._vad_min_speech_spin = QSpinBox()
        self._vad_min_speech_spin.setRange(50, 2000)
        self._vad_min_speech_spin.setSuffix(" мс")
        vf.addRow("Мин. длина речи:", self._vad_min_speech_spin)

        self._vad_min_silence_spin = QSpinBox()
        self._vad_min_silence_spin.setRange(100, 3000)
        self._vad_min_silence_spin.setSuffix(" мс")
        vf.addRow("Мин. длина паузы:", self._vad_min_silence_spin)

        outer.addWidget(vad_group)
        outer.addStretch()

        self._tabs.addTab(tab, "Распознавание")

    # -- Tab 3: Post-processing -------------------------------------------

    def _build_tab_postprocessing(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # --- LLM group ---
        llm_group = QGroupBox("LLM-коррекция")
        llm_layout = QVBoxLayout(llm_group)

        self._llm_check = QCheckBox("Использовать LLM для коррекции текста")
        self._llm_check.toggled.connect(self._on_llm_toggled)
        llm_layout.addWidget(self._llm_check)

        self._llm_status_label = QLabel("")
        self._llm_status_label.setStyleSheet("color: gray;")
        llm_layout.addWidget(self._llm_status_label)

        self._llm_download_btn = QPushButton("Скачать модель")
        self._llm_download_btn.clicked.connect(self._on_llm_download)
        self._llm_download_btn.hide()
        llm_layout.addWidget(self._llm_download_btn)

        self._llm_progress = QProgressBar()
        self._llm_progress.setRange(0, 0)  # indeterminate
        self._llm_progress.hide()
        llm_layout.addWidget(self._llm_progress)

        llm_hint = QLabel("Исправляет пунктуацию, капитализацию и ошибки. ~3 GB VRAM.")
        llm_hint.setStyleSheet("color: gray; font-style: italic;")
        llm_hint.setWordWrap(True)
        llm_layout.addWidget(llm_hint)

        layout.addWidget(llm_group)

        # --- Regex group ---
        regex_group = QGroupBox("Regex-обработка")
        regex_layout = QVBoxLayout(regex_group)

        self._punct_check = QCheckBox("Нормализация пробелов вокруг знаков препинания")
        regex_layout.addWidget(self._punct_check)

        self._capital_check = QCheckBox("Заглавная буква в начале и после .!?")
        regex_layout.addWidget(self._capital_check)

        self._trailing_dot_check = QCheckBox("Добавлять точку в конце, если нет пунктуации")
        regex_layout.addWidget(self._trailing_dot_check)

        self._regex_disabled_hint = QLabel("При включённой LLM regex-обработка не используется")
        self._regex_disabled_hint.setStyleSheet("color: orange; font-style: italic;")
        self._regex_disabled_hint.hide()
        regex_layout.addWidget(self._regex_disabled_hint)

        layout.addWidget(regex_group)
        layout.addStretch()

        self._tabs.addTab(tab, "Постобработка")

        self._llm_convert_thread = None
        self._update_llm_status()

    # -- LLM helpers ------------------------------------------------------

    def _update_llm_status(self):
        """Обновить статус LLM-модели в UI."""
        from core.llm_manager import LLMManager, MODELS_DIR
        model_name = self._config.get('llm', 'model', default='qwen2.5-1.5b-ct2')
        model_path = MODELS_DIR / model_name / "model.bin"
        if model_path.exists():
            self._llm_status_label.setText("Модель загружена")
            self._llm_download_btn.hide()
        else:
            self._llm_status_label.setText("Модель не скачана")
            self._llm_download_btn.show()
            if self._llm_check.isChecked():
                self._llm_check.setChecked(False)

    def _on_llm_toggled(self, checked: bool):
        """Переключение LLM — заблокировать regex-чекбоксы."""
        from core.llm_manager import MODELS_DIR
        model_name = self._config.get('llm', 'model', default='qwen2.5-1.5b-ct2')
        model_exists = (MODELS_DIR / model_name / "model.bin").exists()

        if checked and not model_exists:
            reply = QMessageBox.question(
                self,
                "Скачать модель?",
                "Для LLM-коррекции нужна модель Qwen2.5-1.5B (~3 GB).\nСкачать и конвертировать?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_llm_download()
            else:
                self._llm_check.setChecked(False)
            return

        self._punct_check.setEnabled(not checked)
        self._capital_check.setEnabled(not checked)
        self._trailing_dot_check.setEnabled(not checked)
        self._regex_disabled_hint.setVisible(checked)

    def _on_llm_download(self):
        """Запустить скачивание + конвертацию LLM."""
        if self._llm_convert_thread is not None and self._llm_convert_thread.isRunning():
            QMessageBox.warning(self, "Конвертация", "Дождитесь завершения текущей конвертации")
            return

        self._llm_convert_thread = LLMConvertThread()
        self._llm_convert_thread.progress_msg.connect(self._on_llm_progress_msg)
        self._llm_convert_thread.finished_ok.connect(self._on_llm_convert_finished)
        self._llm_convert_thread.error.connect(self._on_llm_convert_error)

        self._llm_progress.show()
        self._llm_download_btn.setEnabled(False)
        self._llm_status_label.setText("Скачивание и конвертация...")
        self._llm_convert_thread.start()

    def _on_llm_progress_msg(self, msg: str):
        self._llm_status_label.setText(msg)

    def _on_llm_convert_finished(self):
        self._llm_progress.hide()
        self._llm_download_btn.setEnabled(True)
        self._llm_convert_thread = None
        self._update_llm_status()
        self._llm_status_label.setText("Модель готова")
        self._llm_check.setChecked(True)

    def _on_llm_convert_error(self, msg: str):
        self._llm_progress.hide()
        self._llm_download_btn.setEnabled(True)
        self._llm_convert_thread = None
        self._llm_status_label.setText(f"Ошибка: {msg}")
        self._llm_check.setChecked(False)

    # -- Tab 5: Dictionary ------------------------------------------------

    def _build_tab_dictionary(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel("Выберите доменные словари для улучшения распознавания терминов")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._dict_checks: dict[str, QCheckBox] = {}
        active = self._config.get("dictionaries", "active", default=[])

        if DICTIONARIES_DIR.exists():
            for f in sorted(DICTIONARIES_DIR.iterdir()):
                if f.suffix == ".txt" and f.is_file():
                    domain = f.stem
                    display = domain.upper() if domain.lower() == domain and len(domain) <= 3 else domain.capitalize()
                    cb = QCheckBox(display)
                    cb.setChecked(domain in active)
                    self._dict_checks[domain] = cb
                    layout.addWidget(cb)

        layout.addStretch()
        self._tabs.addTab(tab, "Словари")

    # -- Tab 6: Models ----------------------------------------------------

    def _build_tab_models(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self._models_table = QTableWidget()
        self._models_table.setColumnCount(4)
        self._models_table.setHorizontalHeaderLabels(["Модель", "Размер", "Статус", ""])
        self._models_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._models_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._models_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._models_table.verticalHeader().hide()
        layout.addWidget(self._models_table)

        self._model_progress = QProgressBar()
        self._model_progress.hide()
        layout.addWidget(self._model_progress)

        self._model_status = QLabel("")
        layout.addWidget(self._model_status)

        self._tabs.addTab(tab, "Модели")
        self._populate_models_table()

    def _populate_models_table(self):
        active_model = self._config.get("recognition", "model", default="large-v3-turbo")
        models = list(MODEL_CATALOG.items())
        self._models_table.setRowCount(len(models))

        for row, (name, info) in enumerate(models):
            downloaded = is_model_downloaded(name)
            is_active = (name == active_model)

            self._models_table.setItem(row, 0, QTableWidgetItem(f"{name}\n{info['description']}"))
            self._models_table.setItem(row, 1, QTableWidgetItem(f"{info['size_gb']:.1f} GB"))

            if is_active:
                status = "Активна"
            elif downloaded:
                status = "Установлена"
            elif not info["downloadable"]:
                status = "Ручная установка"
            else:
                status = "Не скачана"
            self._models_table.setItem(row, 2, QTableWidgetItem(status))

            btn = QPushButton()
            if is_active:
                btn.setText("Активна")
                btn.setEnabled(False)
            elif downloaded:
                btn.setText("Выбрать")
                btn.clicked.connect(lambda checked, n=name: self._on_model_select(n))
            elif info["downloadable"]:
                btn.setText("Скачать")
                btn.clicked.connect(lambda checked, n=name: self._on_model_download(n))
            else:
                btn.setText("—")
                btn.setEnabled(False)
            self._models_table.setCellWidget(row, 3, btn)

        self._models_table.resizeRowsToContents()

    def _on_model_select(self, model_name):
        self._config.set("recognition", "model", model_name)
        self._config.save()
        self._populate_models_table()
        # Синхронизировать combo модели на вкладке "Распознавание"
        self._sync_model_combo(model_name)
        self._model_status.setText(f"Модель {model_name} будет загружена при нажатии OK")

    def _sync_model_combo(self, model_name: str):
        """Синхронизировать _model_combo на вкладке 'Распознавание' с выбранной моделью."""
        idx = self._model_combo.findData(model_name)
        if idx < 0:
            label = MODEL_LABELS.get(model_name, model_name)
            self._model_combo.addItem(f"{label} ({model_name})", model_name)
            idx = self._model_combo.findData(model_name)
        self._model_combo.setCurrentIndex(idx)

    def _on_model_download(self, model_name):
        if self._download_thread is not None and self._download_thread.isRunning():
            QMessageBox.warning(self, "Скачивание", "Дождитесь завершения текущего скачивания")
            return

        info = MODEL_CATALOG[model_name]
        self._download_thread = ModelDownloadThread(
            info["repo_id"], MODELS_DIR / model_name, model_name,
        )
        self._download_thread.progress.connect(self._on_model_download_progress)
        self._download_thread.finished_ok.connect(self._on_model_download_finished)
        self._download_thread.error.connect(self._on_model_download_error)

        self._model_progress.setValue(0)
        self._model_progress.show()
        self._model_status.setText(f"Скачивание {model_name}...")
        self._download_thread.start()

    def _on_model_download_progress(self, current, total):
        self._model_progress.setMaximum(total)
        self._model_progress.setValue(current)

    def _on_model_download_finished(self, model_name):
        self._model_progress.hide()
        self._download_thread = None
        self._model_status.setText(f"Модель {model_name} скачана")
        self._populate_models_table()

    def _on_model_download_error(self, msg):
        self._model_progress.hide()
        self._download_thread = None
        self._model_status.setText(f"Ошибка: {msg}")

    # ======================================================================
    # Load / Collect values
    # ======================================================================

    def _load_values(self):
        c = self._config

        # General
        self._hotkey_edit.setHotkey(c.get("recognition", "hotkey", default="f9"))

        lang = c.get("recognition", "language", default="auto")
        idx = self._language_combo.findData(lang)
        if idx >= 0:
            self._language_combo.setCurrentIndex(idx)

        self._autostart_check.setChecked(c.get("system", "autostart", default=False))
        self._start_minimized_check.setChecked(c.get("system", "start_minimized", default=False))
        self._audio_gain_spin.setValue(c.get("recognition", "audio_gain", default=1.0))
        self._sound_effects_check.setChecked(c.get("widget", "sound_effects", default=True))
        self._audio_ducking_check.setChecked(c.get("widget", "audio_ducking", default=True))

        # Recognition
        model = c.get("recognition", "model", default="large-v3-turbo")
        idx = self._model_combo.findData(model)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)

        device = c.get("recognition", "device", default="cuda")
        idx = self._device_combo.findData(device)
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)

        compute = c.get("recognition", "compute_type", default="float16")
        idx = self._compute_combo.findData(compute)
        if idx >= 0:
            self._compute_combo.setCurrentIndex(idx)

        self._beam_size_spin.setValue(c.get("recognition", "beam_size", default=5))
        self._condition_prev_check.setChecked(c.get("recognition", "condition_on_previous_text", default=False))
        self._compression_spin.setValue(c.get("recognition", "compression_ratio_threshold", default=2.4))
        self._log_prob_spin.setValue(c.get("recognition", "log_prob_threshold", default=-1.0))
        self._no_speech_spin.setValue(c.get("recognition", "no_speech_threshold", default=0.6))
        self._repetition_spin.setValue(c.get("recognition", "repetition_penalty", default=1.2))
        self._no_repeat_ngram_spin.setValue(c.get("recognition", "no_repeat_ngram_size", default=3))
        self._hallucination_spin.setValue(c.get("recognition", "hallucination_silence_threshold", default=2.0))

        # VAD
        self._vad_threshold_spin.setValue(c.get("vad", "threshold", default=0.5))
        self._vad_min_speech_spin.setValue(c.get("vad", "min_speech_ms", default=250))
        self._vad_min_silence_spin.setValue(c.get("vad", "min_silence_ms", default=500))

        # Post-processing
        self._llm_check.setChecked(c.get("llm", "enabled", default=False))
        self._punct_check.setChecked(c.get("postprocessing", "punctuation", default=True))
        self._capital_check.setChecked(c.get("postprocessing", "capitalization", default=True))
        self._trailing_dot_check.setChecked(c.get("postprocessing", "trailing_dot", default=True))

        # Apply LLM toggle state to regex checkboxes
        llm_on = c.get("llm", "enabled", default=False)
        self._punct_check.setEnabled(not llm_on)
        self._capital_check.setEnabled(not llm_on)
        self._trailing_dot_check.setEnabled(not llm_on)
        self._regex_disabled_hint.setVisible(llm_on)

        # Dictionary -- already loaded during build

    def _collect_all_values(self) -> dict:
        """Snapshot of all widget values as flat dict keyed by config path."""
        vals = {}

        # General
        vals["recognition.hotkey"] = self._hotkey_edit.hotkey()
        vals["recognition.language"] = self._language_combo.currentData()
        vals["system.autostart"] = self._autostart_check.isChecked()
        vals["system.start_minimized"] = self._start_minimized_check.isChecked()
        vals["recognition.audio_gain"] = self._audio_gain_spin.value()
        vals["widget.sound_effects"] = self._sound_effects_check.isChecked()
        vals["widget.audio_ducking"] = self._audio_ducking_check.isChecked()

        # Recognition
        vals["recognition.model"] = self._model_combo.currentData()
        vals["recognition.device"] = self._device_combo.currentData()
        vals["recognition.compute_type"] = self._compute_combo.currentData()
        vals["recognition.beam_size"] = self._beam_size_spin.value()
        vals["recognition.condition_on_previous_text"] = self._condition_prev_check.isChecked()
        vals["recognition.compression_ratio_threshold"] = self._compression_spin.value()
        vals["recognition.log_prob_threshold"] = self._log_prob_spin.value()
        vals["recognition.no_speech_threshold"] = self._no_speech_spin.value()
        vals["recognition.repetition_penalty"] = self._repetition_spin.value()
        vals["recognition.no_repeat_ngram_size"] = self._no_repeat_ngram_spin.value()
        vals["recognition.hallucination_silence_threshold"] = self._hallucination_spin.value()

        # VAD
        vals["vad.threshold"] = self._vad_threshold_spin.value()
        vals["vad.min_speech_ms"] = self._vad_min_speech_spin.value()
        vals["vad.min_silence_ms"] = self._vad_min_silence_spin.value()

        # Post-processing
        vals["llm.enabled"] = self._llm_check.isChecked()
        vals["postprocessing.punctuation"] = self._punct_check.isChecked()
        vals["postprocessing.capitalization"] = self._capital_check.isChecked()
        vals["postprocessing.trailing_dot"] = self._trailing_dot_check.isChecked()

        # Dictionary
        vals["dictionaries.active"] = sorted(
            d for d, cb in self._dict_checks.items() if cb.isChecked()
        )

        return vals

    # ======================================================================
    # Change tracking
    # ======================================================================

    def _has_unsaved_changes(self) -> bool:
        return self._collect_all_values() != self._initial_values

    def _get_changed_keys(self) -> set[str]:
        current = self._collect_all_values()
        return {k for k, v in current.items() if v != self._initial_values.get(k)}

    def _get_restart_needed(self) -> set[str]:
        return self._get_changed_keys() & self.RESTART_KEYS

    @property
    def changed_settings(self) -> dict:
        return self._changed_settings

    # ======================================================================
    # Button handlers
    # ======================================================================

    def _on_ok(self):
        current = self._collect_all_values()
        changed = {k for k, v in current.items() if v != self._initial_values.get(k)}

        # Write all values to config
        for key, value in current.items():
            parts = key.split(".")
            self._config.set(*parts, value)

        self._config.save()

        # Track changed sections
        self._changed_settings = {}
        for k in changed:
            section = k.split(".")[0]
            self._changed_settings.setdefault(section, []).append(k)

        # Check restart-required
        restart_keys = changed & self.RESTART_KEYS
        if restart_keys:
            QMessageBox.information(
                self,
                "Требуется перезапуск",
                "Перезапустите приложение для применения изменений модели/устройства.",
            )

        self.accept()

    def _on_cancel(self):
        if self._has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Несохранённые изменения",
                "Есть несохранённые изменения. Закрыть?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.reject()

    def closeEvent(self, event):
        # Check whisper model download
        if self._download_thread is not None and self._download_thread.isRunning():
            reply = QMessageBox.question(
                self, "Скачивание",
                "Скачивание модели в процессе. Прервать?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._download_thread.quit()
            self._download_thread.wait(3000)
            self._download_thread = None
        # Check LLM conversion
        if self._llm_convert_thread is not None and self._llm_convert_thread.isRunning():
            reply = QMessageBox.question(
                self, "Конвертация LLM",
                "Конвертация LLM-модели в процессе. Прервать?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._llm_convert_thread.quit()
            self._llm_convert_thread.wait(3000)
            self._llm_convert_thread = None
        if self._has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Несохранённые изменения",
                "Есть несохранённые изменения. Закрыть?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()

    def _on_reset_defaults(self):
        idx = self._tabs.currentIndex()
        defaults = copy.deepcopy(DEFAULT_CONFIG)

        if idx == 0:
            self._reset_general(defaults)
        elif idx == 1:
            self._reset_recognition(defaults)
        elif idx == 2:
            self._reset_postprocessing(defaults)
        elif idx == 3:
            self._reset_dictionary(defaults)

    # ======================================================================
    # Reset helpers (per tab)
    # ======================================================================

    def _reset_general(self, d: dict):
        self._hotkey_edit.setHotkey(d["recognition"]["hotkey"])
        idx = self._language_combo.findData(d["recognition"]["language"])
        if idx >= 0:
            self._language_combo.setCurrentIndex(idx)

        self._autostart_check.setChecked(d["system"]["autostart"])
        self._start_minimized_check.setChecked(d["system"]["start_minimized"])
        self._audio_gain_spin.setValue(d["recognition"]["audio_gain"])
        self._sound_effects_check.setChecked(d["widget"]["sound_effects"])
        self._audio_ducking_check.setChecked(d["widget"]["audio_ducking"])

    def _reset_recognition(self, d: dict):
        model = d["recognition"]["model"]
        idx = self._model_combo.findData(model)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)

        idx = self._device_combo.findData(d["recognition"]["device"])
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)

        idx = self._compute_combo.findData(d["recognition"]["compute_type"])
        if idx >= 0:
            self._compute_combo.setCurrentIndex(idx)

        self._beam_size_spin.setValue(d["recognition"]["beam_size"])
        self._condition_prev_check.setChecked(d["recognition"]["condition_on_previous_text"])
        self._compression_spin.setValue(d["recognition"]["compression_ratio_threshold"])
        self._log_prob_spin.setValue(d["recognition"]["log_prob_threshold"])
        self._no_speech_spin.setValue(d["recognition"]["no_speech_threshold"])
        self._repetition_spin.setValue(d["recognition"]["repetition_penalty"])
        self._no_repeat_ngram_spin.setValue(d["recognition"]["no_repeat_ngram_size"])
        self._hallucination_spin.setValue(d["recognition"]["hallucination_silence_threshold"])

        self._vad_threshold_spin.setValue(d["vad"]["threshold"])
        self._vad_min_speech_spin.setValue(d["vad"]["min_speech_ms"])
        self._vad_min_silence_spin.setValue(d["vad"]["min_silence_ms"])

    def _reset_postprocessing(self, d: dict):
        self._llm_check.setChecked(d["llm"]["enabled"])
        self._punct_check.setChecked(d["postprocessing"]["punctuation"])
        self._capital_check.setChecked(d["postprocessing"]["capitalization"])
        self._trailing_dot_check.setChecked(d["postprocessing"]["trailing_dot"])

    def _reset_dictionary(self, d: dict):
        active = d["dictionaries"]["active"]
        for domain, cb in self._dict_checks.items():
            cb.setChecked(domain in active)
