"""
SystemTray — управление иконкой в системном трее.
Обёртка над PyQt6 QSystemTrayIcon для упрощения работы.
"""

from typing import Callable, Optional

from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from PyQt6.QtGui import QColor, QPixmap, QPainter, QBrush, QIcon
from PyQt6.QtCore import Qt


# Размер иконки в трее
TRAY_ICON_SIZE = 64


class SystemTray:
    """Иконка в системном трее."""

    def __init__(
        self,
        parent=None,
        tooltip: str = "Voice Input",
        on_double_click: Optional[Callable] = None,
    ):
        """
        Создать иконку в трее.

        Args:
            parent: Родительский виджет (обычно главное окно)
            tooltip: Подсказка при наведении
            on_double_click: Callback при двойном клике
        """
        self._parent = parent
        self._tooltip = tooltip
        self._on_double_click = on_double_click
        self._tray_icon: Optional[QSystemTrayIcon] = None
        self._menu: Optional[QMenu] = None
        self._current_color = QColor(76, 175, 80)  # Зелёный по умолчанию

        self._setup()

    def _setup(self):
        """Настройка иконки в трее."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("Системный трей недоступен")
            return

        self._tray_icon = QSystemTrayIcon(self._parent)
        self._tray_icon.setIcon(self._create_icon(self._current_color))
        self._tray_icon.setToolTip(self._tooltip)

        if self._on_double_click:
            self._tray_icon.activated.connect(self._on_activated)

    def _create_icon(self, color: QColor) -> QIcon:
        """
        Создание иконки заданного цвета.

        Args:
            color: Цвет круга

        Returns:
            QIcon с круглой иконкой
        """
        size = TRAY_ICON_SIZE
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        margin = 4
        painter.drawEllipse(margin, margin, size - margin * 2, size - margin * 2)

        painter.end()

        return QIcon(pixmap)

    def _on_activated(self, reason):
        """Обработка клика по иконке."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self._on_double_click:
                self._on_double_click()

    def set_icon(self, color: QColor):
        """
        Установить цвет иконки.

        Args:
            color: Новый цвет
        """
        if self._tray_icon:
            self._current_color = color
            self._tray_icon.setIcon(self._create_icon(color))

    def set_tooltip(self, tooltip: str):
        """
        Установить подсказку.

        Args:
            tooltip: Текст подсказки
        """
        if self._tray_icon:
            self._tooltip = tooltip
            self._tray_icon.setToolTip(tooltip)

    def set_menu(self, menu: QMenu):
        """
        Установить контекстное меню.

        Args:
            menu: Меню для отображения при правом клике
        """
        if self._tray_icon:
            self._menu = menu
            self._tray_icon.setContextMenu(menu)

    def show_notification(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        duration_ms: int = 2000,
    ):
        """
        Показать уведомление.

        Args:
            title: Заголовок уведомления
            message: Текст сообщения
            icon: Тип иконки (Information, Warning, Critical)
            duration_ms: Длительность отображения в миллисекундах
        """
        if self._tray_icon:
            self._tray_icon.showMessage(title, message, icon, duration_ms)

    def show(self):
        """Показать иконку в трее."""
        if self._tray_icon:
            self._tray_icon.show()

    def hide(self):
        """Скрыть иконку из трея."""
        if self._tray_icon:
            self._tray_icon.hide()

    def is_available(self) -> bool:
        """Проверка доступности системного трея."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    @property
    def icon(self) -> Optional[QSystemTrayIcon]:
        """Доступ к QSystemTrayIcon для расширенного использования."""
        return self._tray_icon
