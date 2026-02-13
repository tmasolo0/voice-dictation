# Codebase Concerns

**Analysis Date:** 2026-02-13

## Tech Debt

**Duplicate Model Loading Logic:**
- Issue: Model loading logic is duplicated between `dictation.pyw` (lines 326-363) and `core/recognizer.py` (lines 45-72). DictationWidget manages its own model lifecycle independently from SpeechRecognizer class, which exists but is never used.
- Files: `C:\Project\voice-input\dictation.pyw`, `C:\Project\voice-input\core\recognizer.py`
- Impact: Maintaining model loading in two places causes inconsistency. Unused SpeechRecognizer class represents wasted abstraction. Changes to model loading must be synchronized manually in both locations.
- Fix approach: Remove SpeechRecognizer class or refactor DictationWidget to use it. Choose one single source of truth for model management.

**Unused SpeechRecognizer Abstraction:**
- Issue: `core/recognizer.py` provides a clean SpeechRecognizer API but is never imported or used. DictationWidget directly uses faster-whisper WhisperModel instead.
- Files: `C:\Project\voice-input\core\recognizer.py` (entire file)
- Impact: Dead code adds cognitive load. API improvements in SpeechRecognizer don't benefit the main application. Maintenance burden for unused code.
- Fix approach: Either integrate SpeechRecognizer into DictationWidget._process_audio() and _load_model(), or delete the class. The recognizer.py module provides good abstractions but needs to be actually used.

**Model Memory Management Without Verification:**
- Issue: Line 343-351 in `dictation.pyw` attempts to clean CUDA cache via `torch.cuda.empty_cache()`, but torch is not a required dependency (only faster-whisper). Import happens inside try-except but may fail silently.
- Files: `C:\Project\voice-input\dictation.pyw` lines 343-351
- Impact: VRAM leaks when switching models if torch is not installed. Users with 4GB VRAM cards may experience slowdown or crashes during model switching without understanding why.
- Fix approach: Either add torch to requirements, verify it's installed at startup, or implement model unloading through faster-whisper's native mechanisms. Document the VRAM requirement.

**Configuration Desynchronization:**
- Issue: Settings Dialog (`settings_dialog.py` lines 173-187) saves hotkey/model changes to config.json but DictationWidget doesn't reload these settings without restart. New hotkey becomes effective only after app restart, not on config save.
- Files: `C:\Project\voice-input\settings_dialog.py`, `C:\Project\voice-input\dictation.pyw`
- Impact: User changes hotkey in settings, hits save, and it doesn't work until full app restart. Confusing UX. Settings changes are partially applied (size/fullscreen) and partially not (hotkey).
- Fix approach: Implement Settings → Main window communication. Emit signal when hotkey changes. Have DictationWidget re-register keyboard listener with new hotkey without restart.

## Known Bugs

**Audio Stream Lifecycle Issue:**
- Symptoms: Audio stream started in `_start_audio_stream()` (line 365-374) but cleanup only happens in `_quit()` (line 628-631). If app crashes or is force-killed, stream resources may leak.
- Files: `C:\Project\voice-input\dictation.pyw` lines 365-374, 628-631
- Trigger: App abnormal termination, or OS resource limits exhaustion after multiple runs
- Workaround: Restart application to release audio resources. Use Ctrl+C instead of force-killing.

**Fullscreen Detection False Positives:**
- Symptoms: `is_fullscreen_app_active()` (lines 68-85) may incorrectly detect fullscreen status on multi-monitor setups or with windowed games using exclusive fullscreen mode.
- Files: `C:\Project\voice-input\dictation.pyw` lines 68-85
- Trigger: Play game in "exclusive fullscreen" on secondary monitor, widget hides when it shouldn't. Or windowed game maximized on primary monitor with taskbar hidden.
- Workaround: Disable "hide_in_fullscreen" setting in config. Manually manage widget visibility.

**Clipboard Race Condition:**
- Symptoms: When pasting text rapidly (line 524), timing sleep of 0.05s may be insufficient on slow systems. Clipboard content could be overwritten before paste completes, or old clipboard content pasted.
- Files: `C:\Project\voice-input\dictation.pyw` lines 515-527 (_paste_text method)
- Trigger: Very fast consecutive voice inputs (multiple F9 presses within 200ms). Slow system with many background processes.
- Workaround: Increase sleep delays in _paste_text() manually in source code. Wait longer between dictations.

**Model Cache Path Inconsistency:**
- Symptoms: MODELS_DIR (line 46) expects models in `./models/`, but if models don't exist there, Whisper silently downloads them to system cache instead (usually ~/.cache/huggingface/). User doesn't see where models are stored.
- Files: `C:\Project\voice-input\dictation.pyw` lines 46, 354-355
- Trigger: First run without pre-downloaded models. App may hang during inference while downloading models in background.
- Workaround: Pre-download models using download_medium.py. Monitor disk space.

## Security Considerations

**No Input Validation on Config Keys:**
- Risk: ConfigManager.set() (lines 116-135 in config_manager.py) accepts arbitrary nested dictionaries without schema validation. Malformed config.json could cause crashes or unexpected behavior.
- Files: `C:\Project\voice-input\core\config_manager.py` lines 116-135
- Current mitigation: DEFAULT_CONFIG provides structure, _migrate() handles version changes
- Recommendations: Add JSON schema validation. Validate config on load (line 70-71). Reject unknown keys. Add type hints for config values.

**Global Hotkey Registration Without Permissions Check:**
- Risk: Keyboard library (keyboard.hook()) requires elevated privileges on Windows. App fails silently if run without admin privileges—user won't know why F9 doesn't work.
- Files: `C:\Project\voice-input\dictation.pyw` lines 381-388 (keyboard listener), `C:\Project\voice-input\core\hotkeys.py` lines 72-75
- Current mitigation: None. No admin check, no fallback.
- Recommendations: Check for admin privileges at startup. Display clear error if privileges insufficient. Provide instructions for running as admin. Consider using pywin32 for Windows-specific hotkey registration (which may have different privilege model).

**Credential Exposure via Logs:**
- Risk: Logging is minimal (only to errors file), but if initial_prompt contains sensitive dictionary terms, they're not masked. Future features (OpenAI, TTS visible in config) could expose credentials if logging is expanded.
- Files: `C:\Project\voice-input\dictation.pyw` lines 639-656, `C:\Project\voice-input\core\config_manager.py` lines 145-155
- Current mitigation: initial_prompt only contains user dictionary (not credentials), minimal logging
- Recommendations: Mask sensitive config values (API keys, credentials) before any logging. Add config validation to prevent storing plaintext secrets.

**No Rate Limiting on Hotkey:**
- Risk: Rapid F9 presses could spawn many transcription threads without limit. Thread pool unbounded—could cause DoS by exhausting system resources.
- Files: `C:\Project\voice-input\dictation.pyw` lines 439-460, 454-458
- Current mitigation: model_loading flag prevents recording during model switch, but doesn't prevent spawning multiple audio processing threads
- Recommendations: Implement debounce/throttle on hotkey. Add maximum concurrent transcription limit (e.g., only 1 active transcription). Reject recording if previous result still pending.

## Performance Bottlenecks

**Synchronous Audio Processing Blocks Recording:**
- Problem: Audio processing in `_process_audio()` (lines 462-513) runs in background thread but full Whisper transcription (100% CPU) may still cause laggy UI if system has few cores
- Files: `C:\Project\voice-input\dictation.pyw` lines 462-513
- Cause: While threading prevents UI freeze, transcription is CPU-intensive (especially large-v3 model). Limited CPU cores → slow responsiveness even in background thread.
- Improvement path: Use process pool instead of threads (bypass GIL). Implement timeout on transcription (max 30s). Add progress feedback during long transcription. Profile actual CPU usage.

**Model Loading Blocks UI (Even Though Async):**
- Problem: Line 243-255 (`_switch_model`) sets model_loading=True and prevents new recording, but UI continues responding only because of Qt event loop. Actual model loading in background thread can take 5-15 seconds on slow VRAM.
- Files: `C:\Project\voice-input\dictation.pyw` lines 238-255
- Cause: Large models (large-v3 = 2.4GB) need full VRAM transfer. No progress indication while loading.
- Improvement path: Show loading progress bar or percentage. Add timeout (fail gracefully if model load > 60s). Cache models more aggressively. Allow recording with old model while new model loads in background.

**Full-Screen Check Every 1.5 Seconds:**
- Problem: `_check_fullscreen_visibility()` runs on 1500ms timer (line 397), checking window geometry constantly. Inefficient for check that rarely changes.
- Files: `C:\Project\voice-input\dictation.pyw` lines 390-411
- Cause: Fixed 1.5s interval regardless of whether focus changed. Win32 calls in loop.
- Improvement path: Hook WM_ACTIVATE instead of polling. Only check on window focus change event. Reduce polling to 5s if no changes detected recently.

**Animation Timer Always Running:**
- Problem: `_start_animation()` timer (line 413-417) runs every 50ms even when recording is false and widget is minimized to tray.
- Files: `C:\Project\voice-input\dictation.pyw` lines 413-429
- Cause: Unconditional timer start in __init__, no state-based optimization
- Improvement path: Stop animation timer when app minimized/recording. Resume on restore. Reduces CPU wake-ups.

## Fragile Areas

**DictationWidget Monolithic God Object:**
- Files: `C:\Project\voice-input\dictation.pyw` (entire file, 682 lines)
- Why fragile: Single class handles UI, audio capture, model management, transcription, paste logic, settings, hotkeys, tray, animation. 30+ methods. Adding feature requires touching main class. Testing any feature requires full Qt stack.
- Safe modification: Extract audio capture logic into separate AudioCapture class. Extract transcription into separate TranscriptionEngine. Extract UI animations into separate WidgetAnimator. Keep DictationWidget as thin coordinator layer.
- Test coverage: No unit tests present. UI testing only possible through manual interaction. Model loading untested. Transcription untested.

**Hardcoded Model Names and Paths:**
- Files: `C:\Project\voice-input\dictation.pyw` lines 43-50 (MODEL_TURBO, MODEL_QUALITY, MODEL_TRANSLATE, MODELS_DIR)
- Why fragile: Model names and switching logic scattered across code. Changing model names requires updates in multiple places (dictation.pyw lines 44-45, line 209, lines 213-225, settings_dialog.py lines 17-22).
- Safe modification: Move all model metadata to config.json. Create ModelRegistry class. Define model capabilities (supports_translate, speed, quality) as metadata. Use registry in model selection logic.
- Test coverage: Model switching tested only manually. No regression tests for model-switching edge cases.

**Keyboard Library Dependency on Global Hook:**
- Files: `C:\Project\voice-input\dictation.pyw` lines 381-388, `C:\Project\voice-input\core\hotkeys.py`
- Why fragile: keyboard.hook() registers global system hotkey. If multiple apps do this, only last one wins. If keyboard library crashes, entire app becomes unresponsive. Requires admin privileges but doesn't check explicitly.
- Safe modification: Add privilege check at startup. Use fallback to local hotkey detection if global hook fails. Detect hotkey conflicts with other apps. Implement timeout on keyboard.wait() call.
- Test coverage: Hotkey registration untested. No test for what happens when hotkey unavailable.

**State Machine Without Explicit State Representation:**
- Files: `C:\Project\voice-input\dictation.pyw` lines 102-138 (state variables: recording, model_loading, current_state, minimized_to_tray, hidden_by_fullscreen)
- Why fragile: State managed through individual boolean/string variables (lines 103-111). Invalid state combinations possible (recording=True AND model_loading=True). No state machine formalism.
- Safe modification: Create AppState enum or State class. Define valid state transitions. Use state machine library (transitions, statemachine). Validate all state changes.
- Test coverage: State transitions untested. No test for invalid state combinations. Race conditions possible during concurrent state changes.

## Scaling Limits

**Single Model in VRAM:**
- Current capacity: One model (2-3GB depending on size) loaded at a time
- Limit: Cannot maintain two models simultaneously for fast mode-switching (e.g., turbo for quick turnaround, quality for important dictation). Switching requires unload/load cycle (5-15s gap).
- Scaling path: Implement model pooling. Pre-load two models in background (if VRAM > 6GB). Allow instant switching. Add user-configurable model swap threshold (auto-switch to quality if detected pause > 3s).

**Transcription Queue Unbounded:**
- Current capacity: No queue—each recording spawns a new transcription thread immediately
- Limit: 100 rapid recordings → 100 concurrent threads. Most blocked waiting for GPU/CPU. System thrashing.
- Scaling path: Implement queue with max size (default 3 pending transcriptions). Queue additional requests. Users see "queue full" feedback. Implement priority queue for urgent transcriptions.

**Single-User Only:**
- Current capacity: One app instance, one user's settings, single config.json
- Limit: Cannot multi-instance. Cannot share profiles. No user switching.
- Scaling path: Not a priority for single-user dictation app, but if ever needed: implement user profiles in config.json. Each user gets separate model cache. Settings per profile.

## Dependencies at Risk

**faster-whisper Unmaintained Risk:**
- Risk: faster-whisper is community fork of OpenAI Whisper. Main Whisper repo is more stable but slower. If faster-whisper maintainer abandons project, models won't be updated for new language support or accuracy improvements.
- Impact: Locked into stale models. Community forks may have unpatched bugs.
- Migration plan: Monitor faster-whisper repo activity. Have contingency plan to switch to official OpenAI Whisper (would require removing turbo model, increasing latency). Alternative: Evaluate other STT engines (vosk for offline, faster but lower accuracy).

**PyQt6 Version Lock:**
- Risk: PyQt6 versioning tied to Qt versioning. Major version bumps rare but breaking. No version pinning in requirements.
- Impact: pip install on new machine might pull incompatible PyQt6 version if requirements don't specify range.
- Migration plan: Pin PyQt6 version in requirements (e.g., PyQt6>=6.0.0,<7.0.0). Test on PyQt6 major version changes before updating.

**keyboard Library Fragile:**
- Risk: keyboard library uses ctypes to hook system events. May break on Windows updates or with certain security software (Windows Defender, EDR tools).
- Impact: Hotkey stops working silently on some Windows installations. No fallback mechanism.
- Migration plan: Add logging to detect hotkey hook failures. Implement fallback using pywin32 (RegisterHotKey API). Test on clean Windows install and on enterprise locked-down machines.

**Windows-Only Dependencies (win32gui, win32api, pyautogui):**
- Risk: Project explicitly Windows-only. If ever need to port to Linux/Mac, significant refactoring needed (pyautogui may not work perfectly, window focus APIs completely different).
- Impact: Can't expand to other platforms without major rewrite.
- Migration plan: Not critical for current scope, but could improve portability by abstracting window focus and paste logic behind WindowManager interface.

## Missing Critical Features

**No Error Recovery:**
- Problem: If Whisper transcription fails (out of memory, corrupted audio, timeout), user gets generic "Ошибка" message and must re-dictate. No partial results, no suggestion to try again with smaller model.
- Blocks: Better user experience. Robustness in poor audio conditions.

**No Audio Quality Feedback:**
- Problem: User records audio but doesn't know if it was too quiet, too noisy, or too short until transcription fails. No real-time waveform, no loudness meter.
- Blocks: Users recording in noisy environments can't adjust microphone position or input levels before transcription attempt.

**No Undo for Incorrect Transcription:**
- Problem: After text is pasted, no easy way to revert. Copy-paste clipboard state is not saved.
- Blocks: Quick error correction. Currently user must manually Ctrl+Z and retype.

**No Transcript History:**
- Problem: All transcribed text is lost once pasted. No history to review, search, or re-paste previous transcriptions.
- Blocks: Workflow efficiency if user needs to reference earlier dictations. Learning what gets transcribed incorrectly.

**No Manual Language Selection Per-Dictation:**
- Problem: Language is global setting (auto or fixed). Can't quickly dictate a sentence in different language without changing config.
- Blocks: Multi-language users from efficient workflow. Always defaults to detected language.

## Test Coverage Gaps

**No Unit Tests:**
- What's not tested: Audio processing, model loading, transcription, configuration loading/saving, hotkey registration, clipboard operations
- Files: All source files lack corresponding test files. No tests/ directory.
- Risk: Any refactoring could break functionality silently. Model switching bugs undiscovered. Edge cases in configuration migration untested.
- Priority: High - test AudioCapture, SpeechRecognizer, ConfigManager as minimum. Mock external dependencies (faster-whisper, pyautogui).

**No Integration Tests:**
- What's not tested: Full pipeline (record → transcribe → paste). Settings changes propagation. Model switching workflow. Hotkey re-registration without app restart.
- Files: No test fixtures or test data for audio samples.
- Risk: Shipping broken workflows (e.g., hotkey changes that don't apply). Configuration changes causing crashes.
- Priority: High - add integration tests for main workflows. Create test audio fixtures (silent audio, speech audio, noise).

**No UI Tests:**
- What's not tested: Widget rendering, tray menu interactions, settings dialog save/load, context menu, minimize/restore
- Files: No UI test framework integrated.
- Risk: UI regressions undetected. Settings dialog changes could break workflows.
- Priority: Medium - UI less critical than core logic but still valuable. Could use pytest-qt or similar.

**No Regression Tests for Model Switching:**
- What's not tested: Fast switching between turbo/quality, switching to translate mode and back, VRAM cleanup correctness
- Files: Model loading logic in dictation.pyw
- Risk: Model switching bugs introduce new memory leaks. Previous fixes regress silently.
- Priority: High - test model switching with memory profiling. Verify CUDA cache actually clears.

---

*Concerns audit: 2026-02-13*
