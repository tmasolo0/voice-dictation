"""
SettingsDialog — окно настроек приложения Voice Dictation.
PyQt6 диалог для редактирования config.json.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QSlider, QCheckBox, QComboBox, QKeySequenceEdit,
    QPushButton, QGroupBox, QFormLayout, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from core.config_manager import config


# === Константы распознавания ===
MODELS = [
    ("large-v3-turbo", "Large v3 Turbo (рекомендуется)"),
    ("large-v3", "Large v3 (медленнее)"),
    ("medium", "Medium (быстрее, хуже качество)"),
    ("small", "Small (быстрый, базовое качество)"),
]

LANGUAGES = [
    ("auto", "Авто (смешанная речь)"),
    ("ru", "Русский"),
    ("en", "Английский"),
]


class SettingsDialog(QDialog):
    """Диалог настроек приложения."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(400)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._original_hotkey = config.get('recognition', 'hotkey', default='f9')
        self._original_model = config.get('recognition', 'model', default='large-v3-turbo')

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Построение интерфейса."""
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._create_widget_tab(), "Виджет")
        tabs.addTab(self._create_recognition_tab(), "Распознавание")
        tabs.addTab(self._create_system_tab(), "Система")
        layout.addWidget(tabs)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self._save_settings)
        save_btn.setDefault(True)

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)

        buttons_layout.addWidget(save_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)

    def _create_widget_tab(self) -> QWidget:
        """Вкладка настроек виджета."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Отображение")
        form = QFormLayout(group)

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(100, 200)
        self.size_slider.setTickInterval(10)
        self.size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.size_label = QLabel()
        self.size_slider.valueChanged.connect(
            lambda v: self.size_label.setText(f"{v} px")
        )

        size_layout = QHBoxLayout()
        size_layout.addWidget(self.size_slider)
        size_layout.addWidget(self.size_label)
        form.addRow("Размер виджета:", size_layout)

        self.hide_fullscreen_cb = QCheckBox("Скрывать в полноэкранных приложениях")
        form.addRow("", self.hide_fullscreen_cb)

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _create_recognition_tab(self) -> QWidget:
        """Вкладка настроек распознавания."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Параметры распознавания")
        form = QFormLayout(group)

        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumSequenceLength(1)
        form.addRow("Горячая клавиша:", self.hotkey_edit)

        self.model_combo = QComboBox()
        for value, label in MODELS:
            self.model_combo.addItem(label, value)
        form.addRow("Модель:", self.model_combo)

        self.language_combo = QComboBox()
        for value, label in LANGUAGES:
            self.language_combo.addItem(label, value)
        form.addRow("Язык:", self.language_combo)

        restart_label = QLabel("Изменение горячей клавиши или модели требует перезапуска")
        restart_label.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", restart_label)

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _create_system_tab(self) -> QWidget:
        """Вкладка системных настроек."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Запуск")
        form = QFormLayout(group)

        self.autostart_cb = QCheckBox("Запускать при старте Windows")
        self.autostart_cb.setEnabled(False)
        self.autostart_cb.setToolTip("Будет реализовано в следующей версии")
        form.addRow("", self.autostart_cb)

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _load_settings(self):
        """Загрузка текущих настроек из конфига."""
        size = config.get('widget', 'size', default=150)
        self.size_slider.setValue(size)
        self.size_label.setText(f"{size} px")

        hide_fs = config.get('widget', 'hide_in_fullscreen', default=True)
        self.hide_fullscreen_cb.setChecked(hide_fs)

        hotkey = config.get('recognition', 'hotkey', default='f9')
        self.hotkey_edit.setKeySequence(QKeySequence(hotkey.upper()))

        model = config.get('recognition', 'model', default='large-v3-turbo')
        idx = self.model_combo.findData(model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

        language = config.get('recognition', 'language', default='auto')
        idx = self.language_combo.findData(language)
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)

        autostart = config.get('system', 'autostart', default=False)
        self.autostart_cb.setChecked(autostart)

    def _save_settings(self):
        """Сохранение настроек в конфиг."""
        config.set('widget', 'size', self.size_slider.value())
        config.set('widget', 'hide_in_fullscreen', self.hide_fullscreen_cb.isChecked())

        hotkey = self.hotkey_edit.keySequence().toString().lower()
        if not hotkey:
            hotkey = 'f9'
        config.set('recognition', 'hotkey', hotkey)
        config.set('recognition', 'model', self.model_combo.currentData())
        config.set('recognition', 'language', self.language_combo.currentData())

        config.set('system', 'autostart', self.autostart_cb.isChecked())

        config.save()

        new_hotkey = config.get('recognition', 'hotkey')
        new_model = config.get('recognition', 'model')

        needs_restart = (
            new_hotkey != self._original_hotkey or
            new_model != self._original_model
        )

        if needs_restart:
            QMessageBox.information(
                self,
                "Требуется перезапуск",
                "Некоторые настройки вступят в силу после перезапуска приложения."
            )

        self.accept()

    def get_immediate_changes(self) -> dict:
        """Настройки, которые применяются сразу без перезапуска."""
        return {
            'size': config.get('widget', 'size', default=150),
            'hide_in_fullscreen': config.get('widget', 'hide_in_fullscreen', default=True),
            'language': config.get('recognition', 'language', default='auto'),
        }
