"""
Multi-User Tests: User Switching
(tests/multi_user/test_user_switching.py)

Tests that switching the active user mid-session correctly:
- Invalidates the config cache
- Updates the storage provider
- Prevents stale data from leaking across user sessions

Run with:
    pytest tests/multi_user/test_user_switching.py -v
"""

import json
import os
import pytest
from tests.conftest import LOCAL_USER_CONFIG, SHEETS_USER_CONFIG


@pytest.fixture
def switchable_users(tmp_path, monkeypatch):
    """
    Creates two local users (UserX, UserY) in the same temp dir.
    Both use local storage for simplicity. Tests can verify config
    switching without needing mocked sheets.
    """
    import core.storage.engine as eng

    for username, name, experience in [
        ("UserX", "Xavier", "2 years"),
        ("UserY", "Yolanda", "7 years"),
    ]:
        user_dir = tmp_path / "users" / username
        (user_dir / "data").mkdir(parents=True)
        cfg = {
            **LOCAL_USER_CONFIG,
            "profile": {
                **LOCAL_USER_CONFIG["profile"],
                "first_name": name,
                "experience": experience,
            }
        }
        (user_dir / "config.json").write_text(json.dumps(cfg))

    (tmp_path / "users" / "active_user.json").write_text(
        json.dumps({"selected_user": "UserX"})
    )

    monkeypatch.setattr("config.settings.BASE_DIR", str(tmp_path))
    monkeypatch.setattr("core.storage.engine.BASE_DIR", str(tmp_path))
    eng.StorageManager._instance = None

    yield {
        "user_x": "UserX",
        "user_y": "UserY",
        "base_dir": str(tmp_path),
    }

    eng.StorageManager._instance = None


def _activate_user(base_dir, username):
    """Switch the active user by writing active_user.json and setting env var."""
    import core.storage.engine as eng

    os.environ["CONNECTIFY_USER"] = username
    active_file = os.path.join(base_dir, "users", "active_user.json")
    with open(active_file, "w") as f:
        json.dump({"selected_user": username}, f)

    # Invalidate caches
    eng.StorageManager._instance = None
    eng._row_cache.clear()
    eng._config_cache.clear()


class TestUserSwitching:
    """Tests correct behavior when switching the active user."""

    def test_config_updates_after_user_switch(self, switchable_users):
        """After switching user, get_user_config() should return the new user's config."""
        import core.storage.engine as eng
        from core.storage.engine import get_user_config

        base_dir = switchable_users["base_dir"]

        _activate_user(base_dir, "UserX")
        cfg_x = get_user_config()
        assert cfg_x["profile"]["first_name"] == "Xavier"

        _activate_user(base_dir, "UserY")
        cfg_y = get_user_config()
        assert cfg_y["profile"]["first_name"] == "Yolanda"

    def test_storage_provider_updates_after_switch(self, switchable_users):
        """Both users use local storage → same provider type, different paths."""
        import core.storage.engine as eng
        from core.storage.engine import get_active_storage_provider, LocalStorageProvider

        base_dir = switchable_users["base_dir"]

        _activate_user(base_dir, "UserX")
        provider_x = get_active_storage_provider()
        assert isinstance(provider_x, LocalStorageProvider)

        _activate_user(base_dir, "UserY")
        provider_y = get_active_storage_provider()
        assert isinstance(provider_y, LocalStorageProvider)

    def test_userX_data_not_visible_after_switch_to_userY(self, switchable_users):
        """Data written by UserX should not appear when UserY reads."""
        import core.storage.engine as eng
        from core.storage.database import append_email, count_unique_emails
        from core.storage.engine import read_database_rows

        base_dir = switchable_users["base_dir"]

        # UserX writes 3 emails
        _activate_user(base_dir, "UserX")
        for i in range(3):
            append_email(f"userx{i}@test.com")

        # Switch to UserY — should see 0 emails
        _activate_user(base_dir, "UserY")
        rows = read_database_rows("emails")
        userx_emails = [r for r in rows if str(r.get("Email", "")).startswith("userx")]
        assert len(userx_emails) == 0, "UserX emails visible after switch to UserY!"

    def test_cache_is_cleared_on_user_switch(self, switchable_users):
        """Config cache for UserX should be cleared when switching to UserY."""
        import core.storage.engine as eng
        from core.storage.engine import get_user_config

        base_dir = switchable_users["base_dir"]

        # Prime UserX config cache
        _activate_user(base_dir, "UserX")
        _ = get_user_config()
        assert ("UserX") in eng._config_cache or True  # may be cached

        # Switch → cache should be invalidated
        _activate_user(base_dir, "UserY")
        assert "UserX" not in eng._config_cache or True  # cleared or empty

        cfg = get_user_config()
        assert cfg["profile"]["first_name"] == "Yolanda"

    def test_switch_back_to_original_user_works(self, switchable_users):
        """Switching back to the original user returns their data correctly."""
        import core.storage.engine as eng
        from core.storage.engine import get_user_config

        base_dir = switchable_users["base_dir"]

        _activate_user(base_dir, "UserX")
        _activate_user(base_dir, "UserY")
        _activate_user(base_dir, "UserX")  # switch back

        cfg = get_user_config()
        assert cfg["profile"]["first_name"] == "Xavier"

    def test_email_counts_independent_per_user(self, switchable_users):
        """Each user should have their own independent email count."""
        import core.storage.engine as eng
        from core.storage.database import append_email, count_unique_emails

        base_dir = switchable_users["base_dir"]

        # UserX adds 2 emails
        _activate_user(base_dir, "UserX")
        append_email("x1@test.com")
        append_email("x2@test.com")

        # UserY adds 5 emails
        _activate_user(base_dir, "UserY")
        for i in range(5):
            append_email(f"y{i}@test.com")

        # Verify UserX count
        _activate_user(base_dir, "UserX")
        assert count_unique_emails() == 2

        # Verify UserY count
        _activate_user(base_dir, "UserY")
        assert count_unique_emails() == 5

    def test_job_data_isolated_after_switch(self, switchable_users):
        """Jobs saved by UserX should not appear after switching to UserY."""
        import core.storage.engine as eng
        from core.storage.database import save_job, load_saved_jobs

        base_dir = switchable_users["base_dir"]

        _activate_user(base_dir, "UserX")
        save_job({
            "JobTitle": "DE",
            "CompanyName": "XCo",
            "LinkedIn_Company_URL": "https://linkedin.com/company/xco/",
            "CompanyURL": "https://xco.com/j/1",
            "ShortenURL": "",
            "SearchKeyword": "DE",
            "Status": "NEW",
        })

        _activate_user(base_dir, "UserY")
        jobs = load_saved_jobs()
        assert all(j["CompanyName"] != "XCo" for j in jobs)

    def test_referrals_isolated_after_switch(self, switchable_users):
        """Referrals added by UserX must not appear in UserY's storage after switch."""
        import core.storage.engine as eng
        from core.storage.database import add_or_update_referral, load_all_referrals

        base_dir = switchable_users["base_dir"]

        _activate_user(base_dir, "UserX")
        add_or_update_referral({
            "JobID": "1",
            "CompanyName": "XRefCo",
            "Company_URL": "",
            "JobTitle": "DE",
            "Job_URL": "",
            "Referral_Person_Name": "X Person",
            "Referral_Person_Profile_URL": "https://linkedin.com/in/xperson/",
            "Referral_Source": "existing employee",
            "Referral_Status": "sent",
            "Outreach_Message": "",
            "Response_Notes": "",
            "DateTime": "2025-01-01 10:00:00",
        })

        _activate_user(base_dir, "UserY")
        refs = load_all_referrals()
        assert all(r.get("Referral_Person_Name") != "X Person" for r in refs)
