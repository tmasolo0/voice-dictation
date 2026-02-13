# Technology Stack

**Analysis Date:** 2026-02-13

## Languages

**Primary:**
- Python 3.11 - Core application language, distributed locally in `python311/` directory

**Secondary:**
- None (no additional languages used)

## Runtime

**Environment:**
- Python 3.11 (embedded locally)
- Windows-only (win32api, win32gui dependencies)

**Package Manager:**
- pip
- Lockfile: Not detected (uses direct pip install via `install_local.bat`)

## Frameworks

**Core UI:**
- PyQt6 - Desktop GUI framework for main widget, settings dialog, and system tray integration
  - Used in `dictation.pyw`, `settings_dialog.py`, `core/tray.py`

**Speech Recognition:**
- faster-whisper - Optimized Whisper speech-to-text model inference
  - Core STT engine wrapped in `core/recognizer.py`
  - Loads local models from `models/` directory
  - Supports transcription and translation tasks

**Audio Capture:**
- sounddevice (scipy backend) - Low-level audio stream recording at 16kHz mono
  - Configured in `DictationWidget._start_audio_stream()` at line 365-374

**System Integration:**
- keyboard - Global keyboard hotkey listener and key state detection
  - Hooks F9 for push-to-talk in `dictation.pyw` line 381-388
  - Used in `core/hotkeys.py` for HotkeyManager

**Clipboard & Automation:**
- pyperclip - Cross-platform clipboard copy/paste
- pyautogui - Simulate keyboard input (Ctrl+V) for text insertion
- pywin32 (win32gui, win32api, win32con) - Windows API access for window management and focus control

**Utility Libraries:**
- numpy - Audio data processing (array operations)

## Key Dependencies

**Critical:**
- `faster-whisper` - Core functionality; application cannot work without it
  - Models: large-v3-turbo, large-v3, medium (stored locally in `models/` directory)
  - Loads via WhisperModel class in `dictation.pyw` line 357

- `PyQt6` - UI framework dependency
  - All UI operations depend on PyQt6 widgets and signals

- `keyboard` - Global hotkey interception
  - Without it, F9 push-to-talk cannot be detected globally

- `sounddevice` - Audio capture
  - Records audio stream during F9 press

**Infrastructure:**
- `numpy` - Audio array manipulation (required by faster-whisper)
- `pyperclip` - Clipboard integration for text paste
- `pyautogui` - Keyboard simulation for insertion
- `pywin32` - Windows window management and focus

## Configuration

**Environment:**
- Configured via JSON file: `config.json` at project root
- Managed by singleton `ConfigManager` in `core/config_manager.py`
- No env vars required for base functionality
- Optional: OpenAI API config present but not actively used in current code (line 32-35 in config.json)

**Build:**
- No build config (Python .pyw script runs directly)
- Batch scripts for execution:
  - `Dictation.vbs` - Runs without console window
  - `Dictation.bat` - Runs with console (debugging)

**Configuration Sections:**
- `widget` - UI position, size, fullscreen behavior
- `recognition` - Hotkey, model choice, Whisper parameters (beam_size, temperature, compression_ratio_threshold, etc.)
- `system` - Autostart flags
- `vad` - Voice Activity Detection thresholds
- `tts` - Text-to-speech settings (configured but not used in current version)
- `openai` - OpenAI API config (present but unused)

## Platform Requirements

**Development:**
- Windows 7+ (win32gui APIs required)
- CUDA-capable GPU recommended (can fall back to CPU via `device: "cuda"` → CPU in config)
- RAM: 2GB minimum for medium model, 4GB+ for large-v3-turbo

**Production:**
- Windows-only deployment
- Python 3.11 embedded locally (bundled)
- GPU strongly recommended for real-time transcription
- Display required (GUI application)

## Quality Parameters

Whisper transcription quality is controlled through config.json parameters in `recognition` section:

- `beam_size: 5` - Search width (higher = more accurate but slower)
- `temperature: 0.3` - Sampling temperature (0 = greedy decoding)
- `compression_ratio_threshold: 2.4` - Filter repetitive hallucinations
- `log_prob_threshold: -1.0` - Filter low-confidence segments
- `no_speech_threshold: 0.6` - Silence detection threshold
- `repetition_penalty: 1.2` - Token repetition penalty
- `no_repeat_ngram_size: 3` - Prevent n-gram repetition
- `condition_on_previous_text: false` - Disable for push-to-talk (prevents context carryover)
- `hallucination_silence_threshold: 2.0` - Filter false speech on silence

## Model Management

**Model Selection:**
- Default: `large-v3-turbo` (fast, good quality)
- Alternative: `large-v3` (slower, highest quality)
- Translation mode: `medium` (supports translate task)
- Storage: Local directory `models/` (not tracked in git)

**Model Loading:**
- Lazy-loaded on first use or when switching modes
- Unloaded from VRAM when switching to reduce memory (line 339-351 in dictation.pyw)
- CUDA cache cleared after unload if PyTorch available

---

*Stack analysis: 2026-02-13*
