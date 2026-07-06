"""
Unit Tests: Database Layer (core/storage/database.py)

Tests all public CRUD functions for emails, jobs, and referrals tables,
including deduplication logic, status transitions, and helper queries.

Run with:
    pytest tests/unit/test_database_layer.py -v
"""

import pytest
from tests.fixtures.sample_data import SAMPLE_EMAILS, SAMPLE_JOBS, SAMPLE_REFERRALS


# ===========================================================================
#  EMAILS TABLE TESTS
# ===========================================================================

class TestAppendEmail:
    def test_append_new_email_succeeds(self, local_user):
        from core.storage.database import append_email, count_unique_emails
        result = append_email("new@company.com", keyword="Data Engineer", post_url="https://li.com/p/1")
        assert result is True
        assert count_unique_emails() == 1

    def test_append_duplicate_email_returns_false(self, local_user):
        from core.storage.database import append_email
        append_email("dup@company.com")
        result = append_email("dup@company.com")
        assert result is False

    def test_append_email_case_insensitive_dedup(self, local_user):
        from core.storage.database import append_email
        append_email("User@Company.COM")
        result = append_email("user@company.com")  # lowercase duplicate
        assert result is False

    def test_append_multiple_unique_emails(self, local_user):
        from core.storage.database import append_email, count_unique_emails
        for email in ["a@x.com", "b@x.com", "c@x.com"]:
            append_email(email)
        assert count_unique_emails() == 3

    def test_append_email_stores_all_fields(self, local_user):
        from core.storage.database import append_email, read_database_rows
        from core.storage.engine import read_database_rows as read_rows
        append_email(
            "full@company.com",
            keyword="ETL Engineer",
            post_url="https://li.com/p/full",
            company_name="FullCo",
            experience="5 years",
            location="Pune",
        )
        rows = read_rows("emails")
        row = next(r for r in rows if r["Email"] == "full@company.com")
        assert row["Keyword"] == "ETL Engineer"
        assert row["CompanyName"] == "FullCo"
        assert row["Location"] == "Pune"
        assert row["Status"] == "New"

    def test_append_email_auto_increments_id(self, local_user):
        from core.storage.database import append_email
        from core.storage.engine import read_database_rows
        append_email("first@test.com")
        append_email("second@test.com")
        rows = read_database_rows("emails")
        ids = [int(float(r["ID"])) for r in rows]
        assert ids == [1, 2]


class TestUpdateEmailStatus:
    def test_update_status_to_sent(self, local_user):
        from core.storage.database import append_email, update_status
        from core.storage.engine import read_database_rows
        append_email("target@company.com")
        result = update_status("target@company.com", "sent")
        assert result is True
        rows = read_database_rows("emails")
        assert rows[0]["Status"] == "sent"

    def test_update_status_to_skipped(self, local_user):
        from core.storage.database import append_email, update_status
        from core.storage.engine import read_database_rows
        append_email("skip@company.com")
        update_status("skip@company.com", "skipped")
        rows = read_database_rows("emails")
        assert rows[0]["Status"] == "skipped"

    def test_update_status_nonexistent_email_returns_false(self, local_user):
        from core.storage.database import update_status
        result = update_status("ghost@nowhere.com", "sent")
        assert result is False

    def test_update_status_case_insensitive(self, local_user):
        from core.storage.database import append_email, update_status
        from core.storage.engine import read_database_rows
        append_email("CASE@Test.COM")
        result = update_status("case@test.com", "sent")
        assert result is True

    def test_update_status_updates_timestamp(self, local_user):
        from core.storage.database import append_email, update_status
        from core.storage.engine import read_database_rows
        import time
        append_email("ts@test.com")
        time.sleep(0.01)  # ensure timestamp changes
        update_status("ts@test.com", "sent")
        rows = read_database_rows("emails")
        assert rows[0]["Timestamp"] != ""


class TestEmailHelpers:
    def test_count_unique_emails_empty(self, local_user):
        from core.storage.database import count_unique_emails
        assert count_unique_emails() == 0

    def test_edit_row_updates_fields(self, local_user):
        from core.storage.database import append_email, edit_row
        from core.storage.engine import read_database_rows
        append_email("edit@test.com", keyword="Old Keyword")
        rows = read_database_rows("emails")
        row_id = rows[0]["ID"]
        edit_row(row_id, "edit@test.com", "sent", "New Keyword", post_url="https://li.com/new")
        rows = read_database_rows("emails")
        assert rows[0]["Keyword"] == "New Keyword"
        assert rows[0]["Status"] == "sent"


# ===========================================================================
#  JOBS TABLE TESTS
# ===========================================================================

class TestSaveJob:
    def _job(self, company="TestCo", url="https://testco.com/jobs/1", title="Data Engineer"):
        return {
            "JobTitle": title,
            "CompanyName": company,
            "LinkedIn_Company_URL": f"https://linkedin.com/company/{company.lower()}/",
            "CompanyURL": url,
            "ShortenURL": "",
            "SearchKeyword": "Data Engineer",
            "Status": "NEW",
        }

    def test_save_new_job_succeeds(self, local_user):
        from core.storage.database import save_job, load_saved_jobs
        result = save_job(self._job())
        assert result is True
        assert len(load_saved_jobs()) == 1

    def test_save_duplicate_job_url_returns_false(self, local_user):
        from core.storage.database import save_job
        save_job(self._job())
        result = save_job(self._job())  # same URL
        assert result is False

    def test_save_multiple_unique_jobs(self, local_user):
        from core.storage.database import save_job, load_saved_jobs
        for i in range(3):
            save_job(self._job(company=f"Co{i}", url=f"https://co{i}.com/jobs/1"))
        assert len(load_saved_jobs()) == 3

    def test_job_auto_increments_id(self, local_user):
        from core.storage.database import save_job, load_saved_jobs
        save_job(self._job(company="A", url="https://a.com/j/1"))
        save_job(self._job(company="B", url="https://b.com/j/2"))
        jobs = load_saved_jobs()
        ids = [int(float(j["JobID"])) for j in jobs]
        assert ids == [1, 2]


class TestJobStatusUpdate:
    def test_update_status_by_id(self, local_user):
        from core.storage.database import save_job, update_status_by_id, load_saved_jobs
        save_job({"JobTitle": "DE", "CompanyName": "Co", "LinkedIn_Company_URL": "", "CompanyURL": "https://co.io/j/1", "ShortenURL": "", "SearchKeyword": "DE", "Status": "NEW"})
        jobs = load_saved_jobs()
        job_id = jobs[0]["JobID"]
        update_status_by_id(job_id, "Asked for Referral")
        jobs = load_saved_jobs()
        assert jobs[0]["Status"] == "Asked for Referral"

    def test_update_nonexistent_job_returns_false(self, local_user):
        from core.storage.database import update_status_by_id
        result = update_status_by_id(9999, "sent")
        assert result is False

    def test_load_jobs_for_referral_filters_correctly(self, local_user):
        from core.storage.engine import write_database_rows
        from core.storage.database import load_jobs_for_referral
        write_database_rows("jobs", SAMPLE_JOBS)
        referral_jobs = load_jobs_for_referral(status_filter="Asked for Referral")
        assert all(j["Status"] == "Asked for Referral" for j in referral_jobs)
        assert len(referral_jobs) == 1


# ===========================================================================
#  REFERRALS TABLE TESTS
# ===========================================================================

class TestAddOrUpdateReferral:
    def _referral(self, profile_url="https://li.com/in/person1/", job_id="1", company="TechCo", status="pending"):
        return {
            "JobID": job_id,
            "CompanyName": company,
            "Company_URL": f"https://linkedin.com/company/{company.lower()}/",
            "JobTitle": "Data Engineer",
            "Job_URL": "https://co.com/j/1",
            "Referral_Person_Name": "Test Person",
            "Referral_Person_Profile_URL": profile_url,
            "Referral_Source": "existing employee",
            "Referral_Status": status,
            "Outreach_Message": "Hi!",
            "Response_Notes": "",
            "DateTime": "2025-01-01 10:00:00",
        }

    def test_add_new_referral(self, local_user):
        from core.storage.database import add_or_update_referral, load_all_referrals
        add_or_update_referral(self._referral())
        assert len(load_all_referrals()) == 1

    def test_update_existing_referral(self, local_user):
        from core.storage.database import add_or_update_referral, load_all_referrals
        add_or_update_referral(self._referral(status="pending"))
        add_or_update_referral(self._referral(status="sent"))  # same profile + job_id
        referrals = load_all_referrals()
        assert len(referrals) == 1
        assert referrals[0]["Referral_Status"] == "sent"

    def test_is_profile_already_contacted(self, local_user):
        from core.storage.database import add_or_update_referral, is_profile_already_contacted
        url = "https://li.com/in/targetperson/"
        add_or_update_referral(self._referral(profile_url=url))
        assert is_profile_already_contacted(url) is True
        assert is_profile_already_contacted("https://li.com/in/unknown/") is False

    def test_get_company_sent_count(self, local_user):
        from core.storage.database import add_or_update_referral, get_company_sent_count
        add_or_update_referral(self._referral(profile_url="https://li.com/in/p1/", status="sent"))
        add_or_update_referral(self._referral(profile_url="https://li.com/in/p2/", status="pending"))
        assert get_company_sent_count("TechCo") == 1

    def test_referrals_auto_increment_id(self, local_user):
        from core.storage.database import add_or_update_referral, load_all_referrals
        add_or_update_referral(self._referral(profile_url="https://li.com/in/p1/"))
        add_or_update_referral(self._referral(profile_url="https://li.com/in/p2/"))
        referrals = load_all_referrals()
        ids = [int(float(r["ReferralID"])) for r in referrals]
        assert ids == [1, 2]


class TestGetSheetsConfig:
    def test_local_user_returns_none(self, local_user):
        from core.storage.database import get_sheets_config
        result = get_sheets_config()
        assert result is None

    def test_sheets_user_returns_url_and_creds(self, sheets_user):
        from core.storage.database import get_sheets_config
        result = get_sheets_config()
        assert result is not None
        url, creds = result
        assert "docs.google.com" in url
        assert "service_account" in creds
