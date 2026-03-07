"""TextInserter — вставка текста в активное окно (гибридная стратегия)."""

import ctypes
import ctypes.wintypes
import logging
import threading
import time
import win32gui
import win32api
import win32con
import win32clipboard
import win32process

log = logging.getLogger(__name__)

# ── SendInput structures ─────────────────────────────────────
# Union должен включать MOUSEINPUT (самый большой член),
# иначе sizeof(INPUT) будет меньше ожидаемого и SendInput вернёт ERROR_INVALID_PARAMETER (87).
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

_user32 = ctypes.WinDLL('user32', use_last_error=True)

# ── Классы окон терминалов (Ctrl+Shift+V вместо Ctrl+V) ─────
TERMINAL_CLASSES = {
    'ConsoleWindowClass',        # cmd.exe, legacy console
    'CASCADIA_HOSTING_WINDOW_CLASS',  # Windows Terminal
    'mintty',                    # Git Bash, MSYS2
    'VirtualConsoleClass',       # ConEmu
    'PuTTY',                     # PuTTY
}

# ── Классы Electron/Chromium (SendInput Ctrl+V ненадёжен) ────
ELECTRON_CLASSES = {
    'Chrome_WidgetWin_1',        # Electron (VS Code, Slack, Discord...)
    'Chrome_WidgetWin_2',        # Chromium variants
}

# Порог длины текста: выше — clipboard paste, ниже — Unicode SendInput
UNICODE_THRESHOLD = 50


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ('dx', ctypes.c_long),
        ('dy', ctypes.c_long),
        ('mouseData', ctypes.c_ulong),
        ('dwFlags', ctypes.c_ulong),
        ('time', ctypes.c_ulong),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', ctypes.c_ushort),
        ('wScan', ctypes.c_ushort),
        ('dwFlags', ctypes.c_ulong),
        ('time', ctypes.c_ulong),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ('uMsg', ctypes.c_ulong),
        ('wParamL', ctypes.c_ushort),
        ('wParamH', ctypes.c_ushort),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [
            ('mi', _MOUSEINPUT),
            ('ki', _KEYBDINPUT),
            ('hi', _HARDWAREINPUT),
        ]
    _fields_ = [
        ('type', ctypes.c_ulong),
        ('u', _U),
    ]


def _key_input(vk, flags=0):
    """Создать INPUT-структуру для SendInput с правильным scan code."""
    scan = _user32.MapVirtualKeyW(vk, 0)
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.wScan = scan
    inp.u.ki.dwFlags = flags
    return inp


def _unicode_input(scan_code, flags=0):
    """Создать INPUT-структуру для Unicode-символа (KEYEVENTF_UNICODE)."""
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = 0
    inp.u.ki.wScan = scan_code
    inp.u.ki.dwFlags = KEYEVENTF_UNICODE | flags
    return inp


# ── Публичные утилиты ──

def detect_window_type(hwnd):
    """Определить тип окна: 'terminal', 'electron' или 'normal'."""
    if not hwnd:
        return 'normal'
    try:
        cls = win32gui.GetClassName(hwnd)
        if cls in TERMINAL_CLASSES:
            return 'terminal'
        if cls in ELECTRON_CLASSES:
            return 'electron'
    except Exception:
        pass
    return 'normal'


def send_text_unicode(text):
    """Отправить текст посимвольно через KEYEVENTF_UNICODE.

    Каждый символ отправляется как пара down/up событий.
    \\n → VK_RETURN, \\t → VK_TAB, остальное — Unicode scan code.
    Символы за пределами BMP (emoji) кодируются UTF-16 surrogate pairs.
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    events = []

    for char in text:
        if char == '\n':
            events.append(_key_input(win32con.VK_RETURN))
            events.append(_key_input(win32con.VK_RETURN, KEYEVENTF_KEYUP))
        elif char == '\t':
            events.append(_key_input(win32con.VK_TAB))
            events.append(_key_input(win32con.VK_TAB, KEYEVENTF_KEYUP))
        else:
            code = ord(char)
            if code > 0xFFFF:
                # UTF-16 surrogate pair для символов за пределами BMP
                high = 0xD800 + ((code - 0x10000) >> 10)
                low = 0xDC00 + ((code - 0x10000) & 0x3FF)
                events.append(_unicode_input(high))
                events.append(_unicode_input(low))
                events.append(_unicode_input(low, KEYEVENTF_KEYUP))
                events.append(_unicode_input(high, KEYEVENTF_KEYUP))
            else:
                events.append(_unicode_input(code))
                events.append(_unicode_input(code, KEYEVENTF_KEYUP))

    if not events:
        log.warning("send_text_unicode: no events to send")
        return True

    # Отправляем батчами (макс 500 событий = ~250 символов за вызов)
    BATCH = 500
    total_sent = 0
    for i in range(0, len(events), BATCH):
        batch = events[i:i + BATCH]
        n = len(batch)
        arr = (_INPUT * n)(*batch)
        sent = _user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(_INPUT))
        if sent != n:
            err = ctypes.get_last_error()
            log.error("SendInput unicode: expected %d, sent %d, err=%d", n, sent, err)
            return False
        total_sent += sent

    log.info("SendInput unicode: %d events sent OK (%d chars)", total_sent, len(text))
    return True


def clipboard_get():
    """Получить текст из буфера обмена."""
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            return None
        finally:
            win32clipboard.CloseClipboard()
    except Exception as e:
        log.warning("clipboard_get failed: %s", e)
        return None


def clipboard_set(text, retries=5):
    """Установить текст в буфер обмена с ретраями при блокировке."""
    for attempt in range(retries):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                return True
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            log.warning("clipboard_set attempt %d/%d failed: %s", attempt + 1, retries, e)
            time.sleep(0.05)
    return False


def clipboard_set_verified(text, retries=5):
    """Установить текст в clipboard и верифицировать чтением обратно."""
    for attempt in range(retries):
        if not clipboard_set(text, retries=1):
            time.sleep(0.05)
            continue
        # Верификация: прочитать обратно и сравнить
        time.sleep(0.01)
        readback = clipboard_get()
        if readback == text:
            return True
        log.warning("clipboard_verify: mismatch on attempt %d/%d (got %d chars, expected %d)",
                     attempt + 1, retries,
                     len(readback) if readback else 0, len(text))
        time.sleep(0.05)
    return False


def force_foreground(hwnd):
    """Вывести окно на передний план через AttachThreadInput."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        log.warning("force_foreground: invalid hwnd=%s", hwnd)
        return False

    fg = win32gui.GetForegroundWindow()
    if fg == hwnd:
        log.debug("force_foreground: already foreground")
        return True

    try:
        fg_tid = win32process.GetWindowThreadProcessId(fg)[0]
        our_tid = win32api.GetCurrentThreadId()

        attached = False
        if fg_tid != our_tid:
            attached = bool(ctypes.windll.user32.AttachThreadInput(our_tid, fg_tid, True))

        try:
            win32gui.SetForegroundWindow(hwnd)
            log.debug("force_foreground OK hwnd=%s attached=%s", hwnd, attached)
        finally:
            if attached:
                ctypes.windll.user32.AttachThreadInput(our_tid, fg_tid, False)

        return True
    except Exception as e:
        log.error("force_foreground FAILED hwnd=%s: %s", hwnd, e)
        return False


def _log_and_release_modifiers():
    """Диагностика и сброс залипших модификаторов перед Ctrl+V.

    Безопасно сбрасываем Ctrl и Shift. Alt/Win только логируем
    (отпускание Alt активирует меню в Electron).
    """
    modifiers = [
        (win32con.VK_CONTROL, "Ctrl", True),    # safe to release
        (win32con.VK_SHIFT, "Shift", True),      # safe to release
        (win32con.VK_MENU, "Alt", False),         # dangerous: activates menu
        (win32con.VK_LWIN, "LWin", False),        # dangerous: opens Start
        (win32con.VK_RWIN, "RWin", False),
    ]
    stuck = []
    for vk, name, safe in modifiers:
        if win32api.GetAsyncKeyState(vk) & 0x8000:
            stuck.append(name)
            if safe:
                inputs = (_INPUT * 1)(_key_input(vk, KEYEVENTF_KEYUP))
                _user32.SendInput(1, ctypes.byref(inputs), ctypes.sizeof(_INPUT))

    if stuck:
        log.warning("modifier_state before Ctrl+V: stuck=%s", stuck)
        time.sleep(0.03)
    else:
        log.debug("modifier_state before Ctrl+V: all clear")

    return stuck


def _log_focus_info():
    """Диагностика: какое окно/контрол реально имеет фокус ввода."""
    try:
        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', ctypes.c_ulong),
                ('flags', ctypes.c_ulong),
                ('hwndActive', ctypes.wintypes.HWND),
                ('hwndFocus', ctypes.wintypes.HWND),
                ('hwndCapture', ctypes.wintypes.HWND),
                ('hwndMenuOwner', ctypes.wintypes.HWND),
                ('hwndMoveSize', ctypes.wintypes.HWND),
                ('hwndCaret', ctypes.wintypes.HWND),
                ('rcCaret', ctypes.wintypes.RECT),
            ]

        gti = GUITHREADINFO()
        gti.cbSize = ctypes.sizeof(GUITHREADINFO)
        if _user32.GetGUIThreadInfo(0, ctypes.byref(gti)):
            focus_cls = ""
            try:
                if gti.hwndFocus:
                    focus_cls = win32gui.GetClassName(gti.hwndFocus)
            except Exception:
                pass
            log.info("focus_info: active=%s focus=%s focus_class='%s'",
                     gti.hwndActive, gti.hwndFocus, focus_cls)
        else:
            log.warning("focus_info: GetGUIThreadInfo failed")
    except Exception as e:
        log.warning("focus_info error: %s", e)


def send_ctrl_v():
    """Отправить Ctrl+V через SendInput с правильными scan codes."""
    # Диагностика фокуса
    _log_focus_info()

    # Сброс залипших модификаторов (Ctrl, Shift — безопасно)
    _log_and_release_modifiers()

    # Ctrl↓ → V↓ → V↑ → Ctrl↑ — одним вызовом SendInput (атомарно)
    inputs = (_INPUT * 4)(
        _key_input(win32con.VK_CONTROL),
        _key_input(ord('V')),
        _key_input(ord('V'), KEYEVENTF_KEYUP),
        _key_input(win32con.VK_CONTROL, KEYEVENTF_KEYUP),
    )
    sent = _user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(_INPUT))
    if sent != 4:
        log.error("SendInput Ctrl+V: expected 4, sent %d, err=%d", sent, ctypes.get_last_error())
    else:
        log.debug("SendInput Ctrl+V: 4 events sent OK")


def send_ctrl_shift_v():
    """Отправить Ctrl+Shift+V для терминалов (Windows Terminal, ConEmu и др.)."""
    _log_focus_info()
    _log_and_release_modifiers()

    # Ctrl↓ → Shift↓ → V↓ → V↑ → Shift↑ → Ctrl↑
    inputs = (_INPUT * 6)(
        _key_input(win32con.VK_CONTROL),
        _key_input(win32con.VK_SHIFT),
        _key_input(ord('V')),
        _key_input(ord('V'), KEYEVENTF_KEYUP),
        _key_input(win32con.VK_SHIFT, KEYEVENTF_KEYUP),
        _key_input(win32con.VK_CONTROL, KEYEVENTF_KEYUP),
    )
    sent = _user32.SendInput(6, ctypes.byref(inputs), ctypes.sizeof(_INPUT))
    if sent != 6:
        log.error("SendInput Ctrl+Shift+V: expected 6, sent %d, err=%d", sent, ctypes.get_last_error())
    else:
        log.debug("SendInput Ctrl+Shift+V: 6 events sent OK")


def insert_text(text, hwnd=None):
    """Гибридная вставка текста: auto-выбор метода по длине и типу окна.

    Стратегия:
    - Electron (VS Code и др.) → ВСЕГДА unicode SendInput (Ctrl+V ненадёжен)
    - Короткий текст (<= UNICODE_THRESHOLD) → unicode SendInput
    - Длинный текст → clipboard paste (Ctrl+V / Ctrl+Shift+V)
    - Терминалы → Ctrl+Shift+V
    - Unicode failure → fallback на clipboard
    """
    fg = win32gui.GetForegroundWindow()
    window_type = detect_window_type(fg)

    # Electron-окна: SendInput Ctrl+V ненадёжен в Chromium,
    # используем посимвольный unicode ввод (KEYEVENTF_UNICODE)
    use_unicode = (window_type == 'electron') or (len(text) <= UNICODE_THRESHOLD)

    if use_unicode:
        method = 'unicode'
        log.info("insert_method_chosen: unicode (text_len=%d, window=%s)",
                 len(text), window_type)
        if send_text_unicode(text):
            log.info("insert_done: success, method=unicode, window=%s", window_type)
            return True
        log.warning("insert: unicode failed, falling back to clipboard")
        method = 'clipboard_fallback'
    else:
        method = 'clipboard'
        log.info("insert_method_chosen: clipboard (text_len=%d > %d, window=%s)",
                 len(text), UNICODE_THRESHOLD, window_type)

    # Clipboard paste (fallback для electron, основной для normal/terminal)
    old_clipboard = clipboard_get()
    if not clipboard_set_verified(text):
        raise RuntimeError("clipboard_set_verified failed after retries")

    log.debug("clipboard_set OK: %d chars", len(text))

    time.sleep(0.1)  # 100ms задержка перед paste

    # Финальная проверка clipboard перед Ctrl+V
    pre_paste_clip = clipboard_get()
    if pre_paste_clip != text:
        log.error("clipboard_tampered! expected %d chars, got %d",
                  len(text), len(pre_paste_clip) if pre_paste_clip else 0)
        if not clipboard_set_verified(text):
            raise RuntimeError("clipboard_set_verified retry failed")
        time.sleep(0.05)

    if window_type == 'terminal':
        send_ctrl_shift_v()
    else:
        send_ctrl_v()

    time.sleep(0.3)

    log.info("insert_done: success, method=%s, window=%s", method, window_type)

    # Восстановить clipboard пользователя (с большой задержкой для надёжности)
    if old_clipboard is not None:
        _restore_clipboard_delayed(old_clipboard)

    return True


def _restore_clipboard_delayed(old_clipboard):
    """Восстановить clipboard через 2с в фоновом потоке.

    Задержка должна быть достаточной, чтобы даже медленные приложения (Electron)
    успели обработать Ctrl+V и прочитать clipboard. 500мс — недостаточно для VS Code.
    """
    def _restore():
        try:
            clipboard_set(old_clipboard)
            log.debug("clipboard restored (delayed)")
        except Exception as e:
            log.warning("clipboard restore failed: %s", e)
    threading.Timer(2.0, _restore).start()


# Символы, перед которыми не нужен пробел (пунктуация в начале текста)
_PUNCTUATION_START = set('.,;:!?)}]>»"\'')


class TextInserter:
    """Захват целевого окна и вставка текста (гибридная стратегия)."""

    # Окно времени (с), в течение которого считаем, что пользователь продолжает диктовку
    _SMART_SPACING_WINDOW = 60.0

    def __init__(self, event_bus, config):
        self._bus = event_bus
        self._config = config
        self._target_window = None
        self._last_insert_time = 0.0

        self._bus.recording_start.connect(self._capture_window)
        self._bus.text_processed.connect(self._on_text_ready)

    def _capture_window(self, hwnd):
        """Запомнить активное окно (захвачено в keyboard hook thread)."""
        self._target_window = hwnd
        try:
            title = win32gui.GetWindowText(hwnd) if hwnd else "<None>"
            cls = win32gui.GetClassName(hwnd) if hwnd else "<None>"
        except Exception:
            title, cls = "<error>", "<error>"
        log.info("capture_window: hwnd=%s title='%s' class='%s'", hwnd, title, cls)

    def _on_text_ready(self, text: str):
        """Вставить текст в целевое окно (запуск в фоновом потоке)."""
        log.info("insert_start: text_len=%d target_hwnd=%s method=auto",
                 len(text), self._target_window)
        hwnd = self._target_window
        try:
            t = threading.Thread(target=self._do_insert, args=(text, hwnd), daemon=True)
            t.start()
        except Exception as e:
            log.exception("insert_thread_start FAILED: %s", e)
            self._bus.error_occurred.emit("TextInserter", str(e))

    def _do_insert(self, text, hwnd):
        """Фоновый поток: фокус окна + гибридная вставка."""
        try:
            # Диагностика: проверяем, что целевое окно ещё существует
            if hwnd:
                try:
                    is_valid = win32gui.IsWindow(hwnd)
                    title = win32gui.GetWindowText(hwnd) if is_valid else "<destroyed>"
                    log.info("insert_target: valid=%s title='%s'", is_valid, title)
                except Exception as e:
                    log.warning("insert_target: check failed: %s", e)

            # Шаг 1: Активируем целевое окно
            if hwnd:
                force_foreground(hwnd)
                time.sleep(0.05)
            else:
                log.warning("insert: no target window, using current foreground")

            fg = win32gui.GetForegroundWindow()
            fg_title = win32gui.GetWindowText(fg) if fg else "<None>"
            log.debug("insert: foreground=%s title='%s'", fg, fg_title)

            # Шаг 2: Smart spacing — пробел если продолжаем диктовку
            now = time.monotonic()
            if text and text[0] not in _PUNCTUATION_START:
                elapsed = now - self._last_insert_time
                if self._last_insert_time > 0 and elapsed < self._SMART_SPACING_WINDOW:
                    text = " " + text
                    log.info("smart_spacing: prepended space (last insert %.1fs ago)", elapsed)

            # Шаг 3: Гибридная вставка
            insert_text(text, hwnd)
            self._last_insert_time = time.monotonic()

            self._bus.text_inserted.emit()

        except Exception as e:
            log.exception("insert_error: %s", e)
            self._bus.error_occurred.emit("TextInserter", str(e))
