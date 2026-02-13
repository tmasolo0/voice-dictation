# Codebase Structure

**Analysis Date:** 2026-02-13

## Directory Layout

```
voice-input/
├── dictation.pyw           # Entry point, main PyQt6 widget + audio/recognition logic
├── settings_dialog.py      # Settings UI dialog (tabbed configuration interface)
├── config.json             # Runtime configuration (persisted state + settings)
├── dictionary.txt          # Custom terms for Whisper initial_prompt (for accuracy)
├── Dictation.vbs           # Windows script launcher (runs without console)
├── Dictation.bat           # Windows batch launcher (shows console for debugging)
├── install_local.bat       # Dependency installation script
├── core/                   # Core service modules
│   ├── __init__.py
│   ├── config_manager.py   # Singleton config management + JSON persistence
│   ├── recognizer.py       # SpeechRecognizer class (faster-whisper wrapper)
│   ├── hotkeys.py          # HotkeyManager class (keyboard event handling)
│   └── tray.py             # SystemTray class (PyQt6 tray icon wrapper)
├── models/                 # Local Whisper model storage (not in git)
│   ├── large-v3-turbo/
│   ├── large-v3/
│   └── medium/
├── logs/                   # Application logs (runtime created)
│   └── dictation.log
└── python311/              # Embedded Python 3.11 distribution (not in git)
    ├── python.exe
    ├── Lib/
    │   └── site-packages/  # Dependencies (PyQt6, faster-whisper, etc.)
    └── Scripts/
```

## Directory Purposes

**`core/`:**
- Purpose: Reusable service abstractions and utilities
- Contains: Configuration singleton, audio recognizer, hotkey manager, tray utilities
- Key files: `config_manager.py` (most critical), `recognizer.py` (optional, currently unused), `hotkeys.py` (optional, currently unused), `tray.py` (optional, currently unused)
- Status: Partially utilized (ConfigManager is essential, others are available but not used in main flow)

**`models/`:**
- Purpose: Local cache for Whisper model weights
- Contains: Pre-downloaded model directories (large-v3-turbo, large-v3, medium)
- Files: Model weights, config.json, tokenizer.json, vocabulary.json per model
- Generated: Yes (populated by user or by faster-whisper auto-download)
- Committed: No (directory ignored in .gitignore due to size)

**`logs/`:**
- Purpose: Runtime application logs for debugging
- Contains: dictation.log (Python logging output at ERROR level)
- Generated: Yes (created on first run by setup_logging())
- Committed: No

**`python311/`:**
- Purpose: Bundled Python runtime (standalone execution without system Python)
- Contains: Python 3.11 interpreter, standard library, all pip dependencies
- Generated: No (committed or bundled separately)
- Committed: No

## Key File Locations

**Entry Points:**

- `C:\Project\voice-input\Dictation.vbs`: Windows launcher (silent, no console window)
- `C:\Project\voice-input\Dictation.bat`: Windows launcher (debug, shows console)
- `C:\Project\voice-input\dictation.pyw`: Python entry point, main() function at line 659

**Configuration:**

- `C:\Project\voice-input\config.json`: Runtime settings (widget position, hotkey, model, Whisper params)
- `C:\Project\voice-input\core\config_manager.py`: ConfigManager singleton, schema definition (lines 17-46)
- `C:\Project\voice-input\dictionary.txt`: Custom terms for initial_prompt (auto-loaded by ConfigManager.get_initial_prompt())

**Core Logic:**

- `C:\Project\voice-input\dictation.pyw` - DictationWidget class (lines 93-637):
  - `_setup_ui()` (line 140): Window creation, frameless + always-on-top flags
  - `_init_model()` (line 326): Model initialization on startup
  - `_on_key_event()` (line 431): Hotkey handler, recording state machine
  - `_process_audio()` (line 462): Whisper transcription in background thread
  - `_paste_text()` (line 515): Text insertion via clipboard + Ctrl+V
  - `paintEvent()` (line 536): Circular animation rendering with state colors

**Testing:**

- Not detected (no test files found in codebase)

## Naming Conventions

**Files:**

- Snake_case: `config_manager.py`, `settings_dialog.py`, `dictation.pyw`
- All lowercase: Python modules and packages
- Capital camelCase: Windows launchers (`Dictation.vbs`, `Dictation.bat`)

**Directories:**

- Lowercase: `core/`, `models/`, `logs/`, `python311/`
- Function: Directory names are plural or descriptive of content

**Functions:**

- Snake_case (Python standard): `_on_key_event()`, `_process_audio()`, `_set_state()`
- Private methods prefixed with single underscore: `_setup_ui()`, `_load_model()`
- Public methods (few): No underscore, e.g. `recognize()` in SpeechRecognizer

**Variables:**

- Snake_case: `current_state`, `recording`, `focused_window`, `audio_data`
- Constants: UPPER_SNAKE_CASE: `HOTKEY`, `SAMPLE_RATE`, `MODEL_TURBO`, `COLORS`

**Classes:**

- PascalCase: `DictationWidget`, `ConfigManager`, `SpeechRecognizer`, `HotkeyManager`, `SystemTray`, `SettingsDialog`

**Config Keys:**

- Nested hierarchy with lowercase: `config.get('recognition', 'hotkey')`, `config.get('widget', 'position', 'x')`

## Where to Add New Code

**New Feature (e.g. logging, export transcription history):**
- Primary code: Add to `DictationWidget` class methods in `C:\Project\voice-input\dictation.pyw` OR create new service in `core/`
- Configuration: Add new section to DEFAULT_CONFIG in `C:\Project\voice-input\core\config_manager.py` (lines 17-46)
- UI if needed: Extend `SettingsDialog` tabs in `C:\Project\voice-input\settings_dialog.py` (add new QWidget via `_create_*_tab()` method)
- Tests: Create `test_*.py` at project root (pattern: test_dictation.py, test_config_manager.py)

**New Core Service (e.g. custom audio processing, external API integration):**
- Implementation: Create new file in `core/` directory, e.g. `core/my_service.py`
- Class pattern: Follow existing classes (ConfigManager singleton, HotkeyManager init/register pattern, SystemTray wrapper pattern)
- Export: Add to `core/__init__.py` for public import
- Usage: Import in `dictation.pyw` and integrate into DictationWidget lifecycle

**UI Component (new window, dialog, or widget):**
- Dialog classes: Create in `C:\Project\voice-input\settings_dialog.py` (or separate file if complex)
- Widget classes: Keep in `dictation.pyw` or create `ui_components.py` if reusable
- Pattern: Inherit from PyQt6.QtWidgets (QDialog, QWidget, etc.), use form layouts for settings

**Utilities and Helpers:**
- Shared functions: Create `core/utils.py` or append to relevant service module
- Data transformations: Add class methods to existing service classes (e.g. ConfigManager)
- One-off: Keep in `dictation.pyw` if simple and single-use

## Special Directories

**`models/`:**
- Purpose: Cached Whisper model weights (downloaded by faster-whisper)
- Generated: Yes (auto-created by faster-whisper if missing, unless local_path exists)
- Committed: No (.gitignore prevents large binary uploads)
- Manual population: User runs `download_medium.py` to pre-cache models
- Behavior: `WhisperModel(local_path or model_name)` checks `models/model_name/` first; if exists, loads; else downloads

**`logs/`:**
- Purpose: Runtime diagnostic logs
- Generated: Yes (created by setup_logging() on first run)
- Committed: No
- Rotation: No rotation configured (single file, unbounded growth)

**`python311/`:**
- Purpose: Bundled Python interpreter + dependencies (self-contained)
- Generated: No (pre-built, distributed with application)
- Committed: Conditionally (typically bundled as separate archive, not git)
- Invocation: Batch/VBS scripts call `python311\python.exe` explicitly

## File Responsibilities Matrix

| File | Responsibility | Editable | Public |
|------|-----------------|----------|--------|
| `dictation.pyw` | Main UI + audio/recognition orchestration | Yes | Entry point |
| `core/config_manager.py` | Settings I/O, schema | Yes | ConfigManager singleton |
| `core/recognizer.py` | Whisper wrapper (optional) | Yes | SpeechRecognizer class |
| `core/hotkeys.py` | Global hotkey handling (optional) | Yes | HotkeyManager class |
| `core/tray.py` | Tray icon abstraction (optional) | Yes | SystemTray class |
| `settings_dialog.py` | Settings GUI | Yes | SettingsDialog class |
| `config.json` | Runtime settings | Yes (via UI or manual edit) | Config file |
| `dictionary.txt` | Custom Whisper terms | Yes (manual edit) | Text file |
| `models/*/` | Model weights | Auto-generated | Binary files |
| `logs/dictation.log` | Debug output | No | Log file |

---

*Structure analysis: 2026-02-13*
