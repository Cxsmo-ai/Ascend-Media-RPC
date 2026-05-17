import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config import DEFAULT_CONFIG, load_config, save_config, validate_config, export_config, import_config, _apply_env_overrides


class TestConfig:
    def test_default_config_has_all_sections(self):
        assert "adb_host" in DEFAULT_CONFIG
        assert "discord_client_id" in DEFAULT_CONFIG
        assert "skip_mode" in DEFAULT_CONFIG
        assert "artwork_provider" in DEFAULT_CONFIG
        assert "privacy_mode" in DEFAULT_CONFIG
        assert "theme_mode" in DEFAULT_CONFIG
        assert "fanart_api_key" in DEFAULT_CONFIG

    def test_validate_config_valid(self):
        config = DEFAULT_CONFIG.copy()
        warnings = validate_config(config)
        assert isinstance(warnings, list)

    def test_validate_config_bad_port(self):
        config = DEFAULT_CONFIG.copy()
        config["dashboard_port"] = 80
        warnings = validate_config(config)
        assert any("dashboard_port" in w for w in warnings)

    def test_export_config_hides_secrets(self):
        config = DEFAULT_CONFIG.copy()
        config["trakt_access_token"] = "secret123"
        exported = json.loads(export_config(config))
        assert "trakt_access_token" not in exported

    def test_import_config_merges(self):
        current = DEFAULT_CONFIG.copy()
        imported_json = json.dumps({"adb_host": "192.168.1.100"})
        merged = import_config(imported_json, current)
        assert merged["adb_host"] == "192.168.1.100"
        assert merged["discord_client_id"] == DEFAULT_CONFIG["discord_client_id"]

    def test_skip_category_toggles_exist(self):
        assert "skip_cat_intro" in DEFAULT_CONFIG
        assert "skip_cat_outro" in DEFAULT_CONFIG
        assert "skip_cat_mature" in DEFAULT_CONFIG
        assert "skip_cat_scare" in DEFAULT_CONFIG

    def test_container_environment_overrides(self, monkeypatch):
        monkeypatch.setenv("ADB_HOST", "100.64.0.10")
        monkeypatch.setenv("DASHBOARD_PORT", "7777")
        monkeypatch.setenv("TMDB_API_KEY", "tmdb-live-key")
        config = _apply_env_overrides(DEFAULT_CONFIG.copy())
        assert config["adb_host"] == "100.64.0.10"
        assert config["dashboard_port"] == 7777
        assert config["tmdb_api_key"] == "tmdb-live-key"
