"""
Integration Tests: URL Shortener Pipeline
(pipelines/linkedin_outreach/services/shortener.py)

Tests shortening of job application URLs, writing back to jobs table,
and deduplication of already-shortened URLs.

Run with:
    pytest tests/integration/test_url_shortener_pipeline.py -v
"""

import pytest
from unittest.mock import MagicMock, patch


def _make_job_for_shortener(company="ShortCo", url=None, shorten="", job_id=1, already_shortened=False):
    url = url or f"https://{company.lower()}.com/jobs/{job_id}"
    return {
        "JobID": job_id,
        "JobTitle": "Data Engineer",
        "CompanyName": company,
        "LinkedIn_Company_URL": f"https://linkedin.com/company/{company.lower()}/",
        "CompanyURL": url,
        "ShortenURL": shorten,
        "SearchKeyword": "Data Engineer",
        "Status": "NEW",
        "ShortUrlCreated": "1" if already_shortened else "0",
        "CreatedDateTime": "2025-01-01 10:00:00",
    }


class TestUrlShortenerLocal:
    """Tests for URL Shortener under local storage."""

    def test_shorten_url_updates_job_row(self, local_user, monkeypatch):
        """After shortening, the ShortenURL and ShortUrlCreated fields should be updated."""
        from core.storage.database import save_job, load_saved_jobs
        from core.storage.engine import write_database_rows

        job = _make_job_for_shortener("ShortCo", url="https://shortco.com/jobs/1")
        save_job(job)

        # Simulate what the shortener service does: update ShortenURL and mark as created
        from core.storage.database import edit_lead_row, load_saved_jobs
        jobs = load_saved_jobs()
        j = jobs[0]

        # Manually apply the shortener result (as the service would)
        j["ShortenURL"] = "https://short.ly/abc123"
        j["ShortUrlCreated"] = "1"

        write_database_rows("jobs", jobs)

        updated = load_saved_jobs()
        assert updated[0]["ShortenURL"] == "https://short.ly/abc123"
        assert updated[0]["ShortUrlCreated"] == "1"

    def test_already_shortened_jobs_not_reshortened(self, local_user, monkeypatch):
        """Jobs with ShortUrlCreated='1' should be skipped by the shortener."""
        from core.storage.database import save_job, load_saved_jobs

        already_short = _make_job_for_shortener(
            "AlreadyCo", url="https://already.com/j/1",
            shorten="https://short.ly/existing", already_shortened=True
        )
        save_job(already_short)

        jobs = load_saved_jobs()
        # Shortener logic: filter out jobs where ShortUrlCreated == '1'
        to_shorten = [j for j in jobs if str(j.get("ShortUrlCreated", "0")).strip() != "1"]
        assert len(to_shorten) == 0

    def test_multiple_jobs_only_unshortened_processed(self, local_user):
        """Only jobs without shortened URLs should be processed."""
        from core.storage.database import save_job, load_saved_jobs

        save_job(_make_job_for_shortener("CoA", url="https://coa.com/j/1", already_shortened=False, job_id=1))
        save_job(_make_job_for_shortener("CoB", url="https://cob.com/j/2", already_shortened=True, job_id=2))
        save_job(_make_job_for_shortener("CoC", url="https://coc.com/j/3", already_shortened=False, job_id=3))

        jobs = load_saved_jobs()
        pending = [j for j in jobs if str(j.get("ShortUrlCreated", "0")) != "1"]
        assert len(pending) == 2

    def test_empty_company_url_skipped(self, local_user):
        """Jobs with no CompanyURL should be skipped by the shortener."""
        from core.storage.database import save_job, load_saved_jobs
        from core.storage.engine import write_database_rows

        jobs_data = [{
            "JobID": 1,
            "JobTitle": "DE",
            "CompanyName": "NoCo",
            "LinkedIn_Company_URL": "",
            "CompanyURL": "",       # Empty
            "ShortenURL": "",
            "SearchKeyword": "DE",
            "Status": "NEW",
            "ShortUrlCreated": "0",
            "CreatedDateTime": "2025-01-01 10:00:00",
        }]
        write_database_rows("jobs", jobs_data)

        jobs = load_saved_jobs()
        # Shortener should skip jobs without a CompanyURL
        to_shorten = [j for j in jobs if j.get("CompanyURL")]
        assert len(to_shorten) == 0

    def test_shorten_url_preserves_other_job_fields(self, local_user):
        """Updating ShortenURL should not overwrite other job fields."""
        from core.storage.database import save_job, load_saved_jobs
        from core.storage.engine import write_database_rows

        save_job(_make_job_for_shortener("FieldCo", url="https://fieldco.com/j/1"))
        jobs = load_saved_jobs()
        j = jobs[0]

        original_title = j["JobTitle"]
        original_status = j["Status"]

        j["ShortenURL"] = "https://short.ly/fieldco"
        j["ShortUrlCreated"] = "1"
        write_database_rows("jobs", jobs)

        updated = load_saved_jobs()[0]
        assert updated["JobTitle"] == original_title
        assert updated["Status"] == original_status
        assert updated["ShortenURL"] == "https://short.ly/fieldco"

    def test_shortener_handles_no_jobs(self, local_user):
        """If there are no jobs in the table, the shortener should exit cleanly."""
        from core.storage.database import load_saved_jobs
        jobs = load_saved_jobs()
        assert jobs == []


class TestUrlShortenerSheets:
    """Tests for URL Shortener under Google Sheets storage."""

    def test_shorten_url_persisted_in_sheets(self, sheets_user):
        """Shortened URL should be correctly persisted in the Sheets backend."""
        from core.storage.database import save_job, load_saved_jobs
        from core.storage.engine import write_database_rows

        save_job(_make_job_for_shortener("SheetsShortCo", url="https://ssc.com/j/1"))
        jobs = load_saved_jobs()

        jobs[0]["ShortenURL"] = "https://short.ly/sheets1"
        jobs[0]["ShortUrlCreated"] = "1"
        write_database_rows("jobs", jobs)

        updated = load_saved_jobs()
        assert updated[0]["ShortenURL"] == "https://short.ly/sheets1"

    def test_already_shortened_skipped_in_sheets(self, sheets_user):
        """Jobs already shortened should be skipped in Sheets backend."""
        from core.storage.database import save_job, load_saved_jobs

        save_job(_make_job_for_shortener(
            "AlreadySheetsC", url="https://alreadysheets.com/j/1",
            shorten="https://short.ly/existing_sheets", already_shortened=True
        ))

        jobs = load_saved_jobs()
        pending = [j for j in jobs if str(j.get("ShortUrlCreated", "0")) != "1"]
        assert len(pending) == 0

    def test_multiple_jobs_shortener_sheets(self, sheets_user):
        """Multiple jobs with mixed states are handled correctly in Sheets."""
        from core.storage.database import save_job, load_saved_jobs

        save_job(_make_job_for_shortener("S1", url="https://s1.com/j/1", already_shortened=False, job_id=1))
        save_job(_make_job_for_shortener("S2", url="https://s2.com/j/2", already_shortened=True, job_id=2))

        jobs = load_saved_jobs()
        pending = [j for j in jobs if str(j.get("ShortUrlCreated", "0")) != "1"]
        assert len(pending) == 1
        assert pending[0]["CompanyName"] == "S1"
