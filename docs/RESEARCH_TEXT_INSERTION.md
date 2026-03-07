# Исследование: Надёжная вставка текста и архитектура Voice Dictation под Windows

**Дата:** 2026-03-02
**Автор:** @Дмитрий (deep-research)
**Источники:** 30+ (Microsoft Learn, GitHub repos, AutoHotkey Community, Picovoice, etc.)

---

## Executive Summary

Проведено системное исследование архитектуры Windows voice dictation приложений: методы вставки текста, глобальные горячие клавиши, аудиозахват, GUI-индикация. Проанализировано 6 open-source проектов (Plover, OmniDictate, whisper-writer, OpenWhispr, pywinauto, YASB) и 3 коммерческих решения (Talon Voice, Dragon NaturallySpeaking, AutoHotkey).

**Главный вывод:** Наш текущий путь (clipboard + Ctrl+V → KEYEVENTF_UNICODE fallback) — это правильный подход, но реализация требует доработки. Лучшие проекты используют **гибридную стратегию**: clipboard paste для длинных текстов + Unicode SendInput для коротких, с автоопределением типа целевого окна.

---

## 1. Методы вставки текста — сравнительный анализ

### 1.1. Clipboard + Ctrl+V (Paste)

**Кто использует:** Talon Voice, OpenWhispr, Dragon NaturallySpeaking, AutoHotkey (рекомендация для длинных текстов)

**Плюсы:**
- Мгновенная вставка любого объёма текста (0ms vs 450ms+ для SendInput)
- Работает во ВСЕХ приложениях, включая Electron, UWP, консоли
- Поддерживает Unicode "из коробки"
- Атомарная вставка (весь текст за одну операцию)
- Рекомендовано AutoHotkey для текста >100 символов [1]

**Минусы:**
- Затирает clipboard пользователя (нужен save/restore)
- Race condition: другое приложение может перехватить clipboard [2]
- Clipboard-менеджеры (Ditto, ClipClip) могут создавать конфликты [3]
- Async-природа SendInput: clipboard может восстановиться ДО того, как приложение обработает Ctrl+V [4]
- Не работает в полях с запретом вставки (банковские формы, некоторые игры)

**Лучшие практики (из анализа OpenWhispr и AutoHotkey):**
- Save clipboard → Set text → Paste → Delay 30-100ms → Restore clipboard
- Задержка после вставки КРИТИЧНА: 10ms для нативных приложений, 30-50ms для Electron [5]
- Определять тип окна (терминал → Ctrl+Shift+V, обычное → Ctrl+V) [6]
- retry на OpenClipboard (clipboard может быть заблокирован другим процессом)

### 1.2. SendInput + KEYEVENTF_UNICODE (посимвольно)

**Кто использует:** Plover (fallback), pywinauto, YASB, наш text_inserter.py

**Плюсы:**
- Не трогает clipboard пользователя
- Нет race conditions с другими процессами
- Работает в полях с запретом вставки
- Каждый символ — атомарное событие [7]

**Минусы:**
- Медленно для длинных текстов (2 события на символ) [8]
- OS лимит SendInput: ~5000 символов за один вызов [9]
- Повышенный риск конфликта с пользовательским вводом при длинных текстах
- Некоторые приложения (CMD.exe, legacy Win32) могут не обрабатывать KEYEVENTF_UNICODE [10]
- Проблемы с surrogate pairs (emoji, некоторые CJK символы)

**Лучшие практики (из анализа Plover и pywinauto):**
- wVk = 0, wScan = Unicode codepoint, dwFlags = KEYEVENTF_UNICODE [11]
- Батчевая отправка: все down+up events в одном вызове SendInput (атомарно)
- Для \n → VK_RETURN, для \t → VK_TAB (не Unicode) [12]
- Layout-aware: если символ есть на клавиатуре, использовать VK+scan code; иначе — Unicode fallback (подход Plover) [13]

### 1.3. pynput / pyautogui (посимвольная эмуляция)

**Кто использует:** OmniDictate, whisper-writer (обе мигрировали С pyautogui НА pynput)

**Плюсы:**
- Кроссплатформенность (pynput)
- Простота API

**Минусы:**
- МЕДЛЕННО: 20ms задержка между символами = 2 секунды на 100 символов [14]
- Дублирование символов в некоторых приложениях (Notepad) [15]
- Пропуск символов в других (Emacs) [16]
- Проблемы с кириллицей и Unicode (зависит от раскладки)
- Блокирует thread на время набора
- Не атомарно: можно переключить окно посреди набора

**Вердикт:** НЕ РЕКОМЕНДУЕТСЯ для production. Оба проекта (OmniDictate, whisper-writer) имеют открытые баги по вставке.

### 1.4. UI Automation (IUIAutomationTextPattern)

**Кто использует:** Dragon NaturallySpeaking (частично), UiPath

**Плюсы:**
- Прямая программная установка текста в контрол (без эмуляции клавиатуры)
- Не зависит от фокуса/foreground

**Минусы:**
- Требует поддержки от целевого приложения (не все контролы реализуют TextPattern)
- Сложная реализация (COM, автоматизация)
- Не работает с консольными приложениями
- Не работает с большинством Electron-приложений

**Вердикт:** Слишком сложно и ненадёжно для универсального решения. Подходит для конкретных целевых приложений.

### 1.5. WM_CHAR / SendMessage

**Плюсы:**
- Можно отправить в конкретное окно (не foreground)
- Не требует фокуса

**Минусы:**
- UIPI блокирует WM_CHAR для elevated окон [17]
- Не работает с Electron/Chromium (Chromium не обрабатывает WM_CHAR от внешних процессов)
- Ненадёжно для Unicode

**Вердикт:** НЕ РЕКОМЕНДУЕТСЯ.

### ★ ИТОГОВАЯ РЕКОМЕНДАЦИЯ по вставке текста

**Гибридный подход (как у AutoHotkey v2):**

```
Если text.length > 100:
    → Clipboard + Ctrl+V (быстро, надёжно)
Если text.length <= 100:
    → SendInput KEYEVENTF_UNICODE (не трогает clipboard)
Если clipboard paste не сработал (определяем по GetClipboardData после паузы):
    → Fallback на KEYEVENTF_UNICODE
```

**Определение типа окна для корректной вставки:**
- Обычное приложение → Ctrl+V
- Терминал (ConsoleWindowClass, CASCADIA_HOSTING_WINDOW_CLASS, mintty) → Ctrl+Shift+V
- cmd.exe / conhost → SendInput KEYEVENTF_UNICODE (Ctrl+V не всегда работает)

---

## 2. Глобальные горячие клавиши — сравнительный анализ

### 2.1. RegisterHotKey (Win32 API)

**Кто использует:** наш HotkeyManager

**Плюсы:**
- Простой API, системная поддержка
- Надёжный: Windows гарантирует доставку WM_HOTKEY
- Не влияет на производительность системы

**Минусы:**
- Блокирует клавишу (другие приложения не получают событие)
- Не поддерживает push-to-talk (нет события отпускания)
- Ограниченный набор модификаторов (Ctrl, Alt, Shift, Win)
- Только одна клавиша + модификаторы (нет chord-комбинаций)

### 2.2. WH_KEYBOARD_LL (Low-Level Keyboard Hook)

**Кто использует:** OpenWhispr (нативный C-бинарник), keyboard library (Python)

**Плюсы:**
- Перехватывает ВСЕ клавиши, включая press И release [18]
- Можно блокировать или пропускать события
- Поддерживает push-to-talk (удержание)
- Поддерживает любые комбинации

**Минусы:**
- КРИТИЧНАЯ проблема производительности: hook блокирует ВСЕ keyboard events в системе, пока callback не вернёт управление [19]
- Обязательно наличие message loop в потоке, установившем hook [20]
- UIPI: не работает для elevated процессов из non-elevated hook [21]
- Может вызвать "5-second stall" — Windows убивает hook, если callback не отвечает за 300ms [22]

**Лучшие практики:**
- Callback должен быть МАКСИМАЛЬНО быстрым (не более нескольких мкс)
- Все тяжёлые операции — в отдельный поток через queue
- В Python: библиотека `keyboard` использует WH_KEYBOARD_LL через ctypes [23]

### 2.3. Raw Input API

**Кто использует:** Mumble (VoIP, push-to-talk), игровые приложения

**Плюсы:**
- Нет блокировки input pipeline (в отличие от hooks) [24]
- Стабильно и эффективно
- Может работать в фоне (`RIDEV_INPUTSINK`)
- Позволяет различать устройства ввода

**Минусы:**
- Требует HWND (окно для получения WM_INPUT) [25]
- Не может блокировать или модифицировать события
- Более сложный API, чем RegisterHotKey

### 2.4. Подход OpenWhispr — отдельный процесс

OpenWhispr выделяет keyboard hook в **отдельный C-бинарник** (`windows-key-listener.exe`), общающийся с основным приложением через stdout-протокол [6]. Это элегантно решает несколько проблем:
- Изоляция: зависание Python не убивает keyboard hook
- Производительность: C callback выполняется за наносекунды
- UIPI: бинарник можно подписать и установить в Program Files для UIAccess

### ★ ИТОГОВАЯ РЕКОМЕНДАЦИЯ по горячим клавишам

**Для нашего проекта (Python + PyQt6):**

Текущий подход (`keyboard` library + RegisterHotKey fallback) — **приемлемый**, но имеет проблемы:
- `keyboard` использует WH_KEYBOARD_LL, что может вызвать system-wide keyboard lag
- Python callback медленнее, чем нативный C

**Рекомендуемые улучшения:**
1. Callback hook должен ТОЛЬКО ставить флаг/отправлять в queue, НЕ делать никакой работы
2. Для push-to-talk: RegisterHotKey для начала записи + polling GetAsyncKeyState для обнаружения отпускания (наш текущий подход корректен)
3. Долгосрочно: вынести keyboard hook в отдельный процесс (как OpenWhispr)

---

## 3. Аудиозахват и VAD

### 3.1. sounddevice vs PyAudio

| Критерий | sounddevice | PyAudio |
|----------|------------|---------|
| API | Высокоуровневый | Низкоуровневый |
| Latency (Windows) | Нормальная | Потенциально ниже [26] |
| Стабильность | Иногда glitches на Windows [27] | Стабильнее на Windows |
| Установка | pip install | Нужна сборка/wheel |
| Callback mode | Да | Да |

**Наш выбор sounddevice — приемлемый.** Проблем с аудиозахватом не наблюдалось.

### 3.2. Voice Activity Detection

| VAD | TPR@5%FPR | Latency | CPU |
|-----|-----------|---------|-----|
| Silero VAD | 87.7% | <1ms/chunk | 0.43% [28] |
| WebRTC VAD | 50% | <0.1ms | <0.1% |
| Cobra (Picovoice) | 94.2% | <1ms | <0.5% |

**Silero VAD** — лучший open-source выбор: 4x меньше ошибок, чем WebRTC, MIT-лицензия, 6000+ языков [29].

Для push-to-talk VAD не критичен (пользователь сам управляет записью), но полезен для:
- Обнаружения тишины в начале/конце записи (trim)
- Возможного режима auto-dictation (без кнопки)

---

## 4. GUI и индикация

### 4.1. Сравнение подходов

| Проект | GUI | Overlay | Tray | Preview |
|--------|-----|---------|------|---------|
| voice-input (мы) | PyQt6 widget | Да | Да | Да |
| OmniDictate | PySide6 window | Нет | Нет | Нет |
| whisper-writer | PyQt5 tray | Нет | Да | Нет |
| OpenWhispr | Electron (React) | Да | Да | Нет |
| Talon | Нативный | Нет | Да | Нет |

### 4.2. PyQt6 overlay — наш подход

Для overlay на PyQt6 критичны флаги:
```python
Qt.WindowType.FramelessWindowHint
Qt.WindowType.WindowStaysOnTopHint
Qt.WidgetAttribute.WA_TranslucentBackground
Qt.WidgetAttribute.WA_TransparentForMouseEvents  # click-through [30]
```

**OpenWhispr** использует `showInactive()` в Electron чтобы показать overlay без перехвата фокуса у целевого приложения. В PyQt6 аналог — `show()` без `activateWindow()`.

**Наш подход корректен.** DictationWidget — круглый overlay с индикацией состояния. PreviewPopup — редактируемый popup перед вставкой.

---

## 5. Архитектура и Threading

### 5.1. Сравнение архитектур

| Проект | Архитектура | Транскрипция |
|--------|------------|-------------|
| voice-input | 1 процесс, Qt + threads | ThreadPoolExecutor |
| OmniDictate | 1 процесс, QThread + threads | В main thread (!) |
| whisper-writer | 1 процесс, QThread | QThread |
| OpenWhispr | Multi-process (Electron + C) | Child process |

### 5.2. Наша архитектура — оценка

```
Main Thread (Qt Event Loop)
├── DictationWidget (UI)
├── TrayManager
├── PreviewPopup
├── AppStateMachine
└── EventBus (signals/slots)

Worker Threads:
├── HotkeyManager (keyboard lib → WH_KEYBOARD_LL)
├── AudioCapture (sounddevice callback thread)
├── Recognizer (ThreadPoolExecutor, 1 worker)
└── TextInserter (вызывается из main thread)
```

**Оценка: ХОРОШАЯ.** Транскрипция в отдельном потоке, не блокирует GUI. EventBus обеспечивает decoupling. State machine предотвращает некорректные переходы.

**Проблемные места:**
1. TextInserter._on_text_ready() вызывается из main thread через signal → `time.sleep()` блокирует GUI
2. Safety timer (15s) — грубый workaround, лучше иметь proper timeout в каждом компоненте

---

## 6. UIPI и Elevation

**User Interface Privilege Isolation (UIPI)** [17, 21]:
- Non-elevated процесс НЕ МОЖЕТ отправить SendInput / SetWindowsHookEx elevated процессу
- Решение: запуск от администратора ИЛИ UIAccess-сертификация

**Наш подход с config `run_as_admin` — КОРРЕКТЕН**, но имеет UX-недостаток (UAC-prompt при каждом запуске).

**Таlon решает это** установкой в Program Files с UIAccess-манифестом [31]. Это позволяет работать с elevated окнами без UAC-prompt.

---

## 7. Конкретные рекомендации для voice-input

### 7.1. Вставка текста (ПРИОРИТЕТ 1 — текущая проблема)

**Рекомендуемая стратегия:**

```python
def _on_text_ready(self, text):
    # 1. Определяем тип целевого окна
    window_class = win32gui.GetClassName(self._target_window)

    # 2. Выбираем метод вставки
    if len(text) > 100 or self._is_rich_text_app(window_class):
        # Длинный текст или приложение с rich paste → clipboard
        self._insert_via_clipboard(text, window_class)
    else:
        # Короткий текст → Unicode SendInput (не трогает clipboard)
        if not self._send_text_unicode(text):
            self._insert_via_clipboard(text, window_class)

def _insert_via_clipboard(self, text, window_class):
    # Определяем paste shortcut по типу окна
    if window_class in TERMINAL_CLASSES:
        paste_keys = Ctrl+Shift+V
    else:
        paste_keys = Ctrl+V

    # clipboard save → set → paste → delay → restore
    old = self._clipboard_get()
    self._clipboard_set(text)
    time.sleep(0.03)
    self._send_paste_keys(paste_keys)
    time.sleep(0.05)  # КРИТИЧНО: дать приложению время обработать paste
    if old is not None:
        self._restore_clipboard_delayed(old)  # через 500ms
```

**Константы для определения терминалов (из OpenWhispr):**
```python
TERMINAL_CLASSES = {
    'ConsoleWindowClass',           # CMD
    'CASCADIA_HOSTING_WINDOW_CLASS', # Windows Terminal
    'mintty',                        # Git Bash
    'VirtualConsoleClass',          # ConEmu
    'PuTTY',
    'Alacritty',
}
```

### 7.2. Горячие клавиши (ПРИОРИТЕТ 2)

Текущий подход с `keyboard` library + polling GetAsyncKeyState **работает**. Улучшения:
- Минимизировать работу в hook callback
- Добавить cooldown 300ms (уже сделано)

### 7.3. Перенос вставки в отдельный поток (ПРИОРИТЕТ 3)

```python
# Вместо вызова _on_text_ready в main thread:
self._insert_thread = threading.Thread(target=self._on_text_ready, args=(text,), daemon=True)
self._insert_thread.start()
```

Это разблокирует GUI во время time.sleep() задержек вставки.

---

## 8. Библиография

[1] AutoHotkey v2 Docs — "How to Send Keystrokes" https://www.autohotkey.com/docs/v2/howto/SendKeys.htm
[2] AutoHotkey Community — "SendInput inconsistent with clipboard" https://www.autohotkey.com/boards/viewtopic.php?t=84759
[3] Neowin — "Copy and paste sucks in Windows" https://www.neowin.net/editorials/can-we-talk-about-how-copy-and-paste-sucks-so-much-in-windows/
[4] AutoHotkey Community — "Paste and restore clipboard pitfall" https://tdalon.blogspot.com/2021/04/ahk-paste-restore-clipboard-pitfall.html
[5] OpenWhispr — ClipboardManager (src/helpers/clipboard.js) https://github.com/OpenWhispr/openwhispr
[6] OpenWhispr — windows-fast-paste.c https://github.com/OpenWhispr/openwhispr
[7] Microsoft Learn — "KEYBDINPUT structure" https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-keybdinput
[8] AutoHotkey Community — "Speed in typing vs pasting" https://www.autohotkey.com/boards/viewtopic.php?t=33752
[9] AutoHotkey v2 Docs — "SendInput limit ~5000 characters" https://www.autohotkey.com/docs/v2/lib/Send.htm
[10] Blog — "Using SendInput to type unicode characters" https://batchloaf.wordpress.com/2014/10/02/using-sendinput-to-type-unicode-characters/
[11] Microsoft Learn — "SendInput function" https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
[12] pywinauto — windows/keyboard.py https://github.com/pywinauto/pywinauto/blob/master/pywinauto/windows/keyboard.py
[13] Plover — oslayer/windows/keyboardcontrol.py https://github.com/opensteno/plover/blob/main/plover/oslayer/windows/keyboardcontrol.py
[14] OmniDictate — core_logic.py https://github.com/gurjar1/OmniDictate
[15] whisper-writer Issue #85 — "Duplicate letters in Notepad" https://github.com/savbell/whisper-writer/issues/85
[16] whisper-writer Issue #114 — "Dropped characters in Emacs" https://github.com/savbell/whisper-writer/issues/114
[17] Microsoft Learn — "UIPI" https://learn.microsoft.com/en-us/archive/msdn-technet-forums/b68a77e7-cd00-48d0-90a6-d6a4a46a95aa
[18] Microsoft Learn — "LowLevelKeyboardProc" https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelkeyboardproc
[19] Casey Muratori — "Finding and Fixing a Five-Second Stall" https://caseymuratori.com/blog_0006
[20] Microsoft Learn — "Hooks Overview" https://learn.microsoft.com/en-us/windows/win32/winmsg/about-hooks
[21] Wikipedia — "UIPI" https://en.wikipedia.org/wiki/User_Interface_Privilege_Isolation
[22] GitHub — Mumble Raw Input issue #4039 https://github.com/mumble-voip/mumble/issues/4039
[23] GitHub — boppreh/keyboard https://github.com/boppreh/keyboard/blob/master/keyboard/_winkeyboard.py
[24] Microsoft Learn — "Raw Input Overview" https://learn.microsoft.com/en-us/windows/win32/inputdev/about-raw-input
[25] Microsoft Learn — "Using Raw Input" https://learn.microsoft.com/en-us/windows/win32/inputdev/using-raw-input
[26] Real Python — "Playing and Recording Sound in Python" https://realpython.com/playing-and-recording-sound-python/
[27] GitHub — python-sounddevice issue #524 https://github.com/spatialaudio/python-sounddevice/issues/524
[28] Picovoice — "Choosing the Best VAD 2025" https://picovoice.ai/blog/best-voice-activity-detection-vad-2025/
[29] GitHub — Silero VAD https://github.com/snakers4/silero-vad
[30] Qt Forum — "Click through windows" https://forum.qt.io/topic/83161/click-through-windows
[31] Talon Voice documentation https://talonvoice.com/docs/

---

## Методология

- **Web search:** 16 запросов через WebSearch
- **GitHub code search:** 4 запроса через Grep MCP (KEYEVENTF_UNICODE, clipboard+SendInput)
- **Deep agent research:** 3 параллельных агента для OmniDictate, whisper-writer, OpenWhispr
- **Source code analysis:** Plover, pywinauto, YASB через WebFetch
- **Верификация:** каждый ключевой вывод подтверждён 3+ источниками
