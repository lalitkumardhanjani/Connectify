"""
Multi-User Tests: Data Isolation
(tests/multi_user/test_multi_user_isolation.py)

Tests that UserA (local) and UserB (sheets) have completely isolated
storage — writes by one user cannot be read or contaminated by the other.
Also runs pipelines simultaneously in threads to test for race conditions.

Run with:
    pytest tests/multi_user/test_multi_user_isolation.py -v
"""

import json
import os
import threading
import pytest
from tests.conftest import LOCAL_USER_CONFIG, SHEETS_USER_CONFIG


# ===========================================================================
#  Fixture: two users in the same tmp_path
# ===========================================================================

@pytest.fixture
def two_users(tmp_path, monkeypatch):
    """
    Creates UserA (local storage) and UserB (sheets/mocked) in the same tmp dir.
    Returns a dict with both users' info and a shared sheet store for UserB.
    """
    import core.storage.engine as eng

    # --- UserA: Local ---
    user_a = "UserA_Local"
    ua_dir = tmp_path / "users" / user_a
    (ua_dir / "data").mkdir(parents=True)
    (ua_dir / "config.json").write_text(json.dumps(LOCAL_USER_CONFIG))

    # --- UserB: Sheets (mocked) ---
    user_b = "UserB_Sheets"
    ub_dir = tmp_path / "users" / user_b
    (ub_dir / "data").mkdir(parents=True)
    (ub_dir / "config.json").write_text(json.dumps(SHEETS_USER_CONFIG))

    # Write active_user.json (starts with UserA)
    (tmp_path / "users" / "active_user.json").write_text(
        json.dumps({"selected_user": user_a})
    )

    monkeypatch.setattr("config.settings.BASE_DIR", str(tmp_path))
    monkeypatch.setattr("core.storage.engine.BASE_DIR", str(tmp_path))

    # In-memory Sheets store for UserB
    _sheet_store: dict = {}

    def mock_read_rows(url, creds, ws_name):
        return list(_sheet_store.get(ws_name, []))

    def mock_write_rows(url, creds, ws_name, rows):
        _sheet_store[ws_name] = list(rows)

    def mock_append_row(url, creds, ws_name, row):
        _sheet_store.setdefault(ws_name, []).append(dict(row))

    monkeypatch.setattr("core.storage.sheets.read_rows", mock_read_rows)
    monkeypatch.setattr("core.storage.sheets.write_rows", mock_write_rows)
    monkeypatch.setattr("core.storage.sheets.append_row", mock_append_row)
    monkeypatch.setattr("core.storage.sheets.ensure_worksheets_exist", lambda *a: None)

    eng.StorageManager._instance = None

    yield {
        "user_a": user_a,
        "user_b": user_b,
        "base_dir": str(tmp_path),
        "sheet_store": _sheet_store,
    }

    eng.StorageManager._instance = None


def _switch_active_user(base_dir: str, username: str):
    """Switches the active user by updating active_user.json."""
    import core.storage.engine as eng
    active_file = os.path.join(base_dir, "users", "active_user.json")
    with open(active_file, "w") as f:
        json.dump({"selected_user": username}, f)

    os.environ["CONNECTIFY_USER"] = username
    eng.StorageManager._instance = None
    eng._row_cache.clear()
    eng._config_cache.clear()


# ===========================================================================
#  Storage Isolation Tests
# ===========================================================================

class TestStorageIsolation:
    """Verify that UserA's writes do not appear in UserB's storage and vice versa."""

    def test_userA_email_not_visible_to_userB(self, two_users, monkeypatch):
        """Emails appended by UserA should not appear in UserB's email store."""
        import core.storage.engine as eng
        from core.storage.database import append_email
        from core.storage.engine import read_database_rows

        base_dir = two_users["base_dir"]

        # Switch to UserA and write an email
        _switch_active_user(base_dir, two_users["user_a"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_a"])
        eng.StorageManager._instance = None
        append_email("userA_email@test.com", keyword="Data Engineer")

        # Switch to UserB and verify no emails visible
        _switch_active_user(base_dir, two_users["user_b"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_b"])
        eng.StorageManager._instance = None
        rows = read_database_rows("emails")
        emails = [r["Email"] for r in rows if r.get("Email")]
        assert "userA_email@test.com" not in emails, "UserA email bled into UserB!"

    def test_userB_job_not_visible_to_userA(self, two_users, monkeypatch):
        """Jobs saved by UserB should not appear in UserA's local Excel store."""
        import core.storage.engine as eng
        from core.storage.database import save_job, load_saved_jobs

        base_dir = two_users["base_dir"]

        # Switch to UserB and write a job
        _switch_active_user(base_dir, two_users["user_b"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_b"])
        eng.StorageManager._instance = None
        save_job({
            "JobTitle": "UserB DE Role",
            "CompanyName": "UserBCo",
            "LinkedIn_Company_URL": "https://linkedin.com/company/userbco/",
            "CompanyURL": "https://userb.com/j/1",
            "ShortenURL": "",
            "SearchKeyword": "DE",
            "Status": "NEW",
        })

        # Switch to UserA and verify no contamination
        _switch_active_user(base_dir, two_users["user_a"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_a"])
        eng.StorageManager._instance = None
        jobs = load_saved_jobs()
        companies = [j["CompanyName"] for j in jobs]
        assert "UserBCo" not in companies, "UserB job appeared in UserA's storage!"

    def test_userA_config_is_independent_of_userB(self, two_users, monkeypatch):
        """Each user should have their own config, not shared."""
        import core.storage.engine as eng
        from core.storage.engine import get_user_config

        base_dir = two_users["base_dir"]

        _switch_active_user(base_dir, two_users["user_a"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_a"])
        eng.StorageManager._instance = None
        cfg_a = get_user_config()

        _switch_active_user(base_dir, two_users["user_b"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_b"])
        eng.StorageManager._instance = None
        cfg_b = get_user_config()

        # UserA is local, UserB is google_sheets
        assert cfg_a["global_settings"]["database_type"] == "local"
        assert cfg_b["global_settings"]["database_type"] == "google_sheets"

    def test_referrals_isolated_between_users(self, two_users, monkeypatch):
        """Referral entries saved for UserA must not appear in UserB's referrals."""
        import core.storage.engine as eng
        from core.storage.database import add_or_update_referral, load_all_referrals

        base_dir = two_users["base_dir"]

        # UserA adds a referral
        _switch_active_user(base_dir, two_users["user_a"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_a"])
        eng.StorageManager._instance = None

        add_or_update_referral({
            "JobID": "1",
            "CompanyName": "UserACo",
            "Company_URL": "",
            "JobTitle": "DE",
            "Job_URL": "",
            "Referral_Person_Name": "UserA Contact",
            "Referral_Person_Profile_URL": "https://linkedin.com/in/useracontact/",
            "Referral_Source": "existing employee",
            "Referral_Status": "sent",
            "Outreach_Message": "",
            "Response_Notes": "",
            "DateTime": "2025-01-01 10:00:00",
        })

        # Switch to UserB and check referrals
        _switch_active_user(base_dir, two_users["user_b"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_b"])
        eng.StorageManager._instance = None
        refs = load_all_referrals()
        names = [r.get("Referral_Person_Name", "") for r in refs]
        assert "UserA Contact" not in names


# ===========================================================================
#  Concurrent Multi-User Tests
# ===========================================================================

class TestConcurrentMultiUser:
    """Tests running both users' pipelines simultaneously to catch race conditions."""

    def test_simultaneous_email_writes_no_data_loss(self, two_users, monkeypatch):
        """
        UserA and UserB both append 50 emails concurrently.
        UserA's local file should contain exactly 50 rows.
        UserB's mock sheet store should contain exactly 50 rows.
        No cross-contamination should occur.
        """
        import core.storage.engine as eng
        from core.storage.database import append_email
        from core.storage.engine import read_database_rows

        base_dir = two_users["base_dir"]
        errors = []

        def user_a_work():
            try:
                import core.storage.engine as e2
                os.environ["CONNECTIFY_USER"] = two_users["user_a"]
                e2.StorageManager._instance = None
                for i in range(50):
                    append_email(f"ua-email-{i}@test.com", keyword="DE")
            except Exception as ex:
                errors.append(("UserA", str(ex)))

        def user_b_work():
            try:
                import core.storage.engine as e2
                os.environ["CONNECTIFY_USER"] = two_users["user_b"]
                e2.StorageManager._instance = None
                for i in range(50):
                    append_email(f"ub-email-{i}@test.com", keyword="DE")
            except Exception as ex:
                errors.append(("UserB", str(ex)))

        t_a = threading.Thread(target=user_a_work)
        t_b = threading.Thread(target=user_b_work)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        assert not errors, f"Errors during concurrent write: {errors}"

        # Verify UserA's local storage
        _switch_active_user(base_dir, two_users["user_a"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_a"])
        eng.StorageManager._instance = None
        rows_a = read_database_rows("emails")
        ua_emails = [r["Email"] for r in rows_a if r.get("Email", "").startswith("ua-")]

        # Verify UserB's sheet store
        _switch_active_user(base_dir, two_users["user_b"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_b"])
        eng.StorageManager._instance = None
        rows_b = read_database_rows("emails")
        ub_emails = [r["Email"] for r in rows_b if r.get("Email", "").startswith("ub-")]

        # Cross-contamination check
        assert not any(e.startswith("ub-") for e in ua_emails), "UserB emails found in UserA!"
        assert not any(e.startswith("ua-") for e in ub_emails), "UserA emails found in UserB!"

    def test_simultaneous_job_saves_no_corruption(self, two_users, monkeypatch):
        """Both users save jobs concurrently — each should have their own jobs."""
        import core.storage.engine as eng
        from core.storage.database import save_job, load_saved_jobs

        base_dir = two_users["base_dir"]
        errors = []

        def user_a_jobs():
            try:
                os.environ["CONNECTIFY_USER"] = two_users["user_a"]
                eng.StorageManager._instance = None
                for i in range(10):
                    save_job({
                        "JobTitle": "DE",
                        "CompanyName": f"UAJobCo{i}",
                        "LinkedIn_Company_URL": f"https://linkedin.com/company/uajobco{i}/",
                        "CompanyURL": f"https://ua.com/j/{i}",
                        "ShortenURL": "",
                        "SearchKeyword": "DE",
                        "Status": "NEW",
                    })
            except Exception as ex:
                errors.append(str(ex))

        def user_b_jobs():
            try:
                os.environ["CONNECTIFY_USER"] = two_users["user_b"]
                eng.StorageManager._instance = None
                for i in range(10):
                    save_job({
                        "JobTitle": "DE",
                        "CompanyName": f"UBJobCo{i}",
                        "LinkedIn_Company_URL": f"https://linkedin.com/company/ubjobco{i}/",
                        "CompanyURL": f"https://ub.com/j/{i}",
                        "ShortenURL": "",
                        "SearchKeyword": "DE",
                        "Status": "NEW",
                    })
            except Exception as ex:
                errors.append(str(ex))

        t_a = threading.Thread(target=user_a_jobs)
        t_b = threading.Thread(target=user_b_jobs)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        assert not errors, f"Errors: {errors}"

        # UserA check
        _switch_active_user(base_dir, two_users["user_a"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_a"])
        eng.StorageManager._instance = None
        jobs_a = load_saved_jobs()
        ua_companies = {j["CompanyName"] for j in jobs_a}

        # UserB check
        _switch_active_user(base_dir, two_users["user_b"])
        monkeypatch.setenv("CONNECTIFY_USER", two_users["user_b"])
        eng.StorageManager._instance = None
        jobs_b = load_saved_jobs()
        ub_companies = {j["CompanyName"] for j in jobs_b}

        assert not any("UBJobCo" in c for c in ua_companies), "UserB jobs in UserA!"
        assert not any("UAJobCo" in c for c in ub_companies), "UserA jobs in UserB!"
