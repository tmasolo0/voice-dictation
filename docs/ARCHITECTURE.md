# ARCHITECTURE.md — Voice Dictation

> Заполняется Claude APP при старте проекта. Обновляется при архитектурных изменениях.
> Claude Code следует решениям из этого файла, не принимает архитектурных решений самостоятельно.

---

## Обзор
Voice Dictation — утилита для голосового ввода текста в Windows. Push-to-talk локальное распознавание через faster-whisper на NVIDIA GPU. Только Windows.

## Стек
- **Python 3.11** (встроенный `python311/`)
- **PyQt6** — GUI (виджет, диалоги, трей)
- **faster-whisper** — STT (CTranslate2 backend, CUDA)
- **sounddevice** — захват аудио
- **keyboard** — глобальные горячие клавиши
- **pyperclip + pyautogui** — вставка текста
- **SQLite** (WAL mode) — история диктовок

## AI/LLM
- **Whisper large-v3-turbo** — основная модель распознавания (локально, GPU)
- Каталог моделей: tiny → large-v3 (выбор пользователя)
- Доменные словари (IT, математика, инженерия) для hotwords

## Структура
```
app.py                 — Application coordinator
dictation.pyw          — точка входа (PyQt6 QApplication)
core/
  event_bus.py         — EventBus (PyQt signals)
  app_state.py         — AppStateMachine (INIT→READY→RECORDING→PROCESSING→READY)
  config_manager.py    — ConfigManager singleton (config.json v7)
  audio_capture.py     — AudioCapture (sounddevice, threading.Event)
  model_manager.py     — ModelManager (load-at-startup, VRAM measurement)
  recognizer.py        — Recognizer (ThreadPoolExecutor, busy guard)
  history_manager.py   — HistoryManager (SQLite, EventBus auto-save)
  output_pipeline.py   — OutputPipeline (Punctuation + Capitalization + TrailingDot)
  text_inserter.py     — TextInserter (clipboard save/restore)
  hotkeys.py           — HotkeyManager (F9 push-to-talk, F10 translate, Ctrl+H history)
  model_catalog.py     — MODEL_CATALOG, MODEL_LABELS, is_model_downloaded()
ui/
  widget.py            — DictationWidget (pulsating circle + model label + VRAM)
  preview_popup.py     — PreviewPopup (Tool window, WA_ShowWithoutActivating, timer, re-dictate)
  settings_dialog.py   — SettingsDialog (5-tab QDialog) + HotkeyEdit
  history_dialog.py    — HistoryDialog (search, copy, insert, clear)
  tray.py              — TrayManager (system tray + context menu)
  model_dialog.py      — ModelManagerDialog
```

## Деплой
- PyInstaller (`VoiceDictation.spec`, `build.bat`)
- Inno Setup (`installer.iss`) → инсталлятор
- VBS launcher (`Dictation.vbs`) — запуск без консоли
- Встроенный Python 3.11 в `python311/`

## Принятые решения
Полный список решений — в `.planning/STATE.md` секция "Accumulated Context → Decisions" (сохранён как архив).
Ключевые:
- CTranslate2 не поддерживает runtime model swap → поля model/device/compute_type помечены "requires restart"
- Preview popup: Tool + WA_ShowWithoutActivating (не крадёт фокус)
- Глобальные keyboard hooks (Enter/Esc suppress=True) через keyboard library
- OutputPipeline rebuilds processor list per call — hot-apply без перезапуска
- CONFIG_VERSION=7: миграция через _deep_update()
