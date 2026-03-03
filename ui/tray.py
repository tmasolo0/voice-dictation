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

        self._tray_icon.setIcon(self._create_tray_icon("ready"))
        from app import get_version
        self._tray_icon.setToolTip(f"Voice Dictation v{get_version()}")
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

        settings_action = tray_menu.addAction("Настройки...")
        settings_action.triggered.connect(lambda: self._bus.mode_changed.emit("open_settings", None))

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
        pass

