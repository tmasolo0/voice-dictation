#!/usr/bin/env python
"""Voice Dictation — entry point."""
import sys
import io
import logging
from pathlib import Path

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from app import Application
from core.config_manager import APP_DIR


def setup_logging():
    log_dir = APP_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "dictation.log"

    logging.basicConfig(
        level=logging.DEBUG if getattr(sys, 'frozen', False) else logging.ERROR,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_file, encoding='utf-8')]
    )

    # Frozen windowed: stdout/stderr -> лог-файл (не StringIO)
    if getattr(sys, 'frozen', False):
        log_stream = open(log_dir / "stdout.log", 'w', encoding='utf-8', errors='replace')
        sys.stdout = log_stream
        sys.stderr = log_stream

    def exception_handler(exc_type, exc_value, exc_tb):
        logging.exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = exception_handler


def main():
    setup_logging()
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    app = Application()
    app.start()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
