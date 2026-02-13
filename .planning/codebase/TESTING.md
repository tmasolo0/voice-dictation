# Testing Patterns

**Analysis Date:** 2026-02-13

## Test Framework

**Status:** Not configured

- No test runner installed (pytest, unittest, vitest not detected)
- No test files present in codebase
- No testing dependencies in requirements
- No test configuration files (pytest.ini, setup.cfg, pyproject.toml with test config)

**Manual Testing:**
- Code relies on manual testing during development
- Entry points exist for Windows execution: `Dictation.bat` (with console), `Dictation.vbs` (without console)

## Test File Organization

**Current State:**
- Zero test files detected
- Test directory structure: Not applicable (no tests present)

**Recommended Pattern (for future implementation):**
```
C:\Project\voice-input\
├── tests/                          # Test directory
│   ├── __init__.py
│   ├── test_config_manager.py      # Tests for core/config_manager.py
│   ├── test_recognizer.py          # Tests for core/recognizer.py
│   ├── test_hotkeys.py             # Tests for core/hotkeys.py
│   ├── test_tray.py                # Tests for core/tray.py
│   └── test_settings_dialog.py      # Tests for settings_dialog.py
└── dictation.pyw                   # Main entry point
```

## Code Testability Issues

**Tightly Coupled Components:**
- `DictationWidget` (dictation.pyw) is a monolithic class mixing concerns:
  - UI setup, audio recording, model management, hotkey handling
  - Creates and manages own threads, timers, streams
  - Difficult to test in isolation without mocking extensive PyQt6 infrastructure

**Example of coupling** (dictation.pyw line 96-138):
```python
def __init__(self):
    super().__init__()
    # ... state initialization ...
    self._setup_ui()           # UI depends on config
    self._setup_tray()         # Tray depends on self.dictation_model
    self._init_model()         # Model loading (blocking operation)
    self._start_audio_stream() # Starts sounddevice stream
    self._start_keyboard_listener()  # Spawns threading
    self._start_fullscreen_monitor() # Creates timer
    self._start_animation()    # Creates timer
```

**Global Dependencies:**
- `config` singleton imported globally: `from core.config_manager import config`
- Difficult to test with different configurations without singleton pattern workarounds
- `HOTKEY`, `DEVICE`, `COMPUTE_TYPE` constants read at module level, not from config parameter

## Current Error Handling Testability

**Exception Handling:**
- Broad `except Exception:` blocks prevent specific error testing
  - Example: `dictation.pyw` line 509-510: `except Exception as e: print(f"Ошибка: {e}")`
  - No custom exception types defined

**Threading Without Observability:**
- Threads spawned for audio processing, model loading, hotkey listening
- No threading event/callback pattern to verify completion
- Example (dictation.pyw line 454-458): Threading spawned with daemon=True, no way to await result

**File I/O Not Isolated:**
- Config file operations hardcoded to filesystem
- Audio streams hardcoded to sounddevice and Windows API
- No interface/abstract base class to inject test doubles

## Potential Testing Strategy

**Unit Test Candidates:**
1. `ConfigManager` - Singleton pattern, file I/O
   - Test loading/saving config.json
   - Test nested key access (get/set)
   - Test migration logic
   - Test default values

2. `SpeechRecognizer` - Model loading, transcription logic
   - Test model loading (mock WhisperModel)
   - Test recognize() with mock audio data
   - Test parameter passing to transcribe()

3. `HotkeyManager` - Hotkey registration and event handling
   - Test register/unregister methods
   - Test callback invocation (mock keyboard module)
   - Test key press/release state tracking

4. Settings Dialog - PyQt6 widget
   - Test load/save settings with mock ConfigManager
   - Test UI state changes

**Integration Test Candidates:**
1. Config file persistence end-to-end
2. Model switching workflow
3. Audio recording and transcription flow (with mock audio)
4. Hotkey triggering and text insertion (Windows-specific, manual testing likely)

**Manual Testing:**
- Push-to-talk hotkey (F9) recording and transcription
- Translation mode toggle
- Quality mode toggle
- Widget drag and position persistence
- Fullscreen application detection and widget hiding
- Tray icon and context menu interactions

## Architecture for Testability (Recommendations)

**Current Pattern:**
```python
class DictationWidget(QWidget):
    def __init__(self):
        self.model = WhisperModel(...)  # Hardcoded dependency
        self.stream = sd.InputStream(...)  # Hardcoded dependency
        keyboard.hook(...)  # Hardcoded dependency
```

**Testable Pattern (recommended for refactoring):**
```python
class DictationWidget(QWidget):
    def __init__(self,
                 recognizer: SpeechRecognizer,  # Injected
                 audio_stream: AudioStreamInterface,  # Injected
                 hotkey_manager: HotkeyManager):  # Injected
        self.recognizer = recognizer
        self.stream = audio_stream
        self.hotkey_manager = hotkey_manager
```

## Code Patterns Inhibiting Testing

**1. Circular Imports Prevention:**
- Settings dialog imports config: `from core.config_manager import config`
- DictationWidget imports config: `from core.config_manager import config`
- No test doubles possible without refactoring

**2. Thread Spawning in Methods:**
- Audio processing: `threading.Thread(target=self._process_audio, ..., daemon=True).start()`
- Model loading: `threading.Thread(target=do_load, daemon=True).start()`
- No way to verify completion or inject test audio

**3. Platform Dependencies:**
- Windows-only APIs: `win32gui`, `win32api`, `win32con`
- System tray requires X11/Win32 platform (not testable cross-platform)
- Keyboard library hooks system input (requires root/admin)

**4. Direct File System Access:**
- Config file: `C:\Project\voice-input\config.json`
- Dictionary: `C:\Project\voice-input\dictionary.txt`
- Models: `C:\Project\voice-input\models\`
- Log directory: `C:\Project\voice-input\logs\`
- No abstraction for file paths or mock filesystem support

## Logging for Test Verification

**Current Approach:**
- Print statements to stdout for all status messages
- Exception logging to `logs/dictation.log` (only ERROR level)
- No structured logging (all logs are formatted strings)

**Testing Implication:**
- Cannot verify application behavior by capturing logs (no structured data)
- Hard to assert on behavior from test code (print statements not capturable in all scenarios)

## Signal/Slot Testing

**PyQt6 Signals Used:**
- `SignalEmitter.state_changed` (custom signal)
- Connected to `_set_state()` method for UI updates
- Signal-based state management enables testing UI state transitions
- Could be tested by mocking signal sender and verifying connected slot calls

**Example** (dictation.pyw line 99-100):
```python
self.signals = SignalEmitter()
self.signals.state_changed.connect(self._set_state)
```

## Missing Critical Test Infrastructure

- No mock objects or factories
- No test fixtures for configuration states
- No test audio data
- No way to isolate Windows-specific code for cross-platform testing
- No mocking of external dependencies (faster-whisper, sounddevice)
- No dependency injection pattern

---

*Testing analysis: 2026-02-13*
