#!/usr/bin/env python
"""Voice Dictation — entry point."""
import ctypes
import json
import sys
import io
import logging
from pathlib import Path

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from app import Application
from core.config_manager import APP_DIR, CONFIG_FILE


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate():
    """Перезапуск с правами администратора (UAC prompt)."""
    if getattr(sys, 'frozen', False):
        exe = sys.executable
        params = ' '.join(f'"{a}"' for a in sys.argv[1:])
        workdir = str(Path(sys.executable).parent)
    else:
        exe = sys.executable
        params = ' '.join(f'"{a}"' for a in sys.argv)
        workdir = str(Path(__file__).parent)

    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, workdir, 1)
    if int(ret) > 32:
        sys.exit(0)
    # UAC отклонён — продолжаем без повышения


def _check_elevation():
    """Проверить config.json → system.run_as_admin и повысить привилегии если нужно."""
    if _is_admin():
        return
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            if cfg.get('system', {}).get('run_as_admin', False):
                _elevate()
    except Exception:
        pass


def setup_logging():
    log_dir = APP_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "dictation.log"

    # Debug-режим: через config.json или наличие файла debug.flag
    debug_forced = (APP_DIR / "debug.flag").exists()
    if not debug_forced:
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                debug_forced = cfg.get('system', {}).get('debug_logging', False)
        except Exception:
            pass

    level = logging.DEBUG if (debug_forced or not getattr(sys, 'frozen', False)) else logging.INFO

    # force=True гарантирует настройку даже если библиотеки уже настроили root logger
    fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]

    # Dev-режим: дублируем в консоль для отладки
    if not getattr(sys, 'frozen', False):
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(level=level, format=fmt, handlers=handlers, force=True)

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
    _check_elevation()
    setup_logging()
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    app = Application()
    app.start()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
