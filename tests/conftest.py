"""
Connectify Test Suite — Shared Fixtures (conftest.py)

All tests use these fixtures. Key design decisions:
- `tmp_path` (pytest built-in) is used for all file I/O so nothing touches production user data.
- `CONNECTIFY_USER` env var is used to point the engine at the temp test user.
- Selenium WebDriver is always mocked — no real browser is launched.
- Google Sheets is mocked with an in-memory dict-based worksheet.
"""

import json
import os
import shutil
import threading
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Minimal valid user configs
# ---------------------------------------------------------------------------

LOCAL_USER_CONFIG = {
    "profile": {
        "first_name": "TestLocal",
        "last_name": "User",
        "email": "local@test.com",
        "phone": "9999999999",
        "experience": "3 years",
        "current_location": "Bangalore",
        "preferred_locations": "Bangalore, Remote",
        "linkedin_url": "https://www.linkedin.com/in/testlocal/",
        "resume_name": "TestLocal_Resume.pdf",
        "resume_url": "https://short.ly/testlocal",
        "current_ctc": 10.0,
        "expected_ctc": 15.0,
        "notice_period": "30 Days",
        "last_working_day": "",
    },
    "email_scraper": {
        "interval": "15",
        "review_mode": False,
        "max_emails_per_run": "5",
        "search_keywords": ["Data Engineer", "Senior Data Engineer"],
        "title_keywords": ["Data Engineer"],
        "keywords": ["Data Engineer"],
        "excluded_keywords": ["Open to work"],
        "email_subject": "Data Engineer Application",
        "email_template": "Hi,\n\nI'm applying for {POST_URL}.\n\nRegards,\n{FIRST_NAME} {LAST_NAME}",
        "sender_email": "",
        "filter_experience_enabled": True,
        "filter_experience_ranges": ["fresher", "0-1"],
        "filter_location_enabled": False,
        "filter_locations": [],
        "filter_strict_mode": False,
    },
    "linkedin_connect": {
        "interval": 15,
        "review_mode": False,
        "max_connections_per_company": 3,
        "max_connections_per_run": 5,
        "search_keywords": ["Data Engineer"],
        "title_keywords": ["Data Engineer"],
        "keywords": ["Data Engineer"],
        "excluded_keywords": [],
        "message_template": "Hi {RECEIVER_NAME}, I'm a Data Engineer. Resume: {RESUME}.",
    },
    "recruiter_outreach": {
        "interval": 120,
        "target_count": 2,
        "review_mode": False,
        "message_template": "Hi {RECEIVER_NAME}, I'm looking for Data Engineer roles.",
        "direct_message_template": "Hi! Noticed you're at {COMPANY}. I'm open to Data Engineer roles.",
    },
    "referral_outreach": {
        "message_template": "Hi {RECEIVER_NAME}, saw {COMPANY} has an opening ({JOB_URL}). Would you refer me?\n{FIRST_NAME}",
    },
    "global_settings": {
        "database_type": "local",
        "dry_run": "0",
        "google_credentials_json": "",
        "google_sheet_url": "",
        "linkedin_email": "test@linkedin.com",
        "linkedin_password": "testpassword",
        "max_apply": "5",
        "max_run_duration_seconds": "300",
        "search_location": "Bangalore, Karnataka, India",
        "search_time_range": "r604800",
        "smtp_email": "test@gmail.com",
        "smtp_password": "smtppassword",
        "smtp_port": "587",
        "smtp_server": "smtp.gmail.com",
    },
}

SHEETS_USER_CONFIG = {
    **{k: v for k, v in LOCAL_USER_CONFIG.items() if k != "global_settings"},
    "global_settings": {
        **LOCAL_USER_CONFIG["global_settings"],
        "database_type": "google_sheets",
        "google_sheet_url": "https://docs.google.com/spreadsheets/d/FAKE_ID/edit",
        "google_credentials_json": json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "client_id": "123456",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
    },
}


# ---------------------------------------------------------------------------
# Helper: create a temp user directory with config.json
# ---------------------------------------------------------------------------

def _make_user_dir(tmp_path, username: str, config: dict) -> str:
    """Creates a temporary user directory structure and writes config.json."""
    user_dir = tmp_path / "users" / username
    data_dir = user_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    config_path = user_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return str(user_dir)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def local_user(tmp_path, monkeypatch):
    """
    Provides a LOCAL storage user in a temp directory.
    Sets BASE_DIR to tmp_path so all engine file I/O goes to the temp dir.
    """
    username = "TestUserLocal"
    _make_user_dir(tmp_path, username, LOCAL_USER_CONFIG)

    # Write active_user.json
    users_dir = tmp_path / "users"
    (users_dir / "active_user.json").write_text(
        json.dumps({"selected_user": username}), encoding="utf-8"
    )

    # Point the engine at our temp directory
    monkeypatch.setenv("CONNECTIFY_USER", username)
    monkeypatch.setattr("config.settings.BASE_DIR", str(tmp_path))
    monkeypatch.setattr("core.storage.engine.BASE_DIR", str(tmp_path))

    # Reset StorageManager singleton so it re-reads config
    import core.storage.engine as eng
    eng.StorageManager._instance = None

    yield {"username": username, "config": LOCAL_USER_CONFIG, "base_dir": str(tmp_path)}

    # Cleanup singleton after test
    eng.StorageManager._instance = None


@pytest.fixture
def sheets_user(tmp_path, monkeypatch):
    """
    Provides a GOOGLE SHEETS storage user with a fully mocked gspread backend.
    All worksheet operations go to an in-memory dict store.
    """
    username = "TestUserSheets"
    _make_user_dir(tmp_path, username, SHEETS_USER_CONFIG)

    users_dir = tmp_path / "users"
    (users_dir / "active_user.json").write_text(
        json.dumps({"selected_user": username}), encoding="utf-8"
    )

    monkeypatch.setenv("CONNECTIFY_USER", username)
    monkeypatch.setattr("config.settings.BASE_DIR", str(tmp_path))
    monkeypatch.setattr("core.storage.engine.BASE_DIR", str(tmp_path))

    # In-memory sheet store: { worksheet_name: [row_dict, ...] }
    _sheet_store: dict[str, list] = {}

    def mock_read_rows(url, creds, ws_name):
        return list(_sheet_store.get(ws_name, []))

    def mock_write_rows(url, creds, ws_name, rows):
        _sheet_store[ws_name] = list(rows)

    def mock_append_row(url, creds, ws_name, row):
        _sheet_store.setdefault(ws_name, []).append(dict(row))

    def mock_ensure(url, creds):
        pass

    def mock_cache_invalidate(ws_name):
        pass

    monkeypatch.setattr("core.storage.sheets.read_rows", mock_read_rows)
    monkeypatch.setattr("core.storage.sheets.write_rows", mock_write_rows)
    monkeypatch.setattr("core.storage.sheets.append_row", mock_append_row)
    monkeypatch.setattr("core.storage.sheets.ensure_worksheets_exist", mock_ensure)

    # Patch the dynamic import inside engine.py as well
    import core.storage.engine as eng
    eng.StorageManager._instance = None

    yield {
        "username": username,
        "config": SHEETS_USER_CONFIG,
        "base_dir": str(tmp_path),
        "sheet_store": _sheet_store,
    }

    eng.StorageManager._instance = None


@pytest.fixture
def mock_driver():
    """Returns a MagicMock Selenium WebDriver. No real browser is launched."""
    driver = MagicMock()
    driver.current_url = "https://www.linkedin.com/feed/"
    driver.find_elements.return_value = []
    driver.find_element.return_value = MagicMock()
    driver.page_source = "<html><body>LinkedIn Mock</body></html>"
    return driver


@pytest.fixture
def mock_linkedin_login(mock_driver, monkeypatch):
    """Patches LinkedInScraper.login() to always succeed without a browser."""
    monkeypatch.setattr(
        "pipelines.email_outreach.services.scraper.LinkedInScraper.login",
        lambda self: True,
    )
    monkeypatch.setattr(
        "core.integrations.selenium_driver.get_driver",
        lambda *a, **kw: mock_driver,
    )
    return mock_driver


@pytest.fixture(autouse=True)
def clear_all_caches():
    """Autouse fixture to reset internal storage and sheets cache pools before and after each test."""
    try:
        from core.storage.engine import _clear_all_caches
        _clear_all_caches()
    except ImportError:
        pass
    try:
        from core.storage.sheets import _cache_invalidate_all
        _cache_invalidate_all()
    except ImportError:
        pass
    yield
    try:
        from core.storage.engine import _clear_all_caches
        _clear_all_caches()
    except ImportError:
        pass
    try:
        from core.storage.sheets import _cache_invalidate_all
        _cache_invalidate_all()
    except ImportError:
        pass

