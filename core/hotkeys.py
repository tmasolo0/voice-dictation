"""HotkeyManager — глобальные горячие клавиши через Win32 RegisterHotKey."""

import ctypes
import ctypes.wintypes
import logging
import queue
import threading
import time

import win32gui

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL('user32', use_last_error=True)

# Virtual key codes
_VK = {
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
    'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
    'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    'space': 0x20, 'tab': 0x09, 'escape': 0x1B, 'enter': 0x0D,
    'backspace': 0x08, 'insert': 0x2D, 'delete': 0x2E,
    'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'capslock': 0x14, 'numlock': 0x90, 'scrolllock': 0x91,
    'printscreen': 0x2C, 'pause': 0x13, 'menu': 0x5D,
}
_MOD = {'ctrl': 0x0002, 'alt': 0x0001, 'shift': 0x0004, 'win': 0x0008}

_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_WM_APP_UPDATE = 0x8001  # custom: re-register a hotkey
_WM_APP_QUIT = 0x8002    # custom: exit message loop

_ID_RECORD = 1
_ID_HISTORY = 3


def _parse_hotkey(hotkey_str):
    """'ctrl+h' → (mod_flags, vk_code)."""
    parts = [p.strip().lower() for p in hotkey_str.split('+')]
    key, mods = parts[-1], parts[:-1]

    vk = _VK.get(key)
    if vk is None and len(key) == 1:
        vk = ord(key.upper())
    if vk is None:
        log.warning("Unknown key: %s", key)
        return 0, 0

    mod_flags = _MOD_NOREPEAT
    for m in mods:
        mod_flags |= _MOD.get(m, 0)
    return mod_flags, vk


class HotkeyManager:
    """Горячие клавиши через RegisterHotKey + GetAsyncKeyState polling для push-to-talk."""

    def __init__(self, event_bus, config):
        self._bus = event_bus
        self._recording = False
        self._enabled = True
        self._hotkey = config.get('recognition', 'hotkey', default='f9')
        self._history_hotkey = config.get('recognition', 'history_hotkey', default='ctrl+h')
        self._thread_id = None
        self._running = False
        self._update_q = queue.Queue()

    # --- public API (любой поток) ---

    def start(self):
        """Запустить слушатель горячих клавиш в фоновом потоке."""
        self._running = True
        threading.Thread(target=self._listener, daemon=True).start()

    def stop(self):
        """Остановить слушатель."""
        self._running = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, _WM_APP_QUIT, 0, 0)

    def set_enabled(self, enabled: bool):
        """Включить/выключить обработку горячей клавиши записи."""
        if self._enabled != enabled:
            log.debug("set_enabled: %s", enabled)
        self._enabled = enabled

    def update_hotkey(self, hotkey: str):
        """Обновить горячую клавишу записи без перезапуска."""
        log.info("update_hotkey: record '%s' -> '%s'", self._hotkey, hotkey)
        self._hotkey = hotkey
        self._request_update(_ID_RECORD, hotkey)

    def update_history_hotkey(self, hotkey: str):
        """Обновить горячую клавишу истории без перезапуска."""
        log.info("update_hotkey: history '%s' -> '%s'", self._history_hotkey, hotkey)
        self._history_hotkey = hotkey
        self._request_update(_ID_HISTORY, hotkey)

    def _request_update(self, hotkey_id, hotkey_str):
        if self._thread_id:
            self._update_q.put((hotkey_id, hotkey_str))
            user32.PostThreadMessageW(self._thread_id, _WM_APP_UPDATE, 0, 0)

    # --- listener thread ---

    def _listener(self):
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        # Форсируем создание очереди сообщений потока (без неё RegisterHotKey fails)
        msg_init = ctypes.wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg_init), None, 0, 0, 0)

        self._register(_ID_RECORD, self._hotkey)
        self._register(_ID_HISTORY, self._history_hotkey)

        log.info("RegisterHotKey started: record=%s history=%s",
                 self._hotkey, self._history_hotkey)

        msg = ctypes.wintypes.MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            if msg.message == _WM_HOTKEY:
                self._on_hotkey(msg.wParam)
            elif msg.message == _WM_APP_UPDATE:
                self._process_updates()
            elif msg.message == _WM_APP_QUIT:
                break

        user32.UnregisterHotKey(None, _ID_RECORD)
        user32.UnregisterHotKey(None, _ID_HISTORY)
        log.info("RegisterHotKey stopped")

    def _register(self, hotkey_id, hotkey_str):
        mod, vk = _parse_hotkey(hotkey_str)
        if vk == 0:
            return
        ok = user32.RegisterHotKey(None, hotkey_id, mod, vk)
        if not ok:
            err = ctypes.get_last_error()
            log.error("RegisterHotKey FAILED: '%s' id=%d vk=0x%02X mod=0x%04X err=%d",
                      hotkey_str, hotkey_id, vk, mod, err)
        else:
            log.info("RegisterHotKey OK: '%s' id=%d vk=0x%02X", hotkey_str, hotkey_id, vk)

    def _process_updates(self):
        while not self._update_q.empty():
            try:
                hid, hstr = self._update_q.get_nowait()
                ok = user32.UnregisterHotKey(None, hid)
                log.info("UnregisterHotKey id=%d: %s", hid, "OK" if ok else "FAILED")
                self._register(hid, hstr)
            except queue.Empty:
                break

    def _on_hotkey(self, hotkey_id):
        if hotkey_id == _ID_HISTORY:
            self._bus.mode_changed.emit("open_history", None)
            return

        if hotkey_id == _ID_RECORD:
            if not self._enabled or self._recording:
                return
            self._recording = True
            hwnd = win32gui.GetForegroundWindow()
            log.info("recording_start hwnd=%s", hwnd)
            self._bus.recording_start.emit(hwnd)
            threading.Thread(target=self._poll_key_up, daemon=True).start()

    def _poll_key_up(self):
        """Опрос GetAsyncKeyState до отпускания клавиши записи."""
        _, vk = _parse_hotkey(self._hotkey)
        while self._recording:
            state = user32.GetAsyncKeyState(vk)
            if not (state & 0x8000):
                if self._recording:
                    self._recording = False
                    log.info("recording_stop")
                    self._bus.recording_stop.emit()
                return
            time.sleep(0.02)
