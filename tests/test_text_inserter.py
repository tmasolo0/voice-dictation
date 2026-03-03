"""Tests for TextInserter — гибридная стратегия вставки."""

from unittest.mock import patch, MagicMock, call
from core.text_inserter import TextInserter, insert_text, UNICODE_THRESHOLD


class TestInsertText:
    """Тесты для публичной функции insert_text."""

    @patch("core.text_inserter.send_text_unicode", return_value=True)
    @patch("core.text_inserter.detect_window_type", return_value="normal")
    @patch("core.text_inserter.win32gui")
    def test_short_text_uses_unicode(self, mock_gui, mock_detect, mock_unicode):
        """Короткий текст (<= UNICODE_THRESHOLD) → Unicode SendInput."""
        mock_gui.GetForegroundWindow.return_value = 12345
        short = "Привет"
        assert len(short) <= UNICODE_THRESHOLD
        insert_text(short)
        mock_unicode.assert_called_once_with(short)

    @patch("core.text_inserter._restore_clipboard_delayed")
    @patch("core.text_inserter.send_ctrl_v")
    @patch("core.text_inserter.clipboard_set_verified", return_value=True)
    @patch("core.text_inserter.clipboard_get", return_value="old data")
    @patch("core.text_inserter.detect_window_type", return_value="normal")
    @patch("core.text_inserter.win32gui")
    def test_long_text_uses_clipboard(self, mock_gui, mock_detect, mock_get,
                                       mock_set, mock_ctrl_v, mock_restore):
        """Длинный текст (> UNICODE_THRESHOLD) → clipboard + Ctrl+V."""
        mock_gui.GetForegroundWindow.return_value = 12345
        long_text = "x" * (UNICODE_THRESHOLD + 1)
        insert_text(long_text)
        mock_set.assert_called_once_with(long_text)
        mock_ctrl_v.assert_called_once()
        mock_restore.assert_called_once_with("old data")

    @patch("core.text_inserter._restore_clipboard_delayed")
    @patch("core.text_inserter.send_ctrl_shift_v")
    @patch("core.text_inserter.clipboard_set_verified", return_value=True)
    @patch("core.text_inserter.clipboard_get", return_value=None)
    @patch("core.text_inserter.detect_window_type", return_value="terminal")
    @patch("core.text_inserter.win32gui")
    def test_terminal_uses_ctrl_shift_v(self, mock_gui, mock_detect, mock_get,
                                         mock_set, mock_ctrl_shift_v, mock_restore):
        """Терминал → Ctrl+Shift+V вместо Ctrl+V."""
        mock_gui.GetForegroundWindow.return_value = 12345
        long_text = "x" * (UNICODE_THRESHOLD + 1)
        insert_text(long_text)
        mock_ctrl_shift_v.assert_called_once()
        mock_restore.assert_not_called()  # clipboard был None

    @patch("core.text_inserter._restore_clipboard_delayed")
    @patch("core.text_inserter.send_ctrl_v")
    @patch("core.text_inserter.clipboard_set_verified", return_value=True)
    @patch("core.text_inserter.clipboard_get", return_value=None)
    @patch("core.text_inserter.send_text_unicode", return_value=False)
    @patch("core.text_inserter.detect_window_type", return_value="normal")
    @patch("core.text_inserter.win32gui")
    def test_unicode_failure_falls_back_to_clipboard(self, mock_gui, mock_detect,
                                                      mock_unicode, mock_get,
                                                      mock_set, mock_ctrl_v,
                                                      mock_restore):
        """Unicode fallback: если SendInput не сработал → clipboard."""
        mock_gui.GetForegroundWindow.return_value = 12345
        short = "Привет"
        insert_text(short)
        mock_unicode.assert_called_once_with(short)
        mock_set.assert_called_once_with(short)
        mock_ctrl_v.assert_called_once()


class TestTextInserterClass:
    """Тесты для класса TextInserter (wiring + threading)."""

    def test_on_text_ready_starts_thread(self, mock_bus, mock_config):
        inserter = TextInserter(mock_bus, mock_config)
        inserter._target_window = None

        with patch("core.text_inserter.threading") as mock_threading:
            mock_thread = MagicMock()
            mock_threading.Thread.return_value = mock_thread
            inserter._on_text_ready("текст")
            mock_threading.Thread.assert_called_once()
            mock_thread.start.assert_called_once()
