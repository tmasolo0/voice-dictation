# Coding Conventions

**Analysis Date:** 2026-02-13

## Naming Patterns

**Files:**
- `snake_case.py` - All Python module files use lowercase with underscores
  - Examples: `config_manager.py`, `settings_dialog.py`, `dictation.pyw`
  - Main entry point exception: `dictation.pyw` (uses `.pyw` extension for Windows GUI without console)

**Classes:**
- `PascalCase` - All classes follow PascalCase
  - Examples: `DictationWidget`, `ConfigManager`, `SpeechRecognizer`, `HotkeyManager`, `SystemTray`, `SettingsDialog`

**Functions & Methods:**
- `snake_case` - All functions and methods use lowercase with underscores
  - Public methods: `_setup_ui()`, `load_model()`, `transcribe()`
  - Private methods prefixed with single underscore: `_load_position()`, `_on_key_event()`, `_animate()`

**Variables:**
- `snake_case` - All variables use lowercase with underscores
  - Instance variables: `self.recording`, `self.model`, `self.audio_data`
  - Constants in UPPER_CASE_WITH_UNDERSCORES: `HOTKEY`, `SAMPLE_RATE`, `MODEL_TURBO`, `COLORS`, `ANIMATION_INTERVAL`
  - Local variables in functions: `audio_np`, `model_name`, `elapsed`

**Type Hints:**
- Used for public method signatures, not enforced throughout
  - Example from `core/recognizer.py`: `def recognize(self, audio: np.ndarray, language: Optional[str] = None, vad_filter: bool = True) -> str:`
  - Return types specified for key methods

## Code Style

**Formatting:**
- No explicit formatter detected (no .pylintrc, .flake8, or pyproject.toml with formatter config)
- Style is Python 3.11 compliant
- String encoding: UTF-8 explicitly set in file operations (`encoding='utf-8'`)
- Multi-line method calls: arguments aligned naturally without strict formatting rules

**Linting:**
- No linter configuration detected - code relies on developer discipline
- PEP 8 style generally followed with some flexibility

**Line Length:**
- Appears to allow longer lines for readability (some lines exceed 100 characters)
- Example: Line 479 in `dictation.pyw`: 96+ characters for configuration parameters

## Import Organization

**Order:**
1. Built-in modules (`sys`, `logging`, `pathlib.Path`, `json`, `copy`, `typing`)
2. Third-party packages (`numpy`, `PyQt6`, `keyboard`, `sounddevice`, `pyperclip`, `pyautogui`, `faster_whisper`, `win32*`)
3. Local imports from project (`from core.config_manager import config`, `from .config_manager import ...`)

**Path Aliases:**
- Relative imports used in `core/` modules: `from .config_manager import config`
- Absolute path insertion in `dictation.pyw`: `sys.path.insert(0, str(Path(__file__).parent))`
- No import aliases (no `import X as Y`) in observed code

**Wildcard Imports:**
- Generally avoided; specific imports preferred
- Exception: PyQt6 widgets imported with specific items listed

## Error Handling

**Patterns:**
- Try-except with broad exception catching in critical paths
  - `dictation.pyw` line 70: `except Exception: return False` in `is_fullscreen_app_active()`
  - `core/recognizer.py` line 70: `except Exception as e: print(f"Ошибка загрузки модели Whisper: {e}")`
- Exception info printed to stdout (console) - no logging framework used
- Graceful degradation: missing files return defaults rather than raise
  - `core/config_manager.py` line 147: `if not DICTIONARY_FILE.exists(): return ""`

**Specific Patterns:**
- Model loading failures emit error message and continue: `try-except-return False`
- File I/O errors caught with specific exception types: `except (json.JSONDecodeError, IOError) as e:`
- Threading errors not explicitly caught (threads run with try-finally wrappers in some cases)

## Logging

**Framework:** No logging framework configured - uses `print()` statements

**Patterns:**
- Information messages: `print(f"Загрузка модели {model_name}...")` (line 337 in dictation.pyw)
- Error messages: `print(f"Ошибка: {e}")` (line 510 in dictation.pyw)
- Status messages: `print(f"[{elapsed:.1f}с] {mode_info}: {text}")`
- Setup logging function exists (`setup_logging()` line 639) that configures exception handler to write to `logs/dictation.log`
- Log format: `%(asctime)s - %(levelname)s - %(message)s`
- Log level: ERROR (only exceptions logged to file)

**Stdout Usage:**
- All application messages go to stdout
- Examples: "Запись...", mode status, quality changes, model loading progress

## Comments

**When to Comment:**
- Module-level docstrings required (every `.py` file starts with triple-quoted module description)
- Class docstrings: Brief one-liner after class declaration
  - Example: `"""Минималистичный виджет для голосовой диктовки."""`
- Method docstrings: Present for public methods, sparse for private methods
- Inline comments minimal - code is self-documenting where possible

**Docstring Style (Russian):**
- Module docstrings explain purpose and key features
- Class docstrings one-liner
- Method docstrings include:
  - One-line summary
  - Args section with type hints
  - Returns section
  - Example: `core/recognizer.py` line 84-93

**Section Comments:**
- Used to separate logical blocks within functions
  - `# === НАСТРОЙКИ ===` (line 38 in dictation.pyw)
  - `# Модели Whisper` (line 42)
  - `# Цвета состояний` (line 52)

## Function Design

**Size:** Functions typically 10-50 lines, with some longer methods handling complex UI (paintEvent: 40+ lines)

**Parameters:**
- Methods use self-explanatory parameter names
- Default values provided through config, not function parameters (except in recognizer API)
- Optional parameters marked with `Optional[Type]` in type hints

**Return Values:**
- Single return values preferred
- Methods modifying state return None (UI setup methods)
- Methods querying state return typed values (str, bool, dict, Tuple)
- Example: `_process_audio()` returns None but emits signals for state changes

**Error Returns:**
- Methods return False on error rather than raising exceptions: `load_model() -> bool`
- Empty strings returned for missing config: `get_initial_prompt() -> str` returns `""`
- Tuple returns for complex data: `recognize_with_info() -> Tuple[str, dict]`

## Module Design

**Exports:**
- Core modules export through `__all__` list in `core/__init__.py`
  - Exports: `config`, `ConfigManager`, `SpeechRecognizer`, `HotkeyManager`, `SystemTray`
- Singleton pattern used for config: `config = ConfigManager()` at module level in `core/config_manager.py`

**Barrel Files:**
- `core/__init__.py` serves as barrel file for core modules
- Imports and re-exports key classes and singletons for convenience
- Consumers import: `from core import config, ConfigManager` or `from core.config_manager import config`

**State Management:**
- Singleton pattern: `ConfigManager` uses `__new__` to ensure single instance
- Global instance creation: `config = ConfigManager()` at module level (line 163)
- Hot key manager: `_default_manager` pattern with `get_hotkey_manager()` getter (line 129)

## Configuration Pattern

**ConfigManager (Singleton):**
- Located: `core/config_manager.py`
- Design: Thread-safe singleton via `__new__` method
- Usage: `config.get('section', 'key', default=value)`
- Nested access: `config.get('widget', 'position', 'x', default=None)` - variadic path arguments
- Setting: `config.set('section', 'key', value)` with auto-creation of missing keys
- Persistence: `config.save()` writes to `config.json` with UTF-8 encoding and pretty-print (indent=2)
- Migration: `_migrate()` method handles version upgrades

**Configuration File:**
- Location: `C:\Project\voice-input\config.json`
- Schema: Nested sections (widget, recognition, system, vad, tts, openai)
- Type preservation: JSON native types (bool, int, float, list, string)
- Default values: `DEFAULT_CONFIG` dict defined in module

## String Handling

**Encoding:**
- All file operations explicitly use UTF-8: `open(..., encoding='utf-8')`
- F-strings used throughout for formatting
- Russian text literals in code (not externalized)

**Text Processing:**
- Strip whitespace after concatenation: `text.strip()`
- Join lists for output: `"".join([segment.text for segment in segments]).strip()`

---

*Convention analysis: 2026-02-13*
