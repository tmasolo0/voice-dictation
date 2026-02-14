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
_dict_dir = Path(_tmp) / "dictionaries"


@pytest.fixture(autouse=True)
def _patch_paths():
    with patch("core.config_manager.CONFIG_FILE", _config_file), \
         patch("core.config_manager.DICTIONARY_FILE", _dict_file), \
         patch("core.config_manager.DICTIONARIES_DIR", _dict_dir):
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
        assert "kubernetes" in hotwords  # lowercased
        assert "postgresql" in hotwords
        assert "nginx" in hotwords
        assert "," not in hotwords

    def test_empty_dictionary(self):
        _dict_file.unlink(missing_ok=True)
        cfg = _fresh_config()
        assert cfg.get_hotwords() == ""

    def test_domain_dictionaries(self):
        _dict_file.write_text("базовый\n", encoding='utf-8')
        _dict_dir.mkdir(exist_ok=True)
        (_dict_dir / "math.txt").write_text("# Математика\nинтеграл\nградиент\n", encoding='utf-8')

        cfg = _fresh_config()
        cfg.set('dictionaries', 'active', ['math'])
        hotwords = cfg.get_hotwords()
        assert "базовый" in hotwords
        assert "интеграл" in hotwords
        assert "градиент" in hotwords

    def test_domain_deduplication(self):
        _dict_file.write_text("Python\nDocker\n", encoding='utf-8')
        _dict_dir.mkdir(exist_ok=True)
        (_dict_dir / "it.txt").write_text("python\ndocker\nnginx\n", encoding='utf-8')

        cfg = _fresh_config()
        cfg.set('dictionaries', 'active', ['it'])
        hotwords = cfg.get_hotwords()
        # Дедупликация: python и docker не дублируются
        assert hotwords.count("python") == 1
        assert hotwords.count("docker") == 1
        assert "nginx" in hotwords

    def test_missing_domain_no_crash(self):
        _dict_file.write_text("базовый\n", encoding='utf-8')
        cfg = _fresh_config()
        cfg.set('dictionaries', 'active', ['nonexistent'])
        hotwords = cfg.get_hotwords()
        assert "базовый" in hotwords  # base всё ещё загружается
