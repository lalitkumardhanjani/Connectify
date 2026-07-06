"""
Unit Tests: Storage Engine (core/storage/engine.py)

Tests the LocalStorageProvider and GoogleSheetsStorageProvider (mocked)
for correct read/write/append behavior, caching, and cache invalidation.

Run with:
    pytest tests/unit/test_storage_engine.py -v
"""

import json
import pytest
from tests.fixtures.sample_data import SAMPLE_EMAILS, SAMPLE_JOBS, SAMPLE_REFERRALS


# ===========================================================================
#  LOCAL STORAGE PROVIDER TESTS
# ===========================================================================

class TestLocalStorageRead:
    """Tests for reading from local Excel files."""

    def test_read_empty_emails_table_returns_empty_list(self, local_user):
        """Reading emails from a new user dir (no Excel) returns []."""
        from core.storage.engine import read_database_rows
        rows = read_database_rows("emails")
        assert rows == [], f"Expected [], got {rows}"

    def test_read_empty_jobs_table_returns_empty_list(self, local_user):
        from core.storage.engine import read_database_rows
        rows = read_database_rows("jobs")
        assert rows == []

    def test_read_empty_referrals_table_returns_empty_list(self, local_user):
        from core.storage.engine import read_database_rows
        rows = read_database_rows("referrals")
        assert rows == []

    def test_read_after_write_returns_correct_data(self, local_user):
        """write then read should return identical rows."""
        from core.storage.engine import read_database_rows, write_database_rows
        write_database_rows("emails", SAMPLE_EMAILS)
        rows = read_database_rows("emails")
        assert len(rows) == len(SAMPLE_EMAILS)
        assert rows[0]["Email"] == SAMPLE_EMAILS[0]["Email"]

    def test_read_jobs_after_write(self, local_user):
        from core.storage.engine import read_database_rows, write_database_rows
        write_database_rows("jobs", SAMPLE_JOBS)
        rows = read_database_rows("jobs")
        assert len(rows) == len(SAMPLE_JOBS)
        assert rows[1]["CompanyName"] == "DataViz"

    def test_read_referrals_after_write(self, local_user):
        from core.storage.engine import read_database_rows, write_database_rows
        write_database_rows("referrals", SAMPLE_REFERRALS)
        rows = read_database_rows("referrals")
        assert len(rows) == len(SAMPLE_REFERRALS)

    def test_invalid_table_key_raises(self, local_user):
        from core.storage.engine import LocalStorageProvider
        provider = LocalStorageProvider()
        with pytest.raises(ValueError):
            provider.get_excel_path(local_user["username"], "nonexistent_table")


class TestLocalStorageAppend:
    """Tests for appending rows to local Excel files."""

    def test_append_creates_file_if_not_present(self, local_user):
        from core.storage.engine import append_database_row, read_database_rows
        row = SAMPLE_EMAILS[0]
        append_database_row("emails", row)
        rows = read_database_rows("emails")
        assert len(rows) == 1
        assert rows[0]["Email"] == row["Email"]

    def test_append_multiple_rows(self, local_user):
        from core.storage.engine import append_database_row, read_database_rows
        for r in SAMPLE_EMAILS[:3]:
            append_database_row("emails", r)
        rows = read_database_rows("emails")
        assert len(rows) == 3

    def test_append_to_existing_file_preserves_prior_rows(self, local_user):
        from core.storage.engine import write_database_rows, append_database_row, read_database_rows
        write_database_rows("emails", SAMPLE_EMAILS[:2])
        new_row = SAMPLE_EMAILS[2]
        append_database_row("emails", new_row)
        rows = read_database_rows("emails")
        assert len(rows) == 3


class TestLocalStorageWrite:
    """Tests for overwriting / full-replace of local Excel files."""

    def test_write_overwrites_previous_data(self, local_user):
        from core.storage.engine import write_database_rows, read_database_rows
        write_database_rows("emails", SAMPLE_EMAILS[:2])
        write_database_rows("emails", SAMPLE_EMAILS[2:])  # overwrite with 2 different rows
        rows = read_database_rows("emails")
        assert len(rows) == 2
        assert rows[0]["Email"] == SAMPLE_EMAILS[2]["Email"]

    def test_write_empty_list_clears_table(self, local_user):
        from core.storage.engine import write_database_rows, read_database_rows
        write_database_rows("emails", SAMPLE_EMAILS)
        write_database_rows("emails", [])
        rows = read_database_rows("emails")
        assert rows == []


class TestLocalStorageProviderConfig:
    """Tests for LocalStorageProvider config read/write."""

    def test_get_config_returns_correct_keys(self, local_user):
        from core.storage.engine import get_user_config
        cfg = get_user_config()
        assert "profile" in cfg
        assert "email_scraper" in cfg
        assert "linkedin_connect" in cfg
        assert "global_settings" in cfg

    def test_save_config_persists_changes(self, local_user, tmp_path):
        from core.storage.engine import get_user_config, save_user_config
        cfg = get_user_config()
        cfg["profile"]["first_name"] = "UpdatedName"
        save_user_config(cfg)

        import core.storage.engine as eng
        eng._invalidate_cached_config(local_user["username"])
        eng.StorageManager._instance = None

        refreshed = get_user_config()
        assert refreshed["profile"]["first_name"] == "UpdatedName"


# ===========================================================================
#  CACHE LAYER TESTS
# ===========================================================================

class TestCacheLayer:
    """Tests for the in-memory TTL caching layer on top of storage providers."""

    def test_second_read_uses_cache(self, local_user, monkeypatch):
        """After first read, second read should not re-read from disk."""
        from core.storage.engine import read_database_rows, write_database_rows, LocalStorageProvider

        write_database_rows("emails", SAMPLE_EMAILS[:2])
        _ = read_database_rows("emails")  # prime the cache

        read_count = {"n": 0}
        original_read = LocalStorageProvider.read_rows

        def counting_read(self, username, table_key):
            read_count["n"] += 1
            return original_read(self, username, table_key)

        monkeypatch.setattr(LocalStorageProvider, "read_rows", counting_read)
        _ = read_database_rows("emails")
        # Cache hit: disk read should NOT be called again
        assert read_count["n"] == 0, "Cache miss on second read"

    def test_write_invalidates_cache(self, local_user, monkeypatch):
        """After write, the next read should fetch fresh data from disk."""
        from core.storage.engine import (
            read_database_rows, write_database_rows, _invalidate_cached_rows
        )
        write_database_rows("emails", SAMPLE_EMAILS[:1])
        _ = read_database_rows("emails")  # prime cache

        write_database_rows("emails", SAMPLE_EMAILS[:3])  # this should invalidate cache
        rows = read_database_rows("emails")
        assert len(rows) == 3, "Cache was not invalidated after write"

    def test_cache_ttl_respected(self, local_user, monkeypatch):
        """After cache expires (simulated), next read fetches from disk."""
        import core.storage.engine as eng
        from core.storage.engine import read_database_rows, write_database_rows

        write_database_rows("emails", SAMPLE_EMAILS[:1])
        _ = read_database_rows("emails")

        # Expire the cache manually by setting timestamp far in the past
        username = local_user["username"]
        with eng._cache_lock:
            if (username, "emails") in eng._row_cache:
                eng._row_cache[(username, "emails")] = (0, eng._row_cache[(username, "emails")][1])

        write_database_rows("emails", SAMPLE_EMAILS[:4])  # update disk data

        rows = read_database_rows("emails")
        assert len(rows) == 4, "Stale cache served after TTL expiry"


# ===========================================================================
#  GOOGLE SHEETS STORAGE PROVIDER TESTS (mocked)
# ===========================================================================

class TestSheetsStorageRead:
    def test_read_empty_sheets_returns_empty_list(self, sheets_user):
        from core.storage.engine import read_database_rows
        rows = read_database_rows("emails")
        assert rows == []

    def test_append_then_read_sheets(self, sheets_user):
        from core.storage.engine import append_database_row, read_database_rows
        row = SAMPLE_EMAILS[0]
        append_database_row("emails", row)
        rows = read_database_rows("emails")
        assert len(rows) == 1
        assert rows[0]["Email"] == row["Email"]

    def test_write_then_read_sheets(self, sheets_user):
        from core.storage.engine import write_database_rows, read_database_rows
        write_database_rows("jobs", SAMPLE_JOBS)
        rows = read_database_rows("jobs")
        assert len(rows) == len(SAMPLE_JOBS)

    def test_sheets_write_overwrite(self, sheets_user):
        from core.storage.engine import write_database_rows, read_database_rows
        write_database_rows("emails", SAMPLE_EMAILS)
        write_database_rows("emails", SAMPLE_EMAILS[:1])
        rows = read_database_rows("emails")
        assert len(rows) == 1


class TestSheetsConfigRead:
    def test_get_config_returns_expected_keys(self, sheets_user):
        """Even with mocked sheets, config read falls back to local bootstrap config."""
        from core.storage.engine import get_user_config
        cfg = get_user_config()
        assert "profile" in cfg
        assert cfg["global_settings"]["database_type"] == "google_sheets"
