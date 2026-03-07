# CHANGELOG.md

## 2026-03-07 — v1.0.6
- @Дмитрий — feat: LLM-постобработка через Qwen2.5-1.5B (CTranslate2)
- @Дмитрий — fix: LLM compute_type auto + CUDA DLL path, generate_batch API
- @Дмитрий — fix: LLM валидация compute_type + fallback на float32
- @Дмитрий — fix: LLM валидация через chat template, float32 дефолт
- @Дмитрий — fix: regex-процессоры работают вместе с LLM, а не вместо
- @Дмитрий — docs: полный README с описанием двух режимов, настроек, VRAM

## 2026-03-03 — v1.0.4
- @Дмитрий — fix: история диктовок не сохранялась (баг порядка сигналов: pipeline эмитил text_processed до установки _pending_metadata)
- @Дмитрий — fix: застревание _recording флага в HotkeyManager — сброс при set_enabled(True), try/except + timeout в _poll_key_up
- @Дмитрий — fix: логирование причин отказа горячей клавиши (state != READY, already recording)
- @Дмитрий — fix: error recovery — try/except в OutputPipeline и Application._on_text_processed, сброс recognizer._busy при safety timeout
- @Дмитрий — fix: защита от падения потока создания вставки (TextInserter._on_text_ready)

## 2026-03-02 — v1.0.3
- @Дмитрий — fix: вставка текста в Electron-окна (VS Code, Slack и др.) через unicode SendInput вместо ненадёжного Ctrl+V
- @Дмитрий — fix: safety timeout разделён на RECORDING (120с) и PROCESSING (30с) — длинные записи больше не прерываются
- @Дмитрий — добавлен `AudioCapture.stop_recording()` для принудительной остановки записи при timeout
- @Дмитрий — диагностика вставки: логирование фокуса (GetGUIThreadInfo), модификаторов, верификация clipboard

## 2026-03-01
- @Дмитрий — TASK-3.4: fix переключения модели через вкладку "Модели" (sync combo + hot-reload)
- @Дмитрий — подробное логирование цепочки вставки (text_inserter, output_pipeline, app)
- @Дмитрий — fix: маппинг клавиш settings_dialog ↔ hotkeys ("esc"→"escape", "page up"→"pageup" и др.)
- @Дмитрий — debug-режим логирования через config.json или debug.flag
- @Дмитрий — добавлены VK-коды для стрелок, backspace, capslock, numlock и др.
- @Дима — миграция на стандартный шаблон управления проектом (pm/, docs/, .context/)

## 2026-02-15
- v2 UX завершён: settings dialog (5 табов), preview popup, history viewer, domain dictionaries
- Phase 16 (v2 Polish) спланирован

## 2026-02-14
- Tech debt cleanup, domain dictionaries backend, history backend

## 2026-02-13
- v1 Quality & Distribution shipped (phases 1-9)
