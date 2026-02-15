"""PreviewPopup — немодальный popup для предпросмотра распознанного текста."""

import keyboard

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QProgressBar, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal


POPUP_WIDTH = 350
POPUP_GAP = 10
TIMER_TICK_MS = 50
PROGRESS_MAX = 1000

STYLESHEET = """
QWidget#PreviewPopup {
    background-color: #2b2b2b;
    border: 1px solid #555;
    border-radius: 8px;
}
QTextEdit {
    background-color: #333;
    color: #fff;
    border: none;
    border-radius: 4px;
    padding: 6px;
    font-size: 13px;
}
QProgressBar {
    background-color: #444;
    border: none;
    border-radius: 2px;
    max-height: 4px;
    min-height: 4px;
}
QProgressBar::chunk {
    background-color: #4CAF50;
    border-radius: 2px;
}
QPushButton {
    background-color: #444;
    color: #ccc;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 11px;
}
QPushButton:hover {
    background-color: #555;
}
"""


class PreviewPopup(QWidget):
    """Немодальный popup для предпросмотра и редактирования текста перед вставкой."""

    insert_requested = pyqtSignal(str)
    cancel_requested = pyqtSignal()
    redictate_requested = pyqtSignal()

    # Thread-safe triggers для глобальных keyboard hooks
    _trigger_insert = pyqtSignal()
    _trigger_cancel = pyqtSignal()

    def __init__(self, parent_widget):
        super().__init__(None)
        self._parent_widget = parent_widget
        self._total_ms = 0
        self._remaining_ms = 0
        self._editing = False
        self._waiting = False
        self._hk_enter = None
        self._hk_esc = None

        self.setObjectName("PreviewPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(POPUP_WIDTH)

        self._setup_ui()
        self.setStyleSheet(STYLESHEET)

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(TIMER_TICK_MS)
        self._auto_timer.timeout.connect(self._on_timer_tick)

        # Keyboard hook callbacks приходят из другого потока —
        # сигналы автоматически маршрутизируются в main thread через QueuedConnection
        self._trigger_insert.connect(self._on_insert)
        self._trigger_cancel.connect(self._on_cancel)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._text_edit = QTextEdit()
        self._text_edit.setMaximumHeight(80)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._text_edit)

        self._timer_bar = QProgressBar()
        self._timer_bar.setRange(0, PROGRESS_MAX)
        self._timer_bar.setValue(PROGRESS_MAX)
        self._timer_bar.setTextVisible(False)
        layout.addWidget(self._timer_bar)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self._btn_redictate = QPushButton("Re")
        self._btn_redictate.setToolTip("Re-dictate")
        self._btn_redictate.setFixedWidth(36)
        self._btn_redictate.clicked.connect(self.redictate_requested.emit)
        btn_layout.addWidget(self._btn_redictate)

        btn_layout.addStretch()

        self._btn_cancel = QPushButton("Esc")
        self._btn_cancel.setToolTip("Cancel")
        self._btn_cancel.setFixedWidth(40)
        self._btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._btn_cancel)

        layout.addLayout(btn_layout)

    # ── Show / Position ──────────────────────────────────────

    def show_preview(self, text: str, auto_delay: int):
        """Показать popup с текстом и запустить таймер авто-вставки."""
        if auto_delay == 0:
            self.insert_requested.emit(text)
            return

        self._editing = False
        self._waiting = False
        self._text_edit.setStyleSheet("")
        self._text_edit.setPlainText(text)

        self._position_near_widget()
        self.show()
        self._register_hotkeys()

        self._total_ms = auto_delay * 1000
        self._remaining_ms = self._total_ms
        self._timer_bar.setValue(PROGRESS_MAX)
        self._timer_bar.setVisible(True)
        self._auto_timer.start()

    def _position_near_widget(self):
        """Позиционировать popup слева от parent_widget, с fallback вправо."""
        pw = self._parent_widget
        pw_pos = pw.pos()
        pw_size = pw.size()

        popup_h = self.sizeHint().height()
        self.setFixedHeight(max(popup_h, 120))
        popup_h = self.height()

        x_left = pw_pos.x() - POPUP_WIDTH - POPUP_GAP
        x_right = pw_pos.x() + pw_size.width() + POPUP_GAP
        y = pw_pos.y()

        screen = self._get_screen_geometry()

        if x_left >= screen.x():
            x = x_left
        else:
            x = x_right

        if y + popup_h > screen.y() + screen.height():
            y = screen.y() + screen.height() - popup_h
        if y < screen.y():
            y = screen.y()

        self.move(x, y)

    def _get_screen_geometry(self):
        """Получить геометрию экрана, на котором находится parent_widget."""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.screenAt(self._parent_widget.pos())
        if screen is None:
            screen = QApplication.primaryScreen()
        return screen.availableGeometry()

    # ── Global keyboard hooks ────────────────────────────────

    def _register_hotkeys(self):
        """Зарегистрировать глобальные Enter/Esc хуки (suppress — не пропускать в целевое окно)."""
        self._unregister_hotkeys()
        self._hk_enter = keyboard.add_hotkey('enter', self._trigger_insert.emit, suppress=True)
        self._hk_esc = keyboard.add_hotkey('escape', self._trigger_cancel.emit, suppress=True)

    def _unregister_hotkeys(self):
        """Снять глобальные Enter/Esc хуки."""
        if self._hk_enter is not None:
            try:
                keyboard.remove_hotkey(self._hk_enter)
            except (KeyError, ValueError):
                pass
            self._hk_enter = None
        if self._hk_esc is not None:
            try:
                keyboard.remove_hotkey(self._hk_esc)
            except (KeyError, ValueError):
                pass
            self._hk_esc = None

    # ── Timer ────────────────────────────────────────────────

    def _on_timer_tick(self):
        self._remaining_ms -= TIMER_TICK_MS
        if self._remaining_ms <= 0:
            self._remaining_ms = 0
            self._auto_timer.stop()
            self._on_insert()
            return

        progress = int(self._remaining_ms * PROGRESS_MAX / self._total_ms)
        self._timer_bar.setValue(progress)

    def _on_text_changed(self):
        """При редактировании текста пользователем — остановить таймер."""
        if not self._editing and not self._waiting and self._auto_timer.isActive():
            self._editing = True
            self._auto_timer.stop()
            self._timer_bar.setVisible(False)

    # ── Actions ──────────────────────────────────────────────

    def _on_insert(self):
        if not self.isVisible() or self._waiting:
            return
        self._unregister_hotkeys()
        self._auto_timer.stop()
        text = self._text_edit.toPlainText().strip()
        if not text:
            self._on_cancel()
            return
        self.insert_requested.emit(text)
        self.hide()

    def _on_cancel(self):
        if not self.isVisible():
            return
        self._waiting = False
        self._unregister_hotkeys()
        self._auto_timer.stop()
        self.cancel_requested.emit()
        self.hide()

    def hideEvent(self, event):
        """Гарантировать снятие хуков при скрытии popup."""
        self._unregister_hotkeys()
        super().hideEvent(event)

    # ── Re-dictate support ───────────────────────────────────

    def stop_timer(self):
        """Остановить таймер и скрыть progress bar."""
        self._auto_timer.stop()
        self._timer_bar.setVisible(False)

    def restart_timer(self, delay_seconds: int):
        """Перезапустить таймер с новым delay."""
        self._waiting = False
        self._editing = False
        self._total_ms = delay_seconds * 1000
        self._remaining_ms = self._total_ms
        self._timer_bar.setValue(PROGRESS_MAX)
        self._timer_bar.setVisible(True)
        self._auto_timer.start()

    def set_waiting_state(self):
        """Показать состояние ожидания записи (re-dictate)."""
        self._auto_timer.stop()
        self._timer_bar.setVisible(False)
        self._editing = False
        self._waiting = True
        self._text_edit.setPlainText("Нажмите F9 для записи...")
        self._text_edit.setStyleSheet("QTextEdit { color: #888; }")
        self._btn_redictate.setEnabled(False)

    def update_text(self, text: str):
        """Обновить текст после re-dictate."""
        self._editing = False
        self._waiting = False
        self._text_edit.setStyleSheet("")
        self._text_edit.setPlainText(text)
        self._btn_redictate.setEnabled(True)
