# Architecture

**Analysis Date:** 2026-02-13

## Pattern Overview

**Overall:** Monolithic single-window desktop application with modular core services layer

**Key Characteristics:**
- Event-driven push-to-talk (hotkey-triggered) architecture
- Singleton configuration management pattern
- Multi-threaded audio processing with main UI thread isolation
- Direct Windows API integration for window focus and clipboard management
- Lazy model loading with background threading to prevent UI freezing

## Layers

**Presentation (UI):**
- Purpose: PyQt6 widget rendering, user interaction, state visualization
- Location: `C:\Project\voice-input\dictation.pyw` (DictationWidget class, lines 93-637)
- Contains: Window setup, event handlers, animation loop, tray icon management
- Depends on: ConfigManager, win32gui/win32api, sounddevice, keyboard, pyautogui
- Used by: Entry point main()

**Audio/Recognition:**
- Purpose: Speech recognition via faster-whisper, audio capture, model loading
- Location: `C:\Project\voice-input\dictation.pyw` (audio callbacks and model loading, lines 326-363, 462-513)
- Contains: Whisper model instantiation, transcription with task="transcribe" or task="translate", VAD filtering
- Depends on: faster-whisper, numpy, sounddevice, config parameters
- Used by: DictationWidget._process_audio()

**Configuration (Core):**
- Purpose: Centralized settings management with JSON persistence
- Location: `C:\Project\voice-input\core\config_manager.py` (ConfigManager singleton)
- Contains: Config file I/O, hierarchical key-value access, schema migration, dictionary.txt term loading
- Depends on: pathlib, json
- Used by: All layers for reading Whisper params, hotkey, device settings

**Hotkey Management (Core):**
- Purpose: Global keyboard event capture and callback dispatch
- Location: `C:\Project\voice-input\core\hotkeys.py` (HotkeyManager class)
- Contains: Keyboard hook registration, press/release event handling
- Depends on: keyboard library
- Used by: DictationWidget._start_keyboard_listener() (currently inline, not using HotkeyManager)

**System Tray (Core):**
- Purpose: Tray icon, state visualization, menu integration
- Location: `C:\Project\voice-input\core\tray.py` (SystemTray class)
- Contains: Icon creation, tooltip updates, context menu setup
- Depends on: PyQt6.QtWidgets, PyQt6.QtGui
- Used by: DictationWidget._setup_tray() (direct PyQt6 implementation, not using SystemTray wrapper)

**Settings Dialog:**
- Purpose: Interactive UI for editing config.json
- Location: `C:\Project\voice-input\settings_dialog.py` (SettingsDialog class)
- Contains: Tabbed interface (Widget/Recognition/System), form validation, save/cancel logic
- Depends on: PyQt6, ConfigManager
- Used by: Potential future menu integration (currently unused in dictation.pyw)

## Data Flow

**Record → Recognize → Insert workflow:**

1. User presses F9
   - `_on_key_event()` (line 431) detects hotkey down
   - Stores focused window handle via `win32gui.GetForegroundWindow()`
   - Sets `recording = True`, emits signal → `_set_state("recording")`
   - Audio stream callback (`_audio_callback`, line 376) starts buffering frames to `self.audio_data`

2. User releases F9
   - `_on_key_event()` detects hotkey up
   - Sets `recording = False`, emits signal → `_set_state("processing")`
   - Spawns daemon thread calling `_process_audio(audio_np)`

3. Audio Processing (background thread)
   - Numpy array concatenated from audio frames (line 453)
   - `model.transcribe()` called with Whisper parameters from config (lines 470-496)
   - VAD filter enabled to remove silence
   - Translation mode: `task="translate"` → English output
   - Transcription mode: `task="transcribe"` + `initial_prompt` from dictionary.txt → auto-detected language
   - Text extraction from segments (line 499)

4. Text Insertion
   - `_paste_text(text)` (line 515)
   - Restores focused window with `win32gui.SetForegroundWindow()`
   - Text → clipboard via `pyperclip.copy()`
   - Paste simulated via `pyautogui.hotkey('ctrl', 'v')`
   - UI returns to `_set_state("ready")`

**State Management:**

```
ready (pulsing green) ↓F9↓ → recording (pulsing red)
  ↑ ← processing (yellow) ← (transcription complete)
```

States emit via `SignalEmitter.state_changed` signal (line 90) to decouple threading from UI updates.

Translation mode overlay: State "ready" + `translate_mode=True` → blue circle with "EN" label (lines 545-576).

**Model Loading:**

- On startup: `_init_model()` (line 326) loads configured model synchronously (may block)
- On mode toggle: `_switch_model(new_model)` (line 238) spawns background thread, emits "processing", avoids UI freeze
- Model unloading: Previous model explicitly deleted + `gc.collect()` + `torch.cuda.empty_cache()` (lines 340-351)

## Key Abstractions

**DictationWidget:**
- Purpose: Monolithic UI container integrating all functionality
- Encapsulates: Audio stream, model, keyboard listener, animation loop, tray icon
- Lifetime: Single instance created in main(), persists for app lifetime
- Pattern: Hybrid (contains core logic + UI rendering instead of delegating to service classes)

**ConfigManager (Singleton):**
- Purpose: Immutable configuration interface
- Access pattern: `config.get('section', 'key', default=value)` and `config.set(...)`
- Persistence: Auto-save to `config.json` on `config.save()`
- Migration: Handles version 1→2 schema upgrade (lines 81-98)

**SignalEmitter (QObject):**
- Purpose: Decouple background thread operations from Qt main thread
- Mechanism: `pyqtSignal.connect()` ensures UI updates run in main thread
- Currently used for: State changes only (ready/recording/processing/translate)

**Whisper Model Loading:**
- Pattern: Lazy loading on startup + on-demand background switching
- Device selection: CUDA by default, fallback to CPU via config
- Compute type: float16 for VRAM efficiency
- Local vs remote: Checks `models/` directory first, falls back to auto-download

## Entry Points

**Dictation.vbs / Dictation.bat:**
- Location: `C:\Project\voice-input\Dictation.vbs`, `C:\Project\voice-input\Dictation.bat`
- Triggers: User executes batch/script file
- Responsibilities: Invokes Python interpreter with `dictation.pyw` (hidden console for .vbs)

**dictation.pyw (main function, line 659):**
- Location: `C:\Project\voice-input\dictation.pyw`
- Triggers: Python execution
- Responsibilities:
  1. Setup logging (line 661)
  2. Create QApplication (line 663)
  3. Instantiate DictationWidget (line 666) → triggers all initialization (audio stream, model, listeners)
  4. Show widget + print startup info (lines 667-676)
  5. Run Qt event loop (line 678)

## Error Handling

**Strategy:** Try/catch with console logging, graceful degradation

**Patterns:**

- **Audio Processing:** Wrapped in try/finally (lines 464-513), state reset on any exception
- **Model Loading:** try/except with error print (line 249-252), model_loading flag prevents retry spam
- **Window Focus:** Exception silently caught (line 527), continues paste attempt anyway
- **Config Migration:** IOError → prints message + fallback to DEFAULT_CONFIG (lines 73-79)
- **Whisper Transcription:** No explicit error handling, exceptions bubble to process_audio() handler

## Cross-Cutting Concerns

**Logging:**
- Framework: Python `logging` module
- Output: `logs/dictation.log` (file only, no console, level=ERROR)
- Setup: `setup_logging()` (line 639), custom exception hook captures uncaught exceptions
- Observation: Application logic uses `print()` for console feedback, not logger

**Validation:**
- No explicit input validation layer
- Hotkey validation: keyboard library handles name parsing
- Audio validation: Empty audio_data check before transcription (line 452)
- Model validation: Model existence checked at load time; no validation of audio duration

**Authentication:**
- Not applicable (local-only application, no external APIs)

**Threading:**
- Model: Spawn daemon threads per operation (keyboard listener, model loading, audio processing)
- Synchronization: SignalEmitter.pyqtSignal for main thread communication
- No mutex/lock usage observed (single writer pattern: main thread only modifies state after signal)

**Windows Integration:**
- `win32gui.GetForegroundWindow()` → capture focused window handle
- `win32gui.SetForegroundWindow()` → restore focus for paste
- `win32api.MonitorFromWindow() / GetMonitorInfo()` → fullscreen detection
- `keyboard.hook()` → global hotkey capture (requires elevation)
- `pyperclip.copy()` + `pyautogui.hotkey()` → clipboard text insertion

---

*Architecture analysis: 2026-02-13*
