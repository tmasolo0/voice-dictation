#!/usr/bin/env python
"""
Voice Dictation — простая утилита диктовки.

Минималистичный виджет для голосового ввода текста:
- F9 (push-to-talk) → распознавание → вставка текста
- Опциональный перевод на английский (для LLM задач)
"""

import sys
import logging
from pathlib import Path

# Добавляем директорию скрипта в sys.path
sys.path.insert(0, str(Path(__file__).parent))

import keyboard
import sounddevice as sd
import numpy as np
import time
import pyperclip
import pyautogui
from faster_whisper import WhisperModel
import threading

import win32gui
import win32api
import win32con

from PyQt6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QPoint, QTimer
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QIcon
import math

from core.config_manager import config


# === НАСТРОЙКИ ===
HOTKEY = config.get('recognition', 'hotkey', default='f9')
SAMPLE_RATE = 16000

# Модели: turbo для диктовки, medium для перевода (translate в turbo сломан)
MODEL_DICTATION = config.get('recognition', 'model', default='large-v3-turbo')
MODEL_TRANSLATE = 'medium'  # medium поддерживает task="translate"
MODELS_DIR = Path(__file__).parent / "models"

DEVICE = config.get('recognition', 'device', default='cuda')
COMPUTE_TYPE = config.get('recognition', 'compute_type', default='float16')
BEAM_SIZE = config.get('recognition', 'beam_size', default=5)

# Цвета состояний
COLORS = {
    "ready": QColor(76, 175, 80),       # Зелёный — готов
    "recording": QColor(244, 67, 54),   # Красный — запись
    "processing": QColor(255, 193, 7),  # Жёлтый — обработка
    "translate": QColor(33, 150, 243),  # Синий — режим перевода
}

# UI
ANIMATION_INTERVAL = 50  # мс
PULSE_SPEED_READY = 0.03
PULSE_SPEED_RECORDING = 0.1
FULLSCREEN_CHECK_INTERVAL = 1500
TRAY_ICON_SIZE = 64


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


class SignalEmitter(QObject):
    """Сигналы для обновления UI из других потоков."""
    state_changed = pyqtSignal(str)


class DictationWidget(QWidget):
    """Минималистичный виджет для голосовой диктовки."""

    def __init__(self):
        super().__init__()

        self.signals = SignalEmitter()
        self.signals.state_changed.connect(self._set_state)

        # Состояние
        self.current_state = "ready"
        self.recording = False
        self.audio_data = []
        self.model = None
        self.current_model_name = None  # Какая модель сейчас загружена
        self.stream = None
        self.focused_window = None

        # Режим перевода на английский
        self.translate_mode = config.get('dictation', 'translate_to_english', default=False)

        # Для перетаскивания
        self.drag_position = QPoint()

        # Автоскрытие в fullscreen
        self.hidden_by_fullscreen = False

        # Анимация
        self.animation_phase = 0.0

        # Системный трей
        self.tray_icon = None
        self.minimized_to_tray = False

        self._setup_ui()
        self._setup_tray()
        self._init_model()
        self._start_audio_stream()
        self._start_keyboard_listener()
        self._start_fullscreen_monitor()
        self._start_animation()

    def _setup_ui(self):
        """Настройка UI виджета."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        size = config.get('widget', 'size', default=100)
        self.setFixedSize(size, size)

        pos = self._load_position()
        self.move(pos)

        self.setWindowTitle("Dictation")

    def _setup_tray(self):
        """Настройка системного трея."""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self._create_tray_icon("ready"))
        self.tray_icon.setToolTip("Voice Dictation")
        self.tray_icon.activated.connect(self._on_tray_activated)

        tray_menu = QMenu()

        # Режим перевода
        translate_action = tray_menu.addAction(
            "✓ Перевод → EN" if self.translate_mode else "Перевод → EN"
        )
        translate_action.triggered.connect(self._toggle_translate_mode)

        tray_menu.addSeparator()

        show_action = tray_menu.addAction("Показать")
        show_action.triggered.connect(self._show_from_tray)

        quit_action = tray_menu.addAction("Выход")
        quit_action.triggered.connect(self._quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def _toggle_translate_mode(self):
        """Переключение режима перевода."""
        self.translate_mode = not self.translate_mode
        config.set('dictation', 'translate_to_english', self.translate_mode)

        # Swap модели: turbo ↔ medium
        new_model = MODEL_TRANSLATE if self.translate_mode else MODEL_DICTATION
        if self.current_model_name != new_model:
            self.signals.state_changed.emit("processing")  # Показываем что грузим
            self._load_model(new_model)
            self.signals.state_changed.emit("ready")

        # Обновляем меню трея
        self._setup_tray()

        mode_text = f"EN (перевод, {MODEL_TRANSLATE})" if self.translate_mode else f"RU/EN ({MODEL_DICTATION})"
        print(f"Режим: {mode_text}")
        self.tray_icon.showMessage(
            "Dictation",
            f"Режим: {mode_text}",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

    def _create_tray_icon(self, state: str) -> QIcon:
        """Создание иконки для трея."""
        pixmap = QPixmap(TRAY_ICON_SIZE, TRAY_ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Цвет в зависимости от режима перевода
        if self.translate_mode and state == "ready":
            color = COLORS["translate"]
        else:
            color = COLORS.get(state, COLORS["ready"])

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)

        margin = 4
        painter.drawEllipse(margin, margin,
                          TRAY_ICON_SIZE - 2*margin,
                          TRAY_ICON_SIZE - 2*margin)
        painter.end()

        return QIcon(pixmap)

    def _on_tray_activated(self, reason):
        """Обработка клика по иконке в трее."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        """Показать виджет из трея."""
        self.show()
        self.activateWindow()
        self.minimized_to_tray = False

    def _minimize_to_tray(self):
        """Свернуть в трей."""
        self.hide()
        self.minimized_to_tray = True

    def _load_position(self) -> QPoint:
        """Загрузка позиции из конфига."""
        x = config.get('widget', 'position', 'x', default=None)
        y = config.get('widget', 'position', 'y', default=None)

        if x is not None and y is not None:
            pos = QPoint(x, y)
            if self._is_position_valid(pos):
                return pos

        return self._get_default_position()

    def _get_default_position(self) -> QPoint:
        """Позиция по умолчанию (правый нижний угол)."""
        screen = QApplication.primaryScreen().geometry()
        size = config.get('widget', 'size', default=100)
        return QPoint(screen.width() - size - 50, screen.height() - size - 100)

    def _is_position_valid(self, pos: QPoint) -> bool:
        """Проверка, что позиция на экране."""
        screen = QApplication.primaryScreen().geometry()
        return screen.contains(pos)

    def _save_position(self):
        """Сохранение позиции в конфиг."""
        config.set('widget', 'position', 'x', self.x())
        config.set('widget', 'position', 'y', self.y())

    def _init_model(self):
        """Инициализация модели Whisper."""
        # Выбираем модель в зависимости от режима
        model_name = MODEL_TRANSLATE if self.translate_mode else MODEL_DICTATION
        self._load_model(model_name)

    def _load_model(self, model_name: str):
        """Загрузка конкретной модели Whisper."""
        if self.current_model_name == model_name:
            return  # Уже загружена

        print(f"Загрузка модели {model_name}...")

        # Выгружаем текущую модель из VRAM
        if self.model is not None:
            del self.model
            self.model = None
            import gc
            gc.collect()
            # Очистка CUDA кэша
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

        # Проверяем локальную папку models/
        local_path = MODELS_DIR / model_name
        model_path = str(local_path) if local_path.exists() else model_name

        self.model = WhisperModel(
            model_path,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )
        self.current_model_name = model_name
        print(f"Модель {model_name} загружена ({DEVICE})")

    def _start_audio_stream(self):
        """Запуск аудио потока."""
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=self._audio_callback,
            blocksize=int(SAMPLE_RATE * 0.1),
        )
        self.stream.start()

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback для записи аудио."""
        if self.recording:
            self.audio_data.append(indata.copy())

    def _start_keyboard_listener(self):
        """Запуск слушателя клавиатуры."""
        def listener():
            keyboard.hook(self._on_key_event)
            keyboard.wait()

        thread = threading.Thread(target=listener, daemon=True)
        thread.start()

    def _start_fullscreen_monitor(self):
        """Запуск мониторинга полноэкранных приложений."""
        if not config.get('widget', 'hide_in_fullscreen', default=True):
            return

        self.fullscreen_timer = QTimer()
        self.fullscreen_timer.timeout.connect(self._check_fullscreen_visibility)
        self.fullscreen_timer.start(FULLSCREEN_CHECK_INTERVAL)

    def _check_fullscreen_visibility(self):
        """Проверка видимости в fullscreen."""
        if self.minimized_to_tray:
            return

        is_fullscreen = is_fullscreen_app_active()

        if is_fullscreen and not self.hidden_by_fullscreen:
            self.hide()
            self.hidden_by_fullscreen = True
        elif not is_fullscreen and self.hidden_by_fullscreen:
            self.show()
            self.hidden_by_fullscreen = False

    def _start_animation(self):
        """Запуск анимации."""
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate)
        self.animation_timer.start(ANIMATION_INTERVAL)

    def _animate(self):
        """Обновление анимации."""
        if self.current_state == "ready":
            self.animation_phase += PULSE_SPEED_READY
        elif self.current_state == "recording":
            self.animation_phase += PULSE_SPEED_RECORDING

        if self.animation_phase > 2 * math.pi:
            self.animation_phase -= 2 * math.pi

        self.update()

    def _on_key_event(self, event):
        """Обработка событий клавиатуры."""
        if event.name != HOTKEY:
            return

        if event.event_type == 'down' and not self.recording:
            # Начало записи
            self.focused_window = win32gui.GetForegroundWindow()
            self.recording = True
            self.audio_data = []
            self.signals.state_changed.emit("recording")
            print("Запись...")

        elif event.event_type == 'up' and self.recording:
            # Конец записи
            self.recording = False
            self.signals.state_changed.emit("processing")

            if self.audio_data:
                audio_np = np.concatenate(self.audio_data, axis=0).flatten()
                threading.Thread(
                    target=self._process_audio,
                    args=(audio_np,),
                    daemon=True
                ).start()
            else:
                self.signals.state_changed.emit("ready")

    def _process_audio(self, audio_np):
        """Обработка аудио: распознавание и вставка."""
        try:
            start = time.time()

            # Whisper: transcribe или translate
            if self.translate_mode:
                # Перевод на английский (модель medium поддерживает translate)
                segments, info = self.model.transcribe(
                    audio_np,
                    task="translate",
                    vad_filter=True,
                    condition_on_previous_text=False,
                    beam_size=BEAM_SIZE,
                )
            else:
                # Обычная транскрипция (автоопределение языка)
                segments, info = self.model.transcribe(
                    audio_np,
                    vad_filter=True,
                    initial_prompt=config.get_initial_prompt(),
                    condition_on_previous_text=False,
                    beam_size=BEAM_SIZE,
                )

            text = "".join([segment.text for segment in segments]).strip()
            elapsed = time.time() - start

            if text:
                mode_info = f"({info.language})→EN" if self.translate_mode else f"({info.language})"
                print(f"[{elapsed:.1f}с] {mode_info}: {text}")
                self._paste_text(text)
            else:
                print("Пустой результат")

        except Exception as e:
            print(f"Ошибка: {e}")

        finally:
            self.signals.state_changed.emit("ready")

    def _paste_text(self, text: str):
        """Вставка текста в активное окно."""
        try:
            if self.focused_window:
                win32gui.SetForegroundWindow(self.focused_window)
                time.sleep(0.05)

            pyperclip.copy(text)
            time.sleep(0.05)
            pyautogui.hotkey('ctrl', 'v')

        except Exception as e:
            print(f"Ошибка вставки: {e}")

    def _set_state(self, state: str):
        """Установка состояния UI."""
        self.current_state = state
        self.tray_icon.setIcon(self._create_tray_icon(state))
        self.animation_phase = 0.0
        self.update()

    def paintEvent(self, event):
        """Отрисовка виджета."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = self.width()
        center = size // 2

        # Цвет в зависимости от режима
        if self.translate_mode and self.current_state == "ready":
            base_color = COLORS["translate"]
        else:
            base_color = COLORS.get(self.current_state, COLORS["ready"])

        # Пульсация
        if self.current_state in ("ready", "recording"):
            pulse = 0.15 * math.sin(self.animation_phase)
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

        # Иконка режима перевода (EN)
        if self.translate_mode and self.current_state == "ready":
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            font = painter.font()
            font.setPointSize(int(size * 0.15))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "EN")

        painter.end()

    def mousePressEvent(self, event):
        """Начало перетаскивания."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Перетаскивание."""
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Конец перетаскивания."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._save_position()
            event.accept()

    def contextMenuEvent(self, event):
        """Контекстное меню."""
        menu = QMenu(self)

        # Режим перевода
        translate_action = menu.addAction(
            "✓ Перевод → EN" if self.translate_mode else "Перевод → EN"
        )
        translate_action.triggered.connect(self._toggle_translate_mode)

        menu.addSeparator()

        minimize_action = menu.addAction("Свернуть в трей")
        minimize_action.triggered.connect(self._minimize_to_tray)

        quit_action = menu.addAction("Выход")
        quit_action.triggered.connect(self._quit)

        menu.exec(event.globalPos())

    def _quit(self):
        """Выход из приложения."""
        self._save_position()
        if self.stream:
            self.stream.stop()
            self.stream.close()
        QApplication.quit()

    def closeEvent(self, event):
        """Обработка закрытия окна."""
        self._minimize_to_tray()
        event.ignore()


def setup_logging():
    """Настройка логирования."""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "dictation.log", encoding='utf-8'),
        ]
    )

    def exception_handler(exc_type, exc_value, exc_tb):
        logging.exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = exception_handler


def main():
    """Точка входа."""
    setup_logging()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    widget = DictationWidget()
    widget.show()

    print("=" * 40)
    print("Voice Dictation")
    print("=" * 40)
    print(f"Горячая клавиша: {HOTKEY.upper()}")
    print(f"Режим: {'EN (перевод)' if widget.translate_mode else 'RU/EN (авто)'}")
    print("ПКМ → переключение режима")
    print("=" * 40)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
