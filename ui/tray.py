"""TrayManager — системный трей."""

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QBrush, QPixmap, QIcon

from ui.widget import COLORS


TRAY_ICON_SIZE = 64


class TrayManager:
    """Иконка в системном трее с контекстным меню."""

    def __init__(self, event_bus, config, widget):
        self._bus = event_bus
        self._config = config
        self._widget = widget
        self._tray_icon = QSystemTrayIcon()

        self.translate_mode = config.get('dictation', 'translate_to_english', default=False)
        self.dictation_model = config.get('recognition', 'model', default='large-v3-turbo')

        self._tray_icon.setIcon(self._create_tray_icon("ready"))
        self._tray_icon.setToolTip("Voice Dictation")
        self._tray_icon.activated.connect(self._on_tray_activated)

        self._rebuild_menu()
        self._tray_icon.show()

        # Подписка на сигналы
        self._bus.state_changed.connect(self._on_state_changed)
        self._bus.mode_changed.connect(self._on_mode_changed)

    def _create_tray_icon(self, state: str) -> QIcon:
        """Создание иконки для трея."""
        pixmap = QPixmap(TRAY_ICON_SIZE, TRAY_ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.translate_mode and state == "ready":
            color = COLORS["translate"]
        else:
            color = COLORS.get(state, COLORS["ready"])

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)

        margin = 4
        painter.drawEllipse(margin, margin,
                          TRAY_ICON_SIZE - 2 * margin,
                          TRAY_ICON_SIZE - 2 * margin)
        painter.end()

        return QIcon(pixmap)

    def _rebuild_menu(self):
        """Пересоздание контекстного меню трея."""
        tray_menu = QMenu()

        is_max = self.dictation_model == 'large-v3'
        quality_action = tray_menu.addAction("✓ Макс качество" if is_max else "Макс качество")
        quality_action.triggered.connect(lambda: self._bus.mode_changed.emit("quality_toggle", None))

        translate_action = tray_menu.addAction("✓ Перевод → EN" if self.translate_mode else "Перевод → EN")
        translate_action.triggered.connect(lambda: self._bus.mode_changed.emit("translate_toggle", None))

        tray_menu.addSeparator()

        show_action = tray_menu.addAction("Показать")
        show_action.triggered.connect(self._widget._show_from_tray)

        quit_action = tray_menu.addAction("Выход")
        quit_action.triggered.connect(lambda: self._bus.quit_requested.emit())

        self._tray_icon.setContextMenu(tray_menu)

    def _on_tray_activated(self, reason):
        """Двойной клик — показать виджет."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._widget._show_from_tray()

    def _on_state_changed(self, state: str):
        """Обновить иконку трея при смене состояния."""
        self._tray_icon.setIcon(self._create_tray_icon(state))

    def _on_mode_changed(self, key: str, value):
        """Обновить меню и показать уведомление при смене режима."""
        if key == "translate_toggle":
            self.translate_mode = not self.translate_mode
            model_name = 'medium' if self.translate_mode else self.dictation_model
            mode_text = f"EN (перевод, {model_name})" if self.translate_mode else f"RU/EN ({self.dictation_model})"
            self._tray_icon.showMessage("Dictation", f"Режим: {mode_text}",
                                        QSystemTrayIcon.MessageIcon.Information, 2000)

        elif key == "quality_toggle":
            if self.dictation_model == 'large-v3':
                self.dictation_model = 'large-v3-turbo'
            else:
                self.dictation_model = 'large-v3'
            mode_text = "Макс (large-v3)" if self.dictation_model == 'large-v3' else "Turbo (large-v3-turbo)"
            self._tray_icon.showMessage("Dictation", f"Качество: {mode_text}",
                                        QSystemTrayIcon.MessageIcon.Information, 2000)

        self._rebuild_menu()
        self._tray_icon.setIcon(self._create_tray_icon("ready"))
