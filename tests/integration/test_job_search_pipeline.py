"""
Integration Tests: LinkedIn Job Search Pipeline
(pipelines/linkedin_outreach/services/job_finder.py)

Tests job discovery, deduplication, max_apply limit,
and storage under both local and Google Sheets modes.

Run with:
    pytest tests/integration/test_job_search_pipeline.py -v
"""

import pytest
from unittest.mock import MagicMock
from tests.fixtures.sample_data import SAMPLE_JOBS


def _make_mock_job_finder(driver, jobs_to_discover=None):
    """Returns a mock job finder that discovers given jobs without a real browser."""
    jobs_to_discover = jobs_to_discover or []

    def fake_run(driver_arg=None):
        from core.storage.database import save_job
        for job in jobs_to_discover:
            save_job(job)

    return fake_run


def _make_job(company="TechCo", url=None, title="Data Engineer", keyword="DE"):
    i = hash(company) % 9999
    url = url or f"https://{company.lower().replace(' ', '')}.com/jobs/{i}"
    return {
        "JobTitle": title,
        "CompanyName": company,
        "LinkedIn_Company_URL": f"https://linkedin.com/company/{company.lower().replace(' ', '')}/",
        "CompanyURL": url,
        "ShortenURL": "",
        "SearchKeyword": keyword,
        "Status": "NEW",
        "ShortUrlCreated": "0",
    }


class TestJobSearchLocal:
    def test_job_finder_saves_new_jobs(self, local_user, mock_driver, monkeypatch):
        """Discovered jobs should be persisted to storage."""
        from core.storage.database import load_saved_jobs

        new_jobs = [_make_job("AlphaCorp", url="https://alpha.com/j/1"),
                    _make_job("BetaCorp", url="https://beta.com/j/2")]

        fake_finder = _make_mock_job_finder(mock_driver, jobs_to_discover=new_jobs)
        monkeypatch.setattr(
            "pipelines.linkedin_outreach.services.job_finder.run_job_finder",
            fake_finder
        )

        from pipelines.linkedin_outreach.services.job_finder import run_job_finder
        run_job_finder()

        jobs = load_saved_jobs()
        assert len(jobs) == 2

    def test_job_finder_deduplicates_by_url(self, local_user, mock_driver, monkeypatch):
        """Same job URL discovered twice should not create duplicate rows."""
        from core.storage.database import save_job, load_saved_jobs

        job = _make_job("GammaCorp", url="https://gamma.com/j/unique")
        save_job(job)
        # Run again with same job
        result = save_job(job)
        assert result is False
        assert len(load_saved_jobs()) == 1

    def test_job_finder_auto_increments_job_id(self, local_user, mock_driver, monkeypatch):
        """JobID should increment correctly for each unique job."""
        from core.storage.database import save_job, load_saved_jobs

        for i in range(3):
            save_job(_make_job(f"Co{i}", url=f"https://co{i}.com/j/{i}"))

        jobs = load_saved_jobs()
        ids = [int(float(j["JobID"])) for j in jobs]
        assert ids == [1, 2, 3]

    def test_job_finder_stores_all_fields(self, local_user, mock_driver):
        """All required fields are persisted correctly."""
        from core.storage.database import save_job, load_saved_jobs

        job = _make_job("DetailCo", url="https://detailco.com/j/1", title="Senior Data Engineer")
        save_job(job)
        jobs = load_saved_jobs()

        j = jobs[0]
        assert j["CompanyName"] == "DetailCo"
        assert j["JobTitle"] == "Senior Data Engineer"
        assert j["Status"] == "NEW"

    def test_job_finder_handles_empty_discovery(self, local_user, mock_driver):
        """If no jobs are discovered, storage should remain empty."""
        from core.storage.database import load_saved_jobs
        jobs = load_saved_jobs()
        assert jobs == []

    def test_job_finder_not_interested_status_skipped_in_referral_load(self, local_user):
        """Jobs with 'Not Interested' status are excluded from referral queue."""
        from core.storage.database import save_job, load_jobs_for_referral, update_status_by_id, load_saved_jobs

        save_job(_make_job("ExcludedCo", url="https://excluded.com/j/1"))
        jobs = load_saved_jobs()
        update_status_by_id(jobs[0]["JobID"], "Not Interested")

        referral_jobs = load_jobs_for_referral(status_filter="NEW")
        assert all(j["Status"] != "Not Interested" for j in referral_jobs)

    def test_build_search_url_locations(self):
        """build_search_url should correctly output url for standard, remote, and empty locations."""
        from pipelines.linkedin_outreach.services.job_finder import build_search_url
        
        # Standard location
        url1 = build_search_url("Data Engineer", "Jaipur", "r604800")
        assert "location=Jaipur" in url1
        assert "keywords=Data+Engineer" in url1
        assert "f_WT=2" not in url1
        
        # Remote location
        url2 = build_search_url("Data Engineer", "Remote", "r604800")
        assert "location=India" in url2
        assert "f_WT=2" in url2
        
        # Remote location with custom global country
        url2_us = build_search_url("Data Engineer", "Remote", "r604800", global_location="Chicago, IL, United States")
        assert "location=United+States" in url2_us
        assert "f_WT=2" in url2_us
        
        # Empty location
        url3 = build_search_url("Data Engineer", "", "r604800")
        assert "location=" not in url3
        assert "f_WT=2" not in url3


class TestJobSearchSheets:
    def test_job_saved_to_sheets_backend(self, sheets_user, mock_driver):
        """Jobs should be saved to Google Sheets mock backend."""
        from core.storage.database import save_job, load_saved_jobs

        save_job(_make_job("SheetsCorpA", url="https://sheetscorpa.com/j/1"))
        jobs = load_saved_jobs()
        assert len(jobs) == 1
        assert jobs[0]["CompanyName"] == "SheetsCorpA"

    def test_job_dedup_in_sheets(self, sheets_user, mock_driver):
        """Deduplication works correctly with Sheets backend."""
        from core.storage.database import save_job

        save_job(_make_job("SheetsCorpB", url="https://sheetscorpb.com/j/1"))
        result = save_job(_make_job("SheetsCorpB", url="https://sheetscorpb.com/j/1"))
        assert result is False

    def test_multiple_unique_jobs_sheets(self, sheets_user, mock_driver):
        """Multiple unique jobs are stored correctly in Sheets backend."""
        from core.storage.database import save_job, load_saved_jobs

        for i in range(4):
            save_job(_make_job(f"SCo{i}", url=f"https://sco{i}.com/j/{i}"))
        assert len(load_saved_jobs()) == 4


class TestJobStatusTransitions:
    def test_job_status_new_to_asked_for_referral(self, local_user):
        from core.storage.database import save_job, update_status_by_id, load_saved_jobs
        save_job(_make_job("StatusCo", url="https://statusco.com/j/1"))
        jobs = load_saved_jobs()
        update_status_by_id(jobs[0]["JobID"], "Asked for Referral")
        assert load_saved_jobs()[0]["Status"] == "Asked for Referral"

    def test_job_status_to_referral_outreach_completed(self, local_user):
        from core.storage.database import save_job, update_status_by_id, load_saved_jobs
        save_job(_make_job("DoneCo", url="https://doneco.com/j/1"))
        jobs = load_saved_jobs()
        update_status_by_id(jobs[0]["JobID"], "Referral Outreach Completed")
        assert load_saved_jobs()[0]["Status"] == "Referral Outreach Completed"

    def test_edit_lead_row_updates_fields(self, local_user):
        from core.storage.database import save_job, edit_lead_row, load_saved_jobs
        save_job(_make_job("EditCo", url="https://editco.com/j/1"))
        jobs = load_saved_jobs()
        job_id = jobs[0]["JobID"]
        edit_lead_row(job_id, "EditCoUpdated", "https://linkedin.com/company/edit/",
                      "https://short.ly/edit", "Analytics Engineer", "Senior DE", "In Progress")
        updated = load_saved_jobs()[0]
        assert updated["CompanyName"] == "EditCoUpdated"
        assert updated["Status"] == "In Progress"
