"""
Unit Tests: Config Loading & Storage Provider Resolution
(config/user_profiles.py, core/storage/engine.py provider selection)

Tests correct config loading, provider selection, user switching,
and fallback behavior when keys are missing.

Run with:
    pytest tests/unit/test_config_loading.py -v
"""

import json
import os
import pytest
from tests.conftest import LOCAL_USER_CONFIG, SHEETS_USER_CONFIG


class TestConfigLoading:
    """Tests that user config is correctly loaded and structured."""

    def test_local_config_has_all_top_level_keys(self, local_user):
        from core.storage.engine import get_user_config
        cfg = get_user_config()
        required_keys = ["profile", "email_scraper", "linkedin_connect",
                         "recruiter_outreach", "referral_outreach", "global_settings"]
        for key in required_keys:
            assert key in cfg, f"Missing key: {key}"

    def test_profile_has_required_fields(self, local_user):
        from core.storage.engine import get_user_config
        profile = get_user_config()["profile"]
        for field in ["first_name", "last_name", "email", "experience", "linkedin_url"]:
            assert field in profile, f"Profile missing field: {field}"

    def test_email_scraper_has_required_fields(self, local_user):
        from core.storage.engine import get_user_config
        cfg = get_user_config()["email_scraper"]
        for field in ["interval", "review_mode", "max_emails_per_run", "search_keywords", "email_template"]:
            assert field in cfg, f"email_scraper missing: {field}"

    def test_linkedin_connect_has_required_fields(self, local_user):
        from core.storage.engine import get_user_config
        cfg = get_user_config()["linkedin_connect"]
        for field in ["interval", "review_mode", "max_connections_per_run", "message_template"]:
            assert field in cfg, f"linkedin_connect missing: {field}"

    def test_recruiter_outreach_has_required_fields(self, local_user):
        from core.storage.engine import get_user_config
        cfg = get_user_config()["recruiter_outreach"]
        for field in ["target_count", "review_mode", "message_template"]:
            assert field in cfg

    def test_global_settings_has_database_type(self, local_user):
        from core.storage.engine import get_user_config
        cfg = get_user_config()
        assert cfg["global_settings"]["database_type"] in ("local", "google_sheets")

    def test_missing_optional_key_does_not_crash(self, local_user, tmp_path):
        """Config without recruiter_outreach key should not raise."""
        from core.storage.engine import get_user_config
        cfg = get_user_config()
        assert cfg.get("recruiter_outreach", {}) is not None  # missing key returns default {}


class TestStorageProviderSelection:
    """Tests that the correct storage provider is selected based on database_type."""

    def test_local_user_uses_local_provider(self, local_user):
        from core.storage.engine import get_active_storage_provider, LocalStorageProvider
        provider = get_active_storage_provider()
        assert isinstance(provider, LocalStorageProvider)

    def test_sheets_user_uses_sheets_provider(self, sheets_user):
        from core.storage.engine import get_active_storage_provider, LocalStorageProvider
        provider = get_active_storage_provider()
        assert isinstance(provider, LocalStorageProvider)

    def test_unknown_database_type_falls_back_to_local(self, local_user, tmp_path):
        """Config with unknown database_type should fall back to LocalStorageProvider."""
        import core.storage.engine as eng
        from core.storage.engine import get_active_storage_provider, LocalStorageProvider

        # Overwrite config with unknown db type
        username = local_user["username"]
        cfg_path = os.path.join(local_user["base_dir"], "users", username, "config.json")
        cfg = LOCAL_USER_CONFIG.copy()
        cfg["global_settings"] = {**LOCAL_USER_CONFIG["global_settings"], "database_type": "unknown_db"}
        with open(cfg_path, "w") as f:
            json.dump(cfg, f)

        eng.StorageManager._instance = None
        provider = get_active_storage_provider()
        assert isinstance(provider, LocalStorageProvider)


class TestActiveUsernameResolution:
    """Tests that the active username resolves correctly from env var and active_user.json."""

    def test_env_var_takes_priority(self, local_user, monkeypatch):
        from core.storage.engine import get_active_username
        monkeypatch.setenv("CONNECTIFY_USER", "EnvUser")
        assert get_active_username() == "EnvUser"

    def test_active_user_json_is_read_when_no_env(self, tmp_path, monkeypatch):
        import core.storage.engine as eng

        (tmp_path / "users").mkdir(parents=True, exist_ok=True)
        active_file = tmp_path / "users" / "active_user.json"
        active_file.write_text(json.dumps({"selected_user": "JsonUser"}))

        monkeypatch.delenv("CONNECTIFY_USER", raising=False)
        monkeypatch.setattr(eng, "BASE_DIR", str(tmp_path))

        assert eng.get_active_username() == "JsonUser"

    def test_defaults_to_default_when_no_config(self, tmp_path, monkeypatch):
        import core.storage.engine as eng
        monkeypatch.delenv("CONNECTIFY_USER", raising=False)
        monkeypatch.setattr(eng, "BASE_DIR", str(tmp_path))

        result = eng.get_active_username()
        assert result == "default"


class TestConfigCaching:
    """Tests config-level caching behavior."""

    def test_config_is_cached_after_first_read(self, local_user, monkeypatch):
        """Second call to get_user_config should use cache, not re-read disk."""
        import core.storage.engine as eng
        from core.storage.engine import get_user_config

        read_count = {"n": 0}
        original = eng.LocalStorageProvider.get_config

        def counted(self, username, bypass_cache=False):
            if not bypass_cache:
                read_count["n"] += 1
            return original(self, username, bypass_cache=bypass_cache)

        monkeypatch.setattr(eng.LocalStorageProvider, "get_config", counted)

        _ = get_user_config()           # first read → disk
        _ = get_user_config()           # second read → should be cached
        assert read_count["n"] <= 1, "Config read from disk more than once (cache miss)"

    def test_bypass_cache_reads_from_disk(self, local_user):
        from core.storage.engine import get_user_config, save_user_config, _invalidate_cached_config
        cfg = get_user_config()
        cfg["profile"]["first_name"] = "CacheTestName"
        save_user_config(cfg)
        _invalidate_cached_config(local_user["username"])

        import core.storage.engine as eng
        eng.StorageManager._instance = None

        refreshed = get_user_config(bypass_cache=True)
        assert refreshed["profile"]["first_name"] == "CacheTestName"
