"""PreviewPopup — немодальный popup для предпросмотра распознанного текста."""

import win32gui
import win32con

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QProgressBar, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QScreen


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

    def __init__(self, parent_widget):
        super().__init__(None)
        self._parent_widget = parent_widget
        self._total_ms = 0
        self._remaining_ms = 0
        self._editing = False

        self.setObjectName("PreviewPopup")
        self.setWindowFlags(
            Qt.WindowType.ToolTip |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(POPUP_WIDTH)

        self._setup_ui()
        self.setStyleSheet(STYLESHEET)

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(TIMER_TICK_MS)
        self._auto_timer.timeout.connect(self._on_timer_tick)

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

    def show_preview(self, text: str, auto_delay: int):
        """Показать popup с текстом и запустить таймер авто-вставки."""
        if auto_delay == 0:
            self.insert_requested.emit(text)
            return

        self._editing = False
        self._text_edit.setPlainText(text)

        self._position_near_widget()
        self.show()
        self._apply_noactivate()

        self._total_ms = auto_delay * 1000
        self._remaining_ms = self._total_ms
        self._timer_bar.setValue(PROGRESS_MAX)
        self._timer_bar.setVisible(True)
        self._auto_timer.start()

    def _apply_noactivate(self):
        """Установить WS_EX_NOACTIVATE чтобы popup не крал фокус."""
        try:
            hwnd = int(self.winId())
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style |= win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOPMOST
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
            )
        except Exception as e:
            print(f"PreviewPopup: WS_EX_NOACTIVATE failed: {e}")

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

        # Выбор стороны
        if x_left >= screen.x():
            x = x_left
        else:
            x = x_right

        # Вертикальная коррекция
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
        if not self._editing and self._auto_timer.isActive():
            self._editing = True
            self._auto_timer.stop()
            self._timer_bar.setVisible(False)

    def _on_insert(self):
        self._auto_timer.stop()
        text = self._text_edit.toPlainText().strip()
        if not text:
            self._on_cancel()
            return
        self.insert_requested.emit(text)
        self.hide()

    def _on_cancel(self):
        self._auto_timer.stop()
        self.cancel_requested.emit()
        self.hide()

    def update_text(self, text: str):
        """Обновить текст (для re-dictate в Plan 02)."""
        self._editing = False
        self._text_edit.setPlainText(text)
        if self._total_ms > 0:
            self._remaining_ms = self._total_ms
            self._timer_bar.setValue(PROGRESS_MAX)
            self._timer_bar.setVisible(True)
            self._auto_timer.start()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_insert()
        elif key == Qt.Key.Key_Escape:
            self._on_cancel()
        else:
            super().keyPressEvent(event)
