# External Integrations

**Analysis Date:** 2026-02-13

## APIs & External Services

**OpenAI API:**
- Service: ChatGPT (for future use)
- What it's used for: Configured but NOT currently active in code
- SDK/Client: Not imported (would use openai package)
- Auth: Would use `OPENAI_API_KEY` env var (not implemented)
- Config location: `config.json` lines 32-35 (unused)
- Status: Configuration placeholder only; no integration in dictation.pyw

## Data Storage

**Databases:**
- None used - Application is stateless

**File Storage:**
- Local filesystem only
- Configuration: `config.json` at project root
- Dictionary/terminology: `dictionary.txt` at project root
- Models: `models/` directory (Whisper model files, not tracked in git)
- Logs: `logs/` directory (created at runtime, not tracked)

**Caching:**
- None configured
- Model weights cached in-memory during runtime
- CUDA cache available when GPU used (cleared manually via torch.cuda.empty_cache() at line 349)

## Authentication & Identity

**Auth Provider:**
- None required for local operation
- Optional: OpenAI API key (not implemented)

## Monitoring & Observability

**Error Tracking:**
- None (self-hosted only)

**Logs:**
- File-based logging to `logs/dictation.log` (UTF-8)
- Configured in `setup_logging()` function at line 639-656 in dictation.pyw
- Level: ERROR (only errors logged to file)
- Console output: Print statements for debugging (visible when running Dictation.bat)

**Exceptions:**
- Global exception handler logs uncaught exceptions
- Implementation at line 652-656 in dictation.pyw

## CI/CD & Deployment

**Hosting:**
- Local Windows machine (no cloud deployment)
- Standalone executable wrapper (Dictation.vbs) for production use without console

**CI Pipeline:**
- None detected
- Manual deployment via batch scripts

## Environment Configuration

**Required env vars:**
- None for base operation
- Optional: OPENAI_API_KEY (if OpenAI integration activated in future)

**Secrets location:**
- No secrets required for current implementation
- Config stored in plain text JSON: `config.json`
- Future OpenAI key would need to be stored securely (not yet implemented)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None (application is receive-only: F9 hotkey → internal processing → text insertion)

## External Model Sources

**Whisper Models:**
- Source: Hugging Face Hub (implicitly via faster-whisper)
- Download: Automatic on first use if not in local `models/` directory
- Models supported:
  - `large-v3-turbo` (13.1B parameters, optimized)
  - `large-v3` (1.5B parameters, highest quality)
  - `medium` (769M parameters, translation support)
  - `small` (244M parameters, fastest)
- Storage: `C:\Project\voice-input\models\` (local cache)
- Not committed to git (added to .gitignore or not tracked)

**Current local models:**
- `large-v3-turbo/` - Config and tokenizer present
- `medium/` - Config and tokenizer present
- `xtts-v2/` - TTS model (not used in current code)

## Dictionary & Terminology

**Purpose:**
- Improves Whisper transcription accuracy for domain-specific terms
- Passed as `initial_prompt` parameter to transcribe() method

**Location:**
- `dictionary.txt` at project root (line 14 in core/config_manager.py)

**Loading:**
- Read via `ConfigManager.get_initial_prompt()` at line 145-155
- Splits by newlines, filters empty lines, joins as comma-separated string
- Passed to Whisper at line 486 in dictation.pyw

**Format:**
- Plain text, one term per line
- UTF-8 encoded
- Examples: Russian technical terms, proper nouns, domain vocabulary

## System Integration

**Windows API Calls:**
- Via pywin32 (win32gui, win32api, win32con)
- `win32gui.GetForegroundWindow()` - Get active window handle before recording
- `win32gui.SetForegroundWindow()` - Restore focus to target window before paste
- `win32gui.GetWindowRect()` - Get window dimensions for fullscreen detection
- `win32api.MonitorFromWindow()` - Get monitor from window
- `win32api.GetMonitorInfo()` - Get monitor resolution for fullscreen check
- Implementation in `dictation.pyw` lines 68-86, 441, 519

**Clipboard Operations:**
- Copy text via `pyperclip.copy()`
- Paste via `pyautogui.hotkey('ctrl', 'v')`
- Implementation at line 522-524 in dictation.pyw

**Keyboard Hooking:**
- Global hotkey via `keyboard` library
- Hooks all keyboard events at system level
- Callback fired on F9 down/up (line 384 in dictation.pyw)
- Used to detect push-to-talk activation

**Audio Stream:**
- sounddevice InputStream with callback
- Samplerate: 16kHz (Whisper requirement)
- Channels: 1 (mono)
- Buffer: ~100ms blocks (int(16000 * 0.1))
- Implementation at line 365-374 in dictation.pyw

## Voice Activity Detection (VAD)

**Implementation:**
- Whisper's built-in VAD filter enabled during transcribe
- Parameter: `vad_filter=True` at line 473, 485 in dictation.pyw
- Optional config-based thresholds in config.json lines 36-40 (not currently passed to Whisper)

**Current usage:**
- Automatic silence filtering during transcription
- No pre-processing; full audio recorded during F9 press

## State Management

**No external state systems** - Application maintains state in-memory:
- Current widget state (ready, recording, processing, translate)
- Audio buffer during recording
- Loaded model reference
- Configuration (from config.json)

State persisted locally:
- Widget position saved to config.json on drag end
- Recognition settings saved to config.json on change

---

*Integration audit: 2026-02-13*
