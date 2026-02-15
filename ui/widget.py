"""DictationWidget — UI-only виджет голосовой диктовки."""

import math
import win32gui
import win32api
import win32con

from PyQt6.QtWidgets import QApplication, QWidget, QMenu
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen

from core.model_catalog import MODEL_LABELS


# Цвета состояний
COLORS = {
    "ready": QColor(76, 175, 80),       # Зелёный — готов
    "recording": QColor(244, 67, 54),   # Красный — запись
    "processing": QColor(255, 193, 7),  # Жёлтый — обработка
    "translate": QColor(33, 150, 243),  # Синий — режим перевода
}

# Анимация
ANIMATION_INTERVAL = 50  # мс
PULSE_SPEED_READY = 0.03
PULSE_SPEED_RECORDING = 0.1
FULLSCREEN_CHECK_INTERVAL = 1500


def is_fullscreen_app_active() -> bool:
    """Проверка, активно ли полноэкранное приложение."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        rect = win32gui.GetWindowRect(hwnd)
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        monitor_info = win32api.GetMonitorInfo(monitor)
        monitor_rect = monitor_info['Monitor']
        return (
            rect[0] <= monitor_rect[0] and
            rect[1] <= monitor_rect[1] and
            rect[2] >= monitor_rect[2] and
            rect[3] >= monitor_rect[3]
        )
    except Exception:
        return False


class DictationWidget(QWidget):
    """Минималистичный виджет — только UI, без бизнес-логики."""

    def __init__(self, event_bus, config):
        super().__init__()

        self._bus = event_bus
        self._config = config

        # Визуальное состояние
        self._current_state = "ready"
        self.translate_mode = config.get('dictation', 'translate_to_english', default=False)
        self.dictation_model = config.get('recognition', 'model', default='large-v3-turbo')
        self._vram_mb = 0

        # Перетаскивание
        self._drag_position = QPoint()

        # Автоскрытие в fullscreen
        self._hidden_by_fullscreen = False
        self.minimized_to_tray = False

        # Анимация
        self._animation_phase = 0.0

        self._setup_ui()
        self._start_fullscreen_monitor()
        self._start_animation()

        # Подписка на сигналы
        self._bus.state_changed.connect(self._on_state_changed)
        self._bus.mode_changed.connect(self._on_mode_changed)
        self._bus.vram_updated.connect(self._on_vram_updated)

    def _setup_ui(self):
        """Настройка UI виджета."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        size = self._config.get('widget', 'size', default=100)
        self.setFixedSize(size, size)

        pos = self._load_position()
        self.move(pos)

        self.setWindowTitle("Dictation")

    def _load_position(self) -> QPoint:
        """Загрузка позиции из конфига."""
        x = self._config.get('widget', 'position', 'x', default=None)
        y = self._config.get('widget', 'position', 'y', default=None)

        if x is not None and y is not None:
            pos = QPoint(x, y)
            if self._is_position_valid(pos):
                return pos

        return self._get_default_position()

    def _get_default_position(self) -> QPoint:
        """Позиция по умолчанию (правый нижний угол)."""
        screen = QApplication.primaryScreen().geometry()
        size = self._config.get('widget', 'size', default=100)
        return QPoint(screen.width() - size - 50, screen.height() - size - 100)

    def _is_position_valid(self, pos: QPoint) -> bool:
        """Проверка, что позиция на экране."""
        screen = QApplication.primaryScreen().geometry()
        return screen.contains(pos)

    def _save_position(self):
        """Сохранение позиции в конфиг."""
        self._config.set('widget', 'position', 'x', self.x())
        self._config.set('widget', 'position', 'y', self.y())

    def _start_fullscreen_monitor(self):
        """Запуск мониторинга полноэкранных приложений."""
        if not self._config.get('widget', 'hide_in_fullscreen', default=True):
            return

        self._fullscreen_timer = QTimer()
        self._fullscreen_timer.timeout.connect(self._check_fullscreen_visibility)
        self._fullscreen_timer.start(FULLSCREEN_CHECK_INTERVAL)

    def _check_fullscreen_visibility(self):
        """Проверка видимости в fullscreen."""
        if self.minimized_to_tray:
            return

        is_fullscreen = is_fullscreen_app_active()

        if is_fullscreen and not self._hidden_by_fullscreen:
            self.hide()
            self._hidden_by_fullscreen = True
        elif not is_fullscreen and self._hidden_by_fullscreen:
            self.show()
            self._hidden_by_fullscreen = False

    def _start_animation(self):
        """Запуск анимации пульсации."""
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._animate)
        self._animation_timer.start(ANIMATION_INTERVAL)

    def _animate(self):
        """Обновление фазы анимации."""
        if self._current_state == "ready":
            self._animation_phase += PULSE_SPEED_READY
        elif self._current_state == "recording":
            self._animation_phase += PULSE_SPEED_RECORDING

        if self._animation_phase > 2 * math.pi:
            self._animation_phase -= 2 * math.pi

        self.update()

    def _on_state_changed(self, state: str):
        """Обновление визуального состояния."""
        self._current_state = state
        self._animation_phase = 0.0
        self.update()

    def _on_vram_updated(self, vram_mb: int):
        """Обновление отображения VRAM."""
        self._vram_mb = vram_mb
        self.update()

    def _on_mode_changed(self, key: str, value):
        """Обновление режимов для отображения."""
        if key == "translate_toggle":
            self.translate_mode = not self.translate_mode
            self.update()

    def _minimize_to_tray(self):
        """Свернуть в трей."""
        self.hide()
        self.minimized_to_tray = True

    def _show_from_tray(self):
        """Показать из трея."""
        self.show()
        self.activateWindow()
        self.minimized_to_tray = False

    # --- Отрисовка ---

    def paintEvent(self, event):
        """Отрисовка виджета."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = self.width()
        center = size // 2

        # Цвет в зависимости от режима
        if self.translate_mode and self._current_state == "ready":
            base_color = COLORS["translate"]
        else:
            base_color = COLORS.get(self._current_state, COLORS["ready"])

        # Пульсация
        if self._current_state in ("ready", "recording"):
            pulse = 0.15 * math.sin(self._animation_phase)
            radius = int(center * (0.8 + pulse))
        else:
            radius = int(center * 0.8)

        # Тень
        shadow_color = QColor(0, 0, 0, 50)
        painter.setBrush(QBrush(shadow_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center - radius + 3, center - radius + 3,
                           radius * 2, radius * 2)

        # Основной круг
        painter.setBrush(QBrush(base_color))
        painter.drawEllipse(center - radius, center - radius,
                           radius * 2, radius * 2)

        # Текст на виджете
        if self._current_state == "ready":
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            font = painter.font()
            font.setBold(True)

            has_vram = self._vram_mb > 0
            vram_text = f"{self._vram_mb / 1024:.1f}G" if self._vram_mb >= 1024 else f"{self._vram_mb}M"

            if self.translate_mode:
                if has_vram:
                    # EN + VRAM — две строки
                    font.setPointSize(int(size * 0.13))
                    painter.setFont(font)
                    upper = self.rect().adjusted(0, -int(size * 0.08), 0, 0)
                    painter.drawText(upper, Qt.AlignmentFlag.AlignCenter, "EN")

                    font.setBold(False)
                    font.setPointSize(int(size * 0.07))
                    painter.setFont(font)
                    painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
                    lower = self.rect().adjusted(0, int(size * 0.15), 0, 0)
                    painter.drawText(lower, Qt.AlignmentFlag.AlignCenter, vram_text)
                else:
                    # Только EN
                    font.setPointSize(int(size * 0.15))
                    painter.setFont(font)
                    painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "EN")
            else:
                label = MODEL_LABELS.get(self.dictation_model, self.dictation_model)
                if has_vram:
                    # Модель + VRAM — две строки
                    font.setPointSize(int(size * 0.10))
                    painter.setFont(font)
                    upper = self.rect().adjusted(0, -int(size * 0.08), 0, 0)
                    painter.drawText(upper, Qt.AlignmentFlag.AlignCenter, label)

                    font.setBold(False)
                    font.setPointSize(int(size * 0.07))
                    painter.setFont(font)
                    painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
                    lower = self.rect().adjusted(0, int(size * 0.15), 0, 0)
                    painter.drawText(lower, Qt.AlignmentFlag.AlignCenter, vram_text)
                else:
                    # Только метка модели
                    font.setPointSize(int(size * 0.11))
                    painter.setFont(font)
                    painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, label)

        painter.end()

    # --- Взаимодействие ---

    def mousePressEvent(self, event):
        """Начало перетаскивания."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Перетаскивание."""
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Конец перетаскивания."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._save_position()
            event.accept()

    def contextMenuEvent(self, event):
        """Контекстное меню — сигналы вместо прямых вызовов."""
        menu = QMenu(self)

        models_action = menu.addAction("Управление моделями...")
        models_action.triggered.connect(lambda: self._bus.mode_changed.emit("open_model_manager", None))

        settings_action = menu.addAction("Настройки...")
        settings_action.triggered.connect(lambda: self._bus.mode_changed.emit("open_settings", None))

        translate_action = menu.addAction("✓ Перевод → EN" if self.translate_mode else "Перевод → EN")
        translate_action.triggered.connect(lambda: self._bus.mode_changed.emit("translate_toggle", None))

        menu.addSeparator()

        minimize_action = menu.addAction("Свернуть в трей")
        minimize_action.triggered.connect(self._minimize_to_tray)

        quit_action = menu.addAction("Выход")
        quit_action.triggered.connect(lambda: self._bus.quit_requested.emit())

        menu.exec(event.globalPos())

    def closeEvent(self, event):
        """Закрытие окна — свернуть в трей."""
        self._minimize_to_tray()
        event.ignore()
