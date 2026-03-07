"""DictationWidget — горизонтальная pill-bar панель в стиле Aqua Voice."""

import ctypes
import ctypes.wintypes
import logging
import math
import os
import sys
import winsound

from PyQt6.QtWidgets import QApplication, QWidget, QMenu
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QPixmap,
    QPainterPath, QLinearGradient,
)

log = logging.getLogger(__name__)

# Цвета состояний (используются также в tray.py)
COLORS = {
    "ready": QColor(76, 175, 80),       # Зелёный — готов
    "recording": QColor(244, 67, 54),   # Красный — запись
    "processing": QColor(255, 193, 7),  # Жёлтый — обработка
}

# Анимация
ANIMATION_INTERVAL = 50  # мс


def get_taskbar_rect():
    """Получить прямоугольник таскбара через Windows API."""
    class APPBARDATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("hWnd", ctypes.wintypes.HWND),
            ("uCallbackMessage", ctypes.c_uint),
            ("uEdge", ctypes.c_uint),
            ("rc", ctypes.wintypes.RECT),
            ("lParam", ctypes.wintypes.LPARAM),
        ]

    ABM_GETTASKBARPOS = 5
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)

    result = ctypes.windll.shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(abd))
    if result:
        rc = abd.rc
        return abd.uEdge, QRect(rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top)
    return None, None


def _get_sound_path(name: str) -> str:
    """Путь к звуковому файлу."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'assets', 'sounds', name)


def _get_avatar_path() -> str:
    """Путь к аватару."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'Ava.jpg')


class DictationWidget(QWidget):
    """Горизонтальная pill-bar панель — аватар, waveform, бейдж горячей клавиши."""

    def __init__(self, event_bus, config, audio_capture=None):
        super().__init__()

        self._bus = event_bus
        self._config = config
        self._audio = audio_capture

        # Визуальное состояние
        self._current_state = "ready"
        self.dictation_model = config.get('recognition', 'model', default='large-v3-turbo')
        self._vram_mb = 0

        # Перетаскивание
        self._drag_position = QPoint()
        self._dragging = False

        self.minimized_to_tray = False

        # Hover
        self._hovered = False

        # Анимация
        self._animation_phase = 0.0
        self._hover_opacity = 0.0
        self._processing_dots = 0

        # Audio levels для waveform
        self._audio_levels = []

        # Аватар
        self._avatar_pixmap = None
        self._load_avatar()

        # Звуки
        self._sound_start = _get_sound_path('start.wav')
        self._sound_stop = _get_sound_path('stop.wav')

        self._setup_ui()
        self._start_animation()

        # Подписка на сигналы
        self._bus.state_changed.connect(self._on_state_changed)
        self._bus.vram_updated.connect(self._on_vram_updated)

    def _load_avatar(self):
        """Загрузка и подготовка круглого аватара."""
        path = _get_avatar_path()
        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                size = 24
                scaled = pixmap.scaled(size, size,
                                       Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
                if scaled.width() != size or scaled.height() != size:
                    x = (scaled.width() - size) // 2
                    y = (scaled.height() - size) // 2
                    scaled = scaled.copy(x, y, size, size)
                self._avatar_pixmap = scaled
            else:
                log.warning("Avatar pixmap is null: %s", path)
        else:
            log.warning("Avatar not found: %s", path)

    def _setup_ui(self):
        """Настройка UI виджета."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        bar_w = self._config.get('widget', 'bar_width', default=200)
        bar_h = self._config.get('widget', 'bar_height', default=36)
        self.setFixedSize(bar_w, bar_h)

        pos = self._load_position()
        self.move(pos)

        self.setWindowTitle("Dictation")

    def _load_position(self) -> QPoint:
        """Загрузка позиции из конфига."""
        auto = self._config.get('widget', 'auto_position', default=True)
        if not auto:
            x = self._config.get('widget', 'position', 'x', default=None)
            y = self._config.get('widget', 'position', 'y', default=None)
            if x is not None and y is not None:
                pos = QPoint(x, y)
                if self._is_position_valid(pos):
                    return pos

        return self._get_auto_position()

    def _get_auto_position(self) -> QPoint:
        """Позиция по центру экрана, над таскбаром."""
        screen = QApplication.primaryScreen().geometry()
        bar_w = self.width()
        bar_h = self.height()

        x = (screen.width() - bar_w) // 2

        edge, taskbar_rect = get_taskbar_rect()
        if taskbar_rect is not None:
            if edge == 3:  # bottom
                y = taskbar_rect.top() - bar_h - 8
            elif edge == 1:  # top
                y = taskbar_rect.bottom() + 8
            elif edge == 0:  # left
                y = screen.height() - bar_h - 60
                x = taskbar_rect.right() + 8
            elif edge == 2:  # right
                y = screen.height() - bar_h - 60
                x = taskbar_rect.left() - bar_w - 8
            else:
                y = screen.height() - bar_h - 60
        else:
            y = screen.height() - bar_h - 60

        return QPoint(max(0, x), max(0, y))

    def _is_position_valid(self, pos: QPoint) -> bool:
        """Проверка, что позиция на экране."""
        screen = QApplication.primaryScreen().geometry()
        return screen.contains(pos)

    def _save_position(self):
        """Сохранение позиции в конфиг."""
        self._config.set('widget', 'position', 'x', self.x())
        self._config.set('widget', 'position', 'y', self.y())

    def _reset_position(self):
        """Сброс позиции к авто-позиции над таскбаром."""
        self._config.set('widget', 'auto_position', True)
        self._config.set('widget', 'position', 'x', None)
        self._config.set('widget', 'position', 'y', None)
        self._config.save()
        pos = self._get_auto_position()
        self.move(pos)

    def _start_animation(self):
        """Запуск анимации."""
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._animate)
        self._animation_timer.start(ANIMATION_INTERVAL)

    def _animate(self):
        """Обновление анимации + poll audio levels."""
        self._animation_phase += 0.08
        if self._animation_phase > 2 * math.pi:
            self._animation_phase -= 2 * math.pi

        # Hover opacity плавное нарастание/убывание
        if self._hovered and self._current_state == "ready":
            self._hover_opacity = min(1.0, self._hover_opacity + 0.15)
        else:
            self._hover_opacity = max(0.0, self._hover_opacity - 0.15)

        # Processing dots
        if self._current_state == "processing":
            self._processing_dots = (self._processing_dots + 1) % 12

        # Audio levels для waveform
        if self._current_state == "recording" and self._audio is not None:
            self._audio_levels = self._audio.get_audio_levels()

        self.update()

    def _play_sound(self, path):
        """Воспроизвести звук асинхронно."""
        if not self._config.get('widget', 'sound_effects', default=True):
            return
        try:
            if os.path.exists(path):
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            log.debug("Sound play error: %s", e)

    def _on_state_changed(self, state: str):
        """Обновление визуального состояния + звуки."""
        old_state = self._current_state
        self._current_state = state
        self._animation_phase = 0.0

        if state == "recording" and old_state != "recording":
            self._play_sound(self._sound_start)
        elif state == "processing" and old_state == "recording":
            self._play_sound(self._sound_stop)

        if state != "recording":
            self._audio_levels = []

        self.update()

    def _on_vram_updated(self, vram_mb: int):
        """Обновление отображения VRAM."""
        self._vram_mb = vram_mb
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
        """Отрисовка pill-bar панели."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h // 2

        # Фон — тёмный полупрозрачный
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        painter.fillPath(bg_path, QColor(30, 30, 30, 220))

        # Тонкая рамка
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawPath(bg_path)

        # Аватар (слева)
        avatar_x = 6
        avatar_y = (h - 24) // 2
        self._draw_avatar(painter, avatar_x, avatar_y)

        content_left = avatar_x + 24 + 8  # после аватара + отступ
        content_right = w - 8

        if self._current_state == "recording":
            self._draw_waveform(painter, content_left, content_right, h)
        elif self._current_state == "processing":
            self._draw_processing(painter, content_left, content_right, h)
        else:
            if self._hover_opacity > 0.01:
                self._draw_hover_info(painter, content_left, content_right, h)

        painter.end()

    def _draw_avatar(self, painter: QPainter, x: int, y: int):
        """Рисование круглого аватара с опциональным красным кольцом при записи."""
        size = 24
        center_x = x + size / 2
        center_y = y + size / 2

        if self._current_state == "recording":
            glow_radius = size / 2 + 3
            pulse = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(self._animation_phase * 3))
            glow_color = QColor(244, 67, 54, int(180 * pulse))
            painter.setPen(QPen(glow_color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(center_x - glow_radius, center_y - glow_radius,
                                       glow_radius * 2, glow_radius * 2))

        if self._avatar_pixmap is not None:
            clip_path = QPainterPath()
            clip_path.addEllipse(QRectF(x, y, size, size))
            painter.setClipPath(clip_path)
            painter.drawPixmap(x, y, self._avatar_pixmap)
            painter.setClipping(False)
        else:
            painter.setBrush(QColor(80, 80, 80))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x, y, size, size)

    def _draw_waveform(self, painter: QPainter, left: int, right: int, h: int):
        """Рисование waveform визуализации из RMS-уровней."""
        levels = self._audio_levels
        area_w = right - left
        num_bars = 24
        if not levels:
            levels = [0.0] * num_bars

        if len(levels) >= num_bars:
            step = len(levels) / num_bars
            bars = [levels[int(i * step)] for i in range(num_bars)]
        else:
            bars = levels + [0.0] * (num_bars - len(levels))

        bar_width = max(2, (area_w - (num_bars - 1) * 2) // num_bars)
        gap = 2
        total_bars_w = num_bars * bar_width + (num_bars - 1) * gap
        start_x = left + (area_w - total_bars_w) // 2

        max_bar_h = h * 0.6
        center_y = h / 2

        for i, level in enumerate(bars):
            norm = min(1.0, level * 5)
            bar_h = max(2, norm * max_bar_h)

            x = start_x + i * (bar_width + gap)
            y = center_y - bar_h / 2

            if norm < 0.5:
                r = int(76 + (255 - 76) * norm * 2)
                g = int(175 + (193 - 175) * norm * 2)
                b = int(80 - 73 * norm * 2)
            else:
                r = int(255 - (255 - 244) * (norm - 0.5) * 2)
                g = int(193 - (193 - 67) * (norm - 0.5) * 2)
                b = int(7 + (54 - 7) * (norm - 0.5) * 2)

            bar_color = QColor(r, g, b, 220)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bar_color)
            painter.drawRoundedRect(QRectF(x, y, bar_width, bar_h), 1, 1)

    def _draw_processing(self, painter: QPainter, left: int, right: int, h: int):
        """Рисование индикатора обработки — пульсирующие точки."""
        num_dots = 5
        dot_r = 3
        spacing = 12
        total_w = num_dots * dot_r * 2 + (num_dots - 1) * spacing
        start_x = left + ((right - left) - total_w) // 2
        center_y = h // 2

        for i in range(num_dots):
            phase = self._animation_phase - i * 0.5
            scale = 0.5 + 0.5 * max(0, math.sin(phase))
            r = int(dot_r * scale)
            alpha = int(100 + 155 * scale)

            x = start_x + i * (dot_r * 2 + spacing) + dot_r
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 193, 7, alpha))
            painter.drawEllipse(QRectF(x - r, center_y - r, r * 2, r * 2))

    def _draw_hover_info(self, painter: QPainter, left: int, right: int, h: int):
        """Рисование информации при hover: модель + горячая клавиша."""
        opacity = self._hover_opacity
        alpha = int(220 * opacity)

        font = QFont("Segoe UI", 9)
        painter.setFont(font)

        model_text = self.dictation_model

        painter.setPen(QPen(QColor(255, 255, 255, alpha), 1))
        text_rect = QRectF(left, 0, right - left - 44, h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, model_text)

        # Бейдж горячей клавиши (справа)
        hotkey = self._config.get('recognition', 'hotkey', default='f9').upper()
        badge_font = QFont("Segoe UI", 7)
        painter.setFont(badge_font)

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(hotkey) + 10
        text_h = fm.height() + 4
        badge_x = right - text_w - 2
        badge_y = (h - text_h) // 2

        badge_path = QPainterPath()
        badge_path.addRoundedRect(QRectF(badge_x, badge_y, text_w, text_h), 4, 4)
        painter.fillPath(badge_path, QColor(255, 255, 255, int(30 * opacity)))
        painter.setPen(QPen(QColor(255, 255, 255, int(80 * opacity)), 1))
        painter.drawPath(badge_path)

        painter.setPen(QPen(QColor(255, 255, 255, alpha), 1))
        painter.drawText(QRectF(badge_x, badge_y, text_w, text_h),
                         Qt.AlignmentFlag.AlignCenter, hotkey)

    # --- Взаимодействие ---

    def enterEvent(self, event):
        """Курсор вошёл в область виджета."""
        self._hovered = True

    def leaveEvent(self, event):
        """Курсор покинул область виджета."""
        self._hovered = False

    def mousePressEvent(self, event):
        """Начало перетаскивания."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragging = False
            event.accept()

    def mouseMoveEvent(self, event):
        """Перетаскивание."""
        if event.buttons() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Конец перетаскивания."""
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._config.set('widget', 'auto_position', False)
            self._save_position()
            self._config.save()
            self._dragging = False
            event.accept()

    def contextMenuEvent(self, event):
        """Контекстное меню."""
        menu = QMenu(self)

        settings_action = menu.addAction("Настройки...")
        settings_action.triggered.connect(lambda: self._bus.mode_changed.emit("open_settings", None))

        menu.addSeparator()

        reset_pos_action = menu.addAction("Сбросить позицию")
        reset_pos_action.triggered.connect(self._reset_position)

        minimize_action = menu.addAction("Свернуть в трей")
        minimize_action.triggered.connect(self._minimize_to_tray)

        quit_action = menu.addAction("Выход")
        quit_action.triggered.connect(lambda: self._bus.quit_requested.emit())

        menu.exec(event.globalPos())

    def closeEvent(self, event):
        """Закрытие окна — свернуть в трей."""
        self._minimize_to_tray()
        event.ignore()
