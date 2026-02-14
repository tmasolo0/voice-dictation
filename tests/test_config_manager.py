"""Tests for ConfigManager."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Patch paths before import
_tmp = tempfile.mkdtemp()
_config_file = Path(_tmp) / "config.json"
_dict_file = Path(_tmp) / "dictionary.txt"


@pytest.fixture(autouse=True)
def _patch_paths():
    with patch("core.config_manager.CONFIG_FILE", _config_file), \
         patch("core.config_manager.DICTIONARY_FILE", _dict_file):
        # Reset singleton for each test
        from core.config_manager import ConfigManager
        ConfigManager._instance = None
        yield


def _fresh_config():
    from core.config_manager import ConfigManager
    ConfigManager._instance = None
    return ConfigManager()


class TestConfigRead:
    def test_default_values(self):
        _config_file.unlink(missing_ok=True)
        cfg = _fresh_config()
        assert cfg.get('recognition', 'hotkey', default='f9') == 'f9'
        assert cfg.get('widget', 'size', default=100) is not None

    def test_read_saved_value(self):
        _config_file.write_text(json.dumps({
            "version": 2,
            "recognition": {"hotkey": "f8"}
        }))
        cfg = _fresh_config()
        assert cfg.get('recognition', 'hotkey') == 'f8'

    def test_missing_key_returns_default(self):
        _config_file.unlink(missing_ok=True)
        cfg = _fresh_config()
        assert cfg.get('nonexistent', 'key', default='fallback') == 'fallback'


class TestConfigWrite:
    def test_set_and_save(self):
        _config_file.unlink(missing_ok=True)
        cfg = _fresh_config()
        cfg.set('recognition', 'hotkey', 'f8')
        cfg.save()

        data = json.loads(_config_file.read_text())
        assert data['recognition']['hotkey'] == 'f8'

    def test_nested_set(self):
        _config_file.unlink(missing_ok=True)
        cfg = _fresh_config()
        cfg.set('widget', 'position', 'x', 42)
        assert cfg.get('widget', 'position', 'x') == 42


class TestConfigMigration:
    def test_migrate_old_format(self):
        _config_file.write_text(json.dumps({
            "window_x": 100, "window_y": 200
        }))
        cfg = _fresh_config()
        assert cfg.get('widget', 'position', 'x') == 100
        assert cfg.get('widget', 'position', 'y') == 200


class TestDictionary:
    def test_get_hotwords(self):
        _dict_file.write_text("Kubernetes\nPostgreSQL\nnginx\n", encoding='utf-8')
        cfg = _fresh_config()
        hotwords = cfg.get_hotwords()
        assert "Kubernetes" in hotwords
        assert "PostgreSQL" in hotwords
        assert "nginx" in hotwords
        # hotwords — пробел-разделённые
        assert "," not in hotwords

    def test_empty_dictionary(self):
        _dict_file.unlink(missing_ok=True)
        cfg = _fresh_config()
        assert cfg.get_hotwords() == ""
