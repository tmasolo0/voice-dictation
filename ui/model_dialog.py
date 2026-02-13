"""ModelManagerDialog — UI для управления моделями Whisper."""

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.model_catalog import ALLOW_PATTERNS, MODEL_CATALOG, MODELS_DIR, is_model_downloaded


class ModelDownloadThread(QThread):
    """Скачивание модели через huggingface_hub в отдельном потоке."""

    progress = pyqtSignal(int, int)    # downloaded_bytes, total_bytes
    finished_ok = pyqtSignal(str)      # model_name
    error = pyqtSignal(str)            # error message

    def __init__(self, repo_id: str, output_dir: Path, model_name: str):
        super().__init__()
        self._repo_id = repo_id
        self._output_dir = output_dir
        self._model_name = model_name

    def run(self):
        try:
            from huggingface_hub import snapshot_download
            from tqdm import tqdm as tqdm_base

            thread_ref = self

            class ProgressTqdm(tqdm_base):
                def update(self, n=1):
                    super().update(n)
                    if self.total is not None:
                        thread_ref.progress.emit(int(self.n), int(self.total))

            snapshot_download(
                self._repo_id,
                local_dir=str(self._output_dir),
                allow_patterns=ALLOW_PATTERNS,
                tqdm_class=ProgressTqdm,
            )
            self.finished_ok.emit(self._model_name)
        except Exception as e:
            self.error.emit(str(e))


class ModelManagerDialog(QDialog):
    """Диалог управления моделями — список, скачивание, выбор активной."""

    def __init__(self, config, event_bus=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._bus = event_bus
        self._download_thread = None
        self._model_selected = None

        self.setWindowTitle("Управление моделями")
        self.setMinimumSize(550, 400)

        layout = QVBoxLayout(self)

        # Таблица моделей
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Модель", "Размер", "Статус", ""])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().hide()
        layout.addWidget(self._table)

        # Прогресс-бар скачивания
        self._progress_bar = QProgressBar()
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        # Статус-строка
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # Кнопка закрыть
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Подписка на сигналы загрузки модели
        if self._bus:
            self._bus.model_load_started.connect(self._on_model_load_started)
            self._bus.model_load_finished.connect(self._on_model_load_finished)
            self._bus.model_load_failed.connect(self._on_model_load_failed)

        self._populate_table()

    @property
    def model_selected(self) -> str | None:
        """Имя выбранной модели (None если не менял)."""
        return self._model_selected

    def _populate_table(self):
        """Заполнить таблицу моделями из каталога."""
        active_model = self._config.get('recognition', 'model', default='large-v3-turbo')
        models = list(MODEL_CATALOG.items())

        self._table.setRowCount(len(models))

        for row, (name, info) in enumerate(models):
            downloaded = is_model_downloaded(name)
            is_active = downloaded and (name == active_model)

            # Колонка 0: Имя + описание
            item_name = QTableWidgetItem(f"{name}\n{info['description']}")
            self._table.setItem(row, 0, item_name)

            # Колонка 1: Размер
            item_size = QTableWidgetItem(f"{info['size_gb']:.1f} GB")
            self._table.setItem(row, 1, item_size)

            # Колонка 2: Статус
            if is_active:
                status = "Активна"
            elif downloaded:
                status = "Установлена"
            elif not info['downloadable']:
                status = "Ручная установка"
            else:
                status = "Не скачана"
            self._table.setItem(row, 2, QTableWidgetItem(status))

            # Колонка 3: Кнопка действия
            btn = QPushButton()
            if is_active:
                btn.setText("Активна")
                btn.setEnabled(False)
            elif downloaded:
                btn.setText("Выбрать")
                btn.clicked.connect(lambda checked, n=name: self._on_select_model(n))
            elif info['downloadable']:
                btn.setText("Скачать")
                btn.clicked.connect(lambda checked, n=name: self._on_download_model(n))
            else:
                btn.setText("—")
                btn.setEnabled(False)
            self._table.setCellWidget(row, 3, btn)

        self._table.resizeRowsToContents()

    def _on_select_model(self, model_name: str):
        """Выбрать модель как активную и запустить загрузку."""
        self._config.set('recognition', 'model', model_name)
        self._config.save()
        self._model_selected = model_name
        self._status_label.setText(f"Переключение на {model_name}...")
        self._populate_table()
        # Триггер загрузки модели через EventBus
        if self._bus:
            self._bus.mode_changed.emit("select_model", model_name)

    def _on_model_load_started(self, model_name: str):
        """Модель начала загружаться."""
        self._status_label.setText(f"Выгрузка старой модели, загрузка {model_name}...")

    def _on_model_load_finished(self, model_name: str):
        """Модель загружена."""
        self._status_label.setText(f"Модель {model_name} загружена ✓")
        self._populate_table()

    def _on_model_load_failed(self, error: str):
        """Ошибка загрузки модели."""
        self._status_label.setText(f"Ошибка: {error}")

    def _on_download_model(self, model_name: str):
        """Запустить скачивание модели."""
        if self._download_thread is not None and self._download_thread.isRunning():
            QMessageBox.warning(self, "Скачивание", "Дождитесь завершения текущего скачивания")
            return

        info = MODEL_CATALOG[model_name]
        self._download_thread = ModelDownloadThread(
            info['repo_id'],
            MODELS_DIR / model_name,
            model_name,
        )
        self._download_thread.progress.connect(self._on_download_progress)
        self._download_thread.finished_ok.connect(self._on_download_finished)
        self._download_thread.error.connect(self._on_download_error)

        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._download_thread.start()

    def _on_download_progress(self, current: int, total: int):
        """Обновить прогресс-бар."""
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)

    def _on_download_finished(self, model_name: str):
        """Скачивание завершено."""
        self._progress_bar.hide()
        self._download_thread = None
        self._populate_table()

    def _on_download_error(self, msg: str):
        """Ошибка скачивания."""
        self._progress_bar.hide()
        self._download_thread = None
        QMessageBox.critical(self, "Ошибка скачивания", msg)
