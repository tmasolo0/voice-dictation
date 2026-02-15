"""HistoryDialog — диалог просмотра истории диктовок."""

import time
from datetime import datetime

import pyautogui
import pyperclip
import win32gui
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class HistoryDialog(QDialog):
    """Диалог истории диктовок — список, поиск, копирование, вставка, очистка."""

    def __init__(self, history_manager, target_hwnd=None, parent=None):
        super().__init__(parent)
        self._history = history_manager
        self._target_hwnd = target_hwnd

        self.setWindowTitle("История диктовок")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
        )

        layout = QVBoxLayout(self)

        # Поиск
        self._search = QLineEdit()
        self._search.setPlaceholderText("Поиск...")
        self._search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search)

        # Пустая история
        self._empty_label = QLabel("История пуста")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

        # Список
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list)

        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._insert_btn = QPushButton("Вставить")
        self._insert_btn.setEnabled(False)
        self._insert_btn.clicked.connect(self._on_insert)
        btn_layout.addWidget(self._insert_btn)

        self._clear_btn = QPushButton("Очистить историю")
        self._clear_btn.clicked.connect(self._on_clear)
        btn_layout.addWidget(self._clear_btn)
        layout.addLayout(btn_layout)

        self._refresh_list()

    def _refresh_list(self):
        """Загрузить и отобразить все записи."""
        self._list.clear()
        records = self._history.get_all()

        if not records:
            self._empty_label.show()
            self._list.hide()
            self._insert_btn.setEnabled(False)
            return

        self._empty_label.hide()
        self._list.show()

        for rec in records:
            ts = datetime.fromisoformat(rec['timestamp']).strftime("%d.%m %H:%M")
            text = rec['text'].replace('\n', ' ')
            preview = text[:80] + "..." if len(text) > 80 else text
            item = QListWidgetItem(f"{ts}  {preview}")
            item.setData(Qt.ItemDataRole.UserRole, rec)
            self._list.addItem(item)

    def _on_search_changed(self, text: str):
        """Фильтрация списка по тексту."""
        query = text.strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            rec = item.data(Qt.ItemDataRole.UserRole)
            visible = not query or query in rec['text'].lower()
            item.setHidden(not visible)

    def _on_item_clicked(self, item: QListWidgetItem):
        """Копировать текст в буфер при клике."""
        rec = item.data(Qt.ItemDataRole.UserRole)
        pyperclip.copy(rec['text'])
        self._insert_btn.setEnabled(True)

    def _on_selection_changed(self):
        """Включить/выключить кнопку Вставить."""
        self._insert_btn.setEnabled(bool(self._list.selectedItems()))

    def _on_insert(self):
        """Вставить выбранную запись в целевое окно."""
        items = self._list.selectedItems()
        if not items:
            return
        rec = items[0].data(Qt.ItemDataRole.UserRole)
        text = rec['text']

        self.accept()

        if self._target_hwnd:
            try:
                win32gui.SetForegroundWindow(self._target_hwnd)
                time.sleep(0.05)
            except Exception:
                pass

        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey('ctrl', 'v')

    def _on_clear(self):
        """Очистить всю историю после подтверждения."""
        result = QMessageBox.question(
            self,
            "Очистить историю",
            "Удалить все записи?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._history.clear()
            self._refresh_list()
