# CLAUDE.md — Voice Dictation

## О проекте
Voice Dictation — утилита для голосового ввода текста в Windows. Push-to-talk, локальное распознавание через faster-whisper на NVIDIA GPU. Правильная пунктуация и терминология, доменные словари, preview перед вставкой, история диктовок.

## Стек и архитектура
См. docs/ARCHITECTURE.md — стек, структура, деплой, принятые решения.

## Контекст команды
Обязательно при старте: `.context/WORKFLOW.md` — роли, ответственность, правила
Справочно: `.context/TEAM_SKILLS.md`, `.context/PHILOSOPHY.md`

## Команды
```bash
# Запуск
Dictation.vbs          # Без консоли (production)
Dictation.bat          # С консолью (отладка)
dictation.pyw          # Напрямую через Python

# Зависимости
install_local.bat
.\python311\python.exe -m pip install PyQt6 pywin32 faster-whisper sounddevice numpy keyboard pyperclip pyautogui

# Сборка
build.bat              # PyInstaller
```

## Правила работы
- Выполняй задачи из pm/TASKS.md последовательно по приоритету
- После каждой задачи: обнови pm/TASKS.md, pm/CHANGELOG.md, pm/STATUS.md
- Помечай все выполненные задачи и изменения своим @Именем из секции «Идентификация» глобальной инструкции
- Если задача понятна — делай без вопросов
- Стоп-условия: см. .context/WORKFLOW.md
- Не принимай стратегических решений самостоятельно
- Коммиты: осмысленные сообщения на русском

## Структура проекта
```
CLAUDE.md          — этот файл
.context/          — WORKFLOW.md, TEAM_SKILLS.md, PHILOSOPHY.md
.handoff/          — передача задач APP → Code (не в Git)
pm/                — STATUS.md, TASKS.md, ROADMAP.md, CHANGELOG.md, BACKLOG.md
docs/              — ARCHITECTURE.md
core/              — бизнес-логика (recognizer, config, audio, events, history, output)
ui/                — GUI (widget, tray, settings, preview, history, model dialog)
tests/             — тесты
.planning/         — [АРХИВ] старая система управления, только для чтения
```

## Актуальный статус
См. pm/STATUS.md и pm/TASKS.md
