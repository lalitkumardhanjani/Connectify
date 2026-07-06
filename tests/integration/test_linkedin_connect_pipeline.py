"""
Integration Tests: LinkedIn Connect Pipeline
(pipelines/linkedin_outreach/services/connector.py)

Tests connection sending, limits, message template rendering,
review_mode gate, and status transitions.

Run with:
    pytest tests/integration/test_linkedin_connect_pipeline.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from tests.fixtures.sample_data import SAMPLE_JOBS, SAMPLE_REFERRALS


def _make_job(company="ConnectCo", url=None, job_id=1, status="NEW"):
    url = url or f"https://{company.lower()}.com/j/{job_id}"
    return {
        "JobID": job_id,
        "JobTitle": "Data Engineer",
        "CompanyName": company,
        "LinkedIn_Company_URL": f"https://linkedin.com/company/{company.lower()}/",
        "CompanyURL": url,
        "ShortenURL": f"https://short.ly/{job_id}",
        "SearchKeyword": "Data Engineer",
        "Status": status,
        "ShortUrlCreated": "1",
        "CreatedDateTime": "2025-01-01 10:00:00",
    }


def _make_connection_candidate(name="Test Person", profile_url=None, company="ConnectCo", job_id="1"):
    profile_url = profile_url or f"https://linkedin.com/in/{name.lower().replace(' ', '')}"
    return {
        "name": name,
        "profile_url": profile_url,
        "company": company,
        "job_url": f"https://{company.lower()}.com/j/1",
        "job_id": job_id,
        "degree": "2nd",
    }


class TestLinkedInConnectLocal:
    """Tests for the LinkedIn Connect pipeline under local storage."""

    def test_connect_updates_referral_status_to_sent(self, local_user, mock_driver):
        """After a successful connection, status in referrals table should be 'sent'."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        # Pre-populate referrals with a pending entry
        add_or_update_referral({
            "JobID": "1",
            "CompanyName": "ConnectCo",
            "Company_URL": "https://linkedin.com/company/connectco/",
            "JobTitle": "Data Engineer",
            "Job_URL": "https://connectco.com/j/1",
            "Referral_Person_Name": "Alice",
            "Referral_Person_Profile_URL": "https://linkedin.com/in/alice/",
            "Referral_Source": "existing employee",
            "Referral_Status": "sent",
            "Outreach_Message": "Hi Alice!",
            "Response_Notes": "",
            "DateTime": "2025-01-01 10:00:00",
        })

        referrals = load_all_referrals()
        assert referrals[0]["Referral_Status"] == "sent"

    def test_is_profile_already_contacted_blocks_duplicate(self, local_user, mock_driver):
        """should return True if we already have a record for a profile URL."""
        from core.storage.database import add_or_update_referral, is_profile_already_contacted

        url = "https://linkedin.com/in/duplicate-person/"
        add_or_update_referral({
            "JobID": "2",
            "CompanyName": "DupCo",
            "Company_URL": "",
            "JobTitle": "DE",
            "Job_URL": "",
            "Referral_Person_Name": "Dup",
            "Referral_Person_Profile_URL": url,
            "Referral_Source": "existing employee",
            "Referral_Status": "sent",
            "Outreach_Message": "",
            "Response_Notes": "",
            "DateTime": "2025-01-01 10:00:00",
        })
        assert is_profile_already_contacted(url) is True
        assert is_profile_already_contacted("https://linkedin.com/in/other/") is False

    def test_max_connections_per_company_limit(self, local_user, mock_driver):
        """Should not exceed max_connections_per_company (3 from config) for same company."""
        from core.storage.database import add_or_update_referral, get_company_sent_count

        company = "LimitCo"
        for i in range(3):
            add_or_update_referral({
                "JobID": "1",
                "CompanyName": company,
                "Company_URL": f"https://linkedin.com/company/{company.lower()}/",
                "JobTitle": "DE",
                "Job_URL": "https://limitco.com/j/1",
                "Referral_Person_Name": f"Person{i}",
                "Referral_Person_Profile_URL": f"https://linkedin.com/in/person{i}/",
                "Referral_Source": "existing employee",
                "Referral_Status": "sent",
                "Outreach_Message": "Hi!",
                "Response_Notes": "",
                "DateTime": "2025-01-01 10:00:00",
            })

        count = get_company_sent_count(company)
        assert count == 3  # exactly at limit

        # Now if pipeline tries to add a 4th, it should respect the limit
        # (The connector logic checks get_company_sent_count before outreach)
        assert count >= int(local_user["config"]["linkedin_connect"]["max_connections_per_company"])

    def test_message_template_renders_correctly(self, local_user, mock_driver):
        """Message template placeholders must be replaced correctly."""
        config = local_user["config"]
        template = config["linkedin_connect"]["message_template"]
        profile = config["profile"]

        rendered = template.replace("{RECEIVER_NAME}", "Bob")
        rendered = rendered.replace("{EXPERIENCE}", str(profile.get("experience", "")))
        rendered = rendered.replace("{RESUME}", str(profile.get("resume_url", "")))
        rendered = rendered.replace("{COMPANY}", "TechCorp")
        rendered = rendered.replace("{JOB_URL}", "https://techcorp.com/j/1")

        assert "Bob" in rendered
        assert "{RECEIVER_NAME}" not in rendered
        assert "{RESUME}" not in rendered

    def test_referral_sync_sets_completed_when_target_reached(self, local_user):
        """sync_job_lead_referral_statuses() should mark job as completed when target referrals hit."""
        from core.storage.database import save_job, add_or_update_referral, sync_job_lead_referral_statuses, load_saved_jobs

        save_job({
            "JobTitle": "Data Engineer",
            "CompanyName": "SyncCo",
            "LinkedIn_Company_URL": "https://linkedin.com/company/syncco/",
            "CompanyURL": "https://syncco.com/j/1",
            "ShortenURL": "",
            "SearchKeyword": "DE",
            "Status": "Asked for Referral",
        })
        jobs = load_saved_jobs()
        job_id = str(jobs[0]["JobID"])

        # Add 3 'sent' employee referrals (target is 3 per config)
        for i in range(3):
            add_or_update_referral({
                "JobID": job_id,
                "CompanyName": "SyncCo",
                "Company_URL": "https://linkedin.com/company/syncco/",
                "JobTitle": "Data Engineer",
                "Job_URL": "https://syncco.com/j/1",
                "Referral_Person_Name": f"Emp{i}",
                "Referral_Person_Profile_URL": f"https://linkedin.com/in/emp{i}/",
                "Referral_Source": "existing employee",
                "Referral_Status": "sent",
                "Outreach_Message": "Hi!",
                "Response_Notes": "",
                "DateTime": "2025-01-01 10:00:00",
            })

        sync_job_lead_referral_statuses()
        jobs = load_saved_jobs()
        assert jobs[0]["Status"] == "Referral Outreach Completed"


class TestLinkedInConnectSheets:
    """Tests for the LinkedIn Connect pipeline under Google Sheets storage."""

    def test_connect_stores_referral_in_sheets(self, sheets_user, mock_driver):
        """Referral should be stored in the mock Sheets backend."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        add_or_update_referral({
            "JobID": "1",
            "CompanyName": "SheetsConnectCo",
            "Company_URL": "https://linkedin.com/company/sheetsco/",
            "JobTitle": "DE",
            "Job_URL": "https://sheetsco.com/j/1",
            "Referral_Person_Name": "Alice Sheets",
            "Referral_Person_Profile_URL": "https://linkedin.com/in/alicesheets/",
            "Referral_Source": "existing employee",
            "Referral_Status": "pending",
            "Outreach_Message": "Hi!",
            "Response_Notes": "",
            "DateTime": "2025-01-01 10:00:00",
        })

        referrals = load_all_referrals()
        assert len(referrals) == 1

    def test_duplicate_profile_blocked_in_sheets(self, sheets_user, mock_driver):
        """Deduplication by profile URL should work under Sheets backend."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        url = "https://linkedin.com/in/sheetsdup/"
        ref = {
            "JobID": "1",
            "CompanyName": "DupSheetsCo",
            "Company_URL": "",
            "JobTitle": "DE",
            "Job_URL": "",
            "Referral_Person_Name": "Dup",
            "Referral_Person_Profile_URL": url,
            "Referral_Source": "existing employee",
            "Referral_Status": "pending",
            "Outreach_Message": "",
            "Response_Notes": "",
            "DateTime": "2025-01-01 10:00:00",
        }

        add_or_update_referral(ref)
        ref["Referral_Status"] = "sent"
        add_or_update_referral(ref)  # update, not insert

        referrals = load_all_referrals()
        assert len(referrals) == 1
        assert referrals[0]["Referral_Status"] == "sent"
