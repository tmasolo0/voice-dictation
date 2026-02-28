# Voice Dictation — Руководство по разработке

## Структура проекта

```
dictation.pyw              — точка входа (setup logging + QApplication)
app.py                     — Application: координатор компонентов
VERSION                    — файл версии (SemVer)

core/
  config_manager.py        — ConfigManager singleton, config.json
  event_bus.py             — EventBus (PyQt6 signals)
  app_state.py             — AppState enum + AppStateMachine
  audio_capture.py         — Захват аудио (sounddevice)
  model_manager.py         — Загрузка/управление моделью Whisper
  model_catalog.py         — Каталог доступных моделей
  recognizer.py            — Транскрипция через faster-whisper
  output_pipeline.py       — Пост-обработка текста
  text_inserter.py         — Вставка текста в целевое окно (Ctrl+V)
  hotkeys.py               — Глобальные горячие клавиши (keyboard hook)
  history_manager.py       — Менеджер истории диктовок (SQLite)

ui/
  widget.py                — DictationWidget (PyQt6 виджет-индикатор)
  tray.py                  — TrayManager (системный трей + контекстное меню)
  settings_dialog.py       — Диалог настроек
  model_dialog.py          — Менеджер моделей (скачивание/удаление)
  history_dialog.py        — Диалог истории
  preview_popup.py         — Preview popup перед вставкой

build/
  generate_icon.py         — Генерация иконки приложения
VoiceDictation.spec        — PyInstaller spec файл
installer.iss              — Inno Setup installer скрипт
build.bat                  — Полный пайплайн сборки
```

## Версионирование

- **Формат**: [SemVer](https://semver.org/) — `MAJOR.MINOR.PATCH`
- **Источник правды**: файл `VERSION` в корне проекта
- **Синхронизация**:
  - `app.py` — читает `VERSION` автоматически (`get_version()`)
  - `installer.iss` — `#define MyAppVersion` обновлять вручную (или автоматизировать в `build.bat`)
  - `build.bat` — читает `VERSION` через `set /p VERSION=<VERSION`

## Процесс разработки

### Dev-режим

```bash
python311\python.exe dictation.pyw
```

Уровень логирования: `DEBUG` (в файл `logs/dictation.log`).

### Тестирование

```bash
python311\python.exe -m pytest tests/
```

### Рабочий цикл

1. Внести изменения
2. Проверить в dev-режиме (`python311\python.exe dictation.pyw`)
3. Собрать exe (`build.bat`)
4. Проверить exe
5. Коммит

## Сборка

### Требования

- **Python 3.11** — встроенный (`python311/`)
- **PyInstaller** — устанавливается автоматически через `build.bat`
- **Inno Setup 6** — для создания инсталлера ([скачать](https://jrsoftware.org/isinfo.php))

### Запуск сборки

```bash
build.bat              # Только exe (быстро)
build.bat installer    # Exe + инсталлер (долго, ~15 мин)
```

### Результат

- **EXE**: `dist\VoiceDictation\VoiceDictation.exe`
- **Инсталлер**: `installer_output\VoiceDictation_Setup_X.Y.Z.exe`

## Релиз

1. Обновить `VERSION` (и `#define MyAppVersion` в `installer.iss`)
2. Запустить `build.bat installer`
3. Пройти чеклист тестирования (ниже)
4. Коммит и тег:
   ```bash
   git add -A
   git commit -m "release: vX.Y.Z"
   git tag vX.Y.Z
   ```

## Чеклист тестирования перед релизом

- [ ] Dev-режим запускается без ошибок
- [ ] `build.bat` завершается без ошибок
- [ ] EXE запускается без консоли
- [ ] F9: запись + распознавание + вставка текста
- [ ] Настройки открываются и сохраняются
- [ ] Скачивание модели работает (менеджер моделей)
- [ ] Инсталлер устанавливает приложение в выбранную папку
- [ ] Приложение запускается после установки
- [ ] Деинсталляция удаляет приложение корректно
