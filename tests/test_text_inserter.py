"""Tests for TextInserter — clipboard save/restore."""

from unittest.mock import patch, MagicMock, call
from core.text_inserter import TextInserter


class TestClipboardSafety:
    def test_clipboard_restored_after_insert(self, mock_bus, mock_config):
        inserter = TextInserter(mock_bus, mock_config)
        inserter._target_window = None  # skip SetForegroundWindow

        with patch("core.text_inserter.pyperclip") as mock_clip, \
             patch("core.text_inserter.pyautogui"), \
             patch("core.text_inserter.time"):
            mock_clip.paste.return_value = "old clipboard"
            inserter._on_text_ready("новый текст")

            # pyperclip.copy вызван дважды: текст + восстановление
            calls = mock_clip.copy.call_args_list
            assert calls[0] == call("новый текст")
            assert calls[1] == call("old clipboard")

    def test_clipboard_restored_on_error(self, mock_bus, mock_config):
        inserter = TextInserter(mock_bus, mock_config)
        inserter._target_window = None

        with patch("core.text_inserter.pyperclip") as mock_clip, \
             patch("core.text_inserter.pyautogui") as mock_auto, \
             patch("core.text_inserter.time"):
            mock_clip.paste.return_value = "saved"
            mock_auto.hotkey.side_effect = Exception("paste failed")

            inserter._on_text_ready("текст")

            # Clipboard всё равно восстановлен (finally)
            last_copy = mock_clip.copy.call_args_list[-1]
            assert last_copy == call("saved")

    def test_emit_text_inserted_on_success(self, mock_bus, mock_config):
        inserter = TextInserter(mock_bus, mock_config)
        inserter._target_window = None

        with patch("core.text_inserter.pyperclip"), \
             patch("core.text_inserter.pyautogui"), \
             patch("core.text_inserter.time"):
            inserter._on_text_ready("текст")
            mock_bus.text_inserted.emit.assert_called_once()
