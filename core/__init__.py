"""Core модули Voice Input."""
from .config_manager import config, ConfigManager, CONFIG_FILE, DEFAULT_CONFIG, PROJECT_ROOT
from .recognizer import SpeechRecognizer
from .hotkeys import HotkeyManager, get_hotkey_manager
from .tray import SystemTray

__all__ = [
    'config',
    'ConfigManager',
    'CONFIG_FILE',
    'DEFAULT_CONFIG',
    'PROJECT_ROOT',
    'SpeechRecognizer',
    'HotkeyManager',
    'get_hotkey_manager',
    'SystemTray',
]
