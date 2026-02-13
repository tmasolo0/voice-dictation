#!/usr/bin/env python
"""Voice Dictation — entry point."""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from app import Application


def setup_logging():
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_dir / "dictation.log", encoding='utf-8')]
    )
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
