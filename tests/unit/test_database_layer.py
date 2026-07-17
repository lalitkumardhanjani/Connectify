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

    def test_save_job_missing_fields_returns_false(self, local_user):
        from core.storage.database import save_job, load_saved_jobs
        # Missing CompanyName
        assert save_job(self._job(company="")) is False
        # Missing JobTitle
        result = save_job({
            "CompanyName": "TestCo",
            "CompanyURL": "https://test.com/j1",
            "JobTitle": ""
        })
        assert result is False
        # Missing CompanyURL
        assert save_job(self._job(url="")) is False
        assert len(load_saved_jobs()) == 0


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


class TestCompositeUniquenessConstraints:
    def test_append_email_email_only_uniqueness(self, local_user):
        from core.storage.database import append_email, read_database_rows
        assert append_email("test@domain.com", post_url="https://post.com/1") is True
        assert append_email("test@domain.com", post_url="https://post.com/1") is False
        assert append_email("test@domain.com", post_url="https://post.com/2") is False
        assert append_email("other@domain.com", post_url="https://post.com/1") is True
        assert len(read_database_rows("emails")) == 2

    def test_save_job_composite_uniqueness(self, local_user):
        from core.storage.database import save_job, load_saved_jobs
        j1 = {"JobTitle": "SWE", "CompanyName": "CoA", "LinkedIn_Company_URL": "https://li.com/coa", "CompanyURL": "https://apply.com/1", "Status": "NEW"}
        j2 = {"JobTitle": "SWE", "CompanyName": "CoB", "LinkedIn_Company_URL": "https://li.com/cob", "CompanyURL": "https://apply.com/1", "Status": "NEW"}
        
        assert save_job(j1) is True
        assert save_job(j1) is False
        assert save_job(j2) is True
        assert len(load_saved_jobs()) == 2

    def test_add_or_update_referral_composite_uniqueness(self, local_user):
        from core.storage.database import add_or_update_referral, load_all_referrals
        r1 = {"JobID": "1", "JobTitle": "SWE", "CompanyName": "CoA", "Job_URL": "https://apply.com/1", "Referral_Person_Name": "P1", "Referral_Person_Profile_URL": "https://li.com/in/p1", "Referral_Status": "NEW"}
        r2 = {"JobID": "2", "JobTitle": "SWE", "CompanyName": "CoB", "Job_URL": "https://apply.com/2", "Referral_Person_Name": "P1", "Referral_Person_Profile_URL": "https://li.com/in/p1", "Referral_Status": "NEW"}
        
        assert add_or_update_referral(r1) is True
        assert add_or_update_referral(r1) is True
        assert len(load_all_referrals()) == 1
        assert add_or_update_referral(r2) is True
        assert len(load_all_referrals()) == 2

    def test_deduplicate_all_tables_cleans_existing(self, local_user):
        from core.storage.database import deduplicate_all_tables
        from core.storage.engine import write_database_rows, read_database_rows
        
        emails = [
            {'ID': 1, 'Email': 'a@a.com', 'PostURL': 'http://a.com', 'Status': 'New'},
            {'ID': 2, 'Email': 'a@a.com', 'PostURL': 'http://a.com', 'Status': 'New'},
            {'ID': 3, 'Email': 'b@b.com', 'PostURL': 'http://b.com', 'Status': 'New'}
        ]
        write_database_rows("emails", emails)
        
        deduplicate_all_tables(local_user["username"])
        
        cleaned = read_database_rows("emails")
        assert len(cleaned) == 2

    def test_get_email_metrics_daily_counts(self, local_user):
        from core.storage.database import append_email, update_status
        from core.analytics.metrics import get_email_metrics
        
        # Add a generated email
        append_email("gen@a.com")
        
        # Add another email and update to sent
        append_email("sent@b.com")
        update_status("sent@b.com", "sent")
        
        metrics = get_email_metrics()
        daily = metrics["daily_counts"]
        
        assert len(daily) == 90
        
        # Today's daily stats should show 2 generated and 1 sent
        today_stats = daily[-1]
        assert today_stats["generated"] == 2
        assert today_stats["sent"] == 1
        assert metrics["sent_today"] == 1

    def test_get_company_metrics(self, local_user):
        from core.storage.database import save_job
        from core.analytics.metrics import get_company_metrics
        from core.storage.engine import read_database_rows, write_database_rows
        
        job1 = {
            "JobTitle": "Job 1",
            "CompanyName": "Company A",
            "Location": "New York",
            "CompanyURL": "http://a.com",
            "ShortenURL": "",
            "SearchKeyword": "Python",
            "Status": "NEW"
        }
        job2 = {
            "JobTitle": "Job 2",
            "CompanyName": "Company B",
            "Location": "New York",
            "CompanyURL": "http://b.com",
            "ShortenURL": "",
            "SearchKeyword": "Python",
            "Status": "NEW"
        }
        save_job(job1)
        save_job(job2)
        
        rows = read_database_rows("jobs")
        for r in rows:
            if r["CompanyName"] == "Company B":
                r["Status"] = "Interested"
            elif r["CompanyName"] == "Company A":
                r["Status"] = "Asked for Referral"
        write_database_rows("jobs", rows)
        
        metrics = get_company_metrics()
        assert metrics["total_companies"] == 2
        assert metrics["interested"] == 1
        assert metrics["referral_outreach"] == 1

class TestRobustMatching:
    def test_clean_company_name_for_match(self):
        from core.storage.database import clean_company_name_for_match
        assert clean_company_name_for_match("FetchJobs.co") == "fetchjobsco"
        assert clean_company_name_for_match("micro1") == "micro1"
        assert clean_company_name_for_match("Google, Inc.") == "google"
        assert clean_company_name_for_match("EXL Corp") == "exl"
        assert clean_company_name_for_match("General Mills India") == "generalmillsindia"
        assert clean_company_name_for_match("") == ""
        assert clean_company_name_for_match(None) == ""

    def test_compare_job_ids(self):
        from core.storage.database import compare_job_ids
        assert compare_job_ids("123", 123.0) is True
        assert compare_job_ids(123.0, 123) is True
        assert compare_job_ids("abc", "abc") is True
        assert compare_job_ids("abc", "123") is False
        assert compare_job_ids("15820_4420791253", "15820_4420791253") is True
        assert compare_job_ids(None, "") is True
        assert compare_job_ids("N/A", "n/a") is False  # Case sensitive exact match or type check, wait "N/A" and "n/a" don't match or maybe they do? Wait, compare_job_ids does id1_str == id2_str, which is "N/A" == "n/a" (False)
        assert compare_job_ids("N/A", "N/A") is True

    def test_get_company_metrics_today_counters(self, local_user):
        from core.storage.database import save_job, add_or_update_referral
        from core.analytics.metrics import get_company_metrics
        from datetime import datetime
        
        today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        job = {
            "JobTitle": "Data Engineer",
            "CompanyName": "Tech Corp",
            "Location": "India",
            "CompanyURL": "http://techcorp.com",
            "Status": "referred",
            "CreatedDateTime": today_str
        }
        save_job(job)
        
        ref = {
            "JobID": "123",
            "CompanyName": "Tech Corp",
            "Referral_Source": "Sent Employee Connection",
            "Referral_Status": "Sent",
            "Sent_Time": today_str
        }
        add_or_update_referral(ref)
        
        metrics = get_company_metrics()
        assert metrics["companies_added_today"] == 1
        assert metrics["connections_sent_today"] == 1
        assert metrics["total_connections"] == 1
        assert metrics["total_referrals"] == 1
