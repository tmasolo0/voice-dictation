# TASKS.md

## Этап 3: v2 Polish (Phase 16)

### TASK-3.1: Backend — audio_gain, history TTL, cleanup
- Статус: backlog
- Файлы: core/audio_capture.py, core/history_manager.py, core/config_manager.py, core/event_bus.py
- Детали:
  - config.json: параметр `audio_gain` — AudioCapture умножает семплы на коэффициент усиления
  - История: ротация и по количеству (50), и по сроку хранения (настраиваемый, дни)
  - Удалить orphaned signals `preview_insert`/`preview_cancel` из EventBus

### TASK-3.2: UI — русские метки, модель на виджете, контролы
- Статус: backlog
- Зависит от: TASK-3.1
- Файлы: ui/settings_dialog.py, ui/widget.py
- Детали:
  - Все параметры в табе "Распознавание" — русские названия с описаниями
  - Виджет показывает "large-v3-turbo" вместо "Turbo"
  - Контролы audio_gain и retention_days в настройках

### TASK-3.3: Models tab — перенос управления моделями в настройки
- Статус: backlog
- Зависит от: TASK-3.2
- Файлы: ui/settings_dialog.py, ui/widget.py, ui/tray.py, ui/model_dialog.py
- Детали:
  - Новый таб "Модели" в SettingsDialog
  - "Управление моделями..." убрано из контекстных меню виджета и трея

---

## Завершённые этапы

### Этап 1: v1 Quality & Distribution (2026-02-13)
Phases 1-9. Детали в `.planning/milestones/v1-ROADMAP.md`

### Этап 2: v2 UX (2026-02-15)
Phases 10-15. Детали в `.planning/ROADMAP.md`
